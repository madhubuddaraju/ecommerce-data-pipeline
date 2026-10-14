"""Load step: write raw + staging layers to DuckDB and build SQL models."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

from .config import settings

log = logging.getLogger(__name__)

SCHEMAS = ("raw", "staging", "core", "marts", "audit")


def connect(path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    path = str(path or settings.warehouse_path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(path)
    for schema in SCHEMAS:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    return con


def write_table(con: duckdb.DuckDBPyConnection, schema: str, name: str, df: pd.DataFrame) -> None:
    """Full refresh of a table from a DataFrame (idempotent)."""
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {schema}.{name} AS SELECT * FROM _df")
    con.unregister("_df")


def model_files(sql_dir: Path | None = None) -> list[Path]:
    """SQL models run in layer order (core -> marts), then filename order."""
    sql_dir = sql_dir or settings.sql_dir
    return sorted((sql_dir / "core").glob("*.sql")) + sorted((sql_dir / "marts").glob("*.sql"))


def build_models(con: duckdb.DuckDBPyConnection, sql_dir: Path | None = None) -> list[str]:
    built = []
    for path in model_files(sql_dir):
        schema = path.parent.name
        name = path.stem.split("__", 1)[-1]  # "01__dim_date.sql" -> "dim_date"
        sql = path.read_text()
        con.execute(f"CREATE OR REPLACE TABLE {schema}.{name} AS {sql}")
        rows = con.execute(f"SELECT count(*) FROM {schema}.{name}").fetchone()[0]
        log.info("built %-32s %7d rows", f"{schema}.{name}", rows)
        built.append(f"{schema}.{name}")
    return built
