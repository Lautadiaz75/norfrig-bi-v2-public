with demanda_combos as (
    select * from {{ ref('int_demanda_combos_90d') }}
),

ventas as (
    select
        v.sku,
        sum(v.cantidad)                              as uds_90d_directo,
        coalesce(dc.uds_por_combos_90d, 0)          as uds_90d_combos,
        sum(v.cantidad) + coalesce(dc.uds_por_combos_90d, 0) as uds_90d,
        (sum(v.cantidad) + coalesce(dc.uds_por_combos_90d, 0)) / 90.0 as avg_diario_real,
        max(v.fecha)                                 as ultima_venta
    from {{ source('norfrig_raw', 'raw_ventas') }} v
    left join demanda_combos dc
        on trim(upper(v.sku)) = trim(upper(dc.sku_componente))
    where v.fecha >= date_sub(current_date(), interval 90 day)
    group by v.sku, dc.uds_por_combos_90d
)

select * from ventas