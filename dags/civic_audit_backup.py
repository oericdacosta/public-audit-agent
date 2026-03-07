"""
CivicAudit Backup DAG.

Backup diário do DuckDB via EXPORT DATABASE (formato Parquet).
Exporta todas as tabelas para um diretório com timestamp, mantendo
os últimos 7 dias de backups.

Fluxo::

    export_duckdb → cleanup_old_backups

``export_duckdb`` usa pool ``etl_pool`` para garantir acesso exclusivo
ao DuckDB. ``cleanup_old_backups`` roda após o export (operação de disco).

Schedule: 5h diário — 2h após o ETL das 3h, com folga para conclusão.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.utils.trigger_rule import TriggerRule
from common.callbacks import on_dag_failure, on_task_failure

logger = logging.getLogger(__name__)

_POOL = "etl_pool"
_DATA_DIR = Path("/opt/airflow/app/data")
_BACKUPS_DIR = _DATA_DIR / "backups"
_BACKUP_RETENTION_DAYS = 7

default_args = {
    "owner": "civic-audit",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "on_failure_callback": on_task_failure,
}


@dag(
    dag_id="civic_audit_backup",
    default_args=default_args,
    description="Backup diário do DuckDB via EXPORT DATABASE (Parquet)",
    schedule="0 5 * * *",  # 5h diário
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["backup", "maintenance", "civic-audit"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
    doc_md=__doc__,
)
def civic_audit_backup():
    """Backup diário do CivicAudit DuckDB."""

    @task(pool=_POOL, execution_timeout=timedelta(hours=1))
    def export_duckdb() -> str:
        """
        Exporta todas as tabelas DuckDB para Parquet via EXPORT DATABASE.

        O DuckDB EXPORT DATABASE gera um diretório contendo:
        - Um arquivo .parquet por tabela
        - load.sql com o DDL para reimportar

        Usa pool=etl_pool para garantir acesso exclusivo (sem writers concorrentes).
        """
        from src.etl.db_manager import DatabaseManager

        today = datetime.now().strftime("%Y%m%d_%H%M")
        backup_dir = _BACKUPS_DIR / today
        backup_dir.parent.mkdir(parents=True, exist_ok=True)

        db = DatabaseManager()
        with db.get_connection() as conn:
            conn.execute(f"EXPORT DATABASE '{backup_dir}' (FORMAT PARQUET)")  # noqa: S608

        size_mb = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file())
        size_mb_rounded = round(size_mb / (1024 * 1024), 1)
        logger.info("Backup concluído em %s (%.1f MB)", backup_dir, size_mb_rounded)
        return str(backup_dir)

    @task(trigger_rule=TriggerRule.ALL_SUCCESS)
    def cleanup_old_backups(backup_dir: str) -> dict:
        """
        Remove backups mais antigos que BACKUP_RETENTION_DAYS dias.

        Roda após export bem-sucedido para garantir que o novo backup
        existe antes de remover o mais antigo.
        """
        if not _BACKUPS_DIR.exists():
            return {"removed": 0}

        cutoff = datetime.now() - timedelta(days=_BACKUP_RETENTION_DAYS)
        removed = []

        for entry in sorted(_BACKUPS_DIR.iterdir()):
            if not entry.is_dir():
                continue
            # Tenta parsear o nome como YYYYMMDD ou YYYYMMDD_HHMM
            date_str = entry.name[:8]
            try:
                entry_date = datetime.strptime(date_str, "%Y%m%d")
                if entry_date < cutoff:
                    shutil.rmtree(entry)
                    removed.append(entry.name)
                    logger.info("Backup removido (expirado): %s", entry.name)
            except ValueError:
                continue  # Diretório sem nome de data — ignora

        logger.info(
            "Limpeza concluída: %d backup(s) removido(s), retenção de %d dias",
            len(removed),
            _BACKUP_RETENTION_DAYS,
        )
        return {"removed": len(removed), "dirs": removed}

    # --- Pipeline ---
    exported = export_duckdb()
    cleanup_old_backups(exported)


civic_audit_backup()
