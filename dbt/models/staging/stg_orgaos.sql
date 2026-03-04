with source as (
    select * from {{ source('tce_ce', 'orgaos') }}
)

, renamed as (
    select
        id                                          as orgao_id
        , municipio_id
        , codigo_orgao
        , descricao_orgao
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
