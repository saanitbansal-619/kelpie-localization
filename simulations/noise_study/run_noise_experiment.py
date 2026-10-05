"""Localization error versus SNR on the existing tetrahedral array.

From the project root:

    python simulations/noise_study/run_noise_experiment.py

Writes ``results/noise_experiment_results.csv``,
``results/noise_experiment_summary.csv``, and the figures under ``figures/``.
Existing geometry-study and hydrophone-count results are not modified.

``--plots-only`` rebuilds the figures from the saved trial CSV.
``--seed`` and ``--trials`` override the values in ``configs/experiment.json``.
``--skip-noise-free`` omits the zero-noise baseline.
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

from simulations.geometry_study.pipeline import prepare_reference_waveform
from simulations.noise_study.analysis import (
    BOOL_FIELDS,
    INT_FIELDS,
    RESULT_FIELDS,
    STRING_FIELDS,
    SUMMARY_FIELDS,
    as_bool,
    finite_snr_levels,
    is_noise_free,
    is_success,
    summarize_results,
)
from simulations.noise_study.figures import save_noise_figures
from simulations.noise_study.pipeline import execute_trial, noise_std_for_condition, trial_noise_seed
from src.geometry import SOUND_SPEED_MPS, generate_source_positions, get_geometry
from src.simulation import DEFAULT_FS
from src.tdoa import DEFAULT_SOUND_SPEED_MPS

STUDY_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = STUDY_ROOT / "configs" / "experiment.json"
RESULTS_DIR = STUDY_ROOT / "results"
FIGURES_DIR = STUDY_ROOT / "figures"
RESULTS_CSV = RESULTS_DIR / "noise_experiment_results.csv"
SUMMARY_CSV = RESULTS_DIR / "noise_experiment_summary.csv"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if float(config["sample_rate_hz"]) != float(DEFAULT_FS):
        raise RuntimeError("experiment sample rate does not match src.simulation.DEFAULT_FS")
    if float(config["sound_speed_mps"]) != float(SOUND_SPEED_MPS):
        raise RuntimeError("experiment sound speed does not match src.geometry.SOUND_SPEED_MPS")
    if float(config["sound_speed_mps"]) != float(DEFAULT_SOUND_SPEED_MPS):
        raise RuntimeError("experiment sound speed does not match src.tdoa.DEFAULT_SOUND_SPEED_MPS")
    levels = [float(value) for value in config["snr_levels_db"]]
    if not levels or any(not np.isfinite(level) for level in levels):
        raise RuntimeError("snr_levels_db must be a non-empty list of finite SNR values")
    if len(set(levels)) != len(levels):
        raise RuntimeError("snr_levels_db contains a duplicate")
    if int(config["n_trials"]) < 1:
        raise RuntimeError("n_trials must be at least 1")
    config["snr_levels_db"] = levels
    return config


def _csv_value(key: str, value: Any) -> str:
    if key in STRING_FIELDS:
        return "" if value is None else str(value)
    if key in BOOL_FIELDS:
        return "true" if as_bool(value) else "false"
    if key in INT_FIELDS:
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return ""
        return str(int(value))
    if value is None or value == "":
        return ""
    number = float(value)
    if not np.isfinite(number):
        return ""
    return f"{number:.10g}"


def _parse_value(key: str, value: str) -> Any:
    if key in STRING_FIELDS:
        return value
    if key in BOOL_FIELDS:
        return value.strip().lower() == "true"
    if key in INT_FIELDS:
        return int(value) if value != "" else 0
    if value == "":
        return float("nan")
    return float(value)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(key, row.get(key, "")) for key in fieldnames})


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: _parse_value(key, raw.get(key, "")) for key in reader.fieldnames or []} for raw in reader]


def _fmt_number(value: float, width: int, digits: int) -> str:
    if not np.isfinite(value):
        return f"{'n/a':>{width}}"
    return f"{value:{width}.{digits}f}"


def _fmt_percent(rate: float, width: int) -> str:
    if not np.isfinite(rate):
        return f"{'n/a':>{width}}"
    return f"{100.0 * rate:{width}.1f}%"


def _snr_label(row: dict[str, Any]) -> str:
    if is_noise_free(row):
        return "noise-free"
    return f"{float(row['snr_db']):.0f} dB"


def print_summary(summary: list[dict[str, Any]]) -> None:
    print()
    print("Error columns use successful localizations only. Success uses every trial.")
    print(
        f"{'SNR':<12}{'Mean Error (m)':>16}{'Median Error (m)':>18}"
        f"{'95th % (m)':>14}{'Success':>12}"
    )
    for row in summary:
        print(
            f"{_snr_label(row):<12}"
            f"{_fmt_number(float(row['mean_localization_error_m']), 16, 3)}"
            f"{_fmt_number(float(row['median_localization_error_m']), 18, 3)}"
            f"{_fmt_number(float(row['p95_localization_error_m']), 14, 3)}"
            f"{_fmt_percent(float(row['localization_success_rate']), 12)}"
        )


def run_experiment(
    config: dict[str, Any],
    results_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    array = get_geometry(str(config["geometry"]))
    if array.expected_class != "volumetric":
        raise RuntimeError(
            f"{array.key} is {array.expected_class}; localization versus SNR needs a volumetric array"
        )
    fs = float(config["sample_rate_hz"])
    sound_speed = float(config["sound_speed_mps"])
    n_trials = int(config["n_trials"])
    random_seed = int(config["random_seed"])
    snr_levels = [float(value) for value in config["snr_levels_db"]]
    include_noise_free = bool(config["include_noise_free"])
    _, reference = prepare_reference_waveform(
        fs,
        float(config["capture_duration_s"]),
        float(config["event_time_s"]),
    )
    sources = generate_source_positions(
        n_trials,
        seed=random_seed,
        range_min_m=float(config["range_min_m"]),
        range_max_m=float(config["range_max_m"]),
        elevation_min_deg=float(config["elevation_min_deg"]),
        elevation_max_deg=float(config["elevation_max_deg"]),
    )
    _write_sources(sources, results_dir)

    conditions: list[tuple[bool, float]] = []
    if include_noise_free:
        conditions.append((True, float("nan")))
    conditions.extend((False, snr) for snr in snr_levels)

    n_expected = n_trials * len(conditions)
    print(
        f"Noise study: {n_trials} trials x {len(conditions)} conditions = {n_expected} "
        f"on {array.name} ({array.coordinates_m.shape[0]} hydrophones)",
        flush=True,
    )
    print(f"random seed        : {random_seed}", flush=True)
    print("same source and noise pattern at every SNR; only the noise scale changes", flush=True)

    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    for noise_free, snr in conditions:
        noise_std = noise_std_for_condition(snr, fs, noise_free=noise_free)
        for trial_index in range(n_trials):
            rows.append(
                execute_trial(
                    array,
                    sources[trial_index],
                    trial_index,
                    trial_index + 1,
                    snr,
                    noise_free,
                    reference,
                    fs,
                    sound_speed,
                    noise_std,
                    config,
                    trial_noise_seed(random_seed, trial_index),
                )
            )
        done = rows[-n_trials:]
        n_ok = sum(1 for row in done if is_success(row))
        label = "noise-free" if noise_free else f"{snr:.0f} dB"
        print(f"{label:<12} {n_ok}/{n_trials} succeeded", flush=True)

    elapsed = time.perf_counter() - started
    summary = summarize_results(rows)
    return rows, summary, elapsed


def _write_sources(sources: np.ndarray, directory: Path | None = None) -> None:
    path = (RESULTS_DIR if directory is None else directory) / "source_positions.csv"
    rows = []
    for index, xyz in enumerate(sources):
        rows.append(
            {
                "trial": index + 1,
                "x_m": float(xyz[0]),
                "y_m": float(xyz[1]),
                "z_m": float(xyz[2]),
                "range_m": float(np.linalg.norm(xyz)),
            }
        )
    write_csv(path, ["trial", "x_m", "y_m", "z_m", "range_m"], rows)


def _write_manifest(config: dict[str, Any], n_rows: int, elapsed_s: float) -> None:
    manifest = {
        "label": "SIMULATION",
        "geometry": str(config["geometry"]),
        "n_hydrophones": int(get_geometry(str(config["geometry"])).coordinates_m.shape[0]),
        "n_trials_per_condition": int(config["n_trials"]),
        "snr_levels_db": [float(value) for value in config["snr_levels_db"]],
        "include_noise_free": bool(config["include_noise_free"]),
        "random_seed": int(config["random_seed"]),
        "n_rows": int(n_rows),
        "elapsed_s": round(float(elapsed_s), 3),
        "noise_model": (
            "SNR_dB = 10*log10(P_chirp / P_noise); "
            "independent Gaussian sample on each hydrophone; "
            "one noise pattern per trial, scaled to each SNR"
        ),
    }
    path = RESULTS_DIR / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Localization error versus SNR")
    parser.add_argument(
        "--plots-only",
        action="store_true",
        help="Rebuild figures from results/noise_experiment_results.csv",
    )
    parser.add_argument("--seed", type=int, default=None, help="Override random_seed")
    parser.add_argument("--trials", type=int, default=None, help="Override trials per SNR")
    parser.add_argument(
        "--skip-noise-free",
        action="store_true",
        help="Omit the zero-noise baseline",
    )
    args = parser.parse_args()

    if args.plots_only:
        rows = read_csv(RESULTS_CSV)
        summary = summarize_results(rows)
        write_csv(SUMMARY_CSV, SUMMARY_FIELDS, summary)
        paths = save_noise_figures(rows, summary, FIGURES_DIR, finite_snr_levels(rows))
        print_summary(summary)
        for path in paths:
            print(f"saved plot  : {path.relative_to(PROJECT_ROOT)}")
        return

    config = load_config()
    if args.seed is not None:
        config["random_seed"] = int(args.seed)
    if args.trials is not None:
        if args.trials < 1:
            raise RuntimeError("--trials must be at least 1")
        config["n_trials"] = int(args.trials)
    if args.skip_noise_free:
        config["include_noise_free"] = False

    rows, summary, elapsed = run_experiment(config)
    write_csv(RESULTS_CSV, RESULT_FIELDS, rows)
    write_csv(SUMMARY_CSV, SUMMARY_FIELDS, summary)
    _write_manifest(config, len(rows), elapsed)
    paths = save_noise_figures(
        rows,
        summary,
        FIGURES_DIR,
        [float(value) for value in config["snr_levels_db"]],
    )
    print_summary(summary)
    print()
    print(f"elapsed     : {elapsed:.1f} s")
    print(f"saved CSV   : {RESULTS_CSV.relative_to(PROJECT_ROOT)}")
    print(f"saved CSV   : {SUMMARY_CSV.relative_to(PROJECT_ROOT)}")
    for path in paths:
        print(f"saved plot  : {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
