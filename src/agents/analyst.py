import os

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.agents.graph import app as graph_app
from src.config import get_settings


class AnalystAgent:
    """
    Specialist agent that generates Python code to analyze audit data.
    It uses a LangGraph StateGraph to orchestrate code generation and execution
    with self-correction.
    """

    def __init__(self):
        settings = get_settings()
        try:
            self.model_name = settings["agent"]["analyst_model"]
        except KeyError as e:
            # Fallback only if absolutely necessary, but user requested strictness.
            raise ValueError("Missing 'agent.analyst_model' in config.yaml") from e
        self.graph = graph_app

    def _build_prompt(self):
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "analyst_system.md"
        )
        with open(prompt_path, "r") as f:
            system_instructions = f.read()

        return ChatPromptTemplate.from_messages(
            [("system", system_instructions), ("user", "{input}")]
        )

    def generate_code(self, user_question: str) -> str:
        """
        Generates code based on the input.
        Used by the LangGraph 'generate' node.
        """
        llm = ChatOpenAI(model=self.model_name, temperature=0)
        prompt = self._build_prompt()
        chain = prompt | llm

        response = chain.invoke({"input": user_question})

        # Clean markdown code ('''python ... ''')
        content = response.content.strip()
        if content.startswith("```python"):
            content = content[9:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        return content.strip()

    def run(self, user_question: str) -> str:
        """
        Orchestrates the full analysis process using LangGraph.
        """
        initial_state = {
            "messages": [HumanMessage(content=user_question)],
            "iterations": 0,
            "error": None,
            "code": "",
            "output": "",
        }

        # Invoke the graph
        final_state = self.graph.invoke(initial_state, config={"recursion_limit": 10})

        return final_state.get("output", "No output generated.")
