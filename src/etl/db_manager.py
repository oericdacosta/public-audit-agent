"""
Database Manager.

Handles DuckDB database connections, schema initialization, and query execution.
Uses a single persistent connection with a lock for thread safety.
"""

import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import duckdb
from duckdb import DuckDBPyConnection

from src.config import CONFIG_PATH, get_settings
from src.exceptions import ConfigurationError, DatabaseError

logger = logging.getLogger(__name__)

# Schema file location relative to this module
_SCHEMA_DIR = Path(__file__).parent / "schema"
_TABLES_SQL = _SCHEMA_DIR / "tables.sql"

# Allowlist of valid table names for SQL injection protection
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "licitacoes",
        "despesas",
        "receitas",
        "balancete_despesa_extra",
        "etl_metadata",
        # Dimension/lookup tables
        "municipios",
        "orgaos",
        "unidades_orcamentarias",
        "funcoes",
        "contas_bancarias",
        "programas",
        "orcamento_despesa",
        "orcamento_receita",
        "itens_licitacoes",
        "licitantes",
        "agentes_publicos",
    }
)


class DatabaseManager:
    """
    Manages DuckDB database connections and core operations.

    Uses a single persistent connection with a lock to avoid
    DuckDB file handle conflicts in multi-threaded environments.
    """

    def __init__(self, read_only: bool = False) -> None:
        """Initialize the database manager with configured path.

        Args:
            read_only: Open connection in read-only mode. Allows multiple
                       concurrent readers without DuckDB lock conflicts.
                       Use True for query-only workloads (MCP server, agent).
        """
        settings = get_settings()
        try:
            db_path_str = settings["database"]["path"]
            if db_path_str.endswith(".db") or db_path_str.endswith(".sqlite"):
                db_path_str = db_path_str.replace(".db", ".duckdb").replace(
                    ".sqlite", ".duckdb"
                )
            db_path = Path(db_path_str)
            if not db_path.is_absolute():
                db_path = (CONFIG_PATH.parent / db_path).resolve()
            self.db_path = str(db_path)
        except KeyError as e:
            raise ConfigurationError(
                "Missing configuration key",
                details="'database.path' not found in config.yaml",
            ) from e
        self._setup_directories()
        # Single persistent connection + lock for thread safety
        self._conn: DuckDBPyConnection = duckdb.connect(
            self.db_path, read_only=read_only
        )
        self._conn_lock = threading.Lock()
        # Cache for table column info
        self._columns_cache: dict[str, list[str]] = {}

    def _validate_table_name(self, table_name: str) -> None:
        """Validate table name against allowlist to prevent SQL injection."""
        if table_name not in ALLOWED_TABLES:
            if not table_name.isidentifier():
                raise ValueError(f"Invalid table name: {table_name}")
            logger.warning(
                "Table '%s' not in allowlist. Consider adding it.",
                table_name,
            )

    def _setup_directories(self) -> None:
        """Create necessary directories for database and logs."""
        db_path = Path(self.db_path)
        if db_path.parent:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Generator[DuckDBPyConnection, None, None]:
        """
        Get exclusive access to the shared database connection.

        Uses a lock to serialize all database operations for thread safety.
        DuckDB does not support concurrent writes from multiple connections.
        """
        with self._conn_lock:
            yield self._conn

    def close(self) -> None:
        """Close the persistent connection."""
        with self._conn_lock:
            self._conn.close()

    def initialize_schema(self) -> None:
        """
        Initialize all database tables and indexes from SQL file.

        Loads schema definitions from src/etl/schema/tables.sql.
        """
        if not _TABLES_SQL.exists():
            raise ConfigurationError(
                "Schema file not found",
                details=f"Expected schema at: {_TABLES_SQL}",
            )

        schema_sql = _TABLES_SQL.read_text(encoding="utf-8")

        with self.get_connection() as conn:
            conn.execute(schema_sql)
            logger.info("Database schema initialized from %s", _TABLES_SQL.name)

    def execute_query(self, query: str) -> list[dict[str, Any]]:
        """
        Execute a SQL query and return results as list of dicts.

        Args:
            query: SQL query to execute.

        Returns:
            List of dictionaries representing rows.

        Raises:
            DatabaseError: If query execution fails.
        """
        try:
            with self.get_connection() as conn:
                from typing import cast

                df = conn.execute(query).df()
                return cast(list[dict[str, Any]], df.to_dict(orient="records"))
        except (duckdb.Error, Exception) as e:
            raise DatabaseError("Query execution failed", details=str(e)) from e

    def _get_table_columns(
        self, table_name: str, conn: DuckDBPyConnection
    ) -> list[str]:
        """Get table columns, using cache when available."""
        if table_name in self._columns_cache:
            return self._columns_cache[table_name]

        columns = [
            col[1]
            for col in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        ]

        self._columns_cache[table_name] = columns
        return columns

    def load_data(
        self, table_name: str, data: dict[str, Any] | list[dict[str, Any]]
    ) -> None:
        """
        Load JSON data into a table using DataFrame INSERT.

        Uses DuckDB's native DataFrame support with UPSERT for tables with 'id'.

        Args:
            table_name: Target table name.
            data: List of dicts or single dict to insert.
        """
        if not data:
            return

        if isinstance(data, dict):
            data = [data]

        import pandas as pd

        df = pd.DataFrame(data)

        if df.empty:
            return

        try:
            self._validate_table_name(table_name)

            with self.get_connection() as conn:
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {table_name} "  # nosec B608
                    "AS SELECT * FROM df LIMIT 0"
                )

                columns = self._get_table_columns(table_name, conn)

                # Filter DataFrame to only columns that exist in the table
                valid_cols = [c for c in df.columns if c in columns]
                if not valid_cols:
                    logger.warning(
                        f"No matching columns between data and table {table_name}"
                    )
                    logger.debug(f"DataFrame columns: {list(df.columns)}")
                    logger.debug(f"Table columns: {columns}")
                    return

                df_cols = ", ".join(valid_cols)

                if "id" in columns and "id" in valid_cols:
                    update_cols = [c for c in valid_cols if c != "id"]
                    update_set = ", ".join(
                        [f"{col} = EXCLUDED.{col}" for col in update_cols]
                    )

                    conn.execute(
                        f"INSERT INTO {table_name} ({df_cols}) "  # nosec B608
                        f"SELECT {df_cols} FROM df "
                        f"ON CONFLICT (id) DO UPDATE SET {update_set}"
                    )
                else:
                    conn.execute(
                        f"INSERT INTO {table_name} ({df_cols}) "  # nosec B608
                        f"SELECT {df_cols} FROM df"
                    )

                conn.commit()

        except (duckdb.Error, Exception) as e:
            logger.error(f"Failed to load data into {table_name}: {e}")
            raise DatabaseError(f"Load failed for {table_name}", details=str(e)) from e
