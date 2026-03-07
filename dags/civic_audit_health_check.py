"""
CivicAudit Health Check DAG.

Verificações de saúde a cada 15 minutos — todos os checks rodam em paralelo.

Fluxo::

    [check_mcp_tcp ‖ check_sandbox_container ‖ check_duckdb_wal ‖ check_duckdb_size]
        → report_health_status

Checks:
- ``check_mcp_tcp``: verifica que o MCP TCP server responde na porta configurada
- ``check_sandbox_container``: verifica que o warm container do sandbox está ativo
- ``check_duckdb_wal``: alerta se o WAL do DuckDB estiver grande (conexão travada)
- ``check_duckdb_size``: alerta se o arquivo DuckDB ultrapassar threshold configurado
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.utils.trigger_rule import TriggerRule
from common.callbacks import on_dag_failure, on_task_failure

logger = logging.getLogger(__name__)

_DATA_DIR = Path(
    os.environ.get("DUCKDB_PATH", "/opt/airflow/app/data/civic_audit.duckdb")
).parent
_DUCKDB_PATH = Path(
    os.environ.get("DUCKDB_PATH", "/opt/airflow/app/data/civic_audit.duckdb")
)
_MCP_HOST = os.environ.get("MCP_HOST", "localhost")
_MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
_DUCKDB_SIZE_WARN_MB = 2048  # 2 GB
_WAL_SIZE_WARN_MB = 100  # 100 MB

default_args = {
    "owner": "civic-audit",
    "depends_on_past": False,
    "retries": 0,  # Health checks não fazem retry — resultado imediato é o que importa
    "execution_timeout": timedelta(minutes=2),
    "on_failure_callback": on_task_failure,
}


@dag(
    dag_id="civic_audit_health_check",
    default_args=default_args,
    description="Verificações de saúde: MCP, sandbox Docker, DuckDB WAL e tamanho",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["health", "monitoring", "civic-audit"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
    doc_md=__doc__,
)
def civic_audit_health_check():
    """Health checks paralelos do CivicAudit."""

    @task()
    def check_mcp_tcp() -> dict:
        """
        Verifica que o MCP TCP server responde na porta configurada.

        Envia um payload de inicialização JSON-RPC e verifica que
        a resposta contém o campo 'result' ou 'protocolVersion'.
        """
        import json
        import socket

        try:
            payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "airflow-health-check",
                            "version": "1.0",
                        },
                    },
                }
            )
            with socket.create_connection((_MCP_HOST, _MCP_PORT), timeout=5) as sock:
                sock.sendall((payload + "\n").encode())
                response = sock.recv(4096).decode()
                data = json.loads(response)
                is_ok = "result" in data or "protocolVersion" in str(data)
                logger.info(
                    "MCP TCP check: %s (host=%s port=%d)",
                    "OK" if is_ok else "WARN",
                    _MCP_HOST,
                    _MCP_PORT,
                )
                return {
                    "status": "ok" if is_ok else "warning",
                    "host": _MCP_HOST,
                    "port": _MCP_PORT,
                }
        except Exception as e:
            logger.warning("MCP TCP health check falhou: %s", e)
            return {
                "status": "error",
                "host": _MCP_HOST,
                "port": _MCP_PORT,
                "error": str(e),
            }

    @task()
    def check_sandbox_container() -> dict:
        """
        Verifica que o warm container do sandbox está ativo.

        Busca containers com imagem python:3.12-slim em estado 'running'.
        Se não encontrado, a próxima execução do agente pagará cold start (~300ms).
        """
        try:
            import docker

            client = docker.from_env(timeout=5)
            containers = client.containers.list(
                filters={"ancestor": "python:3.12-slim", "status": "running"}
            )
            warm = [
                c
                for c in containers
                if "sleep" in " ".join(c.attrs.get("Config", {}).get("Cmd") or [])
            ]
            if warm:
                logger.info("Sandbox warm container ativo: %s", warm[0].short_id)
                return {"status": "ok", "container_id": warm[0].short_id}
            else:
                logger.warning(
                    "Nenhum warm container encontrado"
                    " — cold start na próxima execução do agente"
                )
                return {"status": "warning", "message": "no warm container running"}
        except Exception as e:
            logger.warning("Docker health check falhou: %s", e)
            return {"status": "error", "error": str(e)}

    @task()
    def check_duckdb_wal() -> dict:
        """
        Verifica o arquivo WAL do DuckDB.

        Um WAL grande indica uma conexão travada sem commitar,
        o que pode bloquear escritas do ETL.
        """
        wal_path = _DUCKDB_PATH.with_suffix(".duckdb.wal")
        if not wal_path.exists():
            logger.debug("Nenhum arquivo WAL — DuckDB limpo")
            return {"status": "ok", "wal_exists": False}

        size_mb = round(wal_path.stat().st_size / (1024 * 1024), 1)
        if size_mb > _WAL_SIZE_WARN_MB:
            logger.warning(
                "DuckDB WAL grande: %.1f MB (threshold: %d MB)"
                " — possível conexão travada",
                size_mb,
                _WAL_SIZE_WARN_MB,
            )
            return {"status": "warning", "wal_size_mb": size_mb}

        logger.debug("DuckDB WAL: %.1f MB (OK)", size_mb)
        return {"status": "ok", "wal_size_mb": size_mb}

    @task()
    def check_duckdb_size() -> dict:
        """
        Monitora o tamanho do arquivo DuckDB principal.

        Alerta quando o arquivo ultrapassa o threshold para planejamento
        de capacidade e identificação de crescimento inesperado.
        """
        if not _DUCKDB_PATH.exists():
            logger.warning("Arquivo DuckDB não encontrado: %s", _DUCKDB_PATH)
            return {"status": "error", "message": "DuckDB file not found"}

        size_mb = round(_DUCKDB_PATH.stat().st_size / (1024 * 1024), 1)
        if size_mb > _DUCKDB_SIZE_WARN_MB:
            logger.warning(
                "DuckDB grande: %.1f MB (threshold: %d MB)",
                size_mb,
                _DUCKDB_SIZE_WARN_MB,
            )
            return {"status": "warning", "size_mb": size_mb}

        logger.info("DuckDB size: %.1f MB (OK)", size_mb)
        return {"status": "ok", "size_mb": size_mb}

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def report_health_status(results: list[dict]) -> dict:
        """Agrega resultados de todos os checks e loga status consolidado."""
        errors = [r for r in results if r.get("status") == "error"]
        warnings = [r for r in results if r.get("status") == "warning"]
        ok = [r for r in results if r.get("status") == "ok"]

        logger.info(
            "Health check summary — OK: %d | WARN: %d | ERROR: %d",
            len(ok),
            len(warnings),
            len(errors),
        )
        if errors:
            logger.error("Health check errors: %s", errors)
        if warnings:
            logger.warning("Health check warnings: %s", warnings)

        return {"ok": len(ok), "warnings": len(warnings), "errors": len(errors)}

    # Todos os checks em paralelo, depois agrega
    mcp = check_mcp_tcp()
    sandbox = check_sandbox_container()
    wal = check_duckdb_wal()
    size = check_duckdb_size()
    report_health_status([mcp, sandbox, wal, size])


civic_audit_health_check()
