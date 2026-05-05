select
    sku,
    avg(unidades) as avg_mensual
from {{ ref('int_ventas_mensuales') }}
where anio >= extract(year from date_sub(current_date(), interval 12 month))
group by sku
having avg(unidades) > 0