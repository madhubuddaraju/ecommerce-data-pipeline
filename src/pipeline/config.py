"""Central configuration for paths and pipeline settings."""

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    warehouse_path: Path = PROJECT_ROOT / "data" / "warehouse.duckdb"
    sql_dir: Path = PROJECT_ROOT / "sql"
    reports_dir: Path = PROJECT_ROOT / "reports"

    # data generation
    seed: int = 42
    n_customers: int = 5_000
    n_products: int = 250
    n_orders: int = 45_000
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"

    raw_tables: tuple = field(
        default=("customers", "products", "orders", "order_items")
    )


settings = Settings()
