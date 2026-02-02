with
source as (
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
    from {{ source('civic_audit_duckdb', 'licitacoes') }}
)

, renamed as (
    select
        cast(id as varchar) as licitacao_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_licitacao as varchar) as numero_licitacao
        , cast(numero_processo as varchar) as numero_processo
        , cast(objeto_licitacao as varchar) as objeto_licitacao
        , cast(modalidade_licitacao as varchar) as modalidade_licitacao
        , cast(data_realizacao_licitacao as varchar) as data_realizacao
        , cast(valor_estimado as double) as valor_estimado
        , cast(situacao_licitacao as varchar) as situacao_licitacao
        , cast(exercicio_orcamento as int) as ano_exercicio
        , cast(updated_at as timestamp) as data_carga
    from source
)

select *
from renamed
