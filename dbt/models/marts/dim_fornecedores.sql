with
fornecedores as (
    select *
    from {{ ref('int_fornecedores_enriquecido') }}
)

, final as (
    select
        nome_negociante
        , documento_negociante
        , is_pessoa_juridica
        , tipo_pessoa
        , total_contratos
        , contratos_ativos
        , contratos_vencidos
        , valor_total_contratos
        , maior_contrato_valor
        , municipios_contratantes
        , primeiro_contrato_em
        , ultimo_contrato_em
        , total_licitacoes_participou
        , flag_contratado_sem_licitacao
        , porte_fornecedor
    from fornecedores
)

select *
from final
