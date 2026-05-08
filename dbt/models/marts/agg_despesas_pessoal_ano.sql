-- Despesas de pessoal: grupo_despesa = 'Despesas Correntes' + codigo_elemento_despesa
-- que começa com '31' (Pessoal e Encargos Sociais na classificação brasileira).
-- Inclui vencimentos, gratificações, encargos patronais (INSS, PASEP etc.).
with
despesas as (
    select *
    from {{ ref('fct_despesas') }}
    where
        left(codigo_elemento_despesa, 2) = '31'
)

, final as (
    select
        dep.municipio_id
        , dep.nome_municipio
        , dep.ano_exercicio
        , dep.codigo_orgao
        , dep.nome_orgao
        , dep.codigo_elemento_despesa
        , sum(dep.valor_empenhado) as total_empenhado_pessoal
        , sum(dep.valor_liquidado) as total_liquidado_pessoal
        , sum(dep.valor_pago) as total_pago_pessoal
        , count(distinct dep.despesa_id) as total_registros
    from despesas as dep
    group by
        dep.municipio_id
        , dep.nome_municipio
        , dep.ano_exercicio
        , dep.codigo_orgao
        , dep.nome_orgao
        , dep.codigo_elemento_despesa
)

select *
from final
