-- Grain: one row per order, with line items rolled up.
WITH lines AS (
    SELECT
        order_id,
        count(*)              AS line_count,
        sum(quantity)         AS units,
        sum(gross_amount)     AS gross_amount,
        sum(discount_amount)  AS discount_amount,
        sum(net_amount)       AS net_amount,
        sum(gross_profit)     AS gross_profit
    FROM core.fct_order_items
    GROUP BY order_id
),
ordered AS (
    SELECT
        o.*,
        row_number() OVER (PARTITION BY customer_id ORDER BY order_ts) AS customer_order_seq
    FROM staging.stg_orders o
    WHERE o.status = 'completed'
)
SELECT
    o.order_id,
    o.customer_id,
    CAST(strftime(o.order_ts, '%Y%m%d') AS INTEGER)  AS date_key,
    o.order_ts,
    o.order_ts::DATE                                 AS order_date,
    o.status,
    o.payment_method,
    l.line_count,
    l.units,
    l.gross_amount,
    l.discount_amount,
    l.net_amount,
    o.shipping_cost,
    round(l.net_amount + o.shipping_cost, 2)         AS order_total,
    l.gross_profit,
    coalesce(od.customer_order_seq, 0)               AS customer_order_seq,
    coalesce(od.customer_order_seq = 1, FALSE)       AS is_first_order
FROM staging.stg_orders o
JOIN lines l USING (order_id)
LEFT JOIN ordered od USING (order_id)
