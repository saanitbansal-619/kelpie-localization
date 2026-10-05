"""Summaries for the pulsed-pinger waveform experiment.

Localization and angular statistics use successful solves only. Absolute
TDOA error uses every finite non-reference pair, including trials the
solver rejected. A rejected solve does not contribute zero localization error.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

RESULT_FIELDS = [
    "snr_db",
    "noise_free",
    "trial",
    "source_id",
    "carrier_frequency_hz",
    "pulse_duration_s",
    "sample_rate_hz",
    "apply_attenuation",
    "source_x_m",
    "source_y_m",
    "source_z_m",
    "est_x_m",
    "est_y_m",
    "est_z_m",
    "true_tdoa_h1_us",
    "true_tdoa_h2_us",
    "true_tdoa_h3_us",
    "est_tdoa_h1_us",
    "est_tdoa_h2_us",
    "est_tdoa_h3_us",
    "tdoa_err_h1_us",
    "tdoa_err_h2_us",
    "tdoa_err_h3_us",
    "mean_abs_tdoa_error_us",
    "localization_error_m",
    "angular_error_deg",
    "hydrophone_configuration",
    "n_hydrophones",
    "success",
    "failure_reason",
    "flags",
    "noise_seed",
    "physical_max_tdoa_us",
    "arrival_h0_us",
]

SUMMARY_FIELDS = [
    "snr_db",
    "noise_free",
    "carrier_frequency_hz",
    "n_trials",
    "n_successful",
    "mean_localization_error_m",
    "median_localization_error_m",
    "p95_localization_error_m",
    "rmse_localization_error_m",
    "mean_abs_tdoa_error_us",
    "median_abs_tdoa_error_us",
    "mean_angular_error_deg",
    "median_angular_error_deg",
    "localization_success_rate",
    "n_flagged",
    "n_huge_localization_error",
    "n_boundary_peaks",
    "n_tdoa_outside_limit",
]

STRING_FIELDS = {"hydrophone_configuration", "failure_reason", "flags"}
BOOL_FIELDS = {"noise_free", "success", "apply_attenuation"}
INT_FIELDS = {
    "trial",
    "source_id",
    "n_hydrophones",
    "n_trials",
    "n_successful",
    "noise_seed",
    "n_flagged",
    "n_huge_localization_error",
    "n_boundary_peaks",
    "n_tdoa_outside_limit",
}


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def is_noise_free(row: dict[str, Any]) -> bool:
    return as_bool(row["noise_free"])


def is_success(row: dict[str, Any]) -> bool:
    return as_bool(row["success"])


def _finite(values: list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array[np.isfinite(array)]


def _stats(values: list[float]) -> dict[str, float]:
    finite = _finite(values)
    empty = float("nan")
    if finite.size == 0:
        return {"mean": empty, "median": empty, "p95": empty, "rmse": empty}
    return {
        "mean": float(np.mean(finite)),
        "median": float(np.median(finite)),
        "p95": float(np.percentile(finite, 95)),
        "rmse": float(np.sqrt(np.mean(finite**2))),
    }


def pair_abs_errors_us(row: dict[str, Any]) -> list[float]:
    return [
        abs(float(row["tdoa_err_h1_us"])),
        abs(float(row["tdoa_err_h2_us"])),
        abs(float(row["tdoa_err_h3_us"])),
    ]


def _has_flag(row: dict[str, Any], name: str) -> bool:
    return name in str(row.get("flags", "")).split(";")


def _group_key(row: dict[str, Any]) -> tuple[bool, float, float]:
    snr = 0.0 if is_noise_free(row) else float(row["snr_db"])
    return (is_noise_free(row), snr, float(row["carrier_frequency_hz"]))


def summarize_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per noise condition and carrier, in first-seen order."""
    order: list[tuple[bool, float, float]] = []
    grouped: dict[tuple[bool, float, float], list[dict[str, Any]]] = {}
    for row in rows:
        key = _group_key(row)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(row)

    summary: list[dict[str, Any]] = []
    for noise_free, snr, carrier in order:
        selected = grouped[(noise_free, snr, carrier)]
        position: list[float] = []
        angular: list[float] = []
        tdoa: list[float] = []
        n_success = 0
        for row in selected:
            for error in pair_abs_errors_us(row):
                if np.isfinite(error):
                    tdoa.append(error)
            if is_success(row):
                n_success += 1
                position.append(float(row["localization_error_m"]))
                angular.append(float(row["angular_error_deg"]))
        pos = _stats(position)
        ang = _stats(angular)
        td = _stats(tdoa)
        n_trials = len(selected)
        summary.append(
            {
                "snr_db": float("nan") if noise_free else float(snr),
                "noise_free": noise_free,
                "carrier_frequency_hz": float(carrier),
                "n_trials": n_trials,
                "n_successful": n_success,
                "mean_localization_error_m": pos["mean"],
                "median_localization_error_m": pos["median"],
                "p95_localization_error_m": pos["p95"],
                "rmse_localization_error_m": pos["rmse"],
                "mean_abs_tdoa_error_us": td["mean"],
                "median_abs_tdoa_error_us": td["median"],
                "mean_angular_error_deg": ang["mean"],
                "median_angular_error_deg": ang["median"],
                "localization_success_rate": (n_success / n_trials) if n_trials else math.nan,
                "n_flagged": sum(1 for row in selected if str(row.get("flags", "")).strip() != ""),
                "n_huge_localization_error": sum(
                    1 for row in selected if _has_flag(row, "huge_localization_error")
                ),
                "n_boundary_peaks": sum(
                    1 for row in selected if _has_flag(row, "correlation_peak_at_boundary")
                ),
                "n_tdoa_outside_limit": sum(
                    1 for row in selected if _has_flag(row, "tdoa_outside_physical_limit")
                ),
            }
        )
    return summary
