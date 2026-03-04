with source as (
    select * from {{ source('tce_ce', 'municipios') }}
)

, renamed as (
    select
        id                                              as municipio_id
        , codigo_municipio
        , nome_municipio
        , updated_at
        , coalesce(
            uf
            , json_extract_string(raw_data, '$.uf')
        )                                               as uf
    from source
)

select * from renamed
