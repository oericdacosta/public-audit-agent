"""
Database Manager.

Handles DuckDB database connections, schema initialization, and query execution.
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import duckdb
from duckdb import DuckDBPyConnection

from src.config import get_settings
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
        "balancete_receita_extra",
        "etl_metadata",
        # Dimension/lookup tables
        "municipios",
        "orgaos",
        "unidades_orcamentarias",
        "funcoes",
        "ordenadores",
        "contas_bancarias",
        "programas",
        "orcamento_despesa",
        "orcamento_receita",
        "taloes_receitas",
        "taloes_extras",
        "contratos",
        "contratados",
        "itens_licitacoes",
        "licitantes",
        "notas_fiscais",
        "notas_pagamentos",
        "itens_notas_fiscais",
        "agentes_publicos",
    }
)


class DatabaseManager:
    """
    Manages DuckDB database connections and core operations.

    Focused on: connection management, schema initialization,
    query execution, and data loading.

    For schema introspection, use SchemaIntrospector.
    For ETL metadata tracking, use ETLMetadataManager.
    """

    def __init__(self) -> None:
        """Initialize the database manager with configured path."""
        settings = get_settings()
        try:
            db_path_str = settings["database"]["path"]
            if db_path_str.endswith(".db") or db_path_str.endswith(".sqlite"):
                db_path_str = db_path_str.replace(".db", ".duckdb").replace(
                    ".sqlite", ".duckdb"
                )
            self.db_path = db_path_str
        except KeyError as e:
            raise ConfigurationError(
                "Missing configuration key",
                details="'database.path' not found in config.yaml",
            ) from e
        self._setup_directories()

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
        Get a database connection using context manager pattern.

        Yields:
            DuckDB connection that auto-closes on exit.
        """
        conn = duckdb.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_raw_connection(self) -> DuckDBPyConnection:
        """
        Get a raw database connection (caller manages lifecycle).

        Returns:
            DuckDB connection (must be closed by caller).
        """
        return duckdb.connect(self.db_path)

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

                columns = [
                    col[0]
                    for col in conn.execute(
                        f"PRAGMA table_info('{table_name}')"
                    ).fetchall()
                ]

                if "id" in columns and "id" in df.columns:
                    update_cols = [c for c in df.columns if c != "id"]
                    update_set = ", ".join(
                        [f"{col} = EXCLUDED.{col}" for col in update_cols]
                    )

                    conn.execute(
                        f"INSERT INTO {table_name} "  # nosec B608
                        f"SELECT * FROM df "
                        f"ON CONFLICT (id) DO UPDATE SET {update_set}"
                    )
                else:
                    conn.execute(
                        f"INSERT INTO {table_name} SELECT * FROM df"  # nosec B608
                    )

                conn.commit()

        except (duckdb.Error, Exception) as e:
            logger.error(f"Failed to load data into {table_name}: {e}")
            raise DatabaseError(f"Load failed for {table_name}", details=str(e)) from e
