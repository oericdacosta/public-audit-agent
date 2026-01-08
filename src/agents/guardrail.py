
import os
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.schemas.state import AgentState
from src.utils.logger import observe_node

def _load_static_prompt(filename: str) -> str:
    # Assumes file is in src/agents/../prompts
    path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", filename
    )
    with open(path, "r") as f:
        return f.read()

@observe_node(event_type="GUARDRAIL")
def guardrail_input(state: AgentState):
    messages = state["messages"]
    
    # Find the last user message
    user_input = "Unknown input"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
            
    # Load safety prompt
    safety_prompt = _load_static_prompt("guardrail_input.md")
    
    # Use GPT-4o-mini for cost-effective checks
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    chain = ChatPromptTemplate.from_messages([
        ("system", safety_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": user_input})
    verdict = response.content.strip().upper()
    
    if "UNSAFE" in verdict:
        return {
            "guardrail_verdict": "UNSAFE",
            "output": "🚫 **Process blocked by Security Policy.**\nYour request was flagged as unsafe or irrelevant to the public audit context."
        }
    
    return {"guardrail_verdict": "SAFE"}

@observe_node(event_type="GUARDRAIL")
def guardrail_output(state: AgentState):
    output = state.get("output", "No output.")
    
    # Load safety prompt
    safety_prompt = _load_static_prompt("guardrail_output.md")
    
    # Use GPT-4o-mini for cost-effective checks
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    chain = ChatPromptTemplate.from_messages([
        ("system", safety_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": output})
    sanitized_output = response.content.strip()
    
    return {"output": sanitized_output}
