with receitas as (
    select *
    from {{ ref('stg_receitas') }}
)

, orgaos as (
    select *
    from {{ ref('stg_orgaos') }}
)

, unidades as (
    select *
    from {{ ref('stg_unidades_orcamentarias') }}
)

, final as (
    select
        rec.receita_id
        , rec.municipio_id
        , rec.ano_exercicio
        , rec.mes_referencia
        , strptime(rec.mes_referencia, '%Y%m')::date as mes_referencia_date
        , rec.codigo_orgao
        , rec.codigo_unidade_orcamentaria
        , rec.codigo_receita
        , rec.descricao_receita
        , rec.valor_orcado
        , rec.valor_arrecadado
        , rec.updated_at
        , case
            when rec.mes_referencia[5:6] in ('01', '02', '03') then 'T1'
            when rec.mes_referencia[5:6] in ('04', '05', '06') then 'T2'
            when rec.mes_referencia[5:6] in ('07', '08', '09') then 'T3'
            when rec.mes_referencia[5:6] in ('10', '11', '12') then 'T4'
        end as trimestre
        , coalesce(org.descricao_orgao, 'Orgao ' || rec.codigo_orgao) as nome_orgao
        , coalesce(
            uni.descricao_unidade_orcamentaria, 'Unidade ' || rec.codigo_unidade_orcamentaria
        ) as nome_unidade_orcamentaria
        , case
            when rec.valor_orcado > 0
                then round(rec.valor_arrecadado / rec.valor_orcado * 100, 2)
        end as percentual_arrecadado
        , rec.valor_arrecadado - rec.valor_orcado as desvio_arrecadacao
        , case
            when rec.valor_orcado is null or rec.valor_orcado = 0 then 'sem_meta'
            when rec.valor_arrecadado >= rec.valor_orcado * 1.05 then 'superavit'
            when rec.valor_arrecadado >= rec.valor_orcado * 0.9 then 'dentro_meta'
            when rec.valor_arrecadado > 0 then 'abaixo_meta'
            else 'nao_arrecadado'
        end as status_arrecadacao
        , rec.valor_arrecadado < rec.valor_orcado * 0.9 as is_abaixo_meta
    from receitas as rec
    left join orgaos as org
        on
            rec.codigo_orgao = org.codigo_orgao
            and rec.municipio_id = org.municipio_id
            and rec.ano_exercicio = org.ano_exercicio
    left join unidades as uni
        on
            rec.codigo_unidade_orcamentaria = uni.codigo_unidade_orcamentaria
            and rec.municipio_id = uni.municipio_id
            and rec.ano_exercicio = uni.ano_exercicio
)

select * from final
