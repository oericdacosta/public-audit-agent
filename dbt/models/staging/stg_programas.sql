with
source_data as (
    select
        id
        , municipio_id
        , codigo_programa
        , descricao_programa
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'programas') }}
)

, stg_programas as (
    select
        cast(id as varchar) as programa_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(codigo_programa as varchar) as codigo_programa
        , cast(descricao_programa as varchar) as descricao_programa
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_programas
