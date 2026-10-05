"""Run the Change #2 waveform study for one volumetric geometry.

From the project root:

    python simulations/geometry_pair/run_change2.py --geometry tetrahedral
    python simulations/geometry_pair/run_change2.py --geometry three_plus_one

The solver receives GCC-PHAT delays, not geometric travel times. Output goes
to ``results/<geometry>/change_2_waveform/``. The original files in
``simulations/waveform_study/results/`` are not modified.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_pair.directions import DIRECTION_FIELDS, directional_summary
from simulations.geometry_pair.manifest import base_manifest, write_manifest
from simulations.geometry_pair.paths import assert_rows_match_geometry, result_dir
from simulations.geometry_pair.tables import write_table
from simulations.waveform_study.analysis import RESULT_FIELDS, SUMMARY_FIELDS, summarize_results
from simulations.waveform_study.figures import save_waveform_figures
from simulations.waveform_study.pipeline import representative_capture
from simulations.waveform_study.run_waveform_experiment import (
    SOURCE_CSV,
    load_config,
    load_sources,
    print_flags,
    print_summary,
    run_experiment,
    write_csv,
)
from src.geometry import SOUND_SPEED_MPS, get_geometry
from src.tdoa import DEFAULT_SOUND_SPEED_MPS


def main() -> None:
    parser = argparse.ArgumentParser(description="Change #2 waveform study for one geometry")
    parser.add_argument("--geometry", required=True, choices=("tetrahedral", "three_plus_one"))
    parser.add_argument("--trials", type=int, default=None, help="Override the 40 kHz trial count")
    parser.add_argument("--frequency-trials", type=int, default=None)
    args = parser.parse_args()
    if args.trials is not None and args.trials < 1:
        raise RuntimeError("--trials must be at least 1")
    if args.frequency_trials is not None and args.frequency_trials < 1:
        raise RuntimeError("--frequency-trials must be at least 1")

    geometry = str(args.geometry)
    destination = result_dir(geometry, "change_2_waveform")
    config = load_config()
    config["geometry"] = geometry
    if args.trials is not None:
        config["n_trials"] = int(args.trials)
    if args.frequency_trials is not None:
        config["n_frequency_trials"] = int(args.frequency_trials)

    main_rows, frequency_rows, elapsed = run_experiment(config)
    assert_rows_match_geometry(main_rows, geometry)
    assert_rows_match_geometry(frequency_rows, geometry)
    summary = summarize_results(main_rows)
    frequency_summary = summarize_results(frequency_rows)
    write_csv(destination / "waveform_experiment_results.csv", RESULT_FIELDS, main_rows)
    write_csv(destination / "waveform_experiment_summary.csv", SUMMARY_FIELDS, summary)
    write_csv(destination / "waveform_frequency_comparison.csv", RESULT_FIELDS, frequency_rows)
    write_csv(destination / "waveform_frequency_summary.csv", SUMMARY_FIELDS, frequency_summary)

    source_ids, sources = load_sources(int(config["n_trials"]))
    _write_sources(destination / "source_positions.csv", source_ids, sources)

    array = get_geometry(geometry)
    directions = directional_summary(main_rows, geometry, "change_2_waveform", array.center_m)
    write_table(destination / "directional_performance.csv", DIRECTION_FIELDS, directions)

    example = representative_capture(
        array,
        np.asarray(config["representative_source_m"], dtype=float),
        config,
    )
    example["geometry_name"] = geometry
    plots = save_waveform_figures(
        main_rows,
        summary,
        example,
        destination / "plots",
        [float(value) for value in config["snr_levels_db"]],
        frequency_summary,
    )
    manifest = base_manifest(
        array,
        study="change_2_waveform",
        n_trials=int(config["n_trials"]),
        random_seed=int(config["random_seed"]),
        snr_levels_db=[float(value) for value in config["snr_levels_db"]],
        include_noise_free=bool(config["include_noise_free"]),
        source_position_dataset=(
            f"{SOURCE_CSV.relative_to(PROJECT_ROOT)} first {int(config['n_trials'])} rows. "
            "The same rows are used for every geometry. "
            f"Frequency comparison uses the first {int(config['n_frequency_trials'])} rows."
        ),
        n_rows=len(main_rows),
        elapsed_s=elapsed,
    )
    manifest.update(
        {
            "carrier_frequency_hz": float(config["carrier_frequency_hz"]),
            "comparison_frequencies_hz": [float(value) for value in config["comparison_frequencies_hz"]],
            "pulse_duration_s": float(config["pulse_duration_s"]),
            "sampling_rate_hz": float(config["sample_rate_hz"]),
            "TDOA_method": "GCC-PHAT, existing src.tdoa.estimate_tdoas, search limited to baseline/c",
            "speed_of_sound_mps": float(SOUND_SPEED_MPS),
            "fractional_delay": "linear interpolation in src.simulation.delay_signal",
            "apply_attenuation": bool(config["apply_attenuation"]),
            "n_frequency_trials": int(config["n_frequency_trials"]),
            "n_frequency_rows": len(frequency_rows),
        }
    )
    if float(SOUND_SPEED_MPS) != float(DEFAULT_SOUND_SPEED_MPS):
        raise RuntimeError("geometry and TDOA sound speeds disagree")
    write_manifest(destination / "run_manifest.json", manifest)
    print_summary(summary, f"40 kHz waveform experiment - {geometry}")
    print_summary(frequency_summary, f"Carrier-frequency comparison - {geometry}")
    print_flags(main_rows + frequency_rows)
    print()
    print(f"elapsed     : {elapsed:.1f} s")
    print(f"saved       : {destination.relative_to(PROJECT_ROOT)}")
    for path in plots:
        print(f"saved plot  : {path.relative_to(PROJECT_ROOT)}")


def _write_sources(path: Path, source_ids: np.ndarray, sources: np.ndarray) -> None:
    rows = []
    for source_id, xyz in zip(source_ids, sources):
        rows.append(
            {
                "source_id": int(source_id),
                "x_m": float(xyz[0]),
                "y_m": float(xyz[1]),
                "z_m": float(xyz[2]),
            }
        )
    write_csv(path, ["source_id", "x_m", "y_m", "z_m"], rows)


if __name__ == "__main__":
    main()
