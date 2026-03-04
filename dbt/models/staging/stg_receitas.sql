with source as (
    select * from {{ source('tce_ce', 'receitas') }}
)

, renamed as (
    select
        -- ids
        id                                              as receita_id
        , municipio_id

        -- dates
        , cast(exercicio_orcamento as integer)            as ano_exercicio
        , mes_referencia

        -- classifications
        , codigo_orgao
        , codigo_unidade_orcamentaria
        , codigo_receita
        , descricao_receita

        -- amounts
        , valor_orcado
        , valor_arrecadado

        -- metadata
        , updated_at                                      as data_carga

    from source
)

select * from renamed
