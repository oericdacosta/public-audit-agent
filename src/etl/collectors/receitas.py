"""
Revenue (Receitas) Collector - Optimized.

Collects public revenue data from the TCE API with parallel fetching.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.etl.endpoints import Endpoint

from .base import BaseCollector

logger = logging.getLogger(__name__)


class RevenueCollector(BaseCollector):
    """Collector for public revenue (receita) data with parallel fetching."""

    def run(self, municipio_id: str, year: int) -> int:
        """
        Run the revenue collection for a municipality and year.

        Returns:
            Total number of records collected.
        """
        logger.info(">>> Starting Receitas - Parallel Mode")

        # Fetch all 12 months in parallel
        all_records = self._fetch_all_months_parallel(municipio_id, year)

        if not all_records:
            logger.info("Receitas: No records found.")
            return 0

        # Bulk save all records at once
        total = self._save_all(all_records, municipio_id, year)
        logger.info("Receitas completed: %d records.", total)
        return total

    def _fetch_all_months_parallel(
        self, municipio_id: str, year: int
    ) -> list[dict[str, Any]]:
        """
        Fetch all 12 months in parallel.

        Returns:
            Flattened list of all revenue records.
        """
        all_records: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {
                executor.submit(self._fetch_month, municipio_id, year, month): month
                for month in range(1, 13)
            }

            for future in as_completed(futures):
                month = futures[future]
                try:
                    month_records = future.result()
                    if month_records:
                        all_records.extend(month_records)
                        logger.info(
                            "Receitas month %02d: %d records", month, len(month_records)
                        )
                except Exception as e:
                    logger.error("Failed to fetch Receitas month %d: %s", month, e)

        return all_records

    def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict[str, Any]]:
        """Fetch revenue data for a single month."""
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

    def _save_all(
        self,
        all_records: list[dict[str, Any]],
        municipio_id: str,
        year: int,
    ) -> int:
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
