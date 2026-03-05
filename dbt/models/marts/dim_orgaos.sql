with
orgaos as (
    select *
    from {{ ref('int_orgaos_enriched') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
        , uf
    from {{ ref('dim_municipios') }}
)

, final as (
    select
        md5(
            coalesce(org.codigo_orgao, '') || '||'
            || coalesce(org.municipio_id, '') || '||'
            || coalesce(cast(org.ano_exercicio as varchar), '')
        ) as orgao_sk
        , org.codigo_orgao
        , org.nome_orgao
        , org.municipio_id
        , mun.nome_municipio
        , mun.uf
        , org.ano_exercicio
    from orgaos as org
    left join municipios as mun
        on org.municipio_id = mun.municipio_id
)

select *
from final
