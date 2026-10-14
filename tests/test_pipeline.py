import duckdb
import pandas as pd
import pytest

from pipeline import quality


def test_pipeline_builds_all_models(built_warehouse):
    _, summary = built_warehouse
    assert summary["checks_passed"] == summary["checks_total"]
    expected = {"core.dim_date", "core.dim_customers", "core.dim_products", "core.fct_orders",
                "core.fct_order_items", "marts.monthly_revenue", "marts.customer_rfm",
                "marts.cohort_retention", "marts.product_performance", "marts.channel_performance"}
    assert expected <= set(summary["models"])


def test_revenue_reconciles_across_layers(built_warehouse):
    warehouse, _ = built_warehouse
    with duckdb.connect(str(warehouse), read_only=True) as con:
        items = con.execute("""SELECT sum(i.net_amount) FROM staging.stg_order_items i
                               JOIN staging.stg_orders o USING (order_id)
                               WHERE o.status = 'completed'""").fetchone()[0]
        mart = con.execute("SELECT sum(revenue) FROM marts.monthly_revenue").fetchone()[0]
    assert mart == pytest.approx(items, abs=1.0)


def test_rfm_segments_cover_every_buyer(built_warehouse):
    warehouse, _ = built_warehouse
    with duckdb.connect(str(warehouse), read_only=True) as con:
        buyers = con.execute("SELECT count(DISTINCT customer_id) FROM core.fct_orders "
                             "WHERE status = 'completed'").fetchone()[0]
        rfm = con.execute("SELECT count(*), count(segment) FROM marts.customer_rfm").fetchone()
    assert rfm == (buyers, buyers)


def test_pipeline_is_idempotent(built_warehouse, tmp_path):
    """Running twice produces identical marts (full-refresh semantics)."""
    from pipeline import run
    warehouse, _ = built_warehouse
    raw_dir = warehouse.parent / "raw"
    with duckdb.connect(str(warehouse), read_only=True) as con:
        before = con.execute("SELECT * FROM marts.monthly_revenue ORDER BY month").df()
    run.run(warehouse=warehouse, raw_dir=raw_dir)
    with duckdb.connect(str(warehouse), read_only=True) as con:
        after = con.execute("SELECT * FROM marts.monthly_revenue ORDER BY month").df()
        runs = con.execute("SELECT count(*) FROM audit.pipeline_runs").fetchone()[0]
    pd.testing.assert_frame_equal(before, after)
    assert runs == 2


def test_quality_checks_catch_bad_data():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES (1), (1), (NULL)) v(id)")
    checks = [quality.unique("t", "id"), quality.not_null("t", "id")]
    results = quality.run_checks(con, checks, raise_on_error=False)
    assert not results["passed"].any()
    with pytest.raises(quality.DataQualityError):
        quality.run_checks(con, checks)
