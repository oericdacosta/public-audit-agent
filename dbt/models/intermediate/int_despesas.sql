with despesas as (
    select
        despesa_id
        , municipio_id
        , ano_exercicio
        , mes_referencia
        , codigo_orgao
        , codigo_unidade_orcamentaria
        , codigo_funcao
        , codigo_subfuncao
        , codigo_programa
        , codigo_elemento_despesa
        , valor_empenhado
        , valor_liquidado
        , valor_pago
        , data_carga
    from {{ ref('stg_despesas') }}
)

, enriched as (
    select
        despesa_id
        , municipio_id
        , ano_exercicio
        , mes_referencia
        , codigo_orgao
        , codigo_unidade_orcamentaria
        , codigo_funcao
        , codigo_subfuncao
        , codigo_programa
        , codigo_elemento_despesa
        , valor_empenhado
        , valor_liquidado
        , valor_pago
        , data_carga
        , case
            when codigo_funcao = '01' then 'Legislativa'
            when codigo_funcao = '04' then 'Administração'
            when codigo_funcao = '06' then 'Segurança Pública'
            when codigo_funcao = '08' then 'Assistência Social'
            when codigo_funcao = '10' then 'Saúde'
            when codigo_funcao = '12' then 'Educação'
            when codigo_funcao = '15' then 'Urbanismo'
            when codigo_funcao = '18' then 'Gestão Ambiental'
            when codigo_funcao = '27' then 'Desporto e Lazer'
            else 'Outros'
        end as nome_funcao_macro
        , coalesce(valor_pago >= valor_liquidado, false) as is_pago_totalmente
    from despesas
)

select *
from enriched
