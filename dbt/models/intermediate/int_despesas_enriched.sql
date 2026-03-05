with despesas as (
    select *
    from {{ ref('stg_despesas') }}
)

, orgaos as (
    select *
    from {{ ref('int_orgaos_enriched') }}
)

, unidades as (
    select
        codigo_unidade_orcamentaria
        , municipio_id
        , ano_exercicio
        , coalesce(
            descricao_unidade_orcamentaria
            , 'Unidade ' || codigo_unidade_orcamentaria
        ) as nome_unidade_orcamentaria
    from {{ ref('stg_unidades_orcamentarias') }}
)

, classificacao as (
    select *
    from {{ ref('int_classificacao_orcamentaria') }}
)

, final as (
    select
        dep.despesa_id
        , dep.municipio_id
        , dep.ano_exercicio
        , dep.mes_referencia
        , strptime(dep.mes_referencia, '%Y%m')::date as mes_referencia_date
        , dep.codigo_orgao
        , org.nome_orgao
        , dep.codigo_unidade_orcamentaria
        , uni.nome_unidade_orcamentaria
        , dep.codigo_funcao
        , cla.nome_funcao
        , dep.codigo_subfuncao
        , dep.codigo_programa
        , cla.nome_programa
        , dep.codigo_elemento_despesa
        , cla.codigo_projeto_atividade
        , cla.nome_projeto_atividade
        , dep.valor_empenhado
        , dep.valor_liquidado
        , dep.valor_pago
        , dep.updated_at
        , case
            when dep.mes_referencia[5:6] in ('01', '02', '03') then 'T1'
            when dep.mes_referencia[5:6] in ('04', '05', '06') then 'T2'
            when dep.mes_referencia[5:6] in ('07', '08', '09') then 'T3'
            when dep.mes_referencia[5:6] in ('10', '11', '12') then 'T4'
        end as trimestre
        , dep.valor_liquidado - dep.valor_pago as valor_nao_pago
        , case
            when dep.valor_empenhado > 0
                then round(dep.valor_pago / dep.valor_empenhado * 100, 2)
        end as percentual_executado
        , case
            when dep.valor_pago >= dep.valor_empenhado then 'pago_integralmente'
            when dep.valor_pago > 0 then 'pago_parcialmente'
            when dep.valor_liquidado > 0 then 'liquidado_nao_pago'
            else 'empenhado_nao_liquidado'
        end as status_execucao
        , case
            when left(dep.codigo_elemento_despesa, 1) = '3' then 'Despesas Correntes'
            when left(dep.codigo_elemento_despesa, 1) = '4' then 'Despesas de Capital'
            else 'Outros'
        end as grupo_despesa
        , dep.valor_pago >= dep.valor_empenhado as is_pago_integralmente
    from despesas as dep
    left join orgaos as org
        on
            dep.codigo_orgao = org.codigo_orgao
            and dep.municipio_id = org.municipio_id
            and dep.ano_exercicio = org.ano_exercicio
    left join unidades as uni
        on
            dep.codigo_unidade_orcamentaria = uni.codigo_unidade_orcamentaria
            and dep.municipio_id = uni.municipio_id
            and dep.ano_exercicio = uni.ano_exercicio
    left join classificacao as cla
        on
            dep.codigo_funcao = cla.codigo_funcao
            and dep.codigo_programa = cla.codigo_programa
            and dep.ano_exercicio = cla.ano_exercicio
            and dep.municipio_id = cla.municipio_id
)

select * from final
