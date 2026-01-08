import asyncio
from typing import Any, Callable, Dict, List, Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Initialize low-level server
app = Server("civic-audit-mcp")

# Registry for tool handlers
_TOOL_HANDLERS: Dict[str, Callable] = {}


# --- ACTUAL IMPLEMENTATION ---

# We need a centralized list_tools handler since the decorators stack up.
# Registry for internal tool metadata (stores Tool object + extra flags)
_REGISTRY: List[Dict[str, Any]] = []


def register_tool(
    name: str,
    description: str,
    input_schema: Dict[str, Any],
    examples: Optional[List[str]] = None,
    defer_loading: bool = False,
):
    def decorator(func: Callable):
        _TOOL_HANDLERS[name] = func

        # Inject examples into input_schema for standard compliance
        if examples:
            input_schema["examples"] = examples

        # Create Tool object
        tool_obj = types.Tool(
            name=name, 
            description=description, 
            inputSchema=input_schema
        )
        
        # Register with metadata
        _REGISTRY.append({
            "tool": tool_obj,
            "defer": defer_loading,
            "examples": examples
        })
        return func

    return decorator


@app.list_tools()
async def list_tools() -> List[types.Tool]:
    """Returns only non-deferred tools to save context window."""
    return [
        entry["tool"] for entry in _REGISTRY 
        if not entry["defer"]
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[types.TextContent]:
    handler = _TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Tool {name} not found")

    try:
        result = handler(**arguments)
        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


# --- TOOL DEFINITIONS ---

from src.tools.database import (
    describe_table as tool_describe_table,
    list_tables as tool_list_tables,
    query_sql as tool_query_sql,
    search_definitions as tool_search_definitions,
)


@register_tool(
    name="query_sql",
    description="Executes a read-only SQL query against the database. Pay attention to data types: quote TEXT values (e.g. '2024') as seen in the schema.",
    input_schema={
        "type": "object",
        "properties": {
            "sql_query": {"type": "string", "description": "The SQL query to execute"}
        },
        "required": ["sql_query"],
    },
    examples=[
        "SELECT * FROM licitacoes WHERE valor_estimado > 10000 LIMIT 5",
        "SELECT sum(valor_pago) FROM despesas WHERE mes_referencia = '202401' AND codigo_funcao = '12'",
    ],
    defer_loading=True  # Deferred to save context
)
def query_sql(sql_query: str) -> str:
    return tool_query_sql(sql_query)


@register_tool(
    name="describe_table",
    description="Returns the DDL schema for a specific table. IMPORTANT: Read the DDL comments to find numeric codes for categories (e.g. 10: Saúde).",
    input_schema={
        "type": "object",
        "properties": {"table_name": {"type": "string"}},
        "required": ["table_name"],
    },
    defer_loading=True
)
def describe_table(table_name: str) -> str:
    return tool_describe_table(table_name)


@register_tool(
    name="search_definitions",
    description=(
        "Searches table names and schema definitions (DDL) for a given keyword. "
        "CRITICAL: The DDL contains domain mappings in comments (e.g., '-- 10: Saúde', '-- 12: Educação'). "
        "You MUST read these comments to translate names like 'Saúde' into numeric codes (e.g. '10') for querying."
    ),
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    examples=["educacao", "saude", "pagamento"],
    defer_loading=False  # Critical discovery tool
)
def search_definitions(query: str) -> str:
    return tool_search_definitions(query)


@register_tool(
    name="search_tools",
    description="Searches for available capabilities/tools. Use this to find deferred tools.",
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
    defer_loading=False  # Critical discovery tool
)
def search_tools(query: str) -> str:
    query = query.lower()
    matches = []
    
    for entry in _REGISTRY:
        t = entry["tool"]
        if query in t.name.lower() or query in (t.description or "").lower():
            status = "(Deferred)" if entry["defer"] else "(Active)"
            matches.append(f"Tool: {t.name} {status}\nDescription: {t.description}")

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
    defer_loading=True
)
def list_tables() -> str:
    return tool_list_tables()


def main():
    asyncio.run(stdio_server(app))


if __name__ == "__main__":
    main()
