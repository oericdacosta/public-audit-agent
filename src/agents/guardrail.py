import os
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from src.schemas.state import AgentState

def _load_static_prompt(filename: str) -> str:
    # Assumes file is in src/agents/../prompts
    path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", filename
    )
    with open(path, "r") as f:
        return f.read()

def guardrail_input(state: AgentState):
    print("--- NODE: GUARDRAIL INPUT ---")
    messages = state["messages"]
    
    # Find the last user message
    user_input = "Unknown input"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
            
    # Load safety prompt
    safety_prompt = _load_static_prompt("guardrail_input.md")
    
    # Use a fast model for the check
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    chain = ChatPromptTemplate.from_messages([
        ("system", safety_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": user_input})
    verdict = response.content.strip().upper()
    
    print(f"Guardrail Verdict: {verdict}")
    
    if "UNSAFE" in verdict:
        return {
            "guardrail_verdict": "UNSAFE",
            "output": "🚫 **Process blocked by Security Policy.**\nYour request was flagged as unsafe or irrelevant to the public audit context."
        }
    
    return {"guardrail_verdict": "SAFE"}


def guardrail_output(state: AgentState):
    print("--- NODE: GUARDRAIL OUTPUT ---")
    output = state.get("output", "No output.")
    
    # Load safety prompt
    safety_prompt = _load_static_prompt("guardrail_output.md")
    
    # Use a fast model for the check
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    chain = ChatPromptTemplate.from_messages([
        ("system", safety_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": output})
    sanitized_output = response.content.strip()
    
    if sanitized_output != output:
        print("GUARDAIL OUTPUT: Content sanitized.")

    return {"output": sanitized_output}
