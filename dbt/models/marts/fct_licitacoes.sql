with
licitacoes as (
    select *
    from {{ ref('int_licitacoes_enriched') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('stg_municipios') }}
)

, final as (
    select
        lic.licitacao_id
        , lic.municipio_id
        , mun.nome_municipio
        , lic.numero_licitacao
        , lic.numero_processo
        , lic.ano_exercicio
        , lic.data_realizacao
        , lic.ano_realizacao
        , lic.objeto_licitacao
        , lic.modalidade_licitacao
        , lic.modalidade_licitacao_label
        , lic.is_dispensa
        , lic.is_pregao
        , lic.valor_estimado
        , lic.valor_total_vencedor
        , lic.faixa_valor
        , lic.is_alto_valor
        , lic.quantidade_licitantes
        , lic.total_itens
        , lic.situacao_licitacao
        , lic.flag_licitacao_deserta
        , lic.flag_unico_participante
        , lic.updated_at
    from licitacoes as lic
    left join municipios as mun
        on lic.municipio_id = mun.municipio_id
)

select *
from final
