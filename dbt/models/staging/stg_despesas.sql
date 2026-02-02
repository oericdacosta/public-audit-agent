with
    source as (
        select
            id
            , municipio_id
            , exercicio_orcamento
            , mes_referencia
            , codigo_orgao
            , codigo_unidade_orcamentaria
            , codigo_funcao
            , codigo_subfuncao
            , codigo_programa
            , codigo_elemento_despesa
            , valor_empenhado
            , valor_liquidado
            , valor_pago
            , updated_at
        from {{ source('civic_audit_duckdb', 'despesas') }}
    )

    , renamed as (
        select
            cast(id as varchar) as despesa_id
            , cast(municipio_id as varchar) as municipio_id
            , cast(exercicio_orcamento as int) as ano_exercicio
            , cast(mes_referencia as varchar) as mes_referencia
            , cast(codigo_orgao as varchar) as codigo_orgao
            , cast(codigo_unidade_orcamentaria as varchar) as codigo_unidade_orcamentaria
            , cast(codigo_funcao as varchar) as codigo_funcao
            , cast(codigo_subfuncao as varchar) as codigo_subfuncao
            , cast(codigo_programa as varchar) as codigo_programa
            , cast(codigo_elemento_despesa as varchar) as codigo_elemento_despesa
            , cast(valor_empenhado as double) as valor_empenhado
            , cast(valor_liquidado as double) as valor_liquidado
            , cast(valor_pago as double) as valor_pago
            , cast(updated_at as timestamp) as data_carga
        from source
    )

select *
from renamed
