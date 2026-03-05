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
    from funcao_ano as fan
    left join municipios as mun
        on fan.municipio_id = mun.municipio_id
)

select *
from final
