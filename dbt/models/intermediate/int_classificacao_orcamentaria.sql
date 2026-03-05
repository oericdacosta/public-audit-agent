with funcoes as (
    select *
    from {{ ref('stg_funcoes') }}
)

, programas as (
    select *
    from {{ ref('stg_programas') }}
)

, orcamento_despesa as (
    select *
    from {{ ref('stg_orcamento_despesa') }}
)

, final as (
    select
        fnc.codigo_funcao
        , fnc.descricao_funcao as nome_funcao
        , prg.codigo_programa
        , orc.codigo_projeto_atividade
        , orc.descricao_projeto_atividade as nome_projeto_atividade
        , prg.ano_exercicio
        , prg.municipio_id
        , coalesce(prg.descricao_programa, 'Programa ' || prg.codigo_programa) as nome_programa
    from programas as prg
    left join funcoes as fnc
        on prg.codigo_programa = fnc.codigo_funcao
    left join orcamento_despesa as orc
        on
            prg.municipio_id = orc.municipio_id
            and prg.ano_exercicio = orc.ano_exercicio
)

select * from final
