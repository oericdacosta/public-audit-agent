"""
Critic Agent.

Reviewer function that validates the Analyst's code before execution.
Uses load_prompt() with cache to avoid repeated disk reads.
"""

import logging
from typing import cast

from langchain_core.prompts import ChatPromptTemplate

from src.utils.llm import get_llm
from src.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


def review_code(question: str, code: str) -> str:
    """
    Review generated code for correctness and safety.

    Uses the critic_system.md prompt (loaded with cache) to evaluate
    the code against the user's question before sandbox execution.

    Args:
        question: The original user question the code is meant to answer.
        code: The generated Python code to review.

    Returns:
        Review verdict: "APPROVE" or "REJECT: <reason>".
    """
    llm = get_llm("critic_model", timeout=30)
    system_instructions = load_prompt("critic_system.md")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_instructions),
            (
                "user",
                "User Question: {question}\n\nGenerated Code:\n```python\n{code}\n```",
            ),
        ]
    )

    chain = prompt | llm
    response = chain.invoke({"question": question, "code": code})
    verdict = cast(str, response.content).strip()
    logger.debug("Critic verdict: %s", verdict[:100])
    return verdict
