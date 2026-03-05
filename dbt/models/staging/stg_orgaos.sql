with
source_data as (
    select
        id
        , municipio_id
        , codigo_orgao
        , descricao_orgao
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'orgaos') }}
)

, stg_orgaos as (
    select
        cast(id as varchar) as orgao_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(codigo_orgao as varchar) as codigo_orgao
        , cast(descricao_orgao as varchar) as descricao_orgao
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_orgaos
