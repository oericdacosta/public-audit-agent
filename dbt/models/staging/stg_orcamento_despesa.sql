with
source_data as (
    select
        id
        , municipio_id
        , codigo_projeto_atividade
        , descricao_projeto_atividade
        , exercicio_orcamento
        , raw_data
        , updated_at
    from {{ source('tce_ce', 'orcamento_despesa') }}
)

, stg_orcamento_despesa as (
    select
        cast(id as varchar) as orcamento_despesa_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(
            coalesce(
                json_extract_string(raw_data, '$.codigo_funcao')
            ) as varchar
        ) as codigo_funcao
        , cast(
            coalesce(
                json_extract_string(raw_data, '$.codigo_programa')
            ) as varchar
        ) as codigo_programa
        , cast(codigo_projeto_atividade as varchar) as codigo_projeto_atividade
        , cast(
            trim(coalesce(
                descricao_projeto_atividade
                , json_extract_string(raw_data, '$.nome_projeto_atividade')
            )) as varchar
        ) as nome_projeto_atividade
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_orcamento_despesa
