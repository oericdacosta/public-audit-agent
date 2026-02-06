"""
ETL Main Orchestrator.

Coordinates the collection of public audit data from TCE APIs using
dynamic endpoint discovery.
"""

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.etl.client import TCEClient
from src.etl.collectors.despesas import ExpensesCollector
from src.etl.collectors.extra_orcamentaria import (
    DespesaExtraOrcamentariaCollector,
    ReceitaExtraOrcamentariaCollector,
)
from src.etl.collectors.generic import GenericCollector
from src.etl.collectors.licitacoes import LicitacoesCollector
from src.etl.collectors.receitas import RevenueCollector
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


def process_task(
    metadata_mgr: ETLMetadataManager,
    municipality_id: str,
    year: int,
    source_key: str,
    collector: Any,
) -> str:
    """Execute a single ETL task for a (Year, Source) pair."""
    process_id = f"{source_key.upper()}:{year}"

    # Check Idempotency
    current_status = metadata_mgr.get_status(municipality_id, year, source_key)
    if current_status == "COMPLETED":
        return f"⏭️  Skipped {process_id} (Already Completed)"

    # Start
    metadata_mgr.update_status(municipality_id, year, source_key, "STARTED")
    try:
        logger.info("🚀 Starting %s", process_id)
        count = collector.run(municipality_id, year)

        # Success
        metadata_mgr.update_status(
            municipality_id, year, source_key, "COMPLETED", count
        )
        return f"✅ Finished {process_id} ({count} items)"

    except Exception as e:
        logger.error("Failed %s: %s", process_id, e)
        metadata_mgr.update_status(municipality_id, year, source_key, "FAILED")
        return f"⚠️ Failed {process_id}: {str(e)}"


def _create_specialized_collectors(
    db_manager: DatabaseManager, client: TCEClient
) -> dict[Endpoint, Any]:
    """Create specialized collectors that need custom processing logic."""
    return {
        Endpoint.LICITACOES: LicitacoesCollector(
            db_manager, client, Endpoint.LICITACOES
        ),
        Endpoint.CONTRATOS: LicitacoesCollector(db_manager, client, Endpoint.CONTRATOS),
        Endpoint.CONTRATADOS: LicitacoesCollector(
            db_manager, client, Endpoint.CONTRATADOS
        ),
        Endpoint.ITENS_LICITACOES: LicitacoesCollector(
            db_manager, client, Endpoint.ITENS_LICITACOES
        ),
        Endpoint.LICITANTES: LicitacoesCollector(
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


def run_etl(municipality_id: str | None = None, manual_year: str | None = None) -> None:
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
        current_year = datetime.now().year
        lookback = settings.get("audit", {}).get("data_retention_years", 5)
        years = list(range(current_year, current_year - lookback, -1))

    logger.info("--- STARTING AUTOMATED BATCH ETL ---")
    logger.info("Municipality: %s", municipality_id)
    logger.info("Years Window: %s", years)

    db_manager = DatabaseManager()
    db_manager.initialize_schema()
    client = TCEClient()
    metadata_mgr = ETLMetadataManager(db_manager)

    # Create specialized collectors
    specialized_collectors = _create_specialized_collectors(db_manager, client)

    tasks = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        for year in years:
            for endpoint in Endpoint:
                # Skip endpoints without table mapping
                if not endpoint.table_name:
                    logger.warning(
                        "Endpoint %s has no mapped table. Skipping.", endpoint.name
                    )
                    continue

                # Resolve collector strategy
                if endpoint in SPECIALIZED_ENDPOINTS:
                    collector = specialized_collectors[endpoint]
                else:
                    collector = GenericCollector(db_manager, client, endpoint)

                tasks.append(
                    executor.submit(
                        process_task,
                        metadata_mgr,
                        municipality_id,
                        year,
                        endpoint.table_name,
                        collector,
                    )
                )

        for future in as_completed(tasks):
            result = future.result()
            logger.info(result)

    logger.info("Batch Collection Cycle Finished.")


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="CivicAudit Professional ETL")
    parser.add_argument("--municipality", help="Override municipality code (e.g. 162)")
    parser.add_argument("--year", help="Override Rolling Window with single year")

    args = parser.parse_args()
    run_etl(args.municipality, args.year)
