import json
import socket
import os

# Configuration (Injected or Default)
MCP_HOST = os.environ.get("MCP_HOST", "host.docker.internal")
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))

def _rpc_call(method, params=None, msg_id=1):
    """
    Sends a JSON-RPC request over a TCP socket and waits for a response.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": msg_id
    }
    if params:
        payload["params"] = params
    
    # Connect to Server
    try:
        # Create a new socket for each call (Simple & Robust for this use case)
        # For high-performance, we would reuse the socket, but that requires class-based Shim.
        with socket.create_connection((MCP_HOST, MCP_PORT), timeout=10) as sock:
            # Send Request (Newline delimited)
            data = json.dumps(payload) + "\n"
            sock.sendall(data.encode('utf-8'))
            
            # Read Response
            # We expect a single line JSON response
            f = sock.makefile('r', encoding='utf-8')
            response_line = f.readline()
            
            if not response_line:
                raise Exception("Server closed connection without response")
                
            return json.loads(response_line)
            
    except ConnectionRefusedError:
         raise Exception(f"Could not connect to MCP Server at {MCP_HOST}:{MCP_PORT}")
    except Exception as e:
        raise Exception(f"RPC/Network Error: {str(e)}")

def query_sql(sql_query):
    """
    Executes a SQL query via the MCP Server.
    """
    # 1. Initialize (Handshake)
    try:
        _rpc_call("initialize", {
            "protocolVersion": "2024-11-05", 
            "capabilities": {},
            "clientInfo": {"name": "sandbox-shim", "version": "1.0"}
        }, 1)
        # We don't strictly need to wait for initialized notification in this simple TCP adapter
        # but good practice to follow flow if server expects it.
        # calls are sequential on new socket in this implementation?
        # WAIT. ephemeral socket means NEW connection every time.
        # The TCP server I wrote doesn't persist state across connections about "initialization".
        # It just processes messages.
        # So "initialize" might be redundant per call but safe.
        pass 
    except:
        pass # Ignore init errors if server is already running/robust

    # 2. Call Tool
    response = _rpc_call("tools/call", {
        "name": "query_sql",
        "arguments": {"sql_query": sql_query}
    }, 2)
    
    if "error" in response:
        raise Exception(f"MCP Error: {response['error']}")

    if "result" in response:
        res = response["result"]
        if "structuredContent" in res:
             return res["structuredContent"].get("result", [])
             
        if "content" in res:
            items = []
            for content in res.get("content", []):
                if content["type"] == "text":
                    try:
                        items.extend(json.loads(content["text"]))
                    except:
                        items.append(content["text"])
            return items
            
    return response

def list_tables():
    """
    Lists tables in the database.
    """
    # Simply call tool. Initialize irrelevant for this stateless TCP shim logic
    # (My tcp_server.py implementation is naive and handles any request)
    response = _rpc_call("tools/call", {
        "name": "list_tables",
        "arguments": {}
    }, 2)
    
    if "error" in response:
        raise Exception(f"RPC Error calling list_tables: {response['error']}")

    if "result" in response:
        res = response["result"]
        if "structuredContent" in res:
             return res["structuredContent"].get("result", [])
        if "content" in res:
            items = []
            for content in res.get("content", []):
                if content["type"] == "text":
                    try:
                        items.extend(json.loads(content["text"]))
                    except:
                        items.append(content["text"])
            return items
            
    raise Exception(f"Unexpected response format from list_tables: {response}")

def describe_table(table_name):
    """
    Get schema for a table.
    """
    response = _rpc_call("tools/call", {
        "name": "describe_table",
        "arguments": {"table_name": table_name}
    }, 2)

    if "result" in response:
        res = response["result"]
        if "structuredContent" in res:
             return res["structuredContent"].get("result", "")
        for content in res.get("content", []):
            if content["type"] == "text":
                return content["text"]
    return ""

def search_definitions(query: str):
    """
    Search for table definitions.
    """
    response = _rpc_call("tools/call", {
        "name": "search_definitions",
        "arguments": {"query": query}
    }, 2)
    
    if "result" in response:
        res = response["result"]
        for content in res.get("content", []):
            if content["type"] == "text":
                return content["text"]
    return ""
