import operator
from typing import Annotated, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    State definition for the Analyst Graph.
    Acts as the contract between nodes.
    """

    messages: Annotated[List[BaseMessage], operator.add]
    code: str
    output: str
    error: Optional[str]
    evaluation: Optional[str]  # Critic's feedback
    iterations: int
