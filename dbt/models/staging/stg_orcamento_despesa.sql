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

        -- Year normalization: source may store as 202500 (YYYYMM) or plain 2025
        , case
            when cast(exercicio_orcamento as integer) > 9999
                then cast(cast(exercicio_orcamento as integer) / 100 as integer)
            else cast(exercicio_orcamento as integer)
        end as ano_exercicio

        -- Classification fields extracted from raw_data JSON
        , cast(
            trim(coalesce(json_extract_string(raw_data, '$.codigo_orgao'), ''))
            as varchar
        ) as codigo_orgao

        , cast(
            trim(coalesce(json_extract_string(raw_data, '$.codigo_unidade'), ''))
            as varchar
        ) as codigo_unidade_orcamentaria

        , cast(
            coalesce(json_extract_string(raw_data, '$.codigo_funcao'), '')
            as varchar
        ) as codigo_funcao

        , cast(
            coalesce(json_extract_string(raw_data, '$.codigo_subfuncao'), '')
            as varchar
        ) as codigo_subfuncao

        , cast(
            coalesce(json_extract_string(raw_data, '$.codigo_programa'), '')
            as varchar
        ) as codigo_programa

        , cast(codigo_projeto_atividade as varchar) as codigo_projeto_atividade

        , cast(
            coalesce(json_extract_string(raw_data, '$.numero_projeto_atividade'), '')
            as varchar
        ) as numero_projeto_atividade

        -- Budget type: 'F' = Fiscal, 'S' = Seguridade Social
        , cast(
            coalesce(json_extract_string(raw_data, '$.codigo_tipo_orcamento'), '')
            as varchar
        ) as codigo_tipo_orcamento

        , cast(
            trim(coalesce(
                descricao_projeto_atividade
                , json_extract_string(raw_data, '$.nome_projeto_atividade')
                , ''
            )) as varchar
        ) as nome_projeto_atividade

        -- LOA appropriation value: the original budget allocation for this project/activity
        , coalesce(
            try_cast(
                json_extract_string(raw_data, '$.valor_total_fixado_projeto_atividade')
                as decimal(18, 2)
            )
            , 0.0
        ) as valor_fixado_loa

        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_orcamento_despesa
