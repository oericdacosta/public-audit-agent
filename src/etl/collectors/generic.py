"""
Generic Collector.

Handles extraction for standard endpoints that don't require custom processing logic.
Uses Endpoint properties for deterministic data extraction.
"""

import logging
from typing import Any

from src.etl.client import TCEClient
from src.etl.db_manager import DatabaseManager
from src.etl.endpoints import Endpoint
from src.etl.utils.masking import sanitize_record

logger = logging.getLogger(__name__)

# Endpoints that don't require any parameters (global lookups)
NO_PARAMS_ENDPOINTS = frozenset(
    {Endpoint.MUNICIPIOS, Endpoint.FUNCOES, Endpoint.NEGOCIANTES}
)

# Endpoints that require pagination parameters and looping
PAGINATED_ENDPOINTS = frozenset(
    {
        Endpoint.UNIDADES_ORCAMENTARIAS,
        Endpoint.TALOES_RECEITAS,
        Endpoint.TALOES_EXTRAS,
        Endpoint.NOTAS_FISCAIS,
        Endpoint.NOTAS_PAGAMENTOS,
        Endpoint.ITENS_NOTAS_FISCAIS,
        Endpoint.AGENTES_PUBLICOS,
        Endpoint.LIQUIDACOES,
    }
)


class GenericCollector:
    """
    A universal collector for standard TCE endpoints.

    Fetches data from the API and loads it directly into the target table,
    using the Endpoint's response_key for deterministic extraction.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        client: TCEClient,
        endpoint: Endpoint,
    ) -> None:
        """
        Initialize the generic collector.

        Args:
            db_manager: Database manager instance
            client: HTTP Client instance
            endpoint: The Endpoint definition (path, base, table_name, response_key)
        """
        self.db_manager = db_manager
        self.client = client
        self.endpoint = endpoint

    def _build_base_params(self, municipality_id: str, year: int) -> dict[str, str]:
        """Build base request parameters."""
        if self.endpoint in NO_PARAMS_ENDPOINTS:
            return {}

        return {
            "codigo_municipio": municipality_id,
            "exercicio_orcamento": f"{year}00",
        }

    def _extract_records(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract the list of records from API response.

        Uses the Endpoint's response_key for deterministic extraction,
        with fallback patterns for compatibility.
        """
        if not data:
            return []

        # Primary: Use the endpoint's defined response_key
        if self.endpoint.response_key and self.endpoint.response_key in data:
            content = data[self.endpoint.response_key]
            if isinstance(content, list):
                return content
            elif isinstance(content, dict):
                return [content]

        # Fallback: Common API response patterns
        for key in ["data", "rows", "_content"]:
            if key in data:
                content = data[key]
                if isinstance(content, list):
                    return content
                elif isinstance(content, dict):
                    # Handle nested data structure (e.g. data -> data list)
                    if "data" in content and isinstance(content["data"], list):
                        return content["data"]
                    if "rows" in content and isinstance(content["rows"], list):
                        return content["rows"]
                    return [content]

        # Fallback: rsp._content pattern
        if "rsp" in data and isinstance(data["rsp"], dict):
            content = data["rsp"].get("_content")
            if isinstance(content, list):
                return content
            elif isinstance(content, dict):
                return [content]

        # Last resort: single-key wrapper
        if len(data) == 1:
            single_value = list(data.values())[0]
            if isinstance(single_value, list):
                return single_value

        return []

    def _run_paginated(self, municipality_id: str, year: int) -> int:
        """Run collection with loop-based pagination."""
        import json

        params = self._build_base_params(municipality_id, year)
        limit = 100  # Default small page size for detailed endpoints
        offset = 0
        total_records = 0
        page = 1

        while True:
            params["quantidade"] = str(limit)
            params["deslocamento"] = str(offset)

            data = self.client.fetch(self.endpoint, params)
            if not data:
                break

            records = self._extract_records(data)
            if not records:
                break

            # Augment records with standard fields
            augmented = []
            for item in records:
                item_copy = item.copy()
                # Generate unique ID
                id_field = self._get_id_field(item)
                item_copy["id"] = f"{municipality_id}_{id_field}_{year}"
                item_copy["municipio_id"] = municipality_id
                item_copy["exercicio_orcamento"] = str(year)
                item_copy["raw_data"] = json.dumps(item)
                augmented.append(item_copy)

            # Apply data masking for sensitive fields
            sanitized = [
                sanitize_record(r, self.endpoint.table_name) for r in augmented
            ]
            self.db_manager.load_data(self.endpoint.table_name, sanitized)
            count = len(records)
            total_records += count

            # Log progress
            logger.info(
                "%s page %d: %d records (total: %d)",
                self.endpoint.name,
                page,
                count,
                total_records,
            )

            # Stop if we got fewer records than the limit, meaning end of data
            if count < limit:
                break

            offset += limit
            page += 1

        return total_records

    def _get_id_field(self, record: dict) -> str:
        """Generate a unique identifier from record fields."""
        # Try common ID fields
        for field in [
            "numero_talao_receita",
            "nu_talao_receita_tx",
            "numero_nota_fiscal",
            "numero_liquidacao",
            "codigo_agente",
            "numero_pagamento",
        ]:
            if field in record:
                return str(record[field])
        # Fallback: hash of record
        import hashlib

        return hashlib.md5(  # noqa: S324
            str(sorted(record.items())).encode(), usedforsecurity=False
        ).hexdigest()[:12]

    def run(self, municipality_id: str, year: int) -> int:
        """
        Execute collection for the configured endpoint.

        Args:
            municipality_id: The city code
            year: The fiscal year

        Returns:
            Count of records inserted
        """
        if self.endpoint in PAGINATED_ENDPOINTS:
            return self._run_paginated(municipality_id, year)

        # Non-paginated flow (original logic)
        params = self._build_base_params(municipality_id, year)
        data = self.client.fetch(self.endpoint, params)

        if not data:
            return 0

        records = self._extract_records(data)

        if not records:
            return 0

        # Apply data masking for sensitive fields
        sanitized = [sanitize_record(r, self.endpoint.table_name) for r in records]
        self.db_manager.load_data(self.endpoint.table_name, sanitized)

        return len(records)
