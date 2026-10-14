import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeline import generate, run  # noqa: E402


@pytest.fixture(scope="session")
def built_warehouse(tmp_path_factory):
    """Run the full pipeline once on a small dataset and return the warehouse path."""
    base = tmp_path_factory.mktemp("pipeline")
    raw_dir = base / "raw"
    generate.generate(out_dir=raw_dir, seed=7, n_orders=4_000)
    warehouse = base / "test.duckdb"
    summary = run.run(warehouse=warehouse, raw_dir=raw_dir)
    return warehouse, summary
