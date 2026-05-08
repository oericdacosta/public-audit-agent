"""
Extra-Budgetary Collectors.

Collectors for extra-budgetary expense and revenue data from the TCE API.
Uses MonthlyCollector base class for shared monthly iteration logic.
"""

import asyncio
import hashlib
import json
import logging

from src.etl.endpoints import Endpoint

from .base import MonthlyCollector

logger = logging.getLogger(__name__)


class DespesaExtraOrcamentariaCollector(MonthlyCollector):
    """Collector for Extra-Budgetary Expenses (Despesa Extra-Orçamentária).

    Note: This endpoint does NOT support quantidade/deslocamento pagination.
    """

    collector_name = "Despesa Extra"

    async def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict]:
        """Fetch data for a single month (no pagination - API doesn't support it)."""
        month_ref = f"{year}{month:02d}"
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
        }

        url = self.client.build_url(Endpoint.BALANCETE_DESPESA_EXTRA)
        data = await self.client.fetch_json(url, params)
        if not data:
            return []

        return self._extract_records(data)

    def _extract_records(self, data: dict) -> list[dict]:
        """Extract records from API response."""
        records: list = []

        if "rsp" in data and isinstance(data["rsp"], dict):
            content = data["rsp"].get("_content", [])
            if isinstance(content, list):
                records = content
            elif isinstance(content, dict):
                records = [content]
        elif "balancete_despesa_extra_orcamentaria" in data:
            records = data["balancete_despesa_extra_orcamentaria"]
        elif "data" in data:
            records = data["data"]

        if isinstance(records, dict):
            return [records]
        return records if isinstance(records, list) else []

    async def _save_all(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> int:
        """Save to 'balancete_despesa_extra' table."""
        if not all_records:
            return 0

        # Run CPU-bound processing in thread
        records = await asyncio.to_thread(
            self._process_records_sync, all_records, municipio_id, year
        )

        columns = [
            "id",
            "municipio_id",
            "exercicio_orcamento",
            "mes_referencia",
            "raw_data",
        ]

        return await self.bulk_upsert(
            "balancete_despesa_extra", columns, records, ["raw_data"]
        )

    def _process_records_sync(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> list[tuple]:
        """Sync helper to process records."""
        records = []
        for item in all_records:
            month_ref = item.get("data_referencia", f"{year}00")
            serialized = json.dumps(item, sort_keys=True, default=str)
            content_hash = hashlib.sha256(serialized.encode()).hexdigest()
            rec_id = f"{municipio_id}_{content_hash}_{year}"

            records.append(
                (
                    rec_id,
                    municipio_id,
                    str(year),
                    month_ref,
                    json.dumps(item),
                )
            )
        return records
