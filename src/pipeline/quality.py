"""
Data quality checks run against the warehouse after every build.

Each check is a SQL query that returns the number of *failing* rows.
`error` checks stop the pipeline; `warn` checks are logged only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import duckdb
import pandas as pd

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Check:
    name: str
    sql: str
    severity: str = "error"  # "error" | "warn"


def unique(table: str, col: str) -> Check:
    return Check(f"{table}.{col} is unique",
                 f"SELECT count(*) - count(DISTINCT {col}) FROM {table}")


def not_null(table: str, col: str) -> Check:
    return Check(f"{table}.{col} not null",
                 f"SELECT count(*) FROM {table} WHERE {col} IS NULL")


def relationship(child: str, col: str, parent: str, parent_col: str | None = None) -> Check:
    parent_col = parent_col or col
    return Check(f"{child}.{col} -> {parent}.{parent_col}",
                 f"SELECT count(*) FROM {child} c "
                 f"LEFT JOIN {parent} p ON c.{col} = p.{parent_col} "
                 f"WHERE c.{col} IS NOT NULL AND p.{parent_col} IS NULL")


CHECKS: list[Check] = [
    unique("core.dim_customers", "customer_id"),
    unique("core.dim_products", "product_id"),
    unique("core.fct_orders", "order_id"),
    unique("core.fct_order_items", "order_item_id"),
    unique("core.dim_date", "date_key"),
    not_null("core.fct_orders", "order_ts"),
    not_null("core.fct_orders", "customer_id"),
    relationship("core.fct_orders", "customer_id", "core.dim_customers"),
    relationship("core.fct_order_items", "product_id", "core.dim_products"),
    relationship("core.fct_order_items", "order_id", "core.fct_orders"),
    relationship("core.fct_orders", "date_key", "core.dim_date"),
    Check("fct_order_items.quantity > 0",
          "SELECT count(*) FROM core.fct_order_items WHERE quantity <= 0"),
    Check("fct_order_items.net_amount <= gross_amount",
          "SELECT count(*) FROM core.fct_order_items WHERE net_amount > gross_amount + 0.01"),
    Check("fct_orders.status in accepted values",
          "SELECT count(*) FROM core.fct_orders WHERE status NOT IN ('completed','returned','cancelled')"),
    Check("order totals reconcile with line items",
          """SELECT count(*) FROM core.fct_orders o
             JOIN (SELECT order_id, sum(net_amount) s FROM core.fct_order_items GROUP BY 1) i USING (order_id)
             WHERE abs(o.net_amount - i.s) > 0.01"""),
    Check("monthly revenue reconciles with fct_orders",
          """SELECT abs((SELECT sum(revenue) FROM marts.monthly_revenue) -
                        (SELECT sum(net_amount) FROM core.fct_orders WHERE status='completed')) > 1"""),
    Check("retention rate between 0 and 1",
          "SELECT count(*) FROM marts.cohort_retention WHERE retention_rate NOT BETWEEN 0 AND 1"),
    Check("no orders before customer signup",
          """SELECT count(*) FROM core.fct_orders f JOIN core.dim_customers c USING (customer_id)
             WHERE f.order_date < c.signup_date""", severity="warn"),
    Check("reject rate under 2% of raw order items",
          """SELECT (SELECT count(*) FROM audit.rejects WHERE source_table='order_items')
                    > 0.02 * (SELECT count(*) FROM raw.order_items)""", severity="warn"),
]


class DataQualityError(RuntimeError):
    pass


def run_checks(con: duckdb.DuckDBPyConnection, checks: list[Check] | None = None,
               raise_on_error: bool = True) -> pd.DataFrame:
    rows = []
    for check in checks or CHECKS:
        failures = int(con.execute(check.sql).fetchone()[0])
        passed = failures == 0
        rows.append({"check_name": check.name, "severity": check.severity,
                     "failing_rows": failures, "passed": passed})
        level = logging.INFO if passed else (logging.ERROR if check.severity == "error" else logging.WARNING)
        log.log(level, "[%s] %s (%d failing)", "PASS" if passed else "FAIL", check.name, failures)

    results = pd.DataFrame(rows)
    results["checked_at"] = pd.Timestamp.now(tz="UTC").tz_localize(None)

    errors = results[(~results["passed"]) & (results["severity"] == "error")]
    if raise_on_error and not errors.empty:
        raise DataQualityError(f"{len(errors)} data quality check(s) failed: "
                               + ", ".join(errors["check_name"]))
    return results
