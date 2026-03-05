with contratos as (
    select *
    from {{ ref('stg_contratos') }}
)

, contratados_dedup as (
    select *
    from (
        select
            *
            , row_number() over (
                partition by numero_contrato, municipio_id
                order by data_contrato desc
            ) as rn
        from {{ ref('stg_contratados') }}
    )
    where rn = 1
)

, negociantes as (
    select *
    from {{ ref('stg_negociantes') }}
)

, final as (
    select
        con.contrato_id
        , con.municipio_id
        , con.numero_contrato
        , con.data_contrato
        , con.data_inicio_vigencia
        , con.data_fim_vigencia
        , con.valor_total
        , con.descricao_objeto
        , con.tipo_contrato
        , ctd.nome_negociante
        , ctd.documento_negociante
        , neg.endereco_negociante
        , neg.telefone_negociante
        , neg.uf_negociante
        , con.updated_at
        , case
            when con.data_fim_vigencia is not null and con.data_inicio_vigencia is not null
                then datediff('day', con.data_inicio_vigencia, con.data_fim_vigencia)
        end as duracao_vigencia_dias
        , coalesce(
            con.data_inicio_vigencia <= current_date and con.data_fim_vigencia >= current_date
            , false
        ) as flag_contrato_ativo
        , coalesce(con.data_fim_vigencia < current_date, false) as flag_contrato_vencido
        , case
            when con.data_fim_vigencia is not null
                then datediff('day', current_date, con.data_fim_vigencia)
        end as dias_para_vencer
        , con.valor_total > 650000 as is_alto_valor
        , case
            when con.valor_total > 650000 then 'acima de R$650k'
            when con.valor_total > 50000 then 'R$50k a R$650k'
            when con.valor_total is not null then 'até R$50k'
            else 'não informado'
        end as faixa_valor_contrato
        , coalesce(
            length(regexp_replace(coalesce(ctd.documento_negociante, ''), '[^0-9]', '', 'g'))
            = 14, false
        ) as is_pessoa_juridica
    from contratos as con
    left join contratados_dedup as ctd
        on
            con.numero_contrato = ctd.numero_contrato
            and con.municipio_id = ctd.municipio_id
    left join negociantes as neg
        on
            regexp_replace(neg.numero_documento_negociante, '[^0-9]', '', 'g')
            = regexp_replace(ctd.documento_negociante, '[^0-9]', '', 'g')
)

select * from final
