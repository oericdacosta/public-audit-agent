with source as (
    select * from {{ source('tce_ce', 'orcamento_despesa') }}
)

, renamed as (
    select
        id                                          as orcamento_despesa_id
        , municipio_id
        , codigo_projeto_atividade
        , descricao_projeto_atividade
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
