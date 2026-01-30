"""
Base Collector.

Abstract base class for ETL data collectors.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.etl.client import TCEClient
    from src.etl.db_manager import DatabaseManager


class BaseCollector(ABC):
    """
    Abstract base class for data collectors.

    Defines the interface that all collectors must implement.
    """

    def __init__(self, db_manager: "DatabaseManager", client: "TCEClient") -> None:
        """
        Initialize the collector with database and API client.

        Args:
            db_manager: Database manager instance.
            client: TCE API client instance.
        """
        self.db_manager = db_manager
        self.client = client

    @abstractmethod
    def run(self, municipio_id: str, year: int) -> int:
        """
        Execute the collection process for a municipality and year.

        Args:
            municipio_id: Municipality identifier.
            year: Fiscal year to collect.

        Returns:
            Number of records collected.
        """
        pass

    def bulk_insert(self, table: str, columns: list[str], records: list[tuple]) -> int:
        """
        Insert records in bulk using executemany for better performance.

        Args:
            table: Target table name.
            columns: List of column names.
            records: List of tuples with values to insert.

        Returns:
            Number of records inserted.
        """
        if not records:
            return 0

        placeholders = ", ".join(["?" for _ in columns])
        column_names = ", ".join(columns)

        with self.db_manager.get_connection() as conn:
            sql = (
                f"INSERT OR REPLACE INTO {table} "
                f"({column_names}) VALUES ({placeholders})"
            )
            conn.executemany(sql, records)
            conn.commit()

        return len(records)
