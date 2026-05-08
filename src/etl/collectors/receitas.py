"""
Revenue (Receitas) Collector.

Collects public revenue data from the TCE API with parallel fetching.
Uses MonthlyCollector base class for shared monthly iteration logic.
Note: This endpoint does NOT support quantidade/deslocamento pagination.
"""

import asyncio
import hashlib
import json
import logging

from src.etl.endpoints import Endpoint

from .base import MonthlyCollector

logger = logging.getLogger(__name__)


class RevenueCollector(MonthlyCollector):
    """Collector for public revenue (receita) data with parallel fetching."""

    collector_name = "Receitas"

    async def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict]:
        """Fetch revenue data for a single month (no pagination)."""
        month_ref = f"{year}{month:02d}"
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
        }
        url = self.client.build_url(Endpoint.RECEITAS)

        data = await self.client.fetch_json(url, params)
        if not data:
            return []

        return self._extract_records(data)

    def _extract_records(self, data: dict) -> list[dict]:
        """Extract records from API response."""
        content = None

        if "rsp" in data and isinstance(data["rsp"], dict):
            content = data["rsp"].get("_content")
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

    async def _save_all(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> int:
        """Save all records to database in one bulk insert."""
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
            "codigo_orgao",
            "codigo_unidade_orcamentaria",
            "codigo_receita",
            "descricao_receita",
            "valor_orcado",
            "valor_arrecadado",
            "raw_data",
        ]

        update_columns = ["valor_orcado", "valor_arrecadado", "raw_data"]

        # Run Blocking DB write (bulk_upsert handles to_thread internally)
        return await self.bulk_upsert("receitas", columns, records, update_columns)

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
                    item.get("codigo_orgao"),
                    item.get("codigo_unidade"),
                    item.get("codigo_rubrica"),
                    item.get("descricao_receita"),
                    item.get("valor_previsto_orcamento"),
                    item.get("valor_arrecadacao_ate_mes"),
                    json.dumps(item),
                )
            )
        return records
