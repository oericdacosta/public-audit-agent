import argparse
import logging
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import get_settings
from .client import TCEClient
from .collectors.despesas import ExpensesCollector
from .collectors.licitacoes import TendersCollector
from .collectors.receitas import RevenueCollector
from .database import DatabaseManager

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/etl.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_sync_status(db_manager, municipality_id, year, source):
    """
    Checks if a specific year/source has been successfully ingested.
    Returns: 'COMPLETED' or None
    """
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT status FROM etl_metadata 
            WHERE municipality_id = ? AND year = ? AND source = ?
            """,
            (municipality_id, year, source),
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        # Table might not exist yet if schema init failed
        return None
    finally:
        conn.close()


def update_sync_status(db_manager, municipality_id, year, source, status, count=0):
    """
    Updates the execution state in the database.
    """
    conn = db_manager.get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO etl_metadata 
            (municipio_id, year, source, status, record_count, last_updated)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (municipality_id, year, source, status, count),
        )
        conn.commit()
    finally:
        conn.close()


def process_task(db_manager, client, municipality_id, year, source_key, collector):
    """
    Executes a single ETL task for a (Year, Source) pair.
    Updates metadata status accordingly.
    """
    process_id = f"{source_key.upper()}:{year}"
    
    # Check Idempotency
    current_status = get_sync_status(db_manager, municipality_id, year, source_key)
    if current_status == "COMPLETED":
        return f"⏭️  Skipped {process_id} (Already Completed)"

    # Start
    update_sync_status(db_manager, municipality_id, year, source_key, "STARTED")
    try:
        logger.info(f"🚀 Starting {process_id}")
        count = collector.run(municipality_id, year)
        
        # Success
        update_sync_status(db_manager, municipality_id, year, source_key, "COMPLETED", count)
        return f"✅ Finished {process_id} ({count} items)"
    
    except Exception as e:
        logger.error(f"Failed {process_id}: {e}")
        update_sync_status(db_manager, municipality_id, year, source_key, "FAILED")
        return f"⚠️ Failed {process_id}: {str(e)}"


def run_etl(municipality_id=None, manual_year=None):
    settings = get_settings()
    
    # 1. Resolve Parameters
    if not municipality_id:
        municipality_id = settings.get("audit", {}).get("city_code")

    # Dynamic Rolling Window Logic
    if manual_year:
        years = [int(manual_year)]
    else:
        current_year = datetime.now().year
        lookback = settings.get("audit", {}).get("data_retention_years", 5) # Default 5 if missing
        years = list(range(current_year, current_year - lookback, -1))

    # Data Sources
    # Only using stable sources for now
    data_sources = ["licitacoes", "despesas", "receitas"]
    if "contratos" in settings.get("audit", {}).get("data_sources", []):
         data_sources.append("contratos")
    if "notas_fiscais" in settings.get("audit", {}).get("data_sources", []):
         data_sources.append("notas_fiscais")

    logger.info(f"--- STARTING PROFESSIONAL BATCH ETL ---")
    logger.info(f"Municipality: {municipality_id}")
    logger.info(f"Years Window: {years}")
    logger.info(f"Sources: {data_sources}")

    # 2. Infra Init
    db_manager = DatabaseManager()
    db_manager.initialize_schema()
    client = TCEClient()

    # 3. Collector Map
    # Import here to avoid circulars if moved to top
    from .collectors.despesas import ExpensesCollector
    from .collectors.licitacoes import TendersCollector
    from .collectors.receitas import RevenueCollector
    # from .collectors.contratos import ContractsCollector
    # from .collectors.notas import InvoicesCollector

    collector_map = {
        "licitacoes": TendersCollector(db_manager, client),
        "despesas": ExpensesCollector(db_manager, client),
        "receitas": RevenueCollector(db_manager, client),
        # Assuming Contratos/Notas are stable now, add them if imported
        # "contratos": ContractsCollector(db_manager, client),
        # "notas_fiscais": InvoicesCollector(db_manager, client)
    }

    # 4. Parallel Execution with Idempotency
    tasks = []
    
    # Separate DB manager per thread is safer slightly, but SQLite is thread-safe with WAL
    # We pass the shared db_manager but inside it creates fresh connections
    
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
                        collector
                    )
                )

        # Monitor execution
        for future in as_completed(tasks):
            result = future.result()
            logger.info(result)

    logger.info("Batch Collection Cycle Finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CivicAudit Professional ETL")
    parser.add_argument(
        "--municipality", help="Override municipality code (e.g. 162)"
    )
    # Manual override for testing specific years
    parser.add_argument("--year", help="Override Rolling Window with single year")

    args = parser.parse_args()
    run_etl(args.municipality, args.year)
