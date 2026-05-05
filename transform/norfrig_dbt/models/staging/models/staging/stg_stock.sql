with source as (
    select * from {{ source('norfrig_raw', 'stock_por_deposito') }}
),

renamed as (
    select
        fecha_sync,
        cuenta,
        deposito_id,
        deposito_nombre,
        sku,
        stock_actual,
        stock_reservado,
        stock_disponible
    from source
    where sku is not null
      and stock_disponible > 0
)

select * from renamed