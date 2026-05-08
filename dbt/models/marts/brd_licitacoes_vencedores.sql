with
itens as (
    select *
    from {{ ref('stg_itens_licitacoes') }}
)

, licitacoes as (
    select
        licitacao_id
        , numero_licitacao
        , municipio_id
        , nome_municipio
        , ano_exercicio
        , modalidade_licitacao_label
        , data_realizacao
    from {{ ref('fct_licitacoes') }}
)

, dedup_licitacoes as (
    select *
    from licitacoes
    qualify
        row_number() over (partition by numero_licitacao, municipio_id order by licitacao_id) = 1
)

, final as (
    select
        it.item_licitacao_id
        , lic.licitacao_id
        , it.municipio_id
        , lic.nome_municipio
        , it.numero_licitacao
        , lic.ano_exercicio
        , lic.modalidade_licitacao_label
        , lic.data_realizacao as data_realizacao_licitacao
        , it.numero_sequencial_item
        , it.descricao_item
        , it.nome_vencedor
        , it.quantidade
        , it.valor_unitario
        , it.valor_vencedor as valor_adjudicado
        , it.updated_at
    from itens as it
    left join dedup_licitacoes as lic
        on
            it.numero_licitacao = lic.numero_licitacao
            and it.municipio_id = lic.municipio_id
)

select *
from final
