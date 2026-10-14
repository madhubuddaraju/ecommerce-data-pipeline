"""
Generate a realistic (and intentionally messy) e-commerce dataset.

The raw files mimic exports from an operational system: they contain
duplicates, inconsistent casing, mixed date formats, missing values and a
few invalid records, so the transform step has real cleaning work to do.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import settings

log = logging.getLogger(__name__)

COUNTRIES = ["US", "CA", "GB", "DE", "FR", "IN", "AU", "BR", "NL", "ES"]
COUNTRY_WEIGHTS = [0.38, 0.08, 0.11, 0.09, 0.07, 0.09, 0.05, 0.05, 0.04, 0.04]
CHANNELS = ["organic", "paid_search", "social", "email", "referral"]
CHANNEL_WEIGHTS = [0.32, 0.25, 0.2, 0.13, 0.1]

CATEGORIES = {
    # category: (min_price, max_price, popularity weight)
    "Electronics": (25, 900, 0.18),
    "Home & Kitchen": (8, 250, 0.20),
    "Clothing": (10, 120, 0.22),
    "Beauty": (5, 80, 0.12),
    "Sports": (12, 300, 0.10),
    "Books": (6, 45, 0.10),
    "Toys": (8, 110, 0.08),
}

ADJECTIVES = ["Classic", "Pro", "Eco", "Smart", "Ultra", "Compact", "Premium", "Essential", "Deluxe", "Lite"]
NOUNS = {
    "Electronics": ["Headphones", "Speaker", "Charger", "Monitor", "Keyboard", "Webcam", "Tablet"],
    "Home & Kitchen": ["Blender", "Pan Set", "Lamp", "Kettle", "Organizer", "Knife Set", "Mug"],
    "Clothing": ["Hoodie", "Jacket", "T-Shirt", "Jeans", "Sneakers", "Scarf", "Cap"],
    "Beauty": ["Serum", "Moisturizer", "Shampoo", "Lip Balm", "Face Mask", "Perfume"],
    "Sports": ["Yoga Mat", "Dumbbells", "Water Bottle", "Running Belt", "Tennis Racket"],
    "Books": ["Cookbook", "Novel", "Notebook", "Planner", "Guidebook"],
    "Toys": ["Puzzle", "Building Set", "Board Game", "Plush Toy", "RC Car"],
}

FIRST = ["James", "Mary", "Liam", "Olivia", "Noah", "Emma", "Arjun", "Priya", "Lucas", "Sofia",
         "Ethan", "Mia", "Kenji", "Aiko", "Mateo", "Lea", "Omar", "Zara", "Hugo", "Anna"]
LAST = ["Smith", "Johnson", "Brown", "Garcia", "Miller", "Patel", "Kumar", "Muller", "Martin",
        "Rossi", "Silva", "Tanaka", "Nguyen", "Lopez", "Wilson", "Khan", "Dubois", "Jansen"]


def _customers(rng: np.random.Generator, n: int, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    ids = np.arange(1, n + 1)
    first = rng.choice(FIRST, n)
    last = rng.choice(LAST, n)
    span = (end - start).days
    # more sign-ups later in the period (growing business)
    signup_offsets = (rng.beta(1.15, 1.0, n) * span).astype(int)
    signup = start + pd.to_timedelta(signup_offsets, unit="D")

    emails = [f"{fn}.{ln}{i}@example.com".lower() for fn, ln, i in zip(first, last, ids, strict=True)]
    # messiness: random upper-casing and whitespace
    messy = rng.random(n) < 0.07
    emails = [f"  {e.upper()} " if m else e for e, m in zip(emails, messy, strict=False)]

    country = rng.choice(COUNTRIES, n, p=COUNTRY_WEIGHTS).astype(object)
    country[rng.random(n) < 0.02] = None
    lowercase = rng.random(n) < 0.05
    country = np.where(lowercase & pd.notna(country), pd.Series(country).str.lower(), country)

    return pd.DataFrame({
        "customer_id": ids,
        "first_name": first,
        "last_name": last,
        "email": emails,
        "country": country,
        "acquisition_channel": rng.choice(CHANNELS, n, p=CHANNEL_WEIGHTS),
        "signup_date": signup.strftime("%Y-%m-%d"),
    })


def _products(rng: np.random.Generator, n: int) -> pd.DataFrame:
    cats = list(CATEGORIES)
    weights = np.array([CATEGORIES[c][2] for c in cats])
    category = rng.choice(cats, n, p=weights / weights.sum())
    rows = []
    for pid, cat in enumerate(category, start=1):
        lo, hi, _ = CATEGORIES[cat]
        price = round(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))), 2)
        cost = round(price * rng.uniform(0.35, 0.7), 2)
        name = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS[cat])}"
        price_str = f"${price}" if rng.random() < 0.04 else str(price)  # messy currency strings
        rows.append((pid, f"SKU-{pid:05d}", name, cat, price_str, cost))
    return pd.DataFrame(rows, columns=["product_id", "sku", "product_name", "category", "unit_price", "unit_cost"])


def _orders(rng, customers: pd.DataFrame, n: int, end: pd.Timestamp) -> pd.DataFrame:
    # heavy-tailed propensity: a small share of customers place most orders
    propensity = rng.pareto(1.6, len(customers)) + 0.2
    # channel quality differs: referral/email customers buy more often than social/paid
    channel_lift = {"referral": 1.5, "email": 1.3, "organic": 1.0, "paid_search": 0.85, "social": 0.7}
    propensity *= customers["acquisition_channel"].map(channel_lift).to_numpy()
    never_buy = {"referral": 0.12, "email": 0.15, "organic": 0.2, "paid_search": 0.26, "social": 0.32}
    p_never = customers["acquisition_channel"].map(never_buy).to_numpy()
    propensity[rng.random(len(customers)) < p_never] = 0  # registered but never bought
    cust_idx = rng.choice(len(customers), n, p=propensity / propensity.sum())
    signup = pd.to_datetime(customers["signup_date"].to_numpy()[cust_idx])

    days_available = (end - signup).days.to_numpy().clip(min=0)
    offsets = (rng.random(n) ** 1.6 * days_available).astype(int)
    order_date = signup + pd.to_timedelta(offsets, unit="D")

    # seasonality: re-sample some orders into Nov/Dec (holiday peak)
    holiday = rng.random(n) < 0.12
    peak_dates = pd.to_datetime([
        f"{y}-{m:02d}-{d:02d}" for y, m, d in zip(
            rng.choice([2024, 2025], n), rng.choice([11, 12], n), rng.integers(1, 29, n), strict=False)
    ])
    order_date = pd.DatetimeIndex(np.where(holiday & (peak_dates >= signup), peak_dates, order_date))
    order_ts = order_date + pd.to_timedelta(rng.integers(0, 86_400, n), unit="s")

    status = rng.choice(["completed", "returned", "cancelled"], n, p=[0.9, 0.06, 0.04])
    df = pd.DataFrame({
        "order_id": np.arange(100_001, 100_001 + n),
        "customer_id": customers["customer_id"].to_numpy()[cust_idx],
        "order_ts": order_ts,
        "status": status,
        "payment_method": rng.choice(["card", "paypal", "apple_pay", "gift_card"], n, p=[0.6, 0.22, 0.13, 0.05]),
        "shipping_cost": np.round(rng.choice([0, 4.99, 7.99, 12.99], n, p=[0.45, 0.3, 0.18, 0.07]), 2),
    }).sort_values("order_ts").reset_index(drop=True)

    # messiness: mixed timestamp formats and inconsistent status casing
    ts_str = df["order_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    us_fmt = rng.random(n) < 0.08
    ts_str = ts_str.where(~us_fmt, df["order_ts"].dt.strftime("%m/%d/%Y %H:%M"))
    df["order_ts"] = ts_str
    upper = rng.random(n) < 0.05
    df["status"] = df["status"].where(~upper, df["status"].str.upper())

    # duplicate ~1% of rows (re-sent export batches)
    dupes = df.sample(frac=0.01, random_state=int(rng.integers(1e6)))
    return pd.concat([df, dupes]).sample(frac=1, random_state=7).reset_index(drop=True)


def _order_items(rng, orders: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    unique_orders = orders.drop_duplicates("order_id")["order_id"].to_numpy()
    n_items = rng.choice([1, 2, 3, 4, 5], len(unique_orders), p=[0.48, 0.27, 0.14, 0.07, 0.04])
    order_ids = np.repeat(unique_orders, n_items)
    m = len(order_ids)

    popularity = rng.lognormal(0, 1.0, len(products))
    prod_idx = rng.choice(len(products), m, p=popularity / popularity.sum())
    base_price = pd.to_numeric(products["unit_price"].str.replace("$", "", regex=False)).to_numpy()

    qty = rng.choice([1, 1, 1, 2, 2, 3, 4], m)
    qty[rng.random(m) < 0.003] = -1  # invalid records from a buggy client
    discount = rng.choice([0, 0, 0, 0.05, 0.1, 0.15, 0.2], m)

    return pd.DataFrame({
        "order_item_id": np.arange(1, m + 1),
        "order_id": order_ids,
        "product_id": products["product_id"].to_numpy()[prod_idx],
        "quantity": qty,
        "unit_price": base_price[prod_idx],
        "discount_pct": discount,
    })


def generate(out_dir=None, seed: int | None = None, n_orders: int | None = None) -> dict[str, pd.DataFrame]:
    """Create raw CSV files and return them as DataFrames."""
    out_dir = out_dir or settings.raw_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(settings.seed if seed is None else seed)
    start, end = pd.Timestamp(settings.start_date), pd.Timestamp(settings.end_date)

    customers = _customers(rng, settings.n_customers, start, end)
    products = _products(rng, settings.n_products)
    orders = _orders(rng, customers, n_orders or settings.n_orders, end)
    items = _order_items(rng, orders, products)

    tables = {"customers": customers, "products": products, "orders": orders, "order_items": items}
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
        log.info("wrote %-12s %7d rows", name, len(df))
    return tables


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    generate()
