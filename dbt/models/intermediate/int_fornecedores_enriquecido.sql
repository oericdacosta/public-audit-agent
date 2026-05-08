with perfil as (
    select *
    from {{ ref('int_fornecedores_perfil') }}
)

, final as (
    select
        perf.nome_negociante
        , perf.documento_negociante
        , coalesce(
            length(regexp_replace(coalesce(perf.documento_negociante, ''), '[^0-9]', '', 'g')) = 14
            , false
        ) as is_pessoa_juridica
        , case
            when
                length(regexp_replace(coalesce(perf.documento_negociante, ''), '[^0-9]', '', 'g'))
                = 14
                then 'Pessoa Jurídica'
            when perf.documento_negociante is not null then 'Pessoa Física'
            else 'Não identificado'
        end as tipo_pessoa
        , 0 as total_contratos
        , 0 as contratos_ativos
        , 0 as contratos_vencidos
        , null::double as valor_total_contratos
        , null::double as maior_contrato_valor
        , perf.municipios_distintos as municipios_contratantes
        , perf.primeira_licitacao_em as primeiro_contrato_em
        , perf.ultima_licitacao_em as ultimo_contrato_em
        , perf.total_licitacoes_participou
        , false as flag_contratado_sem_licitacao
        , 'Não informado' as porte_fornecedor
    from perfil as perf
)

select * from final
