"""Figures for localization error, its distribution, success rate, and angle.

Every figure is a simulation. Position-error axes are logarithmic because a
small array produces a long error tail. Failed solves are omitted from the
error figures and counted in the success-rate figure.

The line plots draw the mean and the median. The shaded band is the
25th–75th percentile. A ±1 standard-deviation bar is not drawn: at every
SNR in this study the standard deviation is larger than the mean, so that
bar would cross zero and hide the trend. The standard deviation remains in
the summary CSV, and the box plot shows the outliers that produce it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulations.noise_study.analysis import finite_snr_levels, is_noise_free, is_success

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


def _success_values(
    rows: list[dict[str, Any]],
    snr: float | None,
    key: str,
    *,
    noise_free: bool,
) -> np.ndarray:
    selected: list[float] = []
    for row in rows:
        if is_noise_free(row) != noise_free:
            continue
        if not noise_free and float(row["snr_db"]) != float(snr):
            continue
        if is_success(row) and np.isfinite(float(row[key])):
            selected.append(float(row[key]))
    return np.asarray(selected, dtype=float)


def _quartile_band(
    rows: list[dict[str, Any]],
    snr_levels: list[float],
    key: str,
) -> tuple[np.ndarray, np.ndarray]:
    lower = []
    upper = []
    for snr in snr_levels:
        values = _success_values(rows, snr, key, noise_free=False)
        positive = values[np.isfinite(values) & (values > 0.0)]
        if positive.size == 0:
            lower.append(np.nan)
            upper.append(np.nan)
        else:
            q25, q75 = np.percentile(positive, [25, 75])
            lower.append(float(q25))
            upper.append(float(q75))
    return np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)


def _plot_mean_and_band(
    ax: plt.Axes,
    snr_levels: list[float],
    means: np.ndarray,
    medians: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> None:
    x = np.asarray(snr_levels, dtype=float)
    ax.fill_between(
        x,
        lower,
        upper,
        color=MEAN_COLOR,
        alpha=0.18,
        label="25th–75th percentile",
        zorder=1,
    )
    ax.plot(
        x,
        means,
        marker="o",
        color=MEAN_COLOR,
        linewidth=1.8,
        label="mean",
        zorder=3,
    )
    ax.plot(
        x,
        medians,
        marker="s",
        color=MEDIAN_COLOR,
        linestyle="--",
        linewidth=1.4,
        label="median",
        zorder=3,
    )


def _mark_noise_free(ax: plt.Axes, value: float | None, label: str) -> None:
    if value is None or not np.isfinite(value):
        return
    ax.axhline(value, color="0.35", linestyle=":", linewidth=1.3, label=label, zorder=1)


def plot_localization_error_vs_snr(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    means = np.array([_lookup(summary, snr, "mean_localization_error_m") for snr in snr_levels])
    medians = np.array([_lookup(summary, snr, "median_localization_error_m") for snr in snr_levels])
    lower, upper = _quartile_band(rows, snr_levels, "localization_error_m")
    _plot_mean_and_band(ax, snr_levels, means, medians, lower, upper)
    _mark_noise_free(
        ax,
        _noise_free_value(summary, "mean_localization_error_m"),
        "noise-free mean",
    )
    ax.set_yscale("log")
    _snr_axis(ax, snr_levels)
    ax.set_ylabel("Localization error (m)")
    ax.set_title(
        "Localization error versus SNR\n"
        "SIMULATION — successful solves only; band is the 25th–75th percentile; dashed line is the median"
    )
    ax.legend(loc="best")
    ax.grid(True, which="both", alpha=0.35)
    _save(fig, path)


def plot_angular_error_vs_snr(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    means = np.array([_lookup(summary, snr, "mean_angular_error_deg") for snr in snr_levels])
    medians = np.array([_lookup(summary, snr, "median_angular_error_deg") for snr in snr_levels])
    lower, upper = _quartile_band(rows, snr_levels, "angular_error_deg")
    _plot_mean_and_band(ax, snr_levels, means, medians, lower, upper)
    _mark_noise_free(
        ax,
        _noise_free_value(summary, "mean_angular_error_deg"),
        "noise-free mean",
    )
    positive = np.concatenate(
        [
            means[np.isfinite(means) & (means > 0.0)],
            medians[np.isfinite(medians) & (medians > 0.0)],
        ]
    )
    if positive.size:
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


def plot_success_rate_vs_snr(
    summary: list[dict[str, Any]],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    rates = np.array(
        [_lookup(summary, snr, "localization_success_rate") * 100.0 for snr in snr_levels]
    )
    ax.plot(
        snr_levels,
        rates,
        marker="o",
        color=MEAN_COLOR,
        linewidth=1.8,
        label="success rate",
    )
    noise_free = _noise_free_value(summary, "localization_success_rate")
    if noise_free is not None and np.isfinite(noise_free):
        _mark_noise_free(ax, 100.0 * noise_free, "noise-free success rate")
    _snr_axis(ax, snr_levels)
    ax.set_ylim(0.0, 112.0)
    ax.set_ylabel("Successful localizations (%)")
    ax.set_title(
        "Localization success rate versus SNR\n"
        "SIMULATION — a rejected solve is a failure, not a zero error"
    )
    ax.legend(loc="best")
    ax.grid(True, alpha=0.35)
    _save(fig, path)


def _errors_for(
    rows: list[dict[str, Any]],
    *,
    snr: float | None,
    noise_free: bool,
    key: str,
) -> np.ndarray:
    selected: list[float] = []
    for row in rows:
        if is_noise_free(row) != noise_free:
            continue
        if not noise_free and float(row["snr_db"]) != float(snr):
            continue
        if is_success(row) and np.isfinite(float(row[key])) and float(row[key]) > 0.0:
            selected.append(float(row[key]))
    return np.asarray(selected, dtype=float)


def plot_localization_error_distribution(
    rows: list[dict[str, Any]],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(10.2, 5.8))
    include_noise_free = any(is_noise_free(row) for row in rows)
    series: list[np.ndarray] = []
    labels: list[str] = []
    if include_noise_free:
        values = _errors_for(rows, snr=None, noise_free=True, key="localization_error_m")
        series.append(values)
        labels.append(_box_label("noise-free", values))
    # Quiet conditions on the left, matching the reversed SNR axis of the line plots.
    for snr in sorted((float(level) for level in snr_levels), reverse=True):
        values = _errors_for(rows, snr=snr, noise_free=False, key="localization_error_m")
        series.append(values)
        labels.append(_box_label(f"{snr:.0f} dB", values))

    drawable = []
    positions = []
    for index, values in enumerate(series):
        if values.size:
            drawable.append(values)
            positions.append(index)
    if drawable:
        ax.boxplot(
            drawable,
            positions=positions,
            widths=0.55,
            showfliers=True,
            patch_artist=True,
            medianprops={"color": "black", "linewidth": 1.4},
            boxprops={"facecolor": "#d6e6f5"},
        )
        ax.set_yscale("log")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_xlabel("SNR (dB) — noise increases to the right")
    ax.set_ylabel("Localization error (m)")
    ax.set_title(
        "Localization error distribution versus SNR\n"
        "SIMULATION — successful solves only; the line inside each box is the median; outliers are drawn"
    )
    ax.grid(True, axis="y", which="both", alpha=0.35)
    _save(fig, path)


def _box_label(name: str, values: np.ndarray) -> str:
    if values.size == 0:
        return f"{name}\nno successes"
    median = float(np.median(values))
    return f"{name}\nmedian {median:.2f} m\nn={values.size}"


def save_noise_figures(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    figures_dir: Path,
    snr_levels: list[float] | None = None,
) -> list[Path]:
    """Write the four SNR figures and return their paths."""
    levels = list(snr_levels) if snr_levels is not None else finite_snr_levels(rows)
    paths = [
        figures_dir / "localization_error_vs_snr.png",
        figures_dir / "localization_error_distribution_vs_snr.png",
        figures_dir / "success_rate_vs_snr.png",
        figures_dir / "angular_error_vs_snr.png",
    ]
    plot_localization_error_vs_snr(rows, summary, levels, paths[0])
    plot_localization_error_distribution(rows, levels, paths[1])
    plot_success_rate_vs_snr(summary, levels, paths[2])
    plot_angular_error_vs_snr(rows, summary, levels, paths[3])
    return paths
