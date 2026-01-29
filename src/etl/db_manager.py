"""
Database Manager.

Handles SQLite database connections, schema management, and queries.
"""

import logging
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from src.config import get_settings
from src.exceptions import ConfigurationError, DatabaseError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite database operations with connection pooling pattern.
    
    Provides methods for schema initialization, query execution,
    and schema introspection.
    """

    def __init__(self) -> None:
        """Initialize the database manager with configured path."""
        settings = get_settings()
        try:
            self.db_path = settings["database"]["path"]
        except KeyError as e:
            raise ConfigurationError(
                "Missing configuration key",
                details="'database.path' not found in config.yaml"
            ) from e
        self._setup_directories()

    def _setup_directories(self) -> None:
        """Create necessary directories for database and logs."""
        db_path = Path(self.db_path)
        if db_path.parent:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a database connection using context manager pattern.
        
        Yields:
            SQLite connection that auto-closes on exit.
        
        Example:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_raw_connection(self) -> sqlite3.Connection:
        """
        Get a raw database connection (caller manages lifecycle).
        
        Returns:
            SQLite connection (must be closed by caller).
        """
        return sqlite3.connect(self.db_path)

    def initialize_schema(self) -> None:
        """Initialize all database tables and indexes."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Table: Licitações (Tenders)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS licitacoes (
                    id TEXT PRIMARY KEY,
                    municipio_id TEXT,
                    numero_licitacao TEXT,
                    numero_processo TEXT,
                    objeto_licitacao TEXT, -- Description of object
                    modalidade_licitacao TEXT, -- procurement_type
                    data_realizacao_licitacao TEXT, -- date_of_tender (ISO8601)
                    valor_estimado REAL, -- estimated_value
                    situacao_licitacao TEXT, -- status
                    exercicio_orcamento TEXT, -- fiscal_year (YYYY)
                    raw_data JSON,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                /* Metadata: Tenders and Contracts table (licitacao). */
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_municipio "
                "ON licitacoes(municipio_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_objeto "
                "ON licitacoes(objeto_licitacao)"
            )
            # Additional indexes for frequently filtered columns
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_modalidade "
                "ON licitacoes(modalidade_licitacao)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_situacao "
                "ON licitacoes(situacao_licitacao)"
            )
            # Composite index for multi-column queries
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_lic_mun_exerc "
                "ON licitacoes(municipio_id, exercicio_orcamento)"
            )

            # Table: Despesas (Expenses)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS despesas (
                    id TEXT PRIMARY KEY,
                    municipio_id TEXT,
                    exercicio_orcamento TEXT, -- fiscal_year
                    mes_referencia TEXT, -- reference_month (YYYYMM or MM)
                    codigo_orgao TEXT, -- org_code
                    codigo_unidade_orcamentaria TEXT, -- budget_unit_code
                    codigo_funcao TEXT, -- Functional classification
                    -- MAPPING:
                    -- 01: Legislativa
                    -- 04: Administração
                    -- 06: Segurança Pública
                    -- 08: Assistência Social
                    -- 10: Saúde
                    -- 12: Educação
                    -- 13: Cultura
                    -- 15: Urbanismo
                    -- 18: Gestão Ambiental
                    -- 26: Transporte
                    -- 27: Desporto e Lazer
                    -- 28: Encargos Especiais
                    codigo_subfuncao TEXT, -- Subfunction
                    codigo_programa TEXT, -- program_code
                    codigo_elemento_despesa TEXT, -- expense_element_code
                    valor_empenhado REAL, -- committed_value
                    valor_liquidado REAL, -- verified_value
                    valor_pago REAL, -- paid_value
                    raw_data JSON,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                /* Metadata: Public Expenses and Spending table. */
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_desp_municipio "
                "ON despesas(municipio_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_desp_data "
                "ON despesas(mes_referencia)"
            )
            # Additional indexes for frequently filtered columns
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_desp_funcao "
                "ON despesas(codigo_funcao)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_desp_exercicio "
                "ON despesas(exercicio_orcamento)"
            )
            # Composite index for multi-column queries
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_desp_mun_exerc "
                "ON despesas(municipio_id, exercicio_orcamento)"
            )

            # Table: Receitas (Revenue)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS receitas (
                    id TEXT PRIMARY KEY,
                    municipio_id TEXT,
                    exercicio_orcamento TEXT, -- fiscal_year
                    mes_referencia TEXT, -- reference_month
                    codigo_orgao TEXT,
                    codigo_unidade_orcamentaria TEXT,
                    codigo_receita TEXT, -- revenue_code
                    descricao_receita TEXT, -- Revenue source
                    valor_orcado REAL, -- budgeted_value
                    valor_arrecadado REAL, -- collected_value
                    raw_data JSON,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                /* Metadata: Revenue and Collection table (receita). */
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_municipio "
                "ON receitas(municipio_id)"
            )
            # dditional indexes for frequently filtered columns
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_exercicio "
                "ON receitas(exercicio_orcamento)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_mes "
                "ON receitas(mes_referencia)"
            )
            # Composite index for multi-column queries
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_rec_mun_exerc "
                "ON receitas(municipio_id, exercicio_orcamento)"
            )

            # Table: Metadata (Idempotency)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS etl_metadata (
                    municipio_id TEXT,
                    year INTEGER,
                    source TEXT,
                    status TEXT, -- 'STARTED', 'COMPLETED', 'FAILED'
                    record_count INTEGER,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (municipio_id, year, source)
                )
            """)

            conn.commit()

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
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise DatabaseError("Query execution failed", details=str(e)) from e

    def get_all_tables(self) -> list[str]:
        """
        Get list of all table names in the database.
        
        Returns:
            List of table names.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            return [row[0] for row in cursor.fetchall()]

    def get_start_schema(
        self, limit_tables: Optional[list[str]] = None
    ) -> dict[str, str]:
        """
        Get schema definitions for tables.
        
        Args:
            limit_tables: Optional list of specific tables to fetch.
        
        Returns:
            Dictionary mapping table names to DDL statements.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT name, sql FROM sqlite_master WHERE type='table'"
            params: list[str] = []
            
            if limit_tables:
                placeholders = ",".join("?" * len(limit_tables))
                query += f" AND name IN ({placeholders})"
                params = limit_tables

            cursor.execute(query, params)
            return {row[0]: row[1] for row in cursor.fetchall()}

    def search_schema(self, keyword: str) -> dict[str, str]:
        """
        Search table names and schema definitions for a keyword.
        
        Args:
            keyword: Keyword to search for (accent-insensitive).
        
        Returns:
            Dictionary of matching tables and their DDL.
        """
        def normalize_text(text: str) -> str:
            if not text:
                return ""
            return "".join(
                c for c in unicodedata.normalize("NFD", text)
                if unicodedata.category(c) != "Mn"
            ).lower()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
            all_tables = cursor.fetchall()

        results: dict[str, str] = {}
        keyword_norm = normalize_text(keyword)

        for name, sql in all_tables:
            name_norm = normalize_text(name)
            sql_norm = normalize_text(sql) if sql else ""
            
            if keyword_norm in name_norm or keyword_norm in sql_norm:
                results[name] = sql
                
        return results
