with contratados_base as (
    select
        nome_negociante
        , numero_contrato
        , municipio_id
        , data_contrato
    from {{ ref('stg_contratados') }}
)

, licitantes_base as (
    select
        nome_negociante
        , numero_licitacao
        , municipio_id
    from {{ ref('stg_licitantes') }}
)

, contratados_agg as (
    select
        nome_negociante
        , count(distinct numero_contrato) as total_contratos
        , count(distinct municipio_id) as municipios_distintos
        , min(data_contrato) as primeiro_contrato_em
        , max(data_contrato) as ultimo_contrato_em
    from contratados_base
    group by nome_negociante
)

, licitantes_agg as (
    select
        nome_negociante
        , count(distinct numero_licitacao) as total_licitacoes_participou
    from licitantes_base
    group by nome_negociante
)

, final as (
    select
        con.nome_negociante
        , con.total_contratos
        , con.municipios_distintos
        , con.primeiro_contrato_em
        , con.ultimo_contrato_em
        , coalesce(lit.total_licitacoes_participou, 0) as total_licitacoes_participou
    from contratados_agg as con
    left join licitantes_agg as lit
        on con.nome_negociante = lit.nome_negociante
)

select * from final
