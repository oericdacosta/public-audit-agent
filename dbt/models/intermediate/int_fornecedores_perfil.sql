with licitantes_base as (
    select
        nome_negociante
        , documento_negociante
        , numero_licitacao
        , municipio_id
        , data_realizacao_licitacao
    from {{ ref('stg_licitantes') }}
)

, licitantes_agg as (
    select
        nome_negociante
        , max(documento_negociante) as documento_negociante
        , count(distinct numero_licitacao) as total_licitacoes_participou
        , count(distinct municipio_id) as municipios_distintos
        , min(data_realizacao_licitacao) as primeira_licitacao_em
        , max(data_realizacao_licitacao) as ultima_licitacao_em
    from licitantes_base
    group by nome_negociante
)

select * from licitantes_agg
