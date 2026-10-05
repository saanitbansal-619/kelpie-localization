"""CSV writer for comparison tables.

Numeric fields are written with the same blank-for-non-finite rule as the
noise and waveform studies. String fields are written as text.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

STRING_FIELDS = {
    "study",
    "geometry",
    "direction",
    "snr_scope",
    "noise_free",
    "geometry_name",
}
INT_FIELDS = {"number_of_trials", "n_sources", "n_successful", "n_trials"}


def write_table(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _format(key, row.get(key, "")) for key in fieldnames})


def read_table(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        return [{key: _parse(key, raw.get(key, "")) for key in fieldnames} for raw in reader]


def _format(key: str, value: Any) -> str:
    if key in STRING_FIELDS:
        return "" if value is None else str(value)
    if key in INT_FIELDS:
        if value is None or value == "" or (isinstance(value, float) and not np.isfinite(value)):
            return ""
        return str(int(value))
    if value is None or value == "":
        return ""
    number = float(value)
    if not np.isfinite(number):
        return ""
    return f"{number:.10g}"


def _parse(key: str, value: str) -> Any:
    if key in STRING_FIELDS:
        return value
    if key in INT_FIELDS:
        return int(value) if value != "" else 0
    if value == "":
        return float("nan")
    return float(value)
