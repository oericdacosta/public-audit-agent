with source as (
    select * from {{ source('tce_ce', 'itens_notas_fiscais') }}
)

, renamed as (
    select
        id                                          as item_nota_fiscal_id
        , municipio_id
        , numero_nota_fiscal
        , descricao_item
        , quantidade
        , valor_unitario
        , valor_total
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
