with
contratos_fornecedores as (
    select *
    from {{ ref('int_contratos_fornecedores') }}
)

, final as (
    select *
    from contratos_fornecedores
)

select *
from final
