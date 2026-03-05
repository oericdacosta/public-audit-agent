with
source_data as (
    select
        id
        , municipio_id
        , exercicio_orcamento
        , mes_referencia
        , codigo_orgao
        , codigo_unidade_orcamentaria
        , codigo_receita
        , descricao_receita
        , valor_orcado
        , valor_arrecadado
        , updated_at
    from {{ source('tce_ce', 'receitas') }}
)

, stg_receitas as (
    select
        cast(id as varchar) as receita_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(mes_referencia as varchar) as mes_referencia
        , cast(codigo_orgao as varchar) as codigo_orgao
        , cast(codigo_unidade_orcamentaria as varchar) as codigo_unidade_orcamentaria
        , cast(codigo_receita as varchar) as codigo_receita
        , cast(descricao_receita as varchar) as descricao_receita
        , cast(valor_orcado as decimal(18, 2)) as valor_orcado
        , cast(valor_arrecadado as decimal(18, 2)) as valor_arrecadado
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_receitas
