select
    sku,
    extract(month from fecha) as mes_pico,
    sum(cantidad)             as pico_unidades
from {{ source('norfrig_raw', 'raw_ventas') }}
where extract(year from fecha) = extract(year from current_date()) - 1
group by sku, extract(month from fecha)
qualify row_number() over (partition by sku order by sum(cantidad) desc) = 1