with
source_data as (
    select *
    from {{ ref('seed_entidades') }}
)

, final as (
    select
        cast(municipio_id as varchar) as municipio_id
        , lower(nome_municipio) as nome_municipio
        , uf
    from source_data
)

select *
from final
