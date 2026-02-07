"""
Base Collector.

Abstract base class for ETL data collectors.
Uses Parquet for ultra-fast DuckDB inserts with UPSERT support.
"""

import asyncio
import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import pandas as pd

if TYPE_CHECKING:
    from src.etl.client import AsyncTCEClient
    from src.etl.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


# --- Constants ---
MAX_MONTH_WORKERS = 12  # One thread per month
MAX_PAGE_WORKERS = 12  # Threads for pagination within a month


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
        client: "AsyncTCEClient",
    ) -> None:
        """
        Initialize the collector with database and API client.

        Args:
            db_manager: Database manager instance.
            client: AsyncTCE API client instance.
        """
        self.db_manager = db_manager
        self.client = client

    @abstractmethod
    async def run(self, municipio_id: str, year: int) -> int:
        """
        Execute the collection process for a municipality and year.

        Args:
            municipio_id: Municipality identifier.
            year: Fiscal year to collect.

        Returns:
            Number of records collected.
        """
        pass

    async def bulk_upsert(
        self,
        table: str,
        columns: list[str],
        records: list[tuple],
        update_columns: list[str] | None = None,
    ) -> int:
        """
        Insert records using Parquet with UPSERT (ON CONFLICT DO UPDATE).
        Executes in a thread pool to avoid blocking the event loop.
        """
        if not records:
            return 0

        # Offload blocking pandas/duckdb operations to a thread
        return await asyncio.to_thread(
            self._bulk_upsert_sync, table, columns, records, update_columns
        )

    def _bulk_upsert_sync(
        self,
        table: str,
        columns: list[str],
        records: list[tuple],
        update_columns: list[str] | None = None,
    ) -> int:
        """Synchronous implementation of bulk_upsert."""
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

            with self.db_manager.get_connection() as conn:
                conn.execute(sql)
                conn.commit()

            logger.debug("Upserted %d records into %s via Parquet", len(records), table)
            return len(records)

        finally:
            # Cleanup temp file
            Path(parquet_path).unlink(missing_ok=True)

    async def bulk_insert(
        self, table: str, columns: list[str], records: list[tuple]
    ) -> int:
        """
        Legacy method - redirects to bulk_upsert for backward compatibility.
        """
        return await self.bulk_upsert(table, columns, records)


class MonthlyCollector(BaseCollector):
    """
    Abstract base class for collectors that iterate over 12 months.

    Provides shared logic for parallel monthly fetching, reducing
    code duplication across despesas, receitas, and extra-budgetary collectors.
    """

    # Subclasses should override this with a descriptive name for logging
    collector_name: str = "Monthly"

    @abstractmethod
    async def _fetch_month(
        self, municipio_id: str, year: int, month: int
    ) -> list[dict]:
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
    async def _save_all(
        self, all_records: list[dict], municipio_id: str, year: int
    ) -> int:
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

    async def run(self, municipio_id: str, year: int) -> int:
        """
        Run the collection for a municipality and year.

        Fetches all 12 months concurrently.
        """
        logger.info(">>> Starting %s - Async Concurrent Mode", self.collector_name)

        all_records = await self._fetch_all_months_concurrent(municipio_id, year)

        if not all_records:
            logger.info("%s: No records found.", self.collector_name)
            return 0

        total = await self._save_all(all_records, municipio_id, year)
        logger.info("%s completed: %d records.", self.collector_name, total)
        return total

    async def _fetch_all_months_concurrent(
        self, municipio_id: str, year: int
    ) -> list[dict]:
        """
        Fetch all 12 months concurrently using asyncio.gather.
        """
        all_records: list[dict] = []

        tasks = [self._fetch_month(municipio_id, year, month) for month in range(1, 13)]

        # Run all months in parallel
        # return_exceptions=True so one failure doesn't crash everything immediately
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for month_idx, result in enumerate(results):
            month = month_idx + 1
            if isinstance(result, Exception):
                logger.error(
                    "%s:%d month %d failed: %s",
                    self.collector_name,
                    year,
                    month,
                    result,
                )
            elif isinstance(result, list):
                all_records.extend(result)
            elif result is None:
                pass  # Handle None return if applicable
        logger.info(
            "%s fetched total %d records (all months merged)",
            self.collector_name,
            len(all_records),
        )
        return all_records
