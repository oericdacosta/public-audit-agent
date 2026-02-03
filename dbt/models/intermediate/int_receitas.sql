with
receitas as (
    select
        receita_id
        , municipio_id
        , ano_exercicio
        , mes_referencia
        , codigo_orgao
        , codigo_unidade_orcamentaria
        , codigo_receita
        , descricao_receita
        , valor_orcado
        , valor_arrecadado
        , data_carga
    from {{ ref('stg_receitas') }}
)

, enriched as (
    select
        receita_id
        , municipio_id
        , ano_exercicio
        , mes_referencia
        , codigo_orgao
        , codigo_unidade_orcamentaria
        , codigo_receita
        , descricao_receita
        , valor_orcado
        , valor_arrecadado
        , data_carga
        , case
            when valor_orcado > 0 then (valor_arrecadado / valor_orcado)
            else 0
        end as percentual_realizacao
    from receitas
)

select *
from enriched
