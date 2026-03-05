with
source_data as (
    select
        id
        , municipio_id
        , exercicio_orcamento
        , mes_referencia
        , updated_at
    from {{ source('tce_ce', 'balancete_receita_extra') }}
)

, stg_balancete_receita_extra as (
    select
        cast(id as varchar) as balancete_receita_extra_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(mes_referencia as varchar) as mes_referencia
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_balancete_receita_extra
