with source as (
    select * from {{ source('tce_ce', 'despesas') }}
)

, renamed as (
    select
        -- ids
        id                                              as despesa_id
        , municipio_id

        -- dates
        , cast(exercicio_orcamento as integer)            as ano_exercicio
        , mes_referencia

        -- classifications
        , codigo_orgao
        , codigo_unidade_orcamentaria
        , codigo_funcao
        , codigo_subfuncao
        , codigo_programa
        , codigo_elemento_despesa

        -- amounts
        , valor_empenhado
        , valor_liquidado
        , valor_pago

        -- metadata
        , updated_at                                      as data_carga

    from source
)

select * from renamed
