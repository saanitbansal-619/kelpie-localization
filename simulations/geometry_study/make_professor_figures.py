"""Professor-facing figures for the completed geometry study.

Reads the existing CSV results and writes only under ``figures/professor/``.
It does not rerun the 9000-trial Monte Carlo and does not modify result files.

Waveform and GCC-PHAT panels are recreated from the same representative
source and pipeline settings. Those calls return arrays in memory; they do
not write the study CSVs.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_study.pipeline import (
    prepare_reference_waveform,
    representative_waveforms,
)
from src.geometry import get_geometry

STUDY = Path(__file__).resolve().parent
RESULTS = STUDY / "results"
OUT = STUDY / "figures" / "professor"

ORDER = ("linear", "square_planar", "cross_planar", "tetrahedral", "three_plus_one")
COLORS = {
    "linear": "#0072B2",
    "square_planar": "#E69F00",
    "cross_planar": "#009E73",
    "tetrahedral": "#D55E00",
    "three_plus_one": "#CC79A7",
}
HYDRO_COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00")
VOLUMETRIC = ("tetrahedral", "three_plus_one")
SNRS = (40.0, 30.0, 20.0, 10.0, 5.0, 0.0)


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "legend.fontsize": 8,
        }
    )


def _save(fig: plt.Figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}", flush=True)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _success(row: dict[str, str]) -> bool:
    return row["solver_success"].strip().lower() == "true"


def _f(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _snr_axis(ax: plt.Axes) -> None:
    ax.set_xlim(43, -3)
    ax.set_xticks(list(SNRS))
    ax.set_xlabel("SNR (dB) — noise increases to the right")


def _pair_errors(rows: list[dict[str, str]]) -> np.ndarray:
    values = []
    for row in rows:
        for key in ("tdoa_err_h1_us", "tdoa_err_h2_us", "tdoa_err_h3_us"):
            value = abs(_f(row, key))
            if np.isfinite(value):
                values.append(value)
    return np.asarray(values, dtype=float)


def _rows(rows: list[dict[str, str]], geometry: str, snr: float | None = None) -> list[dict[str, str]]:
    selected = [row for row in rows if row["geometry"] == geometry]
    if snr is not None:
        selected = [row for row in selected if float(row["snr_db"]) == float(snr)]
    return selected


def _coords_by_geometry(table: list[dict[str, str]]) -> dict[str, np.ndarray]:
    grouped: dict[str, list[list[float]]] = defaultdict(list)
    names: dict[str, str] = {}
    for row in table:
        grouped[row["geometry"]].append([float(row["x_m"]), float(row["y_m"]), float(row["z_m"])])
        names[row["geometry"]] = row["geometry_name"]
    coords = {key: np.asarray(value, dtype=float) for key, value in grouped.items()}
    return coords, names


def plot_overview(coords: dict[str, np.ndarray], names: dict[str, str]) -> None:
    _style()
    fig = plt.figure(figsize=(14.2, 8.2))
    for index, key in enumerate(ORDER):
        ax = fig.add_subplot(2, 3, index + 1, projection="3d")
        xyz = coords[key]
        for i, j in _edges(key):
            seg = xyz[[i, j]]
            ax.plot(seg[:, 0], seg[:, 1], seg[:, 2], color="0.45", linewidth=1.2)
        ax.scatter([0], [0], [0], c="black", marker="+", s=40, depthshade=False)
        for phone in range(4):
            ax.scatter(
                [xyz[phone, 0]],
                [xyz[phone, 1]],
                [xyz[phone, 2]],
                c=HYDRO_COLORS[phone],
                s=36,
                depthshade=False,
            )
            ax.text(xyz[phone, 0], xyz[phone, 1], xyz[phone, 2], f" H{phone}", fontsize=8)
        ax.set_xlim(-0.20, 0.20)
        ax.set_ylim(-0.20, 0.20)
        ax.set_zlim(-0.20, 0.20)
        ax.set_box_aspect((1, 1, 1))
        ax.set_proj_type("ortho")
        ax.view_init(elev=22, azim=-58)
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.set_zlabel("Z (m)")
        ax.set_title(names[key])
    note = fig.add_subplot(2, 3, 6)
    note.axis("off")
    note.text(
        0.0,
        0.5,
        "SIMULATION\n\n"
        "Coordinates from the completed\n"
        "geometry study.\n"
        "Shared axis limits: ±0.20 m.\n"
        "H0 blue, H1 orange,\n"
        "H2 green, H3 vermillion.\n"
        "Origin marked +.",
        va="center",
        fontsize=11,
    )
    fig.suptitle("Five hydrophone geometries (existing study)", fontsize=15)
    fig.tight_layout()
    _save(fig, "01_five_geometry_overview.png")


def _edges(key: str) -> tuple[tuple[int, int], ...]:
    if key == "linear":
        return ((0, 1), (1, 2), (2, 3))
    if key in ("square_planar", "cross_planar"):
        return ((0, 1), (1, 2), (2, 3), (3, 0))
    if key == "tetrahedral":
        return tuple((i, j) for i in range(4) for j in range(i + 1, 4))
    return ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


def plot_propagation(propagation: list[dict[str, str]]) -> None:
    _style()
    rows = [row for row in propagation if row["Geometry"] == "Tetrahedral"]
    fig = plt.figure(figsize=(8.6, 7.2))
    ax = fig.add_subplot(111, projection="3d")
    source = np.array(
        [float(rows[0]["Source X"]), float(rows[0]["Source Y"]), float(rows[0]["Source Z"])],
        dtype=float,
    )
    for index, row in enumerate(rows):
        phone = np.array(
            [float(row["Hydrophone X"]), float(row["Hydrophone Y"]), float(row["Hydrophone Z"])],
            dtype=float,
        )
        ax.plot(
            [source[0], phone[0]],
            [source[1], phone[1]],
            [source[2], phone[2]],
            color=HYDRO_COLORS[index],
            linewidth=1.3,
        )
        ax.scatter([phone[0]], [phone[1]], [phone[2]], c=HYDRO_COLORS[index], s=40, depthshade=False)
        label = (
            f"H{index}: {float(row['Distance (m)']):.3f} m, "
            f"TDOA {float(row['True TDOA Relative to H0 (us)']):+.1f} us"
        )
        ax.scatter([], [], [], c=HYDRO_COLORS[index], s=40, label=label)
    ax.scatter([source[0]], [source[1]], [source[2]], c="black", marker="*", s=90, depthshade=False, label="source")
    ax.scatter([0], [0], [0], c="black", marker="+", s=50, depthshade=False, label="array origin")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=18, azim=-58)
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title(
        f"SIMULATION — tetrahedral array, source ({source[0]:.2f}, {source[1]:.2f}, {source[2]:.2f}) m\n"
        "Different path lengths are different propagation times, and those differences are the TDOAs"
    )
    _save(fig, "02_source_to_hydrophones.png")


def plot_waveform_and_gcc(config: dict) -> None:
    _style()
    array = get_geometry("tetrahedral")
    fs = float(config["sample_rate_hz"])
    source = np.asarray(config["representative_source_m"], dtype=float)
    _, reference = prepare_reference_waveform(
        fs, float(config["capture_duration_s"]), float(config["event_time_s"])
    )
    bundle = representative_waveforms(
        array,
        source,
        float(config["representative_snr_db"]),
        reference,
        fs,
        float(config["sound_speed_mps"]),
        config,
    )
    window = bundle["window"]
    energy = np.mean(window**2, axis=0)
    above = np.flatnonzero(energy >= 0.2 * np.max(energy))
    edge = int(above[0]) if above.size else int(np.argmax(energy))
    time_ms = np.arange(window.shape[1]) / fs * 1e3
    edge_ms = time_ms[edge]

    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.0))
    for ax, (start, stop, subtitle) in zip(
        axes,
        (
            (edge_ms - 0.25, edge_ms + 2.4, "Shared chirp in one common window"),
            (edge_ms - 0.04, edge_ms + 0.28, "Leading edge, expanded"),
        ),
    ):
        for index in range(4):
            ax.plot(time_ms, window[index], color=HYDRO_COLORS[index], linewidth=1.15, label=f"H{index}")
        ax.set_xlim(start, stop)
        ax.set_ylabel("Amplitude")
        ax.set_title(subtitle)
        ax.grid(True, alpha=0.35)
    axes[0].legend(ncol=4, loc="upper right")
    axes[1].set_xlabel("Time from the start of the common window (ms)")
    fig.suptitle(
        "SIMULATION — tetrahedral array, 30 dB\n"
        "Channels were not shifted to line up. The offsets are the arrivals.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, "03_received_waveforms.png")

    fig, axes = plt.subplots(3, 1, figsize=(10.2, 8.0), sharex=True)
    true_s = bundle["true_tdoa_s"]
    est_s = bundle["estimated_tdoa_s"]
    for axis_index, channel in enumerate((1, 2, 3)):
        ax = axes[axis_index]
        result = bundle["diagnostics"][channel]
        ax.plot(result.lags_seconds * 1e6, result.correlation, color="#0072B2", linewidth=1.0, label="GCC-PHAT")
        true_us = float(true_s[channel] * 1e6)
        est_us = float(est_s[channel] * 1e6)
        ax.axvline(true_us, color="black", linestyle="--", linewidth=1.3, label="true TDOA")
        ax.axvline(est_us, color="#D55E00", linewidth=1.3, label="estimated TDOA")
        ax.scatter([est_us], [result.peak_value], color="#D55E00", s=28, zorder=3)
        ax.set_ylabel(f"H{channel} vs H0")
        ax.set_title(
            f"true {true_us:+.2f} us, estimated {est_us:+.2f} us, absolute error {abs(est_us - true_us):.2f} us",
            loc="left",
            fontsize=10,
        )
        ax.grid(True, alpha=0.35)
    axes[0].legend(loc="upper right")
    axes[-1].set_xlabel("Lag (microseconds)")
    fig.suptitle(
        "SIMULATION — GCC-PHAT on the tetrahedral array\n"
        "The correlation peak is the estimated delay relative to H0",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, "04_gcc_phat_tdoa.png")


def plot_true_vs_estimated(rows: list[dict[str, str]]) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(7.4, 7.0))
    limit = 1.0
    for key in ORDER:
        true_values = []
        est_values = []
        for row in _rows(rows, key):
            for suffix in ("h1", "h2", "h3"):
                true_us = _f(row, f"true_tdoa_{suffix}_us")
                est_us = _f(row, f"est_tdoa_{suffix}_us")
                if np.isfinite(true_us) and np.isfinite(est_us):
                    true_values.append(true_us)
                    est_values.append(est_us)
        ax.scatter(
            true_values,
            est_values,
            s=9,
            alpha=0.25,
            c=COLORS[key],
            linewidths=0,
            label=row_name(rows, key),
            zorder=2,
        )
        if true_values:
            limit = max(limit, float(np.max(np.abs(true_values))), float(np.max(np.abs(est_values))))
    limit *= 1.05
    ax.plot([-limit, limit], [-limit, limit], color="black", linewidth=1.2, label="y = x", zorder=3)
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("True TDOA (µs)")
    ax.set_ylabel("Estimated TDOA (µs)")
    ax.set_title("SIMULATION — true versus estimated TDOA\nAll five geometries and all six SNRs. Outliers are included.")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.35)
    _save(fig, "05_true_vs_estimated_tdoa.png")


def row_name(rows: list[dict[str, str]], key: str) -> str:
    for row in rows:
        if row["geometry"] == key:
            return row["geometry_name"]
    return key


def plot_tdoa_vs_snr(rows: list[dict[str, str]]) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(9.6, 6.0))
    for key in ORDER:
        medians, low, high, tail = [], [], [], []
        for snr in SNRS:
            values = _pair_errors(_rows(rows, key, snr))
            medians.append(float(np.median(values)))
            low.append(float(np.percentile(values, 25)))
            high.append(float(np.percentile(values, 75)))
            tail.append(float(np.percentile(values, 95)))
        color = COLORS[key]
        ax.fill_between(SNRS, low, high, color=color, alpha=0.15, linewidth=0)
        ax.plot(SNRS, medians, color=color, marker="o", linewidth=1.8, label=row_name(rows, key))
        ax.plot(SNRS, tail, color=color, linestyle="--", linewidth=1.0)
    _snr_axis(ax)
    ax.set_ylabel("Absolute TDOA error (µs)")
    ax.set_title(
        "SIMULATION — TDOA error versus SNR\n"
        "Solid line: median. Band: 25th–75th percentile. Dashed line: 95th percentile."
    )
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.35)
    _save(fig, "06_tdoa_error_vs_snr.png")


def plot_tdoa_at_0db(rows: list[dict[str, str]]) -> None:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.6))
    series = []
    labels = []
    for index, key in enumerate(ORDER):
        values = _pair_errors(_rows(rows, key, 0.0))
        series.append(values)
        labels.append(f"{row_name(rows, key)}\nmedian {np.median(values):.2f} µs\nmean {np.mean(values):.2f} µs")
        order = np.sort(values)
        cdf = np.arange(1, order.size + 1) / order.size
        axes[1].plot(order, cdf, color=COLORS[key], label=row_name(rows, key))
    axes[0].boxplot(
        series,
        positions=np.arange(len(ORDER)),
        widths=0.55,
        showfliers=True,
        patch_artist=True,
        medianprops={"color": "black", "linewidth": 1.4},
        boxprops={"facecolor": "#f4f4f4"},
    )
    axes[0].set_yscale("log")
    axes[0].set_xticks(np.arange(len(ORDER)))
    axes[0].set_xticklabels(labels, fontsize=8)
    axes[0].set_ylabel("Absolute TDOA error (µs)")
    axes[0].set_title("Box plot, logarithmic axis\nThe line is the median. Circles are outliers.")
    axes[0].grid(True, axis="y", alpha=0.35)
    axes[1].set_xscale("symlog", linthresh=0.05)
    axes[1].set_xticks([0.01, 0.1, 1, 10, 100])
    axes[1].set_xticklabels(["0.01", "0.1", "1", "10", "100"])
    axes[1].set_xlabel("Absolute TDOA error (µs)")
    axes[1].set_ylabel("Fraction of pairs at or below this error")
    axes[1].set_title("ECDF, symmetric-log horizontal axis\nThe long tail is the right-hand end. Nothing was removed.")
    axes[1].grid(True, alpha=0.35)
    axes[1].legend(loc="lower right")
    fig.suptitle("SIMULATION — absolute TDOA error at 0 dB", fontsize=13)
    fig.tight_layout()
    _save(fig, "07_tdoa_error_distribution_0db.png")


def plot_success(rows: list[dict[str, str]]) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(10.4, 5.6))
    x = np.arange(len(ORDER), dtype=float)
    width = 0.12
    offsets = (np.arange(len(SNRS)) - (len(SNRS) - 1) / 2.0) * width
    for offset, snr in zip(offsets, SNRS):
        rates = []
        for key in ORDER:
            selected = _rows(rows, key, snr)
            rates.append(sum(_success(row) for row in selected) / len(selected))
        ax.bar(x + offset, rates, width=width * 0.92, label=f"{snr:.0f} dB")
    for index, key in enumerate(ORDER):
        rates = [
            sum(_success(row) for row in _rows(rows, key, snr)) / len(_rows(rows, key, snr)) for snr in SNRS
        ]
        if max(rates) == 0.0:
            ax.text(index, 0.06, "0 at\nevery SNR", ha="center", va="bottom", fontsize=8, color="0.25")
    ax.set_xticks(x)
    ax.set_xticklabels([row_name(rows, key) for key in ORDER])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Solver success rate")
    ax.set_title(
        "SIMULATION — localization success\n"
        "A rate of 0 is a reported failure. It is not stored as zero position error."
    )
    ax.legend(title="SNR", ncol=3)
    ax.grid(True, axis="y", alpha=0.35)
    _save(fig, "08_localization_success_by_geometry.png")


def _metric_vs_snr(rows: list[dict[str, str]], key_name: str) -> dict[str, dict[str, list[float]]]:
    curves = {}
    for key in VOLUMETRIC:
        medians, tails = [], []
        for snr in SNRS:
            values = np.asarray(
                [
                    _f(row, key_name)
                    for row in _rows(rows, key, snr)
                    if _success(row) and np.isfinite(_f(row, key_name))
                ],
                dtype=float,
            )
            medians.append(float(np.median(values)) if values.size else np.nan)
            tails.append(float(np.percentile(values, 95)) if values.size else np.nan)
        curves[key] = {"median": medians, "p95": tails}
    return curves


def plot_angular_vs_snr(rows: list[dict[str, str]]) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    curves = _metric_vs_snr(rows, "angular_error_deg")
    for key, curve in curves.items():
        color = COLORS[key]
        ax.plot(SNRS, curve["median"], color=color, marker="o", linewidth=1.8, label=f"{row_name(rows, key)} median")
        ax.plot(SNRS, curve["p95"], color=color, linestyle="--", linewidth=1.1, label=f"{row_name(rows, key)} 95th")
    _snr_axis(ax)
    ax.set_ylabel("Angular error (degrees)")
    ax.set_title(
        "SIMULATION — angular error versus SNR\n"
        "Tetrahedral and three-plus-one only. Linear and planar arrays have no valid direction estimate."
    )
    ax.legend(loc="best")
    ax.grid(True, alpha=0.35)
    _save(fig, "09_angular_error_vs_snr.png")


def plot_position_vs_snr(rows: list[dict[str, str]]) -> None:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.4))
    curves = _metric_vs_snr(rows, "position_error_m")
    maxima = {key: [] for key in VOLUMETRIC}
    for key in VOLUMETRIC:
        for snr in SNRS:
            values = np.asarray(
                [
                    _f(row, "position_error_m")
                    for row in _rows(rows, key, snr)
                    if _success(row) and np.isfinite(_f(row, "position_error_m"))
                ],
                dtype=float,
            )
            maxima[key].append(float(np.max(values)) if values.size else np.nan)
        color = COLORS[key]
        axes[0].plot(SNRS, curves[key]["median"], color=color, marker="o", linewidth=1.8, label=f"{row_name(rows, key)} median")
        axes[0].plot(SNRS, curves[key]["p95"], color=color, linestyle="--", linewidth=1.1, label=f"{row_name(rows, key)} 95th")
        axes[1].plot(SNRS, maxima[key], color=color, marker="o", linewidth=1.6, label=row_name(rows, key))
    for ax in axes:
        _snr_axis(ax)
        ax.grid(True, alpha=0.35)
        ax.legend(loc="best", fontsize=8)
    axes[0].set_ylabel("3D position error (m)")
    axes[0].set_title("Median and 95th percentile")
    axes[1].set_ylabel("3D position error (m)")
    axes[1].set_title("Maximum among successful solves")
    fig.suptitle(
        "SIMULATION — position error versus SNR\n"
        "Valid volumetric solves only. The right panel keeps the tail visible.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, "10_position_error_vs_snr.png")


def plot_direction_vs_position(rows: list[dict[str, str]]) -> None:
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.5))
    for key in VOLUMETRIC:
        selected = [row for row in _rows(rows, key, 20.0) if _success(row)]
        axes[0].scatter(
            [_f(row, "angular_error_deg") for row in selected],
            [_f(row, "position_error_m") for row in selected],
            s=16,
            alpha=0.45,
            c=COLORS[key],
            linewidths=0,
            label=row_name(rows, key),
        )
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Angular error (degrees)")
    axes[0].set_ylabel("3D position error (m)")
    axes[0].set_title("Each successful trial at 20 dB")
    axes[0].grid(True, alpha=0.35)
    axes[0].legend(loc="best")
    angular = _metric_vs_snr(rows, "angular_error_deg")
    position = _metric_vs_snr(rows, "position_error_m")
    x = np.arange(len(SNRS))
    width = 0.18
    axes[1].bar(x - 1.5 * width, angular["tetrahedral"]["median"], width=width, color=COLORS["tetrahedral"], label="Tetrahedral angle")
    axes[1].bar(x - 0.5 * width, angular["three_plus_one"]["median"], width=width, color=COLORS["three_plus_one"], label="Three plus one angle")
    ax2 = axes[1].twinx()
    ax2.bar(x + 0.5 * width, position["tetrahedral"]["median"], width=width, color=COLORS["tetrahedral"], alpha=0.45, label="Tetrahedral position")
    ax2.bar(x + 1.5 * width, position["three_plus_one"]["median"], width=width, color=COLORS["three_plus_one"], alpha=0.45, label="Three plus one position")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([f"{snr:.0f}" for snr in SNRS])
    axes[1].set_xlabel("SNR (dB)")
    axes[1].set_ylabel("Median angular error (degrees)")
    ax2.set_ylabel("Median position error (m)")
    axes[1].set_title("Medians, separate units")
    handles1, labels1 = axes[1].get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    axes[1].legend(handles1 + handles2, labels1 + labels2, loc="upper left", fontsize=7)
    fig.suptitle(
        "SIMULATION — direction can be close while range is not\n"
        "Degrees and metres are not plotted on one shared axis.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, "11_direction_vs_position_accuracy.png")


def plot_vs_distance(rows: list[dict[str, str]]) -> None:
    _style()
    edges = np.array([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    centers = 0.5 * (edges[:-1] + edges[1:])
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.4))
    for key in VOLUMETRIC:
        selected = [row for row in _rows(rows, key, 20.0) if _success(row)]
        ang_med, ang_tail, pos_med, pos_tail = [], [], [], []
        for low, high in zip(edges[:-1], edges[1:]):
            if high == edges[-1]:
                in_bin = [row for row in selected if low <= _f(row, "source_range_m") <= high]
            else:
                in_bin = [row for row in selected if low <= _f(row, "source_range_m") < high]
            ang = np.asarray([_f(row, "angular_error_deg") for row in in_bin if np.isfinite(_f(row, "angular_error_deg"))])
            pos = np.asarray([_f(row, "position_error_m") for row in in_bin if np.isfinite(_f(row, "position_error_m"))])
            ang_med.append(float(np.median(ang)) if ang.size else np.nan)
            ang_tail.append(float(np.percentile(ang, 95)) if ang.size else np.nan)
            pos_med.append(float(np.median(pos)) if pos.size else np.nan)
            pos_tail.append(float(np.percentile(pos, 95)) if pos.size else np.nan)
        color = COLORS[key]
        axes[0].plot(centers, ang_med, marker="o", color=color, label=f"{row_name(rows, key)} median")
        axes[0].plot(centers, ang_tail, linestyle="--", color=color, label=f"{row_name(rows, key)} 95th")
        axes[1].plot(centers, pos_med, marker="o", color=color, label=f"{row_name(rows, key)} median")
        axes[1].plot(centers, pos_tail, linestyle="--", color=color, label=f"{row_name(rows, key)} 95th")
    axes[0].set_ylabel("Angular error (degrees)")
    axes[0].set_title("Direction")
    axes[1].set_ylabel("3D position error (m)")
    axes[1].set_title("Position")
    for ax in axes:
        ax.set_xlabel("Source distance from array center (m)")
        ax.set_ylim(bottom=0.0)
        ax.grid(True, alpha=0.35)
        ax.legend(fontsize=7)
    fig.suptitle(
        "SIMULATION — error versus source distance at 20 dB\n"
        "1 m bins, successful volumetric solves. Dashed lines are 95th percentiles. Not an interpolated map.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, "12_error_vs_source_distance.png")


def plot_summary(rows: list[dict[str, str]]) -> None:
    _style()
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 8.2))
    x = np.arange(len(ORDER))
    medians = [float(np.median(_pair_errors(_rows(rows, key, 20.0)))) for key in ORDER]
    axes[0, 0].bar(x, medians, color=[COLORS[key] for key in ORDER])
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels([row_name(rows, key) for key in ORDER], rotation=15)
    axes[0, 0].set_ylabel("Median |TDOA error| (µs)")
    axes[0, 0].set_title("TDOA at 20 dB")
    rates = []
    for key in ORDER:
        selected = _rows(rows, key, 20.0)
        rates.append(100.0 * sum(_success(row) for row in selected) / len(selected))
    axes[0, 1].bar(x, rates, color=[COLORS[key] for key in ORDER])
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels([row_name(rows, key) for key in ORDER], rotation=15)
    axes[0, 1].set_ylim(0, 105)
    axes[0, 1].set_ylabel("Success (%)")
    axes[0, 1].set_title("Localization success at 20 dB")
    angular = _metric_vs_snr(rows, "angular_error_deg")
    position = _metric_vs_snr(rows, "position_error_m")
    for key in VOLUMETRIC:
        axes[1, 0].plot(SNRS, angular[key]["median"], marker="o", color=COLORS[key], label=row_name(rows, key))
        axes[1, 1].plot(SNRS, position[key]["median"], marker="o", color=COLORS[key], label=row_name(rows, key))
    for ax in (axes[1, 0], axes[1, 1]):
        _snr_axis(ax)
        ax.legend(loc="best")
        ax.grid(True, alpha=0.35)
    axes[1, 0].set_ylabel("Median angular error (degrees)")
    axes[1, 0].set_title("Direction, volumetric arrays")
    axes[1, 1].set_ylabel("Median position error (m)")
    axes[1, 1].set_title("Position, volumetric arrays")
    for ax in (axes[0, 0], axes[0, 1]):
        ax.grid(True, axis="y", alpha=0.35)
    fig.suptitle(
        "SIMULATION — geometry study at a glance\n"
        "TDOA error is similar. Unique 3D fixes exist only for the two non-coplanar arrays.",
        fontsize=13,
    )
    fig.tight_layout()
    _save(fig, "13_geometry_study_summary.png")


def main() -> None:
    rows = _read_csv(RESULTS / "experiment_results.csv")
    if len(rows) != 9000:
        raise SystemExit(f"expected 9000 result rows, found {len(rows)}")
    present = {row["geometry"] for row in rows}
    if set(ORDER) != present:
        raise SystemExit(f"unexpected geometries: {sorted(present)}")
    coords, names = _coords_by_geometry(_read_csv(RESULTS / "hydrophone_coordinates.csv"))
    config = json.loads((STUDY / "configs" / "experiment.json").read_text(encoding="utf-8"))
    plot_overview(coords, names)
    plot_propagation(_read_csv(RESULTS / "propagation_ground_truth.csv"))
    plot_waveform_and_gcc(config)
    plot_true_vs_estimated(rows)
    plot_tdoa_vs_snr(rows)
    plot_tdoa_at_0db(rows)
    plot_success(rows)
    plot_angular_vs_snr(rows)
    plot_position_vs_snr(rows)
    plot_direction_vs_position(rows)
    plot_vs_distance(rows)
    plot_summary(rows)


if __name__ == "__main__":
    main()
