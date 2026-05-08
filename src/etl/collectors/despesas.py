"""
Expenses (Despesas) Collector.

Collects public expense data from the TCE API with parallel fetching.
Uses MonthlyCollector base class for shared monthly iteration logic.
"""

import asyncio
import hashlib
import json
import logging

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.etl.endpoints import Endpoint

from .base import MonthlyCollector

# ---------------------------------------------------------------------------
# Pydantic models for the 3 known TCE API response shapes
# ---------------------------------------------------------------------------


class _RspContent(BaseModel):
    """Inner envelope from shape {"rsp": {"_total": N, "_content": [...]}}."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    total: int = Field(alias="_total", default=0)
    content: list[dict] = Field(alias="_content", default_factory=list)

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, v: object) -> list[dict]:
        if isinstance(v, dict):
            return [v]
        if isinstance(v, list):
            return [r for r in v if isinstance(r, dict)]
        return []


class _RspEnvelope(BaseModel):
    rsp: _RspContent


class _DataDictInner(BaseModel):
    model_config = ConfigDict(extra="allow")
    total: int = 0
    data: list[dict] = Field(default_factory=list)

    @field_validator("data", mode="before")
    @classmethod
    def normalize_data(cls, v: object) -> list[dict]:
        if isinstance(v, list):
            return [r for r in v if isinstance(r, dict)]
        return []


class _BalanceteEnvelope(BaseModel):
    balancete_despesa_orcamentaria: list[dict]


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

        for offset, result in zip(offsets, results, strict=True):
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
        """Extract records list and total count from API response.

        Tries each known TCE API response shape via Pydantic models. Falls back
        to ([], 0) on unexpected shapes instead of silently returning partial data.
        """
        if "rsp" in data:
            try:
                envelope = _RspEnvelope.model_validate(data)
                return envelope.rsp.content, envelope.rsp.total
            except Exception:
                pass

        if "data" in data:
            inner = data["data"]
            if isinstance(inner, list):
                return [r for r in inner if isinstance(r, dict)], 0
            try:
                inner_model = _DataDictInner.model_validate(inner)
                return inner_model.data, inner_model.total
            except Exception:
                pass

        if "balancete_despesa_orcamentaria" in data:
            try:
                bal_envelope = _BalanceteEnvelope.model_validate(data)
                return bal_envelope.balancete_despesa_orcamentaria, 0
            except Exception:
                pass

        logger.warning(
            "Unexpected API response shape — keys: %s", list(data.keys())[:5]
        )
        return [], 0

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
            serialized = json.dumps(item, sort_keys=True, default=str)
            content_hash = hashlib.sha256(serialized.encode()).hexdigest()
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
