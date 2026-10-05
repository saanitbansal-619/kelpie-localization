"""Run the 3 by 3 H4-height and base-scale study on the Change #2 pipeline.

From the project root:

    python simulations/joint_geometry_study/run_joint_geometry_study.py

Writes ``results_joint_geometry_optimization/``. It does not modify ``results/``,
``results_h4_height_study/``, or the earlier noise and waveform result folders.

``--trials`` overrides the source count. The reported study uses the Change #2
count, 100.
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

from simulations.h4_height_study.directions import MIN_SOURCES, classify_direction
from simulations.h4_height_study.geometry import plane_z_m, triangle_centroid_m, triangle_coordinates_m
from simulations.joint_geometry_study.figures import (
    plot_accuracy_reliability,
    plot_design_heatmap,
    plot_geometries,
    plot_snr_heatmap,
)
from simulations.joint_geometry_study.geometry import assert_layouts_match_catalog, coordinate_rows, geometry_id, iter_geometries
from simulations.joint_geometry_study.paths import OUTPUT_ROOT, PROTECTED_DIRS, output_path
from simulations.joint_geometry_study.ranking import directional_summaries, pooled_summaries, rank_layouts, selected_geometry_ids, snr_summaries
from simulations.joint_geometry_study.report import render_readme
from simulations.joint_geometry_study.tables import write_table
from simulations.waveform_study.pipeline import execute_trial, trial_noise_seed
from simulations.waveform_study.run_waveform_experiment import load_config, load_sources
from src.geometry import SOUND_SPEED_MPS

RAW_PREFIX = [
    "geometry_id",
    "h4_height_m",
    "base_scale",
    "is_control",
    "triangle_side_m",
    "max_baseline_m",
    "direction",
]
SUMMARY_FIELDS = [
    "geometry_id",
    "h4_height_m",
    "base_scale",
    "is_control",
    "triangle_side_m",
    "max_baseline_m",
    "n_trials",
    "n_successful",
    "median_localization_error_m",
    "mean_localization_error_m",
    "p95_localization_error_m",
    "median_angular_error_deg",
    "success_rate",
    "catastrophic_failure_rate",
    "median_abs_tdoa_error_us",
    "rank_median",
    "rank_p95",
    "rank_angular",
    "rank_success",
    "rank_catastrophic",
    "rank_accuracy",
    "rank_reliability",
    "rank_balanced",
    "pareto",
    "roles",
]
SNR_FIELDS = [
    "geometry_id",
    "h4_height_m",
    "base_scale",
    "is_control",
    "snr_label",
    "noise_free",
    "snr_db",
    "n_trials",
    "n_successful",
    "median_localization_error_m",
    "success_rate",
    "median_abs_tdoa_error_us",
]
DIRECTION_FIELDS = [
    "geometry_id",
    "h4_height_m",
    "base_scale",
    "is_control",
    "direction",
    "n_sources",
    "n_trials",
    "n_successful",
    "median_localization_error_m",
    "mean_localization_error_m",
    "p95_localization_error_m",
    "median_angular_error_deg",
    "success_rate",
    "catastrophic_failure_rate",
    "median_abs_tdoa_error_us",
    "flag",
]
COORD_FIELDS = [
    "geometry_id",
    "h4_height_m",
    "base_scale",
    "is_control",
    "channel",
    "label",
    "x_m",
    "y_m",
    "z_m",
    "triangle_side_m",
    "max_baseline_m",
]


def main() -> None:
    args = _parse_args()
    started = time.perf_counter()
    before = _snapshot_protected()
    assert_layouts_match_catalog()
    config = load_config()
    n_trials = int(args.trials) if args.trials is not None else int(config["n_trials"])
    source_ids, sources = load_sources(n_trials)
    center = triangle_centroid_m()
    directions = [classify_direction(source, center) for source in sources]
    _print_plan(n_trials, sources)

    rows: list[dict[str, Any]] = []
    signatures: list[tuple[Any, ...]] | None = None
    conditions = _conditions(bool(config["include_noise_free"]), [float(value) for value in config["snr_levels_db"]])
    print(
        f"Change #2: 9 geometries x {n_trials} sources x {len(conditions)} SNR "
        f"at {float(config['carrier_frequency_hz']) / 1000.0:.0f} kHz",
        flush=True,
    )
    for height, scale, array in iter_geometries():
        geometry_rows = []
        side = float(coordinate_rows(height, scale, array)[0]["triangle_side_m"])
        baseline = float(array.max_pairwise_distance_m())
        for noise_free_flag, snr in conditions:
            for index in range(n_trials):
                trial = execute_trial(
                    array,
                    sources[index],
                    index + 1,
                    int(source_ids[index]),
                    snr,
                    noise_free_flag,
                    float(config["carrier_frequency_hz"]),
                    float(config["sample_rate_hz"]),
                    float(config["sound_speed_mps"]),
                    config,
                    trial_noise_seed(int(config["random_seed"]), index),
                )
                geometry_rows.append(
                    _annotate(
                        trial,
                        array_key=array.key,
                        height_m=height,
                        base_scale=scale,
                        side_m=side,
                        baseline_m=baseline,
                        direction=directions[index],
                    )
                )
        signature = [_case_signature(row) for row in geometry_rows]
        if signatures is None:
            signatures = signature
        elif signature != signatures:
            raise RuntimeError(f"{array.key} did not see the same sources, SNR list, and seeds")
        rows.extend(geometry_rows)
        _write_rows(output_path("data", f"{array.figure_stem}.csv"), geometry_rows)
        print(f"  {array.key:<12} done", flush=True)

    _write_rows(output_path("data", "experiment_results.csv"), rows)
    _write_products(rows, config, n_trials, time.perf_counter() - started, center)
    _assert_unchanged(before)
    print()
    print(f"saved under : {OUTPUT_ROOT.relative_to(PROJECT_ROOT)}")
    print("Previous result files were not modified.")


def _write_products(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    n_trials: int,
    elapsed_s: float,
    center: np.ndarray,
) -> None:
    ranked = rank_layouts(pooled_summaries(rows))
    snr_rows = snr_summaries(rows)
    selected = selected_geometry_ids(ranked)
    directional = directional_summaries(rows, set(selected))
    for record in directional:
        record["selection"] = _selection_label(record["geometry_id"], ranked)

    coordinates = []
    layouts = []
    for height, scale, array in iter_geometries():
        coordinates.extend(coordinate_rows(height, scale, array))
        layouts.append((height, scale, array.coordinates_m, array.key, array.key == geometry_id(0.30, 1.0)))

    write_table(output_path("geometries", "geometry_coordinates.csv"), COORD_FIELDS, coordinates)
    write_table(output_path("summaries", "geometry_comparison_summary.csv"), SUMMARY_FIELDS, ranked)
    write_table(output_path("summaries", "snr_comparison_summary.csv"), SNR_FIELDS, snr_rows)
    write_table(output_path("directional", "directional_comparison_summary.csv"), DIRECTION_FIELDS, directional)

    plot_geometries(layouts, output_path("plots", "geometries_3d.png"))
    plot_design_heatmap(
        ranked,
        "median_localization_error_m",
        "SIMULATION — median localization error",
        "Median localization error (m)",
        output_path("plots", "heatmap_median_error.png"),
    )
    plot_design_heatmap(
        ranked,
        "p95_localization_error_m",
        "SIMULATION — 95th percentile localization error",
        "95th percentile localization error (m)",
        output_path("plots", "heatmap_p95_error.png"),
    )
    plot_design_heatmap(
        ranked,
        "success_rate",
        "SIMULATION — localization success rate",
        "Success rate (%)",
        output_path("plots", "heatmap_success_rate.png"),
        percent=True,
        lower_is_better=False,
    )
    plot_design_heatmap(
        ranked,
        "catastrophic_failure_rate",
        "SIMULATION — catastrophic failure rate",
        "Catastrophic failure rate (%)",
        output_path("plots", "heatmap_catastrophic_rate.png"),
        percent=True,
    )
    plot_design_heatmap(
        ranked,
        "median_angular_error_deg",
        "SIMULATION — median angular error",
        "Median angular error (deg)",
        output_path("plots", "heatmap_angular_error.png"),
    )
    plot_accuracy_reliability(ranked, output_path("plots", "accuracy_vs_reliability.png"))
    plot_snr_heatmap(
        snr_rows,
        "median_localization_error_m",
        "SIMULATION — median localization error by SNR",
        "Median localization error (m)",
        output_path("plots", "snr_median_error.png"),
    )
    plot_snr_heatmap(
        snr_rows,
        "success_rate",
        "SIMULATION — success rate by SNR",
        "Success rate (%)",
        output_path("plots", "snr_success_rate.png"),
        percent=True,
        lower_is_better=False,
    )

    readme = render_readme(ranked, n_trials=n_trials, elapsed_s=elapsed_s, selected_ids=selected)
    readme_path = output_path("README.md")
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(readme, encoding="utf-8")
    _write_manifest(config, n_trials, elapsed_s, ranked, selected, center)
    _print_findings(ranked)


def _annotate(
    row: dict[str, Any],
    *,
    array_key: str,
    height_m: float,
    base_scale: float,
    side_m: float,
    baseline_m: float,
    direction: str,
) -> dict[str, Any]:
    annotated = {key: value for key, value in row.items() if not key.startswith("_")}
    annotated["geometry_id"] = array_key
    annotated["h4_height_m"] = float(height_m)
    annotated["base_scale"] = float(base_scale)
    annotated["is_control"] = array_key == geometry_id(0.30, 1.0)
    annotated["triangle_side_m"] = float(side_m)
    annotated["max_baseline_m"] = float(baseline_m)
    annotated["direction"] = direction
    return annotated


def _case_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row["source_id"]),
        int(row["trial"]),
        bool(row["noise_free"]),
        None if row["noise_free"] else round(float(row["snr_db"]), 6),
        int(row["noise_seed"]),
        round(float(row["source_x_m"]), 6),
        round(float(row["source_y_m"]), 6),
        round(float(row["source_z_m"]), 6),
    )


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = RAW_PREFIX + [key for key in rows[0] if key not in RAW_PREFIX]
    write_table(path, fieldnames, rows)


def _selection_label(geometry: str, ranked: list[dict[str, Any]]) -> str:
    match = next(row for row in ranked if row["geometry_id"] == geometry)
    return str(match["roles"])


def _print_plan(n_trials: int, sources: np.ndarray) -> None:
    print("Joint 3+1 study. H4 stays above the triangle. Base scale is about the H1/H2/H3 centroid.")
    print(f"  plane z = {plane_z_m():.12f} m")
    print(f"  centroid = ({triangle_centroid_m()[0]:.12f}, {triangle_centroid_m()[1]:.12f}, {triangle_centroid_m()[2]:.12f})")
    triangle = triangle_coordinates_m()
    for label, xyz in zip(("H1", "H2", "H3"), triangle):
        print(f"  catalog {label} = ({xyz[0]:.12f}, {xyz[1]:.12f}, {xyz[2]:.12f})")
    print(f"Sources: {sources.shape[0]}  (requested {n_trials})")
    print("Geometries:")
    for height, scale, array in iter_geometries():
        h4 = array.coordinates_m[3]
        mark = "  control" if array.key == geometry_id(0.30, 1.0) else ""
        print(
            f"  {array.key:<12} H4=({h4[0]:.6f}, {h4[1]:.6f}, {h4[2]:.6f})  "
            f"side={coordinate_rows(height, scale, array)[0]['triangle_side_m']:.6f} m{mark}"
        )
    print("Tetrahedral results are not read or written.", flush=True)


def _print_findings(ranked: list[dict[str, Any]]) -> None:
    print()
    print("Layouts, best balanced rank first:")
    ordered = sorted(ranked, key=lambda row: (int(row["rank_balanced"]), float(row["median_localization_error_m"])))
    for row in ordered:
        print(
            f"  {row['geometry_id']:<12} median {float(row['median_localization_error_m']):.3f} m  "
            f"success {100 * float(row['success_rate']):.1f}%  "
            f"balanced rank {int(row['rank_balanced'])}  {row['roles']}"
        )


def _write_manifest(
    config: dict[str, Any],
    n_trials: int,
    elapsed_s: float,
    ranked: list[dict[str, Any]],
    selected: list[str],
    center: np.ndarray,
) -> None:
    manifest = {
        "label": "SIMULATION",
        "study": "joint_geometry_optimization",
        "pipeline": "change_2_waveform",
        "comparison_with_tetrahedral": False,
        "control_geometry_id": geometry_id(0.30, 1.0),
        "h4_heights_m": [0.30, 0.40, 0.50],
        "base_scales": [1.00, 1.25, 1.50],
        "h4_sign": "positive, above the H1/H2/H3 plane",
        "scaling": "H1/H2/H3 x and y about the triangle centroid; z unchanged; H4 xy at that centroid",
        "classification_center_m": [float(value) for value in center],
        "classification_rule": (
            "Include an axis when its absolute component is at least 0.5 times the largest component. "
            f"Bins with fewer than {MIN_SOURCES} unique sources are flagged INSUFFICIENT_SAMPLE_COUNT."
        ),
        "catastrophic_definition": (
            "A trial is catastrophic when the solver rejects it or the accepted localization error exceeds 20 m."
        ),
        "number_of_trials": int(n_trials),
        "random_seed": int(config["random_seed"]),
        "paired_cases": True,
        "carrier_frequency_hz": float(config["carrier_frequency_hz"]),
        "pulse_duration_s": float(config["pulse_duration_s"]),
        "sampling_rate_hz": float(config["sample_rate_hz"]),
        "sound_speed_mps": float(SOUND_SPEED_MPS),
        "apply_attenuation": bool(config["apply_attenuation"]),
        "snr": (["noise-free"] if config["include_noise_free"] else [])
        + [f"{float(level):.0f} dB" for level in config["snr_levels_db"]],
        "TDOA_method": "GCC-PHAT, existing src.tdoa.estimate_tdoas, search limited to that array's baseline/c",
        "source_position_dataset": "first N rows of simulations/geometry_study/results/source_positions.csv",
        "ranking_rule": (
            "Accuracy rank sums median error, 95th percentile, and median angular error. "
            "Reliability rank sums success rate and catastrophic rate. "
            "Balanced rank sums those five. Median error alone is not the selector."
        ),
        "directional_geometry_ids": selected,
        "geometries": [
            {
                "geometry_id": row["geometry_id"],
                "h4_height_m": float(row["h4_height_m"]),
                "base_scale": float(row["base_scale"]),
                "is_control": bool(row["is_control"]),
                "triangle_side_m": float(row["triangle_side_m"]),
                "max_baseline_m": float(row["max_baseline_m"]),
                "roles": row["roles"],
                "pareto": bool(row["pareto"]),
                "rank_balanced": int(row["rank_balanced"]),
            }
            for row in ranked
        ],
        "elapsed_s": round(float(elapsed_s), 3),
        "protected_result_directories": [str(path.relative_to(PROJECT_ROOT)) for path in PROTECTED_DIRS],
    }
    path = output_path("run_manifest.json")
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _conditions(include_noise_free: bool, levels: list[float]) -> list[tuple[bool, float]]:
    conditions: list[tuple[bool, float]] = []
    if include_noise_free:
        conditions.append((True, float("nan")))
    conditions.extend((False, float(level)) for level in levels)
    return conditions


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
        raise RuntimeError("a protected result file changed during the joint geometry study")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Joint H4 height and base-scale study")
    parser.add_argument("--trials", type=int, default=None, help="Override the Change #2 source count")
    args = parser.parse_args()
    if args.trials is not None and args.trials < 1:
        parser.error("--trials must be at least 1")
    return args


if __name__ == "__main__":
    main()
