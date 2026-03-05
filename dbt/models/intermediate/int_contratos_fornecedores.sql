with
contratos as (
    select *
    from {{ ref('int_contratos_enriched') }}
)

, fornecedores as (
    select *
    from {{ ref('int_fornecedores_enriquecido') }}
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
        , con.valor_total as valor_contrato
        , con.faixa_valor_contrato
        , con.is_alto_valor
        , con.flag_contrato_ativo
        , con.flag_contrato_vencido
        , con.dias_para_vencer
        , con.nome_negociante as nome_fornecedor
        , con.documento_negociante as documento_fornecedor
        , con.is_pessoa_juridica
        , con.uf_negociante as uf_fornecedor
        , forn.tipo_pessoa
        , forn.total_contratos as fornecedor_total_contratos
        , forn.contratos_ativos as fornecedor_contratos_ativos
        , forn.valor_total_contratos as fornecedor_valor_total_acumulado
        , forn.maior_contrato_valor as fornecedor_maior_contrato
        , forn.municipios_contratantes as fornecedor_municipios
        , forn.total_licitacoes_participou as fornecedor_licitacoes_participadas
        , forn.porte_fornecedor
        , forn.flag_contratado_sem_licitacao
        , forn.total_contratos >= 5 and con.is_alto_valor as flag_fornecedor_recorrente_alto_valor
    from contratos as con
    left join fornecedores as forn
        on con.nome_negociante = forn.nome_negociante
    left join municipios as mun
        on con.municipio_id = mun.municipio_id
)

select *
from final
