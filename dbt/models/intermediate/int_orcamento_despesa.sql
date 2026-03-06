with
orcamento as (
    select * from {{ ref('stg_orcamento_despesa') }}
)

, funcoes as (
    select
        codigo_funcao
        , descricao_funcao as nome_funcao
    from {{ ref('stg_funcoes') }}
)

, programas as (
    select
        codigo_programa
        , municipio_id
        , ano_exercicio
        , coalesce(descricao_programa, 'Programa ' || codigo_programa) as nome_programa
    from {{ ref('stg_programas') }}
)

, orgaos as (
    select
        codigo_orgao
        , municipio_id
        , ano_exercicio
        , coalesce(descricao_orgao, 'Orgao ' || codigo_orgao) as nome_orgao
    from {{ ref('stg_orgaos') }}
)

, final as (
    select
        orc.orcamento_despesa_id
        , orc.municipio_id
        , orc.ano_exercicio
        , orc.codigo_orgao
        , org.nome_orgao
        , orc.codigo_unidade_orcamentaria
        , orc.codigo_funcao
        , fnc.nome_funcao
        , orc.codigo_subfuncao
        , orc.codigo_programa
        , prg.nome_programa
        , orc.codigo_projeto_atividade
        , orc.numero_projeto_atividade
        , orc.codigo_tipo_orcamento
        , case orc.codigo_tipo_orcamento
            when 'F' then 'Fiscal'
            when 'S' then 'Seguridade Social'
            else orc.codigo_tipo_orcamento
        end as tipo_orcamento
        , orc.nome_projeto_atividade
        , orc.valor_fixado_loa
        , orc.updated_at
    from orcamento as orc
    left join funcoes as fnc
        on orc.codigo_funcao = fnc.codigo_funcao
    left join programas as prg
        on
            orc.codigo_programa = prg.codigo_programa
            and orc.municipio_id = prg.municipio_id
            and orc.ano_exercicio = prg.ano_exercicio
    left join orgaos as org
        on
            orc.codigo_orgao = org.codigo_orgao
            and orc.municipio_id = org.municipio_id
            and orc.ano_exercicio = org.ano_exercicio
)

select * from final
