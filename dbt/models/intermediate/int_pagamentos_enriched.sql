with notas_pagamentos as (
    select *
    from {{ ref('stg_notas_pagamentos') }}
)

, final as (
    select
        np.nota_pagamento_id
        , np.municipio_id
        , np.ano_exercicio
        , np.numero_nota_pagamento
        , np.data_nota_pagamento
        , np.valor_nota_pagamento
        , np.nome_pagador
        , extract(year from np.data_nota_pagamento)::integer as ano_pagamento
        , extract(month from np.data_nota_pagamento)::integer as mes_pagamento
        , np.updated_at
        , date_trunc('month', np.data_nota_pagamento) as mes_pagamento_date
        , case
            when extract(month from np.data_nota_pagamento)::integer = 1 then 'Janeiro'
            when extract(month from np.data_nota_pagamento)::integer = 2 then 'Fevereiro'
            when extract(month from np.data_nota_pagamento)::integer = 3 then 'Março'
            when extract(month from np.data_nota_pagamento)::integer = 4 then 'Abril'
            when extract(month from np.data_nota_pagamento)::integer = 5 then 'Maio'
            when extract(month from np.data_nota_pagamento)::integer = 6 then 'Junho'
            when extract(month from np.data_nota_pagamento)::integer = 7 then 'Julho'
            when extract(month from np.data_nota_pagamento)::integer = 8 then 'Agosto'
            when extract(month from np.data_nota_pagamento)::integer = 9 then 'Setembro'
            when extract(month from np.data_nota_pagamento)::integer = 10 then 'Outubro'
            when extract(month from np.data_nota_pagamento)::integer = 11 then 'Novembro'
            when extract(month from np.data_nota_pagamento)::integer = 12 then 'Dezembro'
        end as nome_mes_pagamento
        , np.valor_nota_pagamento > 100000 as is_alto_valor
    from notas_pagamentos as np
)

select * from final
