"""
Analyst Agent Node Functions.

This module contains the node functions used by the AuditGraph workflow
for code generation, critique, and execution.
"""

import logging
from typing import Any, Optional, cast

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END

from src.config import get_settings
from src.execution.sandbox import DockerSandbox
from src.schemas.state import AgentState
from src.utils.llm import get_llm
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
    llm = get_llm("analyst_model", timeout=90)

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

    return clean_markdown_code(response.content)  # type: ignore


# --- NODE FUNCTIONS ---


@observe_node(event_type="THOUGHT", model_key="analyst_model")
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
    last_message = str(messages[-1].content)
    sql_query = cast(str, state.get("sql_query")) if state.get("sql_query") else None

    code = _generate_code_logic(last_message, sql_query)

    return {
        "code": code,
        "iterations": state.get("iterations", 0) + 1,
        "error": None,
        "evaluation": None,
    }


@observe_node(event_type="THOUGHT", model_key="critic_model")
def critique(state: AgentState) -> dict[str, str]:
    """
    Review generated code using the CriticAgent.

    Args:
        state: Current agent state containing code and messages.

    Returns:
        Updated state with critic's evaluation.
    """
    logger.debug("NODE: CRITIC")
    code = state["code"] or ""

    # Use the original user question stored at guardrail time.
    # Do NOT scan messages backwards — after the first REJECT, generate() appends
    # a HumanMessage with critic feedback, which would become the "question" and
    # cause the critic to review code against the wrong prompt on retry passes.
    user_question = state.get("user_question") or "Unknown question"

    from src.agents.critic import review_code

    evaluation = review_code(user_question, code)
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

    sandbox = DockerSandbox.get_instance()
    result = sandbox.execute(code)  # type: ignore

    if (
        result.startswith("Execution Error")
        or result.startswith("System Error")
        or "Traceback" in result
    ):
        return {"output": result, "error": result}

    return {"output": result, "error": None}


@observe_node(event_type="TOOL_CALL")
def simple_execute(state: AgentState) -> dict[str, Any]:
    """
    Execute a pre-validated SQL query directly without Python code generation.

    Used for simple single-aggregation queries to bypass the full analyst pipeline
    (generate Python → critic → Docker sandbox), saving ~3.7s and ~2 LLM calls.

    Returns:
        Updated state with SQL result as output.
    """
    import json

    from src.tools.sql import query_sql

    logger.debug("NODE: SIMPLE_EXECUTE")
    sql_query = state.get("sql_query") or ""
    logger.debug("SIMPLE EXECUTE SQL: %s", sql_query)

    result = query_sql(sql_query)
    if isinstance(result, str):
        output = result
    elif isinstance(result, list):
        # Sanitize NaN/Inf floats → None so JSON is always valid
        sanitized = []
        for row in result:
            if isinstance(row, dict):
                sanitized.append(
                    {
                        k: (None if isinstance(v, float) and not (v == v) else v)
                        for k, v in row.items()
                    }
                )
            else:
                sanitized.append(row)
        output = json.dumps(sanitized, ensure_ascii=False)
    else:
        output = json.dumps(result, ensure_ascii=False)
    return {"output": output, "error": None}


def should_continue(state: AgentState) -> str:
    """
    Determine whether to continue the generate-critique loop.

    Returns one of three values:
    - "generate": REJECT with retries remaining → regenerate code
    - "execute": APPROVE → run the code in sandbox
    - "abort": REJECT at max_retries → skip execution, go to output

    Args:
        state: Current agent state with iteration count and any errors.

    Returns:
        "generate", "execute", or "abort".
    """
    settings = get_settings()
    max_retries = settings.get("agent", {}).get("max_retries", 3)

    evaluation = state.get("evaluation")
    iterations = state.get("iterations")

    if evaluation and "REJECT" in evaluation:
        if iterations < max_retries:
            logger.debug("DECISION: REJECTED -> RETRY (%d/%d)", iterations, max_retries)
            return "generate"
        else:
            logger.debug("DECISION: MAX RETRIES REACHED -> ABORT")
            return "abort"

    logger.debug("DECISION: APPROVED -> EXECUTE")
    return "execute"


def check_execution(state: AgentState) -> str:
    """
    Check execution result and decide whether to retry.

    Args:
        state: Current agent state with execution result.

    Returns:
        Either "generate" to retry or END to finish.
    """
    settings = get_settings()
    max_retries = settings.get("agent", {}).get("max_retries", 3)

    error = state.get("error")
    iterations = state.get("iterations", 0)

    if error and iterations < max_retries:
        logger.debug("DECISION: EXEC ERROR -> RETRY (%d/%d)", iterations, max_retries)
        return "generate"

    return cast(str, END)
