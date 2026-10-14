"""Extract step: read raw CSV exports exactly as delivered (all columns as text)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .config import settings

log = logging.getLogger(__name__)


def extract(raw_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    raw_dir = raw_dir or settings.raw_dir
    frames = {}
    for name in settings.raw_tables:
        path = raw_dir / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"missing raw file: {path} (run `make data` first)")
        # read as strings so no information is lost before validation
        frames[name] = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
        log.info("extracted %-12s %7d rows", name, len(frames[name]))
    return frames
