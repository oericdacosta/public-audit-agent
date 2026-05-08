with
funcao_ano as (
    select *
    from {{ ref('int_despesas_por_funcao_ano') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('dim_municipios') }}
)

, quality as (
    select
        municipio_id
        , ano_exercicio
        , nome_funcao
        , status_qualidade
        , explicacao_qualidade
        , anos_com_historico_nao_zero
    from {{ ref('agg_data_quality') }}
)

, final as (
    select
        fan.municipio_id
        , mun.nome_municipio
        , fan.ano_exercicio
        , fan.codigo_funcao
        , fan.nome_funcao
        , fan.total_empenhado_ano
        , fan.total_liquidado_ano
        , fan.total_pago_ano
        , fan.percentual_executado
        , fan.percentual_orcamento_total
        , fan.rank_funcao_no_ano
        , q.status_qualidade
        , q.explicacao_qualidade
        , q.anos_com_historico_nao_zero
    from funcao_ano as fan
    left join municipios as mun
        on fan.municipio_id = mun.municipio_id
    left join quality as q
        on
            fan.municipio_id = q.municipio_id
            and fan.ano_exercicio = q.ano_exercicio
            and fan.nome_funcao = q.nome_funcao
)

select *
from final
