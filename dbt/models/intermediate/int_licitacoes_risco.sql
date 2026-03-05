with
licitacoes as (
    select *
    from {{ ref('int_licitacoes_enriched') }}
)

, compras_diretas as (
    select
        licitacao_id
        , flag_valor_acima_limite_dispensa
    from {{ ref('int_compras_diretas') }}
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
        , lic.valor_total_vencedor - lic.valor_estimado as desvio_valor_absoluto
        , case
            when lic.valor_estimado > 0
                then round(lic.valor_total_vencedor / lic.valor_estimado * 100 - 100, 2)
        end as desvio_valor_percentual
        , coalesce(
            lic.valor_estimado > 0
            and lic.valor_total_vencedor > lic.valor_estimado * 1.10
            , false
        ) as flag_possivel_superfaturamento
        , lic.quantidade_licitantes
        , lic.total_itens
        , lic.situacao_licitacao
        , lic.flag_licitacao_deserta
        , lic.flag_unico_participante
        , coalesce(cd.flag_valor_acima_limite_dispensa, false) as flag_dispensa_acima_limite
        , (
            (lic.flag_licitacao_deserta::int)
            + (lic.flag_unico_participante::int)
            + (coalesce(cd.flag_valor_acima_limite_dispensa, false)::int)
            + (
                case
                    when
                        lic.valor_estimado > 0
                        and lic.valor_total_vencedor > lic.valor_estimado * 1.10
                        then 1
                    else 0
                end
            )
        ) as score_risco
        , lic.updated_at
    from licitacoes as lic
    left join compras_diretas as cd
        on lic.licitacao_id = cd.licitacao_id
    left join municipios as mun
        on lic.municipio_id = mun.municipio_id
)

select *
from final
