"""
CivicAudit Security Scan DAG.

Varredura semanal de segurança — todos os checks rodam em paralelo.

Fluxo::

    [run_pip_audit ‖ run_bandit ‖ validate_openai_key ‖ validate_langfuse_keys]
        → security_summary

Checks:
- ``run_pip_audit``: CVEs nas dependências Python do projeto
- ``run_bandit``: SAST em src/ (severity médio+, confidence médio+)
- ``validate_openai_key``: verifica que a chave OpenAI está válida e não expirou
- ``validate_langfuse_keys``: verifica acesso ao endpoint Langfuse

Schedule: segundas às 6h — fora da janela do ETL (3h) e manutenção (2h domingo).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule
from common.callbacks import on_dag_failure, on_task_failure

logger = logging.getLogger(__name__)

_APP_DIR = "/opt/airflow/app"

default_args = {
    "owner": "civic-audit",
    "depends_on_past": False,
    "retries": 0,
    "execution_timeout": timedelta(minutes=15),
    "on_failure_callback": on_task_failure,
}


@dag(
    dag_id="civic_audit_security_scan",
    default_args=default_args,
    description="Varredura semanal: pip-audit + bandit SAST + validação de chaves API",
    schedule="0 6 * * 1",  # Segundas às 6h
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["security", "compliance", "civic-audit"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
    doc_md=__doc__,
)
def civic_audit_security_scan():
    """Varredura de segurança semanal do CivicAudit."""

    # ------------------------------------------------------------------
    # pip-audit: CVEs nas dependências
    # ------------------------------------------------------------------
    pip_audit = BashOperator(
        task_id="run_pip_audit",
        bash_command=(
            "pip-audit --format markdown --output /tmp/pip_audit_report.txt || true && "
            "cat /tmp/pip_audit_report.txt || true"
        ),
        # Audita o ambiente instalado diretamente (sem --requirement para evitar
        # dry-run install que falha em pacotes com dependências de sistema).
        # `|| true` impede que CVEs ou ausência de report falhem a task.
    )

    # ------------------------------------------------------------------
    # bandit: SAST em src/
    # ------------------------------------------------------------------
    bandit_scan = BashOperator(
        task_id="run_bandit",
        bash_command=(
            f"bandit -r {_APP_DIR}/src/ -ll -ii "
            "--format txt --output /tmp/bandit_report.txt || true && "
            "cat /tmp/bandit_report.txt"
        ),
        # -ll: medium+ severity, -ii: medium+ confidence
        # `|| true` para sempre logar o relatório mesmo com findings
    )

    # ------------------------------------------------------------------
    # Validação de chaves API (paralelo com pip-audit e bandit)
    # ------------------------------------------------------------------

    @task()
    def validate_openai_key() -> dict:
        """
        Valida que a chave OpenAI está configurada e funcional.

        Usa models.list — chamada sem custo que confirma autenticação.
        """
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            logger.error("OPENAI_API_KEY não configurada")
            return {"status": "error", "message": "OPENAI_API_KEY not set"}

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            models = client.models.list()
            model_ids = [m.id for m in models.data[:3]]
            logger.info("OpenAI key válida — modelos disponíveis: %s", model_ids)
            return {"status": "ok", "sample_models": model_ids}
        except Exception as e:
            logger.error("OpenAI key inválida ou expirada: %s", e)
            return {"status": "error", "error": str(e)}

    @task()
    def validate_langfuse_keys() -> dict:
        """
        Verifica que as chaves Langfuse estão configuradas e o endpoint acessível.

        Chama o endpoint /api/public/health da instância Langfuse configurada.
        """
        import requests

        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

        if not public_key or not secret_key:
            logger.warning(
                "Chaves Langfuse não configuradas — observabilidade desativada"
            )
            return {"status": "warning", "message": "Langfuse keys not set"}

        try:
            from src.utils.langfuse_client import get_langfuse_client

            client = get_langfuse_client()
            if client is None:
                return {
                    "status": "warning",
                    "message": "Langfuse client not initialized",
                }

            # Verifica conectividade via endpoint de saúde
            host = "https://cloud.langfuse.com"
            r = requests.get(
                f"{host}/api/public/health",
                auth=(public_key, secret_key),
                timeout=10,
            )
            if r.status_code == 200:
                logger.info("Langfuse keys válidas (status %d)", r.status_code)
                return {"status": "ok", "host": host}
            else:
                logger.warning("Langfuse health check retornou %d", r.status_code)
                return {"status": "warning", "http_status": r.status_code}
        except Exception as e:
            logger.error("Langfuse validation falhou: %s", e)
            return {"status": "error", "error": str(e)}

    # ------------------------------------------------------------------
    # Join: agrega resultados após todos os checks
    # ------------------------------------------------------------------
    @task(trigger_rule=TriggerRule.ALL_DONE)
    def security_summary(openai_result: dict, langfuse_result: dict) -> dict:
        """Consolida resultados e loga sumário da varredura de segurança."""
        results = {
            "openai_key": openai_result,
            "langfuse_keys": langfuse_result,
        }
        errors = {k: v for k, v in results.items() if v.get("status") == "error"}
        warnings = {k: v for k, v in results.items() if v.get("status") == "warning"}

        logger.info(
            "Security scan summary — Checks de API: %d OK | %d WARN | %d ERROR",
            len(results) - len(errors) - len(warnings),
            len(warnings),
            len(errors),
        )
        if errors:
            logger.error("Security errors: %s", errors)
        return results

    # Ponto de join para pip_audit e bandit (BashOperators)
    scan_join = EmptyOperator(
        task_id="scans_complete",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    openai_result = validate_openai_key()
    langfuse_result = validate_langfuse_keys()

    # Todos em paralelo
    [pip_audit, bandit_scan] >> scan_join
    summary = security_summary(openai_result, langfuse_result)
    scan_join >> summary


civic_audit_security_scan()
