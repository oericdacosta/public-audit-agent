from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from src.agents.graph import app as graph_app
import os

class AnalystAgent:
    """
    Specialist agent that generates Python code to analyze audit data.
    It uses a LangGraph StateGraph to orchestrate code generation and execution with self-correction.
    """
    def __init__(self, model_name="gpt-4o-mini"):
        # The core logic is now in the graph, but we keep this class as the main entry point
        # for API consistency.
        self.graph = graph_app

    # We keep this helper for the Generate Node to use (circular dependency avoidance strategy:
    # ideally, the node logic should be decoupled, but for now we will instantiate the LLM in the node
    # or pass it. In src/agents/graph.py we instantiated a NEW AnalystAgent(), which is risky for recursion.
    # Refactoring:
    # The 'generate' node in graph.py instantiates AnalystAgent. 
    # If we change AnalystAgent to USE graph.py, we have a cycle if graph.py imports AnalystAgent.
    # 
    # SOLUTION: We will extract the LLM generation logic to a mixin or separate method that graph.py can use, 
    # OR we make AnalystAgent the "orchestrator" and the graph uses a lighter "Generator" class.
    #
    # Given the current setup in graph.py:
    # "agent = AnalystAgent()" inside generate()
    #
    # If I change AnalystAgent here to call app.invoke(), then generate() calling AnalystAgent() will create infinite recursion if it calls run().
    # But generate() calls generate_code().
    #
    # So:
    # 1. AnalystAgent.run(question) -> calls Graph
    # 2. Graph Node "generate" -> calls AnalystAgent.generate_code(question)
    #
    # This works IF generate_code() is PURE GENERATION (Chain only).
    # And run() is the Orchestration.
    
    def _build_prompt(self):
        system_instructions = """
You are a Senior Data Auditor (Code Mode).
Your task is to answer questions about public data by writing Python scripts.

RULES:
1. DO NOT respond with explanatory text. Respond ONLY with Python code.
2. Your code must be complete and executable.
3. You have access to the following functions (tools) that are already imported in the environment:
   - `query_sql(query: str) -> list[dict]`: Executes SQL in the database (readonly).
   - `print(obj)`: Use print to show the final result.

4. ATTENTION: The database is **SQLite**.
   - DO NOT use `information_schema`.
   - Use `search_definitions(keyword)` to find tables related to your query (e.g., 'educacao', 'saude').
   - Use `list_tables()` ONLY if you need a full overview.
   - Use `describe_table(table_name)` to see the schema (already imported).
   - Dates are in TEXT format (ISO 8601) or similar.

5. When generating charts, save them as files (e.g., 'chart.png') instead of trying to show them on screen.

EXAMPLE OF CORRECT RESPONSE:
```python
# Discover tables
tables = list_tables()
print(f"Tables: {{tables}}")

# Query data
data = query_sql("SELECT * FROM despesas WHERE valor_liquidado > 1000 LIMIT 10")

total = sum(d['valor_pago'] for d in data)
print(f"Total spent: {{total}}")
```
        """
        return ChatPromptTemplate.from_messages([
            ("system", system_instructions),
            ("user", "{input}")
        ])

    def generate_code(self, user_question: str) -> str:
        """
        Generates code based on the input. 
        Used by the LangGraph 'generate' node.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
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
            "output": ""
        }
        
        # Invoke the graph
        final_state = self.graph.invoke(initial_state, config={"recursion_limit": 10})
        
        return final_state.get("output", "No output generated.")
