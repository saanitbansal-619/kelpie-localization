"""Summaries for the hydrophone-count study. Failures stay missing, not zero."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

COUNTS = (4, 5, 6)
SNRS = (40.0, 30.0, 20.0, 10.0, 5.0, 0.0)
PRIMARY_SNR_DB = 20.0


def read_results(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def success(row: dict[str, str]) -> bool:
    return str(row["solver_success"]).strip().lower() == "true"


def _finite(row: dict, key: str) -> float | None:
    text = row.get(key, "")
    if text is None or text == "":
        return None
    if isinstance(text, str) and text.lower() == "nan":
        return None
    value = float(text)
    if not np.isfinite(value):
        return None
    return value


def select(rows: list[dict[str, str]], sensor_count: int, snr: float | None = None) -> list[dict[str, str]]:
    chosen = [row for row in rows if int(float(row["sensor_count"])) == int(sensor_count)]
    if snr is not None:
        chosen = [row for row in chosen if float(row["snr_db"]) == float(snr)]
    return chosen


def pair_abs_errors(rows: list[dict[str, str]]) -> np.ndarray:
    values: list[float] = []
    for row in rows:
        count = int(float(row["sensor_count"]))
        for index in range(1, count):
            value = _finite(row, f"tdoa_err_h{index}_us")
            if value is not None:
                values.append(abs(value))
    return np.asarray(values, dtype=float)


def success_metric(rows: list[dict[str, str]], key: str) -> np.ndarray:
    values = []
    for row in rows:
        if not success(row):
            continue
        value = _finite(row, key)
        if value is not None:
            values.append(value)
    return np.asarray(values, dtype=float)


def _median(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.median(values))


def _p95(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.percentile(values, 95))


def _q25(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.percentile(values, 25))


def _q75(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.percentile(values, 75))


def summary_rows(rows: list[dict[str, str]]) -> list[dict[str, float | int | str]]:
    table = []
    for count in COUNTS:
        name = ""
        for row in rows:
            if int(float(row["sensor_count"])) == count:
                name = row["configuration_name"]
                break
        for snr in SNRS:
            selected = select(rows, count, snr)
            tdoa = pair_abs_errors(selected)
            angular = success_metric(selected, "angular_error_deg")
            position = success_metric(selected, "position_error_m")
            n_success = sum(success(row) for row in selected)
            table.append(
                {
                    "sensor_count": count,
                    "configuration": selected[0]["configuration"] if selected else "",
                    "configuration_name": name,
                    "snr_db": snr,
                    "trials": len(selected),
                    "median_tdoa_abs_error_us": _median(tdoa),
                    "p95_tdoa_abs_error_us": _p95(tdoa),
                    "median_angular_error_deg": _median(angular),
                    "p95_angular_error_deg": _p95(angular),
                    "q25_angular_error_deg": _q25(angular),
                    "q75_angular_error_deg": _q75(angular),
                    "median_position_error_m": _median(position),
                    "p95_position_error_m": _p95(position),
                    "q25_position_error_m": _q25(position),
                    "q75_position_error_m": _q75(position),
                    "solver_success_rate": (n_success / len(selected)) if selected else float("nan"),
                    "failure_count": len(selected) - n_success,
                }
            )
    return table


def _lookup(table: list[dict], count: int, snr: float, key: str) -> float:
    for row in table:
        if int(row["sensor_count"]) == int(count) and float(row["snr_db"]) == float(snr):
            return float(row[key])
    raise KeyError((count, snr, key))


def _percent_change(new: float, old: float) -> float:
    if not np.isfinite(new) or not np.isfinite(old) or old == 0.0:
        return float("nan")
    return 100.0 * (new - old) / old


def comparison_rows(table: list[dict], snr: float = PRIMARY_SNR_DB) -> list[dict[str, float | str]]:
    """Percent change in error, and percentage-point change in success.

    A negative percent change in an error is a reduction of that error.
    Success is reported in percentage points, not as a relative percent.
    """
    pairs = (("5_vs_4", 5, 4), ("6_vs_4", 6, 4), ("6_vs_5", 6, 5))
    rows = []
    for label, newer, older in pairs:
        ang_new = _lookup(table, newer, snr, "median_angular_error_deg")
        ang_old = _lookup(table, older, snr, "median_angular_error_deg")
        pos_new = _lookup(table, newer, snr, "median_position_error_m")
        pos_old = _lookup(table, older, snr, "median_position_error_m")
        suc_new = _lookup(table, newer, snr, "solver_success_rate")
        suc_old = _lookup(table, older, snr, "solver_success_rate")
        rows.append(
            {
                "comparison": label,
                "snr_db": snr,
                "median_angular_error_deg_new": ang_new,
                "median_angular_error_deg_baseline": ang_old,
                "angular_error_percent_change": _percent_change(ang_new, ang_old),
                "median_position_error_m_new": pos_new,
                "median_position_error_m_baseline": pos_old,
                "position_error_percent_change": _percent_change(pos_new, pos_old),
                "success_rate_new": suc_new,
                "success_rate_baseline": suc_old,
                "success_rate_percentage_point_change": 100.0 * (suc_new - suc_old),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
