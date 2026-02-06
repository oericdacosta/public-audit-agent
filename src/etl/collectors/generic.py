"""
Generic Collector.

Handles extraction for standard endpoints that don't require custom processing logic.
Uses Endpoint properties for deterministic data extraction.
"""

from typing import Any

from src.etl.client import TCEClient
from src.etl.db_manager import DatabaseManager
from src.etl.endpoints import Endpoint

# Endpoints that don't require any parameters (global lookups)
NO_PARAMS_ENDPOINTS = frozenset({Endpoint.MUNICIPIOS, Endpoint.FUNCOES})

# Endpoints that require pagination parameters and looping
PAGINATED_ENDPOINTS = frozenset(
    {
        Endpoint.UNIDADES_ORCAMENTARIAS,
        Endpoint.TALOES_RECEITAS,
        Endpoint.TALOES_EXTRAS,
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
        params = self._build_base_params(municipality_id, year)
        limit = 100  # Default small page size for detailed endpoints
        offset = 0
        total_records = 0

        while True:
            params["quantidade"] = str(limit)
            params["deslocamento"] = str(offset)

            data = self.client.fetch(self.endpoint, params)
            if not data:
                break

            records = self._extract_records(data)
            if not records:
                break

            self.db_manager.load_data(self.endpoint.table_name, records)
            count = len(records)
            total_records += count

            # Stop if we got fewer records than the limit, meaning end of data
            if count < limit:
                break

            offset += limit

        return total_records

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

        self.db_manager.load_data(self.endpoint.table_name, records)

        return len(records)
