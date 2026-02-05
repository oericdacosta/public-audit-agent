"""
Expenses (Despesas) Collector - Optimized.

Collects public expense data from the TCE API with parallel fetching.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.etl.endpoints import Endpoint

from .base import BaseCollector

logger = logging.getLogger(__name__)


class ExpensesCollector(BaseCollector):
    """Collector for public expense (despesa) data with parallel fetching."""

    def run(self, municipio_id: str, year: int) -> int:
        """
        Run the expense collection for a municipality and year.

        Returns:
            Total number of records collected.
        """
        logger.info(">>> Starting Despesas (Financial) - Parallel Mode")

        # Fetch all 12 months in parallel, each with parallel pagination
        all_records = self._fetch_all_months_parallel(municipio_id, year)

        if not all_records:
            logger.info("Despesas: No records found.")
            return 0

        # Bulk save all records at once
        total = self._save_all(all_records, municipio_id, year)
        logger.info("Despesas completed: %d records.", total)
        return total

    def _fetch_all_months_parallel(
        self, municipio_id: str, year: int
    ) -> list[dict[str, Any]]:
        """
        Fetch all 12 months in parallel. Each month fetches all pages in parallel.

        Returns:
            Flattened list of all expense records.
        """
        all_records: list[dict[str, Any]] = []

        # Submit all 12 months to thread pool
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {
                executor.submit(
                    self._fetch_month_with_pagination, municipio_id, year, month
                ): month
                for month in range(1, 13)
            }

            for future in as_completed(futures):
                month = futures[future]
                try:
                    month_records = future.result()
                    if month_records:
                        all_records.extend(month_records)
                        logger.info(
                            "Month %d: Collected %d records", month, len(month_records)
                        )
                except Exception as e:
                    logger.error("Failed to fetch month %d: %s", month, e)

        return all_records

    def _fetch_month_with_pagination(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict[str, Any]]:
        """
        Fetch a single month with parallel pagination.

        Strategy:
        1. Fetch page 0 to get total count
        2. Calculate all page offsets
        3. Fetch all remaining pages in parallel
        """
        month_ref = f"{year}{month:02d}"
        url = self.client.build_url(Endpoint.DESPESAS)

        # First request: get total and first batch
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
            "quantidade": "100",
            "deslocamento": "0",
        }

        first_response = self.client.fetch_json(url, params)
        if not first_response:
            return []

        first_batch, total = self._extract_records_and_total(first_response)
        if not first_batch:
            return []

        logger.info("Month %s: Found %d records", month_ref, total)

        # If all records fit in first page, done
        if total <= 100:
            return first_batch

        # Calculate remaining offsets
        offsets = list(range(100, total, 100))

        # Fetch all remaining pages in parallel (within this month)
        all_records = list(first_batch)

        with ThreadPoolExecutor(max_workers=10) as page_executor:
            page_futures = {
                page_executor.submit(
                    self._fetch_page, url, municipio_id, year, month_ref, offset
                ): offset
                for offset in offsets
            }

            for future in as_completed(page_futures):
                try:
                    page_records = future.result()
                    if page_records:
                        all_records.extend(page_records)
                except Exception as e:
                    offset = page_futures[future]
                    logger.warning("Failed to fetch page offset %d: %s", offset, e)

        return all_records

    def _fetch_page(
        self,
        url: str,
        municipio_id: str,
        year: int,
        month_ref: str,
        offset: int,
    ) -> list[dict[str, Any]]:
        """Fetch a single page of data."""
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
            "quantidade": "100",
            "deslocamento": str(offset),
        }
        response = self.client.fetch_json(url, params)
        if response:
            records, _ = self._extract_records_and_total(response)
            return records
        return []

    def _extract_records_and_total(
        self, data: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int]:
        """Extract records list and total count from API response."""
        total = 0
        records: list[dict[str, Any]] = []

        if "rsp" in data and "_content" in data["rsp"]:
            content = data["rsp"]["_content"]
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
            elem = item.get("codigo_elemento_despesa", "0")
            val = item.get("valor_pago_no_mes", "0")
            exp_id = f"{municipio_id}_{month_ref}_{elem}_{val}_{i}"

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

        # Columns to update on conflict (all except id)
        update_columns = [
            "valor_empenhado",
            "valor_liquidado",
            "valor_pago",
            "raw_data",
        ]

        return self.bulk_upsert("despesas", columns, records, update_columns)
