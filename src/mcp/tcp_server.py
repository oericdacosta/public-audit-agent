"""
TCP Server for MCP.

Simple JSON-RPC server that bridges sandbox containers to database tools.
"""

import argparse
import asyncio
import json
import logging
import traceback
from typing import Any

logger = logging.getLogger(__name__)

# Import the unified tool registry from the STDIO MCP server
# This ensures TCP and STDIO servers always have identical tool sets
from src.mcp.server import _TOOL_HANDLERS as TOOL_MAP  # noqa: E402


async def handle_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """
    Handle a single TCP client connection.

    Implements a simple JSON-RPC style protocol for the sandbox shim.

    Args:
        reader: Stream reader for incoming data.
        writer: Stream writer for outgoing data.
    """
    addr = writer.get_extra_info("peername")
    logger.debug("Accepted connection from %s", addr)

    try:
        while True:
            data = await reader.readline()
            if not data:
                logger.debug("Client %s disconnected (EOF)", addr)
                break

            message = data.decode().strip()
            if not message:
                continue

            try:
                req = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from %s", addr)
                continue

            resp: dict[str, Any] | None = None
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
                    result = tool_func(**args)

                    # Serialize result
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
                    logger.error("Tool call error: %s", e)
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
        logger.error("Connection error: %s", e)
    finally:
        writer.close()
        await writer.wait_closed()


async def start_tcp_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """
    Start the TCP server.

    Args:
        host: Host address to bind to.
        port: Port number to listen on.
    """
    server = await asyncio.start_server(handle_client, host, port)

    addr = server.sockets[0].getsockname()
    logger.info("Serving TCP on %s", addr)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="CivicAudit MCP TCP Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    try:
        asyncio.run(start_tcp_server(host=args.host, port=args.port))
    except KeyboardInterrupt:
        pass
