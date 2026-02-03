with
licitacoes as (
    select
        licitacao_id
        , municipio_id
        , numero_licitacao
        , numero_processo
        , objeto_licitacao
        , modalidade_licitacao
        , data_realizacao
        , valor_estimado
        , situacao_licitacao
        , ano_exercicio
        , data_carga
    from {{ ref('stg_licitacoes') }}
)

, enriched as (
    select
        licitacao_id
        , municipio_id
        , numero_licitacao
        , numero_processo
        , objeto_licitacao
        , modalidade_licitacao
        , data_realizacao
        , valor_estimado
        , situacao_licitacao
        , ano_exercicio
        , data_carga
        , case
            when modalidade_licitacao = '1' then 'Convite'
            when modalidade_licitacao = '2' then 'Tomada de Preços'
            when modalidade_licitacao = '3' then 'Concorrência'
            when modalidade_licitacao = '4' then 'Concurso'
            when modalidade_licitacao = '5' then 'Pregão'
            when modalidade_licitacao = '6' then 'Dispensada'
            when modalidade_licitacao = '7' then 'Inexigível'
            else 'Outros'
        end as nome_modalidade
        , case
            when valor_estimado > 1000000 then 'Alto Custo'
            when valor_estimado between 80000 and 1000000 then 'Médio Custo'
            else 'Baixo Custo'
        end as faixa_valor_estimado
    from licitacoes
)

select *
from enriched
