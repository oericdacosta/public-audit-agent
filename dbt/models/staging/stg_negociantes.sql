with source as (
    select * from {{ source('tce_ce', 'negociantes') }}
)

, renamed as (
    select
        id                                          as negociante_id
        , numero_documento_negociante
        , nome_negociante
        , endereco_negociante
        , fone_negociante                             as telefone_negociante
        , cep_negociante
        , nome_municipio_negociante
        , uf_negociante
        , updated_at
    from source
)

select * from renamed
