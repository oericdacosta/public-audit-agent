with source as (
    select * from {{ source('tce_ce', 'funcoes') }}
)

, renamed as (
    select
        id                                              as funcao_id
        , codigo_funcao
        , updated_at
        , coalesce(
            descricao_funcao
            , json_extract_string(raw_data, '$.nome_funcao')
        )                                               as descricao_funcao
    from source
)

select * from renamed
