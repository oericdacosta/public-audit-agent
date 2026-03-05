with
source_data as (
    select
        id
        , municipio_id
        , codigo_ordenador
        , nome_ordenador
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'ordenadores') }}
)

, stg_ordenadores as (
    select
        cast(id as varchar) as ordenador_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(codigo_ordenador as varchar) as codigo_ordenador
        , cast(nome_ordenador as varchar) as nome_ordenador
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_ordenadores
