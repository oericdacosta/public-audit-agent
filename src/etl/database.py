import logging
import sqlite3
from pathlib import Path

from src.config import get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        settings = get_settings()
        try:
            self.db_path = settings["database"]["path"]
        except KeyError as e:
            raise ValueError("Missing 'database.path' in config.yaml") from e
        self._setup_directories()

    def _setup_directories(self):
        import os

        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(parents=True, exist_ok=True)

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def initialize_schema(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        # Table: Licitações (Tenders)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS licitacoes (
                id TEXT PRIMARY KEY,
                municipio_id TEXT,
                numero_licitacao TEXT,
                numero_processo TEXT,
                objeto_licitacao TEXT, -- Description of object
                -- (e.g., School Lunch/Merenda, Renovation/Reforma)
                modalidade_licitacao TEXT, -- procurement_type
                -- (e.g., Pregão, Concorrência)
                data_realizacao_licitacao TEXT, -- date_of_tender (ISO8601 YYYY-MM-DD)
                valor_estimado REAL, -- estimated_value
                -- (The max value the gov expects to pay)
                situacao_licitacao TEXT, -- status
                -- (e.g., Concluída, Deserta, Fracassada)
                exercicio_orcamento TEXT, -- fiscal_year (YYYY)
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            /* Metadata: Tenders and Contracts table (licitacao).
               Search here for purchases, works, and services. */
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_lic_municipio ON licitacoes(municipio_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_lic_objeto ON licitacoes(objeto_licitacao)"
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
                codigo_subfuncao TEXT, -- Subfunction (more specific area)
                codigo_programa TEXT, -- program_code
                codigo_elemento_despesa TEXT, -- expense_element_code
                -- (nature of expense)
                valor_empenhado REAL, -- committed_value (Funds reserved/promised)
                valor_liquidado REAL, -- verified_value
                -- (Service/Product delivered and verified)
                valor_pago REAL, -- paid_value (Actual money transfer to supplier)
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            /* Metadata: Public Expenses and Spending table.
               Contains data for Education (educacao), Health (saude),
               Infrastructure, etc. */
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_desp_municipio ON despesas(municipio_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_desp_data ON despesas(mes_referencia)"
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
                -- (e.g., Taxes/IPTU, FPM, Royalties)
                valor_orcado REAL, -- budgeted_value (Expected revenue)
                valor_arrecadado REAL, -- collected_value (Actual revenue received)
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            /* Metadata: Revenue and Collection table (receita). */
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rec_municipio ON receitas(municipio_id)")

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
        conn.close()

    def execute_query(self, query: str) -> list[dict]:
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            # return as list of dicts
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            raise
        finally:
            conn.close()

    def get_all_tables(self) -> list[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables

    def get_start_schema(self, limit_tables: list[str] = None) -> dict[str, str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        query = "SELECT name, sql FROM sqlite_master WHERE type='table'"
        params = []
        if limit_tables:
            query += " AND name IN ({})".format(",".join("?" * len(limit_tables)))
            params = limit_tables

        cursor.execute(query, params)
        schema = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return schema

    def search_schema(self, keyword: str) -> dict[str, str]:
        import unicodedata

        def normalize_text(text: str) -> str:
            if not text:
                return ""
            return "".join(
                c for c in unicodedata.normalize("NFD", text)
                if unicodedata.category(c) != "Mn"
            ).lower()

        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Fetch ALL tables and definitions
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
        all_tables = cursor.fetchall()
        conn.close()

        results = {}
        keyword_norm = normalize_text(keyword)

        for name, sql in all_tables:
            name_norm = normalize_text(name)
            sql_norm = normalize_text(sql)
            
            if (keyword_norm in name_norm) or (keyword_norm in sql_norm):
                results[name] = sql
                
        return results
