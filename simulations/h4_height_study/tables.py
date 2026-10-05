"""CSV IO for the H4 height study. Writes only inside the study folder."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from simulations.h4_height_study.paths import assert_output_path

STRING_FIELDS = {
    "study",
    "h4_name",
    "direction",
    "flag",
    "noise_free",
    "snr_scope",
    "snr_label",
    "scope",
    "best_h4_name",
    "neg_name",
    "pos_name",
    "note",
    "failure_reason",
    "hydrophone_configuration",
    "flags",
}
INT_FIELDS = {
    "n_trials",
    "n_successful",
    "n_sources",
    "trial",
    "source_id",
    "rank_median",
    "rank_p95",
    "rank_angular",
    "rank_success",
    "rank_catastrophic",
    "rank_consistency",
    "rank_tdoa",
    "rank_sum",
    "rank_overall",
}


def write_table(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path = assert_output_path(path)
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
        if isinstance(value, bool):
            return "true" if value else "false"
        return "" if value is None else str(value)
    if key in INT_FIELDS:
        if value is None or value == "" or (isinstance(value, float) and not np.isfinite(value)):
            return ""
        return str(int(value))
    if isinstance(value, bool):
        return "true" if value else "false"
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
