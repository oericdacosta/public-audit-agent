with
source_data as (
    select *
    from {{ ref('seed_entidades') }}
)

, final as (
    select
        municipio_id
        , nome_municipio
        , uf
    from source_data
)

select *
from final
