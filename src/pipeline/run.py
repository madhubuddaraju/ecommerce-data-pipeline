"""
Pipeline orchestrator.

    python -m pipeline                # extract -> transform -> load -> build -> test
    python -m pipeline --generate     # also (re)generate the raw source data first
"""

from __future__ import annotations

import argparse
import logging
import time
import uuid
from pathlib import Path

import pandas as pd

from . import extract, generate, load, quality, transform
from .config import settings

log = logging.getLogger("pipeline")


def run(warehouse: Path | str | None = None, raw_dir: Path | None = None,
        regenerate: bool = False) -> dict:
    run_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    started_at = pd.Timestamp.now(tz="UTC").tz_localize(None)
    log.info("pipeline run %s started", run_id)

    if regenerate:
        generate.generate(out_dir=raw_dir)

    raw = extract.extract(raw_dir)
    result = transform.transform(raw)

    con = load.connect(warehouse)
    status = "failed"
    try:
        for name, df in raw.items():
            load.write_table(con, "raw", name, df)
        for name, df in result.tables.items():
            load.write_table(con, "staging", name, df)
        load.write_table(con, "audit", "rejects", result.rejects_df)

        built = load.build_models(con)
        dq = quality.run_checks(con)
        dq["run_id"] = run_id
        load.write_table(con, "audit", "dq_results", dq)
        status = "success"
        return {"run_id": run_id, "models": built, "rejects": len(result.rejects_df),
                "checks_passed": int(dq["passed"].sum()), "checks_total": len(dq)}
    finally:
        elapsed = round(time.perf_counter() - started, 2)
        con.execute("""CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
                           run_id VARCHAR, started_at TIMESTAMP, status VARCHAR,
                           duration_s DOUBLE, raw_order_rows BIGINT, rejected_rows BIGINT)""")
        con.execute("INSERT INTO audit.pipeline_runs VALUES (?, ?, ?, ?, ?, ?)",
                    [run_id, started_at, status, elapsed, len(raw["orders"]), len(result.rejects_df)])
        con.close()
        log.info("pipeline run %s finished: %s in %.2fs", run_id, status, elapsed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the e-commerce data pipeline")
    parser.add_argument("--generate", action="store_true", help="regenerate raw source data first")
    parser.add_argument("--warehouse", default=None, help="path to DuckDB file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

    needs_data = not (settings.raw_dir / "orders.csv").exists()
    try:
        summary = run(args.warehouse, regenerate=args.generate or needs_data)
    except quality.DataQualityError as exc:
        log.error(str(exc))
        return 1
    log.info("summary: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
