"""
Fiscal Agent Node Functions.

SQL specialist agent for generating and validating database queries.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.schemas.state import AgentState
from src.tools.sql import describe_table, list_tables
from src.utils.logger import observe_node

logger = logging.getLogger(__name__)


# --- SYSTEM PROMPTS ---

GENERATE_SQL_PROMPT = """
You are a SQL Expert for a SQLite database containing public audit data (tenders, expenses, revenues).
Your Goal: Given a user question, generate a correct executable SQL query.

DIALECT: SQLite
RULES:
1. PUSH DOWN COMPUTATION: Do NOT select all columns. Use SUM(), COUNT(), etc. whenever possible.
2. QUOTE VALUES: `where exercicio_orcamento = '2024'` (String comparison).
3. JSON HANDLING: Some columns are JSON. You generally don't need to parse them in SQL, just select the columns asked.
4. ONLY SELECT queries. No DML.
5. IF the question requires data from multiple tables, use JOIN.
6. RETURN ONLY THE RAW SQL. No markdown blocks, no 'Here is the code'. Just the SQL string.

Schema Context:
{schema_context}
"""

CHECK_SQL_PROMPT = """
You are a Senior SQL Reviewer.
Check the following SQLite query for common mistakes:
1. Syntax errors
2. Column hallucination (columns that don't exist in schema)
3. Data type mismatches (quoting years '2024')
4. Logical errors (using WHERE instead of HAVING)

Query:
{query}

Schema Context:
{schema_context}

If the query is VALID, output: VALID
If the query is INVALID, output the CORRECTED query (JUST the SQL).
"""


# --- NODE FUNCTIONS ---


@observe_node(event_type="TOOL_CALL")
def list_tables_node(state: AgentState) -> dict[str, Any]:
    """
    List all available database tables.
    
    Returns:
        Updated state with table list message.
    """
    logger.debug("FISCAL: LIST TABLES")
    tables = list_tables()
    return {"messages": [HumanMessage(content=f"Available tables: {tables}")]}


@observe_node(event_type="TOOL_CALL")
def get_schema_node(state: AgentState) -> dict[str, Any]:
    """
    Fetch schema information for relevant tables.
    
    Returns:
        Updated state with schema context message.
    """
    logger.debug("FISCAL: GET SCHEMA")
    
    # Get schema for main tables to ensure context
    target_tables = ["licitacoes", "despesas", "receitas"]
    schemas: list[str] = []
    
    for t in target_tables:
        s = describe_table(t)
        if "not found" not in s:
            schemas.append(s)
            
    schema_text = "\n\n".join(schemas)
    return {"messages": [HumanMessage(content=f"Schema Context:\n{schema_text}")]}


@observe_node(event_type="THOUGHT")
def generate_query_node(state: AgentState) -> dict[str, Any]:
    """
    Generate SQL query based on user question and schema context.
    
    Validates generated SQL for safety before returning.
    
    Returns:
        Updated state with generated SQL query or error if unsafe.
    """
    from src.tools.sql import validate_sql_safety
    
    logger.debug("FISCAL: GENERATE SQL")
    messages = state["messages"]
    
    # Extract user question and schema context from history
    user_question = "Unknown"
    schema_context = ""
    
    for m in messages:
        if isinstance(m, HumanMessage):
            if "Schema Context:" in m.content:
                schema_context = m.content
            elif "Available tables:" not in m.content:
                user_question = m.content

    settings = get_settings()
    model_name = settings["agent"].get("fiscal_model", "gpt-4o")
    llm = ChatOpenAI(model=model_name, temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", GENERATE_SQL_PROMPT),
        ("human", "{question}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({
        "schema_context": schema_context,
        "question": user_question
    })
    
    sql_query = response.content.replace("```sql", "").replace("```", "").strip()
    logger.debug("Generated SQL: %s", sql_query)
    
    # P7: Validate LLM-generated SQL for safety
    is_safe, error = validate_sql_safety(sql_query)
    if not is_safe:
        logger.warning("LLM generated unsafe SQL: %s - %s", sql_query[:100], error)
        return {"sql_query": None, "error": f"Generated SQL is unsafe: {error}"}
    
    return {"sql_query": sql_query}


@observe_node(event_type="THOUGHT")
def check_query_node(state: AgentState) -> dict[str, str]:
    """
    Validate and potentially correct the generated SQL query.
    
    Returns:
        Updated state with validated/corrected SQL query.
    """
    logger.debug("FISCAL: CHECK SQL")
    sql_query = state["sql_query"]
    messages = state["messages"]
    
    schema_context = ""
    for m in messages:
        if isinstance(m, HumanMessage) and "Schema Context:" in m.content:
            schema_context = m.content
            
    settings = get_settings()
    model_name = settings["agent"].get("fiscal_model", "gpt-4o")
    llm = ChatOpenAI(model=model_name, temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", CHECK_SQL_PROMPT),
    ])
    
    chain = prompt | llm
    response = chain.invoke({
        "query": sql_query,
        "schema_context": schema_context
    })
    
    result = response.content.strip()
    
    if result == "VALID":
        logger.debug("SQL Verdict: VALID")
        return {"sql_query": sql_query}
    
    # The output is the corrected query
    corrected = result.replace("```sql", "").replace("```", "").strip()
    logger.debug("SQL Verdict: FIXED -> %s", corrected)
    return {"sql_query": corrected}
