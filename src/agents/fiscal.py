import os
from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from src.config import get_settings  # noqa: F401
from src.tools.database import describe_table as mcp_describe_table
from src.tools.database import list_tables as mcp_list_tables
from src.tools.database import query_sql as mcp_query_sql

# --- TOOL WRAPPERS ---


@tool
def list_tables_tool():
    """Lists all available tables in the database."""
    return mcp_list_tables()


@tool
def get_schema_tool(table_names: str):
    """
    Returns the schema for specific tables.
    Input should be a comma-separated list of table names.
    """
    tables = [t.strip() for t in table_names.split(",")]
    schemas = []
    for t in tables:
        schemas.append(mcp_describe_table(t))
    return "\n\n".join(schemas)


@tool
def run_query_tool(query: str):
    """
    Executes a SQL query against the database.
    Input must be a valid SELECT statement.
    """
    return mcp_query_sql(query)


# --- HELPER FUNCTIONS ---


def _load_prompt(filename: str) -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", filename)
    with open(prompt_path, "r") as f:
        return f.read()


def _get_llm():
    # Use gpt-4o-mini as requested for SQL specialization
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


# --- NODE FUNCTIONS ---


def force_list_tables(state: MessagesState):
    """Injects an initial tool call to list tables."""
    call_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "list_tables_tool",
                "args": {},
                "id": "init_list_tables",
                "type": "tool_call",
            }
        ],
    )
    return {"messages": [call_message]}


def call_get_schema(state: MessagesState):
    """Decides which tables to get schema for using LLM."""
    llm = _get_llm()
    llm_with_tools = llm.bind_tools([get_schema_tool], tool_choice="any")
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


def generate_query(state: MessagesState):
    """Generates the SQL query based on the schema and question."""
    llm = _get_llm()
    system_prompt = _load_prompt("fiscal_generate.md")
    system_message = SystemMessage(content=system_prompt)
    # Bind run_query_tool so the LLM writes the query as a tool call
    llm_with_tools = llm.bind_tools([run_query_tool])

    response = llm_with_tools.invoke([system_message] + state["messages"])
    return {"messages": [response]}


def check_query(state: MessagesState):
    """Double-checks the generated SQL query before execution."""
    llm = _get_llm()
    system_prompt = _load_prompt("fiscal_check.md")
    system_message = SystemMessage(content=system_prompt)

    # Get the query generated in the previous step
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return {"messages": []}

    tool_call = last_message.tool_calls[0]
    generated_sql = tool_call["args"].get("query")

    # Ask LLM to check it
    user_message_content = f"Check this query:\n{generated_sql}"
    user_message = {"role": "user", "content": user_message_content}

    llm_with_tools = llm.bind_tools([run_query_tool], tool_choice="run_query_tool")
    response = llm_with_tools.invoke([system_message, user_message])

    return {"messages": [response]}


def should_continue_gen(state: MessagesState) -> Literal["check_query", END]:
    """Decides whether to verify the query or end."""
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return END
    return "check_query"


# --- AGENT CLASS ---


class FiscalAgent:
    """
    Specialist agent for SQL generation and execution.
    Follows a strict graph: List -> Schema -> Generate -> Check -> Run.
    """

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self):
        # 1. Define Nodes
        list_tables_node = ToolNode([list_tables_tool])
        get_schema_execute_node = ToolNode([get_schema_tool])
        run_query_execute_node = ToolNode([run_query_tool])

        # 2. Build Graph
        builder = StateGraph(MessagesState)

        builder.add_node("force_list_tables", force_list_tables)
        builder.add_node("list_tables", list_tables_node)
        builder.add_node("call_get_schema", call_get_schema)
        builder.add_node("get_schema", get_schema_execute_node)
        builder.add_node("generate_query", generate_query)
        builder.add_node("check_query", check_query)
        builder.add_node("run_query", run_query_execute_node)

        # Edges
        builder.add_edge(START, "force_list_tables")
        builder.add_edge("force_list_tables", "list_tables")
        builder.add_edge("list_tables", "call_get_schema")
        builder.add_edge("call_get_schema", "get_schema")
        builder.add_edge("get_schema", "generate_query")

        builder.add_conditional_edges("generate_query", should_continue_gen)

        builder.add_edge("check_query", "run_query")

        builder.add_edge("run_query", END)

        return builder.compile()

    def run(self, user_question: str) -> str:
        """
        Executes the fiscal agent workflow.
        """
        inputs = {"messages": [("user", user_question)]}
        final_state = self.graph.invoke(inputs)

        # Extract the final result.
        messages = final_state["messages"]
        last_msg = messages[-1]

        # Start searching from the end
        for msg in reversed(messages):
            if msg.type == "tool" and msg.name == "run_query_tool":
                return msg.content

        # If we didn't find a run_query output, return the last message content
        return last_msg.content
