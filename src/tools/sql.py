"""
Database Tools.

Public interface for database operations exposed to agents and MCP server.
"""

import logging
import re
import signal
from typing import Any, Tuple, Union

from src.exceptions import DatabaseError, ValidationError

logger = logging.getLogger(__name__)

# Lazy-loaded database manager
_db = None

# Configuration constants
DEFAULT_LIMIT = 1000
QUERY_TIMEOUT_SECONDS = 30


class QueryTimeout(Exception):
    """Raised when a query exceeds the time limit."""
    pass


def _get_db():
    """Lazy-load the database manager to avoid import-time execution."""
    global _db
    if _db is None:
        from src.etl.db_manager import DatabaseManager
        _db = DatabaseManager()
    return _db


def _sanitize_query(sql_query: str) -> str:
    """
    Remove SQL comments and normalize whitespace.
    
    This prevents bypass attacks using comments like:
    /* bypass */ SELECT * FROM users; DROP TABLE users
    
    Args:
        sql_query: Raw SQL query string.
    
    Returns:
        Sanitized SQL query without comments.
    """
    # Remove single-line comments (-- comment)
    sql = re.sub(r'--.*$', '', sql_query, flags=re.MULTILINE)
    # Remove multi-line comments (/* comment */)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    # Normalize whitespace
    return ' '.join(sql.split()).strip()


def _ensure_limit(sql_query: str, default_limit: int = DEFAULT_LIMIT) -> str:
    """
    Add LIMIT clause if not present to prevent OOM from large result sets.
    
    Args:
        sql_query: SQL query to check.
        default_limit: Maximum rows to return if LIMIT not specified.
    
    Returns:
        Query with LIMIT clause.
    """
    if "LIMIT" not in sql_query.upper():
        return f"{sql_query.rstrip(';')} LIMIT {default_limit}"
    return sql_query


def _timeout_handler(signum, frame):
    """Signal handler for query timeout."""
    raise QueryTimeout("Query exceeded time limit")


def validate_sql_safety(sql_query: str) -> Tuple[bool, str]:
    """
    Validate that a SQL query is safe to execute.
    
    Checks for:
    - SELECT-only queries
    - No dangerous keywords (DROP, DELETE, etc.)
    - No multiple statements (semicolon injection)
    
    Args:
        sql_query: SQL query to validate.
    
    Returns:
        Tuple of (is_safe, error_message).
    """
    sanitized = _sanitize_query(sql_query)
    normalized = sanitized.upper()
    
    # Must start with SELECT
    if not normalized.startswith("SELECT"):
        return False, "Only SELECT queries are allowed."
    
    # Check for dangerous keywords
    dangerous_keywords = [
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", 
        "CREATE", "TRUNCATE", "EXEC", "EXECUTE"
    ]
    for keyword in dangerous_keywords:
        # Use word boundary to avoid false positives (e.g., "UPDATED_AT")
        pattern = rf'\b{keyword}\b'
        if re.search(pattern, normalized):
            return False, f"{keyword} operations are not allowed."
    
    # Check for multiple statements (semicolon not at end)
    semicolon_count = sanitized.count(';')
    if semicolon_count > 1 or (semicolon_count == 1 and not sanitized.rstrip().endswith(';')):
        return False, "Multiple SQL statements are not allowed."
    
    return True, ""


def query_sql(sql_query: str) -> Union[list[dict[str, Any]], str]:
    """
    Execute a read-only SQL query against the database.
    
    Security features:
    - Sanitizes SQL comments to prevent bypass attacks
    - Validates query is SELECT-only with no dangerous keywords
    - Adds default LIMIT to prevent OOM from large result sets
    - Implements query timeout to prevent hanging queries
    
    Args:
        sql_query: SQL SELECT query to execute.
    
    Returns:
        List of result dictionaries or error message string.
    """
    # Sanitize query (remove comments)
    sanitized = _sanitize_query(sql_query)
    
    # Validate query safety
    is_safe, error = validate_sql_safety(sanitized)
    if not is_safe:
        logger.warning("Rejected unsafe query: %s - %s", sql_query[:50], error)
        return f"Error: {error}"
    
    # Add default LIMIT if not present
    query_with_limit = _ensure_limit(sanitized)
    
    try:
        db = _get_db()
        
        # Set timeout for query execution (Unix only)
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(QUERY_TIMEOUT_SECONDS)
        except (ValueError, AttributeError):
            # signal.SIGALRM not available on Windows
            pass
        
        try:
            results = db.execute_query(query_with_limit)
            return results
        finally:
            # Cancel alarm
            try:
                signal.alarm(0)
            except (ValueError, AttributeError):
                pass
                
    except QueryTimeout:
        logger.error("Query timeout after %ds: %s", QUERY_TIMEOUT_SECONDS, sql_query[:100])
        return f"Error: Query exceeded {QUERY_TIMEOUT_SECONDS} second time limit."
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
