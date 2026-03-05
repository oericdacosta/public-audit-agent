with
source_data as (
    select
        id
        , municipio_id
        , numero_contrato
        , data_contrato
        , documento_negociante
        , nome_negociante
        , updated_at
    from {{ source('tce_ce', 'contratados') }}
)

, stg_contratados as (
    select
        cast(id as varchar) as contratado_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_contrato as varchar) as numero_contrato
        , cast(data_contrato as date) as data_contrato
        , cast(documento_negociante as varchar) as documento_negociante
        , cast(nome_negociante as varchar) as nome_negociante
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_contratados
