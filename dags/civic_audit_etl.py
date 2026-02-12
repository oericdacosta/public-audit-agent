"""
CivicAudit ETL DAG.

Orquestra a coleta de dados públicos do TCE-CE para o Data Warehouse DuckDB.
Cada ano é uma task que executa ``run_etl()`` do ``src/etl/main.py``, que
internamente roda todos os 23 endpoints com concorrência async (semaphore=5),
rate limiting e circuit breaker.

Pool ``etl_pool`` (1 slot) garante um ano por vez (DuckDB single-writer).
Anos são calculados em parse-time a partir do ``config.yaml``.

Fluxo::

    init_schema → [run_year_2025, run_year_2024, …, run_year_2016] → validate_counts
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from airflow.decorators import dag, task
from common.callbacks import on_dag_failure, on_task_failure

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parse-time helper — reads config.yaml directly (no src.* imports)
# ---------------------------------------------------------------------------
def _get_years() -> list[int]:
    candidates = [
        Path(__file__).parent.parent / "config.yaml",
        Path("/opt/airflow/app/config.yaml"),
    ]
    for config_path in candidates:
        if config_path.exists():
            break
    else:
        raise FileNotFoundError(f"config.yaml not found in: {candidates}")

    with open(config_path) as f:
        config = yaml.safe_load(f)
    lookback = config.get("audit", {}).get("data_retention_years", 10)
    current_year = datetime.now().year - 1
    return list(range(current_year, current_year - lookback, -1))


# ---------------------------------------------------------------------------
# Default args
# ---------------------------------------------------------------------------
default_args = {
    "owner": "civic-audit",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(hours=2),
    "on_failure_callback": on_task_failure,
}


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
@dag(
    dag_id="civic_audit_etl",
    default_args=default_args,
    description="ETL de dados públicos do TCE-CE para DuckDB",
    schedule="0 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["etl", "tce", "civic-audit"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
    doc_md=__doc__,
)
def civic_audit_etl():
    """Pipeline ETL do CivicAudit."""

    @task()
    def init_schema() -> str:
        """Inicializa o schema do DuckDB (idempotente)."""
        from src.etl.db_manager import DatabaseManager

        db = DatabaseManager()
        db.initialize_schema()
        logger.info("Schema inicializado com sucesso")
        return "schema_ready"

    @task(
        pool="etl_pool",
        max_active_tis_per_dag=1,
        execution_timeout=timedelta(hours=2),
    )
    def run_year_etl(year: int) -> dict:
        """
        Executa o ETL completo para um ano específico.

        Chama ``run_etl()`` que internamente:
        - Roda todos os 23 endpoints com asyncio.gather (concorrência real)
        - Prioriza dimensões → simples → pesados
        - Idempotência via etl_metadata
        - Rate limiting (semaphore) e circuit breaker
        """
        from src.config import get_settings
        from src.etl.main import run_etl

        settings = get_settings()
        municipality = str(settings.get("audit", {}).get("city_code", "162"))

        logger.info("Iniciando ETL para ano %d (municipio %s)", year, municipality)

        start_time = time.time()
        asyncio.run(run_etl(municipality, str(year)))
        elapsed = round(time.time() - start_time, 1)

        logger.info("Ano %d concluido em %ss", year, elapsed)

        return {"year": year, "elapsed_seconds": elapsed, "status": "completed"}

    @task(trigger_rule="all_done")
    def validate_counts(results: list[dict]) -> dict:
        """
        Valida contagens no banco após ETL.

        Executa independente de falhas upstream (trigger_rule=all_done)
        para sempre gerar um relatório de status.
        """
        from src.etl.db_manager import DatabaseManager

        db = DatabaseManager()
        summary: dict[str, object] = {}
        total = 0

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                )
                tables = [row[0] for row in cursor.fetchall()]

                for table in sorted(tables):
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                        count = cursor.fetchone()[0]
                        summary[table] = count
                        total += count
                    except Exception:
                        summary[table] = "ERROR"
        except Exception as e:
            logger.error("Erro ao validar contagens: %s", e)
            return {"error": str(e)}

        summary["_TOTAL"] = total
        logger.info("Validacao - Total de registros: %d", total)

        completed = [
            r for r in results if isinstance(r, dict) and r.get("status") == "completed"
        ]
        failed = [
            r for r in results if isinstance(r, dict) and r.get("status") != "completed"
        ]
        logger.info("Resumo: %d anos OK, %d falhas", len(completed), len(failed))

        return summary

    # ------------------------------------------------------------------
    # Pipeline: init_schema → [run_year_etl per year] → validate_counts
    # ------------------------------------------------------------------
    schema = init_schema()
    years = _get_years()
    etl_results = run_year_etl.expand(year=years)
    validation = validate_counts(etl_results)

    schema >> etl_results >> validation


# Instantiate the DAG
civic_audit_etl()
