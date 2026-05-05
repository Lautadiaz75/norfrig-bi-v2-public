with source as (
    select * from {{ source('norfrig_raw', 'raw_ventas') }}
),

renamed as (
    select
        fecha,
        cuenta,
        id_comprobante,
        numero,
        tipo_fc,
        es_cot,
        origen,
        sku,
        nombre_producto,
        cantidad
    from source
    where fecha is not null
      and sku is not null
      and cantidad > 0
)

select * from renamed