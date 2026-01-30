"""
ETL Main Orchestrator.

Coordinates the collection of public audit data from TCE APIs.
"""

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import duckdb

from src.config import get_settings

from .client import TCEClient
from .collectors.despesas import ExpensesCollector
from .collectors.licitacoes import TendersCollector
from .collectors.receitas import RevenueCollector
from .db_manager import DatabaseManager

# Logging Configuration
_log_dir = Path(__file__).parent.parent.parent / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_log_dir / "etl.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def get_sync_status(
    db_manager: DatabaseManager, municipality_id: str, year: int, source: str
) -> Optional[str]:
    """
    Check if a specific year/source has been successfully ingested.

    Returns:
        'COMPLETED', 'STARTED', 'FAILED', or None if not found.
    """
    try:
        with db_manager.get_connection() as conn:
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
        # Table might not exist yet if schema init failed
        return None


def update_sync_status(
    db_manager: DatabaseManager,
    municipality_id: str,
    year: int,
    source: str,
    status: str,
    count: int = 0,
) -> None:
    """Update the execution state in the database."""
    with db_manager.get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO etl_metadata
            (municipio_id, year, source, status, record_count, last_updated)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (municipality_id, year, source, status, count),
        )
        conn.commit()


def process_task(
    db_manager: DatabaseManager,
    client: TCEClient,
    municipality_id: str,
    year: int,
    source_key: str,
    collector: Any,
) -> str:
    """
    Execute a single ETL task for a (Year, Source) pair.

    Returns:
        Status message string.
    """
    process_id = f"{source_key.upper()}:{year}"

    # Check Idempotency
    current_status = get_sync_status(db_manager, municipality_id, year, source_key)
    if current_status == "COMPLETED":
        return f"⏭️  Skipped {process_id} (Already Completed)"

    # Start
    update_sync_status(db_manager, municipality_id, year, source_key, "STARTED")
    try:
        logger.info("🚀 Starting %s", process_id)
        count = collector.run(municipality_id, year)

        # Success
        update_sync_status(
            db_manager, municipality_id, year, source_key, "COMPLETED", count
        )
        return f"✅ Finished {process_id} ({count} items)"

    except Exception as e:
        logger.error("Failed %s: %s", process_id, e)
        update_sync_status(db_manager, municipality_id, year, source_key, "FAILED")
        return f"⚠️ Failed {process_id}: {str(e)}"


def run_etl(
    municipality_id: Optional[str] = None, manual_year: Optional[str] = None
) -> None:
    """
    Run the ETL process for a municipality.

    Args:
        municipality_id: Municipality code (e.g., '162'). Uses config if not provided.
        manual_year: Override the rolling window with a specific year.
    """
    settings = get_settings()

    # 1. Resolve Parameters
    if not municipality_id:
        municipality_id = settings.get("audit", {}).get("city_code")

    # Dynamic Rolling Window Logic
    if manual_year:
        years = [int(manual_year)]
    else:
        current_year = datetime.now().year
        lookback = settings.get("audit", {}).get("data_retention_years", 5)
        years = list(range(current_year, current_year - lookback, -1))

    # Data Sources
    data_sources = ["licitacoes", "despesas", "receitas"]
    if "contratos" in settings.get("audit", {}).get("data_sources", []):
        data_sources.append("contratos")
    if "notas_fiscais" in settings.get("audit", {}).get("data_sources", []):
        data_sources.append("notas_fiscais")

    logger.info("--- STARTING PROFESSIONAL BATCH ETL ---")
    logger.info("Municipality: %s", municipality_id)
    logger.info("Years Window: %s", years)
    logger.info("Sources: %s", data_sources)

    # 2. Infra Init
    db_manager = DatabaseManager()
    db_manager.initialize_schema()
    client = TCEClient()

    # 3. Collector Map
    collector_map = {
        "licitacoes": TendersCollector(db_manager, client),
        "despesas": ExpensesCollector(db_manager, client),
        "receitas": RevenueCollector(db_manager, client),
    }

    # 4. Parallel Execution with Idempotency
    tasks = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        for year in years:
            for source_key in data_sources:
                if source_key not in collector_map:
                    continue

                collector = collector_map[source_key]
                tasks.append(
                    executor.submit(
                        process_task,
                        db_manager,
                        client,
                        municipality_id,
                        year,
                        source_key,
                        collector,
                    )
                )

        # Monitor execution
        for future in as_completed(tasks):
            result = future.result()
            logger.info(result)

    logger.info("Batch Collection Cycle Finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CivicAudit Professional ETL")
    parser.add_argument("--municipality", help="Override municipality code (e.g. 162)")
    parser.add_argument("--year", help="Override Rolling Window with single year")

    args = parser.parse_args()
    run_etl(args.municipality, args.year)
