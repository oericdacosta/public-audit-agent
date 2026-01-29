"""
Audit Workflow Graph.

Main orchestrator for the CivicAudit workflow integrating all agents.
"""

import logging
import uuid
from typing import Optional

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.analyst import (
    check_execution,
    critique,
    execute,
    generate,
    should_continue,
)
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


def check_guardrail(state: AgentState) -> str:
    """
    Route based on guardrail verdict.
    
    Returns:
        "planner" if safe, END if blocked.
    """
    verdict = state.get("guardrail_verdict")
    if verdict == "UNSAFE":
        logger.debug("DECISION: BLOCKED BY GUARDRAIL")
        return END
    return "planner"


def should_check_sql(state: AgentState) -> str:
    """
    Route to SQL validation.
    
    Returns:
        Always "check_sql" for now.
    """
    return "check_sql"


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
        workflow.add_node("generate", generate)
        workflow.add_node("critic", critique)
        workflow.add_node("execute", execute)
        workflow.add_node("guardrail_output", guardrail_output)

        # --- EDGES ---
        
        # Entry Point
        workflow.set_entry_point("guardrail_input")

        # Guardrail -> Planner
        workflow.add_conditional_edges(
            "guardrail_input",
            check_guardrail,
            {
                "planner": "planner",
                END: END
            }
        )

        # Planner -> Fiscal Agent Pipeline
        workflow.add_edge("planner", "list_tables")
        workflow.add_edge("list_tables", "get_schema")
        workflow.add_edge("get_schema", "generate_sql")
        workflow.add_edge("generate_sql", "check_sql")
        
        # Fiscal Agent -> Analyst Agent (Handover valid SQL)
        workflow.add_edge("check_sql", "generate")

        # Analyst Agent Loop (Generate Code -> Critic -> Execute)
        workflow.add_edge("generate", "critic")

        workflow.add_conditional_edges(
            "critic",
            should_continue,
            {
                "generate": "generate",
                END: "execute",
            },
        )

        # Execute -> Output Guardrail
        workflow.add_conditional_edges(
            "execute",
            check_execution,
            {"generate": "generate", END: "guardrail_output"}
        )

        # Output -> End
        workflow.add_edge("guardrail_output", END)

        return workflow.compile(checkpointer=self.memory)

    def run(self, user_question: str, thread_id: Optional[str] = None) -> str:
        """
        Execute the audit workflow for a user question.
        
        Args:
            user_question: The user's audit question.
            thread_id: Optional thread ID for conversation continuity.
        
        Returns:
            The final output from the workflow.
        """
        if not thread_id:
            thread_id = str(uuid.uuid4())

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 30
        }

        inputs = {
            "messages": [HumanMessage(content=user_question)],
            "iterations": 0,
            "error": None,
            "evaluation": None,
            "sql_query": None
        }

        final_state = self.graph.invoke(inputs, config=config)
        return final_state.get("output", "No output generated.")
