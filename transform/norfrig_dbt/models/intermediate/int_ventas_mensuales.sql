select
    sku,
    extract(month from fecha) as mes,
    extract(year from fecha)  as anio,
    sum(cantidad)             as unidades
from {{ source('norfrig_raw', 'raw_ventas') }}
where fecha >= date_sub(current_date(), interval 24 month)
group by sku, extract(month from fecha), extract(year from fecha)