"""Report figures for the pulsed-pinger waveform experiment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulations.waveform_study.analysis import is_noise_free, is_success, pair_abs_errors_us

HYDRO_COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00")
MEAN_COLOR = "#0072B2"
MEDIAN_COLOR = "#D55E00"


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
            "legend.fontsize": 9,
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _snr_axis(ax: plt.Axes, snr_levels: list[float]) -> None:
    ordered = sorted(float(snr) for snr in snr_levels)
    ax.set_xlim(ordered[-1] + 3.0, ordered[0] - 3.0)
    ax.set_xticks(ordered)
    ax.set_xlabel("SNR (dB) — noise increases to the right")


def _rows_at(rows: list[dict[str, Any]], snr: float) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if not is_noise_free(row) and float(row["snr_db"]) == float(snr)
    ]


def _lookup(summary: list[dict[str, Any]], snr: float, key: str) -> float:
    for row in summary:
        if is_noise_free(row):
            continue
        if float(row["snr_db"]) == float(snr):
            return float(row[key])
    return float("nan")


def _noise_free_value(summary: list[dict[str, Any]], key: str) -> float | None:
    for row in summary:
        if is_noise_free(row):
            return float(row[key])
    return None


def plot_waveforms(example: dict[str, Any], path: Path) -> None:
    """Raw hydrophone channels, with a zoom on the leading edge."""
    _apply_style()
    channels = np.asarray(example["channels"], dtype=float)
    fs = float(example["fs"])
    time_ms = np.arange(channels.shape[1]) / fs * 1e3
    envelope = np.max(np.abs(channels), axis=0)
    peak_value = float(np.max(envelope))
    above = np.flatnonzero(envelope >= 0.2 * peak_value) if peak_value > 0 else np.array([0])
    onset = int(above[0]) if above.size else int(np.argmax(envelope))
    pulse_end = int(above[-1]) if above.size else onset
    zoom_start = max(0, onset - int(0.08e-3 * fs))
    zoom_stop = min(channels.shape[1], zoom_start + int(0.45e-3 * fs))
    view_start = max(0, onset - int(0.4e-3 * fs))
    view_stop = min(channels.shape[1] - 1, pulse_end + int(0.4e-3 * fs))

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 6.6))
    for index in range(channels.shape[0]):
        axes[0].plot(
            time_ms,
            channels[index],
            color=HYDRO_COLORS[index % len(HYDRO_COLORS)],
            linewidth=0.8,
            label=f"H{index}",
        )
        axes[1].plot(
            time_ms[zoom_start:zoom_stop],
            channels[index, zoom_start:zoom_stop],
            color=HYDRO_COLORS[index % len(HYDRO_COLORS)],
            linewidth=1.2,
            label=f"H{index}",
        )
    axes[0].set_xlim(time_ms[view_start], time_ms[view_stop])
    axes[0].set_ylabel("Amplitude")
    axes[0].set_title("Received pinger waveforms")
    axes[0].legend(loc="upper right", ncol=4)
    axes[1].set_ylabel("Amplitude")
    axes[1].set_xlabel("Time (ms)")
    axes[1].set_title("Onset of the same pulse on each hydrophone")
    axes[1].legend(loc="upper right", ncol=4)
    geometry_name = str(example.get("geometry_name") or "tetrahedral").replace("_", " ")
    fig.suptitle(
        f"SIMULATION — noise-free 40 kHz, 4 ms pulse on the {geometry_name} array",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, path)


def plot_gcc(example: dict[str, Any], path: Path) -> None:
    """GCC-PHAT trace for H1 relative to H0, with the selected peak marked."""
    _apply_style()
    diagnostics = example["diagnostics"]
    diagnostic = diagnostics[1]
    if diagnostic is None:
        raise RuntimeError("representative capture has no H1 GCC-PHAT trace")
    row = example["row"]
    lags_us = np.asarray(diagnostic.lags_seconds) * 1e6
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    ax.plot(lags_us, diagnostic.correlation, color=MEAN_COLOR, linewidth=1.2, label="GCC-PHAT")
    peak_us = float(diagnostic.lags_seconds[diagnostic.peak_index] * 1e6)
    ax.axvline(peak_us, color=MEDIAN_COLOR, linewidth=1.4, label=f"estimated peak ({peak_us:.2f} µs)")
    true_us = float(row["true_tdoa_h1_us"])
    ax.axvline(true_us, color="0.2", linestyle="--", linewidth=1.2, label=f"theoretical TDOA ({true_us:.2f} µs)")
    ax.set_xlabel("Lag (µs) — positive means H1 arrives later than H0")
    ax.set_ylabel("PHAT correlation")
    ax.set_title(
        "GCC-PHAT delay estimate, H1 relative to H0\n"
        "SIMULATION — noise-free 40 kHz pulse; search limited to the array baseline"
    )
    ax.legend(loc="best")
    _save(fig, path)


def _band(rows: list[dict[str, Any]], snr_levels: list[float], key: str) -> tuple[np.ndarray, np.ndarray]:
    lower = []
    upper = []
    for snr in snr_levels:
        values = [
            float(row[key])
            for row in _rows_at(rows, snr)
            if is_success(row) and np.isfinite(float(row[key])) and float(row[key]) > 0.0
        ]
        if not values:
            lower.append(np.nan)
            upper.append(np.nan)
        else:
            q25, q75 = np.percentile(np.asarray(values, dtype=float), [25, 75])
            lower.append(float(q25))
            upper.append(float(q75))
    return np.asarray(lower), np.asarray(upper)


def _plot_mean_median(
    ax: plt.Axes,
    snr_levels: list[float],
    means: np.ndarray,
    medians: np.ndarray,
    lower: np.ndarray | None = None,
    upper: np.ndarray | None = None,
) -> None:
    x = np.asarray(snr_levels, dtype=float)
    if lower is not None and upper is not None:
        ax.fill_between(x, lower, upper, color=MEAN_COLOR, alpha=0.18, label="25th–75th percentile", zorder=1)
    ax.plot(x, means, marker="o", color=MEAN_COLOR, linewidth=1.8, label="mean", zorder=3)
    ax.plot(x, medians, marker="s", color=MEDIAN_COLOR, linestyle="--", linewidth=1.4, label="median", zorder=3)


def plot_tdoa_error_vs_snr(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    means = np.array([_lookup(summary, snr, "mean_abs_tdoa_error_us") for snr in snr_levels])
    medians = np.array([_lookup(summary, snr, "median_abs_tdoa_error_us") for snr in snr_levels])
    lower = []
    upper = []
    for snr in snr_levels:
        values = []
        for row in _rows_at(rows, snr):
            values.extend(error for error in pair_abs_errors_us(row) if np.isfinite(error) and error > 0.0)
        if not values:
            lower.append(np.nan)
            upper.append(np.nan)
        else:
            q25, q75 = np.percentile(np.asarray(values), [25, 75])
            lower.append(float(q25))
            upper.append(float(q75))
    _plot_mean_median(ax, snr_levels, means, medians, np.asarray(lower), np.asarray(upper))
    noise_free = _noise_free_value(summary, "median_abs_tdoa_error_us")
    if noise_free is not None and np.isfinite(noise_free):
        ax.axhline(noise_free, color="0.35", linestyle=":", linewidth=1.3, label="noise-free median")
    positive = medians[np.isfinite(medians) & (medians > 0)]
    if positive.size:
        ax.set_yscale("log")
    _snr_axis(ax, snr_levels)
    ax.set_ylabel("Absolute TDOA error (µs)")
    ax.set_title(
        "TDOA estimation error versus SNR\n"
        "SIMULATION — GCC-PHAT on the pinger waveform, compared with the geometric TDOA"
    )
    ax.legend(loc="best")
    ax.grid(True, which="both", alpha=0.35)
    _save(fig, path)


def plot_localization_error_vs_snr(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    means = np.array([_lookup(summary, snr, "mean_localization_error_m") for snr in snr_levels])
    medians = np.array([_lookup(summary, snr, "median_localization_error_m") for snr in snr_levels])
    lower, upper = _band(rows, snr_levels, "localization_error_m")
    _plot_mean_median(ax, snr_levels, means, medians, lower, upper)
    noise_free = _noise_free_value(summary, "mean_localization_error_m")
    if noise_free is not None and np.isfinite(noise_free) and noise_free > 0:
        ax.axhline(noise_free, color="0.35", linestyle=":", linewidth=1.3, label="noise-free mean")
    ax.set_yscale("log")
    _snr_axis(ax, snr_levels)
    ax.set_ylabel("Localization error (m)")
    ax.set_title(
        "Localization error versus SNR\n"
        "SIMULATION — position from estimated TDOAs; successful solves only"
    )
    ax.legend(loc="best")
    ax.grid(True, which="both", alpha=0.35)
    _save(fig, path)


def plot_success_vs_snr(summary: list[dict[str, Any]], snr_levels: list[float], path: Path) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    rates = np.array([_lookup(summary, snr, "localization_success_rate") * 100.0 for snr in snr_levels])
    ax.plot(snr_levels, rates, marker="o", color=MEAN_COLOR, linewidth=1.8, label="success rate")
    noise_free = _noise_free_value(summary, "localization_success_rate")
    if noise_free is not None and np.isfinite(noise_free):
        ax.axhline(100.0 * noise_free, color="0.35", linestyle=":", linewidth=1.3, label="noise-free success rate")
    _snr_axis(ax, snr_levels)
    ax.set_ylim(0.0, 112.0)
    ax.set_ylabel("Successful localizations (%)")
    ax.set_title(
        "Localization success rate versus SNR\n"
        "SIMULATION — a rejected solve is a failure, not a zero error"
    )
    ax.legend(loc="best")
    _save(fig, path)


def plot_angular_vs_snr(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    means = np.array([_lookup(summary, snr, "mean_angular_error_deg") for snr in snr_levels])
    medians = np.array([_lookup(summary, snr, "median_angular_error_deg") for snr in snr_levels])
    lower, upper = _band(rows, snr_levels, "angular_error_deg")
    _plot_mean_median(ax, snr_levels, means, medians, lower, upper)
    noise_free = _noise_free_value(summary, "mean_angular_error_deg")
    if noise_free is not None and np.isfinite(noise_free) and noise_free > 0:
        ax.axhline(noise_free, color="0.35", linestyle=":", linewidth=1.3, label="noise-free mean")
    if np.any(np.isfinite(medians) & (medians > 0)):
        ax.set_yscale("log")
    _snr_axis(ax, snr_levels)
    ax.set_ylabel("Angular error (deg)")
    ax.set_title(
        "Angular error versus SNR\n"
        "SIMULATION — angle between true and estimated direction; successful solves only"
    )
    ax.legend(loc="best")
    ax.grid(True, which="both", alpha=0.35)
    _save(fig, path)


def plot_frequency_comparison(summary: list[dict[str, Any]], path: Path) -> None:
    """Median TDOA and localization error against carrier frequency."""
    _apply_style()
    carriers = sorted({float(row["carrier_frequency_hz"]) for row in summary})
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.8))

    def _series(noise_free: bool, snr: float | None, key: str) -> list[float]:
        values = []
        for carrier in carriers:
            match = [
                row
                for row in summary
                if float(row["carrier_frequency_hz"]) == carrier
                and is_noise_free(row) == noise_free
                and (noise_free or float(row["snr_db"]) == float(snr))
            ]
            values.append(float(match[0][key]) if match else float("nan"))
        return values

    khz = [carrier / 1000.0 for carrier in carriers]
    axes[0].plot(khz, _series(True, None, "median_abs_tdoa_error_us"), marker="o", label="noise-free")
    axes[0].plot(khz, _series(False, 20.0, "median_abs_tdoa_error_us"), marker="s", label="20 dB")
    axes[0].set_xlabel("Carrier frequency (kHz)")
    axes[0].set_ylabel("Median |TDOA error| (µs)")
    axes[0].set_title("TDOA error")
    axes[0].legend(loc="best")
    axes[1].plot(khz, _series(True, None, "median_localization_error_m"), marker="o", label="noise-free")
    axes[1].plot(khz, _series(False, 20.0, "median_localization_error_m"), marker="s", label="20 dB")
    axes[1].set_xlabel("Carrier frequency (kHz)")
    axes[1].set_ylabel("Median localization error (m)")
    axes[1].set_title("Localization error")
    axes[1].legend(loc="best")
    fig.suptitle(
        "SIMULATION — carrier comparison on the same 25 sources",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, path)


def save_waveform_figures(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    example: dict[str, Any],
    figures_dir: Path,
    snr_levels: list[float],
    frequency_summary: list[dict[str, Any]] | None = None,
) -> list[Path]:
    paths = [
        figures_dir / "hydrophone_waveforms.png",
        figures_dir / "gcc_phat_example.png",
        figures_dir / "tdoa_error_vs_snr.png",
        figures_dir / "localization_error_vs_snr.png",
        figures_dir / "success_rate_vs_snr.png",
        figures_dir / "angular_error_vs_snr.png",
    ]
    plot_waveforms(example, paths[0])
    plot_gcc(example, paths[1])
    plot_tdoa_error_vs_snr(rows, summary, snr_levels, paths[2])
    plot_localization_error_vs_snr(rows, summary, snr_levels, paths[3])
    plot_success_vs_snr(summary, snr_levels, paths[4])
    plot_angular_vs_snr(rows, summary, snr_levels, paths[5])
    if frequency_summary:
        freq_path = figures_dir / "frequency_comparison.png"
        plot_frequency_comparison(frequency_summary, freq_path)
        paths.append(freq_path)
    return paths
