"""Run the 4 vs 5 vs 6 hydrophone simulation.

Results are written only under ``simulations/hydrophone_count_study/``.
The geometry-study CSVs are read and not modified.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.hydrophone_count_study.analysis import (
    comparison_rows,
    read_results,
    summary_rows,
    write_csv,
)
from simulations.hydrophone_count_study.figures import make_all
from simulations.hydrophone_count_study.pipeline import (
    load_source_positions,
    noise_std_for_snr,
    prepare_reference_waveform,
    run_count_trial,
)
from src.hydrophone_counts import list_count_arrays, reference_tdoa_count, unordered_pair_count

STUDY = Path(__file__).resolve().parent
RESULTS = STUDY / "results"
CONFIG_PATH = STUDY / "configs" / "experiment.json"


def _csv_value(value):
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not np.isfinite(number):
            return "nan"
        return f"{number:.10g}"
    return value


def _write_trials(path: Path, rows: list[dict]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row[key]) for key in fieldnames})


def _coordinate_rows(arrays) -> list[dict]:
    rows = []
    for array in arrays:
        for index, xyz in enumerate(array.coordinates_m):
            rows.append(
                {
                    "sensor_count": array.sensor_count,
                    "configuration": array.key,
                    "configuration_name": array.name,
                    "channel": f"H{index}",
                    "x_m": float(xyz[0]),
                    "y_m": float(xyz[1]),
                    "z_m": float(xyz[2]),
                    "max_pairwise_baseline_m": array.max_pairwise_distance_m(),
                    "max_physical_tdoa_us": array.max_physical_tdoa_s() * 1e6,
                    "reference_tdoa_count": reference_tdoa_count(array.sensor_count),
                    "unordered_pair_count": unordered_pair_count(array.sensor_count),
                }
            )
    return rows


def write_summaries(rows: list[dict], settings: dict, arrays, source_path: Path, source_bytes: bytes, elapsed_s: float) -> None:
    snrs = [float(value) for value in settings["snr_levels_db"]]
    fs = float(settings["sample_rate_hz"])
    sound_speed = float(settings["sound_speed_mps"])
    summary = summary_rows(rows)
    comparisons = comparison_rows(summary, snr=float(settings["primary_comparison_snr_db"]))
    write_csv(RESULTS / "hydrophone_count_summary.csv", summary)
    write_csv(RESULTS / "count_comparison_summary.csv", comparisons)
    write_csv(RESULTS / "hydrophone_coordinates.csv", _coordinate_rows(arrays))
    manifest = {
        "label": "SIMULATION",
        "study": "hydrophone_count_study",
        "description": settings["description"],
        "source_count": len({int(float(row["source_id"])) for row in rows}),
        "source_positions_csv": settings["source_positions_csv"],
        "source_positions_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "sensor_counts": [array.sensor_count for array in arrays],
        "configurations": [array.key for array in arrays],
        "snr_levels_db": snrs,
        "total_trials": len(rows),
        "random_seed_rule": "1_000_000 + source_id * 100 + round(snr_db * 10); noise is the leading rows of a 6-channel draw",
        "sound_speed_mps": sound_speed,
        "sample_rate_hz": fs,
        "sample_period_us": 1e6 / fs,
        "metres_per_sample": sound_speed / fs,
        "noise_draw_channels": int(settings["noise_draw_channels"]),
        "dc_offsets": settings["dc_offsets"],
        "baselines_m": {array.key: array.max_pairwise_distance_m() for array in arrays},
        "max_physical_tdoa_us": {
            array.key: array.max_physical_tdoa_s(sound_speed) * 1e6 for array in arrays
        },
        "reference_tdoa_counts": {
            str(array.sensor_count): reference_tdoa_count(array.sensor_count) for array in arrays
        },
        "unordered_pair_counts": {
            str(array.sensor_count): unordered_pair_count(array.sensor_count) for array in arrays
        },
        "elapsed_s": elapsed_s,
        "hardware_validation": False,
    }
    # source_count above used a set of ids across all rows, which is correct.
    (RESULTS / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    make_all(rows)


def main() -> None:
    settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    source_path = PROJECT_ROOT / settings["source_positions_csv"]
    source_bytes = source_path.read_bytes()
    sources = load_source_positions(source_path)
    arrays = list_count_arrays()
    snrs = [float(value) for value in settings["snr_levels_db"]]
    fs = float(settings["sample_rate_hz"])
    sound_speed = float(settings["sound_speed_mps"])
    expected = len(sources) * len(snrs) * len(arrays)
    print(
        f"hydrophone-count study: {len(sources)} sources x {len(snrs)} SNRs x {len(arrays)} arrays = {expected} trials",
        flush=True,
    )
    for array in arrays:
        print(
            f"  {array.name}: max baseline {array.max_pairwise_distance_m():.6f} m, "
            f"max TDOA {array.max_physical_tdoa_s(sound_speed) * 1e6:.6f} us, "
            f"reference TDOAs {reference_tdoa_count(array.sensor_count)}, "
            f"unordered pairs {unordered_pair_count(array.sensor_count)}",
            flush=True,
        )

    _chirp, reference = prepare_reference_waveform(
        fs,
        float(settings["capture_duration_s"]),
        float(settings["event_time_s"]),
    )
    noise_std = {snr: noise_std_for_snr(snr, fs) for snr in snrs}
    started = time.perf_counter()
    rows: list[dict] = []
    completed = 0
    for array in arrays:
        for source in sources:
            source_m = np.array([source["x_m"], source["y_m"], source["z_m"]], dtype=float)
            for snr in snrs:
                rows.append(
                    run_count_trial(
                        array,
                        source_m,
                        int(source["source_id"]),
                        snr,
                        reference,
                        fs,
                        sound_speed,
                        noise_std[snr],
                        settings,
                    )
                )
                completed += 1
            if int(source["source_id"]) % 25 == 24 or int(source["source_id"]) == sources[-1]["source_id"]:
                elapsed = time.perf_counter() - started
                print(
                    f"  {array.sensor_count} hydrophones, source {source['source_id']}, "
                    f"{completed}/{expected} trials, {elapsed:.1f} s",
                    flush=True,
                )
        _write_trials(RESULTS / "experiment_results.csv", rows)

    if len(rows) != expected:
        raise SystemExit(f"expected {expected} trials, wrote {len(rows)}")
    elapsed = time.perf_counter() - started
    print(f"trial loop finished in {elapsed:.1f} s", flush=True)
    write_summaries(rows, settings, arrays, source_path, source_bytes, elapsed)
    print(f"figures finished, total {time.perf_counter() - started:.1f} s", flush=True)


if __name__ == "__main__":
    main()
