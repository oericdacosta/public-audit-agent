"""
MCP Server Shim.

Client shim for sandbox code to communicate with the MCP server via TCP.
This file is injected into the Docker sandbox to provide database access.
"""

import json
import logging
import os
import socket
from typing import Any, Optional, Union

# Configuration (Injected or Default)
MCP_HOST = os.environ.get("MCP_HOST", "host.docker.internal")

# Safe parsing of MCP_PORT with fallback
try:
    MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
except ValueError:
    MCP_PORT = 8000

logger = logging.getLogger(__name__)


def _rpc_call(
    method: str,
    params: Optional[dict[str, Any]] = None,
    msg_id: int = 1
) -> dict[str, Any]:
    """
    Send a JSON-RPC request over a TCP socket and wait for response.
    
    Args:
        method: RPC method name.
        params: Optional method parameters.
        msg_id: Message ID for request tracking.
    
    Returns:
        Parsed JSON response dictionary.
    
    Raises:
        Exception: If connection fails or response is invalid.
    """
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": msg_id
    }
    if params:
        payload["params"] = params

    try:
        with socket.create_connection((MCP_HOST, MCP_PORT), timeout=10) as sock:
            data = json.dumps(payload) + "\n"
            sock.sendall(data.encode("utf-8"))

            f = sock.makefile("r", encoding="utf-8")
            response_line = f.readline()

            if not response_line:
                raise Exception("Server closed connection without response")

            return json.loads(response_line)

    except ConnectionRefusedError as e:
        raise Exception(
            f"Could not connect to MCP Server at {MCP_HOST}:{MCP_PORT}"
        ) from e
    except Exception as e:
        raise Exception(f"RPC/Network Error: {str(e)}") from e


def _initialize_session() -> None:
    """Initialize a session with the MCP server (best effort)."""
    try:
        _rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "sandbox-shim", "version": "1.0"},
            },
            1,
        )
    except Exception:
        # Ignore init errors if server is already running/robust
        pass


def query_sql(sql_query: str) -> Union[list[dict[str, Any]], str]:
    """
    Execute a SQL query via the MCP Server.
    
    Args:
        sql_query: SQL query to execute.
    
    Returns:
        Query results as list of dicts, or error message string.
    """
    _initialize_session()
    
    response = _rpc_call(
        "tools/call",
        {"name": "query_sql", "arguments": {"sql_query": sql_query}},
        2
    )

    if "error" in response:
        raise Exception(f"MCP Error: {response['error']}")

    if "result" in response:
        res = response["result"]
        if "structuredContent" in res:
            return res["structuredContent"].get("result", [])

        if "content" in res:
            items: list[Any] = []
            for content in res.get("content", []):
                if content["type"] == "text":
                    try:
                        text_val = content["text"].strip()
                        vals = json.loads(text_val)
                        if isinstance(vals, list):
                            items.extend(vals)
                        else:
                            items.append(vals)
                    except Exception:
                        items.append(content["text"])
            return items

    return response


def list_tables() -> list[str]:
    """
    List all tables in the database.
    
    Returns:
        List of table names.
    """
    response = _rpc_call(
        "tools/call",
        {"name": "list_tables", "arguments": {}},
        2
    )

    if "error" in response:
        raise Exception(f"RPC Error calling list_tables: {response['error']}")

    if "result" in response:
        res = response["result"]
        if "structuredContent" in res:
            return res["structuredContent"].get("result", [])
        if "content" in res:
            items: list[str] = []
            for content in res.get("content", []):
                if content["type"] == "text":
                    try:
                        items.extend(json.loads(content["text"]))
                    except Exception:
                        items.append(content["text"])
            return items

    raise Exception(f"Unexpected response format from list_tables: {response}")


def describe_table(table_name: str) -> str:
    """
    Get schema DDL for a table.
    
    Args:
        table_name: Name of the table to describe.
    
    Returns:
        DDL statement for the table.
    """
    response = _rpc_call(
        "tools/call",
        {"name": "describe_table", "arguments": {"table_name": table_name}},
        2,
    )

    if "result" in response:
        res = response["result"]
        if "structuredContent" in res:
            return res["structuredContent"].get("result", "")
        for content in res.get("content", []):
            if content["type"] == "text":
                return content["text"]
    return ""


def search_definitions(query: str) -> Union[list[dict[str, str]], str]:
    """
    Search for table definitions matching a keyword.
    
    Args:
        query: Keyword to search for.
    
    Returns:
        Matching definitions or empty string.
    """
    response = _rpc_call(
        "tools/call",
        {"name": "search_definitions", "arguments": {"query": query}},
        2
    )

    if "result" in response:
        res = response["result"]
        for content in res.get("content", []):
            if content["type"] == "text":
                try:
                    return json.loads(content["text"])
                except Exception:
                    return content["text"]
    return ""
