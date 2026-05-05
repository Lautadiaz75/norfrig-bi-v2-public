with stock as (
    select * from {{ ref('stg_stock') }}
),

consolidado as (
    select
        sku,
        sum(stock_disponible)   as stock_disponible_total,
        sum(stock_actual)       as stock_actual_total,
        sum(stock_reservado)    as stock_reservado_total,
        max(fecha_sync)         as ultima_sync
    from stock
    group by sku
)

select * from consolidado