with
source_data as (
    select
        id
        , municipio_id
        , exercicio_orcamento
        , codigo_municipio
        , codigo_orgao
        , codigo_unidade
        , codigo_rubrica
        , tipo_fonte
        , codigo_fonte
        , numero_talao_receita
        , data_talao_receita
        , data_referencia
        , valor_receita
        , historico_receita
        , tipo_doc_contribuinte
        , numero_doc_contribuinte
        , nome_razao_social_contribuinte
        , numero_banco
        , numero_agencia_bancaria
        , numero_conta_corrente
        , numero_doc_credito
        , dt_credito_tr
        , tipo_doc_credito
        , updated_at
    from {{ source('tce_ce', 'taloes_receitas') }}
)

, stg_taloes_receitas as (
    select
        cast(id as varchar) as talao_receita_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(codigo_municipio as varchar) as codigo_municipio
        , cast(codigo_orgao as varchar) as codigo_orgao
        , cast(trim(codigo_unidade) as varchar) as codigo_unidade
        , cast(codigo_rubrica as varchar) as codigo_rubrica
        , cast(tipo_fonte as varchar) as tipo_fonte
        , cast(codigo_fonte as varchar) as codigo_fonte
        , cast(numero_talao_receita as varchar) as numero_talao_receita
        , cast(data_talao_receita as date) as data_talao_receita
        , cast(data_referencia as integer) as data_referencia_int
        , cast(valor_receita as decimal(18, 2)) as valor_receita
        , cast(historico_receita as varchar) as historico_receita
        , cast(tipo_doc_contribuinte as varchar) as tipo_doc_contribuinte
        , cast(numero_doc_contribuinte as varchar) as numero_doc_contribuinte
        , cast(nome_razao_social_contribuinte as varchar) as nome_contribuinte
        , cast(numero_banco as varchar) as numero_banco
        , cast(numero_agencia_bancaria as varchar) as numero_agencia
        , cast(numero_conta_corrente as varchar) as numero_conta_corrente
        , cast(numero_doc_credito as varchar) as numero_doc_credito
        , cast(dt_credito_tr as date) as data_credito
        , cast(tipo_doc_credito as integer) as tipo_doc_credito
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_taloes_receitas
