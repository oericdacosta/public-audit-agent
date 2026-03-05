with
source_data as (
    select
        id
        , municipio_id
        , numero_banco
        , numero_agencia
        , numero_conta
        , descricao_conta
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'contas_bancarias') }}
)

, stg_contas_bancarias as (
    select
        cast(id as varchar) as conta_bancaria_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_banco as varchar) as numero_banco
        , cast(numero_agencia as varchar) as numero_agencia
        , cast(numero_conta as varchar) as numero_conta
        , cast(descricao_conta as varchar) as descricao_conta
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_contas_bancarias
