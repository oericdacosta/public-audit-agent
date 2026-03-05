with
licitacoes_risco as (
    select *
    from {{ ref('int_licitacoes_risco') }}
)

, final as (
    select *
    from licitacoes_risco
)

select *
from final
