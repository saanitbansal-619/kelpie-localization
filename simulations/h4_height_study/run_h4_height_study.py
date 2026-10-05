"""H4 height sweep for the fixed 3+1 triangle.

From the project root:

    python simulations/h4_height_study/run_h4_height_study.py

Writes only ``results_h4_height_study/``. Existing result folders are not
opened for writing. The tetrahedral array is not part of this study.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_study.pipeline import prepare_reference_waveform
from simulations.h4_height_study.directions import (
    CARDINALS,
    DIRECTION_ORDER,
    MIN_SOURCES,
    classify_direction,
)
from simulations.h4_height_study.figures import (
    insufficient_directions,
    plot_all_h4_positions,
    plot_direction_vs_height,
    plot_geometry,
    plot_heatmap,
    plot_metric_vs_height,
    present_directions,
)
from simulations.h4_height_study.geometry import (
    AXIS_CONVENTION,
    HEIGHTS_M,
    array_for_height,
    coordinate_records,
    h4_coordinate_m,
    height_name,
    original_h4_m,
    plane_z_m,
    triangle_centroid_m,
    triangle_coordinates_m,
)
from simulations.h4_height_study.metrics import (
    best_direction_rows,
    directional_table,
    height_summaries,
    pooled_height_record,
    positive_negative_rows,
    ranking_rows,
    source_direction_counts,
)
from simulations.h4_height_study.paths import OUTPUT_ROOT, PROTECTED_DIRS, output_path
from simulations.h4_height_study.tables import write_table
from simulations.noise_study.pipeline import execute_trial as run_noise_trial
from simulations.noise_study.pipeline import noise_std_for_condition, trial_noise_seed
from simulations.noise_study.run_noise_experiment import load_config as load_noise_config
from simulations.waveform_study.pipeline import execute_trial as run_waveform_trial
from simulations.waveform_study.run_waveform_experiment import load_config as load_waveform_config
from simulations.waveform_study.run_waveform_experiment import load_sources
from src.geometry import SOUND_SPEED_MPS

SUMMARY_FIELDS = [
    "h4_name",
    "h4_height_m",
    "h4_z_m",
    "snr_label",
    "noise_free",
    "snr_db",
    "n_trials",
    "n_successful",
    "mean_localization_error_m",
    "median_localization_error_m",
    "rmse_localization_error_m",
    "std_localization_error_m",
    "p95_localization_error_m",
    "max_localization_error_m",
    "mean_angular_error_deg",
    "median_angular_error_deg",
    "success_rate",
    "catastrophic_failure_rate",
]
WAVE_SUMMARY_FIELDS = SUMMARY_FIELDS + ["mean_abs_tdoa_error_us", "median_abs_tdoa_error_us"]
DIRECTION_FIELDS = [
    "study",
    "h4_name",
    "h4_height_m",
    "direction",
    "n_sources",
    "n_trials",
    "n_successful",
    "success_rate",
    "mean_localization_error_m",
    "median_localization_error_m",
    "p95_localization_error_m",
    "rmse_localization_error_m",
    "mean_angular_error_deg",
    "median_angular_error_deg",
    "mean_abs_tdoa_error_us",
    "median_abs_tdoa_error_us",
    "flag",
]
RANK_FIELDS = [
    "study",
    "scope",
    "h4_name",
    "h4_height_m",
    "median_localization_error_m",
    "p95_localization_error_m",
    "median_angular_error_deg",
    "success_rate",
    "catastrophic_failure_rate",
    "directional_std_m",
    "median_abs_tdoa_error_us",
    "rank_median",
    "rank_p95",
    "rank_angular",
    "rank_success",
    "rank_catastrophic",
    "rank_consistency",
    "rank_tdoa",
    "rank_sum",
    "rank_overall",
    "note",
]
BEST_FIELDS = [
    "study",
    "direction",
    "n_sources",
    "n_trials",
    "flag",
    "best_h4_name",
    "best_h4_height_m",
    "median_localization_error_m",
    "success_rate",
    "median_angular_error_deg",
    "note",
]
PAIR_FIELDS = [
    "study",
    "magnitude_m",
    "neg_name",
    "pos_name",
    "neg_median_m",
    "pos_median_m",
    "median_difference_pos_minus_neg_m",
    "neg_success_rate",
    "pos_success_rate",
    "neg_p95_m",
    "pos_p95_m",
    "neg_catastrophic_failure_rate",
    "pos_catastrophic_failure_rate",
    "neg_median_angular_deg",
    "pos_median_angular_deg",
    "neg_median_tdoa_us",
    "pos_median_tdoa_us",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="3+1 H4 height study")
    parser.add_argument("--trials", type=int, default=None, help="Override the shared trial count")
    args = parser.parse_args()
    if args.trials is not None and args.trials < 1:
        raise RuntimeError("--trials must be at least 1")

    before = _snapshot_protected()
    started = time.perf_counter()
    noise_config = load_noise_config()
    wave_config = load_waveform_config()
    n_trials = int(args.trials) if args.trials is not None else int(noise_config["n_trials"])
    if int(wave_config["n_trials"]) != int(noise_config["n_trials"]) and args.trials is None:
        raise RuntimeError("Change #1 and Change #2 trial counts differ; refusing to guess")
    if int(noise_config["random_seed"]) != int(wave_config["random_seed"]):
        raise RuntimeError("Change #1 and Change #2 random seeds differ")

    triangle = triangle_coordinates_m()
    original = original_h4_m()
    center = triangle_centroid_m()
    _print_geometry(triangle, original, center)

    noise_sources = _noise_sources(noise_config, n_trials)
    wave_ids, wave_sources = load_sources(n_trials)
    _assign_directions(noise_sources, center)
    _assign_directions(wave_sources, center)

    print()
    print(f"Change #1 sources : {noise_sources.shape[0]}")
    print(f"Change #2 sources : {wave_sources.shape[0]}")
    print(f"H4 heights        : {len(HEIGHTS_M)}")
    print("Tetrahedral results are not read or written.", flush=True)

    noise_rows = _run_change1(noise_config, noise_sources, center, n_trials)
    wave_rows = _run_change2(wave_config, wave_ids, wave_sources, center, n_trials)
    _write_products(noise_rows, wave_rows, triangle, noise_config, wave_config, n_trials, time.perf_counter() - started)
    _assert_unchanged(before)
    print()
    print(f"saved under : {OUTPUT_ROOT.relative_to(PROJECT_ROOT)}")
    print("Previous result files were not modified.")


def _print_geometry(triangle: np.ndarray, original: np.ndarray, center: np.ndarray) -> None:
    labels = ("H1", "H2", "H3")
    print("Fixed 3+1 triangle, catalog coordinates")
    for label, xyz in zip(labels, triangle):
        print(f"  {label} = ({xyz[0]:.12f}, {xyz[1]:.12f}, {xyz[2]:.12f})")
    print(f"  H4 original = ({original[0]:.12f}, {original[1]:.12f}, {original[2]:.12f})")
    print(f"  triangle centroid = ({center[0]:.12f}, {center[1]:.12f}, {center[2]:.12f})")
    print(f"  plane z = {plane_z_m():.12f} m")
    print("Coordinate convention, source direction relative to that centroid:")
    for axis, name in AXIS_CONVENTION.items():
        print(f"  {axis} = {name}")


def _noise_sources(config: dict[str, Any], n_trials: int) -> np.ndarray:
    from src.geometry import generate_source_positions

    return generate_source_positions(
        n_trials,
        seed=int(config["random_seed"]),
        range_min_m=float(config["range_min_m"]),
        range_max_m=float(config["range_max_m"]),
        elevation_min_deg=float(config["elevation_min_deg"]),
        elevation_max_deg=float(config["elevation_max_deg"]),
    )


def _assign_directions(sources: np.ndarray, center: np.ndarray) -> list[str]:
    return [classify_direction(source, center) for source in sources]


def _run_change1(
    config: dict[str, Any],
    sources: np.ndarray,
    center: np.ndarray,
    n_trials: int,
) -> list[dict[str, Any]]:
    directions = _assign_directions(sources, center)
    fs = float(config["sample_rate_hz"])
    _, reference = prepare_reference_waveform(
        fs,
        float(config["capture_duration_s"]),
        float(config["event_time_s"]),
    )
    conditions = _conditions(bool(config["include_noise_free"]), [float(value) for value in config["snr_levels_db"]])
    rows: list[dict[str, Any]] = []
    print()
    print(f"Change #1: {len(HEIGHTS_M)} heights x {n_trials} trials x {len(conditions)} SNR", flush=True)
    for height in HEIGHTS_M:
        array = array_for_height(height)
        h4 = h4_coordinate_m(height)
        height_rows: list[dict[str, Any]] = []
        for noise_free_flag, snr in conditions:
            noise_std = noise_std_for_condition(snr, fs, noise_free=noise_free_flag)
            for index in range(n_trials):
                row = run_noise_trial(
                    array,
                    sources[index],
                    index,
                    index + 1,
                    snr,
                    noise_free_flag,
                    reference,
                    fs,
                    float(config["sound_speed_mps"]),
                    noise_std,
                    config,
                    trial_noise_seed(int(config["random_seed"]), index),
                )
                height_rows.append(_annotate(row, height, h4, directions[index]))
        rows.extend(height_rows)
        _write_raw("change_1_noise", height_name(height), height_rows)
        print(f"  {height_name(height):<14} done", flush=True)
    return rows


def _run_change2(
    config: dict[str, Any],
    source_ids: np.ndarray,
    sources: np.ndarray,
    center: np.ndarray,
    n_trials: int,
) -> list[dict[str, Any]]:
    directions = _assign_directions(sources, center)
    conditions = _conditions(bool(config["include_noise_free"]), [float(value) for value in config["snr_levels_db"]])
    carrier = float(config["carrier_frequency_hz"])
    rows: list[dict[str, Any]] = []
    print()
    print(
        f"Change #2: {len(HEIGHTS_M)} heights x {n_trials} trials x {len(conditions)} SNR "
        f"at {carrier / 1000.0:.0f} kHz",
        flush=True,
    )
    for height in HEIGHTS_M:
        array = array_for_height(height)
        h4 = h4_coordinate_m(height)
        height_rows: list[dict[str, Any]] = []
        for noise_free_flag, snr in conditions:
            for index in range(n_trials):
                row = run_waveform_trial(
                    array,
                    sources[index],
                    index + 1,
                    int(source_ids[index]),
                    snr,
                    noise_free_flag,
                    carrier,
                    float(config["sample_rate_hz"]),
                    float(config["sound_speed_mps"]),
                    config,
                    trial_noise_seed(int(config["random_seed"]), index),
                )
                height_rows.append(_annotate(row, height, h4, directions[index]))
        rows.extend(height_rows)
        _write_raw("change_2_waveform", height_name(height), height_rows)
        print(f"  {height_name(height):<14} done", flush=True)
    return rows


def _conditions(include_noise_free: bool, levels: list[float]) -> list[tuple[bool, float]]:
    conditions: list[tuple[bool, float]] = []
    if include_noise_free:
        conditions.append((True, float("nan")))
    conditions.extend((False, float(level)) for level in levels)
    return conditions


def _annotate(row: dict[str, Any], height: float, h4: np.ndarray, direction: str) -> dict[str, Any]:
    annotated = dict(row)
    annotated["h4_name"] = height_name(height)
    annotated["h4_height_m"] = float(height)
    annotated["h4_z_m"] = float(h4[2])
    annotated["direction"] = direction
    return annotated


def _write_raw(change: str, name: str, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys())
    preferred = ["h4_name", "h4_height_m", "h4_z_m", "direction"]
    fieldnames = preferred + [key for key in fieldnames if key not in preferred and not key.startswith("_")]
    write_table(output_path(change, "raw", f"{name}.csv"), fieldnames, rows)


def _write_products(
    noise_rows: list[dict[str, Any]],
    wave_rows: list[dict[str, Any]],
    triangle: np.ndarray,
    noise_config: dict[str, Any],
    wave_config: dict[str, Any],
    n_trials: int,
    elapsed_s: float,
) -> None:
    noise_summary = height_summaries(noise_rows)
    wave_summary = height_summaries(wave_rows)
    write_table(output_path("change_1_noise", "summaries", "h4_height_change1_summary.csv"), SUMMARY_FIELDS, noise_summary)
    write_table(output_path("change_2_waveform", "summaries", "h4_height_change2_summary.csv"), WAVE_SUMMARY_FIELDS, wave_summary)
    write_table(output_path("final_summary", "tables", "h4_height_change1_summary.csv"), SUMMARY_FIELDS, noise_summary)
    write_table(output_path("final_summary", "tables", "h4_height_change2_summary.csv"), WAVE_SUMMARY_FIELDS, wave_summary)

    noise_directions = directional_table(noise_rows, "change_1")
    wave_directions = directional_table(wave_rows, "change_2")
    directional = noise_directions + wave_directions
    write_table(output_path("change_1_noise", "directional", "directional_performance_by_height.csv"), DIRECTION_FIELDS, noise_directions)
    write_table(output_path("change_2_waveform", "directional", "directional_performance_by_height.csv"), DIRECTION_FIELDS, wave_directions)
    write_table(output_path("directional_comparison", "tables", "directional_performance_by_height.csv"), DIRECTION_FIELDS, directional)
    write_table(output_path("final_summary", "tables", "directional_performance_by_height.csv"), DIRECTION_FIELDS, directional)

    noise_counts = source_direction_counts(noise_rows)
    wave_counts = source_direction_counts(wave_rows)
    for row in noise_counts:
        row["study"] = "change_1"
    for row in wave_counts:
        row["study"] = "change_2"
    count_fields = ["study", "direction", "n_sources", "flag"]
    write_table(output_path("directional_comparison", "tables", "source_direction_counts.csv"), count_fields, noise_counts + wave_counts)

    noise_pooled = _pooled(noise_rows, noise_directions, None)
    wave_pooled = _pooled(wave_rows, wave_directions, None)
    rankings = []
    rankings.extend(_scope_rankings(noise_rows, noise_directions, noise_counts, "change_1", False))
    rankings.extend(_scope_rankings(wave_rows, wave_directions, wave_counts, "change_2", True))
    write_table(output_path("final_summary", "tables", "overall_height_ranking.csv"), RANK_FIELDS, rankings)
    write_table(output_path("height_comparison", "tables", "overall_height_ranking.csv"), RANK_FIELDS, rankings)

    best = best_direction_rows(noise_directions, "change_1") + best_direction_rows(wave_directions, "change_2")
    write_table(output_path("final_summary", "tables", "best_height_by_direction.csv"), BEST_FIELDS, best)
    write_table(output_path("directional_comparison", "tables", "best_height_by_direction.csv"), BEST_FIELDS, best)

    pairs = positive_negative_rows(noise_pooled, "change_1") + positive_negative_rows(wave_pooled, "change_2")
    write_table(output_path("final_summary", "tables", "positive_vs_negative_height.csv"), PAIR_FIELDS, pairs)
    write_table(output_path("height_comparison", "tables", "positive_vs_negative_height.csv"), PAIR_FIELDS, pairs)

    _write_height_plots(noise_pooled, "Change #1", output_path("change_1_noise", "plots"), include_tdoa=False)
    _write_height_plots(wave_pooled, "Change #2", output_path("change_2_waveform", "plots"), include_tdoa=True)
    _write_height_plots(noise_pooled, "Change #1", output_path("height_comparison", "plots"), include_tdoa=False)
    _write_height_plots(wave_pooled, "Change #2", output_path("height_comparison", "plots"), include_tdoa=True)
    _write_heatmaps(noise_summary, noise_directions, "change1", "Change #1", include_tdoa=False)
    _write_heatmaps(wave_summary, wave_directions, "change2", "Change #2", include_tdoa=True)
    _write_direction_plots(noise_directions, "change1", "Change #1")
    _write_direction_plots(wave_directions, "change2", "Change #2")
    _write_geometry_plots(triangle)
    _write_manifest(noise_config, wave_config, n_trials, elapsed_s, noise_counts, wave_counts, triangle)
    _print_findings(rankings, best, pairs, noise_counts, wave_counts)


def _pooled(
    rows: list[dict[str, Any]],
    directional: list[dict[str, Any]],
    directions: tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    names = list(dict.fromkeys(str(row["h4_name"]) for row in rows))
    pooled = []
    for name in names:
        selected = [row for row in rows if str(row["h4_name"]) == name]
        record = pooled_height_record(selected, directional, directions)
        pooled.append(record)
    return pooled


def _scope_rankings(
    rows: list[dict[str, Any]],
    directional: list[dict[str, Any]],
    counts: list[dict[str, Any]],
    study: str,
    include_tdoa: bool,
) -> list[dict[str, Any]]:
    count_map = {str(row["direction"]): int(row["n_sources"]) for row in counts}
    horizontal = tuple(name for name in ("FRONT", "BACK", "LEFT", "RIGHT") if count_map.get(name, 0) >= MIN_SOURCES)
    vertical, vertical_note = _vertical_directions(count_map)
    scopes: list[tuple[str, list[dict[str, Any]], str]] = [
        ("all", rows, ""),
        ("low_noise", _filter_noise(rows, low=True), ""),
        ("high_noise", _filter_noise(rows, low=False), ""),
        ("horizontal", [row for row in rows if str(row["direction"]) in horizontal], ""),
        ("vertical", [row for row in rows if str(row["direction"]) in vertical], vertical_note),
    ]
    ranked: list[dict[str, Any]] = []
    for scope, selected, note in scopes:
        pooled = _pooled(selected, directional, horizontal if scope == "horizontal" else vertical if scope == "vertical" else None)
        for row in ranking_rows(pooled, study=study, scope=scope, include_tdoa=include_tdoa):
            row["note"] = note
            ranked.append(row)
    return ranked


def _vertical_directions(count_map: dict[str, int]) -> tuple[tuple[str, ...], str]:
    pure = tuple(name for name in ("ABOVE", "BELOW") if count_map.get(name, 0) >= MIN_SOURCES)
    if pure:
        return pure, "cardinal ABOVE and/or BELOW with at least 5 sources"
    broader = tuple(
        name
        for name in DIRECTION_ORDER
        if count_map.get(name, 0) >= MIN_SOURCES and ("ABOVE" in name or "BELOW" in name)
    )
    return broader, "pure ABOVE/BELOW had fewer than 5 sources; vertical uses every sufficient bin with a vertical component"


def _filter_noise(rows: list[dict[str, Any]], *, low: bool) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        if low:
            if noise_free_row(row) or (np.isfinite(float(row["snr_db"])) and float(row["snr_db"]) >= 25.0):
                selected.append(row)
        elif (not noise_free_row(row)) and np.isfinite(float(row["snr_db"])) and float(row["snr_db"]) <= 5.0:
            selected.append(row)
    return selected


def noise_free_row(row: dict[str, Any]) -> bool:
    value = row["noise_free"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _write_height_plots(rows: list[dict[str, Any]], title: str, directory: Path, *, include_tdoa: bool) -> None:
    stem = "change1" if title.endswith("1") else "change2"
    specs = [
        ("median_localization_error_m", "Median localization error (m)", "median localization error versus H4 height", False),
        ("mean_localization_error_m", "Mean localization error (m)", "mean localization error versus H4 height", False),
        ("p95_localization_error_m", "95th percentile localization error (m)", "95th percentile error versus H4 height", False),
        ("median_angular_error_deg", "Median angular error (deg)", "median angular error versus H4 height", False),
        ("success_rate", "Successful localizations (%)", "success rate versus H4 height", True),
        ("catastrophic_failure_rate", "Catastrophic trials (%)", "catastrophic failure rate versus H4 height", True),
    ]
    if include_tdoa:
        specs.append(
            ("median_abs_tdoa_error_us", "Median absolute TDOA error (us)", "median TDOA error versus H4 height", False)
        )
    for key, ylabel, caption, percent in specs:
        plot_metric_vs_height(
            rows,
            key,
            ylabel,
            f"{title} — {caption}\nSIMULATION — all SNR conditions; localization stats use successful solves",
            directory / f"{stem}_{key}.png",
            percent=percent,
        )


def _write_heatmaps(
    summary: list[dict[str, Any]],
    directional: list[dict[str, Any]],
    stem: str,
    title: str,
    *,
    include_tdoa: bool,
) -> None:
    summary_rows = []
    for row in summary:
        copied = dict(row)
        copied["snr_label"] = "noise-free" if str(row["noise_free"]).lower() == "true" else f"{float(row['snr_db']):.0f} dB"
        summary_rows.append(copied)
    snr_labels = _snr_labels(summary_rows)
    plot_heatmap(
        summary_rows,
        snr_labels,
        "snr_label",
        "median_localization_error_m",
        f"{title} — median localization error\nSIMULATION — SNR versus H4 height",
        "Median localization error (m)",
        output_path("height_comparison", "plots", f"{stem}_snr_height_median_error.png"),
    )
    plot_heatmap(
        summary_rows,
        snr_labels,
        "snr_label",
        "success_rate",
        f"{title} — success rate\nSIMULATION — SNR versus H4 height",
        "Success rate (%)",
        output_path("height_comparison", "plots", f"{stem}_snr_height_success.png"),
        percent=True,
    )
    if include_tdoa:
        plot_heatmap(
            summary_rows,
            snr_labels,
            "snr_label",
            "median_abs_tdoa_error_us",
            f"{title} — median absolute TDOA error\nSIMULATION — SNR versus H4 height",
            "Median |TDOA error| (us)",
            output_path("height_comparison", "plots", f"{stem}_snr_height_tdoa.png"),
        )
    directions = present_directions(directional)
    insufficient = insufficient_directions(directional)
    common = dict(
        rows=directional,
        row_labels=directions,
        row_key="direction",
        insufficient_rows=insufficient,
    )
    plot_heatmap(
        **common,
        value_key="median_localization_error_m",
        title=f"{title} — median localization error by direction\nSIMULATION — white x marks bins with fewer than {MIN_SOURCES} sources",
        colorbar="Median localization error (m)",
        path=output_path("directional_comparison", "plots", f"{stem}_direction_height_median_error.png"),
    )
    plot_heatmap(
        **common,
        value_key="success_rate",
        title=f"{title} — success rate by direction\nSIMULATION — white x marks bins with fewer than {MIN_SOURCES} sources",
        colorbar="Success rate (%)",
        path=output_path("directional_comparison", "plots", f"{stem}_direction_height_success.png"),
        percent=True,
    )
    plot_heatmap(
        **common,
        value_key="median_angular_error_deg",
        title=f"{title} — median angular error by direction\nSIMULATION — white x marks bins with fewer than {MIN_SOURCES} sources",
        colorbar="Median angular error (deg)",
        path=output_path("directional_comparison", "plots", f"{stem}_direction_height_angular.png"),
    )
    if include_tdoa:
        plot_heatmap(
            **common,
            value_key="median_abs_tdoa_error_us",
            title=f"{title} — median absolute TDOA error by direction\nSIMULATION — white x marks bins with fewer than {MIN_SOURCES} sources",
            colorbar="Median |TDOA error| (us)",
            path=output_path("directional_comparison", "plots", f"{stem}_direction_height_tdoa.png"),
        )


def _snr_labels(rows: list[dict[str, Any]]) -> list[str]:
    labels = []
    if any(str(row["noise_free"]).lower() == "true" for row in rows):
        labels.append("noise-free")
    levels = sorted(
        {float(row["snr_db"]) for row in rows if str(row["noise_free"]).lower() != "true"},
        reverse=True,
    )
    labels.extend(f"{level:.0f} dB" for level in levels)
    return labels


def _write_direction_plots(directional: list[dict[str, Any]], stem: str, title: str) -> None:
    for direction in present_directions(directional):
        if directional and directional[0]["flag"] == "" or any(
            row["direction"] == direction and row["flag"] == "" for row in directional
        ):
            plot_direction_vs_height(
                directional,
                direction,
                output_path("directional_comparison", "plots", f"{stem}_{direction}.png"),
                title,
            )


def _write_geometry_plots(triangle: np.ndarray) -> None:
    positions = []
    for height in HEIGHTS_M:
        array = array_for_height(height)
        plot_geometry(
            array.coordinates_m,
            f"SIMULATION — {height_name(height)}\nH4 is {height * 100:.0f} cm from the H1/H2/H3 plane",
            output_path("final_summary", "plots", "geometry", f"{height_name(height)}.png"),
        )
        positions.append((height, h4_coordinate_m(height)))
    plot_all_h4_positions(
        triangle,
        positions,
        output_path("final_summary", "plots", "geometry", "all_h4_positions.png"),
    )


def _write_manifest(
    noise_config: dict[str, Any],
    wave_config: dict[str, Any],
    n_trials: int,
    elapsed_s: float,
    noise_counts: list[dict[str, Any]],
    wave_counts: list[dict[str, Any]],
    triangle: np.ndarray,
) -> None:
    heights = []
    for height in HEIGHTS_M:
        h4 = h4_coordinate_m(height)
        array = array_for_height(height)
        heights.append(
            {
                "h4_name": height_name(height),
                "h4_height_m": float(height),
                "h4_coordinate_m": [float(value) for value in h4],
                "maximum_baseline_m": float(array.max_pairwise_distance_m()),
                "hydrophones": coordinate_records(array.coordinates_m),
            }
        )
    manifest = {
        "label": "SIMULATION",
        "study": "h4_height_study",
        "geometry": "three_plus_one",
        "comparison_with_tetrahedral": False,
        "coordinate_convention": AXIS_CONVENTION,
        "classification_center": "centroid of fixed H1/H2/H3",
        "classification_center_m": [float(value) for value in triangle_centroid_m()],
        "classification_rule": (
            "Include an axis when its absolute component is at least 0.5 times "
            "the largest component. Label order is X, then Y, then Z. "
            f"Bins with fewer than {MIN_SOURCES} unique sources are flagged "
            "INSUFFICIENT_SAMPLE_COUNT and are not removed."
        ),
        "catastrophic_definition": (
            "A trial is catastrophic when the solver rejects it or the accepted "
            "localization error exceeds 20 m. Success rate still counts a huge "
            "accepted range as a success."
        ),
        "h1_h2_h3": coordinate_records(np.vstack([triangle, original_h4_m()]))[:3],
        "h4_original": coordinate_records(np.vstack([triangle, original_h4_m()]))[3],
        "plane_z_m": plane_z_m(),
        "heights": heights,
        "number_of_trials": int(n_trials),
        "random_seed": int(noise_config["random_seed"]),
        "speed_of_sound_mps": float(SOUND_SPEED_MPS),
        "change_1_snr": (["noise-free"] if noise_config["include_noise_free"] else [])
        + [f"{float(level):.0f} dB" for level in noise_config["snr_levels_db"]],
        "change_2_snr": (["noise-free"] if wave_config["include_noise_free"] else [])
        + [f"{float(level):.0f} dB" for level in wave_config["snr_levels_db"]],
        "carrier_frequency_hz": float(wave_config["carrier_frequency_hz"]),
        "pulse_duration_s": float(wave_config["pulse_duration_s"]),
        "sampling_rate_hz": float(wave_config["sample_rate_hz"]),
        "TDOA_method": "GCC-PHAT, existing src.tdoa.estimate_tdoas, search limited to that array's baseline/c",
        "apply_attenuation": bool(wave_config["apply_attenuation"]),
        "source_position_dataset": {
            "change_1": "generate_source_positions with the Change #1 seed, range, and elevation",
            "change_2": "first N rows of simulations/geometry_study/results/source_positions.csv",
        },
        "change_1_direction_counts": noise_counts,
        "change_2_direction_counts": wave_counts,
        "ranking_rule": (
            "Within a scope, heights are ranked separately on median error, "
            "95th percentile, median angular error, success rate, catastrophic rate, "
            "and the standard deviation of sufficient per-direction medians. "
            "Change #2 also ranks median absolute TDOA error. rank_sum is the "
            "sum of those ranks. rank_overall 1 has the lowest sum."
        ),
        "elapsed_s": round(float(elapsed_s), 3),
        "protected_result_directories": [str(path.relative_to(PROJECT_ROOT)) for path in PROTECTED_DIRS],
    }
    path = output_path("run_manifest.json")
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    output_path("change_1_noise", "run_manifest.json").write_text(
        json.dumps({key: manifest[key] for key in manifest if key != "change_2_direction_counts"}, indent=2) + "\n",
        encoding="utf-8",
    )
    output_path("change_2_waveform", "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def _print_findings(
    rankings: list[dict[str, Any]],
    best: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    noise_counts: list[dict[str, Any]],
    wave_counts: list[dict[str, Any]],
) -> None:
    print()
    print("=" * 78)
    print("H4 HEIGHT STUDY")
    print("=" * 78)
    print("Direction counts, Change #1 sources")
    _print_counts(noise_counts)
    print("Direction counts, Change #2 sources")
    _print_counts(wave_counts)
    for study in ("change_1", "change_2"):
        print()
        print(study)
        for scope in ("all", "low_noise", "high_noise", "horizontal", "vertical"):
            winner = _winner(rankings, study, scope)
            if winner is None:
                continue
            print(
                f"  {scope:<12} {winner['h4_name']:<14} "
                f"median {float(winner['median_localization_error_m']):.3f} m  "
                f"p95 {float(winner['p95_localization_error_m']):.3f} m  "
                f"success {100 * float(winner['success_rate']):.1f}%  "
                f"catastrophic {100 * float(winner['catastrophic_failure_rate']):.1f}%"
            )
        consistent = _most_consistent(rankings, study)
        if consistent is not None:
            print(f"  {'consistent':<12} {consistent['h4_name']:<14} directional std {float(consistent['directional_std_m']):.3f} m")
    print()
    print("Best sufficient direction bins by median localization error")
    for direction in CARDINALS:
        _print_best(best, direction)
    print()
    print("Equal-magnitude median difference (positive minus negative), metres")
    for row in pairs:
        print(
            f"  {row['study']:<10} {float(row['magnitude_m']) * 100:4.0f} cm  "
            f"{float(row['median_difference_pos_minus_neg_m']):+.3f}"
        )


def _print_counts(rows: list[dict[str, Any]]) -> None:
    ordered = sorted(rows, key=lambda row: DIRECTION_ORDER.index(row["direction"]) if row["direction"] in DIRECTION_ORDER else 99)
    for row in ordered:
        flag = f"  {row['flag']}" if row["flag"] else ""
        print(f"  {row['direction']:<24} {int(row['n_sources']):3d}{flag}")


def _winner(rows: list[dict[str, Any]], study: str, scope: str) -> dict[str, Any] | None:
    matches = [row for row in rows if row["study"] == study and row["scope"] == scope and int(row["rank_overall"]) == 1]
    return matches[0] if matches else None


def _most_consistent(rows: list[dict[str, Any]], study: str) -> dict[str, Any] | None:
    matches = [
        row
        for row in rows
        if row["study"] == study and row["scope"] == "all" and np.isfinite(float(row["directional_std_m"]))
    ]
    if not matches:
        return None
    return min(matches, key=lambda row: float(row["directional_std_m"]))


def _print_best(rows: list[dict[str, Any]], direction: str) -> None:
    for study in ("change_1", "change_2"):
        match = [row for row in rows if row["study"] == study and row["direction"] == direction]
        if not match:
            print(f"  {direction:<8} {study:<10} no sources")
            continue
        row = match[0]
        if row["flag"]:
            print(f"  {direction:<8} {study:<10} {row['flag']} (n={int(row['n_sources'])})")
            continue
        print(
            f"  {direction:<8} {study:<10} {row['best_h4_name']:<14} "
            f"median {float(row['median_localization_error_m']):.3f} m  "
            f"success {100 * float(row['success_rate']):.0f}%"
            + (f"  {row['note']}" if row["note"] else "")
        )


def _snapshot_protected() -> dict[str, str]:
    found: dict[str, str] = {}
    for directory in PROTECTED_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                found[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _assert_unchanged(before: dict[str, str]) -> None:
    after = _snapshot_protected()
    if set(before) != set(after) or any(before[key] != after[key] for key in before):
        raise RuntimeError("a protected result file changed during the H4 height study")


if __name__ == "__main__":
    main()
