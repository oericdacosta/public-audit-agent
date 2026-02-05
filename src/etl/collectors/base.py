"""
Base Collector.

Abstract base class for ETL data collectors.
Uses Parquet for ultra-fast DuckDB inserts with UPSERT support.
"""

import logging
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.etl.client import TCEClient
    from src.etl.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

# Global lock to serialize database writes across all collectors
# DuckDB does not support concurrent writes from multiple threads
_DB_WRITE_LOCK = threading.Lock()


class BaseCollector(ABC):
    """
    Abstract base class for data collectors.

    Uses Parquet files for ultra-fast bulk inserts with UPSERT support
    for incremental extraction.
    """

    def __init__(
        self,
        db_manager: "DatabaseManager",
        client: "TCEClient",
    ) -> None:
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

    def bulk_upsert(
        self,
        table: str,
        columns: list[str],
        records: list[tuple],
        update_columns: list[str] | None = None,
    ) -> int:
        """
        Insert records using Parquet with UPSERT (ON CONFLICT DO UPDATE).

        This is 10-100x faster than executemany for large datasets and
        supports incremental extraction (updates existing records).

        Args:
            table: Target table name.
            columns: List of column names.
            records: List of tuples with values to insert.
            update_columns: Columns to update on conflict. If None, updates all
                           columns except 'id'.

        Returns:
            Number of records upserted.
        """
        if not records:
            return 0

        # Convert tuples to DataFrame
        df = pd.DataFrame(records, columns=columns)

        # Create temp Parquet file
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            parquet_path = f.name

        try:
            df.to_parquet(parquet_path, index=False)

            # Build UPSERT SQL
            if update_columns is None:
                # Update all columns except 'id'
                update_columns = [c for c in columns if c != "id"]

            update_set = ", ".join(
                [f"{col} = EXCLUDED.{col}" for col in update_columns]
            )

            sql = f"""
                INSERT INTO {table} ({", ".join(columns)})
                SELECT {", ".join(columns)} FROM read_parquet('{parquet_path}')
                ON CONFLICT (id) DO UPDATE SET {update_set}
            """

            with _DB_WRITE_LOCK:
                with self.db_manager.get_connection() as conn:
                    conn.execute(sql)
                    conn.commit()

            logger.debug("Upserted %d records into %s via Parquet", len(records), table)
            return len(records)

        finally:
            # Cleanup temp file
            Path(parquet_path).unlink(missing_ok=True)

    def bulk_insert(self, table: str, columns: list[str], records: list[tuple]) -> int:
        """
        Legacy method - redirects to bulk_upsert for backward compatibility.
        """
        return self.bulk_upsert(table, columns, records)
