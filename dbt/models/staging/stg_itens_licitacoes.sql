with
source_data as (
    select
        id
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
    from {{ source('tce_ce', 'itens_licitacoes') }}
)

, stg_itens_licitacoes as (
    select
        cast(id as varchar) as item_licitacao_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_licitacao as varchar) as numero_licitacao
        , cast(data_realizacao_licitacao as date) as data_realizacao_licitacao
        , cast(numero_sequencial_item as integer) as numero_sequencial_item
        , cast(descricao_item as varchar) as descricao_item
        , cast(valor_vencedor as decimal(18, 2)) as valor_vencedor
        , cast(quantidade as varchar) as quantidade
        , cast(valor_unitario as decimal(18, 2)) as valor_unitario
        , cast(nome_vencedor as varchar) as nome_vencedor
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_itens_licitacoes
