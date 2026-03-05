with despesa_extra as (
    select
        balancete_despesa_extra_id as balancete_id
        , 'DESPESA_EXTRA' as tipo_movimento
        , municipio_id
        , ano_exercicio
        , mes_referencia
        , strptime(mes_referencia, '%Y%m')::date as mes_referencia_date
    from {{ ref('stg_balancete_despesa_extra') }}
)

, receita_extra as (
    select
        balancete_receita_extra_id as balancete_id
        , 'RECEITA_EXTRA' as tipo_movimento
        , municipio_id
        , ano_exercicio
        , mes_referencia
        , strptime(mes_referencia, '%Y%m')::date as mes_referencia_date
    from {{ ref('stg_balancete_receita_extra') }}
)

, final as (
    select * from despesa_extra
    union all
    select * from receita_extra
)

select * from final
