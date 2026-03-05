with despesas as (
    select *
    from {{ ref('int_despesas_enriched') }}
)

, final as (
    select
        ano_exercicio
        , municipio_id
        , codigo_funcao
        , nome_funcao
        , sum(valor_empenhado) as total_empenhado_ano
        , sum(valor_liquidado) as total_liquidado_ano
        , sum(valor_pago) as total_pago_ano
        , case
            when sum(valor_empenhado) > 0
                then round(sum(valor_pago) / sum(valor_empenhado) * 100, 2)
        end as percentual_executado
        , round(
            sum(valor_pago) / nullif(
                sum(sum(valor_pago)) over (partition by ano_exercicio, municipio_id)
                , 0
            ) * 100
            , 2
        ) as percentual_orcamento_total
        , rank() over (
            partition by ano_exercicio, municipio_id
            order by sum(valor_pago) desc
        ) as rank_funcao_no_ano
    from despesas
    group by
        ano_exercicio
        , municipio_id
        , codigo_funcao
        , nome_funcao
)

select * from final
