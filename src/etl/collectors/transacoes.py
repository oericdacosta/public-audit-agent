"""
Procurement Collector.

Collects date-range based procurement data (Licitações, Contratos, etc.)
from the TCE API. Uses parallel month fetching + parallel pagination.
"""

import asyncio
import calendar
import json
import logging
from typing import Any, cast

from src.etl.client import AsyncTCEClient
from src.etl.collectors.base import MonthlyCollector
from src.etl.db_manager import DatabaseManager
from src.etl.endpoints import Endpoint

logger = logging.getLogger(__name__)


class TransacoesCollector(MonthlyCollector):
    """
    Generalized collector for transactional endpoints (Procurement, Empenhos, etc.).

    These endpoints require:
    1. Month-by-month fetching (to avoid timeouts on large intervals)
    2. Date range construction (YYYY-MM-DD_YYYY-MM-DD)
    3. Pagination (parallel when total is known, sequential fallback otherwise)
    """

    collector_name = "Transações"

    # Map each endpoint to its specific date parameter name
    DATE_PARAM_MAP = {
        Endpoint.LICITACOES: "data_realizacao_autuacao_licitacao",
        Endpoint.ITENS_LICITACOES: "data_realizacao_licitacao",
        Endpoint.LICITANTES: "data_realizacao_licitacao",
        Endpoint.CONTRATOS: "data_contrato",
        Endpoint.CONTRATADOS: "data_contrato",
    }

    # Endpoints that DON'T support quantidade/deslocamento pagination
    NO_PAGINATION_ENDPOINTS = {
        Endpoint.LICITACOES,
        Endpoint.ITENS_LICITACOES,
    }

    def __init__(
        self,
        db_manager: DatabaseManager,
        client: AsyncTCEClient,
        endpoint: Endpoint,
    ) -> None:
        super().__init__(db_manager, client)
        self.endpoint = endpoint
        self.collector_name = f"Transações({endpoint.name})"

    def _extract_records_and_total(self, data: Any) -> tuple[list[dict], int]:
        """Extract records list and total count from API response."""
        total = 0
        records: list[dict] = []

        if isinstance(data, list):
            return data, 0

        if not isinstance(data, dict):
            return [], 0

        # Try rsp format first (has _total)
        if "rsp" in data and isinstance(data["rsp"], dict):
            rsp = data["rsp"]
            total = int(rsp.get("_total", 0))
            content = rsp.get("_content", [])
            if isinstance(content, list):
                records = content
            elif isinstance(content, dict):
                records = [content]
            return records, total

        # Try response_key
        if self.endpoint.response_key and self.endpoint.response_key in data:
            content = data[self.endpoint.response_key]
            if isinstance(content, list):
                records = content
            elif isinstance(content, dict):
                records = [content]
            return records, total

        # Try nested data format
        raw = data.get("data", data.get("rows", None))
        if raw is not None:
            if isinstance(raw, dict):
                total = int(raw.get("total", 0))
                inner = raw.get("data", raw.get("rows", []))
                if isinstance(inner, list):
                    records = inner
                else:
                    records = [cast(dict, raw)]
            elif isinstance(raw, list):
                records = cast(list[dict], raw)
            return records, total

        return [], 0

    def _build_params(
        self, municipio_id: str, date_range: str, date_param: str
    ) -> dict[str, str]:
        """Build base request parameters for this endpoint."""
        return {
            "codigo_municipio": municipio_id,
            date_param: date_range,
        }

    async def _fetch_page(
        self,
        municipio_id: str,
        date_range: str,
        date_param: str,
        offset: int,
        page_size: int = 100,
    ) -> list[dict]:
        """Fetch a single page of paginated data."""
        params = self._build_params(municipio_id, date_range, date_param)
        params["quantidade"] = str(page_size)
        params["deslocamento"] = str(offset)

        url = self.client.build_url(self.endpoint)
        data = await self.client.fetch_json(url, params)
        if not data:
            return []

        records, _ = self._extract_records_and_total(data)
        return records

    async def _fetch_month_paginated(
        self, municipio_id: str, date_range: str, date_param: str
    ) -> list[dict]:
        """Fetch all pages for a given month/date range with parallel pagination."""
        supports_pagination = self.endpoint not in self.NO_PAGINATION_ENDPOINTS
        page_size = 100
        all_records = []

        # Build first request
        params = self._build_params(municipio_id, date_range, date_param)
        if supports_pagination:
            params["quantidade"] = str(page_size)
            params["deslocamento"] = "0"

        url = self.client.build_url(self.endpoint)
        data = await self.client.fetch_json(url, params)
        if not data:
            return []

        first_records, api_total = self._extract_records_and_total(data)
        if not first_records:
            return []

        # For endpoints without pagination, return all records from single request
        if not supports_pagination:
            return first_records

        all_records.extend(first_records)

        # If all records fit in first page, done
        if not api_total:
            api_total = len(first_records)

        if api_total <= page_size and len(first_records) < page_size:
            return all_records

        if api_total > page_size:
            # Known total: fetch remaining pages in parallel
            offsets = list(range(page_size, api_total, page_size))

            tasks = [
                self._fetch_page(
                    municipio_id, date_range, date_param, offset, page_size
                )
                for offset in offsets
            ]

            # Fetch all concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for offset, result in zip(offsets, results, strict=False):
                if isinstance(result, Exception):
                    logger.warning("API error at offset %d: %s", offset, result)
                elif isinstance(result, list):
                    all_records.extend(result)

        else:
            # Unknown total but full first page: sequential fallback
            offset = page_size
            while True:
                page_records = await self._fetch_page(
                    municipio_id, date_range, date_param, offset, page_size
                )
                if not page_records:
                    break
                all_records.extend(page_records)
                if len(page_records) < page_size:
                    break
                offset += page_size

        return all_records

    async def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict]:
        """Fetch data for a single month with pagination."""
        last_day = calendar.monthrange(int(year), month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
        date_range = f"{start_date}_{end_date}"

        date_param = self.DATE_PARAM_MAP.get(
            self.endpoint, "data_realizacao_autuacao_licitacao"
        )

        return await self._fetch_month_paginated(municipio_id, date_range, date_param)

    async def _save_all(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> int:
        """Save records to database."""
        if not all_records:
            return 0

        # Run CPU-bound processing in thread
        augmented_records = await asyncio.to_thread(
            self._process_records_sync, all_records, municipio_id, year
        )

        # Run Blocking DB write in thread
        await asyncio.to_thread(
            self.db_manager.load_data, self.endpoint.table_name, augmented_records
        )
        return len(augmented_records)

    def _process_records_sync(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> list[dict]:
        """Sync helper for processing records."""
        augmented_records = []
        for item in all_records:
            item_copy = item.copy()

            # ID GENERATION
            rec_id_parts = [municipio_id]
            if self.endpoint == Endpoint.LICITACOES:
                rec_id_parts.append(str(item.get("numero_licitacao", "unk")))
                rec_id_parts.append(str(item.get("numero_processo_licitatorio", "unk")))
            elif self.endpoint == Endpoint.CONTRATOS:
                rec_id_parts.append(str(item.get("numero_contrato", "unk")))
            elif self.endpoint == Endpoint.CONTRATADOS:
                rec_id_parts.append(str(item.get("numero_contrato", "unk")))
                rec_id_parts.append(str(item.get("documento_negociante", "unk")))
            elif self.endpoint == Endpoint.LICITANTES:
                rec_id_parts.append(str(item.get("numero_licitacao", "unk")))
                rec_id_parts.append(str(item.get("numero_documento_negociante", "unk")))
            elif self.endpoint == Endpoint.ITENS_LICITACOES:
                rec_id_parts.append(str(item.get("numero_licitacao", "unk")))
                rec_id_parts.append(
                    str(item.get("numero_sequencial_item_licitacao", "unk"))
                )

            rec_id_parts.append(str(year))
            item_copy["id"] = "_".join(rec_id_parts)
            item_copy["municipio_id"] = municipio_id
            item_copy["exercicio_orcamento"] = str(year)
            item_copy["raw_data"] = json.dumps(item)

            augmented_records.append(item_copy)

        return augmented_records
