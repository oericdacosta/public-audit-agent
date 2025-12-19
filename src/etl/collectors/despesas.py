import json
import logging
from .base import BaseCollector

logger = logging.getLogger(__name__)

class ExpensesCollector(BaseCollector):
    def run(self, municipio_id, year):
        total = 0
        logger.info(">>> Starting Despesas (Financial)")
        for batch, month_ref in self.fetch_by_month(municipio_id, year):
            saved = self.save(batch, municipio_id, year, month_ref)
            total += saved
            print(f"Despesas: accumulated {total} records...", end='\r')
        print(f"\nDespesas completed: {total} records.")
        return total

    def fetch_by_month(self, municipio_id, year):
        for month in range(1, 13):
            month_ref = f"{year}{month:02d}"
            params = {
                "codigo_municipio": municipio_id,
                "exercicio_orcamento": f"{year}00",
                "data_referencia": month_ref
            }
            url = f"{self.client.SIM_BASE_URL}/balancete_despesa_orcamentaria.json"
            
            logger.info(f"Fetching Despesas: {month_ref}")
            data = self.client.fetch_json(url, params)
            
            if data:
                content = None
                if 'rsp' in data and '_content' in data['rsp']:
                     content = data['rsp']['_content']
                else:
                     content = data.get('data') or data.get('rows') or data.get('balancete_despesa_orcamentaria')
                
                if content:
                    if isinstance(content, list): yield (content, month_ref)
                    elif isinstance(content, dict): yield ([content], month_ref)

    def save(self, batch_data, municipio_id, year, month_ref):
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        count = 0
        for i, item in enumerate(batch_data):
            elem = item.get('codigo_elemento_despesa', '0')
            val = item.get('valor_pago_no_mes', '0')
            exp_id = f"{municipio_id}_{month_ref}_{elem}_{val}_{i}"
            
            cursor.execute("""
                INSERT OR REPLACE INTO despesas (
                    id, municipio_id, exercicio_orcamento, mes_referencia,
                    codigo_orgao, codigo_unidade_orcamentaria, codigo_funcao,
                    codigo_subfuncao, codigo_programa, codigo_elemento_despesa,
                    valor_empenhado, valor_liquidado, valor_pago, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exp_id, municipio_id, str(year), month_ref,
                item.get('codigo_orgao'), item.get('codigo_unidade_orcamentaria'),
                item.get('codigo_funcao'), item.get('codigo_subfuncao'),
                item.get('codigo_programa'), item.get('codigo_elemento_despesa'),
                item.get('valor_empenhado_no_mes'), item.get('valor_liquidado_no_mes'),
                item.get('valor_pago_no_mes'), json.dumps(item)
            ))
            count += 1
        conn.commit()
        conn.close()
        return count
