with ventas as (
    select * from {{ ref('stg_ventas') }}
),

ventas_sin_cot as (
    select * from ventas
    where es_cot = false
),

agregado as (
    select
        sku,
        count(distinct fecha)                    as dias_con_venta,
        sum(cantidad)                            as cantidad_total,
        min(fecha)                               as primera_venta,
        max(fecha)                               as ultima_venta,
        round(sum(cantidad) / nullif(
            date_diff(max(fecha), min(fecha), day) + 1
        , 0), 2)                                 as demanda_diaria_promedio
    from ventas_sin_cot
    group by sku
)

select * from agregado