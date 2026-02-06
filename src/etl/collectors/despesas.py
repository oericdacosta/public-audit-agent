"""
Expenses (Despesas) Collector.

Collects public expense data from the TCE API with parallel fetching.
Uses MonthlyCollector base class for shared monthly iteration logic.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.etl.endpoints import Endpoint

from .base import MAX_PAGE_WORKERS, APIFetchError, MonthlyCollector

logger = logging.getLogger(__name__)


class ExpensesCollector(MonthlyCollector):
    """Collector for public expense (despesa) data with parallel fetching."""

    collector_name = "Despesas"

    def _fetch_month(self, municipio_id: str, year: int, month: int) -> list[dict]:
        """Fetch a single month with parallel pagination."""
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

        logger.debug("Month %s: Found %d records", month_ref, total)

        # If all records fit in first page, done
        if total <= 100:
            return first_batch

        # Fetch remaining pages in parallel
        return self._fetch_remaining_pages(
            url, municipio_id, year, month_ref, first_batch, total
        )

    def _fetch_remaining_pages(
        self,
        url: str,
        municipio_id: str,
        year: int,
        month_ref: str,
        first_page: list[dict],
        total: int,
    ) -> list[dict]:
        """Fetch all remaining pages after the first one."""
        all_records = list(first_page)
        offsets = list(range(100, total, 100))

        with ThreadPoolExecutor(max_workers=MAX_PAGE_WORKERS) as executor:
            futures = {
                executor.submit(
                    self._fetch_page, url, municipio_id, year, month_ref, offset
                ): offset
                for offset in offsets
            }

            for future in as_completed(futures):
                offset = futures[future]
                try:
                    page_records = future.result()
                    if page_records:
                        all_records.extend(page_records)
                except APIFetchError as e:
                    logger.warning("API error at offset %d: %s", offset, e)
                except Exception:
                    logger.exception("Unexpected error at offset %d", offset)

        return all_records

    def _fetch_page(
        self, url: str, municipio_id: str, year: int, month_ref: str, offset: int
    ) -> list[dict]:
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

    def _extract_records_and_total(self, data: dict) -> tuple[list[dict], int]:
        """Extract records list and total count from API response."""
        total = 0
        records: list = []

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

    def _save_all(self, all_records: list[dict], municipio_id: str, year: int) -> int:
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

        update_columns = [
            "valor_empenhado",
            "valor_liquidado",
            "valor_pago",
            "raw_data",
        ]

        return self.bulk_upsert("despesas", columns, records, update_columns)
