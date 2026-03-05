with
receitas as (
    select *
    from {{ ref('int_receitas_enriched') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('stg_municipios') }}
)

, final as (
    select
        rec.receita_id
        , rec.municipio_id
        , mun.nome_municipio
        , rec.ano_exercicio
        , rec.mes_referencia
        , rec.mes_referencia_date
        , rec.trimestre
        , rec.codigo_orgao
        , rec.nome_orgao
        , rec.codigo_unidade_orcamentaria
        , rec.nome_unidade_orcamentaria
        , rec.codigo_receita
        , rec.descricao_receita
        , rec.valor_orcado
        , rec.valor_arrecadado
        , rec.desvio_arrecadacao
        , rec.percentual_arrecadado
        , rec.status_arrecadacao
        , rec.is_abaixo_meta
        , rec.updated_at
    from receitas as rec
    left join municipios as mun
        on rec.municipio_id = mun.municipio_id
)

select *
from final
