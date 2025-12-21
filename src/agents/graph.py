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
    iterations: int

# 2. Node: Generate Code
def generate(state: AgentState):
    print("--- NODE: GENERATE ---")
    messages = state['messages']
    error = state.get('error')
    
    # If there is an error, we need to inform the agent
    if error:
        messages.append(HumanMessage(content=f"The previous code failed with this error:\n{error}\nPlease fix the code and try again."))
    
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
    
    return {"code": code, "iterations": state['iterations'] + 1}

# 3. Node: Execute Code
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

# 4. Conditional Edge: Should Continue?
def should_continue(state: AgentState):
    error = state.get('error')
    iterations = state.get('iterations')
    
    if error and iterations < 3: # Max 3 retries
        print(f"--- DECISION: RETRY ({iterations}/3) ---")
        return "generate"
    
    print("--- DECISION: END ---")
    return END

# 5. Build the Graph
workflow = StateGraph(AgentState)

workflow.add_node("generate", generate)
workflow.add_node("execute", execute)

workflow.set_entry_point("generate")

workflow.add_edge("generate", "execute")
workflow.add_conditional_edges(
    "execute",
    should_continue,
    {
        "generate": "generate",
        END: END
    }
)

app = workflow.compile()
