with
source_data as (
    select
        id
        , municipio_id
        , codigo_receita
        , descricao_receita
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'orcamento_receita') }}
)

, stg_orcamento_receita as (
    select
        cast(id as varchar) as orcamento_receita_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(codigo_receita as varchar) as codigo_receita
        , cast(descricao_receita as varchar) as descricao_receita
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_orcamento_receita
