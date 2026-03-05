with
source_data as (
    select
        id
        , municipio_id
        , exercicio_orcamento
        , codigo_municipio
        , codigo_orgao
        , codigo_unidade
        , cd_conta_ctx
        , nu_talao_receita_tx
        , dt_talao_receita_tx
        , dt_ref_tx
        , vl_receita_tx
        , de_hist_receita_tx
        , tp_doc_contrib_tx
        , nu_doc_contrib_tx
        , nm_razao_social_contrib_tx
        , nu_banco_tx
        , nu_agencia_bancaria_tx
        , nu_conta_corrente_tx
        , nu_doc_credito_tx
        , dt_credito_tx
        , tp_doc_credito_tx
        , updated_at
    from {{ source('tce_ce', 'taloes_extras') }}
)

, stg_taloes_extras as (
    select
        cast(id as varchar) as talao_extra_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(codigo_municipio as varchar) as codigo_municipio
        , cast(codigo_orgao as varchar) as codigo_orgao
        , cast(trim(codigo_unidade) as varchar) as codigo_unidade
        , cast(cd_conta_ctx as integer) as codigo_conta_extra
        , cast(nu_talao_receita_tx as varchar) as numero_talao
        , cast(dt_talao_receita_tx as date) as data_talao
        , cast(dt_ref_tx as integer) as data_referencia_int
        , cast(vl_receita_tx as decimal(18, 2)) as valor_receita
        , cast(de_hist_receita_tx as varchar) as historico_receita
        , cast(tp_doc_contrib_tx as varchar) as tipo_doc_contribuinte
        , cast(nu_doc_contrib_tx as varchar) as numero_doc_contribuinte
        , cast(nm_razao_social_contrib_tx as varchar) as nome_contribuinte
        , cast(nu_banco_tx as varchar) as numero_banco
        , cast(nu_agencia_bancaria_tx as varchar) as numero_agencia
        , cast(nu_conta_corrente_tx as varchar) as numero_conta_corrente
        , cast(nu_doc_credito_tx as varchar) as numero_doc_credito
        , cast(dt_credito_tx as date) as data_credito
        , cast(tp_doc_credito_tx as integer) as tipo_doc_credito
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_taloes_extras
