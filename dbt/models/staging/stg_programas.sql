with source as (
    select * from {{ source('tce_ce', 'programas') }}
)

, renamed as (
    select
        id                                          as programa_id
        , municipio_id
        , codigo_programa
        , descricao_programa
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
