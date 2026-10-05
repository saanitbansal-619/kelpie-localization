"""Localization from a pulsed sinusoidal pinger, using estimated TDOAs.

From the project root:

    python simulations/waveform_study/run_waveform_experiment.py

Writes the 40 kHz SNR sweep and a smaller 25/30/35/40 kHz comparison under
``simulations/waveform_study/results/`` and ``figures/``. The Change #1 noise
study is not modified.

``--plots-only`` rebuilds figures from the saved CSVs.
``--trials`` overrides the trial count for the 40 kHz sweep.
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

from simulations.waveform_study.analysis import (
    BOOL_FIELDS,
    INT_FIELDS,
    RESULT_FIELDS,
    STRING_FIELDS,
    SUMMARY_FIELDS,
    as_bool,
    is_noise_free,
    is_success,
    summarize_results,
)
from simulations.waveform_study.figures import save_waveform_figures
from simulations.waveform_study.pipeline import (
    execute_trial,
    representative_capture,
    trial_noise_seed,
)
from src.geometry import SOUND_SPEED_MPS, get_geometry
from src.simulation import DEFAULT_FS
from src.tdoa import DEFAULT_SOUND_SPEED_MPS

STUDY_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = STUDY_ROOT / "configs" / "experiment.json"
RESULTS_DIR = STUDY_ROOT / "results"
FIGURES_DIR = STUDY_ROOT / "figures"
RESULTS_CSV = RESULTS_DIR / "waveform_experiment_results.csv"
SUMMARY_CSV = RESULTS_DIR / "waveform_experiment_summary.csv"
FREQUENCY_CSV = RESULTS_DIR / "waveform_frequency_comparison.csv"
FREQUENCY_SUMMARY_CSV = RESULTS_DIR / "waveform_frequency_summary.csv"
SOURCE_CSV = PROJECT_ROOT / "simulations" / "geometry_study" / "results" / "source_positions.csv"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    if float(config["sample_rate_hz"]) != float(DEFAULT_FS):
        raise RuntimeError("experiment sample rate does not match src.simulation.DEFAULT_FS")
    if float(config["sound_speed_mps"]) != float(SOUND_SPEED_MPS):
        raise RuntimeError("experiment sound speed does not match src.geometry.SOUND_SPEED_MPS")
    if float(config["sound_speed_mps"]) != float(DEFAULT_SOUND_SPEED_MPS):
        raise RuntimeError("experiment sound speed does not match src.tdoa.DEFAULT_SOUND_SPEED_MPS")
    config["snr_levels_db"] = [float(value) for value in config["snr_levels_db"]]
    config["comparison_frequencies_hz"] = [float(value) for value in config["comparison_frequencies_hz"]]
    if int(config["n_trials"]) < 1 or int(config["n_frequency_trials"]) < 1:
        raise RuntimeError("trial counts must be at least 1")
    nyquist = 0.5 * float(config["sample_rate_hz"])
    carriers = [float(config["carrier_frequency_hz"]), *config["comparison_frequencies_hz"]]
    if any(carrier <= 0 or carrier >= nyquist for carrier in carriers):
        raise RuntimeError("a carrier frequency is outside (0, Nyquist)")
    return config


def load_sources(n_sources: int) -> tuple[np.ndarray, np.ndarray]:
    """First ``n_sources`` positions from the geometry-study source table."""
    if not SOURCE_CSV.is_file():
        raise RuntimeError(f"missing source table {SOURCE_CSV}")
    with SOURCE_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < n_sources:
        raise RuntimeError(f"source table has {len(rows)} rows; need {n_sources}")
    ids = np.array([int(row["source_id"]) for row in rows[:n_sources]], dtype=int)
    xyz = np.array(
        [[float(row["x_m"]), float(row["y_m"]), float(row["z_m"])] for row in rows[:n_sources]],
        dtype=float,
    )
    return ids, xyz


def _csv_value(key: str, value: Any) -> str:
    if key in STRING_FIELDS:
        return "" if value is None else str(value)
    if key in BOOL_FIELDS:
        return "true" if as_bool(value) else "false"
    if key in INT_FIELDS:
        if value is None or (isinstance(value, float) and not np.isfinite(float(value))):
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
        fieldnames = reader.fieldnames or []
        return [{key: _parse_value(key, raw.get(key, "")) for key in fieldnames} for raw in reader]


def _conditions(config: dict[str, Any]) -> list[tuple[bool, float]]:
    conditions: list[tuple[bool, float]] = []
    if bool(config["include_noise_free"]):
        conditions.append((True, float("nan")))
    conditions.extend((False, float(snr)) for snr in config["snr_levels_db"])
    return conditions


def _run_grid(
    config: dict[str, Any],
    array: Any,
    source_ids: np.ndarray,
    sources: np.ndarray,
    carriers: list[float],
    conditions: list[tuple[bool, float]],
    label: str,
) -> list[dict[str, Any]]:
    fs = float(config["sample_rate_hz"])
    sound_speed = float(config["sound_speed_mps"])
    seed0 = int(config["random_seed"])
    n_trials = int(sources.shape[0])
    expected = n_trials * len(carriers) * len(conditions)
    print(
        f"{label}: {n_trials} trials x {len(carriers)} carriers x {len(conditions)} conditions = {expected}",
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    for carrier in carriers:
        for noise_free, snr in conditions:
            for index in range(n_trials):
                rows.append(
                    execute_trial(
                        array,
                        sources[index],
                        int(index + 1),
                        int(source_ids[index]),
                        snr,
                        noise_free,
                        float(carrier),
                        fs,
                        sound_speed,
                        config,
                        trial_noise_seed(seed0, index),
                    )
                )
            done = rows[-n_trials:]
            n_ok = sum(1 for row in done if is_success(row))
            n_flag = sum(1 for row in done if str(row["flags"]).strip() != "")
            condition = "noise-free" if noise_free else f"{snr:.0f} dB"
            print(
                f"  {carrier / 1000.0:.0f} kHz  {condition:<12} {n_ok}/{n_trials} succeeded, {n_flag} flagged",
                flush=True,
            )
    return rows


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


def print_summary(summary: list[dict[str, Any]], title: str) -> None:
    print()
    print(title)
    print("Localization columns use successful solves. TDOA columns use every finite pair.")
    print(
        f"{'SNR':<12}{'Carrier':>10}{'Mean (m)':>12}{'Median (m)':>12}"
        f"{'95th % (m)':>12}{'RMSE (m)':>12}{'Med |TDOA| us':>16}{'Success':>10}"
    )
    for row in summary:
        carrier = f"{float(row['carrier_frequency_hz']) / 1000.0:.0f} kHz"
        print(
            f"{_snr_label(row):<12}{carrier:>10}"
            f"{_fmt_number(float(row['mean_localization_error_m']), 12, 3)}"
            f"{_fmt_number(float(row['median_localization_error_m']), 12, 3)}"
            f"{_fmt_number(float(row['p95_localization_error_m']), 12, 3)}"
            f"{_fmt_number(float(row['rmse_localization_error_m']), 12, 3)}"
            f"{_fmt_number(float(row['median_abs_tdoa_error_us']), 16, 3)}"
            f"{_fmt_percent(float(row['localization_success_rate']), 10)}"
        )


def print_flags(rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    non_finite = 0
    for row in rows:
        for value in (
            row["localization_error_m"],
            row["est_tdoa_h1_us"],
            row["est_x_m"],
            row["angular_error_deg"],
        ):
            if row["success"] and not np.isfinite(float(value)):
                non_finite += 1
                break
        for flag in str(row["flags"]).split(";"):
            if flag:
                counts[flag] = counts.get(flag, 0) + 1
    print()
    if not counts and non_finite == 0:
        print("Sanity flags: none")
        return
    print("Sanity flags:")
    for name in sorted(counts):
        print(f"  {name:<32} {counts[name]}")
    if non_finite:
        print(f"  {'non_finite_success_fields':<32} {non_finite}")


def _write_manifest(config: dict[str, Any], n_rows: int, n_frequency: int, elapsed_s: float) -> None:
    manifest = {
        "label": "SIMULATION",
        "geometry": str(config["geometry"]),
        "sample_rate_hz": float(config["sample_rate_hz"]),
        "carrier_frequency_hz": float(config["carrier_frequency_hz"]),
        "pulse_duration_s": float(config["pulse_duration_s"]),
        "apply_attenuation": bool(config["apply_attenuation"]),
        "n_trials": int(config["n_trials"]),
        "n_frequency_trials": int(config["n_frequency_trials"]),
        "comparison_frequencies_hz": [float(value) for value in config["comparison_frequencies_hz"]],
        "snr_levels_db": [float(value) for value in config["snr_levels_db"]],
        "include_noise_free": bool(config["include_noise_free"]),
        "random_seed": int(config["random_seed"]),
        "source_table": str(SOURCE_CSV.relative_to(PROJECT_ROOT)),
        "n_rows": int(n_rows),
        "n_frequency_rows": int(n_frequency),
        "elapsed_s": round(float(elapsed_s), 3),
        "tdoa_method": "GCC-PHAT, existing src.tdoa.estimate_tdoas, search limited to baseline/c",
        "fractional_delay": "linear interpolation in src.simulation.delay_signal",
    }
    path = RESULTS_DIR / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def run_experiment(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    array = get_geometry(str(config["geometry"]))
    if array.expected_class != "volumetric":
        raise RuntimeError(f"{array.key} is {array.expected_class}; waveform localization needs a volumetric array")
    n_trials = int(config["n_trials"])
    n_frequency = int(config["n_frequency_trials"])
    source_ids, sources = load_sources(max(n_trials, n_frequency))
    started = time.perf_counter()
    main_rows = _run_grid(
        config,
        array,
        source_ids[:n_trials],
        sources[:n_trials],
        [float(config["carrier_frequency_hz"])],
        _conditions(config),
        "40 kHz waveform study",
    )
    freq_conditions: list[tuple[bool, float]] = []
    if bool(config["frequency_include_noise_free"]):
        freq_conditions.append((True, float("nan")))
    freq_conditions.append((False, float(config["frequency_snr_db"])))
    frequency_rows = _run_grid(
        config,
        array,
        source_ids[:n_frequency],
        sources[:n_frequency],
        [float(value) for value in config["comparison_frequencies_hz"]],
        freq_conditions,
        "Carrier comparison",
    )
    elapsed = time.perf_counter() - started
    return main_rows, frequency_rows, elapsed


def _example(config: dict[str, Any]) -> dict[str, Any]:
    array = get_geometry(str(config["geometry"]))
    return representative_capture(
        array,
        np.asarray(config["representative_source_m"], dtype=float),
        config,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Pulsed-pinger waveform localization experiment")
    parser.add_argument("--plots-only", action="store_true")
    parser.add_argument("--trials", type=int, default=None, help="Override the 40 kHz trial count")
    parser.add_argument(
        "--frequency-trials",
        type=int,
        default=None,
        help="Override the per-frequency trial count",
    )
    args = parser.parse_args()
    config = load_config()

    if args.plots_only:
        rows = read_csv(RESULTS_CSV)
        summary = summarize_results(rows)
        frequency_summary = summarize_results(read_csv(FREQUENCY_CSV)) if FREQUENCY_CSV.is_file() else None
        write_csv(SUMMARY_CSV, SUMMARY_FIELDS, summary)
        paths = save_waveform_figures(
            rows,
            summary,
            _example(config),
            FIGURES_DIR,
            [float(value) for value in config["snr_levels_db"]],
            frequency_summary,
        )
        print_summary(summary, "40 kHz waveform experiment")
        for path in paths:
            print(f"saved plot  : {path.relative_to(PROJECT_ROOT)}")
        return

    if args.trials is not None:
        if args.trials < 1:
            raise RuntimeError("--trials must be at least 1")
        config["n_trials"] = int(args.trials)
    if args.frequency_trials is not None:
        if args.frequency_trials < 1:
            raise RuntimeError("--frequency-trials must be at least 1")
        config["n_frequency_trials"] = int(args.frequency_trials)

    main_rows, frequency_rows, elapsed = run_experiment(config)
    summary = summarize_results(main_rows)
    frequency_summary = summarize_results(frequency_rows)
    write_csv(RESULTS_CSV, RESULT_FIELDS, main_rows)
    write_csv(SUMMARY_CSV, SUMMARY_FIELDS, summary)
    write_csv(FREQUENCY_CSV, RESULT_FIELDS, frequency_rows)
    write_csv(FREQUENCY_SUMMARY_CSV, SUMMARY_FIELDS, frequency_summary)
    _write_manifest(config, len(main_rows), len(frequency_rows), elapsed)
    paths = save_waveform_figures(
        main_rows,
        summary,
        _example(config),
        FIGURES_DIR,
        [float(value) for value in config["snr_levels_db"]],
        frequency_summary,
    )
    print_summary(summary, "40 kHz waveform experiment")
    print_summary(frequency_summary, "Carrier-frequency comparison")
    print_flags(main_rows + frequency_rows)
    print()
    print(f"elapsed     : {elapsed:.1f} s")
    print(f"saved CSV   : {RESULTS_CSV.relative_to(PROJECT_ROOT)}")
    print(f"saved CSV   : {SUMMARY_CSV.relative_to(PROJECT_ROOT)}")
    print(f"saved CSV   : {FREQUENCY_CSV.relative_to(PROJECT_ROOT)}")
    print(f"saved CSV   : {FREQUENCY_SUMMARY_CSV.relative_to(PROJECT_ROOT)}")
    for path in paths:
        print(f"saved plot  : {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
