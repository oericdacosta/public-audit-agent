with source as (
    select * from {{ source('tce_ce', 'notas_pagamentos') }}
)

, renamed as (
    select
        id                                          as nota_pagamento_id
        , municipio_id
        , numero_nota_pagamento
        , data_nota_pagamento
        , valor_nota_pagamento
        , nome_pagador
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , updated_at
    from source
)

select * from renamed
