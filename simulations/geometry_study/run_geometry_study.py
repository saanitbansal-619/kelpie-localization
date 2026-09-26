"""Run the five-geometry TDOA and localization simulation study.

From the project root:

    python simulations/geometry_study/run_geometry_study.py

Pass ``--plots-only`` to rebuild figures from ``results/experiment_results.csv``
without repeating the Monte Carlo loop. Representative waveform figures are
recomputed either way; that step is a handful of trials.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_study.analysis import (
    EXPERIMENT_FIELDS,
    STRING_FIELDS,
    SUMMARY_FIELDS,
    summarize_results,
    verify_experiment,
)
from simulations.geometry_study.figures import (
    plot_all_geometries,
    plot_angular_error_by_geometry,
    plot_error_vs_distance,
    plot_gcc,
    plot_geometry,
    plot_localization_error_vs_snr,
    plot_position_error_by_geometry,
    plot_propagation,
    plot_spatial_error,
    plot_success_rate,
    plot_tdoa_error_by_geometry,
    plot_tdoa_error_vs_snr,
    plot_true_vs_estimated,
    plot_waveforms,
    spatial_color_limit,
)
from simulations.geometry_study.pipeline import (
    geometry_delays_samples,
    noise_std_for_snr,
    prepare_reference_waveform,
    representative_waveforms,
    run_trial,
)
from src.geometry import (
    SOUND_SPEED_MPS,
    generate_source_positions,
    list_geometries,
    max_pairwise_distance_m,
    max_pairwise_tdoa_s,
    minimum_source_hydrophone_distance_m,
    sampling_sanity,
)
from src.simulation import DEFAULT_FS
from src.tdoa import DEFAULT_SOUND_SPEED_MPS

STUDY_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = STUDY_ROOT / "configs" / "experiment.json"
RESULTS_DIR = STUDY_ROOT / "results"
FIGURES_DIR = STUDY_ROOT / "figures"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if float(config["sample_rate_hz"]) != float(DEFAULT_FS):
        raise RuntimeError("experiment sample rate does not match src.simulation.DEFAULT_FS")
    if float(config["sound_speed_mps"]) != float(SOUND_SPEED_MPS):
        raise RuntimeError("experiment sound speed does not match src.geometry.SOUND_SPEED_MPS")
    if float(config["sound_speed_mps"]) != float(DEFAULT_SOUND_SPEED_MPS):
        raise RuntimeError("experiment sound speed does not match src.tdoa.DEFAULT_SOUND_SPEED_MPS")
    return config


def _csv_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not np.isfinite(number):
            return "nan"
        return f"{number:.10g}"
    return str(value)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in fieldnames})


def read_experiment_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, Any]] = []
        for raw in reader:
            row: dict[str, Any] = {}
            for key, value in raw.items():
                if key in STRING_FIELDS:
                    row[key] = value
                elif value == "":
                    row[key] = float("nan")
                else:
                    row[key] = float(value)
            rows.append(row)
    return rows


def write_coordinates(arrays: list, path: Path) -> None:
    rows = []
    for array in arrays:
        for channel, xyz in enumerate(array.coordinates_m):
            rows.append(
                {
                    "geometry": array.key,
                    "geometry_name": array.name,
                    "channel": f"H{channel}",
                    "x_m": float(xyz[0]),
                    "y_m": float(xyz[1]),
                    "z_m": float(xyz[2]),
                }
            )
    write_csv(path, ["geometry", "geometry_name", "channel", "x_m", "y_m", "z_m"], rows)


def write_physical_bounds(arrays: list, rows: list[dict[str, Any]], sound_speed: float, path: Path) -> None:
    table = []
    for array in arrays:
        separation = max_pairwise_distance_m(array.coordinates_m)
        max_tdoa_us = max_pairwise_tdoa_s(array.coordinates_m, sound_speed) * 1e6
        observed = []
        for row in rows:
            if row["geometry"] != array.key:
                continue
            for key in ("true_tdoa_h1_us", "true_tdoa_h2_us", "true_tdoa_h3_us"):
                observed.append(abs(float(row[key])))
        observed_max = float(np.max(observed)) if observed else float("nan")
        table.append(
            {
                "geometry": array.key,
                "geometry_class": array.expected_class,
                "max_pairwise_separation_m": separation,
                "max_pairwise_tdoa_us": max_tdoa_us,
                "observed_max_abs_true_tdoa_us": observed_max,
                "within_physical_bound": "true" if observed_max <= max_tdoa_us + 1e-6 else "false",
            }
        )
    write_csv(
        path,
        [
            "geometry",
            "geometry_class",
            "max_pairwise_separation_m",
            "max_pairwise_tdoa_us",
            "observed_max_abs_true_tdoa_us",
            "within_physical_bound",
        ],
        table,
    )


def write_sampling_sanity(fs: float, sound_speed: float, path: Path) -> dict[str, float]:
    sanity = sampling_sanity(fs, sound_speed)
    write_csv(path, list(sanity.keys()), [sanity])
    return sanity


def run_representative(config: dict[str, Any], arrays: list) -> None:
    fs = float(config["sample_rate_hz"])
    sound_speed = float(config["sound_speed_mps"])
    source = np.asarray(config["representative_source_m"], dtype=float)
    snr_db = float(config["representative_snr_db"])
    _, reference = prepare_reference_waveform(
        fs,
        float(config["capture_duration_s"]),
        float(config["event_time_s"]),
    )
    propagation_rows = []
    tdoa_rows = []
    for array in arrays:
        distances, true_tdoa_s, _delays = geometry_delays_samples(array, source, fs, sound_speed)
        times_s = distances / sound_speed
        for channel in range(4):
            xyz = array.coordinates_m[channel]
            propagation_rows.append(
                {
                    "Geometry": array.name,
                    "Channel": f"H{channel}",
                    "Hydrophone X": float(xyz[0]),
                    "Hydrophone Y": float(xyz[1]),
                    "Hydrophone Z": float(xyz[2]),
                    "Source X": float(source[0]),
                    "Source Y": float(source[1]),
                    "Source Z": float(source[2]),
                    "Distance (m)": float(distances[channel]),
                    "Propagation Time (us)": float(times_s[channel] * 1e6),
                    "True TDOA Relative to H0 (us)": float(true_tdoa_s[channel] * 1e6),
                }
            )
        bundle = representative_waveforms(
            array,
            source,
            snr_db,
            reference,
            fs,
            sound_speed,
            config,
        )
        estimated = bundle["estimated_tdoa_s"]
        for channel, pair in ((1, "H1-H0"), (2, "H2-H0"), (3, "H3-H0")):
            true_us = float(true_tdoa_s[channel] * 1e6)
            est_us = float(estimated[channel] * 1e6)
            tdoa_rows.append(
                {
                    "Geometry": array.name,
                    "Channel Pair": pair,
                    "True TDOA (us)": true_us,
                    "Estimated TDOA (us)": est_us,
                    "Absolute Error (us)": abs(est_us - true_us),
                }
            )
        stem = array.figure_stem
        plot_propagation(
            array,
            source,
            distances,
            true_tdoa_s * 1e6,
            FIGURES_DIR / "propagation" / f"{stem}.png",
        )
        plot_waveforms(array, bundle["window"], fs, FIGURES_DIR / "waveforms" / f"{stem}.png")
        plot_gcc(
            array,
            bundle["diagnostics"],
            true_tdoa_s,
            estimated,
            FIGURES_DIR / "gcc_phat" / f"{stem}.png",
        )
        print(f"representative figures: {array.key}", flush=True)

    write_csv(
        RESULTS_DIR / "propagation_ground_truth.csv",
        [
            "Geometry",
            "Channel",
            "Hydrophone X",
            "Hydrophone Y",
            "Hydrophone Z",
            "Source X",
            "Source Y",
            "Source Z",
            "Distance (m)",
            "Propagation Time (us)",
            "True TDOA Relative to H0 (us)",
        ],
        propagation_rows,
    )
    write_csv(
        RESULTS_DIR / "representative_tdoa.csv",
        ["Geometry", "Channel Pair", "True TDOA (us)", "Estimated TDOA (us)", "Absolute Error (us)"],
        tdoa_rows,
    )


def run_monte_carlo(config: dict[str, Any], arrays: list) -> list[dict[str, Any]]:
    fs = float(config["sample_rate_hz"])
    sound_speed = float(config["sound_speed_mps"])
    snr_levels = [float(value) for value in config["snr_levels_db"]]
    n_sources = int(config["n_sources"])
    sources = generate_source_positions(
        n_sources=n_sources,
        seed=int(config["source_seed"]),
        range_min_m=float(config["range_min_m"]),
        range_max_m=float(config["range_max_m"]),
        elevation_min_deg=float(config["elevation_min_deg"]),
        elevation_max_deg=float(config["elevation_max_deg"]),
    )
    closest = min(
        minimum_source_hydrophone_distance_m(sources, array.coordinates_m) for array in arrays
    )
    if closest < 0.5:
        raise RuntimeError(f"a source is only {closest:.3f} m from a hydrophone")

    source_rows = []
    for source_id, xyz in enumerate(sources):
        source_rows.append(
            {
                "source_id": source_id,
                "x_m": float(xyz[0]),
                "y_m": float(xyz[1]),
                "z_m": float(xyz[2]),
                "range_m": float(np.linalg.norm(xyz)),
            }
        )
    write_csv(
        RESULTS_DIR / "source_positions.csv",
        ["source_id", "x_m", "y_m", "z_m", "range_m"],
        source_rows,
    )

    _, reference = prepare_reference_waveform(
        fs,
        float(config["capture_duration_s"]),
        float(config["event_time_s"]),
    )
    noise_std = {snr: noise_std_for_snr(snr, fs) for snr in snr_levels}
    rows: list[dict[str, Any]] = []
    total = n_sources * len(snr_levels) * len(arrays)
    print(f"Monte Carlo: {total} trials ({n_sources} sources x {len(snr_levels)} SNRs x {len(arrays)} geometries)", flush=True)
    started = time.perf_counter()
    done = 0
    for source_id, source in enumerate(sources):
        for snr in snr_levels:
            for array in arrays:
                rows.append(
                    run_trial(
                        array,
                        source,
                        source_id,
                        snr,
                        reference,
                        fs,
                        sound_speed,
                        noise_std[snr],
                        config,
                    )
                )
                done += 1
        if source_id % 25 == 0 or source_id == n_sources - 1:
            elapsed = time.perf_counter() - started
            rate = done / elapsed if elapsed else 0.0
            remaining = (total - done) / rate if rate else float("nan")
            print(
                f"  source {source_id + 1}/{n_sources}  trials {done}/{total}  "
                f"elapsed {elapsed:.0f}s  remaining ~{remaining:.0f}s",
                flush=True,
            )
    return rows


def comparison_figures(rows: list[dict[str, Any]], arrays: list, config: dict[str, Any]) -> None:
    snr_levels = [float(value) for value in config["snr_levels_db"]]
    primary = float(config["primary_comparison_snr_db"])
    comparisons = FIGURES_DIR / "comparisons"
    plot_true_vs_estimated(rows, arrays, FIGURES_DIR / "tdoa" / "true_vs_estimated_tdoa.png")
    plot_tdoa_error_by_geometry(rows, arrays, primary, comparisons / "tdoa_error_by_geometry.png")
    plot_tdoa_error_vs_snr(rows, arrays, snr_levels, comparisons / "tdoa_error_vs_snr.png")
    plot_angular_error_by_geometry(rows, arrays, primary, comparisons / "angular_error_by_geometry.png")
    plot_position_error_by_geometry(rows, arrays, primary, comparisons / "position_error_by_geometry.png")
    plot_localization_error_vs_snr(rows, arrays, snr_levels, comparisons / "localization_error_vs_snr.png")
    plot_success_rate(rows, arrays, snr_levels, comparisons / "solver_success_by_geometry.png")
    plot_error_vs_distance(rows, arrays, primary, comparisons / "error_vs_source_distance.png")
    color_max = spatial_color_limit(rows, arrays, primary)
    for array in arrays:
        plot_spatial_error(
            rows,
            array,
            primary,
            FIGURES_DIR / "localization" / f"{array.figure_stem}.png",
            vmax_deg=color_max,
        )


def required_figure_paths(arrays: list) -> list[Path]:
    paths = [FIGURES_DIR / "geometries" / "all_geometries_comparison.png"]
    for array in arrays:
        stem = array.figure_stem
        paths.extend(
            [
                FIGURES_DIR / "geometries" / f"{stem}.png",
                FIGURES_DIR / "propagation" / f"{stem}.png",
                FIGURES_DIR / "waveforms" / f"{stem}.png",
                FIGURES_DIR / "gcc_phat" / f"{stem}.png",
                FIGURES_DIR / "localization" / f"{stem}.png",
            ]
        )
    paths.extend(
        [
            FIGURES_DIR / "tdoa" / "true_vs_estimated_tdoa.png",
            FIGURES_DIR / "comparisons" / "tdoa_error_by_geometry.png",
            FIGURES_DIR / "comparisons" / "tdoa_error_vs_snr.png",
            FIGURES_DIR / "comparisons" / "angular_error_by_geometry.png",
            FIGURES_DIR / "comparisons" / "position_error_by_geometry.png",
            FIGURES_DIR / "comparisons" / "localization_error_vs_snr.png",
            FIGURES_DIR / "comparisons" / "solver_success_by_geometry.png",
            FIGURES_DIR / "comparisons" / "error_vs_source_distance.png",
        ]
    )
    return paths


def verify_figures(paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        if not path.is_file():
            problems.append(f"missing figure {path}")
            continue
        size = path.stat().st_size
        if size < 8_000:
            problems.append(f"figure looks empty ({size} bytes): {path}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hydrophone geometry simulation study.")
    parser.add_argument(
        "--plots-only",
        action="store_true",
        help="Reload results/experiment_results.csv and rebuild figures.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    config = load_config()
    arrays = list(list_geometries())
    print("SIMULATION geometry study", flush=True)
    print(f"geometries: {', '.join(array.key for array in arrays)}", flush=True)

    for array in arrays:
        plot_geometry(array, FIGURES_DIR / "geometries" / f"{array.figure_stem}.png")
    plot_all_geometries(arrays, FIGURES_DIR / "geometries" / "all_geometries_comparison.png")
    write_coordinates(arrays, RESULTS_DIR / "hydrophone_coordinates.csv")
    sanity = write_sampling_sanity(
        float(config["sample_rate_hz"]),
        float(config["sound_speed_mps"]),
        RESULTS_DIR / "sampling_sanity.csv",
    )
    print(
        f"sample period {sanity['sample_period_us']:.5f} us, "
        f"{sanity['millimetres_per_sample']:.5f} mm/sample, "
        f"0.25 m transit {sanity['reference_max_tdoa_us']:.2f} us",
        flush=True,
    )

    run_representative(config, arrays)

    results_path = RESULTS_DIR / "experiment_results.csv"
    if args.plots_only:
        if not results_path.is_file():
            raise SystemExit(f"missing {results_path}")
        rows = read_experiment_csv(results_path)
        print(f"loaded {len(rows)} rows from {results_path}", flush=True)
    else:
        rows = run_monte_carlo(config, arrays)
        write_csv(results_path, EXPERIMENT_FIELDS, rows)
        print(f"wrote {results_path} ({len(rows)} rows)", flush=True)

    problems = verify_experiment(
        rows,
        arrays,
        [float(value) for value in config["snr_levels_db"]],
        n_sources=len({int(row["source_id"]) for row in rows}),
        sound_speed_mps=float(config["sound_speed_mps"]),
    )
    if problems:
        raise SystemExit("experiment table failed checks:\n" + "\n".join(problems))

    summary = summarize_results(
        rows,
        arrays,
        [float(value) for value in config["snr_levels_db"]],
    )
    write_csv(RESULTS_DIR / "geometry_summary.csv", SUMMARY_FIELDS, summary)
    write_physical_bounds(
        arrays,
        rows,
        float(config["sound_speed_mps"]),
        RESULTS_DIR / "geometry_physical_bounds.csv",
    )
    comparison_figures(rows, arrays, config)

    figure_problems = verify_figures(required_figure_paths(arrays))
    if figure_problems:
        raise SystemExit("figure checks failed:\n" + "\n".join(figure_problems))

    elapsed = time.perf_counter() - started
    manifest_path = RESULTS_DIR / "run_manifest.json"
    previous = {}
    if args.plots_only and manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = {
        "label": "SIMULATION",
        "n_sources": len({int(row["source_id"]) for row in rows}),
        "n_geometries": len(arrays),
        "snr_levels_db": [float(value) for value in config["snr_levels_db"]],
        "n_rows": len(rows),
        "source_seed": int(config["source_seed"]),
        "primary_comparison_snr_db": float(config["primary_comparison_snr_db"]),
        "representative_source_m": config["representative_source_m"],
        "representative_snr_db": float(config["representative_snr_db"]),
        "elapsed_s": previous.get("elapsed_s", round(elapsed, 1)) if args.plots_only else round(elapsed, 1),
        "monte_carlo_note": "elapsed_s is the full study script, including figures, from the Monte Carlo run",
        "plots_only": bool(args.plots_only),
    }
    if args.plots_only:
        manifest["figure_refresh_s"] = round(elapsed, 1)
    manifest_path = RESULTS_DIR / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"finished in {elapsed:.1f} s", flush=True)
    print(f"manifest {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
