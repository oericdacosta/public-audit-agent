"""
Revenue (Receitas) Collector.

Collects public revenue data from the TCE API with parallel fetching.
Uses MonthlyCollector base class for shared monthly iteration logic.
"""

import json
import logging

from src.etl.endpoints import Endpoint

from .base import MonthlyCollector

logger = logging.getLogger(__name__)


class RevenueCollector(MonthlyCollector):
    """Collector for public revenue (receita) data with parallel fetching."""

    collector_name = "Receitas"

    def _fetch_month(self, municipio_id: str, year: int, month: int) -> list[dict]:
        """Fetch revenue data for a single month (no pagination)."""
        month_ref = f"{year}{month:02d}"
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
        }
        url = self.client.build_url(Endpoint.RECEITAS)

        data = self.client.fetch_json(url, params)
        if not data:
            return []

        return self._extract_records(data)

    def _extract_records(self, data: dict) -> list[dict]:
        """Extract records from API response."""
        content = None

        if "rsp" in data and "_content" in data["rsp"]:
            content = data["rsp"]["_content"]
        elif "data" in data:
            content = data["data"]
        elif "balancete_receita_orcamentaria" in data:
            content = data["balancete_receita_orcamentaria"]

        if content:
            if isinstance(content, list):
                return content
            elif isinstance(content, dict):
                return [content]

        return []

    def _save_all(self, all_records: list[dict], municipio_id: str, year: int) -> int:
        """Save all records to database in one bulk insert."""
        if not all_records:
            return 0

        records = []
        for i, item in enumerate(all_records):
            month_ref = item.get("data_referencia", f"{year}00")
            rec_code = item.get("codigo_receita", "0")
            val = item.get("valor_arrecadado_no_mes", "0")
            rec_id = f"{municipio_id}_{month_ref}_{rec_code}_{val}_{i}"

            records.append(
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
                )
            )

        columns = [
            "id",
            "municipio_id",
            "exercicio_orcamento",
            "mes_referencia",
            "codigo_orgao",
            "codigo_unidade_orcamentaria",
            "codigo_receita",
            "descricao_receita",
            "valor_orcado",
            "valor_arrecadado",
            "raw_data",
        ]

        update_columns = ["valor_orcado", "valor_arrecadado", "raw_data"]

        return self.bulk_upsert("receitas", columns, records, update_columns)
