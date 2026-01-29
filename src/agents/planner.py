"""
Planner Agent Node Function.

Responsible for decomposing user queries into execution plans.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.schemas.state import AgentState
from src.utils.logger import observe_node
from src.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


@observe_node(event_type="THOUGHT")
def planner(state: AgentState) -> dict[str, Any]:
    """
    Create an execution plan based on the user's question.
    
    Args:
        state: Current agent state containing user messages.
    
    Returns:
        Updated state with execution plan and plan message.
    """
    messages = state["messages"]
    
    # Find the last user message
    user_input = "Unknown input"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
            
    # Load planner prompt using shared utility
    planner_prompt = load_prompt("planner.md")
    
    # Use a reasoning model for planning
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    chain = ChatPromptTemplate.from_messages([
        ("system", planner_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": user_input})
    plan_text = response.content.strip()
    
    # Append the plan to the message history so the Analyst sees it
    plan_message = HumanMessage(
        content=f"Here is the execution plan you must follow:\n{plan_text}"
    )
    
    return {
        "plan": plan_text,
        "messages": [plan_message]
    }
