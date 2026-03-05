with
source_data as (
    select
        id
        , municipio_id
        , cpf_servidor
        , nome_servidor
        , numero_matricula
        , cargo
        , tipo_cargo
        , situacao_funcional
        , codigo_vinculo
        , codigo_ingresso
        , valor_carga_horaria
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'agentes_publicos') }}
)

, stg_agentes_publicos as (
    select
        cast(id as varchar) as agente_publico_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(cpf_servidor as varchar) as cpf_servidor
        , cast(nome_servidor as varchar) as nome_servidor
        , cast(numero_matricula as varchar) as numero_matricula
        , cast(cargo as varchar) as cargo
        , cast(tipo_cargo as varchar) as tipo_cargo
        , cast(situacao_funcional as varchar) as situacao_funcional
        , cast(codigo_vinculo as varchar) as codigo_vinculo
        , cast(codigo_ingresso as varchar) as codigo_ingresso
        , cast(valor_carga_horaria as double) as valor_carga_horaria
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_agentes_publicos
