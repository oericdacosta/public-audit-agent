with
source_data as (
    select
        id
        , municipio_id
        , numero_nota_fiscal
        , data_emissao
        , valor_liquido
        , valor_bruto
        , tipo_nota_fiscal
        , cpf_cnpj_credor
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'notas_fiscais') }}
)

, stg_notas_fiscais as (
    select
        cast(id as varchar) as nota_fiscal_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_nota_fiscal as varchar) as numero_nota_fiscal
        , cast(data_emissao as date) as data_emissao
        , cast(valor_liquido as decimal(18, 2)) as valor_liquido
        , cast(valor_bruto as decimal(18, 2)) as valor_bruto
        , cast(tipo_nota_fiscal as varchar) as tipo_nota_fiscal
        , cast(cpf_cnpj_credor as varchar) as cpf_cnpj_credor
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_notas_fiscais
