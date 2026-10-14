-- Acquisition channel quality: conversion, repeat rate and average customer value.
WITH cust AS (
    SELECT
        c.customer_id,
        c.acquisition_channel,
        count(f.order_id)                 AS orders,
        coalesce(sum(f.net_amount), 0)    AS lifetime_revenue
    FROM core.dim_customers c
    LEFT JOIN core.fct_orders f
        ON f.customer_id = c.customer_id AND f.status = 'completed'
    GROUP BY 1, 2
)
SELECT
    acquisition_channel,
    count(*)                                                   AS customers,
    round(avg((orders > 0)::INT), 4)                           AS conversion_rate,
    round(avg((orders > 1)::INT) / nullif(avg((orders > 0)::INT), 0), 4) AS repeat_purchase_rate,
    round(avg(lifetime_revenue), 2)                            AS revenue_per_customer,
    round(avg(lifetime_revenue) FILTER (WHERE orders > 0), 2)  AS revenue_per_buyer,
    round(sum(lifetime_revenue), 2)                            AS total_revenue
FROM cust
GROUP BY 1
ORDER BY total_revenue DESC
