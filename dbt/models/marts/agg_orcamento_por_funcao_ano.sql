with
loa_por_funcao as (
    select
        municipio_id
        , ano_exercicio
        , codigo_funcao
        , nome_funcao
        , sum(valor_fixado_loa) as total_fixado_loa
    from {{ ref('int_orcamento_despesa') }}
    group by
        municipio_id
        , ano_exercicio
        , codigo_funcao
        , nome_funcao
)

, execucao as (
    select
        municipio_id
        , ano_exercicio
        , codigo_funcao
        , sum(total_empenhado_ano) as total_empenhado_ano
        , sum(total_liquidado_ano) as total_liquidado_ano
        , sum(total_pago_ano) as total_pago_ano
    from {{ ref('int_despesas_por_funcao_ano') }}
    group by
        municipio_id
        , ano_exercicio
        , codigo_funcao
)

, final as (
    select
        loa.municipio_id
        , dm.nome_municipio
        , loa.ano_exercicio
        , loa.codigo_funcao
        , loa.nome_funcao
        , loa.total_fixado_loa
        , coalesce(exc.total_empenhado_ano, 0) as total_empenhado_ano
        , coalesce(exc.total_liquidado_ano, 0) as total_liquidado_ano
        , coalesce(exc.total_pago_ano, 0)      as total_pago_ano
        , round(
            coalesce(exc.total_empenhado_ano, 0) / nullif(loa.total_fixado_loa, 0) * 100
            , 2
        ) as percentual_empenhado_loa
        , round(
            coalesce(exc.total_pago_ano, 0) / nullif(loa.total_fixado_loa, 0) * 100
            , 2
        ) as percentual_executado_loa
        , loa.total_fixado_loa - coalesce(exc.total_empenhado_ano, 0) as saldo_orcamentario
        , rank() over (
            partition by loa.ano_exercicio, loa.municipio_id
            order by loa.total_fixado_loa desc
        ) as rank_funcao_por_fixado
        , rank() over (
            partition by loa.ano_exercicio, loa.municipio_id
            order by coalesce(exc.total_pago_ano, 0) desc
        ) as rank_funcao_por_executado
    from loa_por_funcao as loa
    left join execucao as exc
        on
            loa.municipio_id = exc.municipio_id
            and loa.ano_exercicio = exc.ano_exercicio
            and loa.codigo_funcao = exc.codigo_funcao
    left join {{ ref('dim_municipios') }} as dm
        on loa.municipio_id = dm.municipio_id
)

select * from final
