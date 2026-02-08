"""
Expenses (Despesas) Collector.

Collects public expense data from the TCE API with parallel fetching.
Uses MonthlyCollector base class for shared monthly iteration logic.
"""

import asyncio
import json
import logging

from src.etl.endpoints import Endpoint

from .base import MonthlyCollector

logger = logging.getLogger(__name__)


class ExpensesCollector(MonthlyCollector):
    """Collector for public expense (despesa) data with parallel fetching."""

    collector_name = "Despesas"

    async def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict]:
        """Fetch a single month with parallel pagination."""
        month_ref = f"{year}{month:02d}"
        url = self.client.build_url(Endpoint.DESPESAS)

        # First request: get total and first batch
        page_size = 500
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

        first_batch, total = self._extract_records_and_total(first_response)
        if not first_batch:
            return []

        # If total unknown, estimate from first page
        if not total:
            total = len(first_batch)
        logger.debug("Month %s: Found %d records", month_ref, total)

        # If all records fit in first page, done
        if total <= page_size and len(first_batch) < page_size:
            return first_batch

        # Fetch remaining pages in parallel
        return await self._fetch_remaining_pages(
            url, municipio_id, year, month_ref, first_batch, total, page_size
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
            if isinstance(content, list):
                records = content
            elif isinstance(content, dict):
                records = [content]
        elif "data" in data:
            inner = data["data"]
            if isinstance(inner, dict):
                total = int(inner.get("total", 0))
                if "data" in inner:
                    records = inner["data"] if isinstance(inner["data"], list) else []
            elif isinstance(inner, list):
                records = inner
        elif "balancete_despesa_orcamentaria" in data:
            records = data["balancete_despesa_orcamentaria"]

        return records, total

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
            "codigo_funcao",
            "codigo_subfuncao",
            "codigo_programa",
            "codigo_elemento_despesa",
            "valor_empenhado",
            "valor_liquidado",
            "valor_pago",
            "raw_data",
        ]

        update_columns = [
            "valor_empenhado",
            "valor_liquidado",
            "valor_pago",
            "raw_data",
        ]

        # Run Blocking DB write (bulk_upsert handles to_thread internally)
        return await self.bulk_upsert("despesas", columns, records, update_columns)

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
            content_hash = hashlib.md5(serialized.encode()).hexdigest()
            exp_id = f"{municipio_id}_{content_hash}_{year}"

            records.append(
                (
                    exp_id,
                    municipio_id,
                    str(year),
                    month_ref,
                    item.get("codigo_orgao"),
                    item.get("codigo_unidade_orcamentaria"),
                    item.get("codigo_funcao"),
                    item.get("codigo_subfuncao"),
                    item.get("codigo_programa"),
                    item.get("codigo_elemento_despesa"),
                    item.get("valor_empenhado_no_mes"),
                    item.get("valor_liquidado_no_mes"),
                    item.get("valor_pago_no_mes"),
                    json.dumps(item),
                )
            )
        return records
