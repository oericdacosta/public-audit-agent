with
agentes as (
    select *
    from {{ ref('int_agentes_publicos_enriched') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('dim_municipios') }}
)

, final as (
    select
        age.agente_publico_id
        , age.municipio_id
        , mun.nome_municipio
        , age.ano_exercicio
        , age.cpf_servidor
        , age.nome_servidor
        , age.numero_matricula
        , age.cargo
        , age.tipo_cargo
        , age.tipo_cargo_label
        , age.codigo_vinculo
        , age.codigo_ingresso
        , age.situacao_funcional
        , age.situacao_funcional_label
        , age.is_ativo
        , age.is_comissionado
        , age.is_efetivo
        , age.valor_carga_horaria
        , age.faixa_carga_horaria
        , age.updated_at
    from agentes as age
    left join municipios as mun
        on age.municipio_id = mun.municipio_id
)

select *
from final
