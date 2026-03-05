with orgaos as (
    select *
    from {{ ref('stg_orgaos') }}
)

, final as (
    select
        org.codigo_orgao
        , org.ano_exercicio
        , org.municipio_id
        , coalesce(org.descricao_orgao, 'Orgao ' || org.codigo_orgao) as nome_orgao
    from orgaos as org
)

select * from final
