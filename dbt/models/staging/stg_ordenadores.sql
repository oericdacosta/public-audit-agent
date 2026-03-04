with source as (
    select * from {{ source('tce_ce', 'ordenadores') }}
)

, renamed as (
    select
        id                                          as ordenador_id
        , municipio_id
        , codigo_ordenador
        , nome_ordenador
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
