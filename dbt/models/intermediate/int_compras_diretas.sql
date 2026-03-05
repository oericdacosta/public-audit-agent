with licitacoes_dispensa as (
    select *
    from {{ ref('int_licitacoes_enriched') }}
    where is_dispensa = true
)

, final as (
    select
        licitacao_id
        , municipio_id
        , ano_exercicio
        , numero_licitacao
        , numero_processo
        , objeto_licitacao
        , modalidade_licitacao
        , modalidade_licitacao_label
        , is_dispensa
        , is_pregao
        , data_realizacao
        , ano_realizacao
        , valor_estimado
        , is_alto_valor
        , faixa_valor
        , situacao_licitacao
        , flag_licitacao_deserta
        , flag_unico_participante
        , quantidade_licitantes
        , total_itens
        , valor_total_vencedor
        , updated_at
        , valor_estimado > 50000 as flag_valor_acima_limite_dispensa
    from licitacoes_dispensa
)

select * from final
