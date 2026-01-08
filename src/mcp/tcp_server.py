import asyncio
import json
import logging
import traceback

from src.tools.database import describe_table, list_tables, query_sql, search_definitions

# Map tool names to functions
TOOL_MAP = {
    "list_tables": list_tables,
    "query_sql": query_sql,
    "describe_table": describe_table,
    "search_definitions": search_definitions,
}

logger = logging.getLogger(__name__)


async def handle_client(reader, writer):
    """
    Handles a single TCP client connection.
    Implements a simple JSON-RPC style protocol for the Sandbox shim.
    """
    addr = writer.get_extra_info("peername")
    print(f"DEBUG: Accepted connection from {addr}")

    try:
        while True:
            data = await reader.readline()
            if not data:
                print(f"DEBUG: Client {addr} disconnected (EOF)")
                break

            message = data.decode().strip()
            if not message:
                continue

            # It's a JSON-RPC message
            try:
                req = json.loads(message)
            except json.JSONDecodeError:
                print(f"DEBUG: Invalid JSON from {addr}")
                continue

            resp = None
            method = req.get("method")
            msg_id = req.get("id")

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "CivicAudit TCP", "version": "2.0"},
                    },
                }

            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})

                try:
                    if name not in TOOL_MAP:
                        raise ValueError(f"Tool '{name}' not found.")

                    tool_func = TOOL_MAP[name]
                    
                    # Call the tool (synchronous tools)
                    result = tool_func(**args)

                    # Serialize result
                    # Shim expects formatted content or structuredContent
                    # Our tools return strings mostly, or lists of dicts (for query_sql)
                    if isinstance(result, (dict, list)):
                        text_content = json.dumps(result, default=str)
                    else:
                        text_content = str(result)

                    content_list = [{"type": "text", "text": text_content}]

                    resp = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"content": content_list},
                    }
                except Exception as e:
                    logger.error(f"Tool call error: {e}")
                    traceback.print_exc()
                    resp = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32000, "message": str(e)},
                    }

            if resp:
                resp_str = json.dumps(resp) + "\n"
                writer.write(resp_str.encode())
                await writer.drain()

    except Exception as e:
        print(f"Connection Error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()


async def start_tcp_server(host="0.0.0.0", port=8000):
    server = await asyncio.start_server(handle_client, host, port)

    addr = server.sockets[0].getsockname()
    print(f"Serving TCP on {addr}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    try:
        asyncio.run(start_tcp_server(host=args.host, port=args.port))
    except KeyboardInterrupt:
        pass
