with
source_data as (
    select
        id
        , codigo_municipio
        , nome_municipio
        , uf
        , raw_data
        , updated_at
    from {{ source('tce_ce', 'municipios') }}
)

, stg_municipios as (
    select
        cast(id as varchar) as municipio_id
        , cast(codigo_municipio as varchar) as codigo_municipio
        , cast(nome_municipio as varchar) as nome_municipio
        , cast(
            coalesce(uf, json_extract_string(raw_data, '$.uf'))
            as varchar
        ) as uf
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_municipios
