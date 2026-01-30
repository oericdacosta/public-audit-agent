"""
Revenue (Receitas) Collector.

Collects public revenue data from the TCE API.
"""

import json
import logging
from typing import Any, Iterator

from src.etl.endpoints import Endpoint

from .base import BaseCollector

logger = logging.getLogger(__name__)


class RevenueCollector(BaseCollector):
    """Collector for public revenue (receita) data."""

    def run(self, municipio_id: str, year: int) -> int:
        """
        Run the revenue collection for a municipality and year.

        Returns:
            Total number of records collected.
        """
        total = 0
        logger.info(">>> Starting Receitas")

        for batch, month_ref in self.fetch_by_month(municipio_id, year):
            saved = self.save(batch, municipio_id, year, month_ref)
            total += saved

        logger.info("Receitas completed: %d records.", total)
        return total

    def fetch_by_month(
        self, municipio_id: str, year: int
    ) -> Iterator[tuple[list[dict[str, Any]], str]]:
        """
        Fetch revenue data month by month.

        Yields:
            Tuples of (batch_data, month_reference).
        """
        for month in range(1, 13):
            month_ref = f"{year}{month:02d}"
            params = {
                "codigo_municipio": municipio_id,
                "exercicio_orcamento": f"{year}00",
                "data_referencia": month_ref,
            }
            url = self.client.build_url(Endpoint.RECEITAS)

            logger.info("Fetching Receitas: %s", month_ref)
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

    def save(
        self,
        batch_data: list[dict[str, Any]],
        municipio_id: str,
        year: int,
        month_ref: str,
    ) -> int:
        """
        Save revenue records to the database using bulk insert.

        Returns:
            Number of records saved.
        """
        if not batch_data:
            return 0

        # Transform records for bulk insert
        records = []
        for i, item in enumerate(batch_data):
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

        return self.bulk_insert("receitas", columns, records)
