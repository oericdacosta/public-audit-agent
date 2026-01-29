"""
Guardrail Agent Node Functions.

Input and output safety validation for the audit workflow.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from src.schemas.state import AgentState
from src.utils.llm import get_llm
from src.utils.logger import observe_node
from src.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


@observe_node(event_type="GUARDRAIL")
def guardrail_input(state: AgentState) -> dict[str, Any]:
    """
    Validate user input for safety and relevance.
    
    Args:
        state: Current agent state containing user messages.
    
    Returns:
        Updated state with guardrail verdict and optional blocked output.
    """
    messages = state["messages"]
    
    # Find the last user message
    user_input = "Unknown input"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break
            
    # Load safety prompt using shared utility
    safety_prompt = load_prompt("guardrail_input.md")
    
    # Use config-driven model for cost-effective checks
    llm = get_llm("guardrail_model")
    
    chain = ChatPromptTemplate.from_messages([
        ("system", safety_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": user_input})
    verdict = response.content.strip().upper()
    
    if "UNSAFE" in verdict:
        logger.warning("Input blocked by guardrail: %s", user_input[:100])
        return {
            "guardrail_verdict": "UNSAFE",
            "output": (
                "🚫 **Process blocked by Security Policy.**\n"
                "Your request was flagged as unsafe or irrelevant "
                "to the public audit context."
            )
        }
    
    return {"guardrail_verdict": "SAFE"}


@observe_node(event_type="GUARDRAIL")
def guardrail_output(state: AgentState) -> dict[str, str]:
    """
    Sanitize and validate output before returning to user.
    
    Args:
        state: Current agent state containing output to validate.
    
    Returns:
        Updated state with sanitized output.
    """
    output = state.get("output", "No output.")
    
    # Load safety prompt using shared utility
    safety_prompt = load_prompt("guardrail_output.md")
    
    # Use config-driven model for cost-effective checks
    llm = get_llm("guardrail_model")
    
    chain = ChatPromptTemplate.from_messages([
        ("system", safety_prompt),
        ("human", "{input}")
    ]) | llm
    
    response = chain.invoke({"input": output})
    sanitized_output = response.content.strip()
    
    return {"output": sanitized_output}
