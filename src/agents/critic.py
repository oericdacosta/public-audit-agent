"""
Critic Agent.

Reviewer agent that validates the Analyst's code before execution.
"""

import logging
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from src.utils.llm import get_llm

logger = logging.getLogger(__name__)


class CriticAgent:
    """
    Reviewer agent that validates the Analyst's code BEFORE execution.
    
    Checks for:
    1. Alignment with user question (e.g., correct year, correct filters).
    2. Safety (no dangerous commands).
    3. Completeness (uses print to show results).
    """

    def __init__(self) -> None:
        """Initialize the CriticAgent with configured LLM."""
        self.llm = get_llm("critic_model")
        self.prompt = self._build_prompt()

    def _build_prompt(self) -> ChatPromptTemplate:
        """Build the critic prompt template."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "critic_system.md"
        system_instructions = prompt_path.read_text(encoding="utf-8")

        return ChatPromptTemplate.from_messages([
            ("system", system_instructions),
            (
                "user",
                "User Question: {question}\n\n"
                "Generated Code:\n```python\n{code}\n```"
            ),
        ])

    def review_code(self, question: str, code: str) -> str:
        """
        Review generated code for correctness and safety.
        
        Args:
            question: The original user question.
            code: The generated Python code to review.
        
        Returns:
            Review verdict (APPROVE or REJECT with feedback).
        """
        chain = self.prompt | self.llm
        response = chain.invoke({"question": question, "code": code})
        return response.content.strip()
