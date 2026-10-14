-- Monthly cohort retention: share of each first-purchase cohort active N months later.
WITH activity AS (
    SELECT DISTINCT
        f.customer_id,
        c.cohort_month,
        date_trunc('month', f.order_date)::DATE AS active_month
    FROM core.fct_orders f
    JOIN core.dim_customers c USING (customer_id)
    WHERE f.status = 'completed'
),
counts AS (
    SELECT
        cohort_month,
        date_diff('month', cohort_month, active_month) AS months_since_first,
        count(DISTINCT customer_id)                    AS active_customers
    FROM activity
    GROUP BY 1, 2
)
SELECT
    cohort_month,
    months_since_first,
    active_customers,
    first_value(active_customers) OVER w                              AS cohort_size,
    round(active_customers / first_value(active_customers) OVER w, 4) AS retention_rate
FROM counts
WINDOW w AS (PARTITION BY cohort_month ORDER BY months_since_first)
ORDER BY cohort_month, months_since_first
