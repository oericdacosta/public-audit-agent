with notas_fiscais as (
    select *
    from {{ ref('stg_notas_fiscais') }}
)

, negociantes as (
    select *
    from {{ ref('stg_negociantes') }}
)

, itens_agg as (
    select
        numero_nota_fiscal
        , municipio_id
        , ano_exercicio
        , count(*) as total_itens
        , sum(valor_total) as valor_total_itens
    from {{ ref('stg_itens_notas_fiscais') }}
    group by numero_nota_fiscal, municipio_id, ano_exercicio
)

, final as (
    select
        nf.nota_fiscal_id
        , nf.municipio_id
        , nf.ano_exercicio
        , nf.numero_nota_fiscal
        , nf.data_emissao
        , nf.tipo_nota_fiscal
        , nf.cpf_cnpj_credor
        , nf.valor_bruto
        , nf.valor_liquido
        , neg.nome_negociante
        , neg.endereco_negociante
        , neg.uf_negociante
        , ite.total_itens
        , ite.valor_total_itens
        , nf.updated_at
        , nf.valor_bruto - nf.valor_liquido as diferenca_bruto_liquido
        , (
            nf.tipo_nota_fiscal ilike '%serv%'
            or nf.tipo_nota_fiscal in ('S', 'NFS', 'NFS-e', 'NFSe')
        ) as flag_nota_servico
        , nf.valor_liquido > 100000 as is_alto_valor
        , case
            when nf.valor_liquido > 100000 then 'acima de R$100k'
            when nf.valor_liquido > 10000 then 'R$10k a R$100k'
            else 'até R$10k'
        end as faixa_valor
    from notas_fiscais as nf
    left join negociantes as neg
        on
            regexp_replace(neg.numero_documento_negociante, '[^0-9]', '', 'g')
            = regexp_replace(nf.cpf_cnpj_credor, '[^0-9]', '', 'g')
    left join itens_agg as ite
        on
            nf.numero_nota_fiscal = ite.numero_nota_fiscal
            and nf.municipio_id = ite.municipio_id
            and nf.ano_exercicio = ite.ano_exercicio
)

select * from final
