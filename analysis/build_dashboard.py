"""
Build the static web dashboard (docs/index.html, served by GitHub Pages) from the warehouse marts.

    python analysis/build_dashboard.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
TEMPLATE = ROOT / "dashboard" / "template.html"
OUT = ROOT / "docs" / "index.html"


def rows(con, sql: str) -> list:
    return [list(r) for r in con.execute(sql).fetchall()]


def build() -> Path:
    if not WAREHOUSE.exists():
        sys.exit("warehouse not found - run `make pipeline` first")
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    months = [r[0] for r in con.execute(
        "SELECT strftime(month, '%Y-%m') FROM marts.monthly_revenue ORDER BY month").fetchall()]
    countries = [r[0] for r in con.execute("SELECT DISTINCT country FROM core.dim_customers ORDER BY 1").fetchall()]
    mi = {m: i for i, m in enumerate(months)}
    ci = {c: i for i, c in enumerate(countries)}
    cats = [r[0] for r in con.execute("SELECT DISTINCT category FROM core.dim_products ORDER BY 1").fetchall()]

    agg = rows(con, """
        SELECT strftime(f.order_date, '%Y-%m'), d.country, count(*), round(sum(net_amount), 2),
               round(coalesce(sum(net_amount) FILTER (WHERE is_first_order), 0), 2), round(sum(gross_profit), 2)
        FROM core.fct_orders f JOIN core.dim_customers d USING (customer_id)
        WHERE status = 'completed' GROUP BY 1, 2""")
    act = rows(con, """
        SELECT DISTINCT strftime(f.order_date, '%Y-%m'), d.country, customer_id
        FROM core.fct_orders f JOIN core.dim_customers d USING (customer_id) WHERE status = 'completed'""")
    cat = rows(con, """
        SELECT strftime(i.order_date, '%Y-%m'), d.country, p.category, round(sum(i.net_amount), 2)
        FROM core.fct_order_items i JOIN core.dim_products p USING (product_id)
        JOIN core.dim_customers d USING (customer_id) WHERE i.status = 'completed' GROUP BY 1, 2, 3""")
    run = con.execute("SELECT started_at, status, duration_s, raw_order_rows, rejected_rows "
                      "FROM audit.pipeline_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    data = {
        "months": months, "countries": countries, "cats": cats,
        "agg": [[mi[m], ci[c], o, r, nr, gp] for m, c, o, r, nr, gp in agg],
        "act": [[mi[m], ci[c], cid] for m, c, cid in act],
        "cat": [[mi[m], ci[c], cats.index(g), v] for m, c, g, v in cat],
        "ch": rows(con, "SELECT acquisition_channel, customers, conversion_rate, repeat_purchase_rate, "
                        "revenue_per_customer, total_revenue FROM marts.channel_performance"),
        "coh": rows(con, "SELECT strftime(cohort_month, '%Y-%m'), months_since_first, retention_rate, cohort_size "
                         "FROM marts.cohort_retention WHERE months_since_first <= 12"),
        "rfm": rows(con, "SELECT segment, count(*), round(sum(monetary)), round(avg(recency_days)), "
                         "round(avg(frequency), 1) FROM marts.customer_rfm GROUP BY 1 ORDER BY 3 DESC"),
        "prod": rows(con, "SELECT sku, product_name, category, units_sold, revenue, margin_pct, return_rate "
                          "FROM marts.product_performance LIMIT 12"),
        "dq": rows(con, "SELECT check_name, severity, failing_rows, passed FROM audit.dq_results"),
        "run": [run[0].strftime("%Y-%m-%d %H:%M UTC"), run[1], run[2], run[3], run[4]],
        "rej": rows(con, "SELECT reason, count(*) FROM audit.rejects GROUP BY 1"),
    }
    con.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(data, separators=(",", ":"))))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    return OUT


if __name__ == "__main__":
    build()
