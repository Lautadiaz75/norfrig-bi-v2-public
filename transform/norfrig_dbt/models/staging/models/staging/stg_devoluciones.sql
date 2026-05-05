with source as (
    select * from {{ source('norfrig_raw', 'devoluciones_diarias') }}
),

renamed as (
    select
        fecha,
        cuenta,
        id_comprobante,
        tipo_fc,
        sku,
        cantidad
    from source
    where fecha is not null
      and sku is not null
      and cantidad > 0
)

select * from renamed