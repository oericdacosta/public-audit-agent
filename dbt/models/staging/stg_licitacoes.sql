with source as (
    select * from {{ source('tce_ce', 'licitacoes') }}
)

, renamed as (
    select
        -- ids
        id                                              as licitacao_id
        , municipio_id

        -- identifiers
        , numero_licitacao
        , numero_processo

        -- descriptions
        , objeto_licitacao
        , modalidade_licitacao

        -- dates
        , data_realizacao_licitacao                       as data_realizacao

        -- amounts
        , valor_estimado

        -- status
        , situacao_licitacao

        -- dates
        , cast(exercicio_orcamento as integer)            as ano_exercicio

        -- metadata
        , updated_at                                      as data_carga

    from source
)

select * from renamed
