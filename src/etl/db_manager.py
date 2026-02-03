"""
Database Manager.

Handles DuckDB database connections, schema management, and queries.
"""

import logging
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

import duckdb
from duckdb import DuckDBPyConnection

from src.config import get_settings
from src.exceptions import ConfigurationError, DatabaseError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages DuckDB database operations.

    Provides methods for schema initialization, query execution,
    and schema introspection.
    """

    def __init__(self) -> None:
        """Initialize the database manager with configured path."""
        settings = get_settings()
        try:
            # Fallback to .duckdb extension if still pointing to .db
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
        """Video game validation for table names to prevent SQL injection."""
        if not table_name.isidentifier():
            raise ValueError(f"Invalid table name: {table_name}")

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
        """Initialize all database tables and indexes."""
        with self.get_connection() as conn:
            # Enable JSON extension if not already enabled (usually built-in)
            # conn.execute("INSTALL json; LOAD json;")

            # Table: Licitações (Tenders)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS licitacoes (
                    id TEXT PRIMARY KEY,
                    municipio_id TEXT,
                    numero_licitacao TEXT,
                    numero_processo TEXT,
                    objeto_licitacao TEXT,
                    modalidade_licitacao TEXT,
                    data_realizacao_licitacao TEXT,
                    valor_estimado DOUBLE,
                    situacao_licitacao TEXT,
                    exercicio_orcamento TEXT,
                    raw_data JSON,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_municipio "
                "ON licitacoes(municipio_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_objeto "
                "ON licitacoes(objeto_licitacao)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_mun_exerc "
                "ON licitacoes(municipio_id, exercicio_orcamento)"
            )

            # Table: Despesas (Expenses)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS despesas (
                    id TEXT PRIMARY KEY,
                    municipio_id TEXT,
                    exercicio_orcamento TEXT,
                    mes_referencia TEXT,
                    codigo_orgao TEXT,
                    codigo_unidade_orcamentaria TEXT,
                    codigo_funcao TEXT,
                    codigo_subfuncao TEXT,
                    codigo_programa TEXT,
                    codigo_elemento_despesa TEXT,
                    valor_empenhado DOUBLE,
                    valor_liquidado DOUBLE,
                    valor_pago DOUBLE,
                    raw_data JSON,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_desp_municipio "
                "ON despesas(municipio_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_desp_mun_exerc "
                "ON despesas(municipio_id, exercicio_orcamento)"
            )

            # Table: Receitas (Revenue)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS receitas (
                    id TEXT PRIMARY KEY,
                    municipio_id TEXT,
                    exercicio_orcamento TEXT,
                    mes_referencia TEXT,
                    codigo_orgao TEXT,
                    codigo_unidade_orcamentaria TEXT,
                    codigo_receita TEXT,
                    descricao_receita TEXT,
                    valor_orcado DOUBLE,
                    valor_arrecadado DOUBLE,
                    raw_data JSON,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_municipio ON receitas(municipio_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_mun_exerc "
                "ON receitas(municipio_id, exercicio_orcamento)"
            )

            # Table: Metadata
            conn.execute("""
                CREATE TABLE IF NOT EXISTS etl_metadata (
                    municipio_id TEXT,
                    year INTEGER,
                    source TEXT,
                    status TEXT,
                    record_count INTEGER,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (municipio_id, year, source)
                )
            """)

            # Implicitly committed. Explicit commit is no-op in AutoCommit mode
            # but good practice if disabling autocommit.
            # conn.commit()

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

                # Use .df() to leverage Pandas for easy dict conversion
                df = conn.execute(query).df()
                return cast(list[dict[str, Any]], df.to_dict(orient="records"))
        except (duckdb.Error, Exception) as e:
            raise DatabaseError("Query execution failed", details=str(e)) from e

    def get_all_tables(self) -> list[str]:
        """
        Get list of all table names in the database.

        Returns:
            List of table names.
        """
        with self.get_connection() as conn:
            # DuckDB-specific system query
            rows = conn.execute("SHOW TABLES").fetchall()
            return [row[0] for row in rows]

    def get_start_schema(
        self, limit_tables: Optional[list[str]] = None
    ) -> dict[str, str]:
        """
        Get schema definitions for tables.
        For DuckDB, we reconstruct a CREATE TABLE statement from DESCRIBE.
        """
        with self.get_connection() as conn:
            tables = self.get_all_tables()
            if limit_tables:
                tables = [t for t in tables if t in limit_tables]

            schemas = {}
            for table in tables:
                # Reconstruct simplified DDL
                columns = conn.execute(f"DESCRIBE {table}").fetchall()
                # columns row: column_name, column_type, null, key, default, extra
                cols_ddl = []
                for col in columns:
                    name = col[0]
                    dtype = col[1]
                    is_null = col[2]
                    key = col[3]
                    # default = col[4]

                    part = f"{name} {dtype}"
                    if key == "PRI":
                        part += " PRIMARY KEY"
                    elif is_null == "NO":
                        part += " NOT NULL"
                    cols_ddl.append(part)

                ddl = (
                    f"CREATE TABLE {table} (\n    " + ",\n    ".join(cols_ddl) + "\n);"
                )
                schemas[table] = ddl
            return schemas

    def search_schema(self, keyword: str) -> dict[str, str]:
        """
        Search table names and schema definitions for a keyword.
        """

        def normalize_text(text: str) -> str:
            if not text:
                return ""
            return "".join(
                c
                for c in unicodedata.normalize("NFD", text)
                if unicodedata.category(c) != "Mn"
            ).lower()

        schemas = self.get_start_schema()
        results: dict[str, str] = {}
        keyword_norm = normalize_text(keyword)

        for name, sql in schemas.items():
            name_norm = normalize_text(name)
            sql_norm = normalize_text(sql)

            if keyword_norm in name_norm or keyword_norm in sql_norm:
                results[name] = sql

        return results

    def load_data(
        self, table_name: str, data: dict[str, Any] | list[dict[str, Any]]
    ) -> None:
        """
        Load JSON data into a table, creating it if it doesn't exist.

        Args:
            table_name: Target table name.
            data: List of dicts or single dict to insert.
        """
        if not data:
            return

        # Ensure data is a list
        if isinstance(data, dict):
            # If the API returns a single object wrapper (e.g. {"data": [...]})
            # we might need adjustment, but assuming list of rows for now
            # or wrapping single object in list.
            data = [data]

        # We use a temporary file or memory to load into DuckDB
        # A simple way is to register the list of dicts as a virtual table in Python
        # DuckDB Python client handles list of dicts automatically in insert/create

        try:
            with self.get_connection() as conn:
                # Validate input to prevent SQL injection
                self._validate_table_name(table_name)

                # 1. Create Table if not exists (Schema Inference)
                # We create a temporary view from the data first to infer types
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {table_name} "  # nosec B608
                    "AS SELECT * FROM data LIMIT 0"
                )

                # 2. Insert Data
                # Note: 'data' variable is auto-magically recognized by DuckDB
                # python client
                conn.execute(f"INSERT INTO {table_name} SELECT * FROM data")  # nosec B608

        except (duckdb.Error, Exception) as e:
            logger.error(f"Failed to load data into {table_name}: {e}")
            raise DatabaseError(f"Load failed for {table_name}", details=str(e)) from e
