"""Result rows and per-SNR summaries for the localization noise study.

Error statistics use successful localizations only. A failed solve keeps a
missing error and is counted in the success rate. Failures are not entered
as zero error.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

RESULT_FIELDS = [
    "snr_db",
    "noise_free",
    "trial",
    "source_x_m",
    "source_y_m",
    "source_z_m",
    "est_x_m",
    "est_y_m",
    "est_z_m",
    "est_azimuth_deg",
    "est_elevation_deg",
    "localization_error_m",
    "angular_error_deg",
    "hydrophone_configuration",
    "n_hydrophones",
    "success",
    "failure_reason",
    "noise_seed",
]

SUMMARY_FIELDS = [
    "snr_db",
    "noise_free",
    "n_trials",
    "n_successful",
    "hydrophone_configuration",
    "n_hydrophones",
    "mean_localization_error_m",
    "median_localization_error_m",
    "std_localization_error_m",
    "rmse_localization_error_m",
    "p95_localization_error_m",
    "min_localization_error_m",
    "max_localization_error_m",
    "localization_success_rate",
    "mean_angular_error_deg",
    "median_angular_error_deg",
    "std_angular_error_deg",
    "p95_angular_error_deg",
]

STRING_FIELDS = {"hydrophone_configuration", "failure_reason"}
BOOL_FIELDS = {"noise_free", "success"}
INT_FIELDS = {"trial", "n_hydrophones", "n_trials", "n_successful", "noise_seed"}


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def is_noise_free(row: dict[str, Any]) -> bool:
    return as_bool(row["noise_free"])


def is_success(row: dict[str, Any]) -> bool:
    return as_bool(row["success"])


def _finite(values: list[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def _stats(values: list[float] | np.ndarray) -> dict[str, float]:
    """Mean, median, sample standard deviation, RMSE, 95th percentile, min, max.

    The standard deviation uses the sample divisor ``n - 1``. Fewer than two
    finite values leaves the standard deviation undefined.
    """
    finite = _finite(values)
    empty = float("nan")
    if finite.size == 0:
        return {
            "mean": empty,
            "median": empty,
            "std": empty,
            "rmse": empty,
            "p95": empty,
            "min": empty,
            "max": empty,
        }
    std = float(np.std(finite, ddof=1)) if finite.size > 1 else empty
    return {
        "mean": float(np.mean(finite)),
        "median": float(np.median(finite)),
        "std": std,
        "rmse": float(np.sqrt(np.mean(finite**2))),
        "p95": float(np.percentile(finite, 95)),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
    }


def _nan_estimates() -> dict[str, float]:
    missing = float("nan")
    return {
        "est_x_m": missing,
        "est_y_m": missing,
        "est_z_m": missing,
        "est_azimuth_deg": missing,
        "est_elevation_deg": missing,
        "localization_error_m": missing,
        "angular_error_deg": missing,
    }


def _clean_reason(reason: str) -> str:
    text = " ".join(str(reason).split())
    if len(text) > 300:
        return text[:297] + "..."
    return text


def _configuration(value: str, rows: list[dict[str, Any]], key: str) -> str:
    found = {str(row[key]) for row in rows}
    if not found:
        return value
    if len(found) == 1:
        return next(iter(found))
    return "mixed"


def measurement_row(
    raw: dict[str, Any],
    *,
    trial_number: int,
    noise_free: bool,
    configuration: str,
    n_hydrophones: int,
) -> dict[str, Any]:
    """Map one geometry-study trial row onto the noise-study columns."""
    source = np.asarray(
        [raw["source_x_m"], raw["source_y_m"], raw["source_z_m"]],
        dtype=float,
    )
    success = bool(raw["solver_success"])
    snr = float("nan") if noise_free else float(raw["snr_db"])
    row: dict[str, Any] = {
        "snr_db": snr,
        "noise_free": bool(noise_free),
        "trial": int(trial_number),
        "source_x_m": float(source[0]),
        "source_y_m": float(source[1]),
        "source_z_m": float(source[2]),
        "est_x_m": float(raw["est_x_m"]),
        "est_y_m": float(raw["est_y_m"]),
        "est_z_m": float(raw["est_z_m"]),
        "est_azimuth_deg": float(raw["est_azimuth_deg"]),
        "est_elevation_deg": float(raw["est_elevation_deg"]),
        "localization_error_m": float(raw["position_error_m"]),
        "angular_error_deg": float(raw["angular_error_deg"]),
        "hydrophone_configuration": str(configuration),
        "n_hydrophones": int(n_hydrophones),
        "success": success,
        "failure_reason": _clean_reason(raw.get("failure_reason", "")),
        "noise_seed": int(raw["noise_seed"]),
    }
    if not success:
        for key, value in _nan_estimates().items():
            if key in ("localization_error_m", "angular_error_deg", "est_x_m", "est_y_m", "est_z_m"):
                row[key] = value
            elif not np.isfinite(float(row[key])):
                row[key] = value
    return row


def failed_measurement_row(
    *,
    trial_number: int,
    noise_free: bool,
    snr_db: float,
    source_m: np.ndarray,
    configuration: str,
    n_hydrophones: int,
    noise_seed: int,
    failure_reason: str,
) -> dict[str, Any]:
    """A recorded failure. Used when a trial raises instead of returning."""
    source_m = np.asarray(source_m, dtype=float).reshape(3)
    row: dict[str, Any] = {
        "snr_db": float("nan") if noise_free else float(snr_db),
        "noise_free": bool(noise_free),
        "trial": int(trial_number),
        "source_x_m": float(source_m[0]),
        "source_y_m": float(source_m[1]),
        "source_z_m": float(source_m[2]),
        "hydrophone_configuration": str(configuration),
        "n_hydrophones": int(n_hydrophones),
        "success": False,
        "failure_reason": _clean_reason(failure_reason),
        "noise_seed": int(noise_seed),
    }
    row.update(_nan_estimates())
    return row


def _group_key(row: dict[str, Any]) -> tuple[bool, float]:
    if is_noise_free(row):
        return (True, 0.0)
    return (False, float(row["snr_db"]))


def summarize_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One summary row per noise condition, in the order conditions first appear.

    Localization and angular statistics use successful solves only. The
    success rate uses every trial in the group.
    """
    order: list[tuple[bool, float]] = []
    grouped: dict[tuple[bool, float], list[dict[str, Any]]] = {}
    for row in rows:
        key = _group_key(row)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(row)

    summary: list[dict[str, Any]] = []
    for noise_free, snr in order:
        selected = grouped[(noise_free, snr)]
        position: list[float] = []
        angular: list[float] = []
        n_success = 0
        for row in selected:
            if is_success(row):
                n_success += 1
                position.append(float(row["localization_error_m"]))
                angular.append(float(row["angular_error_deg"]))
        position_stats = _stats(position)
        angular_stats = _stats(angular)
        n_trials = len(selected)
        counts = {int(row["n_hydrophones"]) for row in selected}
        n_hydrophones = next(iter(counts)) if len(counts) == 1 else -1
        summary.append(
            {
                "snr_db": float("nan") if noise_free else float(snr),
                "noise_free": noise_free,
                "n_trials": n_trials,
                "n_successful": n_success,
                "hydrophone_configuration": _configuration("", selected, "hydrophone_configuration"),
                "n_hydrophones": n_hydrophones,
                "mean_localization_error_m": position_stats["mean"],
                "median_localization_error_m": position_stats["median"],
                "std_localization_error_m": position_stats["std"],
                "rmse_localization_error_m": position_stats["rmse"],
                "p95_localization_error_m": position_stats["p95"],
                "min_localization_error_m": position_stats["min"],
                "max_localization_error_m": position_stats["max"],
                "localization_success_rate": (n_success / n_trials) if n_trials else math.nan,
                "mean_angular_error_deg": angular_stats["mean"],
                "median_angular_error_deg": angular_stats["median"],
                "std_angular_error_deg": angular_stats["std"],
                "p95_angular_error_deg": angular_stats["p95"],
            }
        )
    return summary


def finite_snr_levels(rows: list[dict[str, Any]]) -> list[float]:
    """Finite SNR values in order of first appearance."""
    levels: list[float] = []
    for row in rows:
        if is_noise_free(row):
            continue
        snr = float(row["snr_db"])
        if np.isfinite(snr) and snr not in levels:
            levels.append(snr)
    return levels
