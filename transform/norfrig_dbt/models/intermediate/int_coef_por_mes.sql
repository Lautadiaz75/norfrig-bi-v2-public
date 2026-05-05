select
    vm.sku,
    vm.mes,
    safe_divide(
        array_agg(vm.unidades order by vm.anio desc limit 1)[offset(0)],
        pa.avg_mensual
    ) as coef
from {{ ref('int_ventas_mensuales') }} vm
join {{ ref('int_promedio_anual') }} pa on vm.sku = pa.sku
group by vm.sku, vm.mes, pa.avg_mensual