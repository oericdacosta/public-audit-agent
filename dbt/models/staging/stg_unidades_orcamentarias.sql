with source as (
    select * from {{ source('tce_ce', 'unidades_orcamentarias') }}
)

, renamed as (
    select
        id                                          as unidade_orcamentaria_id
        , municipio_id
        , codigo_unidade_orcamentaria
        , descricao_unidade_orcamentaria
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
