"""
CivicAudit Maintenance DAG.

Manutenção semanal — tarefas de limpeza rodam em paralelo,
depois o CHECKPOINT do DuckDB (exclusivo via pool).

Fluxo::

    [cleanup_docker_orphans ‖ cleanup_airflow_logs
    ‖ cleanup_dbt_artifacts ‖ rotate_etl_log]
        → duckdb_checkpoint

Tarefas:
- ``cleanup_docker_orphans``: remove containers python:3.12-slim parados/expirados
- ``cleanup_airflow_logs``: remove logs Airflow com mais de 30 dias
- ``cleanup_dbt_artifacts``: executa ``dbt clean`` (target/ e dbt_packages/)
- ``rotate_etl_log``: rotaciona logs/etl.log sem retenção configurada
- ``duckdb_checkpoint``: flush do WAL para o arquivo principal (libera espaço)

Schedule: domingos às 2h — antes do ETL (3h), garante espaço em disco.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule
from common.callbacks import on_dag_failure, on_task_failure

logger = logging.getLogger(__name__)

_POOL = "etl_pool"
_APP_DIR = Path("/opt/airflow/app")
_DBT_DIR = _APP_DIR / "dbt"
_AIRFLOW_LOGS_DIR = Path("/opt/airflow/logs")
_ETL_LOG_PATH = _APP_DIR / "logs" / "etl.log"
_LOG_RETENTION_DAYS = 30

default_args = {
    "owner": "civic-audit",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=30),
    "on_failure_callback": on_task_failure,
}


@dag(
    dag_id="civic_audit_maintenance",
    default_args=default_args,
    description="Manutenção semanal: Docker, logs, dbt clean e DuckDB CHECKPOINT",
    schedule="0 2 * * 0",  # Domingos às 2h
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["maintenance", "cleanup", "civic-audit"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
    doc_md=__doc__,
)
def civic_audit_maintenance():
    """Manutenção semanal do CivicAudit."""

    # ------------------------------------------------------------------
    # Fase 1: limpeza paralela (sem pool — sem acesso a DuckDB)
    # ------------------------------------------------------------------

    @task()
    def cleanup_docker_orphans() -> dict:
        """
        Remove containers python:3.12-slim parados (orfãos do sandbox).

        Containers em estado 'exited' com imagem do sandbox podem acumular
        quando o processo do agente é morto com SIGKILL sem executar cleanup().
        Verifica que o warm container ativo não é removido.
        """
        try:
            import docker

            client = docker.from_env(timeout=10)

            # Lista containers exited com a imagem do sandbox
            exited = client.containers.list(
                filters={"ancestor": "python:3.12-slim", "status": "exited"},
                all=True,
            )

            removed = []
            for container in exited:
                try:
                    container.remove(force=False)
                    removed.append(container.short_id)
                    logger.info("Container orfão removido: %s", container.short_id)
                except Exception as e:
                    logger.warning(
                        "Não foi possível remover %s: %s", container.short_id, e
                    )

            logger.info(
                "Docker cleanup: %d container(s) orfão(s) removido(s)", len(removed)
            )
            return {"removed": len(removed), "ids": removed}
        except Exception as e:
            logger.warning(
                "Docker cleanup falhou (Docker pode estar indisponível): %s", e
            )
            return {"removed": 0, "error": str(e)}

    @task()
    def cleanup_airflow_logs() -> dict:
        """
        Remove logs Airflow com mais de LOG_RETENTION_DAYS dias.

        Os logs ficam em /opt/airflow/logs/ organizados por DAG/task/run_id.
        Com execuções diárias, o volume pode crescer rapidamente sem limpeza.
        """
        if not _AIRFLOW_LOGS_DIR.exists():
            return {"removed_files": 0}

        cutoff = datetime.now() - timedelta(days=_LOG_RETENTION_DAYS)
        removed_files = 0
        removed_dirs = 0

        for log_file in _AIRFLOW_LOGS_DIR.rglob("*.log"):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    removed_files += 1
            except Exception as e:
                logger.debug("Erro ao remover %s: %s", log_file, e)

        # Remove diretórios vazios deixados pela limpeza
        for dirpath in sorted(_AIRFLOW_LOGS_DIR.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    dirpath.rmdir()  # Só remove se vazio
                    removed_dirs += 1
                except OSError:
                    pass  # Não está vazio — normal

        logger.info(
            "Airflow log cleanup: %d arquivo(s) e %d dir(s) removido(s) "
            "(retenção: %d dias)",
            removed_files,
            removed_dirs,
            _LOG_RETENTION_DAYS,
        )
        return {"removed_files": removed_files, "removed_dirs": removed_dirs}

    # dbt clean — usa BashOperator (comando CLI)
    dbt_clean = BashOperator(
        task_id="cleanup_dbt_artifacts",
        bash_command=(
            f"cd {_DBT_DIR} && "
            f"cd {_DBT_DIR} && DBT_PROFILES_DIR={_DBT_DIR} dbt clean || true && "
            "echo 'dbt clean concluído'"
        ),
        # `|| true` pois dbt clean pode falhar se target/ não existir
    )

    @task()
    def rotate_etl_log() -> dict:
        """
        Rotaciona logs/etl.log para evitar arquivo crescendo indefinidamente.

        O ETL usa FileHandler sem RotatingFileHandler — sem rotação manual,
        o arquivo pode crescer vários GB por mês com execuções diárias.
        Move para etl.log.YYYYMMDD e cria novo arquivo vazio.
        """
        if not _ETL_LOG_PATH.exists():
            logger.info("etl.log não encontrado — nada a rotacionar")
            return {"rotated": False}

        size_mb = round(_ETL_LOG_PATH.stat().st_size / (1024 * 1024), 1)
        today = datetime.now().strftime("%Y%m%d")
        archive_path = _ETL_LOG_PATH.with_name(f"etl.log.{today}")

        # Move log atual para arquivo datado
        shutil.move(str(_ETL_LOG_PATH), str(archive_path))

        # Cria novo arquivo vazio (para o FileHandler continuar funcionando)
        _ETL_LOG_PATH.touch()

        logger.info(
            "etl.log rotacionado: %.1f MB → %s",
            size_mb,
            archive_path.name,
        )

        # Remove archives com mais de LOG_RETENTION_DAYS dias
        cutoff = datetime.now() - timedelta(days=_LOG_RETENTION_DAYS)
        removed = []
        for archive in _ETL_LOG_PATH.parent.glob("etl.log.*"):
            try:
                date_str = archive.suffix.lstrip(".")
                archive_date = datetime.strptime(date_str, "%Y%m%d")
                if archive_date < cutoff:
                    archive.unlink()
                    removed.append(archive.name)
            except ValueError:
                continue

        return {"rotated": True, "size_mb": size_mb, "old_archives_removed": removed}

    # ------------------------------------------------------------------
    # Fase 2: DuckDB CHECKPOINT (exclusivo via pool, após limpeza)
    # ------------------------------------------------------------------

    @task(pool=_POOL, execution_timeout=timedelta(minutes=10))
    def duckdb_checkpoint() -> dict:
        """
        Executa CHECKPOINT no DuckDB para flush do WAL ao arquivo principal.

        O CHECKPOINT libera espaço de páginas deletadas por UPSERTs e
        garante que o arquivo .wal seja zerado (importante para backups
        e para detectar conexões travadas via check_duckdb_wal).

        Requer acesso exclusivo de escrita — serializado via etl_pool.
        """
        from src.etl.db_manager import DatabaseManager

        db = DatabaseManager()
        with db.get_connection() as conn:
            conn.execute("CHECKPOINT")

        # Verifica se o WAL foi zerado
        import os
        from pathlib import Path as P

        db_path = P(
            os.environ.get("DUCKDB_PATH", "/opt/airflow/app/data/civic_audit.duckdb")
        )
        wal_path = db_path.with_suffix(".duckdb.wal")
        wal_size = wal_path.stat().st_size if wal_path.exists() else 0

        logger.info("DuckDB CHECKPOINT concluído. WAL residual: %d bytes", wal_size)
        return {"checkpoint_done": True, "wal_residual_bytes": wal_size}

    # ------------------------------------------------------------------
    # Pipeline: limpeza em paralelo → checkpoint
    # ------------------------------------------------------------------
    docker_cleanup = cleanup_docker_orphans()
    log_cleanup = cleanup_airflow_logs()
    log_rotation = rotate_etl_log()

    # Join das tarefas paralelas (inclui dbt_clean BashOperator)
    cleanup_join = EmptyOperator(
        task_id="cleanup_complete",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    checkpoint = duckdb_checkpoint()

    [docker_cleanup, log_cleanup, log_rotation, dbt_clean] >> cleanup_join >> checkpoint


civic_audit_maintenance()
