from src.etl.database import DatabaseManager as Database

db = Database()


def query_sql(sql_query: str):
    """Executes a read-only SQL query against the database."""
    if not sql_query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."
    try:
        results = db.execute_query(sql_query)
        return results
    except Exception as e:
        return f"Error executing query: {str(e)}"


def describe_table(table_name: str) -> str:
    """Returns the schema for a specific table."""
    schema = db.get_start_schema(limit_tables=[table_name])
    if table_name in schema:
        return schema[table_name]
    return f"Table '{table_name}' not found."


def search_definitions(query: str) -> list[dict]:
    """Searches table names and schema definitions (DDL) for a given keyword."""
    results = db.search_schema(query)
    if not results:
        return []

    output = []
    for table, ddl in results.items():
        output.append({"table": table, "definition": ddl})
    return output


def list_tables():
    """Lists all available tables in the database."""
    tables = db.get_all_tables()
    return tables
