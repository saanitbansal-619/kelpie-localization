"""CSV IO for the joint geometry study. Writes only inside the study folder."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from simulations.joint_geometry_study.paths import assert_output_path

STRING_FIELDS = {
    "geometry_id",
    "channel",
    "label",
    "direction",
    "flag",
    "roles",
    "snr_label",
    "noise_free",
    "failure_reason",
    "flags",
    "hydrophone_configuration",
    "note",
    "selection",
}
INT_FIELDS = {
    "n_trials",
    "n_successful",
    "n_sources",
    "trial",
    "source_id",
    "noise_seed",
    "n_hydrophones",
    "rank_accuracy",
    "rank_reliability",
    "rank_balanced",
    "rank_median",
    "rank_p95",
    "rank_angular",
    "rank_success",
    "rank_catastrophic",
}
BOOL_FIELDS = {"is_control", "success", "apply_attenuation", "pareto", "noise_free"}


def write_table(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path = assert_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _format(key, row.get(key, "")) for key in fieldnames})


def _format(key: str, value: Any) -> str:
    if key in STRING_FIELDS - BOOL_FIELDS:
        return "" if value is None else str(value)
    if key in BOOL_FIELDS or isinstance(value, bool):
        if value is None or value == "":
            return ""
        if isinstance(value, str):
            return value.strip().lower()
        return "true" if value else "false"
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
