from typing import Optional
import uuid

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from src.schemas.state import AgentState
from src.agents.analyst import generate, critique, execute, check_execution, should_continue
from src.agents.guardrail import guardrail_input, guardrail_output
from src.agents.planner import planner

def check_guardrail(state: AgentState):
    verdict = state.get("guardrail_verdict")
    if verdict == "UNSAFE":
        print("--- DECISION: BLOCKED BY GUARDRAIL ---")
        return END
    return "planner"

class AuditGraph:
    """
    Main orchestrator for the CivicAudit workflow.
    Integrates Analyst, Critic, and Guardrails.
    """

    def __init__(self):
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Add Nodes
        workflow.add_node("guardrail_input", guardrail_input)
        workflow.add_node("planner", planner)
        workflow.add_node("generate", generate)
        workflow.add_node("critic", critique)
        workflow.add_node("execute", execute)
        workflow.add_node("guardrail_output", guardrail_output)

        # Set Entry Point
        workflow.set_entry_point("guardrail_input")

        # Guardrail Input Logic
        workflow.add_conditional_edges(
            "guardrail_input",
            check_guardrail,
            {
                "planner": "planner",
                END: END
            }
        )

        # Planner -> Generate
        workflow.add_edge("planner", "generate")

        # Generate -> Critic
        workflow.add_edge("generate", "critic")

        # Critic Logic
        workflow.add_conditional_edges(
            "critic",
            should_continue,
            {
                "generate": "generate",
                END: "execute",
            },
        )

        # Execution Logic -> Output Guardrail
        workflow.add_conditional_edges(
            "execute", check_execution, {"generate": "generate", END: "guardrail_output"}
        )

        # Output Guardrail -> End
        workflow.add_edge("guardrail_output", END)

        return workflow.compile(checkpointer=self.memory)

    def run(self, user_question: str, thread_id: Optional[str] = None) -> str:
        
        # If no thread_id provided, generate a new one
        if not thread_id:
            thread_id = str(uuid.uuid4())

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 10
        }

        # For a new turn, we only need to provide the new message
        inputs = {
            "messages": [HumanMessage(content=user_question)],
            "iterations": 0,
            "error": None,
            "evaluation": None
        }

        final_state = self.graph.invoke(inputs, config=config)
        return final_state.get("output", "No output generated.")
