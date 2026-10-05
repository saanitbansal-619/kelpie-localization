"""Compare tetrahedral and 3+1 results. Does not rerun the trials.

From the project root, after both geometries have been run:

    python simulations/geometry_pair/compare.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_pair.directions import CARDINALS, DIRECTION_FIELDS
from simulations.geometry_pair.figures import save_comparison_figures
from simulations.geometry_pair.paths import COMPARISON_DIR, GEOMETRIES, result_dir
from simulations.geometry_pair.tables import read_table, write_table
from simulations.noise_study.run_noise_experiment import read_csv as read_noise_csv
from simulations.waveform_study.run_waveform_experiment import read_csv as read_waveform_csv

COMPARISON_FIELDS = [
    "study",
    "geometry",
    "snr_db",
    "noise_free",
    "carrier_frequency_hz",
    "n_trials",
    "n_successful",
    "mean_localization_error_m",
    "median_localization_error_m",
    "rmse_localization_error_m",
    "p95_localization_error_m",
    "median_angular_error_deg",
    "mean_abs_tdoa_error_us",
    "localization_success_rate",
]

HUGE_ERROR_M = 20.0
DISPLAY = {"tetrahedral": "Tetrahedral", "three_plus_one": "3+1"}


def main() -> None:
    change1 = []
    change2 = []
    frequency = []
    directions = []
    for geometry in GEOMETRIES:
        noise_dir = result_dir(geometry, "change_1_noise")
        wave_dir = result_dir(geometry, "change_2_waveform")
        _require(noise_dir / "noise_experiment_summary.csv")
        _require(wave_dir / "waveform_experiment_summary.csv")
        _require(noise_dir / "source_positions.csv")
        _require(wave_dir / "source_positions.csv")
        change1.extend(_tagged(read_noise_csv(noise_dir / "noise_experiment_summary.csv"), geometry, "change_1"))
        change2.extend(
            _tagged(read_waveform_csv(wave_dir / "waveform_experiment_summary.csv"), geometry, "change_2")
        )
        frequency.extend(
            _tagged(
                read_waveform_csv(wave_dir / "waveform_frequency_summary.csv"),
                geometry,
                "change_2_frequency",
            )
        )
        directions.extend(read_table(noise_dir / "directional_performance.csv"))
        directions.extend(read_table(wave_dir / "directional_performance.csv"))
        _assert_sources_match(
            noise_dir / "source_positions.csv",
            result_dir("tetrahedral", "change_1_noise") / "source_positions.csv",
            read_noise_csv,
            "Change #1",
        )
        _assert_sources_match(
            wave_dir / "source_positions.csv",
            result_dir("tetrahedral", "change_2_waveform") / "source_positions.csv",
            read_waveform_csv,
            "Change #2",
        )

    rows = [_comparison_row(row) for row in change1 + change2 + frequency]
    write_table(COMPARISON_DIR / "geometry_comparison_summary.csv", COMPARISON_FIELDS, rows)
    write_table(COMPARISON_DIR / "directional_performance.csv", DIRECTION_FIELDS, directions)
    plots = save_comparison_figures(change1, change2, directions, COMPARISON_DIR / "plots")
    _confirm_preserved_tetrahedral(change1, change2)
    _print_report(change1, change2, directions)
    _print_failures()
    print()
    print(f"saved       : {(COMPARISON_DIR / 'geometry_comparison_summary.csv').relative_to(PROJECT_ROOT)}")
    for path in plots:
        print(f"saved plot  : {path.relative_to(PROJECT_ROOT)}")


def _require(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing {path}. Run the geometry-specific experiment before comparing.")


def _tagged(rows: list[dict[str, Any]], geometry: str, study: str) -> list[dict[str, Any]]:
    tagged = []
    for row in rows:
        recorded = str(row.get("hydrophone_configuration", "")).strip()
        if recorded and recorded != geometry:
            raise RuntimeError(f"{geometry} summary contains {recorded} rows")
        copied = dict(row)
        copied["geometry"] = geometry
        copied["study"] = study
        tagged.append(copied)
    return tagged


def _comparison_row(row: dict[str, Any]) -> dict[str, Any]:
    noise_free = row["noise_free"]
    if isinstance(noise_free, str):
        noise_free_text = "true" if noise_free.strip().lower() == "true" else "false"
    else:
        noise_free_text = "true" if noise_free else "false"
    return {
        "study": row["study"],
        "geometry": row["geometry"],
        "snr_db": row.get("snr_db", float("nan")),
        "noise_free": noise_free_text,
        "carrier_frequency_hz": row.get("carrier_frequency_hz", float("nan")),
        "n_trials": row.get("n_trials", 0),
        "n_successful": row.get("n_successful", 0),
        "mean_localization_error_m": row.get("mean_localization_error_m", float("nan")),
        "median_localization_error_m": row.get("median_localization_error_m", float("nan")),
        "rmse_localization_error_m": row.get("rmse_localization_error_m", float("nan")),
        "p95_localization_error_m": row.get("p95_localization_error_m", float("nan")),
        "median_angular_error_deg": row.get("median_angular_error_deg", float("nan")),
        "mean_abs_tdoa_error_us": row.get("mean_abs_tdoa_error_us", float("nan")),
        "localization_success_rate": row.get("localization_success_rate", float("nan")),
    }


def _assert_sources_match(path: Path, reference: Path, reader, label: str) -> None:
    left = _xyz(reader(path))
    right = _xyz(reader(reference))
    if left.shape != right.shape or not np.allclose(left, right):
        raise RuntimeError(f"{label} source positions differ between geometries")


def _xyz(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.array([[float(row["x_m"]), float(row["y_m"]), float(row["z_m"])] for row in rows], dtype=float)


def _confirm_preserved_tetrahedral(change1: list[dict[str, Any]], change2: list[dict[str, Any]]) -> None:
    """The new tetrahedral run must reproduce the original result tables."""
    legacy_noise = read_noise_csv(
        PROJECT_ROOT / "simulations" / "noise_study" / "results" / "noise_experiment_summary.csv"
    )
    legacy_wave = read_waveform_csv(
        PROJECT_ROOT / "simulations" / "waveform_study" / "results" / "waveform_experiment_summary.csv"
    )
    fresh_noise = [row for row in change1 if row["geometry"] == "tetrahedral"]
    fresh_wave = [row for row in change2 if row["geometry"] == "tetrahedral"]
    _same_metric(legacy_noise, fresh_noise, "median_localization_error_m", "preserved Change #1 tetrahedral summary")
    _same_metric(legacy_wave, fresh_wave, "median_localization_error_m", "preserved Change #2 tetrahedral summary")
    print("Preserved tetrahedral summaries match the new tetrahedral runs.")


def _same_metric(legacy: list[dict[str, Any]], fresh: list[dict[str, Any]], key: str, label: str) -> None:
    if len(legacy) != len(fresh):
        raise RuntimeError(f"{label} has a different number of rows")
    for old, new in zip(legacy, fresh):
        if not np.isclose(float(old[key]), float(new[key]), rtol=1e-6, atol=1e-9, equal_nan=True):
            raise RuntimeError(f"{label} disagrees on {key}")


def _print_report(
    change1: list[dict[str, Any]],
    change2: list[dict[str, Any]],
    directions: list[dict[str, Any]],
) -> None:
    print()
    print("=" * 78)
    print("GEOMETRY COMPARISON")
    print("=" * 78)
    print("No overall winner is assigned. Gaps under 10% are marked similar.")
    _print_study("Change #1 - noise robustness", change1, include_tdoa=False)
    _print_study("Change #2 - 40 kHz waveform TDOA", change2, include_tdoa=True)
    print()
    print("Direction labels use the pooled trials. A hyphenated name is diagonal.")
    for study, title in (
        ("change_1_noise", "Change #1 directions"),
        ("change_2_waveform", "Change #2 directions"),
    ):
        print()
        print(title)
        for direction in CARDINALS:
            print(f"  {direction:<8} {_direction_line(directions, study, direction)}")


def _print_study(title: str, rows: list[dict[str, Any]], include_tdoa: bool) -> None:
    print()
    print(title)
    labels = []
    if any(_noise_free(row) for row in rows):
        labels.append("noise-free")
    levels = sorted(
        {float(row["snr_db"]) for row in rows if not _noise_free(row)},
        reverse=True,
    )
    labels.extend(f"{level:.0f} dB" for level in levels)
    header = (
        f"{'SNR':<12}{'Median Tetra':>14}{'Median 3+1':>12}"
        f"{'95th Tetra':>12}{'95th 3+1':>12}"
        f"{'Angle Tetra':>12}{'Angle 3+1':>12}"
        f"{'Success Tetra':>14}{'Success 3+1':>13}"
    )
    if include_tdoa:
        header += f"{'TDOA Tetra':>12}{'TDOA 3+1':>10}"
    print(header)
    for label in labels:
        tetra = _at(rows, "tetrahedral", label)
        three = _at(rows, "three_plus_one", label)
        line = (
            f"{label:<12}"
            f"{_num(tetra, 'median_localization_error_m', 14, 3)}"
            f"{_num(three, 'median_localization_error_m', 12, 3)}"
            f"{_num(tetra, 'p95_localization_error_m', 12, 3)}"
            f"{_num(three, 'p95_localization_error_m', 12, 3)}"
            f"{_num(tetra, 'median_angular_error_deg', 12, 3)}"
            f"{_num(three, 'median_angular_error_deg', 12, 3)}"
            f"{_pct(tetra, 14)}"
            f"{_pct(three, 13)}"
        )
        if include_tdoa:
            line += (
                f"{_num(tetra, 'mean_abs_tdoa_error_us', 12, 3)}"
                f"{_num(three, 'mean_abs_tdoa_error_us', 10, 3)}"
            )
        print(line)
    for label in ("noise-free", "0 dB"):
        if label not in labels:
            continue
        print()
        print(f"{title} at {label}")
        _print_snapshot(_at(rows, "tetrahedral", label), _at(rows, "three_plus_one", label), include_tdoa)


def _print_snapshot(tetra: dict[str, Any] | None, three: dict[str, Any] | None, include_tdoa: bool) -> None:
    print(f"{'':<24}{'Tetrahedral':>16}{'3+1':>12}")
    _snapshot_line("Median error (m)", tetra, three, "median_localization_error_m")
    _snapshot_line("Mean error (m)", tetra, three, "mean_localization_error_m")
    _snapshot_line("RMSE (m)", tetra, three, "rmse_localization_error_m")
    _snapshot_line("95th percentile (m)", tetra, three, "p95_localization_error_m")
    _snapshot_line("Median angular (deg)", tetra, three, "median_angular_error_deg")
    if include_tdoa:
        _snapshot_line("Mean |TDOA| (us)", tetra, three, "mean_abs_tdoa_error_us")
    print(
        f"{'Success rate':<24}"
        f"{_pct(tetra, 16)}{_pct(three, 12)}"
    )


def _snapshot_line(name: str, tetra: dict[str, Any] | None, three: dict[str, Any] | None, key: str) -> None:
    print(f"{name:<24}{_num(tetra, key, 16, 3)}{_num(three, key, 12, 3)}")


def _direction_line(rows: list[dict[str, Any]], study: str, direction: str) -> str:
    pair = {}
    for geometry in GEOMETRIES:
        match = [
            row
            for row in rows
            if row["study"] == study
            and row["snr_scope"] == "all"
            and row["direction"] == direction
            and row["geometry"] == geometry
        ]
        pair[geometry] = match[0] if match else None
    tetra = pair["tetrahedral"]
    three = pair["three_plus_one"]
    if tetra is None or three is None:
        return "no sources in this bin"
    n_sources = min(int(tetra["n_sources"]), int(three["n_sources"]))
    if n_sources < 5:
        return f"too few sources (n={n_sources})"
    left = float(tetra["median_localization_error"])
    right = float(three["median_localization_error"])
    detail = (
        f"tetrahedral {left:.3f} m, 3+1 {right:.3f} m, "
        f"n={n_sources} sources, success {100 * float(tetra['success_rate']):.0f}% / "
        f"{100 * float(three['success_rate']):.0f}%"
    )
    if not np.isfinite(left) or not np.isfinite(right) or max(left, right) == 0.0:
        return detail
    if abs(left - right) / max(left, right) < 0.10:
        return f"similar ({detail})"
    lower = "tetrahedral" if left < right else "3+1"
    return f"lower median: {lower} ({detail})"


def _print_failures() -> None:
    print()
    print("Catastrophic or rejected solves")
    for geometry in GEOMETRIES:
        noise_rows = read_noise_csv(result_dir(geometry, "change_1_noise") / "noise_experiment_results.csv")
        wave_rows = read_waveform_csv(
            result_dir(geometry, "change_2_waveform") / "waveform_experiment_results.csv"
        )
        print(f"  {DISPLAY[geometry]} Change #1: {_failure_text(noise_rows)}")
        print(f"  {DISPLAY[geometry]} Change #2: {_failure_text(wave_rows)}")


def _failure_text(rows: list[dict[str, Any]]) -> str:
    failures = [row for row in rows if not _success(row)]
    huge = [
        row
        for row in rows
        if _success(row) and np.isfinite(float(row["localization_error_m"])) and float(row["localization_error_m"]) > HUGE_ERROR_M
    ]
    reasons: dict[str, int] = {}
    for row in failures:
        reason = str(row.get("failure_reason", "")).strip() or "unspecified"
        reasons[reason] = reasons.get(reason, 0) + 1
    reason_text = ", ".join(f"{name} {count}" for name, count in sorted(reasons.items())) or "none"
    largest = max(
        (
            float(row["localization_error_m"])
            for row in rows
            if _success(row) and np.isfinite(float(row["localization_error_m"]))
        ),
        default=float("nan"),
    )
    largest_text = f"{largest:.1f} m" if np.isfinite(largest) else "n/a"
    return f"{len(failures)} rejected ({reason_text}); {len(huge)} accepted errors above {HUGE_ERROR_M:.0f} m; largest accepted {largest_text}"


def _at(rows: list[dict[str, Any]], geometry: str, label: str) -> dict[str, Any] | None:
    for row in rows:
        if row["geometry"] != geometry:
            continue
        if label == "noise-free" and _noise_free(row):
            return row
        if label != "noise-free" and not _noise_free(row) and f"{float(row['snr_db']):.0f} dB" == label:
            return row
    return None


def _noise_free(row: dict[str, Any]) -> bool:
    value = row["noise_free"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _success(row: dict[str, Any]) -> bool:
    value = row["success"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _num(row: dict[str, Any] | None, key: str, width: int, digits: int) -> str:
    if row is None or not np.isfinite(float(row.get(key, float("nan")))):
        return f"{'n/a':>{width}}"
    return f"{float(row[key]):{width}.{digits}f}"


def _pct(row: dict[str, Any] | None, width: int) -> str:
    if row is None or not np.isfinite(float(row.get("localization_success_rate", float("nan")))):
        return f"{'n/a':>{width}}"
    return f"{100.0 * float(row['localization_success_rate']):{width}.1f}%"


if __name__ == "__main__":
    main()
