from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
import os

class AnalystAgent:
    """
    Specialist agent that generates Python code to analyze audit data.
    It does not execute the code; it only generates it. Execution is done by the Sandbox.
    """
    def __init__(self, model_name="gpt-4o-mini"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Fallback or error - for now assume env var is set or handled elsewhere
            pass
        
        self.llm = ChatOpenAI(model=model_name, temperature=0)
        self.prompt = self._build_prompt()

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
print(f"Tables: {tables}")

# Query data
data = query_sql("SELECT * FROM despesas WHERE valor_liquidado > 1000 LIMIT 10")

total = sum(d['valor_pago'] for d in data)
print(f"Total spent: {total}")
```
        """
        return ChatPromptTemplate.from_messages([
            ("system", system_instructions),
            ("user", "{input}")
        ])

    def generate_code(self, user_question: str) -> str:
        chain = self.prompt | self.llm
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
