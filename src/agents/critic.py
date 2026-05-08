"""
Critic Agent.

Reviewer function that validates the Analyst's code before execution.
Uses structured output to guarantee a clean APPROVE/REJECT verdict.
"""

import logging
from typing import Literal, Optional, cast

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from src.utils.llm import get_llm
from src.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


class _CriticOutput(BaseModel):
    verdict: Literal["APPROVE", "REJECT"]
    reason: Optional[str] = None


def review_code(question: str, code: str, schema_context: str = "") -> str:
    """
    Review generated code for correctness and safety.

    Uses the critic_system.md prompt to evaluate the code against the user's
    question before sandbox execution. Schema context (including documented FK
    gaps from dbt YAML) is injected when available.

    Args:
        question: The original user question the code is meant to answer.
        code: The generated Python code to review.
        schema_context: Compact schema string with table/column metadata.

    Returns:
        Review verdict: "APPROVE" or "REJECT [CODE]: <reason>".
    """
    llm = get_llm("critic_model", timeout=30)
    system_instructions = load_prompt("critic_system.md")
    if schema_context:
        system_instructions = (
            system_instructions + f"\n\n# Schema Context\n{schema_context}"
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_instructions),
            (
                "user",
                "User Question: {question}\n\nGenerated Code:\n```python\n{code}\n```",
            ),
        ]
    )

    chain = prompt | llm.with_structured_output(_CriticOutput)
    result = cast(_CriticOutput, chain.invoke({"question": question, "code": code}))
    logger.debug("Critic verdict: %s reason: %s", result.verdict, result.reason)

    if result.verdict == "APPROVE":
        return "APPROVE"
    return f"REJECT [CODE]: {result.reason or 'See review'}"
