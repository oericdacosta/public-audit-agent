with
source_data as (
    select
        id
        , codigo_funcao
        , descricao_funcao
        , raw_data
        , updated_at
    from {{ source('tce_ce', 'funcoes') }}
)

, stg_funcoes as (
    select
        cast(id as varchar) as funcao_id
        , cast(codigo_funcao as varchar) as codigo_funcao
        , cast(
            trim(coalesce(descricao_funcao, json_extract_string(raw_data, '$.nome_funcao')))
            as varchar
        ) as descricao_funcao
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_funcoes
