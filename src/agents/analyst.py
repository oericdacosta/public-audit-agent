import os
from typing import Optional
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from src.config import get_settings
from src.agents.critic import CriticAgent
from src.execution.sandbox import DockerSandbox
from src.schemas.state import AgentState
from src.utils.parsing import clean_markdown_code

# --- HELPER FUNCTIONS ---


def _build_prompt():
    prompts_dir = os.path.join(
        os.path.dirname(__file__), "..", "prompts", "components"
    )

    components = ["identity.md", "rules.md", "examples.md"]
    parts = []

    for comp in components:
        path = os.path.join(prompts_dir, comp)
        with open(path, "r") as f:
            parts.append(f.read())

    return "\n\n".join(parts)


def _load_static_prompt(filename: str) -> str:
    path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", filename
    )
    with open(path, "r") as f:
        return f.read()


def _generate_code_logic(user_question: str) -> str:
    """Core logic to generate code using LLM."""
    settings = get_settings()
    model_name = settings["agent"]["analyst_model"]
    llm = ChatOpenAI(model=model_name, temperature=0)

    system_instructions = _build_prompt()
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_instructions), ("user", "{input}")]
    )
    chain = prompt | llm
    response = chain.invoke({"input": user_question})

    return clean_markdown_code(response.content)


# --- NODE FUNCTIONS ---


def generate(state: AgentState):
    print("--- NODE: GENERATE ---")
    messages = state["messages"]
    error = state.get("error")
    evaluation = state.get("evaluation")

    if error:
        messages.append(
            HumanMessage(
                content=f"The previous code failed with this error:\n{error}\n"
                "Please fix the code and try again."
            )
        )

    if evaluation and "REJECT" in evaluation:
        messages.append(
            HumanMessage(
                content=f"The code was rejected by the reviewer:\n{evaluation}\n"
                "Please fix the logic errors."
            )
        )

    # Use the pure logic function, avoiding class instantiation loop
    last_message = messages[-1].content
    code = _generate_code_logic(last_message)

    return {
        "code": code,
        "iterations": state["iterations"] + 1,
        "error": None,
        "evaluation": None,
    }


def critique(state: AgentState):
    print("--- NODE: CRITIC ---")
    code = state["code"]
    messages = state["messages"]
    
    # Find the last user message to evaluate against
    user_question = "Unknown question"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_question = m.content
            break

    # Internal instantiation is fine here
    from src.agents.critic import CriticAgent

    critic = CriticAgent()
    evaluation = critic.review_code(user_question, code)
    print(f"Critic Verdict: {evaluation}")

    return {"evaluation": evaluation}


# --- NOTE: The AnalystAgent class has been refactored into src/graph/workflow.py (AuditGraph).
# This file now only contains the node functions used by the graph.


def execute(state: AgentState):
    print("--- NODE: EXECUTE ---")
    code = state["code"]
    sandbox = DockerSandbox()
    result = sandbox.execute(code)

    if (
        result.startswith("Execution Error")
        or result.startswith("System Error")
        or "Traceback" in result
    ):
        return {"output": result, "error": result}
    else:
        return {"output": result, "error": None}


def should_continue(state: AgentState):
    settings = get_settings()
    max_retries = settings.get("agent", {}).get("max_retries", 3)

    error = state.get("error")
    evaluation = state.get("evaluation")
    iterations = state.get("iterations")

    if evaluation and "REJECT" in evaluation:
        if iterations < max_retries:
            print(f"--- DECISION: REJECTED -> RETRY ({iterations}/{max_retries}) ---")
            return "generate"
        else:
            print("--- DECISION: MAX RETRIES (CRITIC) ---")
            return END

    if error:
        if iterations < max_retries:
            print(f"--- DECISION: ERROR -> RETRY ({iterations}/{max_retries}) ---")
            return "generate"

    print("--- DECISION: END ---")
    return END


def check_execution(state: AgentState):
    error = state.get("error")
    iterations = state.get("iterations")

    if error and iterations < 3:
        print(f"--- DECISION: EXEC ERROR -> RETRY ({iterations}/3) ---")
        return "generate"
    return END


# --- WRAPPER CLASS FOR BACKWARD COMPATIBILITY ---

from src.graph.workflow import AuditGraph

class AnalystAgent:
    """
    Wrapper around AuditGraph to maintain backward compatibility.
    """
    def __init__(self):
        self.workflow = AuditGraph()

    def run(self, user_question: str, thread_id: Optional[str] = None) -> str:
        return self.workflow.run(user_question, thread_id)
