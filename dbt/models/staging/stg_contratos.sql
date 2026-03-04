with source as (
    select * from {{ source('tce_ce', 'contratos') }}
)

, renamed as (
    select
        id                                          as contrato_id
        , municipio_id
        , numero_contrato
        , data_contrato
        , data_inicio_vigencia
        , data_fim_vigencia
        , valor_total
        , descricao_objeto
        , tipo_contrato
        , updated_at
    from source
)

select * from renamed
