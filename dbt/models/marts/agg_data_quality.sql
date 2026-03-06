-- Data quality classification per (municipio_id, ano_exercicio, nome_funcao).
-- Uses deterministic rules derived from observable metrics — no LLM required.
--
-- status_qualidade values:
--   DADOS_CONSOLIDADOS          — significant non-zero execution data
--   DADOS_PARCIAIS              — some non-zero but many zero records (still accruing)
--   DADOS_POSSIVELMENTE_INCOMPLETOS — all zeros but historical data shows non-zero
--   ZERO_SEM_HISTORICO          — all zeros, no historical precedent
--   SEM_DADOS_ETL               — no records in the ETL at all
with
despesas_funcao as (
    select
        municipio_id
        , ano_exercicio
        , nome_funcao
        , valor_empenhado
        , valor_liquidado
        , valor_pago
        , (
            coalesce(valor_empenhado, 0) = 0
            and coalesce(valor_liquidado, 0) = 0
            and coalesce(valor_pago, 0) = 0
        ) as is_all_zero
    from {{ ref('int_despesas_enriched') }}
    where nome_funcao is not null
)

, metricas_por_funcao_ano as (
    select
        municipio_id
        , ano_exercicio
        , nome_funcao
        , count(*)                                                    as total_registros
        , sum(case when is_all_zero then 1 else 0 end)               as registros_all_zero
        , round(
            sum(case when is_all_zero then 1 else 0 end) * 100.0
            / nullif(count(*), 0)
            , 1
        )                                                             as pct_registros_all_zero
        , coalesce(sum(valor_empenhado), 0)                          as total_empenhado
        , coalesce(sum(valor_pago), 0)                               as total_pago
    from despesas_funcao
    group by
        municipio_id
        , ano_exercicio
        , nome_funcao
)

-- Count distinct years (across all time) with non-zero execution for this funcao
, historico_nao_zero as (
    select
        municipio_id
        , nome_funcao
        , count(distinct ano_exercicio) as anos_com_historico_nao_zero
    from metricas_por_funcao_ano
    where total_empenhado > 0
    group by
        municipio_id
        , nome_funcao
)

, final as (
    select
        m.municipio_id
        , dm.nome_municipio
        , m.ano_exercicio
        , m.nome_funcao
        , m.total_registros
        , m.registros_all_zero
        , m.pct_registros_all_zero
        , m.total_empenhado
        , m.total_pago
        , coalesce(h.anos_com_historico_nao_zero, 0) as anos_com_historico_nao_zero

        , case
            when m.total_empenhado > 0 and m.pct_registros_all_zero < 10
                then 'DADOS_CONSOLIDADOS'
            when m.total_empenhado > 0 and m.pct_registros_all_zero >= 10
                then 'DADOS_PARCIAIS'
            when
                m.total_empenhado = 0
                and coalesce(h.anos_com_historico_nao_zero, 0) > 0
                then 'DADOS_POSSIVELMENTE_INCOMPLETOS'
            when
                m.total_empenhado = 0
                and coalesce(h.anos_com_historico_nao_zero, 0) = 0
                then 'ZERO_SEM_HISTORICO'
            else 'SEM_DADOS_ETL'
        end as status_qualidade

        , case
            when m.total_empenhado > 0 and m.pct_registros_all_zero < 10
                then
                    'Dados consolidados para '
                    || m.nome_funcao || ' em ' || cast(m.ano_exercicio as varchar)
                    || '. Total de ' || cast(m.total_registros as varchar)
                    || ' registros com valores nao-nulos.'
            when m.total_empenhado > 0 and m.pct_registros_all_zero >= 10
                then
                    'Dados parcialmente consolidados para '
                    || m.nome_funcao || ' em ' || cast(m.ano_exercicio as varchar)
                    || '. ' || cast(m.pct_registros_all_zero as varchar)
                    || '% dos registros ainda apresentam valor zerado, '
                    || 'possivelmente pendentes de lancamento.'
            when
                m.total_empenhado = 0
                and coalesce(h.anos_com_historico_nao_zero, 0) > 0
                then
                    'Dados de '
                    || m.nome_funcao || ' para ' || cast(m.ano_exercicio as varchar)
                    || ' ainda nao foram publicados ou consolidados pela fonte (TCE-CE). '
                    || 'Historico disponivel em '
                    || cast(coalesce(h.anos_com_historico_nao_zero, 0) as varchar)
                    || ' ano(s) anterior(es) com valores nao-nulos.'
            when
                m.total_empenhado = 0
                and coalesce(h.anos_com_historico_nao_zero, 0) = 0
                then
                    'Nenhum gasto registrado para '
                    || m.nome_funcao || ' em ' || cast(m.ano_exercicio as varchar)
                    || ' e tambem nao ha historico de anos anteriores '
                    || 'nesta funcao para o municipio.'
            else
                'Sem dados de execucao para '
                || m.nome_funcao || ' em ' || cast(m.ano_exercicio as varchar) || '.'
        end as explicacao_qualidade

    from metricas_por_funcao_ano as m
    left join historico_nao_zero as h
        on
            m.municipio_id = h.municipio_id
            and m.nome_funcao = h.nome_funcao
    left join {{ ref('dim_municipios') }} as dm
        on m.municipio_id = dm.municipio_id
)

select * from final
