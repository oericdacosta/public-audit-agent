"""
ETL Main Orchestrator.

Coordinates the collection of public audit data from TCE APIs using
dynamic endpoint discovery and AsyncIO for high-performance I/O.
"""

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.etl.client import AsyncTCEClient
from src.etl.collectors.despesas import ExpensesCollector
from src.etl.collectors.extra_orcamentaria import (
    DespesaExtraOrcamentariaCollector,
    ReceitaExtraOrcamentariaCollector,
)
from src.etl.collectors.generic import (
    NO_PARAMS_ENDPOINTS,
    PAGINATED_ENDPOINTS,
    GenericCollector,
)
from src.etl.collectors.receitas import RevenueCollector
from src.etl.collectors.transacoes import TransacoesCollector
from src.etl.db_manager import DatabaseManager
from src.etl.endpoints import Endpoint
from src.etl.metadata import ETLMetadataManager

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure logging for ETL process."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "etl.log"),
            logging.StreamHandler(),
        ],
    )


# Specialized collectors that need custom processing logic
SPECIALIZED_ENDPOINTS: frozenset[Endpoint] = frozenset(
    {
        Endpoint.LICITACOES,
        Endpoint.DESPESAS,
        Endpoint.RECEITAS,
        Endpoint.BALANCETE_DESPESA_EXTRA,
        Endpoint.BALANCETE_RECEITA_EXTRA,
        Endpoint.CONTRATOS,
        Endpoint.CONTRATADOS,
        Endpoint.ITENS_LICITACOES,
        Endpoint.LICITANTES,
    }
)


async def process_task(
    metadata_mgr: ETLMetadataManager,
    municipality_id: str,
    year: int,
    source_key: str,
    collector: Any,
) -> str:
    """Execute a single ETL task for a (Year, Source) pair."""
    process_id = f"{source_key.upper()}:{year}"

    # Check Idempotency
    # Run sync DB check in thread
    current_status = await asyncio.to_thread(
        metadata_mgr.get_status, municipality_id, year, source_key
    )
    if current_status == "COMPLETED":
        return f"⏭️  Skipped {process_id} (Already Completed)"

    # Start
    await asyncio.to_thread(
        metadata_mgr.update_status, municipality_id, year, source_key, "STARTED"
    )
    try:
        logger.info("🚀 Starting %s", process_id)
        # Run async collector
        count = await collector.run(municipality_id, year)

        # Success
        await asyncio.to_thread(
            metadata_mgr.update_status,
            municipality_id,
            year,
            source_key,
            "COMPLETED",
            count,
        )
        return f"✅ Finished {process_id} ({count} items)"

    except Exception as e:
        logger.error("Failed %s: %s", process_id, e)
        await asyncio.to_thread(
            metadata_mgr.update_status, municipality_id, year, source_key, "FAILED"
        )
        return f"⚠️ Failed {process_id}: {str(e)}"


def _create_specialized_collectors(
    db_manager: DatabaseManager, client: AsyncTCEClient
) -> dict[Endpoint, Any]:
    return {
        Endpoint.LICITACOES: TransacoesCollector(
            db_manager, client, Endpoint.LICITACOES
        ),
        Endpoint.CONTRATOS: TransacoesCollector(db_manager, client, Endpoint.CONTRATOS),
        Endpoint.CONTRATADOS: TransacoesCollector(
            db_manager, client, Endpoint.CONTRATADOS
        ),
        Endpoint.ITENS_LICITACOES: TransacoesCollector(
            db_manager, client, Endpoint.ITENS_LICITACOES
        ),
        Endpoint.LICITANTES: TransacoesCollector(
            db_manager, client, Endpoint.LICITANTES
        ),
        Endpoint.DESPESAS: ExpensesCollector(db_manager, client),
        Endpoint.RECEITAS: RevenueCollector(db_manager, client),
        Endpoint.BALANCETE_DESPESA_EXTRA: DespesaExtraOrcamentariaCollector(
            db_manager, client
        ),
        Endpoint.BALANCETE_RECEITA_EXTRA: ReceitaExtraOrcamentariaCollector(
            db_manager, client
        ),
    }


