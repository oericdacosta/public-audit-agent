"""
Audit Workflow Graph.

Main orchestrator for the CivicAudit workflow integrating all agents.
"""

import logging
import uuid
from typing import Optional, cast

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.analyst import (
    check_execution,
    critique,
    execute,
    generate,
    should_continue,
    simple_execute,
)
from src.agents.editor import editor
from src.agents.fiscal import (
    check_query_node,
    generate_query_node,
    get_schema_node,
    list_tables_node,
)
from src.agents.guardrail import guardrail_input, guardrail_output
from src.agents.planner import planner
from src.schemas.state import AgentState

logger = logging.getLogger(__name__)


# Keywords that indicate multi-step or complex analysis
_MULTI_STEP_KEYWORDS = [
    "compare",
    "versus",
    "vs",
    "tendência",
    "tendencia",
    "evolução",
    "evolucao",
    "por ano",
    "ao longo",
    "histórico",
    "historico",
    "ranking",
    "top ",
    "maiores",
    "menores",
    "correlação",
    "correlacao",
    "relação entre",
    "relacao entre",
    "percentual de crescimento",
    "variação",
    "variacao",
    "crescimento",
    "redução",
    "reducao",
    "e também",
    "e tambem",
    "além disso",
    "alem disso",
    "primeiro passo",
    "segundo passo",
    "entre os anos",
    "de 2020 a",
    "de 2021 a",
    "de 2022 a",
    "de 2023 a",
    "múltiplos",
    "multiplos",
    "vários",
    "varios municípios",
]


def check_guardrail(state: AgentState) -> str:
    """
    Route based on guardrail verdict and query complexity.

    Returns:
        "planner" if safe and complex, "list_tables" if safe and simple, END if blocked.
    """
    verdict = state.get("guardrail_verdict")
    if verdict == "UNSAFE":
        logger.debug("DECISION: BLOCKED BY GUARDRAIL")
        return cast(str, END)

    user_question = (state.get("user_question") or "").lower()
    is_complex = any(kw in user_question for kw in _MULTI_STEP_KEYWORDS)
    if is_complex:
        logger.debug("DECISION: COMPLEX QUERY -> PLANNER")
        return "planner"

    logger.debug("DECISION: SIMPLE QUERY -> SKIP PLANNER -> list_tables")
    return "list_tables"


def _is_simple_sql(state: AgentState) -> bool:
    """
    Detect whether the generated SQL is a simple single-scalar aggregation.

    Simple = single SELECT, single aggregate (SUM/COUNT/AVG/MAX/MIN), no GROUP BY,
    no JOIN, no subqueries, no CTEs. These return a single-row result that can be
    executed directly and formatted by the editor without Python code generation.

    Complex queries (breakdowns, comparisons, multi-step) still use the full pipeline.
    """
    sql = (state.get("sql_query") or "").upper()
    has_aggregation = any(f in sql for f in ["SUM(", "COUNT(", "AVG(", "MAX(", "MIN("])
    is_complex = (
        sql.count("SELECT") > 1
        or "WITH " in sql
        or "GROUP BY" in sql
        or " JOIN " in sql
    )
    return has_aggregation and not is_complex


def check_sql_generated(state: AgentState) -> str:
    """
    Route based on whether SQL was successfully generated.

    Returns:
        "check_sql" if SQL was generated, END if generation failed.
    """
    if not state.get("sql_query"):
        logger.debug("DECISION: NO SQL GENERATED -> END")
        return cast(str, END)
    return "check_sql"


def check_sql_validated(state: AgentState) -> str:
    """
    Route based on whether SQL passed validation and query complexity.

    Returns:
        "simple_execute" for simple aggregations, "generate" for complex queries,
        END if validation failed.
    """
    if not state.get("sql_query"):
        logger.debug("DECISION: SQL VALIDATION FAILED -> END")
        return cast(str, END)
    if _is_simple_sql(state):
        logger.debug("DECISION: SIMPLE SQL -> SKIP ANALYST -> simple_execute")
        return "simple_execute"
    return "generate"


