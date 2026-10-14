-- One row per customer, enriched with first/last purchase and cohort.
WITH first_last AS (
    SELECT
        customer_id,
        min(order_ts)::DATE AS first_order_date,
        max(order_ts)::DATE AS last_order_date
    FROM staging.stg_orders
    WHERE status = 'completed'
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name             AS full_name,
    c.email,
    c.country,
    c.acquisition_channel,
    c.signup_date,
    fl.first_order_date,
    fl.last_order_date,
    date_trunc('month', fl.first_order_date)::DATE AS cohort_month,
    fl.first_order_date IS NOT NULL                AS has_purchased
FROM staging.stg_customers c
LEFT JOIN first_last fl USING (customer_id)
