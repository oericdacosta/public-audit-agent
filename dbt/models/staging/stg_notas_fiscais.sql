with source as (
    select * from {{ source('tce_ce', 'notas_fiscais') }}
)

, renamed as (
    select
        id                                          as nota_fiscal_id
        , municipio_id
        , numero_nota_fiscal
        , data_emissao
        , valor_liquido
        , valor_bruto
        , tipo_nota_fiscal
        , cpf_cnpj_credor
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
