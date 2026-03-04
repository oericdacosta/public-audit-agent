with source as (
    select * from {{ source('tce_ce', 'taloes_extras') }}
)

, renamed as (
    select
        id                                          as talao_extra_id
        , municipio_id
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , cast(codigo_municipio as varchar)           as codigo_municipio
        , cast(codigo_orgao as varchar)               as codigo_orgao
        , codigo_unidade
        , cast(cd_conta_ctx as varchar)               as codigo_conta_extra
        , nu_talao_receita_tx                         as numero_talao
        , dt_talao_receita_tx                         as data_talao
        , dt_ref_tx                                   as data_referencia_int
        , vl_receita_tx                               as valor_receita
        , de_hist_receita_tx                          as historico_receita
        , tp_doc_contrib_tx                           as tipo_doc_contribuinte
        , nu_doc_contrib_tx                           as numero_doc_contribuinte
        , nm_razao_social_contrib_tx                  as nome_contribuinte
        , nu_banco_tx                                 as numero_banco
        , nu_agencia_bancaria_tx                      as numero_agencia
        , nu_conta_corrente_tx                        as numero_conta_corrente
        , nu_doc_credito_tx                           as numero_doc_credito
        , dt_credito_tx                               as data_credito
        , cast(tp_doc_credito_tx as varchar)          as tipo_doc_credito
        , updated_at
    from source
)

select * from renamed
