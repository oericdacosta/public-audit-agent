with source as (
    select * from {{ source('tce_ce', 'balancete_receita_extra') }}
)

, renamed as (
    select
        id                                          as balancete_receita_extra_id
        , municipio_id
        , cast(exercicio_orcamento as integer)        as ano_exercicio
        , mes_referencia
        , updated_at
    from source
)

select * from renamed
