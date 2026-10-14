-- RFM segmentation (Recency, Frequency, Monetary) as of the day after the last order.
WITH as_of AS (
    SELECT max(order_date) + INTERVAL 1 DAY AS ref_date FROM core.fct_orders
),
base AS (
    SELECT
        f.customer_id,
        date_diff('day', max(f.order_date), any_value(a.ref_date)) AS recency_days,
        count(*)                                                    AS frequency,
        round(sum(f.net_amount), 2)                                 AS monetary
    FROM core.fct_orders f, as_of a
    WHERE f.status = 'completed'
    GROUP BY f.customer_id
),
scored AS (
    SELECT
        *,
        6 - ntile(5) OVER (ORDER BY recency_days)        AS r_score,
        ntile(5) OVER (ORDER BY frequency, monetary)     AS f_score,
        ntile(5) OVER (ORDER BY monetary)                AS m_score
    FROM base
)
SELECT
    s.*,
    r_score::VARCHAR || f_score::VARCHAR || m_score::VARCHAR AS rfm_code,
    CASE
        WHEN r_score >= 4 AND f_score >= 4                THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 3                THEN 'Loyal'
        WHEN r_score >= 4 AND f_score <= 2                THEN 'New / Promising'
        WHEN r_score <= 2 AND f_score >= 4                THEN 'At Risk'
        WHEN r_score <= 2 AND f_score <= 2                THEN 'Hibernating'
        ELSE 'Needs Attention'
    END AS segment,
    c.country,
    c.acquisition_channel
FROM scored s
JOIN core.dim_customers c USING (customer_id)
