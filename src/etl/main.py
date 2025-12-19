import argparse
import logging
from .database import DatabaseManager
from .client import TCEClient
from .collectors.licitacoes import TendersCollector
from .collectors.despesas import ExpensesCollector
from .collectors.receitas import RevenueCollector

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/etl.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_etl(municipality_id, year):
    # Initialize Core Components
    db_manager = DatabaseManager()
    db_manager.initialize_schema()
    
    client = TCEClient()
    
    # Initialize Collectors
    tenders_collector = TendersCollector(db_manager, client)
    expenses_collector = ExpensesCollector(db_manager, client)
    revenue_collector = RevenueCollector(db_manager, client)
    
    logger.info(f"Starting ETL for Municipality {municipality_id}, Year {year}")
    
    # Pipeline Execution
    tenders_collector.run(municipality_id, year)
    expenses_collector.run(municipality_id, year)
    revenue_collector.run(municipality_id, year)
    
    logger.info("Collection Finished Successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CivicAudit ETL Collector")
    parser.add_argument("--municipality", required=True, help="Municipality code (e.g. 162 for Sobral)")
    parser.add_argument("--year", required=True, help="Budget Year (e.g. 2024)")
    
    args = parser.parse_args()
    run_etl(args.municipality, args.year)
