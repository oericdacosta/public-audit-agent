with
source_data as (
    select *
    from {{ ref('stg_municipios') }}
)

, final as (
    select
        municipio_id
        , codigo_municipio
        , nome_municipio
        , updated_at
    from source_data
)

select *
from final
