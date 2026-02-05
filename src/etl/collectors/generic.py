"""
Generic Collector.

Handles extraction for standard endpoints that don't require custom processing logic.
"""

from typing import Any

from src.etl.client import TCEClient
from src.etl.db_manager import DatabaseManager
from src.etl.endpoints import Endpoint

# Endpoints that don't require any parameters (global lookups)
NO_PARAMS_ENDPOINTS = {Endpoint.MUNICIPIOS, Endpoint.FUNCOES}

# Endpoints that require pagination parameters
PAGINATED_ENDPOINTS = {Endpoint.UNIDADES_ORCAMENTARIAS}

# Mapping of endpoints to their expected response keys
# TCE API wraps data in keys like {"programas": [...], "orgaos": [...]}
ENDPOINT_RESPONSE_KEYS = {
    Endpoint.MUNICIPIOS: "municipios",
    Endpoint.ORGAOS: "orgaos",
    Endpoint.UNIDADES_ORCAMENTARIAS: "unidades_orcamentarias",
    Endpoint.FUNCOES: "funcoes",
    Endpoint.ORDENADORES: "ordenadores",
    Endpoint.CONTAS_BANCARIAS: "contas_bancarias",
    Endpoint.PROGRAMAS: "programas",
    Endpoint.PROJETOS_ATIVIDADES: "despesa_projeto_atividade",
    Endpoint.ORCAMENTO_RECEITA: "orcamento_receita",
}


class GenericCollector:
    """
    A universal collector for standard TCE endpoints.
    It fetches data from the API and loads it directly into the target table,
    handling the common JSON structure automatically.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        client: TCEClient,
        endpoint: Endpoint,
        table_name: str,
    ) -> None:
        """
        Initialize the generic collector.

        Args:
            db_manager: Database manager instance
            client: HTTP Client instance
            endpoint: The Endpoint definition (contains path and base)
            table_name: The name of the target table in the database
        """
        self.db_manager = db_manager
        self.client = client
        self.endpoint = endpoint
        self.table_name = table_name

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

        TCE API returns data wrapped in keys like:
        - {"programas": [{...}, {...}]}
        - {"orgaos": [{...}, {...}]}

        This method extracts the actual list of records.
        """
        if not data:
            return []

        # Try the expected key for this endpoint
        expected_key = ENDPOINT_RESPONSE_KEYS.get(self.endpoint)
        if expected_key and expected_key in data:
            content = data[expected_key]
            if isinstance(content, list):
                return content
            elif isinstance(content, dict):
                return [content]

        # Fallback: try common patterns
        for key in ["data", "rows", "_content", "rsp"]:
            if key in data:
                content = data[key]
                if key == "rsp" and isinstance(content, dict) and "_content" in content:
                    content = content["_content"]
                if isinstance(content, list):
                    return content
                elif isinstance(content, dict):
                    return [content]

        # Last resort: if the response itself looks like a list wrapper
        # with a single key containing a list, extract it
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

        # 4. Load to Database
        self.db_manager.load_data(self.table_name, records)

        return len(records)
