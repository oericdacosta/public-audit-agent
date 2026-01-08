from typing import Optional
import uuid

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from src.schemas.state import AgentState
from src.agents.analyst import generate, critique, execute, check_execution, should_continue
from src.agents.guardrail import guardrail_input, guardrail_output
from src.agents.planner import planner

# Import new Fiscal Agent nodes
from src.agents.fiscal import list_tables_node, get_schema_node, generate_query_node, check_query_node

def check_guardrail(state: AgentState):
    verdict = state.get("guardrail_verdict")
    if verdict == "UNSAFE":
        print("--- DECISION: BLOCKED BY GUARDRAIL ---")
        return END
    return "planner"

def should_check_sql(state: AgentState):
    # Logic to decide if we need to check the SQL or if it's failed too many times
    # For now, we simply always check.
    return "check_sql"

class AuditGraph:
    """
    Main orchestrator for the CivicAudit workflow.
    Integrates Analyst, Critic, Guardrails, AND Fiscal Agent.
    """

    def __init__(self):
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
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
        # Note: In a real loop we might loop back to generate_sql if check fails,
        # but check_sql already tries to fix it.
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
            "execute", check_execution, {"generate": "generate", END: "guardrail_output"}
        )

        # Output -> End
        workflow.add_edge("guardrail_output", END)

        return workflow.compile(checkpointer=self.memory)

    def run(self, user_question: str, thread_id: Optional[str] = None) -> str:
        
        if not thread_id:
            thread_id = str(uuid.uuid4())

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 30 # Increased for deeper pipeline
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
