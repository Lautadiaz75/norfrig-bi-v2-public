with base as (
    select * from {{ ref('int_base') }}
),

coef_por_mes as (
    select * from {{ ref('int_coef_por_mes') }}

),

coef_periodo as (
    select
        b.sku,
        b.lead_time_dias,
        b.dias_colchon,
        avg(coalesce(cm.coef, 1.0)) as coef_promedio_periodo
    from base b
    cross join unnest(generate_array(0, 11)) as offset_mes
    left join coef_por_mes cm
        on b.sku = cm.sku
        and cm.mes = extract(month from date_add(current_date(), interval offset_mes month))
    where b.lead_time_dias is not null
      and date_add(date_trunc(current_date(), month), interval offset_mes month)
          <= date_add(current_date(), interval (b.lead_time_dias + b.dias_colchon) day)
    group by b.sku, b.lead_time_dias, b.dias_colchon
)

select * from coef_periodo