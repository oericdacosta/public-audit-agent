"""
Extra-Budgetary Collectors.

Collectors for extra-budgetary expense and revenue data from the TCE API.
Uses MonthlyCollector base class for shared monthly iteration logic.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.etl.endpoints import Endpoint

from .base import MAX_PAGE_WORKERS, APIFetchError, MonthlyCollector

logger = logging.getLogger(__name__)


class DespesaExtraOrcamentariaCollector(MonthlyCollector):
    """Collector for Extra-Budgetary Expenses (Despesa Extra-Orçamentária)."""

    collector_name = "Despesa Extra"

    def _fetch_month(self, municipio_id: str, year: int, month: int) -> list[dict]:
        """Fetch data for a single month (no pagination)."""
        month_ref = f"{year}{month:02d}"
        params = {
            "codigo_municipio": municipio_id,
            "exercicio_orcamento": f"{year}00",
            "data_referencia": month_ref,
        }

        url = self.client.build_url(Endpoint.BALANCETE_DESPESA_EXTRA)
        data = self.client.fetch_json(url, params)
        if not data:
            return []

        return self._extract_records(data)

    def _extract_records(self, data: dict) -> list[dict]:
        """Extract records from API response."""
        records: list = []

        if "balancete_despesa_extra_orcamentaria" in data:
            records = data["balancete_despesa_extra_orcamentaria"]
        elif "data" in data:
            records = data["data"]
        elif "rsp" in data and "_content" in data["rsp"]:
            records = data["rsp"]["_content"]

        if isinstance(records, dict):
            return [records]
        return records if isinstance(records, list) else []

    def _save_all(self, all_records: list[dict], municipio_id: str, year: int) -> int:
        """Save to 'balancete_despesa_extra' table."""
        if not all_records:
            return 0

        records = []
        for i, item in enumerate(all_records):
            month_ref = item.get("data_referencia", f"{year}00")
            conta = item.get("codigo_conta_extraorcamentaria", "0")
            rec_id = f"{municipio_id}_{month_ref}_{conta}_{i}"

            records.append(
                (
                    rec_id,
                    municipio_id,
                    str(year),
                    month_ref,
                    json.dumps(item),
                )
            )

        columns = [
            "id",
            "municipio_id",
            "exercicio_orcamento",
            "mes_referencia",
            "raw_data",
        ]

        return self.bulk_upsert(
            "balancete_despesa_extra", columns, records, ["raw_data"]
        )


class ReceitaExtraOrcamentariaCollector(MonthlyCollector):
    """Collector for Extra-Budgetary Revenues with Pagination."""

    collector_name = "Receita Extra"

    def _fetch_month(self, municipio_id: str, year: int, month: int) -> list[dict]:
        """Fetch data for a single month with pagination."""
        month_ref = f"{year}{month:02d}"
        url = self.client.build_url(Endpoint.BALANCETE_RECEITA_EXTRA)

        # Initial fetch
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

        records, total = self._extract_records_and_total(first_response)
        if not records:
            return []

        logger.debug("Receita Extra Month %s: Found %d total records", month_ref, total)

        if total <= 100:
            return records

        # Fetch remaining pages in parallel
        return self._fetch_remaining_pages(
            url, municipio_id, year, month_ref, records, total
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

        if "balancete_receita_extra_orcamentaria" in data:
            records = data["balancete_receita_extra_orcamentaria"]

        if "data" in data and isinstance(data["data"], dict):
            total = int(data["data"].get("total", 0))
            records = data["data"].get("data", [])
        elif "rsp" in data and "_content" in data["rsp"]:
            content = data["rsp"]["_content"]
            records = content if isinstance(content, list) else [content]

        return records, total

    def _save_all(self, all_records: list[dict], municipio_id: str, year: int) -> int:
        """Save to 'balancete_receita_extra' table."""
        if not all_records:
            return 0

        records = []
        for i, item in enumerate(all_records):
            month_ref = item.get("data_referencia", f"{year}00")
            conta = item.get("codigo_conta_extraorcamentaria", "0")
            rec_id = f"{municipio_id}_{month_ref}_{conta}_{i}"

            records.append(
                (
                    rec_id,
                    municipio_id,
                    str(year),
                    month_ref,
                    json.dumps(item),
                )
            )

        columns = [
            "id",
            "municipio_id",
            "exercicio_orcamento",
            "mes_referencia",
            "raw_data",
        ]

        return self.bulk_upsert(
            "balancete_receita_extra", columns, records, ["raw_data"]
        )
