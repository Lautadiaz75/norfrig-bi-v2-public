with stock as (
    select * from {{ ref('int_stock_actual') }}
),

ventas as (
    select * from {{ ref('int_ventas_por_sku') }}
),

productos as (
    select * from {{ source('norfrig_raw', 'dim_productos') }}
),

proveedores as (
    select * from {{ source('norfrig_raw', 'dim_proveedores') }}
),

semaforo as (
    select
        s.sku,
        s.stock_disponible_total                                    as stock_actual,
        coalesce(v.demanda_diaria_promedio, 0)                      as demanda_diaria,
        coalesce(v.cantidad_total, 0)                               as ventas_totales,
        coalesce(v.dias_con_venta, 0)                               as dias_con_venta,

        -- Días de stock disponible
        case
            when coalesce(v.demanda_diaria_promedio, 0) = 0 then 999
            else round(s.stock_disponible_total / v.demanda_diaria_promedio, 0)
        end                                                         as dias_stock,

        -- Lead time del proveedor
        coalesce(prov.lead_time_dias, 30)                           as lead_time_dias,
        coalesce(prov.dias_stock_seguridad, 15)                     as dias_stock_seguridad,

        -- Punto de reorden
        round(
            coalesce(v.demanda_diaria_promedio, 0) *
            (coalesce(prov.lead_time_dias, 30) + coalesce(prov.dias_stock_seguridad, 15))
        , 0)                                                        as punto_reorden,

        -- Cantidad sugerida a comprar
        greatest(0, round(
            coalesce(v.demanda_diaria_promedio, 0) *
            (coalesce(prov.lead_time_dias, 30) + coalesce(prov.dias_stock_seguridad, 15) + 30)
            - s.stock_disponible_total
        , 0))                                                       as cantidad_sugerida,

        -- Semáforo
        case
            when coalesce(v.demanda_diaria_promedio, 0) = 0 then 'SIN_MOVIMIENTO'
            when s.stock_disponible_total = 0 then 'ROJO'
            when s.stock_disponible_total <=
                coalesce(v.demanda_diaria_promedio, 0) * coalesce(prov.lead_time_dias, 30)
                then 'ROJO'
            when s.stock_disponible_total <=
                coalesce(v.demanda_diaria_promedio, 0) *
                (coalesce(prov.lead_time_dias, 30) + coalesce(prov.dias_stock_seguridad, 15))
                then 'AMARILLO'
            else 'VERDE'
        end                                                         as semaforo,

        prod.id_proveedor,
        prod.estado_planificacion,
        prov.nombre_proveedor,
        s.ultima_sync,
        v.ultima_venta,
        current_timestamp()                                         as calculado_en

    from stock s
    left join ventas v on upper(trim(s.sku)) = upper(trim(v.sku))
    left join productos prod on upper(trim(s.sku)) = upper(trim(prod.sku))
    left join proveedores prov on prod.id_proveedor = prov.id_proveedor
)

select * from semaforo