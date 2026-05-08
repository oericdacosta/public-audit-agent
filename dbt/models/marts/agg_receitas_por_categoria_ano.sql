with
receitas as (
    select *
    from {{ ref('int_receitas_enriched') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('dim_municipios') }}
)

, categorized as (
    select
        rec.municipio_id
        , rec.ano_exercicio
        , rec.codigo_receita
        , rec.descricao_receita
        , rec.valor_orcado
        , rec.valor_arrecadado
        , case
            when left(rec.codigo_receita, 1) = '1' then 'Receitas Correntes'
            when left(rec.codigo_receita, 1) = '2' then 'Receitas de Capital'
            when left(rec.codigo_receita, 1) = '7' then 'Receitas Correntes Intra-Orçamentárias'
            when left(rec.codigo_receita, 1) = '8' then 'Receitas de Capital Intra-Orçamentárias'
            else 'Outras Receitas'
        end as categoria_receita
        , case
            when lower(rec.descricao_receita) like '%iptu%' then 'IPTU'
            when
                lower(rec.descricao_receita) like '%iss%'
                or lower(rec.descricao_receita) like '%issqn%'
                then 'ISS'
            when lower(rec.descricao_receita) like '%fpm%' then 'FPM'
            when
                lower(rec.descricao_receita) like '%sus%'
                or lower(rec.descricao_receita) like '%saude%'
                then 'Transferências SUS'
            when lower(rec.descricao_receita) like '%fundeb%' then 'FUNDEB'
            when lower(rec.descricao_receita) like '%icms%' then 'ICMS'
            when lower(rec.descricao_receita) like '%itbi%' then 'ITBI'
            when
                lower(rec.descricao_receita) like '%irrf%'
                or lower(rec.descricao_receita) like '%imposto de renda%'
                then 'IRRF'
            else 'Outras'
        end as subcategoria_receita
    from receitas as rec
)

, final as (
    select
        cat.municipio_id
        , mun.nome_municipio
        , cat.ano_exercicio
        , cat.categoria_receita
        , cat.subcategoria_receita
        , sum(cat.valor_orcado) as total_orcado_ano
        , sum(cat.valor_arrecadado) as total_arrecadado_ano
        , case
            when sum(cat.valor_orcado) > 0
                then round(sum(cat.valor_arrecadado) / sum(cat.valor_orcado) * 100, 2)
        end as percentual_arrecadado
        , count(distinct cat.codigo_receita) as total_fontes_receita
    from categorized as cat
    left join municipios as mun
        on cat.municipio_id = mun.municipio_id
    group by
        cat.municipio_id
        , mun.nome_municipio
        , cat.ano_exercicio
        , cat.categoria_receita
        , cat.subcategoria_receita
)

select *
from final
