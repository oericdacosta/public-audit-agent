"""
Airflow Callbacks for CivicAudit ETL.

Provides failure and success callbacks for DAG and task-level alerting.
"""

import logging

logger = logging.getLogger(__name__)


def on_task_failure(context: dict) -> None:
    """
    Callback executado quando uma task falha.

    Loga detalhes da falha. Pode ser estendido para enviar alertas
    via Slack, Discord ou Email.
    """
    ti = context["task_instance"]
    exception = context.get("exception", "Unknown")

    msg = (
        f"❌ Task Falhou!\n"
        f"  DAG: {ti.dag_id}\n"
        f"  Task: {ti.task_id}\n"
        f"  Execução: {context['ds']}\n"
        f"  Tentativa: {ti.try_number}\n"
        f"  Erro: {exception}\n"
        f"  Log: {ti.log_url}"
    )
    logger.error(msg)


def on_task_success(context: dict) -> None:
    """Callback executado quando uma task completa com sucesso."""
    ti = context["task_instance"]
    logger.info(
        "✅ Task concluída: %s.%s (execução: %s)",
        ti.dag_id,
        ti.task_id,
        context["ds"],
    )


def on_dag_failure(context: dict) -> None:
    """
    Callback executado quando a DAG inteira falha.

    Agrega informações de falha para envio de alerta consolidado.
    """
    dag_run = context.get("dag_run")
    dag_id = dag_run.dag_id if dag_run else "unknown"

    failed_tasks = []
    if dag_run:
        for ti in dag_run.get_task_instances():
            if ti.state == "failed":
                failed_tasks.append(ti.task_id)

    msg = (
        f"🚨 DAG Falhou!\n"
        f"  DAG: {dag_id}\n"
        f"  Execução: {context.get('ds', 'N/A')}\n"
        f"  Tasks com falha: {', '.join(failed_tasks) or 'N/A'}"
    )
    logger.error(msg)
