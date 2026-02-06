"""
Base Collector.

Abstract base class for ETL data collectors.
Uses Parquet for ultra-fast DuckDB inserts with UPSERT support.
"""

import logging
import tempfile
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import pandas as pd

if TYPE_CHECKING:
    from src.etl.client import TCEClient
    from src.etl.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

# Global lock to serialize database writes across all collectors
# DuckDB does not support concurrent writes from multiple threads
_DB_WRITE_LOCK = threading.Lock()


# --- Constants ---
MAX_MONTH_WORKERS = 12  # One thread per month
MAX_PAGE_WORKERS = 5  # Threads for pagination within a month


# --- Exceptions ---
class APIFetchError(Exception):
    """Raised when an API fetch operation fails."""

    def __init__(
        self,
        message: str,
        month: int | None = None,
        offset: int | None = None,
    ):
        self.month = month
        self.offset = offset
        super().__init__(message)


# --- Type Definitions ---
class RawRecord(TypedDict, total=False):
    """Base type for raw API records."""

    data_referencia: str
    codigo_municipio: str
    exercicio_orcamento: str


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


class MonthlyCollector(BaseCollector):
    """
    Abstract base class for collectors that iterate over 12 months.

    Provides shared logic for parallel monthly fetching, reducing
    code duplication across despesas, receitas, and extra-budgetary collectors.
    """

    # Subclasses should override this with a descriptive name for logging
    collector_name: str = "Monthly"

    @abstractmethod
    def _fetch_month(self, municipio_id: str, year: int, month: int) -> list[dict]:
        """
        Fetch data for a single month. Must be implemented by subclasses.

        Args:
            municipio_id: Municipality ID.
            year: Fiscal year.
            month: Month number (1-12).

        Returns:
            List of records for that month.
        """
        pass

    @abstractmethod
    def _save_all(self, all_records: list[dict], municipio_id: str, year: int) -> int:
        """
        Save all collected records to the database. Must be implemented by subclasses.

        Args:
            all_records: All records collected across months.
            municipio_id: Municipality ID.
            year: Fiscal year.

        Returns:
            Number of records saved.
        """
        pass

    def run(self, municipio_id: str, year: int) -> int:
        """
        Run the collection for a municipality and year.

        Fetches all 12 months in parallel and saves them.

        Returns:
            Total number of records collected.
        """
        logger.info(">>> Starting %s - Parallel Mode", self.collector_name)

        all_records = self._fetch_all_months_parallel(municipio_id, year)

        if not all_records:
            logger.info("%s: No records found.", self.collector_name)
            return 0

        total = self._save_all(all_records, municipio_id, year)
        logger.info("%s completed: %d records.", self.collector_name, total)
        return total

    def _fetch_all_months_parallel(self, municipio_id: str, year: int) -> list[dict]:
        """
        Fetch all 12 months in parallel using thread pool.

        Returns:
            Flattened list of all records from all months.
        """
        all_records: list[dict] = []

        with ThreadPoolExecutor(max_workers=MAX_MONTH_WORKERS) as executor:
            futures = {
                executor.submit(self._fetch_month, municipio_id, year, month): month
                for month in range(1, 13)
            }

            for future in as_completed(futures):
                month = futures[future]
                try:
                    month_records = future.result()
                    if month_records:
                        all_records.extend(month_records)
                        logger.info(
                            "%s month %02d: %d records",
                            self.collector_name,
                            month,
                            len(month_records),
                        )
                except APIFetchError as e:
                    logger.error(
                        "API error fetching %s month %d: %s",
                        self.collector_name,
                        month,
                        e,
                    )
                except Exception:
                    logger.exception(
                        "Unexpected error fetching %s month %d",
                        self.collector_name,
                        month,
                    )

        return all_records
