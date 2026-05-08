"""
MCP Server.

Model Context Protocol server for exposing database tools to AI assistants.
"""

import asyncio
import functools
from typing import Any, Callable, Optional, Type

import mcp.types as types
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, ValidationError

from mcp.server import Server

# Initialize low-level server
app = Server("civic-audit-mcp")

# Registry for tool handlers (already validates inputs when model is present)
_TOOL_HANDLERS: dict[str, Callable[..., Any]] = {}

# Registry for internal tool metadata
_REGISTRY: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Input models — one per tool.  Derive input_schema via model_json_schema().
# ---------------------------------------------------------------------------


class _QuerySqlInput(BaseModel):
    sql_query: str


class _DescribeTableInput(BaseModel):
    table_name: str


class _SearchInput(BaseModel):
    query: str


def _validated_handler(
    func: Callable[..., Any], model_cls: Type[BaseModel]
) -> Callable[..., Any]:
    """Wrap a tool handler to validate its arguments with a Pydantic model."""

    @functools.wraps(func)
    def wrapper(**kwargs: Any) -> Any:
        try:
            validated = model_cls.model_validate(kwargs)
        except ValidationError as e:
            return f"Input validation error: {e}"
        return func(**validated.model_dump())

    return wrapper


def register_tool(
    name: str,
    description: str,
    input_schema: Optional[dict[str, Any]] = None,
    examples: Optional[list[str]] = None,
    defer_loading: bool = False,
    input_model: Optional[Type[BaseModel]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to register a function as an MCP tool.

    If input_model is provided, the handler is wrapped with Pydantic validation
    and input_schema is auto-derived via model_json_schema() when not given.

    Args:
        name: Tool name for invocation.
        description: Human-readable description.
        input_schema: JSON Schema for input parameters (auto-derived from model).
        examples: Optional usage examples.
        defer_loading: If True, tool is hidden from initial context.
        input_model: Optional Pydantic model for argument validation.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        handler = _validated_handler(func, input_model) if input_model else func
        _TOOL_HANDLERS[name] = handler

        schema = input_schema
        if schema is None and input_model is not None:
            schema = input_model.model_json_schema()
        if schema is None:
            schema = {"type": "object", "properties": {}}

        # Inject examples into schema for standard compliance
        if examples:
            schema["examples"] = examples

        # Create Tool object
        tool_obj = types.Tool(name=name, description=description, inputSchema=schema)

        # Register with metadata
        _REGISTRY.append(
            {"tool": tool_obj, "defer": defer_loading, "examples": examples}
        )
        return func

    return decorator


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Returns only non-deferred tools to save context window."""
    return [entry["tool"] for entry in _REGISTRY if not entry["defer"]]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[types.TextContent]:
    """
    Handle tool invocation requests.

    Args:
        name: Name of the tool to call.
        arguments: Tool arguments.

    Returns:
        List containing the tool result as TextContent.
    """
    handler = _TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Tool {name} not found")

    try:
        result = handler(**arguments)
        return [types.TextContent(type="text", text=str(result))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


# --- TOOL DEFINITIONS ---
# Lazy import to avoid circular dependencies and speed up startup


def _get_database_tools() -> tuple:
    """Lazy load database tools."""
    from src.tools.sql import (
        describe_table as tool_describe_table,
    )
    from src.tools.sql import (
        list_tables as tool_list_tables,
    )
    from src.tools.sql import (
        query_sql as tool_query_sql,
    )
    from src.tools.sql import (
        search_definitions as tool_search_definitions,
    )

    return (
        tool_query_sql,
        tool_describe_table,
        tool_search_definitions,
        tool_list_tables,
    )


@register_tool(
    name="query_sql",
    description=(
        "Executes a read-only SQL query against the database. "
        "Pay attention to data types: quote TEXT values (e.g. '2024') "
        "as seen in the schema."
    ),
    examples=[
        "SELECT * FROM licitacoes WHERE valor_estimado > 10000 LIMIT 5",
        (
            "SELECT sum(valor_pago) FROM despesas "
            "WHERE mes_referencia = '202401' AND codigo_funcao = '12'"
        ),
    ],
    defer_loading=True,
    input_model=_QuerySqlInput,
)
def query_sql(sql_query: str) -> str:
    """Execute a SQL query via the database tools."""
    import json
    import math

    tool_query_sql, _, _, _ = _get_database_tools()
    result = tool_query_sql(sql_query)
    if isinstance(result, list):
        sanitized = []
        for row in result:
            if isinstance(row, dict):
                sanitized.append(
                    {
                        k: (
                            None
                            if isinstance(v, float) and (math.isnan(v) or math.isinf(v))
                            else v
                        )
                        for k, v in row.items()
                    }
                )
            else:
                sanitized.append(row)
        return json.dumps(sanitized, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


@register_tool(
    name="describe_table",
    description=(
        "Returns the DDL schema for a specific table. "
        "IMPORTANT: Read the DDL comments to find numeric codes for categories "
        "(e.g. 10: Saúde)."
    ),
    defer_loading=True,
    input_model=_DescribeTableInput,
)
def describe_table(table_name: str) -> str:
    """Get table schema via the database tools."""
    _, tool_describe_table, _, _ = _get_database_tools()
    result = tool_describe_table(table_name)
    return str(result)


@register_tool(
    name="search_definitions",
    description=(
        "Searches table names and schema definitions (DDL) for a given keyword. "
        "CRITICAL: The DDL contains domain mappings in comments "
        "(e.g., '-- 10: Saúde', '-- 12: Educação'). "
        "You MUST read these comments to translate names like 'Saúde' into "
        "numeric codes (e.g. '10') for querying."
    ),
    examples=["educacao", "saude", "pagamento"],
    defer_loading=False,
    input_model=_SearchInput,
)
def search_definitions(query: str) -> str:
    """Search table definitions via the database tools."""
    _, _, tool_search_definitions, _ = _get_database_tools()
    result = tool_search_definitions(query)
    return str(result)


@register_tool(
    name="search_tools",
    description=(
        "Searches for available capabilities/tools. Use this to find deferred tools."
    ),
    defer_loading=False,
    input_model=_SearchInput,
)
def search_tools(query: str) -> str:
    """Search available tools by keyword."""
    query_lower = query.lower()
    matches: list[str] = []

    for entry in _REGISTRY:
        t = entry["tool"]
        if (
            query_lower in t.name.lower()
            or query_lower in (t.description or "").lower()
        ):
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
    defer_loading=True,
)
def list_tables() -> str:
    """List database tables via the database tools."""
    _, _, _, tool_list_tables = _get_database_tools()
    result = tool_list_tables()
    return str(result)


def main() -> None:
    """Run the MCP server."""
    asyncio.run(stdio_server(app))  # type: ignore


if __name__ == "__main__":
    main()
