with
source_data as (
    select
        id
        , municipio_id
        , numero_empenho
        , data_liquidacao
        , valor_liquidado
        , nome_responsavel_liquidacao
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'liquidacoes') }}
)

, stg_liquidacoes as (
    select
        cast(id as varchar) as liquidacao_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_empenho as varchar) as numero_empenho
        , cast(data_liquidacao as date) as data_liquidacao
        , cast(valor_liquidado as decimal(18, 2)) as valor_liquidado
        , cast(nome_responsavel_liquidacao as varchar) as nome_responsavel_liquidacao
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_liquidacoes
