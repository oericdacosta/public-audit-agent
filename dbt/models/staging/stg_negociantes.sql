with
source_data as (
    select
        id
        , numero_documento_negociante
        , nome_negociante
        , endereco_negociante
        , fone_negociante
        , cep_negociante
        , nome_municipio_negociante
        , uf_negociante
        , updated_at
    from {{ source('tce_ce', 'negociantes') }}
)

, stg_negociantes as (
    select
        cast(id as varchar) as negociante_id
        , cast(numero_documento_negociante as varchar) as numero_documento_negociante
        , cast(nome_negociante as varchar) as nome_negociante
        , cast(endereco_negociante as varchar) as endereco_negociante
        , cast(fone_negociante as varchar) as telefone_negociante
        , cast(cep_negociante as varchar) as cep_negociante
        , cast(nome_municipio_negociante as varchar) as nome_municipio_negociante
        , cast(uf_negociante as varchar) as uf_negociante
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_negociantes
