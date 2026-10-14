import pandas as pd

from pipeline.transform import (
    TransformResult,
    clean_customers,
    clean_order_items,
    clean_orders,
    clean_products,
    parse_timestamps,
)


def test_parse_timestamps_handles_iso_and_us_formats():
    s = pd.Series(["2025-03-01 13:45:00", "03/01/2025 13:45", "not a date"])
    out = parse_timestamps(s)
    assert out[0] == pd.Timestamp("2025-03-01 13:45:00")
    assert out[1] == pd.Timestamp("2025-03-01 13:45:00")
    assert pd.isna(out[2])


def test_clean_customers_normalises_email_and_country():
    raw = pd.DataFrame({
        "customer_id": ["1", "2", "2"],
        "first_name": ["ana", "BOB", "BOB"],
        "last_name": ["lee", "ray", "ray"],
        "email": ["  ANA.LEE@EXAMPLE.COM ", "bob@example.com", "bob@example.com"],
        "country": ["us", None, None],
        "acquisition_channel": ["email", "social", "social"],
        "signup_date": ["2024-01-05", "2024-02-01", "2024-02-01"],
    })
    res = TransformResult()
    out = clean_customers(raw, res)
    assert len(out) == 2
    assert out.loc[0, "email"] == "ana.lee@example.com"
    assert out.loc[0, "country"] == "US"
    assert out.loc[1, "country"] == "UNKNOWN"
    assert out.loc[0, "first_name"] == "Ana"
    assert res.rejects_df["reason"].tolist() == ["duplicate customer_id"]


def test_clean_products_strips_currency_symbols():
    raw = pd.DataFrame({"product_id": ["1", "2"], "sku": ["A", "B"], "product_name": ["x", "y"],
                        "category": ["Books", "Books"], "unit_price": ["$12.50", "-3"], "unit_cost": ["5", "1"]})
    res = TransformResult()
    out = clean_products(raw, res)
    assert out["unit_price"].tolist() == [12.5]
    assert len(res.rejects_df) == 1


def test_clean_orders_dedupes_and_rejects_bad_rows():
    raw = pd.DataFrame({
        "order_id": ["10", "10", "11", "12", "13"],
        "customer_id": ["1", "1", "1", "99", "1"],
        "order_ts": ["2025-01-01 10:00:00", "2025-01-01 10:00:00", "01/02/2025 09:30",
                     "2025-01-03 10:00:00", "garbage"],
        "status": ["completed", "completed", "RETURNED", "completed", "completed"],
        "payment_method": ["card"] * 5,
        "shipping_cost": ["0", "0", "4.99", "0", "0"],
    })
    res = TransformResult()
    out = clean_orders(raw, customer_ids={1}, res=res)
    assert sorted(out["order_id"].tolist()) == [10, 11]
    assert set(out["status"]) == {"completed", "returned"}
    reasons = set(res.rejects_df["reason"])
    assert reasons == {"unknown customer_id", "unparseable order timestamp"}


def test_clean_order_items_computes_amounts_and_rejects_negative_qty():
    raw = pd.DataFrame({"order_item_id": ["1", "2"], "order_id": ["10", "10"], "product_id": ["5", "5"],
                        "quantity": ["2", "-1"], "unit_price": ["10.0", "10.0"], "discount_pct": ["0.1", "0"]})
    res = TransformResult()
    out = clean_order_items(raw, order_ids={10}, product_ids={5}, res=res)
    assert len(out) == 1
    row = out.iloc[0]
    assert (row.gross_amount, row.discount_amount, row.net_amount) == (20.0, 2.0, 18.0)
    assert res.rejects_df["reason"].tolist() == ["non-positive quantity"]
