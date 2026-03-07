"""
CivicAudit ETL DAGs — Historical and Recent.

Dois DAGs com frequências diferentes:

**civic_audit_etl_historical** (anual, 1º de janeiro às 3h):
    Processa todos os anos históricos (current_year-2 até current_year-retention).
    Usa idempotência via etl_metadata — em regime estável é quase no-op.
    Útil na configuração inicial e recuperação de desastres.

    Fluxo::
        [preflight_duckdb ‖ sensor_tce_api] → init_schema
            → [run_year_etl per historical year] → validate_counts → trigger_dbt

**civic_audit_etl_recent** (mensal, 1º de cada mês às 3h):
    Reseta e re-coleta os 2 anos mais recentes para capturar publicações
    tardias da TCE-CE.

    Fluxo::
        [preflight_duckdb ‖ sensor_tce_api] → init_schema
            → reset_recent_metadata → [run_year_etl for 2 recent years]
            → validate_counts → trigger_dbt

Pool ``etl_pool`` (1 slot) garante DuckDB single-writer em todos os tasks
que abrem conexão de escrita.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sensors.base import PokeReturnValue
from airflow.utils.trigger_rule import TriggerRule
from common.callbacks import on_dag_failure, on_task_failure

logger = logging.getLogger(__name__)

_POOL = "etl_pool"


# ---------------------------------------------------------------------------
# Parse-time helpers
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    candidates = [
        Path(__file__).parent.parent / "config.yaml",
        Path("/opt/airflow/app/config.yaml"),
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(f"config.yaml not found in: {candidates}")


def _get_municipality() -> str:
    return str(_load_config().get("audit", {}).get("city_code", "162"))


def _get_recent_years() -> list[int]:
    """2 anos mais recentes com dados: current_year-2 e current_year-1.

    A TCE-CE publica dados até o ano anterior (current_year-1).
    Os 2 últimos anos publicados ainda recebem atualizações tardias
    e são re-coletados mensalmente pelo DAG recent.
    Ex: em 2026 → [2024, 2025].
    """
    current_year = datetime.now().year
    return [current_year - 2, current_year - 1]


def _get_historical_years() -> list[int]:
    """Anos consolidados: current_year-3 até current_year-retention.

    Anos que não recebem mais atualizações da TCE-CE — coletados
    apenas uma vez por ano via etl_metadata (idempotência).
    Ex: em 2026 → [2023, 2022, ..., 2016].
    """
    config = _load_config()
    retention = config.get("audit", {}).get("data_retention_years", 10)
    current_year = datetime.now().year
    return list(range(current_year - 3, current_year - retention - 1, -1))


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
# DAG: civic_audit_etl_historical (anual)
# ---------------------------------------------------------------------------


@dag(
    dag_id="civic_audit_etl_historical",
    default_args=default_args,
    description="ETL histórico: anos consolidados via idempotência (etl_metadata)",
    schedule="0 3 1 1 *",  # 1º de janeiro às 3h
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["etl", "tce", "civic-audit", "historical"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
    doc_md=__doc__,
)
def civic_audit_etl_historical():
    """Pipeline ETL histórico do CivicAudit."""

    @task(retries=0, execution_timeout=timedelta(minutes=2))
    def preflight_duckdb() -> str:
        """Verifica que o DuckDB está acessível antes de iniciar o ETL."""
        import duckdb

        duckdb.connect(":memory:").execute("SELECT 1")
        logger.info("DuckDB preflight check passed")
        return "ok"

    @task.sensor(
        poke_interval=5 * 60,
        timeout=30 * 60,
        mode="reschedule",
        retries=0,
    )
    def sensor_tce_api() -> PokeReturnValue:
        """Aguarda API TCE-CE responder antes de iniciar coleta."""
        import requests

        try:
            url = "https://api-dados-abertos.tce.ce.gov.br/municipios"
            r = requests.get(url, timeout=10, params={"quantidade": 1})
            is_up = r.status_code < 500
            logger.info("TCE-CE API status: %d (is_up=%s)", r.status_code, is_up)
            return PokeReturnValue(is_done=is_up)
        except Exception as e:
            logger.warning("TCE-CE API unreachable: %s", e)
            return PokeReturnValue(is_done=False)

    @task(pool=_POOL)
    def init_schema() -> str:
        """Inicializa o schema DuckDB (idempotente)."""
        from src.etl.db_manager import DatabaseManager

        db = DatabaseManager()
        db.initialize_schema()
        logger.info("Schema initialized")
        return "schema_ready"

    @task(
        pool=_POOL,
        max_active_tis_per_dag=1,
        execution_timeout=timedelta(hours=2),
    )
    def run_year_etl(year: int) -> dict:
        """Executa ETL completo para um ano. Idempotente via etl_metadata."""
        import asyncio

        from src.config import get_settings
        from src.etl.main import run_etl

        settings = get_settings()
        municipality = str(settings.get("audit", {}).get("city_code", "162"))
        logger.info("Starting ETL for year %d (municipality %s)", year, municipality)
        start = time.time()
        asyncio.run(run_etl(municipality, str(year)))
        elapsed = round(time.time() - start, 1)
        logger.info("Year %d done in %ss", year, elapsed)
        return {"year": year, "elapsed_seconds": elapsed, "status": "completed"}

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def validate_counts(results: list[dict]) -> dict:
        """Valida contagens após ETL. Roda mesmo se alguns anos falharam."""
        from src.etl.db_manager import DatabaseManager

        db = DatabaseManager()
        summary: dict = {}
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
            logger.error("Validation error: %s", e)
            return {"error": str(e)}

        summary["_TOTAL"] = total
        completed = [
            r for r in results if isinstance(r, dict) and r.get("status") == "completed"
        ]
        failed = [
            r for r in results if isinstance(r, dict) and r.get("status") != "completed"
        ]
        logger.info("ETL summary: %d years OK, %d failed", len(completed), len(failed))
        return summary

    # --- Pipeline ---
    preflight = preflight_duckdb()
    sensor = sensor_tce_api()
    schema = init_schema()
    years = _get_historical_years()
    etl_results = run_year_etl.expand(year=years)
    counts = validate_counts(etl_results)

    trigger_recent = TriggerDagRunOperator(
        task_id="trigger_etl_recent",
        trigger_dag_id="civic_audit_etl_recent",
        wait_for_completion=True,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_pipeline",
        trigger_dag_id="civic_audit_dbt",
        wait_for_completion=False,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    (
        [preflight, sensor]
        >> schema
        >> etl_results
        >> counts
        >> trigger_recent
        >> trigger_dbt
    )


# ---------------------------------------------------------------------------
# DAG: civic_audit_etl_recent (mensal)
# ---------------------------------------------------------------------------


@dag(
    dag_id="civic_audit_etl_recent",
    default_args=default_args,
    description="ETL recente: reseta e re-coleta os 2 anos mais recentes",
    schedule="0 3 1 * *",  # 1º de cada mês às 3h
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["etl", "tce", "civic-audit", "recent"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
)
def civic_audit_etl_recent():
    """Pipeline ETL recente do CivicAudit."""

    @task(retries=0, execution_timeout=timedelta(minutes=2))
    def preflight_duckdb() -> str:
        """Verifica que o DuckDB está acessível antes de iniciar o ETL."""
        import duckdb

        duckdb.connect(":memory:").execute("SELECT 1")
        logger.info("DuckDB preflight check passed")
        return "ok"

    @task.sensor(
        poke_interval=5 * 60,
        timeout=30 * 60,
        mode="reschedule",
        retries=0,
    )
    def sensor_tce_api() -> PokeReturnValue:
        """Aguarda API TCE-CE responder antes de iniciar coleta."""
        import requests

        try:
            url = "https://api-dados-abertos.tce.ce.gov.br/municipios"
            r = requests.get(url, timeout=10, params={"quantidade": 1})
            is_up = r.status_code < 500
            logger.info("TCE-CE API status: %d (is_up=%s)", r.status_code, is_up)
            return PokeReturnValue(is_done=is_up)
        except Exception as e:
            logger.warning("TCE-CE API unreachable: %s", e)
            return PokeReturnValue(is_done=False)

    @task(pool=_POOL)
    def init_schema() -> str:
        """Inicializa o schema DuckDB (idempotente)."""
        from src.etl.db_manager import DatabaseManager

        db = DatabaseManager()
        db.initialize_schema()
        logger.info("Schema initialized")
        return "schema_ready"

    @task(pool=_POOL)
    def reset_recent_metadata() -> str:
        """
        Deleta entradas etl_metadata dos 2 anos recentes para forçar re-coleta.

        Necessário para capturar publicações tardias da TCE-CE que chegam
        ao longo do ano. Anos históricos não são afetados.
        """
        from src.etl.db_manager import DatabaseManager

        municipality = _get_municipality()
        years = _get_recent_years()
        db = DatabaseManager()
        with db.get_connection() as conn:
            for year in years:
                conn.execute(
                    "DELETE FROM etl_metadata WHERE municipio_id = ? AND year = ?",
                    [municipality, year],
                )
            conn.commit()
        logger.info(
            "Reset etl_metadata for years %s (municipality %s)", years, municipality
        )
        return f"reset:{years}"

    @task(
        pool=_POOL,
        max_active_tis_per_dag=1,
        execution_timeout=timedelta(hours=2),
    )
    def run_year_etl(year: int) -> dict:
        """Executa ETL completo para um ano."""
        import asyncio

        from src.config import get_settings
        from src.etl.main import run_etl

        settings = get_settings()
        municipality = str(settings.get("audit", {}).get("city_code", "162"))
        logger.info("Starting ETL for year %d (municipality %s)", year, municipality)
        start = time.time()
        asyncio.run(run_etl(municipality, str(year)))
        elapsed = round(time.time() - start, 1)
        logger.info("Year %d done in %ss", year, elapsed)
        return {"year": year, "elapsed_seconds": elapsed, "status": "completed"}

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def validate_counts(results: list[dict]) -> dict:
        """Valida contagens após ETL."""
        from src.etl.db_manager import DatabaseManager

        db = DatabaseManager()
        summary: dict = {}
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
            logger.error("Validation error: %s", e)
            return {"error": str(e)}

        summary["_TOTAL"] = total
        completed = [
            r for r in results if isinstance(r, dict) and r.get("status") == "completed"
        ]
        failed = [
            r for r in results if isinstance(r, dict) and r.get("status") != "completed"
        ]
        logger.info("ETL summary: %d years OK, %d failed", len(completed), len(failed))
        return summary

    # --- Pipeline ---
    preflight = preflight_duckdb()
    sensor = sensor_tce_api()
    schema = init_schema()
    reset = reset_recent_metadata()
    years = _get_recent_years()
    etl_results = run_year_etl.expand(year=years)
    counts = validate_counts(etl_results)

    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_pipeline",
        trigger_dag_id="civic_audit_dbt",
        wait_for_completion=False,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    [preflight, sensor] >> schema >> reset >> etl_results >> counts >> trigger_dbt


# Instantiate DAGs
civic_audit_etl_historical()
civic_audit_etl_recent()
