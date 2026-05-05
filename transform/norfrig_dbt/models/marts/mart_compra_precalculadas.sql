with base as (
    select * from {{ ref('int_base') }}
),

coef_periodo as (
    select * from {{ ref('int_coef_periodo') }}
),

pico as (
    select * from {{ ref('int_pico_anio_pasado') }}
),

calculos as (
    select
        b.*,
        coalesce(cp.coef_promedio_periodo, 1.0) as coef_estacional,
        (b.avg_diario_real * coalesce(cp.coef_promedio_periodo, 1.0)) as avg_diario_proy,
        case
            when b.lead_time_dias is null then 0
            else greatest(0, round(
                (b.avg_diario_real * coalesce(cp.coef_promedio_periodo, 1.0))
                * (b.lead_time_dias + b.dias_colchon) - b.stock_actual, 0))
        end as unidades_a_pedir,
        round(safe_divide(
            b.stock_actual,
            nullif(b.avg_diario_real * coalesce(cp.coef_promedio_periodo, 1.0), 0)
        ), 0) as dias_stock_restante
    from base b
    left join coef_periodo cp on b.sku = cp.sku
)

select
    c.proveedor,
    c.sku,
    c.nombre_producto,
    c.rubro,
    c.stock_actual,
    c.avg_diario_real,
    c.avg_diario_proy,
    c.uds_90d,
    c.uds_90d_directo,
    c.uds_90d_combos,
    round(c.coef_estacional, 2)              as coef_estacional,
    c.lead_time_dias,
    c.dias_colchon,
    c.dias_stock_restante,
    c.unidades_a_pedir,
    c.detalle_depositos,
    round(c.costo_interno / 1.21, 2)         as costo_sin_iva,
    coalesce(pp.pico_unidades, 0)            as pico_unidades_anio_pasado,
    pp.mes_pico                              as mes_pico_anio_pasado,
    row_number() over (
        partition by c.proveedor order by c.uds_90d desc
    )                                        as ranking_ventas,
    case
        when c.lead_time_dias is null
            then 'FALTAN DATOS'
        when c.avg_diario_proy > 0
            and c.stock_actual <= (c.avg_diario_proy * c.lead_time_dias)
            then 'CRITICO'
        when c.avg_diario_proy > 0
            and c.stock_actual <= (c.avg_diario_proy * (c.lead_time_dias + c.dias_colchon))
            then 'REORDEN'
        when c.avg_diario_proy > 0
            then 'OK'
        when c.avg_diario_proy = 0 and c.stock_actual = 0
            then 'AGOTADO SIN VENTAS'
        when c.avg_diario_proy = 0 and c.stock_actual > 0
            then 'SIN MOVIMIENTO'
        else 'REVISAR'
    end                                      as semaforo,
    case
        when c.avg_diario_proy > 0
            and c.stock_actual <= (c.avg_diario_proy * c.lead_time_dias)
            then 1
        when c.avg_diario_proy > 0
            and c.stock_actual <= (c.avg_diario_proy * (c.lead_time_dias + c.dias_colchon))
            then 2
        when c.avg_diario_proy > 0
            then 3
        when c.avg_diario_proy = 0 and c.stock_actual = 0
            then 4
        when c.avg_diario_proy = 0 and c.stock_actual > 0
            then 5
        when c.lead_time_dias is null
            then 6
        else 7
    end                                      as orden_prioridad,
    current_timestamp()                      as calculado_en
from calculos c
left join pico pp
    on upper(trim(cast(c.sku as string))) = upper(trim(cast(pp.sku as string)))