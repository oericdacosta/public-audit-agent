with receitas as (
    select *
    from {{ ref('int_receitas_enriched') }}
)

, final as (
    select
        ano_exercicio
        , mes_referencia
        , mes_referencia_date
        , trimestre
        , codigo_orgao
        , nome_orgao
        , municipio_id
        , sum(valor_orcado) as total_orcado
        , sum(valor_arrecadado) as total_arrecadado
        , sum(valor_arrecadado) - sum(valor_orcado) as superavit_deficit
        , case
            when sum(valor_orcado) > 0
                then round(sum(valor_arrecadado) / sum(valor_orcado) * 100, 2)
        end as percentual_arrecadado
        , rank() over (
            partition by ano_exercicio, mes_referencia
            order by sum(valor_arrecadado) desc
        ) as rank_receita_no_mes
    from receitas
    group by
        ano_exercicio
        , mes_referencia
        , mes_referencia_date
        , trimestre
        , codigo_orgao
        , nome_orgao
        , municipio_id
)

select * from final
