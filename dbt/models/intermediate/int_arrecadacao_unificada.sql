with taloes_receitas as (
    select
        talao_receita_id as talao_id
        , 'ORCAMENTARIA' as tipo_arrecadacao
        , municipio_id
        , ano_exercicio
        , codigo_orgao
        , codigo_unidade
        , numero_talao_receita as numero_talao
        , data_talao_receita as data_talao
        , data_referencia_int
        , valor_receita
        , historico_receita
        , nome_contribuinte
        , numero_banco
        , numero_agencia
        , numero_conta_corrente
        , data_credito
        , codigo_rubrica
        , tipo_fonte
        , codigo_fonte
        , null::integer as codigo_conta_extra
        , date_trunc('month', data_talao_receita) as mes_arrecadacao
    from {{ ref('stg_taloes_receitas') }}
)

, taloes_extras as (
    select
        talao_extra_id as talao_id
        , 'EXTRA_ORCAMENTARIA' as tipo_arrecadacao
        , municipio_id
        , ano_exercicio
        , codigo_orgao
        , codigo_unidade
        , numero_talao
        , data_talao
        , data_referencia_int
        , valor_receita
        , historico_receita
        , nome_contribuinte
        , numero_banco
        , numero_agencia
        , numero_conta_corrente
        , data_credito
        , null::varchar as codigo_rubrica
        , null::varchar as tipo_fonte
        , null::varchar as codigo_fonte
        , codigo_conta_extra
        , date_trunc('month', data_talao) as mes_arrecadacao
    from {{ ref('stg_taloes_extras') }}
)

, final as (
    select * from taloes_receitas
    union all
    select * from taloes_extras
)

select * from final
