import json
import logging

from .base import BaseCollector

logger = logging.getLogger(__name__)


class RevenueCollector(BaseCollector):
    def run(self, municipio_id, year):
        total = 0
        logger.info(">>> Starting Receitas")
        for batch, month_ref in self.fetch_by_month(municipio_id, year):
            saved = self.save(batch, municipio_id, year, month_ref)
            total += saved
            print(f"Receitas: accumulated {total} records...", end="\r")
        print(f"\nReceitas completed: {total} records.")
        return total

    def fetch_by_month(self, municipio_id, year):
        for month in range(1, 13):
            month_ref = f"{year}{month:02d}"
            params = {
                "codigo_municipio": municipio_id,
                "exercicio_orcamento": f"{year}00",
                "data_referencia": month_ref,
            }
            url = f"{self.client.SIM_BASE_URL}/balancete_receita_orcamentaria.json"

            logger.info(f"Fetching Receitas: {month_ref}")
            data = self.client.fetch_json(url, params)

            if data:
                content = None
                if "rsp" in data and "_content" in data["rsp"]:
                    content = data["rsp"]["_content"]
                else:
                    content = (
                        data.get("data")
                        or data.get("rows")
                        or data.get("balancete_receita_orcamentaria")
                    )

                if content:
                    if isinstance(content, list):
                        yield (content, month_ref)
                    elif isinstance(content, dict):
                        yield ([content], month_ref)

    def save(self, batch_data, municipio_id, year, month_ref):
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        count = 0
        for i, item in enumerate(batch_data):
            rec_code = item.get("codigo_receita", "0")
            val = item.get("valor_arrecadado_no_mes", "0")
            rec_id = f"{municipio_id}_{month_ref}_{rec_code}_{val}_{i}"

            cursor.execute(
                """
                INSERT OR REPLACE INTO receitas (
                    id, municipio_id, exercicio_orcamento, mes_referencia,
                    codigo_orgao, codigo_unidade_orcamentaria, codigo_receita,
                    descricao_receita, valor_orcado, valor_arrecadado, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    rec_id,
                    municipio_id,
                    str(year),
                    month_ref,
                    item.get("codigo_orgao"),
                    item.get("codigo_unidade_orcamentaria"),
                    item.get("codigo_receita"),
                    item.get("descricao_receita"),
                    item.get("valor_previsto_arrecadacao"),
                    item.get("valor_arrecadado_no_mes"),
                    json.dumps(item),
                ),
            )
            count += 1
        conn.commit()
        conn.close()
        return count
