with despesas as (
    select *
    from {{ ref('int_despesas_enriched') }}
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
        , sum(valor_empenhado) as total_empenhado
        , sum(valor_liquidado) as total_liquidado
        , sum(valor_pago) as total_pago
        , sum(valor_nao_pago) as total_nao_pago
        , case
            when sum(valor_empenhado) > 0
                then round(sum(valor_pago) / sum(valor_empenhado) * 100, 2)
        end as percentual_executado
        , rank() over (
            partition by ano_exercicio, mes_referencia
            order by sum(valor_pago) desc
        ) as rank_orgao_no_mes
    from despesas
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
