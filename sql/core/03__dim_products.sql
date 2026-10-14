-- Product catalog with list margin.
SELECT
    product_id,
    sku,
    product_name,
    category,
    unit_price                                          AS list_price,
    unit_cost,
    round((unit_price - unit_cost) / unit_price, 4)     AS list_margin_pct
FROM staging.stg_products
