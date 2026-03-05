"""
Editor Agent Node Function.

Formats raw agent output into clear, structured Portuguese narratives
for citizens, journalists, and auditors.
"""

import logging
from typing import Any, cast

from langchain_core.prompts import ChatPromptTemplate

from src.schemas.state import AgentState
from src.utils.llm import get_llm
from src.utils.logger import observe_node
from src.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


@observe_node(event_type="THOUGHT")
def editor(state: AgentState) -> dict[str, Any]:
    """
    Format raw execution output into a structured Portuguese narrative.

    Uses the editor.md prompt (Citizen Communications Officer persona) to
    transform technical data into accessible public audit reports.

    Also surfaces the SQL query used (provenance) at the end of the response.

    Args:
        state: Current agent state with raw output and sql_query.

    Returns:
        Updated state with formatted output.
    """
    raw_output = state.get("output") or "Nenhum dado foi retornado pela execução."
    sql_query = state.get("sql_query")

    user_question = state.get("user_question") or "Consulta de auditoria pública"

    editor_prompt = load_prompt("editor.md")
    llm = get_llm("editor_model", timeout=60)

    # Build user input for the editor
    user_input = f"**User Question**: {user_question}\n\n**Raw Data**:\n{raw_output}"
    if sql_query:
        user_input += f"\n\n**Analysis Summary**: Query SQL executada: `{sql_query}`"

    prompt = ChatPromptTemplate.from_messages(
        [("system", editor_prompt), ("human", "{input}")]
    )
    chain = prompt | llm
    response = chain.invoke({"input": user_input})
    formatted = cast(str, response.content).strip()

    # ITEM 18 — Append SQL provenance to output
    if sql_query:
        formatted += (
            f"\n\n---\n\n**Proveniencia dos Dados**\n\n```sql\n{sql_query}\n```"
        )

    return {"output": formatted}
