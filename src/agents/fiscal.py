
import os
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.callbacks import get_openai_callback

from src.schemas.state import AgentState
from src.tools.database import query_sql, list_tables, describe_table

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

from src.utils.logger import observe_node

# --- NODES ---

@observe_node(event_type="TOOL_CALL")
def list_tables_node(state: AgentState):
    print("--- FISCAL: LIST TABLES ---")
    tables = list_tables()
    return {"messages": [HumanMessage(content=f"Available tables: {tables}")]}

@observe_node(event_type="TOOL_CALL")
def get_schema_node(state: AgentState):
    print("--- FISCAL: GET SCHEMA ---")
    messages = state["messages"]
    
    # Simple heuristic: Get schema for all main tables to ensure context.
    # In a larger DB, we would use an LLM to decide which tables to fetch.
    # For now, we fetch 'licitacoes', 'despesas', 'receitas' if present.
    
    target_tables = ["licitacoes", "despesas", "receitas"]
    schemas = []
    
    for t in target_tables:
        s = describe_table(t)
        if "not found" not in s:
            schemas.append(s)
            
    schema_text = "\n\n".join(schemas)
    return {"messages": [HumanMessage(content=f"Schema Context:\n{schema_text}")]}

@observe_node(event_type="THOUGHT")
def generate_query_node(state: AgentState):
    print("--- FISCAL: GENERATE SQL ---")
    messages = state["messages"]
    
    # Extract user question and schema context from history
    user_question = "Unknown"
    schema_context = ""
    
    for m in messages:
        if isinstance(m, HumanMessage):
            if "Schema Context:" in m.content:
                schema_context = m.content
            # The first human message is usually the user question, 
            # but we can look for the last one that is NOT the schema or table list.
            elif "Available tables:" not in m.content:
                user_question = m.content

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
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
    print(f"Generated SQL: {sql_query}")
    
    return {"sql_query": sql_query}

@observe_node(event_type="THOUGHT")
def check_query_node(state: AgentState):
    print("--- FISCAL: CHECK SQL ---")
    sql_query = state["sql_query"]
    messages = state["messages"]
    
    schema_context = ""
    for m in messages:
        if isinstance(m, HumanMessage) and "Schema Context:" in m.content:
            schema_context = m.content
            
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
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
        print("SQL Verdict: VALID")
        return {"sql_query": sql_query}
    else:
        # The output is the corrected query
        corrected = result.replace("```sql", "").replace("```", "").strip()
        print(f"SQL Verdict: FIXED -> {corrected}")
        return {"sql_query": corrected}
