-- Calendar dimension covering the full order history.
WITH bounds AS (
    SELECT min(order_ts)::DATE AS start_date, max(order_ts)::DATE AS end_date
    FROM staging.stg_orders
)
SELECT
    d::DATE                                  AS date_day,
    CAST(strftime(d, '%Y%m%d') AS INTEGER)   AS date_key,
    year(d)                                  AS year,
    quarter(d)                               AS quarter,
    month(d)                                 AS month,
    strftime(d, '%b')                        AS month_name,
    date_trunc('month', d)::DATE             AS month_start,
    dayofweek(d)                             AS day_of_week,
    strftime(d, '%a')                        AS day_name,
    dayofweek(d) IN (0, 6)                   AS is_weekend
FROM bounds, generate_series(bounds.start_date, bounds.end_date, INTERVAL 1 DAY) AS t(d)
