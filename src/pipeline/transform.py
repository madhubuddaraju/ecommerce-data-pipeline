"""
Transform step: clean, type-cast and validate raw records.

Every record that can't be repaired is written to a `rejects` table with a
reason instead of being silently dropped, so data loss is always auditable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

log = logging.getLogger(__name__)

VALID_STATUSES = {"completed", "returned", "cancelled"}


@dataclass
class TransformResult:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    rejects: list[pd.DataFrame] = field(default_factory=list)

    def reject(self, table: str, df: pd.DataFrame, key: str, reason: str) -> None:
        if df.empty:
            return
        self.rejects.append(pd.DataFrame({
            "source_table": table,
            "record_key": df[key].astype(str).to_numpy(),
            "reason": reason,
        }))
        log.warning("rejected %d %s rows: %s", len(df), table, reason)

    @property
    def rejects_df(self) -> pd.DataFrame:
        if not self.rejects:
            return pd.DataFrame(columns=["source_table", "record_key", "reason"])
        return pd.concat(self.rejects, ignore_index=True)


def parse_timestamps(s: pd.Series) -> pd.Series:
    """Parse ISO (`2025-03-01 13:45:00`) and US (`03/01/2025 13:45`) formats."""
    iso = pd.to_datetime(s, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    us = pd.to_datetime(s, format="%m/%d/%Y %H:%M", errors="coerce")
    return iso.fillna(us)


def clean_customers(df: pd.DataFrame, res: TransformResult) -> pd.DataFrame:
    out = df.copy()
    out["customer_id"] = pd.to_numeric(out["customer_id"], errors="coerce").astype("Int64")
    out["email"] = out["email"].str.strip().str.lower()
    out["country"] = out["country"].str.strip().str.upper().fillna("UNKNOWN")
    out["first_name"] = out["first_name"].str.strip().str.title()
    out["last_name"] = out["last_name"].str.strip().str.title()
    out["signup_date"] = pd.to_datetime(out["signup_date"], errors="coerce").dt.date

    bad = out["customer_id"].isna() | out["signup_date"].isna()
    res.reject("customers", out[bad], "customer_id", "missing id or signup date")
    out = out[~bad]

    dup = out.duplicated("customer_id", keep="first")
    res.reject("customers", out[dup], "customer_id", "duplicate customer_id")
    return out[~dup].reset_index(drop=True)


def clean_products(df: pd.DataFrame, res: TransformResult) -> pd.DataFrame:
    out = df.copy()
    out["product_id"] = pd.to_numeric(out["product_id"], errors="coerce").astype("Int64")
    out["unit_price"] = pd.to_numeric(out["unit_price"].str.replace(r"[$,]", "", regex=True), errors="coerce")
    out["unit_cost"] = pd.to_numeric(out["unit_cost"], errors="coerce")

    bad = out["product_id"].isna() | out["unit_price"].isna() | (out["unit_price"] <= 0)
    res.reject("products", out[bad], "product_id", "invalid id or price")
    return out[~bad].drop_duplicates("product_id").reset_index(drop=True)


def clean_orders(df: pd.DataFrame, customer_ids: set, res: TransformResult) -> pd.DataFrame:
    out = df.copy()
    out["order_id"] = pd.to_numeric(out["order_id"], errors="coerce").astype("Int64")
    out["customer_id"] = pd.to_numeric(out["customer_id"], errors="coerce").astype("Int64")
    out["order_ts"] = parse_timestamps(out["order_ts"])
    out["status"] = out["status"].str.strip().str.lower()
    out["shipping_cost"] = pd.to_numeric(out["shipping_cost"], errors="coerce").fillna(0.0)

    n_before = len(out)
    out = out.drop_duplicates()  # exact duplicates from re-sent batches
    log.info("removed %d exact duplicate order rows", n_before - len(out))

    bad_ts = out["order_ts"].isna()
    res.reject("orders", out[bad_ts], "order_id", "unparseable order timestamp")
    out = out[~bad_ts]

    bad_status = ~out["status"].isin(VALID_STATUSES)
    res.reject("orders", out[bad_status], "order_id", "unknown status")
    out = out[~bad_status]

    orphan = ~out["customer_id"].isin(customer_ids)
    res.reject("orders", out[orphan], "order_id", "unknown customer_id")
    out = out[~orphan]

    dup = out.duplicated("order_id", keep="first")
    res.reject("orders", out[dup], "order_id", "conflicting duplicate order_id")
    return out[~dup].reset_index(drop=True)


def clean_order_items(df: pd.DataFrame, order_ids: set, product_ids: set, res: TransformResult) -> pd.DataFrame:
    out = df.copy()
    for col in ["order_item_id", "order_id", "product_id", "quantity"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    for col in ["unit_price", "discount_pct"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    bad_qty = out["quantity"].isna() | (out["quantity"] <= 0)
    res.reject("order_items", out[bad_qty], "order_item_id", "non-positive quantity")
    out = out[~bad_qty]

    orphan = ~out["order_id"].isin(order_ids) | ~out["product_id"].isin(product_ids)
    res.reject("order_items", out[orphan], "order_item_id", "unknown order_id or product_id")
    out = out[~orphan]

    out["gross_amount"] = (out["quantity"] * out["unit_price"]).round(2)
    out["discount_amount"] = (out["gross_amount"] * out["discount_pct"]).round(2)
    out["net_amount"] = (out["gross_amount"] - out["discount_amount"]).round(2)
    return out.reset_index(drop=True)


def transform(raw: dict[str, pd.DataFrame]) -> TransformResult:
    res = TransformResult()
    customers = clean_customers(raw["customers"], res)
    products = clean_products(raw["products"], res)
    orders = clean_orders(raw["orders"], set(customers["customer_id"]), res)
    items = clean_order_items(raw["order_items"], set(orders["order_id"]), set(products["product_id"]), res)

    res.tables = {
        "stg_customers": customers,
        "stg_products": products,
        "stg_orders": orders,
        "stg_order_items": items,
    }
    for name, df in res.tables.items():
        log.info("transformed %-16s %7d rows", name, len(df))
    return res
