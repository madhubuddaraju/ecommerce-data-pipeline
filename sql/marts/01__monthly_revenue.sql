-- Monthly KPIs for completed orders, split by new vs returning customers.
WITH m AS (
    SELECT
        date_trunc('month', order_date)::DATE                       AS month,
        count(*)                                                    AS orders,
        count(DISTINCT customer_id)                                 AS active_customers,
        count(DISTINCT customer_id) FILTER (WHERE is_first_order)   AS new_customers,
        round(sum(net_amount), 2)                                   AS revenue,
        round(sum(net_amount) FILTER (WHERE is_first_order), 2)     AS new_customer_revenue,
        round(sum(gross_profit), 2)                                 AS gross_profit,
        round(avg(net_amount), 2)                                   AS avg_order_value
    FROM core.fct_orders
    WHERE status = 'completed'
    GROUP BY 1
)
SELECT
    *,
    round(revenue - new_customer_revenue, 2)                        AS returning_customer_revenue,
    round(gross_profit / revenue, 4)                                AS gross_margin_pct,
    round(revenue / lag(revenue) OVER (ORDER BY month) - 1, 4)      AS revenue_mom_growth,
    round(sum(revenue) OVER (ORDER BY month), 2)                    AS cumulative_revenue
FROM m
ORDER BY month
