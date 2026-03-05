with
source_data as (
    select
        id
        , municipio_id
        , numero_licitacao
        , numero_processo
        , objeto_licitacao
        , modalidade_licitacao
        , data_realizacao_licitacao
        , valor_estimado
        , situacao_licitacao
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'licitacoes') }}
)

, stg_licitacoes as (
    select
        cast(id as varchar) as licitacao_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_licitacao as varchar) as numero_licitacao
        , cast(numero_processo as varchar) as numero_processo
        , cast(objeto_licitacao as varchar) as objeto_licitacao
        , cast(modalidade_licitacao as varchar) as modalidade_licitacao
        , try_cast(data_realizacao_licitacao as date) as data_realizacao
        , cast(valor_estimado as decimal(18, 2)) as valor_estimado
        , cast(situacao_licitacao as varchar) as situacao_licitacao
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_licitacoes
