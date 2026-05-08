with
movimentos as (
    select *
    from {{ ref('int_movimentos_extra_orcamentarios') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('dim_municipios') }}
)

, final as (
    select
        mov.municipio_id
        , mun.nome_municipio
        , mov.ano_exercicio
        , mov.mes_referencia
        , mov.mes_referencia_date
        , mov.tipo_movimento
        , count(*) as total_registros
    from movimentos as mov
    left join municipios as mun
        on mov.municipio_id = mun.municipio_id
    group by
        mov.municipio_id
        , mun.nome_municipio
        , mov.ano_exercicio
        , mov.mes_referencia
        , mov.mes_referencia_date
        , mov.tipo_movimento
)

select *
from final
