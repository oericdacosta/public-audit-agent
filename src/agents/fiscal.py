"""
Fiscal Agent Node Functions.

SQL specialist agent for generating and validating database queries.
"""

import logging
from typing import Any, Optional, cast

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from src.schemas.state import AgentState
from src.tools.sql import list_tables, list_tables_compact, validate_sql_safety
from src.utils.llm import get_llm
from src.utils.logger import observe_node

logger = logging.getLogger(__name__)


# --- STRUCTURED OUTPUT MODELS ---


class _SqlOutput(BaseModel):
    sql: str


# --- SYSTEM PROMPTS ---

GENERATE_SQL_PROMPT = (
    "You are a SQL Expert for a DuckDB database containing public audit data "
    "(tenders, expenses, revenues, public servants).\n"
    "Your Goal: Given a user question, generate a correct executable SQL query.\n\n"
    "DIALECT: DuckDB\n"
    "RULES:\n"
    "1. PUSH DOWN COMPUTATION: Do NOT select all columns. Use SUM(), COUNT(), etc. "
    "whenever possible.\n"
    "2. STRING COMPARISONS: Quote all VARCHAR/TEXT values in single quotes.\n"
    "3. DATE FUNCTIONS: Use DuckDB syntax: "
    "date_trunc('month', data), strftime(data, '%Y-%m').\n"
    "4. ONLY SELECT queries. No DML.\n"
    "5. IF the question requires data from multiple tables, use JOIN.\n"
    "6. DuckDB supports: STRUCT, LIST, UNNEST, PIVOT, window functions.\n"
    "7. CRITICAL: columns tagged [NULL:API não retorna] are ALWAYS NULL in the source. "
    "NEVER use them in ORDER BY, WHERE, or as the primary SELECT value. "
    "If the user's question requires that value and it's tagged [NULL], "
    "select other available columns instead "
    "(e.g. numero_licitacao, nome_negociante).\n\n"
    "Schema Context:\n"
    "{schema_context}"
)


# --- NODE FUNCTIONS ---


# Mart table prefixes — only these are exposed to the agent.
_MART_PREFIXES = ("fct_", "dim_", "agg_", "brd_")


def _list_mart_tables() -> list[str]:
    """Return only mart-layer tables (fct_, dim_, agg_, brd_ prefixes)."""
    return [t for t in list_tables() if t.startswith(_MART_PREFIXES)]


@observe_node(event_type="TOOL_CALL")
def list_tables_node(state: AgentState) -> dict[str, Any]:
    """
    List available mart-layer tables and build compact schema for all of them.

    The compact schema (one line per table: "table: col TYPE, ...") is stored
    directly in state.schema_context so the fiscal agent sees every mart table
    and can select the right one without a separate schema fetch step.

    Returns:
        Updated state with table list and compact schema context.
    """
    logger.debug("FISCAL: LIST TABLES (marts only)")
    tables = _list_mart_tables()
    schema_text = list_tables_compact(tables)
    logger.debug("FISCAL: Compact schema built for %d tables", len(tables))
    return {"table_list": tables, "schema_context": schema_text}


@observe_node(event_type="TOOL_CALL")
def get_schema_node(state: AgentState) -> dict[str, Any]:
    """
    Schema cache check — no-op if schema_context is already populated.

    list_tables_node now sets schema_context directly, so this node is always
    a cache hit. It is kept in the graph to preserve topology and support
    any future scenario where schema_context might need re-fetching.

    Returns:
        Empty dict (no state update needed).
    """
    logger.debug("FISCAL: GET SCHEMA")
    if state.get("schema_context"):
        logger.debug("FISCAL: SCHEMA CACHE HIT — skipping DDL fetch")
        return {}
    # Fallback (should not happen in normal flow): build compact schema now.
    tables = state.get("table_list") or _list_mart_tables()
    schema_text = list_tables_compact(tables)
    return {"schema_context": schema_text}


@observe_node(event_type="THOUGHT", model_key="fiscal_model")
def generate_query_node(state: AgentState) -> dict[str, Optional[str]]:
    """
    Generate SQL query based on user question and schema context.

    Uses structured output to guarantee a clean SQL string without markdown.
    Validates generated SQL for safety before returning.

    Returns:
        Updated state with generated SQL query or error if unsafe.
    """
    logger.debug("FISCAL: GENERATE SQL")

    user_question = state.get("user_question") or "Unknown"
    schema_context = state.get("schema_context") or ""

    llm = get_llm("fiscal_model", timeout=60)
    prompt = ChatPromptTemplate.from_messages(
        [("system", GENERATE_SQL_PROMPT), ("human", "{question}")]
    )

    chain = prompt | llm.with_structured_output(_SqlOutput)
    response = cast(
        _SqlOutput,
        chain.invoke({"schema_context": schema_context, "question": user_question}),
    )

    sql_query = response.sql.strip()
    logger.debug("Generated SQL: %s", sql_query)

    # Validate LLM-generated SQL for safety
    is_safe, error = validate_sql_safety(sql_query)
    if not is_safe:
        logger.warning("LLM generated unsafe SQL: %s - %s", sql_query[:100], error)
        return {"sql_query": None, "error": f"Generated SQL is unsafe: {error}"}

    return {"sql_query": sql_query}


@observe_node(event_type="TOOL_CALL")
def check_query_node(state: AgentState) -> dict[str, Optional[str]]:
    """
    Validate the generated SQL query using DuckDB EXPLAIN.

    Uses DuckDB's query planner to detect syntax errors and invalid column/table
    references — exact and free, no LLM needed.

    Returns:
        Updated state with validated SQL or None if validation fails.
    """
    logger.debug("FISCAL: CHECK SQL (DuckDB EXPLAIN)")
    sql_query = state.get("sql_query")

    if not sql_query:
        logger.warning("No SQL query to check")
        return {"sql_query": None}

    # Re-validate for safety (LLM may have reintroduced unsafe operations)
    is_safe, safety_error = validate_sql_safety(sql_query)
    if not is_safe:
        logger.warning("SQL failed safety check before EXPLAIN: %s", safety_error)
        return {"sql_query": None, "error": f"SQL failed safety check: {safety_error}"}

    try:
        from src.tools.sql import _get_db

        db = _get_db()
        # Use EXPLAIN to validate syntax and schema without executing the query
        explain_sql = f"EXPLAIN {sql_query}"
        db.execute_query(explain_sql)
        logger.debug("SQL validation passed (DuckDB EXPLAIN)")
    except Exception as e:
        error_msg = str(e)
        logger.warning("SQL validation failed: %s", error_msg)
        return {"sql_query": None, "error": f"SQL syntax/schema error: {error_msg}"}

    return {"sql_query": sql_query}
