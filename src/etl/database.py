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
                objeto_licitacao TEXT,
                modalidade_licitacao TEXT,
                data_realizacao_licitacao TEXT,
                valor_estimado REAL,
                situacao_licitacao TEXT,
                exercicio_orcamento TEXT,
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lic_municipio ON licitacoes(municipio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lic_objeto ON licitacoes(objeto_licitacao)")

        # Table: Despesas (Expenses)
        cursor.execute("""
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
                valor_empenhado REAL,
                valor_liquidado REAL,
                valor_pago REAL,
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_desp_municipio ON despesas(municipio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_desp_data ON despesas(mes_referencia)")

        # Table: Receitas (Revenue)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS receitas (
                id TEXT PRIMARY KEY,
                municipio_id TEXT,
                exercicio_orcamento TEXT,
                mes_referencia TEXT,
                codigo_orgao TEXT,
                codigo_unidade_orcamentaria TEXT,
                codigo_receita TEXT,
                descricao_receita TEXT,
                valor_orcado REAL,
                valor_arrecadado REAL,
                raw_data JSON,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rec_municipio ON receitas(municipio_id)")

        conn.commit()
        conn.close()
