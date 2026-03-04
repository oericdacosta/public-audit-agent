with source as (
    select * from {{ source('tce_ce', 'orcamento_receita') }}
)

, renamed as (
    select
        id                                          as orcamento_receita_id
        , municipio_id
        , codigo_receita
        , descricao_receita
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
