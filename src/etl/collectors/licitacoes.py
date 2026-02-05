"""
Tenders (Licitações) Collector - Optimized.

Collects public tender/procurement data from the TCE API with parallel fetching.
"""

import calendar
import json
import logging
from typing import Any, cast

from src.etl.endpoints import Endpoint

from .base import BaseCollector

logger = logging.getLogger(__name__)


class TendersCollector(BaseCollector):
    """Collector for public tender (licitação) data with parallel fetching."""

    def run(self, municipio_id: str, year: int) -> int:
        """
        Run the tender collection for a municipality and year.

        Returns:
            Total number of records collected.
        """
        logger.info(">>> Starting Licitações - Sequential Mode")

        # Fetch all 12 months sequentially for stability
        all_records = self._fetch_all_months_sequential(municipio_id, year)

        if not all_records:
            logger.info("Licitações: No records found.")
            return 0

        # Bulk save all records at once
        total = self._save_all(all_records, municipio_id, year)
        logger.info("Licitações completed: %d records.", total)
        return total

    def _fetch_all_months_sequential(
        self, municipio_id: str, year: int
    ) -> list[dict[str, Any]]:
        """
        Fetch all 12 months sequentially for API stability.

        Returns:
            Flattened list of all tender records.
        """
        all_records: list[dict[str, Any]] = []

        for month in range(1, 13):
            try:
                month_records = self._fetch_month(municipio_id, year, month)
                if month_records:
                    all_records.extend(month_records)
                    logger.info(
                        "Licitações month %02d: %d records",
                        month,
                        len(month_records),
                    )
            except Exception as e:
                logger.error("Failed to fetch Licitações month %d: %s", month, e)

        return all_records

    def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict[str, Any]]:
        """Fetch tender data for a single month."""
        last_day = calendar.monthrange(int(year), month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
        date_range = f"{start_date}_{end_date}"

        params = {
            "codigo_municipio": municipio_id,
            "data_realizacao_autuacao_licitacao": date_range,
        }
        url = self.client.build_url(Endpoint.LICITACOES)

        data = self.client.fetch_json(url, params)
        if not data:
            return []

        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return cast(list[dict[str, Any]], data.get("data", []))

        return []

    def _save_all(
        self, all_records: list[dict[str, Any]], municipio_id: str, year: int
    ) -> int:
        """Save all records to database in one bulk insert."""
        if not all_records:
            return 0

        records = []
        for item in all_records:
            lic_id = f"{municipio_id}_{item.get('numero_licitacao', 'unknown')}_{year}"
            records.append(
                (
                    lic_id,
                    municipio_id,
                    item.get("numero_licitacao"),
                    item.get("numero_processo_licitatorio"),
                    item.get("objeto_licitacao"),
                    item.get("modalidade_licitacao"),
                    item.get("data_realizacao_licitacao"),
                    item.get("valor_licitacao"),
                    item.get("situacao_licitacao"),
                    str(year),
                    json.dumps(item),
                )
            )

        columns = [
            "id",
            "municipio_id",
            "numero_licitacao",
            "numero_processo",
            "objeto_licitacao",
            "modalidade_licitacao",
            "data_realizacao_licitacao",
            "valor_estimado",
            "situacao_licitacao",
            "exercicio_orcamento",
            "raw_data",
        ]

        update_columns = [
            "objeto_licitacao",
            "valor_estimado",
            "situacao_licitacao",
            "raw_data",
        ]

        return self.bulk_upsert("licitacoes", columns, records, update_columns)
