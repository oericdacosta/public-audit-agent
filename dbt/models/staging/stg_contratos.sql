with
source_data as (
    select
        id
        , municipio_id
        , numero_contrato
        , data_contrato
        , data_inicio_vigencia
        , data_fim_vigencia
        , valor_total
        , descricao_objeto
        , tipo_contrato
        , updated_at
    from {{ source('tce_ce', 'contratos') }}
)

, stg_contratos as (
    select
        cast(id as varchar) as contrato_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_contrato as varchar) as numero_contrato
        , cast(data_contrato as date) as data_contrato
        , cast(data_inicio_vigencia as date) as data_inicio_vigencia
        , cast(data_fim_vigencia as date) as data_fim_vigencia
        , cast(valor_total as decimal(18, 2)) as valor_total
        , cast(descricao_objeto as varchar) as descricao_objeto
        , cast(tipo_contrato as varchar) as tipo_contrato
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_contratos
