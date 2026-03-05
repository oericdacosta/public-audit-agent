with licitacoes as (
    select *
    from {{ ref('stg_licitacoes') }}
)

, licitantes_agg as (
    select
        numero_licitacao
        , municipio_id
        , count(distinct nome_negociante) as quantidade_licitantes
    from {{ ref('stg_licitantes') }}
    group by numero_licitacao, municipio_id
)

, itens_agg as (
    select
        numero_licitacao
        , municipio_id
        , count(*) as total_itens
        , sum(valor_vencedor) as valor_total_vencedor
    from {{ ref('stg_itens_licitacoes') }}
    group by numero_licitacao, municipio_id
)

, final as (
    select
        lic.licitacao_id
        , lic.municipio_id
        , lic.ano_exercicio
        , lic.numero_licitacao
        , lic.numero_processo
        , lic.objeto_licitacao
        , lic.modalidade_licitacao
        , lic.data_realizacao
        , extract(year from lic.data_realizacao)::integer as ano_realizacao
        , lic.valor_estimado
        , lic.situacao_licitacao
        , lit.quantidade_licitantes
        , ite.total_itens
        , ite.valor_total_vencedor
        , lic.updated_at
        , case
            when lic.modalidade_licitacao = '1' then 'Convite'
            when lic.modalidade_licitacao = '2' then 'Tomada de Preços'
            when lic.modalidade_licitacao = '3' then 'Concorrência'
            when lic.modalidade_licitacao = '4' then 'Concurso'
            when lic.modalidade_licitacao = '5' then 'Pregão'
            when lic.modalidade_licitacao = '6' then 'Dispensa de Licitação'
            when lic.modalidade_licitacao = '7' then 'Inexigibilidade'
            else 'Outros'
        end as modalidade_licitacao_label
        , lic.modalidade_licitacao in ('6', '7') as is_dispensa
        , lic.modalidade_licitacao = '5' as is_pregao
        , lic.valor_estimado > 650000 as is_alto_valor
        , case
            when lic.valor_estimado > 650000 then 'acima de R$650k'
            when lic.valor_estimado > 100000 then 'R$100k a R$650k'
            when lic.valor_estimado is not null then 'até R$100k'
            else 'não informado'
        end as faixa_valor
        , coalesce(lit.quantidade_licitantes, 0) = 0 as flag_licitacao_deserta
        , lit.quantidade_licitantes = 1 as flag_unico_participante
    from licitacoes as lic
    left join licitantes_agg as lit
        on
            lic.numero_licitacao = lit.numero_licitacao
            and lic.municipio_id = lit.municipio_id
    left join itens_agg as ite
        on
            lic.numero_licitacao = ite.numero_licitacao
            and lic.municipio_id = ite.municipio_id
)

select * from final
