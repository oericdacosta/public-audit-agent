with
balancete as (
    select *
    from {{ ref('int_balancete_consolidado') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('dim_municipios') }}
)

, com_acumulado as (
    select
        bal.municipio_id
        , bal.ano_exercicio
        , bal.mes_referencia
        , bal.mes_referencia_date
        , bal.trimestre
        , bal.nome_mes_referencia
        , bal.total_despesa_empenhada
        , bal.total_despesa_paga
        , bal.total_receita_arrecadada
        , bal.resultado_primario
        , bal.is_superavit
        , bal.percentual_execucao_despesa
        , sum(bal.total_receita_arrecadada) over (
            partition by bal.municipio_id, bal.ano_exercicio
            order by bal.mes_referencia
            rows between unbounded preceding and current row
        ) as receita_acumulada_ano
        , sum(bal.total_despesa_paga) over (
            partition by bal.municipio_id, bal.ano_exercicio
            order by bal.mes_referencia
            rows between unbounded preceding and current row
        ) as despesa_acumulada_ano
        , sum(bal.resultado_primario) over (
            partition by bal.municipio_id, bal.ano_exercicio
            order by bal.mes_referencia
            rows between unbounded preceding and current row
        ) as resultado_acumulado_ano
    from balancete as bal
)

, final as (
    select
        ac.municipio_id
        , mun.nome_municipio
        , ac.ano_exercicio
        , ac.mes_referencia
        , ac.mes_referencia_date
        , ac.trimestre
        , ac.nome_mes_referencia
        , ac.total_despesa_empenhada
        , ac.total_despesa_paga
        , ac.total_receita_arrecadada
        , ac.resultado_primario
        , ac.is_superavit
        , ac.percentual_execucao_despesa
        , ac.receita_acumulada_ano
        , ac.despesa_acumulada_ano
        , ac.resultado_acumulado_ano
        , ac.resultado_acumulado_ano > 0 as is_superavit_acumulado
        , case
            when ac.resultado_acumulado_ano > 0
                then 'Superávit acumulado'
            when ac.resultado_acumulado_ano < 0
                then 'Déficit acumulado'
            else 'Equilibrado'
        end as situacao_fiscal_acumulada
    from com_acumulado as ac
    left join municipios as mun
        on ac.municipio_id = mun.municipio_id
)

select *
from final
