with
source_data as (
    select
        id
        , municipio_id
        , codigo_unidade_orcamentaria
        , descricao_unidade_orcamentaria
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'unidades_orcamentarias') }}
)

, stg_unidades_orcamentarias as (
    select
        cast(id as varchar) as unidade_orcamentaria_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(codigo_unidade_orcamentaria as varchar) as codigo_unidade_orcamentaria
        , cast(descricao_unidade_orcamentaria as varchar) as descricao_unidade_orcamentaria
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_unidades_orcamentarias
