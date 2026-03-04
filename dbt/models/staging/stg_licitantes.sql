with source as (
    select * from {{ source('tce_ce', 'licitantes') }}
)

, renamed as (
    select
        id                                          as licitante_id
        , municipio_id
        , numero_licitacao
        , data_realizacao_licitacao
        , documento_negociante
        , nome_negociante
        , updated_at
    from source
)

select * from renamed
