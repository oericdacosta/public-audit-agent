import os
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.schemas.state import AgentState

def _load_static_prompt(filename: str) -> str:
    path = os.path.join(
        os.path.dirname(__file__), "..", "prompts", filename
    )
    with open(path, "r") as f:
        return f.read()

def planner(state: AgentState):
    print("--- NODE: PLANNER ---")
    messages = state["messages"]
    
    # Find the last user message
    user_input = "Unknown input"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
            
    # Load planner prompt
    planner_prompt = _load_static_prompt("planner.md")
    
    # Use a reasoning model (or strong model) for planning
    # gpt-4o or gpt-4o-mini depending on complexity/cost trade-off. 
    # Using gpt-4o-mini for speed/efficiency as requested in plan, but could be upgraded.
    llm = ChatOpenAI(model="gpt-4o", temperature=0) 
    
    chain = ChatPromptTemplate.from_messages([
        ("system", planner_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": user_input})
    plan_text = response.content.strip()
    
    print(f"Generated Plan:\n{plan_text}")
    
    # Append the plan to the message history so the Analyst sees it
    plan_message = HumanMessage(content=f"Here is the execution plan you must follow:\n{plan_text}")
    
    return {
        "plan": plan_text,
        "messages": [plan_message]
    }
