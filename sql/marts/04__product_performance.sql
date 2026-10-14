-- Product-level sales, profitability and return rate.
WITH sales AS (
    SELECT
        product_id,
        sum(quantity)     FILTER (WHERE status = 'completed')  AS units_sold,
        sum(net_amount)   FILTER (WHERE status = 'completed')  AS revenue,
        sum(gross_profit) FILTER (WHERE status = 'completed')  AS gross_profit,
        count(DISTINCT order_id)                               AS orders_total,
        count(DISTINCT order_id) FILTER (WHERE status = 'returned') AS orders_returned
    FROM core.fct_order_items
    GROUP BY product_id
)
SELECT
    p.product_id,
    p.sku,
    p.product_name,
    p.category,
    p.list_price,
    coalesce(s.units_sold, 0)                                   AS units_sold,
    round(coalesce(s.revenue, 0), 2)                            AS revenue,
    round(coalesce(s.gross_profit, 0), 2)                       AS gross_profit,
    round(s.gross_profit / nullif(s.revenue, 0), 4)             AS margin_pct,
    round(s.orders_returned / nullif(s.orders_total, 0), 4)     AS return_rate,
    rank() OVER (PARTITION BY p.category ORDER BY s.revenue DESC NULLS LAST) AS rank_in_category
FROM core.dim_products p
LEFT JOIN sales s USING (product_id)
ORDER BY revenue DESC
