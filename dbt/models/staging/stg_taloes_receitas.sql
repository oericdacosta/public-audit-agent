with source as (
    select * from {{ source('tce_ce', 'taloes_receitas') }}
)

, renamed as (
    select
        id                                          as talao_receita_id
        , municipio_id
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , codigo_municipio
        , codigo_orgao
        , codigo_unidade
        , codigo_rubrica
        , tipo_fonte
        , codigo_fonte
        , numero_talao_receita
        , data_talao_receita
        , data_referencia                             as data_referencia_int
        , valor_receita
        , historico_receita
        , tipo_doc_contribuinte
        , numero_doc_contribuinte
        , nome_razao_social_contribuinte              as nome_contribuinte
        , numero_banco
        , numero_agencia_bancaria                     as numero_agencia
        , numero_conta_corrente
        , numero_doc_credito
        , dt_credito_tr                               as data_credito
        , cast(tipo_doc_credito as varchar)           as tipo_doc_credito
        , updated_at
    from source
)

select * from renamed
