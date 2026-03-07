with funcoes as (
    select
        codigo_funcao
        , descricao_funcao as nome_funcao
    from {{ ref('stg_funcoes') }}
    qualify row_number() over (partition by codigo_funcao order by updated_at desc) = 1
)

, programas as (
    select
        codigo_programa
        , municipio_id
        , ano_exercicio
        , coalesce(descricao_programa, 'Programa ' || codigo_programa) as nome_programa
    from {{ ref('stg_programas') }}
)

, orcamento_despesa as (
    select
        codigo_funcao
        , codigo_programa
        , codigo_projeto_atividade
        , nome_projeto_atividade
        , municipio_id
        , ano_exercicio
    from {{ ref('stg_orcamento_despesa') }}
    qualify row_number() over (
        partition by
            codigo_funcao
            , codigo_programa
            , codigo_projeto_atividade
            , municipio_id
            , ano_exercicio
        order by nome_projeto_atividade desc nulls last
    ) = 1
)

, final as (
    select
        orc.codigo_funcao
        , fnc.nome_funcao
        , orc.codigo_programa
        , prg.nome_programa
        , orc.codigo_projeto_atividade
        , orc.nome_projeto_atividade
        , orc.municipio_id
        , orc.ano_exercicio
    from orcamento_despesa as orc
    left join funcoes as fnc
        on orc.codigo_funcao = fnc.codigo_funcao
    left join programas as prg
        on
            orc.codigo_programa = prg.codigo_programa
            and orc.municipio_id = prg.municipio_id
            and orc.ano_exercicio = prg.ano_exercicio
)

select * from final
