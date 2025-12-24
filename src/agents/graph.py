from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from src.config import get_settings
from src.execution.sandbox import DockerSandbox
from src.schemas.state import AgentState


# 2. Node: Generate Code
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

    from src.agents.analyst import AnalystAgent

    agent = AnalystAgent()

    last_message = messages[-1].content

    code = agent.generate_code(last_message)

    return {
        "code": code,
        "iterations": state["iterations"] + 1,
        "error": None,
        "evaluation": None,
    }


# 3. Node: Critic (Review)
def critique(state: AgentState):
    print("--- NODE: CRITIC ---")
    code = state["code"]
    messages = state["messages"]
    user_question = messages[0].content  # Assuming first message is the question

    from src.agents.critic import CriticAgent

    critic = CriticAgent()

    evaluation = critic.review_code(user_question, code)
    print(f"Critic Verdict: {evaluation}")

    return {"evaluation": evaluation}


# 4. Node: Execute Code
def execute(state: AgentState):
    print("--- NODE: EXECUTE ---")
    code = state["code"]
    sandbox = DockerSandbox()

    result = sandbox.execute(code)

    # Simple heuristic: if result starts with "Execution Error" or "System Error",
    # it failed
    if (
        result.startswith("Execution Error")
        or result.startswith("System Error")
        or "Traceback" in result
    ):
        return {"output": result, "error": result}
    else:
        return {"output": result, "error": None}


# 5. Conditional Edge: Should Continue?
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


# 6. Build the Graph
workflow = StateGraph(AgentState)

workflow.add_node("generate", generate)
workflow.add_node("critic", critique)
workflow.add_node("execute", execute)

workflow.set_entry_point("generate")

workflow.add_edge("generate", "critic")

workflow.add_conditional_edges(
    "critic",
    should_continue,
    {
        "generate": "generate",  # Rejected -> Retry
        END: "execute",  # Approved -> Execute
    },
)


def check_execution(state: AgentState):
    error = state.get("error")
    iterations = state.get("iterations")

    if error and iterations < 3:
        print(f"--- DECISION: EXEC ERROR -> RETRY ({iterations}/3) ---")
        return "generate"
    return END


workflow.add_conditional_edges(
    "execute", check_execution, {"generate": "generate", END: END}
)


app = workflow.compile()
