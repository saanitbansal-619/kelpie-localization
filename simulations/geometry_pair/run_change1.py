"""Run the Change #1 noise study for one volumetric geometry.

From the project root:

    python simulations/geometry_pair/run_change1.py --geometry tetrahedral
    python simulations/geometry_pair/run_change1.py --geometry three_plus_one

Writes ``results/<geometry>/change_1_noise/``. The original files in
``simulations/noise_study/results/`` are not modified.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_pair.directions import DIRECTION_FIELDS, directional_summary
from simulations.geometry_pair.manifest import base_manifest, write_manifest
from simulations.geometry_pair.paths import assert_rows_match_geometry, result_dir
from simulations.geometry_pair.tables import write_table
from simulations.noise_study.analysis import RESULT_FIELDS, SUMMARY_FIELDS
from simulations.noise_study.figures import save_noise_figures
from simulations.noise_study.run_noise_experiment import load_config, print_summary, run_experiment, write_csv
from src.geometry import get_geometry

SOURCE_DATASET = (
    "generate_source_positions, seed 20261004, 100 sources, "
    "range 2–8 m, elevation −50° to 50°, azimuth 0–360°. "
    "The draw does not depend on geometry."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Change #1 noise study for one geometry")
    parser.add_argument("--geometry", required=True, choices=("tetrahedral", "three_plus_one"))
    parser.add_argument("--trials", type=int, default=None, help="Override trials per SNR")
    args = parser.parse_args()
    if args.trials is not None and args.trials < 1:
        raise RuntimeError("--trials must be at least 1")

    geometry = str(args.geometry)
    destination = result_dir(geometry, "change_1_noise")
    config = load_config()
    config["geometry"] = geometry
    if args.trials is not None:
        config["n_trials"] = int(args.trials)

    rows, summary, elapsed = run_experiment(config, results_dir=destination)
    assert_rows_match_geometry(rows, geometry)
    write_csv(destination / "noise_experiment_results.csv", RESULT_FIELDS, rows)
    write_csv(destination / "noise_experiment_summary.csv", SUMMARY_FIELDS, summary)

    array = get_geometry(geometry)
    directions = directional_summary(rows, geometry, "change_1_noise", array.center_m)
    write_table(destination / "directional_performance.csv", DIRECTION_FIELDS, directions)
    plots = save_noise_figures(
        rows,
        summary,
        destination / "plots",
        [float(value) for value in config["snr_levels_db"]],
    )
    manifest = base_manifest(
        array,
        study="change_1_noise",
        n_trials=int(config["n_trials"]),
        random_seed=int(config["random_seed"]),
        snr_levels_db=[float(value) for value in config["snr_levels_db"]],
        include_noise_free=bool(config["include_noise_free"]),
        source_position_dataset=SOURCE_DATASET,
        n_rows=len(rows),
        elapsed_s=elapsed,
    )
    manifest["noise_model"] = (
        "SNR_dB = 10*log10(P_chirp / P_noise); independent Gaussian noise "
        "on each hydrophone; seed = random_seed + trial_index, shared across SNR and geometry"
    )
    write_manifest(destination / "run_manifest.json", manifest)
    print_summary(summary)
    print()
    print(f"elapsed     : {elapsed:.1f} s")
    print(f"saved       : {destination.relative_to(PROJECT_ROOT)}")
    for path in plots:
        print(f"saved plot  : {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
