import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path="data/civic_audit.db"):
        self.db_path = db_path
        self._setup_directories()

    def _setup_directories(self):
        Path("data").mkdir(parents=True, exist_ok=True)
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
                objeto_licitacao TEXT, -- Description of object (e.g., School Lunch/Merenda, Renovation/Reforma)
                modalidade_licitacao TEXT, -- procurement_type (e.g., Pregão, Concorrência)
                data_realizacao_licitacao TEXT, -- date_of_tender (ISO8601 YYYY-MM-DD)
                valor_estimado REAL, -- estimated_value (The max value the gov expects to pay)
                situacao_licitacao TEXT, -- status (e.g., Concluída, Deserta, Fracassada)
                exercicio_orcamento TEXT, -- fiscal_year (YYYY)
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            /* Metadata: Tenders and Contracts table (licitacao). Search here for purchases, works, and services. */
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lic_municipio ON licitacoes(municipio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lic_objeto ON licitacoes(objeto_licitacao)")

        # Table: Despesas (Expenses)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS despesas (
                id TEXT PRIMARY KEY,
                municipio_id TEXT,
                exercicio_orcamento TEXT, -- fiscal_year
                mes_referencia TEXT, -- reference_month (YYYYMM or MM)
                codigo_orgao TEXT, -- org_code
                codigo_unidade_orcamentaria TEXT, -- budget_unit_code
                codigo_funcao TEXT, -- Functional classification (e.g., 12=Education/educacao, 10=Health/saude)
                codigo_subfuncao TEXT, -- Subfunction (more specific area)
                codigo_programa TEXT, -- program_code
                codigo_elemento_despesa TEXT, -- expense_element_code (nature of expense)
                valor_empenhado REAL, -- committed_value (Funds reserved/promised)
                valor_liquidado REAL, -- verified_value (Service/Product delivered and verified)
                valor_pago REAL, -- paid_value (Actual money transfer to supplier)
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            /* Metadata: Public Expenses and Spending table. Contains data for Education (educacao), Health (saude), Infrastructure, etc. */
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_desp_municipio ON despesas(municipio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_desp_data ON despesas(mes_referencia)")

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
                descricao_receita TEXT, -- Revenue source (e.g., Taxes/IPTU, FPM, Royalties)
                valor_orcado REAL, -- budgeted_value (Expected revenue)
                valor_arrecadado REAL, -- collected_value (Actual revenue received)
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            /* Metadata: Revenue and Collection table (receita). */
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rec_municipio ON receitas(municipio_id)")

        conn.commit()
        conn.close()
