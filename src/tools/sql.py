"""
Database Tools.

Public interface for database operations exposed to agents and MCP server.
"""

import logging
import re
import signal
from pathlib import Path
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


def _load_column_meta_tags() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """
    Load column-level meta tags from dbt mart YAML files.

    Returns:
        (monetary_index, always_null_index) where each maps table name to
        set of column names with that tag.
        Empty dicts if mart directory not found or YAML parsing fails.
    """
    import yaml

    monetary: dict[str, set[str]] = {}
    always_null: dict[str, set[str]] = {}
    mart_dir = (
        Path(__file__).resolve().parent.parent.parent / "dbt" / "models" / "marts"
    )
    if not mart_dir.exists():
        return monetary, always_null

    for yml_file in mart_dir.glob("*.yml"):
        try:
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            for model in data.get("models", []):
                name = model.get("name", "")
                if not name:
                    continue
                mon_cols: set[str] = set()
                null_cols: set[str] = set()
                for col in model.get("columns", []):
                    col_name = col.get("name", "")
                    meta = col.get("meta") or {}
                    if col_name and meta.get("semantic_type") == "monetary_brl":
                        mon_cols.add(col_name)
                    if col_name and meta.get("data_quality") == "always_null":
                        null_cols.add(col_name)
                if mon_cols:
                    monetary[name] = mon_cols
                if null_cols:
                    always_null[name] = null_cols
        except Exception:
            pass

    return monetary, always_null


def _load_mart_descriptions() -> dict[str, str]:
    """
    Load one-line model descriptions from dbt mart YAML files.

    Reads dbt/models/marts/*.yml and extracts the first sentence of each
    model's description. Used to annotate compact schema lines so the LLM
    understands table semantics without relying on column names alone.

    Returns:
        Dict mapping table name to a short description string (≤ 150 chars).
        Empty dict if the mart directory is not found or YAML parsing fails.
    """
    import yaml

    descriptions: dict[str, str] = {}
    mart_dir = (
        Path(__file__).resolve().parent.parent.parent / "dbt" / "models" / "marts"
    )
    if not mart_dir.exists():
        return descriptions

    for yml_file in mart_dir.glob("*.yml"):
        try:
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            for model in data.get("models", []):
                name = model.get("name", "")
                desc = str(model.get("description", "")).strip()
                if name and desc:
                    # First non-empty line, truncated at 150 chars
                    short = next(
                        (ln.strip() for ln in desc.splitlines() if ln.strip()), desc
                    )
                    if len(short) > 150:
                        short = short[:150].rsplit(" ", 1)[0] + "…"
                    descriptions[name] = short
        except Exception:
            pass

    return descriptions


def list_tables_compact(table_names: Optional[list[str]] = None) -> str:
    """
    Return compact schema for the specified tables as a single formatted string.

    Each line has the format:
        table_name [description]: col1 TYPE, col2 TYPE, ...

    The description is read from the dbt mart YAML files (first sentence of the
    model description). It gives the LLM semantic context — e.g., that
    fct_servidores has NO salary data — without expanding to full DDL.

    Args:
        table_names: Tables to include. None returns all tables.

    Returns:
        Multi-line string with one table per line.
    """
    introspector = _get_introspector()
    compact = introspector.get_compact_schema(table_names)
    descriptions = _load_mart_descriptions()
    monetary_index, always_null_index = _load_column_meta_tags()

    lines = []
    for table, cols in sorted(compact.items()):
        table_monetary = monetary_index.get(table, set())
        table_always_null = always_null_index.get(table, set())
        if table_monetary or table_always_null:
            annotated = []
            for part in cols.split(", "):
                col_name = part.split(" ")[0]
                tags = []
                if col_name in table_monetary:
                    tags.append("monetary")
                if col_name in table_always_null:
                    tags.append("NULL:API não retorna")
                if tags:
                    annotated.append(part + " [" + "][".join(tags) + "]")
                else:
                    annotated.append(part)
            cols = ", ".join(annotated)

        desc = descriptions.get(table, "")
        if desc:
            lines.append(f"{table} [{desc}]: {cols}")
        else:
            lines.append(f"{table}: {cols}")

    legend = (
        "# Type guide: INTEGER/BIGINT = unquoted (2024), "
        "VARCHAR = quoted ('sobral'), [monetary] = R$ currency column, "
        "[NULL:API não retorna] = always NULL in source, "
        "never use for filtering/sorting"
    )
    return "\n".join(lines) + "\n" + legend
