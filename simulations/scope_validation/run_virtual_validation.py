"""Synthetic four-channel records through the acquisition localizer.

Run from the repository root:

    python -m simulations.scope_validation.run_virtual_validation

Writes ``results_scope_validation/``. Does not open a VISA resource and does
not read historical result folders.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from acquisition.waveform import load_npz, save_npz
from simulations.scope_validation.paths import OUTPUT_ROOT, output_path
from simulations.scope_validation.pipeline import (
    BANDPASS_HIGH_HZ,
    BANDPASS_LOW_HZ,
    CONTRAST_MINIMUM,
    ENVELOPE_CYCLE_LIMIT,
    VIRTUAL_SAMPLE_RATE_HZ,
    expected_tdoas_s,
    localize_record,
    stated_hydrophones_m,
    synthetic_record,
)
from src.geometry import SOUND_SPEED_MPS, max_pairwise_distance_m, max_pairwise_tdoa_s
from src.localization import angular_error_between_points_deg, array_center_m

BASE_SEED = 20261101
HUGE_ERROR_M = 20.0
SOURCES = (
    (2.0, 1.0, 1.5),
    (3.0, 0.0, 0.5),
    (1.5, -2.0, 1.0),
    (2.5, 1.5, -1.0),
    (-2.0, 0.5, 0.8),
    (4.0, -1.0, 2.0),
)
FREQUENCIES_HZ = (25000.0, 30000.0, 35000.0, 40000.0)
SNR_LEVELS_DB = (None, 20.0, 10.0, 0.0)
STRESS_SOURCE_INDEX = 0
STRESS_FREQUENCY_HZ = 30000.0
STRESS_SNR_DB = (None, 20.0)
STRESS_OFFSETS_SAMPLES = (0.5, 2.0, VIRTUAL_SAMPLE_RATE_HZ / STRESS_FREQUENCY_HZ)

FREQ_COLORS = {
    25000.0: "#0072B2",
    30000.0: "#E69F00",
    35000.0: "#009E73",
    40000.0: "#D55E00",
}


@dataclass(frozen=True)
class Case:
    group: str
    source_index: int
    source_m: tuple[float, float, float]
    frequency_hz: float
    freq_index: int
    snr_db: float | None
    snr_index: int
    offset_channel: int
    offset_samples: float
    offset_index: int

    @property
    def noise_seed(self) -> int:
        return (
            BASE_SEED
            + self.source_index * 1000
            + self.freq_index * 100
            + self.snr_index * 10
            + self.offset_index
        )


def build_cases() -> list[Case]:
    cases: list[Case] = []
    for source_index, source in enumerate(SOURCES):
        for freq_index, frequency in enumerate(FREQUENCIES_HZ):
            for snr_index, snr in enumerate(SNR_LEVELS_DB):
                cases.append(
                    Case(
                        group="geometry",
                        source_index=source_index,
                        source_m=source,
                        frequency_hz=frequency,
                        freq_index=freq_index,
                        snr_db=snr,
                        snr_index=snr_index,
                        offset_channel=1,
                        offset_samples=0.0,
                        offset_index=0,
                    )
                )
    freq_index = FREQUENCIES_HZ.index(STRESS_FREQUENCY_HZ)
    for offset_index, offset in enumerate(STRESS_OFFSETS_SAMPLES, start=1):
        for snr in STRESS_SNR_DB:
            cases.append(
                Case(
                    group="timing_offset",
                    source_index=STRESS_SOURCE_INDEX,
                    source_m=SOURCES[STRESS_SOURCE_INDEX],
                    frequency_hz=STRESS_FREQUENCY_HZ,
                    freq_index=freq_index,
                    snr_db=snr,
                    snr_index=SNR_LEVELS_DB.index(snr),
                    offset_channel=1,
                    offset_samples=float(offset),
                    offset_index=offset_index,
                )
            )
    return cases


def run_case(case: Case) -> dict[str, object]:
    offsets = np.zeros(4, dtype=float)
    if case.offset_samples != 0.0:
        offsets[case.offset_channel] = case.offset_samples
    source = np.array(case.source_m, dtype=float)
    try:
        record = synthetic_record(
            source,
            case.frequency_hz,
            snr_db=case.snr_db,
            noise_seed=case.noise_seed,
            channel_offset_samples=offsets if case.offset_samples != 0.0 else None,
        )
        outcome = localize_record(record, stated_hydrophones_m(), case.frequency_hz)
    except Exception as exc:  # one bad trial should stay in the table
        return _failed_row(case, f"pipeline_exception:{type(exc).__name__}:{exc}")

    expected = expected_tdoas_s(
        source,
        offsets if case.offset_samples != 0.0 else None,
    )
    estimated = np.asarray(outcome.tdoa_s, dtype=float)
    tdoa_error = estimated - expected
    position = np.asarray(outcome.position_m, dtype=float)
    position_error = float("nan")
    angular = float("nan")
    if outcome.solver_success and np.all(np.isfinite(position)):
        position_error = float(np.linalg.norm(position - source))
        angular = angular_error_between_points_deg(
            array_center_m(stated_hydrophones_m()),
            source,
            position,
        )
    flags = list(outcome.flags)
    if outcome.solver_success and np.isfinite(position_error) and position_error > HUGE_ERROR_M:
        flags.append("huge_localization_error")
    return {
        "group": case.group,
        "source_index": case.source_index,
        "source_x_m": source[0],
        "source_y_m": source[1],
        "source_z_m": source[2],
        "frequency_hz": case.frequency_hz,
        "snr_db": "" if case.snr_db is None else case.snr_db,
        "noise_free": case.snr_db is None,
        "offset_channel": case.offset_channel if case.offset_samples else "",
        "offset_samples": case.offset_samples,
        "noise_seed": case.noise_seed,
        "solver_success": outcome.solver_success,
        "reliable": outcome.reliable,
        "failure_reason": outcome.failure_reason,
        "flags": ";".join(flags),
        "position_error_m": position_error,
        "angular_error_deg": angular,
        "residual_rms_us": outcome.residual_rms_s * 1e6,
        "event_index": outcome.event_index,
        "est_x_m": position[0],
        "est_y_m": position[1],
        "est_z_m": position[2],
        **_series("true_tdoa_us", expected * 1e6),
        **_series("est_tdoa_us", estimated * 1e6),
        **_series("tdoa_error_us", tdoa_error * 1e6),
        **_series("sidelobe_ratio", outcome.sidelobe_ratio, start=1),
        **_series("contrast", outcome.correlation_contrast, start=1),
        **_series("envelope_cycles", outcome.envelope_cycles, start=1),
        "_record": record,
    }


def write_outputs(rows: list[dict[str, object]]) -> None:
    root = output_path()
    root.mkdir(parents=True, exist_ok=True)
    figure_dir = output_path("figures")
    figure_dir.mkdir(parents=True, exist_ok=True)

    _write_example_npz(rows)
    csv_rows = [{key: value for key, value in row.items() if not key.startswith("_")} for row in rows]
    _write_csv(output_path("virtual_trials.csv"), csv_rows)
    _write_plots(csv_rows, figure_dir)
    summary = _summary_markdown(csv_rows)
    output_path("summary.md").write_text(summary, encoding="utf-8")
    manifest = {
        "label": "SYNTHETIC",
        "physical_measurement": False,
        "instrument_connected": False,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "random_seed_base": BASE_SEED,
        "seed_formula": "base + source_index*1000 + freq_index*100 + snr_index*10 + offset_index",
        "sample_rate_hz": VIRTUAL_SAMPLE_RATE_HZ,
        "sound_speed_mps": SOUND_SPEED_MPS,
        "hydrophones_m": stated_hydrophones_m().tolist(),
        "bandpass_hz": [BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ],
        "envelope_cycle_limit": ENVELOPE_CYCLE_LIMIT,
        "contrast_minimum": CONTRAST_MINIMUM,
        "huge_localization_error_m": HUGE_ERROR_M,
        "n_trials": len(csv_rows),
        "sources_m": [list(item) for item in SOURCES],
        "frequencies_hz": list(FREQUENCIES_HZ),
        "snr_levels_db": ["noise_free" if item is None else item for item in SNR_LEVELS_DB],
        "timing_offsets_samples_on_h2": list(STRESS_OFFSETS_SAMPLES),
    }
    output_path("run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    cases = build_cases()
    rows = [run_case(case) for case in cases]
    write_outputs(rows)
    geometry = [row for row in rows if row["group"] == "geometry"]
    solved = sum(bool(row["solver_success"]) for row in geometry)
    reliable = sum(bool(row["reliable"]) for row in reliable_rows(geometry))
    print(f"Wrote {OUTPUT_ROOT}")
    print(f"Geometry trials: {len(geometry)}")
    print(f"Solver successes: {solved}")
    print(f"Reliable: {reliable}")


def reliable_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if row["reliable"]]


def _write_example_npz(rows: list[dict[str, object]]) -> None:
    first = next(row for row in rows if row["group"] == "geometry" and "_record" in row)
    path = output_path("example_record.npz")
    save_npz(str(path), first["_record"])
    loaded = load_npz(str(path))
    again = localize_record(loaded, stated_hydrophones_m(), float(first["frequency_hz"]))
    direct = localize_record(first["_record"], stated_hydrophones_m(), float(first["frequency_hz"]))
    if not np.allclose(again.tdoa_s, direct.tdoa_s, rtol=0.0, atol=0.0):
        raise RuntimeError("NPZ round-trip changed the TDOA estimate")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_plots(rows: list[dict[str, object]], figure_dir: Path) -> None:
    geometry = [row for row in rows if row["group"] == "geometry"]
    _plot_error(geometry, figure_dir / "position_error_vs_snr.png")
    _plot_reliability(geometry, figure_dir / "reliability_vs_snr.png")
    _plot_tdoa(geometry, figure_dir / "tdoa_error_vs_snr.png")


def _plot_error(rows: list[dict[str, object]], path: Path) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for frequency in FREQUENCIES_HZ:
        xs = []
        ys = []
        for index, label in enumerate(_snr_labels()):
            chosen = [
                float(row["position_error_m"])
                for row in rows
                if row["frequency_hz"] == frequency
                and _snr_label(row) == label
                and row["solver_success"]
                and np.isfinite(float(row["position_error_m"]))
            ]
            xs.append(index)
            ys.append(float(np.median(chosen)) if chosen else np.nan)
        ax.plot(xs, ys, marker="o", color=FREQ_COLORS[frequency], label=f"{frequency / 1000:.0f} kHz")
    ax.set_xticks(range(len(_snr_labels())), _snr_labels())
    ax.set_yscale("log")
    ax.set_ylabel("Median position error of solver successes (m)")
    ax.set_xlabel("SNR")
    ax.set_title("Synthetic 3+1 localization error")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _plot_reliability(rows: list[dict[str, object]], path: Path) -> None:
    _apply_style()
    labels = _snr_labels()
    solved = []
    reliable = []
    for label in labels:
        chosen = [row for row in rows if _snr_label(row) == label]
        solved.append(100.0 * _rate(chosen, "solver_success"))
        reliable.append(100.0 * _rate(chosen, "reliable"))
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.bar(x - 0.18, solved, width=0.36, color="#0072B2", label="Solver success")
    ax.bar(x + 0.18, reliable, width=0.36, color="#D55E00", label="Reliable")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of geometry trials (%)")
    ax.set_xlabel("SNR")
    ax.set_title("Solver success and reliability flags")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _plot_tdoa(rows: list[dict[str, object]], path: Path) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for frequency in FREQUENCIES_HZ:
        xs = []
        ys = []
        for index, label in enumerate(_snr_labels()):
            errors = []
            for row in rows:
                if row["frequency_hz"] != frequency or _snr_label(row) != label:
                    continue
                if not row["solver_success"]:
                    continue
                pair = [abs(float(row[f"tdoa_error_us_{channel}"])) for channel in (1, 2, 3)]
                if np.all(np.isfinite(pair)):
                    errors.append(float(np.mean(pair)))
            xs.append(index)
            ys.append(float(np.median(errors)) if errors else np.nan)
        ax.plot(xs, ys, marker="o", color=FREQ_COLORS[frequency], label=f"{frequency / 1000:.0f} kHz")
    ax.set_xticks(range(len(_snr_labels())), _snr_labels())
    ax.set_yscale("log")
    ax.set_ylabel("Median mean |TDOA error| (µs)")
    ax.set_xlabel("SNR")
    ax.set_title("TDOA error on solver successes")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _summary_markdown(rows: list[dict[str, object]]) -> str:
    geometry = [row for row in rows if row["group"] == "geometry"]
    stress = [row for row in rows if row["group"] == "timing_offset"]
    phones = stated_hydrophones_m()
    baseline = max_pairwise_distance_m(phones)
    max_tdoa_us = max_pairwise_tdoa_s(phones, SOUND_SPEED_MPS) * 1e6
    lines = [
        "# Offline scope-record localization",
        "",
        "Every waveform in this run was synthesized in Python and wrapped in `FourChannelRecord`, the same object the Keysight reader returns. No oscilloscope, tank, or transducer measurement was made.",
        "",
        "## Geometry",
        "",
        "Coordinates are the stated metres, with H1 on channel 0. They are not the recentered catalog array.",
        "",
        "| Hydrophone | x (m) | y (m) | z (m) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for index, row in enumerate(phones, start=1):
        lines.append(f"| H{index} | {row[0]:.7f} | {row[1]:.7f} | {row[2]:.7f} |")
    lines.extend(
        [
            "",
            f"Longest pair is {baseline:.6f} m. At {SOUND_SPEED_MPS:.0f} m/s the physical |TDOA| limit is {max_tdoa_us:.2f} µs. The GCC search adds one sample at {VIRTUAL_SAMPLE_RATE_HZ:.0f} Hz.",
            "",
            "## Method",
            "",
            "The record is bandpass-filtered at 15–45 kHz, the same cuts as the waveform study, then a shared event window is cut and GCC-PHAT estimates the delays. `localize_from_tdoa` solves the 3+1 array. A trial is reliable only when that solver accepts a position and none of these waveform flags is set: non-finite TDOA, delay outside the physical limit, correlation peak on the search edge, GCC argmax more than half a carrier cycle from the correlation envelope, or correlation contrast below "
            f"{CONTRAST_MINIMUM:.0f}. Those flags do not use the known source. The contrast floor was raised from 3 to 6 after one pass of this same grid: the lower floor marked a 0 dB, 25 kHz solve reliable when the position error was 131 m and the weakest channel contrast was 3.09. Clean pulses in that pass stayed above 6.9. A synthetic position error above {HUGE_ERROR_M:.0f} m is recorded as `huge_localization_error` and stays in the table. It does not change the reliable bit, so a reliable trial with a large error is visible as false confidence.",
            "",
            f"Sample rate {VIRTUAL_SAMPLE_RATE_HZ:.0f} Hz is the virtual rate. Pulse length is 4 ms with the existing Tukey taper. Noise uses `noise_std_from_snr_db` on that pulse. Seeds start at {BASE_SEED} and follow `base + source*1000 + frequency*100 + snr*10 + offset`.",
            "",
            f"Geometry grid: {len(SOURCES)} sources, frequencies {', '.join(str(int(item)) for item in FREQUENCIES_HZ)} Hz, SNR levels noise-free, 20 dB, 10 dB, and 0 dB. That is {len(geometry)} trials. Timing-offset trials add a delay on H2 at 30 kHz for the source (2, 1, 1.5): 0.5 sample, 2 samples, and one carrier period ({STRESS_OFFSETS_SAMPLES[2]:.4f} samples), each noise-free and at 20 dB ({len(stress)} trials).",
            "",
            "## Geometry-trial results",
            "",
            _rate_table(geometry),
            "",
            _cautious_flags(geometry),
            "",
            "Median position error, in metres, among solver successes. An empty cell has no accepted solver position.",
            "",
            _median_table(geometry, "position_error_m", 4),
            "",
            "Median angular error from the four-phone centroid, in degrees, among solver successes.",
            "",
            _median_table(geometry, "angular_error_deg", 3),
            "",
            "Median of the mean absolute TDOA error across H2, H3, and H4, in microseconds, among solver successes.",
            "",
            _tdoa_table(geometry),
            "",
            _failure_section(geometry),
            "",
            _confidence_section(geometry),
            "",
            "## Timing-offset trials",
            "",
            "These rows inject a known extra delay on H2. TDOA error is scored against the geometry delay plus that offset. Position error is still scored against the original source, so a one-period shift is expected to move the estimate.",
            "",
            _stress_table(stress),
            "",
            "## Files",
            "",
            "- `virtual_trials.csv` — one row per trial",
            "- `example_record.npz` — one synthetic record in the acquisition NPZ layout. Reloading it reproduced the same TDOAs",
            "- `figures/position_error_vs_snr.png`",
            "- `figures/reliability_vs_snr.png`",
            "- `figures/tdoa_error_vs_snr.png`",
            "- `run_manifest.json`",
            "",
            "## Remaining physical validation",
            "",
            "Still required before this pipeline can be treated as a hardware result:",
            "",
            "- Connect the MSOX2014A and capture one four-channel record with `:DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4`. This run did not.",
            "- Survey H1..H4 in the solver frame. The coordinates above are the stated values, not a measurement.",
            "- Confirm which conditioner output is plugged into which scope channel. The CH1=H1 … CH4=H4 map is a convention.",
            "- Measure the sound speed for the test water. The solver used 1480 m/s.",
            "- Calibrate volts to pascals for the Aquarian S1f and PCB 482C05 chain. Synthetic channels are unitless voltages with the simulator's DC offsets.",
            "- Record a real 25–40 kHz burst from a known in-water position and compare the estimate with that position. Multipath, transducer response, and electrical crosstalk are absent from these waveforms.",
            "- Measure cable and trigger skew. The timing offsets here were inserted with `delay_signal`.",
            "- Confirm the scope timebase and record length against the 4 ms pre-window and 6 ms post-window used at 256 kHz.",
            "",
        ]
    )
    return "\n".join(lines)


def _rate_table(rows: list[dict[str, object]]) -> str:
    header = "| SNR | Trials | Solver success | Reliable | Solver failures |"
    rule = "| --- | ---: | ---: | ---: | ---: |"
    body = [header, rule]
    for label in _snr_labels():
        chosen = [row for row in rows if _snr_label(row) == label]
        solved = sum(bool(row["solver_success"]) for row in chosen)
        reliable = sum(bool(row["reliable"]) for row in chosen)
        body.append(
            f"| {label} | {len(chosen)} | {solved} ({_pct(solved, len(chosen))}) | "
            f"{reliable} ({_pct(reliable, len(chosen))}) | {len(chosen) - solved} |"
        )
    solved = sum(bool(row["solver_success"]) for row in rows)
    reliable = sum(bool(row["reliable"]) for row in rows)
    body.append(
        f"| All | {len(rows)} | {solved} ({_pct(solved, len(rows))}) | "
        f"{reliable} ({_pct(reliable, len(rows))}) | {len(rows) - solved} |"
    )
    return "\n".join(body)


def _median_table(rows: list[dict[str, object]], field: str, digits: int) -> str:
    header = "| SNR | " + " | ".join(f"{freq / 1000:.0f} kHz" for freq in FREQUENCIES_HZ) + " |"
    rule = "| --- | " + " | ".join("---:" for _ in FREQUENCIES_HZ) + " |"
    body = [header, rule]
    for label in _snr_labels():
        cells = []
        for frequency in FREQUENCIES_HZ:
            values = [
                float(row[field])
                for row in rows
                if _snr_label(row) == label
                and row["frequency_hz"] == frequency
                and row["solver_success"]
                and np.isfinite(float(row[field]))
            ]
            cells.append(f"{float(np.median(values)):.{digits}f}" if values else "—")
        body.append("| " + label + " | " + " | ".join(cells) + " |")
    return "\n".join(body)


def _tdoa_table(rows: list[dict[str, object]]) -> str:
    header = "| SNR | " + " | ".join(f"{freq / 1000:.0f} kHz" for freq in FREQUENCIES_HZ) + " |"
    rule = "| --- | " + " | ".join("---:" for _ in FREQUENCIES_HZ) + " |"
    body = [header, rule]
    for label in _snr_labels():
        cells = []
        for frequency in FREQUENCIES_HZ:
            errors = []
            for row in rows:
                if _snr_label(row) != label or row["frequency_hz"] != frequency or not row["solver_success"]:
                    continue
                pair = [abs(float(row[f"tdoa_error_us_{channel}"])) for channel in (1, 2, 3)]
                if np.all(np.isfinite(pair)):
                    errors.append(float(np.mean(pair)))
            cells.append(f"{float(np.median(errors)):.3f}" if errors else "—")
        body.append("| " + label + " | " + " | ".join(cells) + " |")
    return "\n".join(body)


def _cautious_flags(rows: list[dict[str, object]]) -> str:
    close = [
        row
        for row in rows
        if row["noise_free"]
        and row["solver_success"]
        and not row["reliable"]
        and np.isfinite(float(row["position_error_m"]))
        and float(row["position_error_m"]) < 0.1
    ]
    if not close:
        return "Every noise-free solver success that was flagged unreliable had position error of at least 0.1 m."
    worst = max(float(row["position_error_m"]) for row in close)
    return (
        f"{len(close)} noise-free solver successes were flagged unreliable even though the position error was under 0.1 m "
        f"(largest of those errors {worst:.3f} m). The flag on those rows is the carrier-envelope check. "
        "The delay estimate was still close, so that check is cautious on a clean pulse."
    )


def _failure_section(rows: list[dict[str, object]]) -> str:
    reasons: dict[str, int] = {}
    flags: dict[str, int] = {}
    for row in rows:
        if not row["solver_success"]:
            reason = str(row["failure_reason"] or "unspecified")
            reasons[reason] = reasons.get(reason, 0) + 1
        for flag in str(row["flags"]).split(";"):
            if flag:
                flags[flag] = flags.get(flag, 0) + 1
    lines = ["Solver rejection counts:"]
    lines.append("")
    if not reasons:
        lines.append("Every geometry trial returned a solver position.")
    else:
        lines.append("| Failure reason | Count |")
        lines.append("| --- | ---: |")
        for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"| {reason} | {count} |")
    lines.append("")
    lines.append("Flag counts. A trial can carry more than one flag.")
    lines.append("")
    if not flags:
        lines.append("No flags were set.")
    else:
        lines.append("| Flag | Trials |")
        lines.append("| --- | ---: |")
        for flag, count in sorted(flags.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"| {flag} | {count} |")
    return "\n".join(lines)


def _confidence_section(rows: list[dict[str, object]]) -> str:
    reliable = [row for row in rows if row["reliable"] and np.isfinite(float(row["position_error_m"]))]
    solved = [
        row
        for row in rows
        if row["solver_success"] and np.isfinite(float(row["position_error_m"]))
    ]
    false_confidence = [
        row for row in reliable if float(row["position_error_m"]) > HUGE_ERROR_M
    ]
    lines = ["Position error on the subsets the flags define:"]
    lines.append("")
    lines.append("| Subset | Trials | Median error (m) | 95th percentile (m) | Max error (m) |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    lines.append(_error_row("Solver success", solved))
    lines.append(_error_row("Reliable", reliable))
    lines.append("")
    lines.append(
        f"Reliable trials with position error above {HUGE_ERROR_M:.0f} m: {len(false_confidence)}."
    )
    return "\n".join(lines)


def _error_row(label: str, rows: list[dict[str, object]]) -> str:
    if not rows:
        return f"| {label} | 0 | — | — | — |"
    values = np.array([float(row["position_error_m"]) for row in rows], dtype=float)
    return (
        f"| {label} | {len(rows)} | {float(np.median(values)):.4f} | "
        f"{float(np.percentile(values, 95)):.4f} | {float(np.max(values)):.4f} |"
    )


def _stress_table(rows: list[dict[str, object]]) -> str:
    header = (
        "| SNR | H2 offset (samples) | Solver success | Reliable | "
        "Mean |TDOA error| (µs) | Position error (m) | Flags |"
    )
    rule = "| --- | ---: | --- | --- | ---: | ---: | --- |"
    body = [header, rule]
    ordered = sorted(rows, key=lambda row: (0 if row["noise_free"] else float(row["snr_db"]), float(row["offset_samples"])))
    for row in ordered:
        pair = [abs(float(row[f"tdoa_error_us_{channel}"])) for channel in (1, 2, 3)]
        tdoa = f"{float(np.mean(pair)):.3f}" if np.all(np.isfinite(pair)) else "—"
        if row["solver_success"] and np.isfinite(float(row["position_error_m"])):
            position = f"{float(row['position_error_m']):.4f}"
        else:
            position = "—"
        body.append(
            f"| {_snr_label(row)} | {float(row['offset_samples']):.4f} | {row['solver_success']} | "
            f"{row['reliable']} | {tdoa} | {position} | {row['flags'] or '—'} |"
        )
    return "\n".join(body)


def _failed_row(case: Case, message: str) -> dict[str, object]:
    source = np.array(case.source_m, dtype=float)
    nan3 = {"0": float("nan"), "1": float("nan"), "2": float("nan"), "3": float("nan")}
    row: dict[str, object] = {
        "group": case.group,
        "source_index": case.source_index,
        "source_x_m": source[0],
        "source_y_m": source[1],
        "source_z_m": source[2],
        "frequency_hz": case.frequency_hz,
        "snr_db": "" if case.snr_db is None else case.snr_db,
        "noise_free": case.snr_db is None,
        "offset_channel": case.offset_channel if case.offset_samples else "",
        "offset_samples": case.offset_samples,
        "noise_seed": case.noise_seed,
        "solver_success": False,
        "reliable": False,
        "failure_reason": message,
        "flags": "pipeline_exception",
        "position_error_m": float("nan"),
        "angular_error_deg": float("nan"),
        "residual_rms_us": float("nan"),
        "event_index": "",
        "est_x_m": float("nan"),
        "est_y_m": float("nan"),
        "est_z_m": float("nan"),
    }
    for prefix in ("true_tdoa_us", "est_tdoa_us", "tdoa_error_us"):
        for index in range(4):
            row[f"{prefix}_{index}"] = float("nan")
    for prefix in ("sidelobe_ratio", "contrast", "envelope_cycles"):
        for index in range(1, 4):
            row[f"{prefix}_{index}"] = float("nan")
    del nan3
    return row


def _series(prefix: str, values: np.ndarray, start: int = 0) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {f"{prefix}_{index}": float(array[index]) for index in range(start, array.shape[0])}


def _snr_labels() -> tuple[str, ...]:
    return tuple("noise-free" if item is None else f"{item:.0f} dB" for item in SNR_LEVELS_DB)


def _snr_label(row: dict[str, object]) -> str:
    if row["noise_free"]:
        return "noise-free"
    return f"{float(row['snr_db']):.0f} dB"


def _rate(rows: list[dict[str, object]], field: str) -> float:
    if not rows:
        return float("nan")
    return sum(bool(row[field]) for row in rows) / len(rows)


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{100.0 * count / total:.1f}%"


def _apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.35,
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
        }
    )


if __name__ == "__main__":
    main()
