with source as (
    select * from {{ source('tce_ce', 'liquidacoes') }}
)

, renamed as (
    select
        id                                          as liquidacao_id
        , municipio_id
        , numero_empenho
        , data_liquidacao
        , valor_liquidado
        , nome_responsavel_liquidacao
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
