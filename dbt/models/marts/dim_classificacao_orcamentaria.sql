with
classificacao as (
    select *
    from {{ ref('int_classificacao_orcamentaria') }}
)

, final as (
    select
        md5(
            coalesce(codigo_funcao, '') || '||'
            || coalesce(codigo_programa, '') || '||'
            || coalesce(codigo_projeto_atividade, '') || '||'
            || coalesce(municipio_id, '') || '||'
            || coalesce(cast(ano_exercicio as varchar), '')
        ) as classificacao_sk
        , municipio_id
        , ano_exercicio
        , codigo_funcao
        , nome_funcao
        , codigo_programa
        , nome_programa
        , codigo_projeto_atividade
        , nome_projeto_atividade
        , nome_funcao
        || ' > ' || nome_programa
        || coalesce(' > ' || nome_projeto_atividade, '')
            as hierarquia_completa
    from classificacao
)

select *
from final
