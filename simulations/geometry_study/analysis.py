"""Summaries and checks for the geometry-study result tables."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from src.geometry import HydrophoneArray, max_pairwise_tdoa_s

EXPERIMENT_FIELDS = [
    "geometry",
    "geometry_name",
    "geometry_class",
    "source_id",
    "source_x_m",
    "source_y_m",
    "source_z_m",
    "source_range_m",
    "snr_db",
    "noise_seed",
    "true_tdoa_h0_us",
    "true_tdoa_h1_us",
    "true_tdoa_h2_us",
    "true_tdoa_h3_us",
    "est_tdoa_h0_us",
    "est_tdoa_h1_us",
    "est_tdoa_h2_us",
    "est_tdoa_h3_us",
    "tdoa_err_h1_us",
    "tdoa_err_h2_us",
    "tdoa_err_h3_us",
    "true_azimuth_deg",
    "true_elevation_deg",
    "distance_h0_m",
    "distance_h1_m",
    "distance_h2_m",
    "distance_h3_m",
    "est_x_m",
    "est_y_m",
    "est_z_m",
    "position_error_m",
    "est_azimuth_deg",
    "est_elevation_deg",
    "angular_error_deg",
    "solver_success",
    "solver_residual_us",
    "failure_reason",
    "solver_geometry_class",
]

SUMMARY_FIELDS = [
    "geometry",
    "geometry_name",
    "geometry_class",
    "snr_db",
    "n_trials",
    "tdoa_mean_abs_error_us",
    "tdoa_median_abs_error_us",
    "tdoa_p95_abs_error_us",
    "n_nonfinite_tdoa_pairs",
    "mean_angular_error_deg",
    "median_angular_error_deg",
    "angular_error_p95_deg",
    "mean_position_error_m",
    "median_position_error_m",
    "position_error_p95_m",
    "n_successful_localizations",
    "localization_success_rate",
    "failure_count",
]

STRING_FIELDS = {
    "geometry",
    "geometry_name",
    "geometry_class",
    "failure_reason",
    "solver_geometry_class",
    "solver_success",
}


def is_success(row: dict[str, Any]) -> bool:
    value = row["solver_success"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _finite(values: list[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def _mean_median_p95(values: list[float] | np.ndarray) -> tuple[float, float, float]:
    finite = _finite(values)
    if finite.size == 0:
        return math.nan, math.nan, math.nan
    return (
        float(np.mean(finite)),
        float(np.median(finite)),
        float(np.percentile(finite, 95)),
    )


def tdoa_abs_errors_us(row: dict[str, Any]) -> list[float]:
    """Absolute TDOA errors for the three non-reference pairs, in microseconds."""
    return [
        abs(float(row["tdoa_err_h1_us"])),
        abs(float(row["tdoa_err_h2_us"])),
        abs(float(row["tdoa_err_h3_us"])),
    ]


def summarize_results(
    rows: list[dict[str, Any]],
    arrays: tuple[HydrophoneArray, ...] | list[HydrophoneArray],
    snr_levels_db: list[float],
) -> list[dict[str, Any]]:
    """One summary row per geometry and SNR.

    TDOA statistics use every finite non-reference pair. Non-finite TDOA
    estimates are counted in ``n_nonfinite_tdoa_pairs`` and are not replaced
    with zero. Angular and position statistics use successful localizations
    only. If a geometry has no successful solve, those entries are NaN and
    ``failure_count`` equals ``n_trials``.
    """
    summary: list[dict[str, Any]] = []
    for array in arrays:
        for snr in snr_levels_db:
            selected = [
                row
                for row in rows
                if row["geometry"] == array.key and float(row["snr_db"]) == float(snr)
            ]
            pair_errors: list[float] = []
            n_nonfinite = 0
            angular: list[float] = []
            position: list[float] = []
            n_success = 0
            for row in selected:
                for error in tdoa_abs_errors_us(row):
                    if np.isfinite(error):
                        pair_errors.append(error)
                    else:
                        n_nonfinite += 1
                if is_success(row):
                    n_success += 1
                    angular.append(float(row["angular_error_deg"]))
                    position.append(float(row["position_error_m"]))
            tdoa_mean, tdoa_median, tdoa_p95 = _mean_median_p95(pair_errors)
            ang_mean, ang_median, ang_p95 = _mean_median_p95(angular)
            pos_mean, pos_median, pos_p95 = _mean_median_p95(position)
            n_trials = len(selected)
            summary.append(
                {
                    "geometry": array.key,
                    "geometry_name": array.name,
                    "geometry_class": array.expected_class,
                    "snr_db": float(snr),
                    "n_trials": n_trials,
                    "tdoa_mean_abs_error_us": tdoa_mean,
                    "tdoa_median_abs_error_us": tdoa_median,
                    "tdoa_p95_abs_error_us": tdoa_p95,
                    "n_nonfinite_tdoa_pairs": n_nonfinite,
                    "mean_angular_error_deg": ang_mean,
                    "median_angular_error_deg": ang_median,
                    "angular_error_p95_deg": ang_p95,
                    "mean_position_error_m": pos_mean,
                    "median_position_error_m": pos_median,
                    "position_error_p95_m": pos_p95,
                    "n_successful_localizations": n_success,
                    "localization_success_rate": (n_success / n_trials) if n_trials else math.nan,
                    "failure_count": n_trials - n_success,
                }
            )
    return summary


def verify_experiment(
    rows: list[dict[str, Any]],
    arrays: tuple[HydrophoneArray, ...] | list[HydrophoneArray],
    snr_levels_db: list[float],
    n_sources: int,
    sound_speed_mps: float,
) -> list[str]:
    """Return a list of problems. An empty list means the table passed."""
    problems: list[str] = []
    expected = n_sources * len(snr_levels_db) * len(arrays)
    if len(rows) != expected:
        problems.append(f"row count {len(rows)} != expected {expected}")

    present = {row["geometry"] for row in rows}
    for array in arrays:
        if array.key not in present:
            problems.append(f"missing geometry {array.key}")

    by_key = {array.key: array for array in arrays}
    grouped: dict[tuple[int, float], list[dict[str, Any]]] = {}
    for row in rows:
        if not np.isfinite(float(row["true_tdoa_h0_us"])) or float(row["true_tdoa_h0_us"]) != 0.0:
            problems.append(f"H0 true TDOA is not 0 for source {row['source_id']}")
            break
        for key in ("tdoa_err_h1_us", "tdoa_err_h2_us", "tdoa_err_h3_us", "true_tdoa_h1_us"):
            value = float(row[key])
            if np.isinf(value):
                problems.append(f"infinite value in {key}")
                break
        success = is_success(row)
        if success:
            for key in ("est_x_m", "est_y_m", "est_z_m", "position_error_m", "angular_error_deg"):
                if not np.isfinite(float(row[key])):
                    problems.append(f"successful solve has non-finite {key}")
                    break
        else:
            for key in ("est_x_m", "est_y_m", "est_z_m", "position_error_m", "angular_error_deg"):
                if np.isfinite(float(row[key])):
                    problems.append(f"failed solve stored a finite {key}")
                    break
            if str(row["failure_reason"]).strip() == "":
                problems.append("failed solve has an empty failure_reason")
        array = by_key[str(row["geometry"])]
        physical_max_us = max_pairwise_tdoa_s(array.coordinates_m, sound_speed_mps) * 1e6
        for key in ("true_tdoa_h1_us", "true_tdoa_h2_us", "true_tdoa_h3_us"):
            if abs(float(row[key])) > physical_max_us + 1e-6:
                problems.append(f"{array.key} true TDOA exceeds d_max/c")
                break
        grouped.setdefault((int(row["source_id"]), float(row["snr_db"])), []).append(row)
        if len(problems) > 12:
            return problems

    for (source_id, snr), group in grouped.items():
        if len(group) != len(arrays):
            problems.append(f"source {source_id} at {snr} dB has {len(group)} geometries")
            break
        seeds = {int(row["noise_seed"]) for row in group}
        if len(seeds) != 1:
            problems.append(f"source {source_id} at {snr} dB used more than one noise seed")
            break
        xyz = {(float(row["source_x_m"]), float(row["source_y_m"]), float(row["source_z_m"])) for row in group}
        if len(xyz) != 1:
            problems.append(f"source {source_id} coordinates differ across geometries")
            break

    return problems
