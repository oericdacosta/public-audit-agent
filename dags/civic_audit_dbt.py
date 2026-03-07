"""
CivicAudit dbt Transformation DAG.

Acionado via TriggerDagRunOperator pelos DAGs ETL após coleta concluída.
Pode também ser executado manualmente via Airflow UI.

Fluxo::

    dbt_seed → dbt_run_staging → dbt_test_sources (BLOQUEIA se falhar)
        → dbt_run_dims → dbt_run_fcts → dbt_run_fcts_enriched
        → dbt_run_aggs → dbt_run_data_quality → dbt_test_marts
        → [check_data_quality_score → reindex_catalog]  ← paralelo → [dbt_docs_generate]

Todos os tasks dbt usam pool ``etl_pool`` (DuckDB single-writer).
``check_data_quality_score`` e ``reindex_catalog`` não precisam do pool
(leitura read_only e acesso apenas a arquivos YML, respectivamente) e
rodam em paralelo com ``dbt_docs_generate``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule
from common.callbacks import on_dag_failure, on_task_failure

logger = logging.getLogger(__name__)

_POOL = "etl_pool"
_DBT_DIR = "/opt/airflow/app/dbt"
_DBT = f"cd {_DBT_DIR} && DBT_PROFILES_DIR={_DBT_DIR} dbt"

default_args = {
    "owner": "civic-audit",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
    "on_failure_callback": on_task_failure,
}


@dag(
    dag_id="civic_audit_dbt",
    default_args=default_args,
    description="dbt: seed → staging → marts → qualidade → reindex catálogo",
    schedule=None,  # Acionado pelo ETL via TriggerDagRunOperator
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["dbt", "transformation", "civic-audit"],
    max_active_runs=1,
    on_failure_callback=on_dag_failure,
    doc_md=__doc__,
)
def civic_audit_dbt():
    """Pipeline dbt de transformação do CivicAudit."""

    # ------------------------------------------------------------------
    # Camada: seeds (dimensão controlada manualmente)
    # ------------------------------------------------------------------
    seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"{_DBT} seed --full-refresh",
        pool=_POOL,
        execution_timeout=timedelta(minutes=10),
    )

    # ------------------------------------------------------------------
    # Camada: staging (views — não materializam tabelas físicas)
    # ------------------------------------------------------------------
    run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"{_DBT} run --select path:models/staging",
        pool=_POOL,
        execution_timeout=timedelta(minutes=15),
    )

    # ------------------------------------------------------------------
    # Teste de sources (BLOQUEIA tudo downstream se falhar)
    # Dados corrompidos no ETL não devem chegar aos marts.
    # ------------------------------------------------------------------
    test_sources = BashOperator(
        task_id="dbt_test_sources",
        bash_command=f"{_DBT} test --select source:*",
        pool=_POOL,
        retries=0,  # Testes são determinísticos — retry não resolve
        execution_timeout=timedelta(minutes=15),
    )

    # ------------------------------------------------------------------
    # Camada: marts — dimensões primeiro (fcts fazem join com dims)
    # ------------------------------------------------------------------
    run_dims = BashOperator(
        task_id="dbt_run_dims",
        bash_command=(
            f"{_DBT} run --select "
            "dim_municipios dim_orgaos dim_fornecedores dim_classificacao_orcamentaria"
        ),
        pool=_POOL,
        execution_timeout=timedelta(minutes=20),
    )

    # Fatos core
    run_fcts = BashOperator(
        task_id="dbt_run_fcts",
        bash_command=(
            f"{_DBT} run --select "
            "fct_despesas fct_receitas fct_contratos fct_licitacoes fct_servidores"
        ),
        pool=_POOL,
        execution_timeout=timedelta(minutes=30),
    )

    # Fatos enriquecidos (dependem dos fcts core)
    run_fcts_enriched = BashOperator(
        task_id="dbt_run_fcts_enriched",
        bash_command=(
            f"{_DBT} run --select "
            "fct_contratos_fornecedores fct_licitacoes_risco brd_licitantes"
        ),
        pool=_POOL,
        execution_timeout=timedelta(minutes=20),
    )

    # Agregações
    run_aggs = BashOperator(
        task_id="dbt_run_aggs",
        bash_command=(
            f"{_DBT} run --select "
            "agg_despesas_por_funcao_ano agg_despesas_por_orgao_ano "
            "agg_orcamento_por_funcao_ano agg_resultado_fiscal_mensal"
        ),
        pool=_POOL,
        execution_timeout=timedelta(minutes=20),
    )

    # Data quality — por último: usa historico_nao_zero que agrega todos os anos
    run_data_quality = BashOperator(
        task_id="dbt_run_data_quality",
        bash_command=f"{_DBT} run --select agg_data_quality",
        pool=_POOL,
        execution_timeout=timedelta(minutes=10),
    )

    # ------------------------------------------------------------------
    # Testes dos marts (alerta, não bloqueia downstream)
    # Downstream usa ALL_DONE para sempre executar reindex e docs.
    # ------------------------------------------------------------------
    test_marts = BashOperator(
        task_id="dbt_test_marts",
        bash_command=f"{_DBT} test --select path:models/marts",
        pool=_POOL,
        retries=0,
        execution_timeout=timedelta(minutes=15),
    )

    # ------------------------------------------------------------------
    # Fan-out paralelo após test_marts:
    #   Caminho A: check_data_quality_score → reindex_catalog  (sem pool)
    #   Caminho B: dbt_docs_generate                           (com pool)
    # ------------------------------------------------------------------

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def check_data_quality_score() -> str:
        """
        Verifica score de qualidade no agg_data_quality para anos consolidados.

        Avalia apenas anos anteriores a current_year-1 (que deveriam estar
        consolidados). Anos recentes com dados parciais são comportamento normal.
        Retorna 'ok', 'warning' ou 'critical' para log e alertas.
        """
        from datetime import datetime as dt

        from src.etl.db_manager import DatabaseManager

        threshold_year = dt.now().year - 1  # Só anos que deveriam estar consolidados
        try:
            db = DatabaseManager(read_only=True)
            with db.get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status_qualidade = 'DADOS_CONSOLIDADOS'
                                 THEN 1 ELSE 0 END) AS consolidated
                    FROM agg_data_quality
                    WHERE ano_exercicio < ?
                    """,
                    [threshold_year],
                ).fetchone()

            if not row or row[0] == 0:
                logger.info("Sem dados de anos consolidados em agg_data_quality ainda")
                return "ok"

            total, consolidated = row[0], row[1]
            pct = (consolidated / total * 100) if total > 0 else 0
            logger.info(
                "Data quality: %.1f%% DADOS_CONSOLIDADOS (%d/%d registros)",
                pct,
                consolidated,
                total,
            )

            if pct < 20:
                logger.error(
                    "CRITICAL: Apenas %.1f%% dos registros de anos consolidados "
                    "com DADOS_CONSOLIDADOS. Possível falha no ETL ou lacuna de dados.",
                    pct,
                )
                return "critical"
            elif pct < 60:
                logger.warning(
                    "Data quality abaixo do esperado: %.1f%% DADOS_CONSOLIDADOS "
                    "(esperado >= 60%%)",
                    pct,
                )
                return "warning"

            return "ok"
        except Exception as e:
            logger.warning("Data quality check falhou: %s — não bloqueando reindex", e)
            return "ok"

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def reindex_catalog() -> str:
        """
        Reconstrói o índice de embeddings semânticos do catálogo de tabelas.

        Usa SHA-256 por arquivo YML para re-embedar apenas tabelas cujos
        metadados mudaram. Limpa lru_cache após rebuild para garantir que
        o próximo acesso ao agente use o índice atualizado.
        """
        from src.utils.embeddings import _load_index, build_index

        build_index()
        _load_index.cache_clear()
        logger.info("Catalog embedding index rebuilt and cache cleared")
        return "reindexed"

    docs_generate = BashOperator(
        task_id="dbt_docs_generate",
        bash_command=f"{_DBT} docs generate",
        pool=_POOL,
        trigger_rule=TriggerRule.ALL_DONE,
        execution_timeout=timedelta(minutes=10),
    )

    # ------------------------------------------------------------------
    # Dependências
    # ------------------------------------------------------------------
    (
        seed
        >> run_staging
        >> test_sources
        >> run_dims
        >> run_fcts
        >> run_fcts_enriched
        >> run_aggs
        >> run_data_quality
        >> test_marts
    )

    # Fan-out paralelo: caminho A (sem pool) e caminho B (com pool)
    quality_result = check_data_quality_score()
    reindex = reindex_catalog()

    test_marts >> quality_result >> reindex
    test_marts >> docs_generate


civic_audit_dbt()
