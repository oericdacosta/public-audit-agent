with
source_data as (
    select
        id
        , municipio_id
        , numero_licitacao
        , data_realizacao_licitacao
        , documento_negociante
        , nome_negociante
        , updated_at
    from {{ source('tce_ce', 'licitantes') }}
)

, stg_licitantes as (
    select
        cast(id as varchar) as licitante_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_licitacao as varchar) as numero_licitacao
        , cast(data_realizacao_licitacao as date) as data_realizacao_licitacao
        , cast(documento_negociante as varchar) as documento_negociante
        , cast(nome_negociante as varchar) as nome_negociante
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_licitantes
