with
licitacoes as (
    select *
    from {{ ref('fct_licitacoes') }}
)

, municipios as (
    select
        municipio_id
        , nome_municipio
    from {{ ref('dim_municipios') }}
)

, final as (
    select
        lic.municipio_id
        , mun.nome_municipio
        , lic.ano_exercicio
        , lic.modalidade_licitacao_label
        , lic.is_dispensa
        , count(*) as total_licitacoes
        , count(case when lic.flag_licitacao_deserta then 1 end) as total_desertas
        , count(case when lic.flag_unico_participante then 1 end) as total_unico_participante
        , sum(lic.valor_estimado) as total_valor_estimado
        , sum(lic.valor_total_vencedor) as total_valor_adjudicado
        , avg(lic.quantidade_licitantes) as media_licitantes
        , round(
            count(case when lic.flag_licitacao_deserta then 1 end) * 100.0 / count(*), 2
        ) as percentual_desertas
    from licitacoes as lic
    left join municipios as mun
        on lic.municipio_id = mun.municipio_id
    group by
        lic.municipio_id
        , mun.nome_municipio
        , lic.ano_exercicio
        , lic.modalidade_licitacao_label
        , lic.is_dispensa
)

select *
from final
