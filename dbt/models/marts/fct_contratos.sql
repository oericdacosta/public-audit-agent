with
contratos as (
    select *
    from {{ ref('int_contratos_enriched') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('stg_municipios') }}
)

, final as (
    select
        con.contrato_id
        , con.municipio_id
        , mun.nome_municipio
        , con.numero_contrato
        , con.data_contrato
        , extract(year from con.data_contrato)::integer as ano_contrato
        , con.data_inicio_vigencia
        , con.data_fim_vigencia
        , con.duracao_vigencia_dias
        , con.descricao_objeto
        , con.tipo_contrato
        , con.valor_total
        , con.faixa_valor_contrato
        , con.is_alto_valor
        , con.nome_negociante as nome_fornecedor
        , con.documento_negociante as documento_fornecedor
        , con.is_pessoa_juridica
        , con.uf_negociante as uf_fornecedor
        , con.flag_contrato_ativo
        , con.flag_contrato_vencido
        , con.dias_para_vencer
        , con.updated_at
    from contratos as con
    left join municipios as mun
        on con.municipio_id = mun.municipio_id
)

select *
from final
