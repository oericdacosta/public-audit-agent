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

# Endpoints that require pagination parameters
PAGINATED_ENDPOINTS = frozenset({Endpoint.UNIDADES_ORCAMENTARIAS})


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

    def _build_params(self, municipality_id: str, year: int) -> dict[str, str]:
        """
        Build request parameters based on endpoint requirements.

        Some endpoints (MUNICIPIOS, FUNCOES) don't require parameters.
        Others require codigo_municipio and exercicio_orcamento.
        Paginated endpoints also require quantidade and deslocamento.
        """
        if self.endpoint in NO_PARAMS_ENDPOINTS:
            return {}

        params = {
            "codigo_municipio": municipality_id,
            "exercicio_orcamento": f"{year}00",
        }

        # Add pagination for endpoints that require it
        if self.endpoint in PAGINATED_ENDPOINTS:
            params["quantidade"] = "10000"
            params["deslocamento"] = "0"

        return params

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

    def run(self, municipality_id: str, year: int) -> int:
        """
        Execute collection for the configured endpoint.

        Args:
            municipality_id: The city code
            year: The fiscal year

        Returns:
            Count of records inserted
        """
        # 1. Build endpoint-specific parameters
        params = self._build_params(municipality_id, year)

        # 2. Fetch Data
        data = self.client.fetch(self.endpoint, params)

        if not data:
            return 0

        # 3. Extract records from response wrapper
        records = self._extract_records(data)

        if not records:
            return 0

        # 4. Load to Database (using endpoint's table_name)
        self.db_manager.load_data(self.endpoint.table_name, records)

        return len(records)
