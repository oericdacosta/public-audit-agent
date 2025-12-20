from mcp.server.fastmcp import FastMCP
import sqlite3
import json

# Initialize FastMCP Server
mcp = FastMCP("CivicAudit SQLite")

DB_PATH = "data/civic_audit.db"

def get_ro_connection():
    """Establishes a Read-Only connection to the SQLite database."""
    # URI mode=ro ensures strict read-only access at the driver level
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

@mcp.tool()
def list_tables() -> list[str]:
    """
    Lists all available tables in the database. 
    Use this to inspect what data is available for audit.
    """
    conn = get_ro_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables

@mcp.tool()
def describe_table(table_name: str) -> str:
    """
    Returns the schema (CREATE TABLE statement) for a specific table.
    Use this to understand the columns and data types before querying.
    """
    conn = get_ro_connection()
    cursor = conn.cursor()
    # Using sqlite_master to get the exact DDL
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result[0]
    else:
        return f"Table '{table_name}' not found."

@mcp.tool()
def query_sql(sql_query: str) -> str:
    """
    Executes a read-only SQL query against the database.
    
    Args:
        sql_query: The SQL SELECT statement to execute.
    
    Returns:
        JSON string containing the query results.
    
    Examples:
        - "SELECT * FROM licitacoes WHERE valor_estimado > 10000 LIMIT 5"
        - "SELECT sum(valor_pago) FROM despesas WHERE mes_referencia = '202401'"
    """
    try:
        conn = get_ro_connection()
        cursor = conn.cursor()
        cursor.execute(sql_query)
        
        # Fetch columns for dictionary creation
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        
        results = [dict(zip(columns, row)) for row in rows]
        conn.close()
        
        return json.dumps(results, ensure_ascii=False)
        
    except sqlite3.OperationalError as e:
        return f"SQL Error: {str(e)} (Ensure you are running SELECT queries only)"
    except Exception as e:
        return f"Error executing query: {str(e)}"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse", "http", "tcp"])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.transport == "tcp":
        import asyncio
        from src.mcp.tcp_server import start_tcp_server
        print(f"Starting MCP Server on TCP - 0.0.0.0:{args.port}")
        # Run async server loop
        asyncio.run(start_tcp_server(mcp, port=args.port))
    elif args.transport == "sse":
        import uvicorn
        print(f"Starting MCP Server on SSE - 0.0.0.0:8000")
        app = mcp.sse_app()
        uvicorn.run(app, host="0.0.0.0", port=8000)
    elif args.transport == "http": # Alias for streamable-http
        import uvicorn
        print(f"Starting MCP Server on HTTP - 0.0.0.0:8000")
        app = mcp.streamable_http_app()
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        mcp.run()
