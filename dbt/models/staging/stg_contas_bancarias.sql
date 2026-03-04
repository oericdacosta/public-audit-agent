with source as (
    select * from {{ source('tce_ce', 'contas_bancarias') }}
)

, renamed as (
    select
        id                                          as conta_bancaria_id
        , municipio_id
        , numero_banco
        , numero_agencia
        , numero_conta
        , descricao_conta
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
