with
despesas_orgao_mes as (
    select *
    from {{ ref('int_despesas_por_orgao_mes') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('stg_municipios') }}
)

, agregado_ano as (
    select
        municipio_id
        , ano_exercicio
        , codigo_orgao
        , nome_orgao
        , sum(total_empenhado) as total_empenhado_ano
        , sum(total_liquidado) as total_liquidado_ano
        , sum(total_pago) as total_pago_ano
        , sum(total_nao_pago) as total_nao_pago_ano
    from despesas_orgao_mes
    group by municipio_id, ano_exercicio, codigo_orgao, nome_orgao
)

, com_ranking as (
    select
        municipio_id
        , ano_exercicio
        , codigo_orgao
        , nome_orgao
        , total_empenhado_ano
        , total_liquidado_ano
        , total_pago_ano
        , total_nao_pago_ano
        , case
            when total_empenhado_ano > 0
                then round(total_pago_ano / total_empenhado_ano * 100, 2)
        end as percentual_executado_ano
        , round(
            total_pago_ano / nullif(
                sum(total_pago_ano) over (partition by municipio_id, ano_exercicio)
                , 0
            ) * 100
            , 2
        ) as participacao_no_total_pct
        , rank() over (
            partition by municipio_id, ano_exercicio
            order by total_pago_ano desc
        ) as rank_gasto_no_ano
    from agregado_ano
)

, final as (
    select
        ran.municipio_id
        , mun.nome_municipio
        , ran.ano_exercicio
        , ran.codigo_orgao
        , ran.nome_orgao
        , ran.total_empenhado_ano
        , ran.total_liquidado_ano
        , ran.total_pago_ano
        , ran.total_nao_pago_ano
        , ran.percentual_executado_ano
        , ran.participacao_no_total_pct
        , ran.rank_gasto_no_ano
    from com_ranking as ran
    left join municipios as mun
        on ran.municipio_id = mun.municipio_id
)

select *
from final
