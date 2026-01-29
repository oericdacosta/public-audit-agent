"""
Analyst Agent Node Functions.

This module contains the node functions used by the AuditGraph workflow
for code generation, critique, and execution.
"""

import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END

from src.config import get_settings
from src.execution.sandbox import DockerSandbox
from src.schemas.state import AgentState
from src.utils.logger import observe_node
from src.utils.parsing import clean_markdown_code
from src.utils.prompts import load_prompt_components

logger = logging.getLogger(__name__)


# --- PRIVATE HELPER FUNCTIONS ---


def _build_prompt() -> str:
    """Build the analyst system prompt from component files."""
    return load_prompt_components("identity.md", "rules.md", "examples.md")


def _generate_code_logic(user_question: str, sql_query: Optional[str] = None) -> str:
    """
    Core logic to generate code using LLM.
    
    Args:
        user_question: The user's question to generate code for.
        sql_query: Optional pre-generated SQL query from Fiscal Agent.
    
    Returns:
        Generated Python code as a string.
    """
    settings = get_settings()
    model_name = settings["agent"]["analyst_model"]
    llm = ChatOpenAI(model=model_name, temperature=0)

    system_instructions = _build_prompt()
    
    # Inject the SQL from Fiscal Agent if available
    input_text = f"User Question: {user_question}"
    if sql_query:
        input_text += (
            f"\n\nPre-Generated, Validated SQL by Fiscal Agent (USE THIS):\n"
            f"```sql\n{sql_query}\n```\n"
            "Make sure to use `query_sql(sql_query)` with this exact query."
        )

    prompt = ChatPromptTemplate.from_messages(
        [("system", system_instructions), ("user", "{input}")]
    )
    chain = prompt | llm
    response = chain.invoke({"input": input_text})

    return clean_markdown_code(response.content)


# --- NODE FUNCTIONS ---


@observe_node(event_type="THOUGHT")
def generate(state: AgentState) -> dict[str, Any]:
    """
    Generate Python code based on user question and optional SQL query.
    
    Args:
        state: Current agent state containing messages, errors, and evaluations.
    
    Returns:
        Updated state with generated code, incremented iterations, and cleared errors.
    """
    logger.debug("NODE: GENERATE")
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
    sql_query = state.get("sql_query")
    
    code = _generate_code_logic(last_message, sql_query)

    return {
        "code": code,
        "iterations": state.get("iterations", 0) + 1,
        "error": None,
        "evaluation": None,
    }


@observe_node(event_type="THOUGHT")
def critique(state: AgentState) -> dict[str, str]:
    """
    Review generated code using the CriticAgent.
    
    Args:
        state: Current agent state containing code and messages.
    
    Returns:
        Updated state with critic's evaluation.
    """
    logger.debug("NODE: CRITIC")
    code = state["code"]
    messages = state["messages"]
    
    # Find the last user message to evaluate against
    user_question = "Unknown question"
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            user_question = m.content
            break

    # Import here to avoid circular dependency
    from src.agents.critic import CriticAgent

    critic = CriticAgent()
    evaluation = critic.review_code(user_question, code)
    logger.debug("Critic Verdict: %s", evaluation)

    return {"evaluation": evaluation}


@observe_node(event_type="TOOL_CALL")
def execute(state: AgentState) -> dict[str, Optional[str]]:
    """
    Execute generated code in a Docker sandbox.
    
    Args:
        state: Current agent state containing code to execute.
    
    Returns:
        Updated state with execution output and any errors.
    """
    logger.debug("NODE: EXECUTE")
    code = state["code"]
    logger.debug("EXECUTING CODE:\n%s\n----------------", code)
    
    sandbox = DockerSandbox()
    result = sandbox.execute(code)

    if (
        result.startswith("Execution Error")
        or result.startswith("System Error")
        or "Traceback" in result
    ):
        return {"output": result, "error": result}
    
    return {"output": result, "error": None}


def should_continue(state: AgentState) -> str:
    """
    Determine whether to continue the generate-critique loop.
    
    Args:
        state: Current agent state with iteration count and any errors.
    
    Returns:
        Either "generate" to retry or END to finish.
    """
    settings = get_settings()
    max_retries = settings.get("agent", {}).get("max_retries", 3)

    error = state.get("error")
    evaluation = state.get("evaluation")
    iterations = state.get("iterations")

    if evaluation and "REJECT" in evaluation:
        if iterations < max_retries:
            logger.debug("DECISION: REJECTED -> RETRY (%d/%d)", iterations, max_retries)
            return "generate"
        else:
            logger.debug("DECISION: MAX RETRIES (CRITIC)")
            return END

    if error:
        if iterations < max_retries:
            logger.debug("DECISION: ERROR -> RETRY (%d/%d)", iterations, max_retries)
            return "generate"

    logger.debug("DECISION: END")
    return END


def check_execution(state: AgentState) -> str:
    """
    Check execution result and decide whether to retry.
    
    Args:
        state: Current agent state with execution result.
    
    Returns:
        Either "generate" to retry or END to finish.
    """
    error = state.get("error")
    iterations = state.get("iterations")

    if error and iterations < 3:
        logger.debug("DECISION: EXEC ERROR -> RETRY (%d/3)", iterations)
        return "generate"
    
    return END
