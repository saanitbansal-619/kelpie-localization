"""Figures for the hydrophone-count study. Reads saved CSV rows only."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulations.hydrophone_count_study.analysis import (
    COUNTS,
    PRIMARY_SNR_DB,
    SNRS,
    pair_abs_errors,
    select,
    success,
    success_metric,
)
from src.hydrophone_counts import list_count_arrays

STUDY = Path(__file__).resolve().parent
ARRAYS = STUDY / "figures" / "arrays"
TDOA = STUDY / "figures" / "tdoa"
LOCALIZATION = STUDY / "figures" / "localization"
COMPARISONS = STUDY / "figures" / "comparisons"

COLORS = {4: "#0072B2", 5: "#E69F00", 6: "#009E73"}
HYDRO_COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9")


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "legend.fontsize": 9,
        }
    )


def _save(fig: plt.Figure, folder: Path, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}", flush=True)


def _snr_axis(ax: plt.Axes) -> None:
    ax.set_xlim(43, -3)
    ax.set_xticks(list(SNRS))
    ax.set_xlabel("SNR (dB) — noise increases to the right")


def _shared_limits() -> tuple[float, float]:
    span = 0.0
    for array in list_count_arrays():
        span = max(span, float(np.max(np.abs(array.coordinates_m))))
    limit = max(0.20, span * 1.35)
    return -limit, limit


def _edges(n: int) -> tuple[tuple[int, int], ...]:
    return tuple((i, j) for i in range(n) for j in range(i + 1, n))


def plot_arrays() -> None:
    _style()
    low, high = _shared_limits()
    arrays = list_count_arrays()
    for array in arrays:
        fig = plt.figure(figsize=(7.2, 6.4))
        ax = fig.add_subplot(111, projection="3d")
        _draw_array(ax, array.coordinates_m, low, high)
        baseline = array.max_pairwise_distance_m()
        ax.set_title(
            f"SIMULATION — {array.name}\n"
            f"Maximum pairwise baseline {baseline:.4f} m"
        )
        _save(fig, ARRAYS, f"{array.sensor_count}_hydrophones.png")

    fig = plt.figure(figsize=(14.5, 5.2))
    for index, array in enumerate(arrays):
        ax = fig.add_subplot(1, 3, index + 1, projection="3d")
        _draw_array(ax, array.coordinates_m, low, high)
        ax.set_title(f"{array.name}\nmax baseline {array.max_pairwise_distance_m():.3f} m")
    fig.suptitle(
        "SIMULATION — same axis limits for 4, 5, and 6 hydrophones",
        fontsize=14,
        y=0.98,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, ARRAYS, "4_vs_5_vs_6_arrays.png")


def _draw_array(ax, coords: np.ndarray, low: float, high: float) -> None:
    n = coords.shape[0]
    for i, j in _edges(n):
        seg = coords[[i, j]]
        ax.plot(seg[:, 0], seg[:, 1], seg[:, 2], color="0.55", linewidth=1.0)
    ax.scatter([0], [0], [0], c="black", marker="+", s=40, depthshade=False)
    for phone in range(n):
        ax.scatter(
            [coords[phone, 0]],
            [coords[phone, 1]],
            [coords[phone, 2]],
            c=HYDRO_COLORS[phone],
            s=42,
            depthshade=False,
        )
        ax.text(coords[phone, 0], coords[phone, 1], coords[phone, 2], f" H{phone}", fontsize=8)
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    ax.set_zlim(low, high)
    ax.set_box_aspect((1, 1, 1))
    ax.set_proj_type("ortho")
    ax.view_init(elev=22, azim=-58)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")


def _curve(rows, key: str, reducer) -> dict[int, list[float]]:
    curves = {}
    for count in COUNTS:
        values = []
        for snr in SNRS:
            selected = select(rows, count, snr)
            if key == "tdoa":
                series = pair_abs_errors(selected)
            elif key == "success":
                series = np.asarray([1.0 if success(row) else 0.0 for row in selected], dtype=float)
            else:
                series = success_metric(selected, key)
            values.append(reducer(series) if series.size else float("nan"))
        curves[count] = values
    return curves


def plot_vs_snr(rows: list[dict[str, str]]) -> None:
    _style()
    specs = (
        (
            "angular_error_deg",
            "Angular error (degrees)",
            "SIMULATION — angular error versus SNR",
            COMPARISONS / "angular_error_vs_snr.png",
        ),
        (
            "position_error_m",
            "3D position error (m)",
            "SIMULATION — position error versus SNR",
            COMPARISONS / "position_error_vs_snr.png",
        ),
        (
            "tdoa",
            "Absolute TDOA error (µs)",
            "SIMULATION — TDOA error versus SNR",
            TDOA / "tdoa_error_vs_snr.png",
        ),
    )
    for key, ylabel, title, path in specs:
        fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.2))
        medians = _curve(rows, key, lambda values: float(np.median(values)))
        tails = _curve(rows, key, lambda values: float(np.percentile(values, 95)))
        for count in COUNTS:
            axes[0].plot(
                SNRS,
                medians[count],
                color=COLORS[count],
                marker="o",
                linewidth=1.8,
                label=f"{count} hydrophones",
            )
            axes[1].plot(
                SNRS,
                tails[count],
                color=COLORS[count],
                marker="o",
                linestyle="--",
                linewidth=1.4,
                label=f"{count} hydrophones",
            )
        axes[0].set_title("Median")
        axes[1].set_title("95th percentile")
        for ax in axes:
            _snr_axis(ax)
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.35)
            ax.legend(loc="best", fontsize=8)
        fig.suptitle(
            title + "\nFailures are excluded from angle and position. The two panels use separate vertical scales.",
            fontsize=12,
        )
        fig.tight_layout()
        _save(fig, path.parent, path.name)

    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    rates = _curve(rows, "success", lambda values: float(np.mean(values)))
    for count in COUNTS:
        ax.plot(
            SNRS,
            [100.0 * value for value in rates[count]],
            color=COLORS[count],
            marker="o",
            linewidth=1.8,
            label=f"{count} hydrophones",
        )
    _snr_axis(ax)
    ax.set_ylim(-3, 105)
    ax.set_ylabel("Successful localization (%)")
    ax.set_title("SIMULATION — localization success versus SNR\nThe same solver rule is used for every sensor count.")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.35)
    _save(fig, COMPARISONS, "success_rate_vs_snr.png")


def _at_snr(rows, count: int, snr: float, key: str) -> np.ndarray:
    selected = select(rows, count, snr)
    if key == "tdoa":
        return pair_abs_errors(selected)
    return success_metric(selected, key)


def plot_vs_count(rows: list[dict[str, str]]) -> None:
    _style()
    snr = PRIMARY_SNR_DB
    angular = [_at_snr(rows, count, snr, "angular_error_deg") for count in COUNTS]
    position = [_at_snr(rows, count, snr, "position_error_m") for count in COUNTS]

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.2))
    _median_p95(axes[0], angular, "Angular error (degrees)")
    _median_p95(axes[1], position, "3D position error (m)")
    axes[0].set_title(f"Direction at {snr:.0f} dB")
    axes[1].set_title(f"Position at {snr:.0f} dB")
    fig.suptitle(
        "SIMULATION — localization error versus hydrophone count\n"
        "Degrees and metres are separate. Bars mark the 25th–75th percentile. Diamonds mark the 95th percentile.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, LOCALIZATION, "localization_error_vs_hydrophone_count.png")

    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    _median_p95(ax, angular, "Angular error (degrees)")
    ax.set_title(f"SIMULATION — angular error versus hydrophone count at {snr:.0f} dB")
    _save(fig, LOCALIZATION, "angular_error_vs_hydrophone_count.png")

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.2))
    _median_p95(axes[0], position, "3D position error (m)")
    position_0 = [_at_snr(rows, count, 0.0, "position_error_m") for count in COUNTS]
    _median_p95(axes[1], position_0, "3D position error (m)")
    axes[0].set_title("20 dB")
    axes[1].set_title("0 dB")
    fig.suptitle(
        "SIMULATION — position error versus hydrophone count\n"
        "The 95th percentile is shown so large errors stay visible.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, LOCALIZATION, "position_error_vs_hydrophone_count.png")

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    x = np.arange(len(COUNTS), dtype=float)
    width = 0.12
    offsets = (np.arange(len(SNRS)) - (len(SNRS) - 1) / 2.0) * width
    for offset, level in zip(offsets, SNRS):
        rates = []
        for count in COUNTS:
            selected = select(rows, count, level)
            rates.append(100.0 * sum(success(row) for row in selected) / len(selected))
        ax.bar(x + offset, rates, width=width * 0.92, label=f"{level:.0f} dB")
    ax.set_xticks(x)
    ax.set_xticklabels([str(count) for count in COUNTS])
    ax.set_xlabel("Number of hydrophones")
    ax.set_ylim(0, 108)
    ax.set_ylabel("Successful localization (%)")
    ax.set_title("SIMULATION — success rate versus hydrophone count\nFailures are counted as failures, not as zero error.")
    ax.legend(title="SNR", ncol=3)
    ax.grid(True, axis="y", alpha=0.35)
    _save(fig, LOCALIZATION, "success_rate_vs_hydrophone_count.png")


def _median_p95(ax: plt.Axes, series: list[np.ndarray], ylabel: str) -> None:
    x = np.arange(len(COUNTS), dtype=float)
    medians = [float(np.median(values)) if values.size else np.nan for values in series]
    low = [float(np.percentile(values, 25)) if values.size else np.nan for values in series]
    high = [float(np.percentile(values, 75)) if values.size else np.nan for values in series]
    tail = [float(np.percentile(values, 95)) if values.size else np.nan for values in series]
    yerr = np.vstack([np.asarray(medians) - np.asarray(low), np.asarray(high) - np.asarray(medians)])
    ax.errorbar(
        x,
        medians,
        yerr=yerr,
        fmt="o",
        color="#0072B2",
        capsize=4,
        linewidth=1.6,
        label="median, 25th–75th",
    )
    ax.plot(x, tail, linestyle="none", marker="D", color="#D55E00", label="95th percentile")
    ax.set_xticks(x)
    ax.set_xticklabels([str(count) for count in COUNTS])
    ax.set_xlabel("Number of hydrophones")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")


def make_all(rows: list[dict[str, str]]) -> None:
    plot_arrays()
    plot_vs_snr(rows)
    plot_vs_count(rows)
