with maestro as (
    select * from {{ source('norfrig_raw', 'maestro_productos') }}
),

ventas_90d as (
    select * from {{ ref('int_ventas_90d') }}
),

dim_productos as (
    select * from {{ source('norfrig_raw', 'dim_productos') }}
),

dim_proveedores as (
    select * from {{ source('norfrig_raw', 'dim_proveedores') }}
),

stock as (
    select * from {{ source('norfrig_raw', 'stock_por_deposito') }}
),

stock_consolidado as (
    select
        sku,
        sum(stock_disponible) as stock_disponible_total,
        string_agg(
            concat(deposito_nombre, ':', cast(cast(stock_disponible as int64) as string)),
            ' | '
        ) as detalle_depositos
    from stock
    group by sku
),

base as (
    select
        coalesce(nullif(trim(m.Proveedor), ''), 'SIN PROVEEDOR') as proveedor,
        m.SKU                                as sku,
        m.Nombre                             as nombre_producto,
        m.Rubro                              as rubro,
        coalesce(sc.stock_disponible_total, 0) as stock_actual,
        coalesce(v90.avg_diario_real, 0)     as avg_diario_real,
        coalesce(v90.uds_90d_directo, 0)     as uds_90d_directo,
        coalesce(v90.uds_90d_combos, 0)      as uds_90d_combos,
        coalesce(v90.uds_90d, 0)             as uds_90d,
        coalesce(v90.ultima_venta, null)     as ultima_venta,
        cast(p.lead_time_dias as int64)      as lead_time_dias,
        cast(p.dias_stock_seguridad as int64) as dias_colchon,
        sc.detalle_depositos,
        coalesce(safe_cast(m.`Costo Interno` as float64), 0.0) as costo_interno
    from maestro m
    left join ventas_90d v90
        on trim(upper(cast(m.SKU as string))) = trim(upper(cast(v90.sku as string)))
    left join dim_productos d
        on trim(upper(cast(m.SKU as string))) = trim(upper(cast(d.sku as string)))
    left join dim_proveedores p
        on split(cast(d.id_proveedor as string), '.')[offset(0)] =
           split(cast(p.id_proveedor as string), '.')[offset(0)]
    left join stock_consolidado sc
        on trim(upper(cast(m.SKU as string))) = trim(upper(cast(sc.sku as string)))
    where m.Estado = 'Activo'
      and m.Tipo = 'Producto'
)

select * from base