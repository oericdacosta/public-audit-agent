"""
Procurement Collector.

Collects date-range based procurement data (Licitações, Contratos, etc.)
from the TCE API. Uses sequential month fetching + pagination.
"""

import calendar
import json
import logging
from typing import cast

from src.etl.client import TCEClient
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
    3. Pagination (looping through 'quantidade' and 'deslocamento')
    """

    collector_name = "Transações"

    # Map each endpoint to its specific date parameter name
    DATE_PARAM_MAP = {
        Endpoint.LICITACOES: "data_realizacao_autuacao_licitacao",
        Endpoint.ITENS_LICITACOES: "data_realizacao_licitacao",
        Endpoint.LICITANTES: "data_realizacao_licitacao",
        Endpoint.CONTRATOS: "data_contrato",
        Endpoint.CONTRATADOS: "data_contrato",
        Endpoint.NOTAS_EMPENHO: "data_emissao_empenho",
    }

    def __init__(
        self,
        db_manager: DatabaseManager,
        client: TCEClient,
        endpoint: Endpoint,
    ) -> None:
        """
        Initialize the transactions collector.

        Args:
            db_manager: Database manager instance
            client: HTTP Client instance
            endpoint: The specific endpoint to collect
        """
        # Initialize BaseCollector (grandparent) attributes
        super().__init__(db_manager, client)
        self.endpoint = endpoint
        # Update collector name for logging
        self.collector_name = f"Transações({endpoint.name})"

    # Endpoints that DON'T support quantidade/deslocamento pagination
    NO_PAGINATION_ENDPOINTS = {
        Endpoint.LICITACOES,
        Endpoint.ITENS_LICITACOES,
    }

    def _fetch_month_paginated(
        self, municipio_id: str, date_range: str, date_param: str
    ) -> list[dict]:
        """Fetch all pages for a given month/date range."""
        all_records = []
        limit = 100
        offset = 0

        # Check if this endpoint supports pagination
        supports_pagination = self.endpoint not in self.NO_PAGINATION_ENDPOINTS

        while True:
            params = {
                "codigo_municipio": municipio_id,
                date_param: date_range,
            }

            # Only add pagination params if supported
            if supports_pagination:
                params["quantidade"] = str(limit)
                params["deslocamento"] = str(offset)

            url = self.client.build_url(self.endpoint)
            data = self.client.fetch_json(url, params)

            if not data:
                break

            # Handle response wrapping
            batch = []
            if isinstance(data, list):
                batch = data
            elif isinstance(data, dict):
                # Using the response key if available, otherwise "data" or "rows"
                if self.endpoint.response_key and self.endpoint.response_key in data:
                    batch = cast(list[dict], data[self.endpoint.response_key])
                else:
                    raw_batch: list[dict] | dict = cast(
                        list[dict] | dict, data.get("data", data.get("rows", [data]))
                    )
                    # Handle nested data structure
                    if isinstance(raw_batch, dict):
                        if "data" in raw_batch and isinstance(raw_batch["data"], list):
                            batch = cast(list[dict], raw_batch["data"])
                        elif "rows" in raw_batch and isinstance(
                            raw_batch["rows"], list
                        ):
                            batch = cast(list[dict], raw_batch["rows"])
                        else:
                            batch = [cast(dict, raw_batch)]
                    else:
                        batch = cast(list[dict], raw_batch)

            if not batch:
                break

            all_records.extend(batch)

            # For endpoints without pagination, we get all records in one request
            if not supports_pagination:
                break

            if len(batch) < limit:
                break

            offset += limit

        return all_records

    def _fetch_month(self, municipio_id: str, year: int, month: int) -> list[dict]:
        """Fetch data for a single month with pagination."""
        last_day = calendar.monthrange(int(year), month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
        date_range = f"{start_date}_{end_date}"

        date_param = self.DATE_PARAM_MAP.get(
            self.endpoint, "data_realizacao_autuacao_licitacao"
        )

        return self._fetch_month_paginated(municipio_id, date_range, date_param)

    def _save_all(self, all_records: list[dict], municipio_id: str, year: int) -> int:
        """Save records to database."""
        if not all_records:
            return 0

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
            elif self.endpoint == Endpoint.NOTAS_EMPENHO:
                rec_id_parts.append(str(item.get("numero_empenho", "unk")))
                rec_id_parts.append(str(item.get("codigo_orgao", "unk")))

            rec_id_parts.append(str(year))
            item_copy["id"] = "_".join(rec_id_parts)
            item_copy["municipio_id"] = municipio_id
            item_copy["exercicio_orcamento"] = str(year)
            item_copy["raw_data"] = json.dumps(item)

            augmented_records.append(item_copy)

        self.db_manager.load_data(self.endpoint.table_name, augmented_records)
        return len(augmented_records)