async def run_etl(
    municipality_id: str | None = None, manual_year: str | None = None
) -> None:
    """
    Run the ETL process for a municipality using dynamic endpoint discovery.

    Args:
        municipality_id: Municipality code (e.g., '162'). Uses config if not provided.
        manual_year: Override the rolling window with a specific year.
    """
    settings = get_settings()

    if not municipality_id:
        municipality_id = settings.get("audit", {}).get("city_code")

    if not municipality_id:
        raise ValueError("Municipality ID must be provided via args or config.")

    if manual_year:
        years = [int(manual_year)]
    else:
        current_year = datetime.now().year - 1
        lookback = settings.get("audit", {}).get("data_retention_years", 5)
        years = list(range(current_year, current_year - lookback, -1))

    logger.info("--- STARTING AUTOMATED BATCH ETL (ASYNC) ---")
    logger.info("Municipality: %s", municipality_id)
    logger.info("Years Window: %s", years)

    db_manager = DatabaseManager()
    db_manager.initialize_schema()

    # Initialize Async Client
    client = AsyncTCEClient()

    metadata_mgr = ETLMetadataManager(db_manager)

    try:
        # Create specialized collectors
        specialized_collectors = _create_specialized_collectors(db_manager, client)

        # Build ordered task list: dimension tables first, then simple, then heavy
        ordered_tasks: list[tuple[int, int, Endpoint]] = []
        for year in years:
            for endpoint in Endpoint:
                if not endpoint.table_name:
                    continue
                # Priority: 0 = no-param lookups, 1 = simple endpoints,
                # 2 = specialized/paginated (heaviest)
                if endpoint in NO_PARAMS_ENDPOINTS:
                    priority = 0
                elif (
                    endpoint not in SPECIALIZED_ENDPOINTS
                    and endpoint not in PAGINATED_ENDPOINTS
                ):
                    priority = 1
                else:
                    priority = 2
                ordered_tasks.append((priority, year, endpoint))

        ordered_tasks.sort(key=lambda t: (t[0], t[1]))

        # Execute tasks
        # We can execute all of them concurrently, honoring the semaphore in the client.
        # Or we can batch them by priority if dependencies exist.
        # Assuming no strict data dependencies between these tasks
        # for now (independent tables).

        tasks = []
        for _priority, year, endpoint in ordered_tasks:
            if endpoint in SPECIALIZED_ENDPOINTS:
                collector = specialized_collectors[endpoint]
            else:
                collector = GenericCollector(db_manager, client, endpoint)

            tasks.append(
                process_task(
                    metadata_mgr,
                    municipality_id,
                    year,
                    endpoint.table_name,
                    collector,
                )
            )

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("Task failed with exception: %s", result)
            else:
                logger.info(result)

    finally:
        await client.close()

    logger.info("Batch Collection Cycle Finished.")


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="CivicAudit Professional ETL")
    parser.add_argument("--municipality", help="Override municipality code (e.g. 162)")
    parser.add_argument("--year", help="Override Rolling Window with single year")

    args = parser.parse_args()

    # Check config for defaults
    settings = get_settings()
    default_municipality = settings.get("audit", {}).get("city_code")
    if not default_municipality:
        raise ValueError("City code not found in config.yaml")

    # Determine years to process
    target_municipality = args.municipality or str(default_municipality)
    target_year = args.year

    years = []
    if target_year:
        years = [int(target_year)]
    else:
        lookback_years = settings.get("audit", {}).get("data_retention_years", 10)
        current_date_year = datetime.now().year

        # Start from the last full year (current_year - 1)
        start_year = current_date_year - 1

        years = list(range(start_year, start_year - lookback_years, -1))

    logger.info("Years Window to Process: %s", years)

    # --- SEQUENTIAL YEAR PROCESSING ---
    # We process each year as a separate async event loop execution
    # This mimics Airflow task behavior (one task per year) and avoids WAF blocks.
    for year in years:
        logger.info(f"=== Starting ETL for Year {year} ===")
        try:
            asyncio.run(run_etl(target_municipality, str(year)))
            logger.info(f"✅ Year {year} completed successfully.")
            # Optional: Add a small sleep between years to be extra safe
            import time

            time.sleep(2)
        except Exception as e:
            logger.error(f"❌ Year {year} failed: {e}")
            # Continue to next year even if one fails
            continue

    logger.info("Batch Collection Cycle Finished.")
