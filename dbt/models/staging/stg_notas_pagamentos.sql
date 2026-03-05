with
source_data as (
    select
        id
        , municipio_id
        , numero_nota_pagamento
        , data_nota_pagamento
        , valor_nota_pagamento
        , nome_pagador
        , exercicio_orcamento
        , updated_at
    from {{ source('tce_ce', 'notas_pagamentos') }}
)

, stg_notas_pagamentos as (
    select
        cast(id as varchar) as nota_pagamento_id
        , cast(municipio_id as varchar) as municipio_id
        , cast(numero_nota_pagamento as varchar) as numero_nota_pagamento
        , cast(data_nota_pagamento as date) as data_nota_pagamento
        , cast(valor_nota_pagamento as decimal(18, 2)) as valor_nota_pagamento
        , cast(nome_pagador as varchar) as nome_pagador
        , cast(exercicio_orcamento as integer) as ano_exercicio
        , cast(updated_at as timestamp) as updated_at
    from source_data
)

select *
from stg_notas_pagamentos
