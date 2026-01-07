import asyncio
from typing import Any, Callable, Dict, List, Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from src.etl.database import DatabaseManager as Database

# Initialize low-level server
app = Server("civic-audit-mcp")

# Registry for tool handlers
_TOOL_HANDLERS: Dict[str, Callable] = {}


# --- ACTUAL IMPLEMENTATION ---

# We need a centralized list_tools handler since the decorators stack up.
_TOOLS_METADATA: List[types.Tool] = []


def register_tool(
    name: str,
    description: str,
    input_schema: Dict[str, Any],
    examples: Optional[List[str]] = None,
):
    def decorator(func: Callable):
        _TOOL_HANDLERS[name] = func

        # Manually construct the Tool object
        # We append examples to description to guarantee visibility
        final_desc = description
        if examples:
            final_desc += "\n\nExamples:\n" + "\n".join([f"- {ex}" for ex in examples])

        tool_obj = types.Tool(
            name=name, description=final_desc, inputSchema=input_schema
        )
        _TOOLS_METADATA.append(tool_obj)
        return func

    return decorator


@app.list_tools()
async def list_tools() -> List[types.Tool]:
    return _TOOLS_METADATA


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[types.TextContent]:
    handler = _TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Tool {name} not found")

    # Execute (arguments is a dict)
    try:
        result = handler(**arguments)
        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


# --- TOOL DEFINITIONS ---

db = Database()


@register_tool(
    name="query_sql",
    description="Executes a read-only SQL query against the database.",
    input_schema={
        "type": "object",
        "properties": {
            "sql_query": {"type": "string", "description": "The SQL query to execute"}
        },
        "required": ["sql_query"],
    },
    examples=[
        "SELECT * FROM licitacoes WHERE valor_estimado > 10000 LIMIT 5",
        "SELECT sum(valor_pago) FROM despesas WHERE mes_referencia = '202401' AND codigo_funcao = '12'",  # noqa: E501
    ],
)
def query_sql(sql_query: str) -> str:
    if not sql_query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."
    try:
        results = db.execute_query(sql_query)
        return str(results)
    except Exception as e:
        return f"Error executing query: {str(e)}"


@register_tool(
    name="describe_table",
    description="Returns the schema for a specific table.",
    input_schema={
        "type": "object",
        "properties": {"table_name": {"type": "string"}},
        "required": ["table_name"],
    },
)
def describe_table(table_name: str) -> str:
    schema = db.get_start_schema(limit_tables=[table_name])
    if table_name in schema:
        return schema[table_name]
    return f"Table '{table_name}' not found."


@register_tool(
    name="search_definitions",
    description="Searches table names and schema definitions (DDL) for a given keyword.",  # noqa: E501
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    examples=["educacao", "saude", "pagamento"],
)
def search_definitions(query: str) -> str:
    results = db.search_schema(query)
    if not results:
        return "No definitions found matching your query."

    output = []
    for table, ddl in results.items():
        output.append(f"Table: {table}\nDefinition: {ddl}")
    return "\n".join(output)


@register_tool(
    name="search_tools",
    description="Searches for available tools to use. The agent starts with limited tools.",  # noqa: E501
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Capability or keyword (e.g., 'sql', 'table')",
            }
        },
        "required": ["query"],
    },
)
def search_tools(query: str) -> str:
    query = query.lower()
    matches = [
        f"Tool: {t.name}\nDescription: {t.description}"
        for t in _TOOLS_METADATA
        if query in t.name.lower() or query in (t.description or "").lower()
    ]

    if not matches:
        return "No tools found matching your query."
    return "\n---\n".join(matches)


@register_tool(
    name="list_tables",
    description="Lists all available tables in the database.",
    input_schema={
        "type": "object",
        "properties": {},
    },
)
def list_tables() -> str:
    tables = db.get_all_tables()
    return str(tables)


def main():
    asyncio.run(stdio_server(app))


if __name__ == "__main__":
    main()
