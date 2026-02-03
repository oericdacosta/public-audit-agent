"""
Generic Collector.

Handles extraction for standard endpoints that don't require custom processing logic.
"""

from src.etl.client import TCEClient
from src.etl.db_manager import DatabaseManager
from src.etl.endpoints import Endpoint


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

    def run(self, municipality_id: str, year: int) -> int:
        """
        Execute collection for the configured endpoint.

        Args:
            municipality_id: The city code
            year: The fiscal year

        Returns:
            Count of records inserted
        """
        # 1. Fetch Data
        params = {
            "codigo_municipio": municipality_id,
            "exercicio_orcamento": f"{year}00",
        }

        data = self.client.fetch(self.endpoint, params)

        if not data:
            return 0

        # 2. Load to Database
        self.db_manager.load_data(self.table_name, data)

        return len(data)
