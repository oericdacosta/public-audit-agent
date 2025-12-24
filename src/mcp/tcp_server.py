import asyncio
import json
import logging

from mcp.server.fastmcp import FastMCP

# We need to bridge raw TCP sockets to the MCP protocol.
# FastMCP typically runs on Stdio or SSE.

logger = logging.getLogger(__name__)


async def handle_client(reader, writer, mcp_server: FastMCP):
    """
    Handles a single TCP client connection.
    Connects the TCP stream to the MCP server processing loop.
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
            print(f"DEBUG: Received message: {message}")
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
                        "capabilities": {},
                        "serverInfo": {"name": "CivicAudit TCP", "version": "1.0"},
                    },
                }
            elif method == "notifications/initialized":
                # No response needed
                pass
            elif method == "tools/list":
                # Get tools using public API
                tools = await mcp_server.list_tools()
                tools_list = []
                for tool in tools:
                    tools_list.append(
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema,
                        }
                    )

                resp = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools_list}}

            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})

                try:
                    # Call using public API
                    # call_tool returns (content_list, context) or similar
                    result = await mcp_server.call_tool(name, args)

                    # Result is likely a list of Content objects
                    # (TextContent, ImageContent, etc) We need to serialize them
                    content_list = []

                    # Handle tuple return if applicable
                    # (based on inspection it returned a tuple)
                    actual_result = result
                    if isinstance(result, tuple):
                        actual_result = result[0]

                    if isinstance(actual_result, list):
                        for item in actual_result:
                            # Check if it has type and text attributes
                            if hasattr(item, "type") and hasattr(item, "text"):
                                content_list.append(
                                    {"type": item.type, "text": item.text}
                                )
                            else:
                                # Fallback serialization
                                content_list.append({"type": "text", "text": str(item)})
                    else:
                        content_list.append(
                            {"type": "text", "text": str(actual_result)}
                        )

                    resp = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"content": content_list},
                    }
                except Exception as e:
                    logger.error(f"Tool call error: {e}")
                    resp = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32000, "message": str(e)},
                    }

            if resp:
                resp_str = json.dumps(resp) + "\n"
                print(f"DEBUG: Sending response: {resp_str.strip()}")
                writer.write(resp_str.encode())
                await writer.drain()

    except Exception as e:
        print(f"Connection Error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()


async def start_tcp_server(mcp_instance, host="0.0.0.0", port=8000):
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, mcp_instance), host, port
    )

    addr = server.sockets[0].getsockname()
    print(f"Serving TCP on {addr}")

    async with server:
        await server.serve_forever()
