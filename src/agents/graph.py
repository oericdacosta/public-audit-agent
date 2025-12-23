from typing import TypedDict, Annotated, List, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
import operator

from src.execution.sandbox import DockerSandbox

# 1. Define the State
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    code: str
    output: str
    error: str
    evaluation: str # New field for Critic's feedback
    iterations: int

# 2. Node: Generate Code
def generate(state: AgentState):
    print("--- NODE: GENERATE ---")
    messages = state['messages']
    error = state.get('error')
    evaluation = state.get('evaluation')
    
    # If there is an error, we need to inform the agent
    if error:
        messages.append(HumanMessage(content=f"The previous code failed with this error:\n{error}\nPlease fix the code and try again."))
    
    # If there is negative feedback from Critic
    if evaluation and "REJECT" in evaluation:
         messages.append(HumanMessage(content=f"The code was rejected by the reviewer:\n{evaluation}\nPlease fix the logic errors."))

    # Initialize the "brain" (Analyst)
    # Ideally, this should be injected or cached, but instantiation is cheap here
    from src.agents.analyst import AnalystAgent
    agent = AnalystAgent()
    
    # Extract the last user question or use the conversation history
    # For simplicity in this v1, we pass the last message text if it's new
    last_message = messages[-1].content
    
    # The AnalystAgent.generate_code logic currently takes a string
    # We might want to pass the full history later, but for now:
    code = agent.generate_code(last_message)
    
    return {"code": code, "iterations": state['iterations'] + 1, "error": None, "evaluation": None}

# 3. Node: Critic (Review)
def critique(state: AgentState):
    print("--- NODE: CRITIC ---")
    code = state['code']
    messages = state['messages']
    user_question = messages[0].content # Assuming first message is the question
    
    from src.agents.critic import CriticAgent
    critic = CriticAgent()
    
    evaluation = critic.review_code(user_question, code)
    print(f"Critic Verdict: {evaluation}")
    
    return {"evaluation": evaluation}

# 4. Node: Execute Code
def execute(state: AgentState):
    print("--- NODE: EXECUTE ---")
    code = state['code']
    sandbox = DockerSandbox()
    
    result = sandbox.execute(code)
    
    # Simple heuristic: if result starts with "Execution Error" or "System Error", it failed
    if result.startswith("Execution Error") or result.startswith("System Error") or "Traceback" in result:
        return {"output": result, "error": result}
    else:
        return {"output": result, "error": None}

# 5. Conditional Edge: Should Continue?
def should_continue(state: AgentState):
    error = state.get('error')
    evaluation = state.get('evaluation')
    iterations = state.get('iterations')
    
    # 1. Critic Rejection Logic
    if evaluation and "REJECT" in evaluation:
        if iterations < 3:
             print(f"--- DECISION: REJECTED -> RETRY ({iterations}/3) ---")
             return "generate"
        else:
             print("--- DECISION: MAX RETRIES (CRITIC) ---")
             return END

    # 2. Execution Error Logic
    if error: 
        if iterations < 3:
            print(f"--- DECISION: ERROR -> RETRY ({iterations}/3) ---")
            return "generate"
    
    print("--- DECISION: END ---")
    return END

# 6. Build the Graph
workflow = StateGraph(AgentState)

workflow.add_node("generate", generate)
workflow.add_node("critic", critique)
workflow.add_node("execute", execute)

workflow.set_entry_point("generate")

# Flow: Generate -> Critic -> (Check) -> Execute -> (Check) -> End or Retry
workflow.add_edge("generate", "critic")

workflow.add_conditional_edges(
    "critic",
    should_continue,
    {
        "generate": "generate", # Rejected -> Retry
        END: "execute"        # Approved -> Execute
    }
)

# New Conditional Edge for Execution Result
def check_execution(state: AgentState):
    error = state.get('error')
    iterations = state.get('iterations')
    
    if error and iterations < 3:
        print(f"--- DECISION: EXEC ERROR -> RETRY ({iterations}/3) ---")
        return "generate"
    return END

workflow.add_conditional_edges(
    "execute",
    check_execution,
    {
        "generate": "generate",
        END: END
    }
)


app = workflow.compile()
