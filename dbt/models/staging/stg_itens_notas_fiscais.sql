with
source_data as (
    select
        id
        , municipio_id
        , numero_nota_fiscal
        , descricao_item
        , quantidade
        , valor_unitario
        , valor_total
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'itens_notas_fiscais') }}
)

, stg_itens_notas_fiscais as (
    select
        cast(id as varchar) as item_nota_fiscal_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_nota_fiscal as varchar) as numero_nota_fiscal
        , cast(descricao_item as varchar) as descricao_item
        , cast(quantidade as double) as quantidade
        , cast(valor_unitario as decimal(18, 2)) as valor_unitario
        , cast(valor_total as decimal(18, 2)) as valor_total
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_itens_notas_fiscais
