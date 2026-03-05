with agentes as (
    select *
    from {{ ref('stg_agentes_publicos') }}
)

, final as (
    select
        ap.agente_publico_id
        , ap.municipio_id
        , ap.ano_exercicio
        , ap.cpf_servidor
        , ap.nome_servidor
        , ap.numero_matricula
        , ap.cargo
        , ap.tipo_cargo
        , ap.situacao_funcional
        , ap.codigo_vinculo
        , ap.codigo_ingresso
        , ap.valor_carga_horaria
        , ap.updated_at
        , case
            when ap.tipo_cargo = '00' then 'Não informado'
            when ap.tipo_cargo in ('01', '1') then 'Efetivo'
            when ap.tipo_cargo in ('02', '2') then 'Comissionado'
            when ap.tipo_cargo in ('03', '3') then 'Temporário'
            else 'Outros'
        end as tipo_cargo_label
        , case
            when ap.situacao_funcional in ('1', 'A', 'ATIVO', 'ATIVA') then 'Ativo'
            when ap.situacao_funcional in ('2', 'I', 'INATIVO', 'INATIVA') then 'Inativo'
            when ap.situacao_funcional in ('3', 'AP', 'APOSENTADO') then 'Aposentado'
            else 'Outros'
        end as situacao_funcional_label
        , coalesce(ap.situacao_funcional in ('1', 'A', 'ATIVO', 'ATIVA'), false) as is_ativo
        , ap.tipo_cargo in ('02', '2') as is_comissionado
        , ap.tipo_cargo in ('01', '1') as is_efetivo
        , case
            when ap.valor_carga_horaria <= 20 then 'Meio período'
            when ap.valor_carga_horaria <= 40 then 'Integral'
            when ap.valor_carga_horaria > 40 then 'Estendida'
            else 'Não informada'
        end as faixa_carga_horaria
    from agentes as ap
)

select * from final
