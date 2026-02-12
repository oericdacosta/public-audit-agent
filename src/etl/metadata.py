"""
ETL Metadata Manager.

Tracks ETL execution status for idempotent processing.
"""

import logging
from typing import TYPE_CHECKING, Optional

import duckdb

if TYPE_CHECKING:
    from src.etl.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class ETLMetadataManager:
    """
    Manages ETL execution metadata for idempotent processing.

    Tracks status (STARTED, COMPLETED, FAILED) for each
    (municipality, year, source) combination.
    """

    def __init__(self, db_manager: "DatabaseManager") -> None:
        """
        Initialize with a database manager.

        Args:
            db_manager: DatabaseManager instance for database access.
        """
        self._db_manager = db_manager

    def get_status(self, municipality_id: str, year: int, source: str) -> Optional[str]:
        """
        Check if a specific year/source has been processed.

        Args:
            municipality_id: Municipality code.
            year: Fiscal year.
            source: Data source identifier (e.g., 'despesas', 'receitas').

        Returns:
            Status string ('COMPLETED', 'STARTED', 'FAILED') or None.
        """
        try:
            with self._db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT status FROM etl_metadata
                    WHERE municipio_id = ? AND year = ? AND source = ?
                    """,
                    (municipality_id, year, source),
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except (duckdb.Error, duckdb.CatalogException):
            return None

    def update_status(
        self,
        municipality_id: str,
        year: int,
        source: str,
        status: str,
        count: int = 0,
    ) -> None:
        """
        Update the execution state in the database.

        Args:
            municipality_id: Municipality code.
            year: Fiscal year.
            source: Data source identifier.
            status: New status ('STARTED', 'COMPLETED', 'FAILED').
            count: Number of records processed.
        """
        with self._db_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO etl_metadata
                (municipio_id, year, source, status, record_count, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (municipality_id, year, source, status, count),
            )
            conn.commit()
