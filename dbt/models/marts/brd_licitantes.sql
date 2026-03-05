with
licitantes as (
    select *
    from {{ ref('stg_licitantes') }}
)

, licitacoes as (
    select
        licitacao_id
        , numero_licitacao
        , municipio_id
    from {{ ref('fct_licitacoes') }}
)

, final as (
    select
        lit.licitante_id
        , lic.licitacao_id
        , lit.municipio_id
        , lit.numero_licitacao
        , lit.nome_negociante
        , lit.documento_negociante
        , lit.data_realizacao_licitacao
        , lit.updated_at
    from licitantes as lit
    left join licitacoes as lic
        on
            lit.numero_licitacao = lic.numero_licitacao
            and lit.municipio_id = lic.municipio_id
)

select *
from final
