"""
Extra-Budgetary Collectors.

Collectors for extra-budgetary expense and revenue data from the TCE API.
Uses MonthlyCollector base class for shared monthly iteration logic.
"""

import asyncio
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
            # Use content hash for robustness
            import hashlib

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


class ReceitaExtraOrcamentariaCollector(MonthlyCollector):
    """Collector for Extra-Budgetary Revenues with Pagination."""

    collector_name = "Receita Extra"

    async def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict]:
        """Fetch data for a single month with pagination."""
        month_ref = f"{year}{month:02d}"
        url = self.client.build_url(Endpoint.BALANCETE_RECEITA_EXTRA)
        page_size = 500

        # Initial fetch
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
            "quantidade": str(page_size),
            "deslocamento": "0",
        }

        first_response = await self.client.fetch_json(url, params)
        if not first_response:
            return []

        records, total = self._extract_records_and_total(first_response)
        if not records:
            return []

        # If total unknown, estimate from first page
        if not total:
            total = len(records)
        logger.debug("Receita Extra Month %s: Found %d total records", month_ref, total)

        if total <= page_size and len(records) < page_size:
            return records

        # Fetch remaining pages in parallel
        return await self._fetch_remaining_pages(
            url, municipio_id, year, month_ref, records, total, page_size
        )

    async def _fetch_remaining_pages(
        self,
        url: str,
        municipio_id: str,
        year: int,
        month_ref: str,
        first_page: list[dict],
        total: int,
        page_size: int = 500,
    ) -> list[dict]:
        """Fetch all remaining pages after the first one."""
        all_records = list(first_page)
        offsets = list(range(page_size, total, page_size))

        tasks = [
            self._fetch_page(url, municipio_id, year, month_ref, offset)
            for offset in offsets
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for offset, result in zip(offsets, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("API error at offset %d: %s", offset, result)
            elif isinstance(result, list):
                all_records.extend(result)

        return all_records

    async def _fetch_page(
        self,
        url: str,
        municipio_id: str,
        year: int,
        month_ref: str,
        offset: int,
        page_size: int = 500,
    ) -> list[dict]:
        """Fetch a single page of data."""
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
            "quantidade": str(page_size),
            "deslocamento": str(offset),
        }
        response = await self.client.fetch_json(url, params)
        if response:
            records, _ = self._extract_records_and_total(response)
            return records
        return []

    def _extract_records_and_total(self, data: dict) -> tuple[list[dict], int]:
        """Extract records list and total count from API response."""
        total = 0
        records: list = []

        if "rsp" in data and isinstance(data["rsp"], dict):
            rsp = data["rsp"]
            total = int(rsp.get("_total", 0))
            content = rsp.get("_content", [])
            records = content if isinstance(content, list) else [content]
        elif "data" in data and isinstance(data["data"], dict):
            total = int(data["data"].get("total", 0))
            records = data["data"].get("data", [])
        elif "balancete_receita_extra_orcamentaria" in data:
            records = data["balancete_receita_extra_orcamentaria"]

        return records, total

    async def _save_all(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> int:
        """Save to 'balancete_receita_extra' table."""
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
            "balancete_receita_extra", columns, records, ["raw_data"]
        )

    def _process_records_sync(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> list[tuple]:
        """Sync helper to process records."""
        records = []
        for item in all_records:
            month_ref = item.get("data_referencia", f"{year}00")
            # Use content hash for robustness
            import hashlib

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
