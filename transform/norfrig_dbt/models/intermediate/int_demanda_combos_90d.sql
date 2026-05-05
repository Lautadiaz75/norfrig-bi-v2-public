select
    c.Codigo as sku_componente,
    sum(v.cantidad * cast(c.Cantidad as float64)) as uds_por_combos_90d
from {{ source('norfrig_raw', 'raw_ventas') }} v
join {{ source('norfrig_raw', 'diccionario_combos') }} c
    on trim(upper(v.sku)) = trim(upper(c.`SKU Combo`))
where v.fecha >= date_sub(current_date(), interval 90 day)
group by c.Codigo