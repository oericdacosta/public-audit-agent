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
    "NOT ano_exercicio = '2024'. Only quote VARCHAR/TEXT values.\n\n"
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


# Domain vocabulary → mart tables mapping.
# Maps words a user would naturally say to the mart tables that answer them.
_DOMAIN_TABLE_MAP: dict[str, list[str]] = {
    # Spending / expenses
    "gasto": ["fct_despesas"],
    "gastos": ["fct_despesas"],
    "despesa": ["fct_despesas"],
    "despesas": ["fct_despesas"],
    "empenho": ["fct_despesas"],
    "empenhos": ["fct_despesas"],
    "liquidado": ["fct_despesas"],
    "pago": ["fct_despesas"],
    "pagamento": ["fct_despesas"],
    "pagamentos": ["fct_despesas"],
    # Revenue
    "receita": ["fct_receitas"],
    "receitas": ["fct_receitas"],
    "arrecadado": ["fct_receitas"],
    "arrecadação": ["fct_receitas"],
    # Budget functions / categories — use aggregated tables
    "educação": ["agg_despesas_por_funcao_ano", "fct_despesas"],
    "educacao": ["agg_despesas_por_funcao_ano", "fct_despesas"],
    "saúde": ["agg_despesas_por_funcao_ano", "fct_despesas"],
    "saude": ["agg_despesas_por_funcao_ano", "fct_despesas"],
    "administração": ["agg_despesas_por_funcao_ano", "fct_despesas"],
    "administracao": ["agg_despesas_por_funcao_ano", "fct_despesas"],
    "função": ["agg_despesas_por_funcao_ano"],
    "funcao": ["agg_despesas_por_funcao_ano"],
    "programa": ["dim_classificacao_orcamentaria", "fct_despesas"],
    "programas": ["dim_classificacao_orcamentaria"],
    "orçamento": ["dim_classificacao_orcamentaria", "agg_resultado_fiscal_mensal"],
    "orcamento": ["dim_classificacao_orcamentaria", "agg_resultado_fiscal_mensal"],
    "resultado fiscal": ["agg_resultado_fiscal_mensal"],
    # Bidding / procurement
    "licitação": ["fct_licitacoes", "fct_licitacoes_risco"],
    "licitações": ["fct_licitacoes", "fct_licitacoes_risco"],
    "licitacao": ["fct_licitacoes"],
    "pregão": ["fct_licitacoes"],
    "dispensa": ["fct_licitacoes"],
    "concorrência": ["fct_licitacoes"],
    "licitante": ["brd_licitantes"],
    "licitantes": ["brd_licitantes"],
    "risco": ["fct_licitacoes_risco"],
    # Contracts / suppliers
    "contrato": ["fct_contratos", "fct_contratos_fornecedores"],
    "contratos": ["fct_contratos", "fct_contratos_fornecedores"],
    "fornecedor": ["dim_fornecedores", "fct_contratos_fornecedores"],
    "fornecedores": ["dim_fornecedores", "fct_contratos_fornecedores"],
    "contratado": ["fct_contratos_fornecedores"],
    # Org structure
    "órgão": ["dim_orgaos", "agg_despesas_por_orgao_ano"],
    "orgao": ["dim_orgaos", "agg_despesas_por_orgao_ano"],
    "órgãos": ["dim_orgaos"],
    "orgaos": ["dim_orgaos"],
    "secretaria": ["dim_orgaos"],
    "unidade": ["dim_orgaos"],
    # Public agents / servers
    "servidor": ["fct_servidores"],
    "servidores": ["fct_servidores"],
    "agente": ["fct_servidores"],
    "agentes": ["fct_servidores"],
    # Municipality
    "município": ["dim_municipios"],
    "municipio": ["dim_municipios"],
    "cidade": ["dim_municipios"],
    "municípios": ["dim_municipios"],
    # Classification / budget structure
    "classificação": ["dim_classificacao_orcamentaria"],
    "classificacao": ["dim_classificacao_orcamentaria"],
}

# Core tables always included when no match is found — minimum viable context
_CORE_TABLES = ["fct_despesas", "dim_orgaos", "agg_despesas_por_funcao_ano"]


@observe_node(event_type="TOOL_CALL")
def get_schema_node(state: AgentState) -> dict[str, Any]:
    """
    Fetch schema information for tables relevant to the user question.

    Uses a two-tier strategy (no LLM):
    1. Domain vocabulary map — matches natural language words (e.g. "educação",
       "gasto", "licitação") to the tables that answer those questions.
    2. Table-name keyword match — fallback for table names that appear literally.
    3. Core tables fallback — always include despesas/funcoes/orgaos when nothing
       else matches, so the LLM always has a valid schema to work with.

    Schema is cached in state.schema_context across turns to avoid re-fetching.

    Returns:
        Updated state with schema context stored in state.schema_context.
    """
    logger.debug("FISCAL: GET SCHEMA")

    # Cache hit — reuse schema from a previous turn in the same conversation
    if state.get("schema_context"):
        logger.debug("FISCAL: SCHEMA CACHE HIT — skipping DDL fetch")
        return {}

    user_question = (state.get("user_question") or "").lower()
    available_tables = set(state.get("table_list") or _list_mart_tables())

    selected: set[str] = set()

    # Tier 1 — domain vocabulary map
    for keyword, tables in _DOMAIN_TABLE_MAP.items():
        if keyword in user_question:
            for t in tables:
                if t in available_tables:
                    selected.add(t)

    # Tier 2 — table-name keyword match (covers table names mentioned literally)
    for table in available_tables:
        base = (
            table.replace("fct_", "")
            .replace("stg_", "")
            .replace("int_", "")
            .replace("dim_", "")
            .replace("agg_", "")
            .replace("brd_", "")
            .replace("_", " ")
        )
        parts = [p for p in base.split() if len(p) > 3]
        if any(part in user_question for part in parts):
            selected.add(table)

    # Tier 3 — fallback to core tables so schema is never empty
    if not selected:
        for t in _CORE_TABLES:
            if t in available_tables:
                selected.add(t)

    target_tables = list(selected)[:5]
    logger.debug("FISCAL: Selected tables for schema: %s", target_tables)

    schemas: list[str] = []
    for t in target_tables:
        s = describe_table(t)
        if "not found" not in s:
            schemas.append(s)

    schema_text = "\n\n".join(schemas)
    return {"schema_context": schema_text}


@observe_node(event_type="THOUGHT")
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