class AuditGraph:
    """
    Main orchestrator for the CivicAudit workflow.

    Integrates:
    - Input Guardrail
    - Planner Agent
    - Fiscal Agent (SQL Specialist)
    - Analyst Agent (Python Specialist)
    - Critic Agent
    - Output Guardrail
    """

    def __init__(self) -> None:
        """Initialize the audit workflow graph."""
        self.memory = MemorySaver()
        self.graph = self._build_graph()
        self.last_thread_id: Optional[str] = None

    def _build_graph(self) -> StateGraph:
        """
        Build and compile the workflow graph.

        Returns:
            Compiled StateGraph ready for execution.
        """
        workflow = StateGraph(AgentState)

        # --- NODES ---
        workflow.add_node("guardrail_input", guardrail_input)
        workflow.add_node("planner", planner)

        # Fiscal Agent Nodes (SQL Specialist)
        workflow.add_node("list_tables", list_tables_node)
        workflow.add_node("get_schema", get_schema_node)
        workflow.add_node("generate_sql", generate_query_node)
        workflow.add_node("check_sql", check_query_node)

        # Analyst Agent Nodes (Python Specialist)
        workflow.add_node("simple_execute", simple_execute)
        workflow.add_node("generate", generate)
        workflow.add_node("critic", critique)
        workflow.add_node("execute", execute)
        workflow.add_node("editor", editor)
        workflow.add_node("guardrail_output", guardrail_output)

        # --- EDGES ---

        # Entry Point
        workflow.set_entry_point("guardrail_input")

        # Guardrail -> Complexity check -> Planner or directly to Fiscal Agent
        workflow.add_conditional_edges(
            "guardrail_input",
            check_guardrail,
            {"planner": "planner", "list_tables": "list_tables", END: END},
        )

        # Planner -> Fiscal Agent Pipeline
        workflow.add_edge("planner", "list_tables")
        workflow.add_edge("list_tables", "get_schema")
        workflow.add_edge("get_schema", "generate_sql")

        # Short-circuit after generate_sql when sql_query is None
        workflow.add_conditional_edges(
            "generate_sql",
            check_sql_generated,
            {"check_sql": "check_sql", END: END},
        )

        # Short-circuit after check_sql when SQL failed validation
        workflow.add_conditional_edges(
            "check_sql",
            check_sql_validated,
            {"simple_execute": "simple_execute", "generate": "generate", END: END},
        )

        # Simple path: direct SQL execution bypasses Python gen + critic + Docker
        workflow.add_edge("simple_execute", "editor")

        # Analyst Agent Loop (Generate Code -> Critic -> Execute)
        workflow.add_edge("generate", "critic")

        workflow.add_conditional_edges(
            "critic",
            should_continue,
            {
                "generate": "generate",
                "execute": "execute",
                "abort": "guardrail_output",
            },
        )

        # Execute -> Editor -> Output Guardrail
        workflow.add_conditional_edges(
            "execute",
            check_execution,
            {"generate": "generate", END: "editor"},
        )

        workflow.add_edge("editor", "guardrail_output")

        # Output -> End
        workflow.add_edge("guardrail_output", END)

        return workflow.compile(checkpointer=self.memory)  # type: ignore

    def run(self, user_question: str, thread_id: Optional[str] = None) -> str:
        """
        Execute the audit workflow for a user question.

        Supports multi-turn conversations: if thread_id is provided (or reused
        from self.last_thread_id), the conversation history is preserved via
        MemorySaver. Use self.last_thread_id after each call to continue the
        same conversation thread.

        Args:
            user_question: The user's audit question.
            thread_id: Thread ID for conversation continuity. If None, starts
                       a new conversation with a fresh thread_id.

        Returns:
            The final formatted output from the workflow.
        """
        is_new_conversation = thread_id is None
        thread_id = thread_id or str(uuid.uuid4())
        self.last_thread_id = thread_id

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 30,
        }

        inputs: dict = {
            "messages": [HumanMessage(content=user_question)],
            "iterations": 0,
        }

        # For new conversations, reset transient state.
        # For follow-ups (thread_id provided), preserve prior sql_query and context.
        if is_new_conversation:
            inputs.update({"error": None, "evaluation": None, "sql_query": None})

        try:
            final_state = self.graph.invoke(inputs, config=config)  # type: ignore
        except Exception as e:
            logger.error("Workflow error for thread %s: %s", thread_id, e)
            return f"Erro interno no processamento da consulta: {e}"

        output = final_state.get("output", "Nenhum resultado gerado.")
        return str(output)
