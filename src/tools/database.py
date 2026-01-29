"""
Database Tools.

Public interface for database operations exposed to agents and MCP server.
"""

import json
import logging
from typing import Any, Union

from src.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)

# Lazy-loaded database manager
_db = None


def _get_db():
    """Lazy-load the database manager to avoid import-time execution."""
    global _db
    if _db is None:
        from src.etl.database import DatabaseManager
        _db = DatabaseManager()
    return _db


def query_sql(sql_query: str) -> Union[list[dict[str, Any]], str]:
    """
    Execute a read-only SQL query against the database.
    
    Args:
        sql_query: SQL SELECT query to execute.
    
    Returns:
        List of result dictionaries or error message string.
    
    Raises:
        ValidationError: If query is not a SELECT statement.
    """
    normalized = sql_query.strip().upper()
    
    # Security: Only allow SELECT queries
    if not normalized.startswith("SELECT"):
        logger.warning("Rejected non-SELECT query: %s", sql_query[:50])
        return "Error: Only SELECT queries are allowed."
    
    # Additional security checks
    dangerous_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"]
    for keyword in dangerous_keywords:
        if keyword in normalized:
            logger.warning("Rejected query with dangerous keyword '%s': %s", keyword, sql_query[:50])
            return f"Error: {keyword} operations are not allowed."
    
    try:
        db = _get_db()
        results = db.execute_query(sql_query)
        return results
    except DatabaseError as e:
        return f"Error executing query: {e.message}"
    except Exception as e:
        logger.error("Unexpected error in query_sql: %s", e)
        return f"Error executing query: {e}"


def describe_table(table_name: str) -> str:
    """
    Return the schema for a specific table.
    
    Args:
        table_name: Name of the table to describe.
    
    Returns:
        DDL statement for the table or error message.
    """
    db = _get_db()
    schema = db.get_start_schema(limit_tables=[table_name])
    
    if table_name in schema:
        return schema[table_name]
    
    return f"Table '{table_name}' not found."


def search_definitions(query: str) -> list[dict[str, str]]:
    """
    Search table names and schema definitions for a keyword.
    
    Args:
        query: Keyword to search for in table names and DDL.
    
    Returns:
        List of matching tables with their definitions.
    """
    db = _get_db()
    results = db.search_schema(query)
    
    if not results:
        return []

    output: list[dict[str, str]] = []
    for table, ddl in results.items():
        output.append({"table": table, "definition": ddl})
    
    return output


def list_tables() -> list[str]:
    """
    List all available tables in the database.
    
    Returns:
        List of table names.
    """
    db = _get_db()
    return db.get_all_tables()
