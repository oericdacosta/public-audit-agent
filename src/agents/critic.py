import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from src.config import get_settings


class CriticAgent:
    """
    Reviewer agent that validates the Analyst's code BEFORE execution.
    It checks for:
    1. Alignment with user question (e.g. correct year, correct filters).
    2. Safety (no dangerous commands).
    3. Completeness (uses print to show results).
    """

    def __init__(self):
        settings = get_settings()
        try:
            model_name = settings["agent"]["critic_model"]
        except KeyError as e:
            raise ValueError("Missing 'agent.critic_model' in config.yaml") from e

        api_key = os.getenv("GOOGLE_API_KEY")

        self.llm = ChatGoogleGenerativeAI(
            model=model_name, temperature=0, google_api_key=api_key
        )
        self.prompt = self._build_prompt()

    def _build_prompt(self):
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "critic_system.md"
        )
        with open(prompt_path, "r") as f:
            system_instructions = f.read()

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_instructions),
                (
                    "user",
                    "User Question: {question}\n\nGenerated Code:\n"
                    "```python\n{code}\n```",
                ),
            ]
        )

    def review_code(self, question: str, code: str) -> str:
        chain = self.prompt | self.llm
        response = chain.invoke({"question": question, "code": code})
        return response.content.strip()
