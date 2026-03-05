"""
Database Tools.

Public interface for database operations exposed to agents and MCP server.
"""

import logging
import re
import signal
from typing import TYPE_CHECKING, Any, Optional, Tuple, Union

from src.config import get_settings
from src.exceptions import DatabaseError

if TYPE_CHECKING:
    from src.etl.db_manager import DatabaseManager
    from src.etl.schema.introspection import SchemaIntrospector

logger = logging.getLogger(__name__)

# Lazy-loaded singletons
_db: Optional["DatabaseManager"] = None
_introspector: Optional["SchemaIntrospector"] = None

# Configuration constants
DEFAULT_LIMIT = 1000
QUERY_TIMEOUT_SECONDS = get_settings().get("database", {}).get("query_timeout", 30)


class QueryTimeout(Exception):
    """Raised when a query exceeds the time limit."""


def _get_db() -> "DatabaseManager":
    """Lazy-load the database manager in read-only mode.

    Read-only allows multiple concurrent readers (agent + MCP server)
    without DuckDB file lock conflicts.
    """
    global _db
    if _db is None:
        from src.etl.db_manager import DatabaseManager

        _db = DatabaseManager(read_only=True)
    return _db


def _get_introspector() -> "SchemaIntrospector":
    """Lazy-load the schema introspector."""
    global _introspector
    if _introspector is None:
        from src.etl.schema.introspection import SchemaIntrospector

        _introspector = SchemaIntrospector(_get_db())
    return _introspector


def _sanitize_query(sql_query: str) -> str:
    """Remove SQL comments and normalize whitespace."""
    sql = re.sub(r"--.*$", "", sql_query, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return " ".join(sql.split()).strip()


def _ensure_limit(sql_query: str, default_limit: int = DEFAULT_LIMIT) -> str:
    """Add LIMIT clause if not present."""
    if "LIMIT" not in sql_query.upper():
        return f"{sql_query.rstrip(';')} LIMIT {default_limit}"
    return sql_query


def _timeout_handler(signum: int, frame: object) -> None:
    """Signal handler for query timeout."""
    raise QueryTimeout("Query exceeded time limit")


def validate_sql_safety(sql_query: str) -> Tuple[bool, str]:
    """Validate that a SQL query is safe to execute."""
    sanitized = _sanitize_query(sql_query)
    normalized = sanitized.upper()

    if not normalized.startswith("SELECT"):
        return False, "Only SELECT queries are allowed."

    dangerous_keywords = [
        "DROP",
        "DELETE",
        "INSERT",
        "UPDATE",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "EXEC",
        "EXECUTE",
        "COPY",
        "ATTACH",
        "LOAD",
        "INSTALL",
        "CALL",
    ]
    for keyword in dangerous_keywords:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, normalized):
            return False, f"{keyword} operations are not allowed."

    # Block dangerous DuckDB file/network reader functions
    dangerous_functions_pattern = (
        r"\b(read_csv|read_parquet|read_json|read_excel|read_csv_auto|glob)\s*\("
    )
    if re.search(dangerous_functions_pattern, normalized, re.IGNORECASE):
        return False, "File reader functions are not allowed for security reasons."

    semicolon_count = sanitized.count(";")
    if semicolon_count > 1:
        return False, "Multiple SQL statements are not allowed."
    if semicolon_count == 1 and not sanitized.rstrip().endswith(";"):
        return False, "Multiple SQL statements are not allowed."

    return True, ""


def query_sql(sql_query: str) -> Union[list[dict[str, Any]], str]:
    """Execute a read-only SQL query against the database."""
    sanitized = _sanitize_query(sql_query)
    is_safe, error = validate_sql_safety(sanitized)
    if not is_safe:
        logger.warning("Rejected unsafe query: %s - %s", sql_query[:50], error)
        return f"Error: {error}"

    query_with_limit = _ensure_limit(sanitized)

    try:
        db = _get_db()
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(QUERY_TIMEOUT_SECONDS)
        except (ValueError, AttributeError):
            pass

        try:
            results = db.execute_query(query_with_limit)
            return results
        finally:
            try:
                signal.alarm(0)
            except (ValueError, AttributeError):
                pass

    except QueryTimeout:
        logger.error(
            "Query timeout after %ds: %s", QUERY_TIMEOUT_SECONDS, sql_query[:100]
        )
        return f"Error: Query exceeded {QUERY_TIMEOUT_SECONDS} second time limit."
    except DatabaseError as e:
        return f"Error executing query: {e.message}"
    except Exception as e:
        logger.error("Unexpected error in query_sql: %s", e)
        return f"Error executing query: {e}"


def describe_table(table_name: str) -> str:
    """Return the schema for a specific table."""
    introspector = _get_introspector()
    schema = introspector.get_schema(limit_tables=[table_name])

    if table_name in schema:
        return schema[table_name]

    return f"Table '{table_name}' not found."


def search_definitions(query: str) -> list[dict[str, str]]:
    """Search table names and schema definitions for a keyword."""
    introspector = _get_introspector()
    results = introspector.search(query)

    if not results:
        return []

    output: list[dict[str, str]] = []
    for table, ddl in results.items():
        output.append({"table": table, "definition": ddl})

    return output


def list_tables() -> list[str]:
    """List all available tables in the database."""
    introspector = _get_introspector()
    return introspector.get_all_tables()
