with source as (
    select * from {{ source('tce_ce', 'agentes_publicos') }}
)

, renamed as (
    select
        id                                          as agente_id
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
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
