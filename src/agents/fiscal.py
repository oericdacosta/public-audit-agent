"""
Fiscal Agent Node Functions.

SQL specialist agent for generating and validating database queries.
"""

import logging
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate

from src.schemas.state import AgentState
from src.tools.sql import describe_table, list_tables, validate_sql_safety
from src.utils.llm import get_llm
from src.utils.logger import observe_node

logger = logging.getLogger(__name__)


# --- SYSTEM PROMPTS ---

GENERATE_SQL_PROMPT = (
    "You are a SQL Expert for a DuckDB database containing public audit data "
    "(tenders, expenses, revenues, contracts).\n"
    "Your Goal: Given a user question, generate a correct executable SQL query.\n\n"
    "DIALECT: DuckDB\n"
    "RULES:\n"
    "1. PUSH DOWN COMPUTATION: Do NOT select all columns. Use SUM(), COUNT(), etc. "
    "whenever possible.\n"
    "2. STRING COMPARISONS: Always wrap VARCHAR columns in LOWER() for "
    "case-insensitive matching: LOWER(nome_municipio) = 'sobral'. "
    "Quote all VARCHAR/TEXT values in single quotes.\n"
    "3. NUMERIC COLUMNS: Cast explicitly when needed: CAST(valor AS DECIMAL).\n"
    "4. DATE FUNCTIONS: Use DuckDB syntax: "
    "date_trunc('month', data), strftime(data, '%Y-%m').\n"
    "5. ONLY SELECT queries. No DML.\n"
    "6. IF the question requires data from multiple tables, use JOIN.\n"
    "7. DuckDB supports: STRUCT, LIST, UNNEST, PIVOT, window functions.\n"
    "8. RETURN ONLY THE RAW SQL. No markdown blocks, no 'Here is the code'. "
    "Just the SQL string.\n"
    "9. INTEGER COLUMNS: Do NOT quote numeric literals — use ano_exercicio = 2024, "
    "NOT ano_exercicio = '2024'. Only quote VARCHAR/TEXT values.\n"
    "10. DATA QUALITY: When the query aggregates monetary values "
    "(empenhado/liquidado/pago) filtered by BOTH ano_exercicio AND nome_funcao, "
    "always add a LEFT JOIN to agg_data_quality ON municipio_id, ano_exercicio, "
    "AND LOWER(nome_funcao) = LOWER(nome_funcao), "
    "and SELECT status_qualidade AND explicacao_qualidade from it. "
    "This lets the user understand whether zero values are real "
    "or a source publication lag.\n\n"
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
    List available mart-layer tables (fct_, dim_, agg_, brd_).

    Returns:
        Updated state with mart table list stored in state.table_list.
    """
    logger.debug("FISCAL: LIST TABLES (marts only)")
    tables = _list_mart_tables()
    return {"table_list": tables}


# Core tables used as fallback when the semantic embedding index is unavailable.
# This ensures the agent always has a minimal schema context to work with.
_CORE_TABLES = [
    "fct_despesas",
    "dim_orgaos",
    "agg_despesas_por_funcao_ano",
    "agg_data_quality",
]


@observe_node(event_type="TOOL_CALL")
def get_schema_node(state: AgentState) -> dict[str, Any]:
    """
    Fetch schema information for tables relevant to the user question.

    Table selection is performed semantically by guardrail_input via embedding
    similarity (stored in state.selected_tables). Falls back to core tables
    when the embedding index is unavailable.

    Schema is cached in state.schema_context across turns to avoid re-fetching.

    Returns:
        Updated state with schema context stored in state.schema_context.
    """
    logger.debug("FISCAL: GET SCHEMA")

    # Cache hit — reuse schema from a previous turn in the same conversation
    if state.get("schema_context"):
        logger.debug("FISCAL: SCHEMA CACHE HIT — skipping DDL fetch")
        return {}

    available_tables = set(state.get("table_list") or _list_mart_tables())

    # Use semantically selected tables from guardrail_input
    selected_tables: list[str] = state.get("selected_tables") or []

    # Filter to only tables that actually exist in the database
    selected = [t for t in selected_tables if t in available_tables]

    # Fallback: if no tables were selected (index unavailable), use core tables
    if not selected:
        logger.debug("FISCAL: No semantic selection — falling back to core tables")
        selected = [t for t in _CORE_TABLES if t in available_tables]

    target_tables = selected[:6]  # Respect hard cap from embeddings design
    logger.debug("FISCAL: Selected tables for schema: %s", target_tables)

    schemas: list[str] = []
    for t in target_tables:
        s = describe_table(t)
        if "not found" not in s:
            schemas.append(s)

    schema_text = "\n\n".join(schemas)
    return {"schema_context": schema_text}


@observe_node(event_type="THOUGHT", model_key="fiscal_model")
def generate_query_node(state: AgentState) -> dict[str, Optional[str]]:
    """
    Generate SQL query based on user question and schema context.

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

    chain = prompt | llm
    response = chain.invoke(
        {"schema_context": schema_context, "question": user_question}
    )

    sql_query = response.content.replace("```sql", "").replace("```", "").strip()  # type: ignore
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
        return {"sql_query": sql_query}
    except Exception as e:
        error_msg = str(e)
        logger.warning("SQL validation failed: %s", error_msg)
        return {"sql_query": None, "error": f"SQL syntax/schema error: {error_msg}"}
