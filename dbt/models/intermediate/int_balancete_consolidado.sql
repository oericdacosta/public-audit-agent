with despesas_agg as (
    select
        ano_exercicio
        , mes_referencia
        , municipio_id
        , sum(valor_empenhado) as total_despesa_empenhada
        , sum(valor_pago) as total_despesa_paga
    from {{ ref('stg_despesas') }}
    group by ano_exercicio, mes_referencia, municipio_id
)

, receitas_agg as (
    select
        ano_exercicio
        , mes_referencia
        , municipio_id
        , sum(valor_arrecadado) as total_receita_arrecadada
    from {{ ref('stg_receitas') }}
    group by ano_exercicio, mes_referencia, municipio_id
)

, base as (
    select
        dep.total_despesa_empenhada
        , dep.total_despesa_paga
        , rec.total_receita_arrecadada
        , coalesce(dep.ano_exercicio, rec.ano_exercicio) as ano_exercicio
        , coalesce(dep.mes_referencia, rec.mes_referencia) as mes_referencia
        , coalesce(dep.municipio_id, rec.municipio_id) as municipio_id
    from despesas_agg as dep
    full outer join receitas_agg as rec
        on
            dep.ano_exercicio = rec.ano_exercicio
            and dep.mes_referencia = rec.mes_referencia
            and dep.municipio_id = rec.municipio_id
)

, final as (
    select
        ano_exercicio
        , mes_referencia
        , municipio_id
        , strptime(mes_referencia, '%Y%m')::date as mes_referencia_date
        , total_despesa_empenhada
        , total_despesa_paga
        , total_receita_arrecadada
        , case
            when mes_referencia[5:6] in ('01', '02', '03') then 'T1'
            when mes_referencia[5:6] in ('04', '05', '06') then 'T2'
            when mes_referencia[5:6] in ('07', '08', '09') then 'T3'
            when mes_referencia[5:6] in ('10', '11', '12') then 'T4'
        end as trimestre
        , case
            when mes_referencia[5:6] = '01' then 'Janeiro'
            when mes_referencia[5:6] = '02' then 'Fevereiro'
            when mes_referencia[5:6] = '03' then 'Março'
            when mes_referencia[5:6] = '04' then 'Abril'
            when mes_referencia[5:6] = '05' then 'Maio'
            when mes_referencia[5:6] = '06' then 'Junho'
            when mes_referencia[5:6] = '07' then 'Julho'
            when mes_referencia[5:6] = '08' then 'Agosto'
            when mes_referencia[5:6] = '09' then 'Setembro'
            when mes_referencia[5:6] = '10' then 'Outubro'
            when mes_referencia[5:6] = '11' then 'Novembro'
            when mes_referencia[5:6] = '12' then 'Dezembro'
        end as nome_mes_referencia
        , total_receita_arrecadada - total_despesa_paga as resultado_primario
        , total_receita_arrecadada - total_despesa_paga > 0 as is_superavit
        , total_despesa_paga
        / nullif(total_despesa_empenhada, 0)
        * 100 as percentual_execucao_despesa
    from base
)

select * from final
