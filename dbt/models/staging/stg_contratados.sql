with source as (
    select * from {{ source('tce_ce', 'contratados') }}
)

, renamed as (
    select
        id                                          as contratado_id
        , municipio_id
        , numero_contrato
        , data_contrato
        , documento_negociante
        , nome_negociante
        , updated_at
    from source
)

select * from renamed
