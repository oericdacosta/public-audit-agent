with source as (
    select * from {{ source('tce_ce', 'itens_licitacoes') }}
)

, renamed as (
    select
        id                                          as item_licitacao_id
        , municipio_id
        , numero_licitacao
        , data_realizacao_licitacao
        , numero_sequencial_item
        , descricao_item
        , valor_vencedor
        , quantidade
        , valor_unitario
        , nome_vencedor
        , updated_at
    from source
)

select * from renamed
