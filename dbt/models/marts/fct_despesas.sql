with
despesas as (
    select *
    from {{ ref('int_despesas_enriched') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('dim_municipios') }}
)

, final as (
    select
        dep.despesa_id
        , dep.municipio_id
        , mun.nome_municipio
        , dep.ano_exercicio
        , dep.mes_referencia
        , dep.mes_referencia_date
        , dep.trimestre
        , dep.codigo_orgao
        , dep.nome_orgao
        , dep.codigo_unidade_orcamentaria
        , dep.nome_unidade_orcamentaria
        , dep.codigo_funcao
        , dep.nome_funcao
        , dep.codigo_subfuncao
        , dep.codigo_programa
        , dep.nome_programa
        , dep.codigo_elemento_despesa
        , dep.grupo_despesa
        , dep.valor_empenhado
        , dep.valor_liquidado
        , dep.valor_pago
        , dep.valor_nao_pago
        , dep.percentual_executado
        , dep.status_execucao
        , dep.is_pago_integralmente
        , dep.updated_at
    from despesas as dep
    left join municipios as mun
        on dep.municipio_id = mun.municipio_id
)

select *
from final
