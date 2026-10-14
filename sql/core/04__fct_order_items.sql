-- Grain: one row per order line.
SELECT
    i.order_item_id,
    i.order_id,
    o.customer_id,
    i.product_id,
    CAST(strftime(o.order_ts, '%Y%m%d') AS INTEGER)       AS date_key,
    o.order_ts::DATE                                      AS order_date,
    o.status,
    i.quantity,
    i.unit_price,
    i.discount_pct,
    i.gross_amount,
    i.discount_amount,
    i.net_amount,
    round(i.quantity * p.unit_cost, 2)                    AS cost_amount,
    round(i.net_amount - i.quantity * p.unit_cost, 2)     AS gross_profit
FROM staging.stg_order_items i
JOIN staging.stg_orders   o USING (order_id)
JOIN staging.stg_products p USING (product_id)
