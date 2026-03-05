with
perfil as (
    select *
    from {{ ref('int_fornecedores_perfil') }}
)

, contratos_agg as (
    select
        nome_negociante
        , sum(valor_total) as valor_total_contratos
        , max(valor_total) as maior_contrato_valor
        , count(distinct municipio_id) as municipios_contratantes
        , sum(case when flag_contrato_ativo then 1 else 0 end) as contratos_ativos
        , sum(case when flag_contrato_vencido then 1 else 0 end) as contratos_vencidos
        , bool_or(is_pessoa_juridica) as is_pessoa_juridica
        , max(documento_negociante) as documento_negociante
    from {{ ref('int_contratos_enriched') }}
    group by nome_negociante
)

, final as (
    select
        perf.nome_negociante
        , con.documento_negociante
        , con.is_pessoa_juridica
        , case
            when con.is_pessoa_juridica then 'Pessoa Jurídica'
            when con.documento_negociante is not null then 'Pessoa Física'
            else 'Não identificado'
        end as tipo_pessoa
        , perf.total_contratos
        , con.contratos_ativos
        , con.contratos_vencidos
        , con.valor_total_contratos
        , con.maior_contrato_valor
        , con.municipios_contratantes
        , perf.primeiro_contrato_em
        , perf.ultimo_contrato_em
        , perf.total_licitacoes_participou
        , coalesce(perf.total_licitacoes_participou = 0 and perf.total_contratos > 0, false)
            as flag_contratado_sem_licitacao
        , case
            when con.valor_total_contratos > 1000000 then 'Grande (> R$1M)'
            when con.valor_total_contratos > 100000 then 'Médio (R$100k–R$1M)'
            when con.valor_total_contratos is not null then 'Pequeno (< R$100k)'
            else 'Não informado'
        end as porte_fornecedor
    from perfil as perf
    left join contratos_agg as con
        on perf.nome_negociante = con.nome_negociante
)

select *
from final
