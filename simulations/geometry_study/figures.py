"""Presentation figures for the hydrophone geometry simulation study.

Every figure is labeled as a simulation. Axis labels carry units. Comparison
plots use one color per geometry and do not drop outliers from the drawn data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers the 3D projection)

from simulations.geometry_study.analysis import is_success, tdoa_abs_errors_us
from src.geometry import HydrophoneArray

GEOM_COLORS = {
    "linear": "#0072B2",
    "square_planar": "#E69F00",
    "cross_planar": "#009E73",
    "tetrahedral": "#D55E00",
    "three_plus_one": "#CC79A7",
}
HYDRO_COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00")
ARRAY_LIMIT_M = 0.20


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


def _style_array_axes(ax: plt.Axes) -> None:
    ax.set_xlim(-ARRAY_LIMIT_M, ARRAY_LIMIT_M)
    ax.set_ylim(-ARRAY_LIMIT_M, ARRAY_LIMIT_M)
    ax.set_zlim(-ARRAY_LIMIT_M, ARRAY_LIMIT_M)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_box_aspect((1.0, 1.0, 1.0))
    ax.set_proj_type("ortho")
    ax.view_init(elev=22, azim=-58)
    ax.grid(True, alpha=0.3)


def _draw_array(ax: plt.Axes, array: HydrophoneArray, show_legend: bool = True) -> None:
    coords = array.coordinates_m
    for i, j in array.edges:
        segment = coords[[i, j]]
        ax.plot(
            segment[:, 0],
            segment[:, 1],
            segment[:, 2],
            color="0.45",
            linewidth=1.3,
            zorder=1,
        )
    ax.scatter([0.0], [0.0], [0.0], c="black", marker="+", s=70, label="origin", zorder=2, depthshade=False)
    for index in range(4):
        ax.scatter(
            [coords[index, 0]],
            [coords[index, 1]],
            [coords[index, 2]],
            c=HYDRO_COLORS[index],
            s=48,
            depthshade=False,
            label=f"H{index}",
            zorder=3,
        )
        direction = coords[index]
        norm = float(np.linalg.norm(direction))
        if norm == 0.0:
            direction = np.array([1.0, 1.0, 1.0])
            norm = float(np.linalg.norm(direction))
        label_at = coords[index] + 0.02 * direction / norm
        ax.text(label_at[0], label_at[1], label_at[2], f"H{index}", fontsize=9)
    if show_legend:
        ax.legend(loc="upper left", fontsize=8)


def plot_geometry(array: HydrophoneArray, path: Path) -> None:
    _apply_style()
    fig = plt.figure(figsize=(7.2, 6.2))
    ax = fig.add_subplot(111, projection="3d")
    _draw_array(ax, array)
    _style_array_axes(ax)
    baseline = array.max_pairwise_distance_m()
    ax.set_title(
        f"{array.name} array\n"
        f"SIMULATION geometry  |  max hydrophone separation {baseline:.3f} m"
    )
    _save(fig, path)


def plot_all_geometries(arrays: list[HydrophoneArray], path: Path) -> None:
    _apply_style()
    fig = plt.figure(figsize=(14.5, 8.6))
    for index, array in enumerate(arrays):
        ax = fig.add_subplot(2, 3, index + 1, projection="3d")
        _draw_array(ax, array, show_legend=False)
        _style_array_axes(ax)
        ax.set_title(f"{array.name}\n{array.max_pairwise_distance_m():.3f} m max separation", fontsize=11)
    note = fig.add_subplot(2, 3, 6)
    note.axis("off")
    note.text(
        0.0,
        0.55,
        "Shared axis limits: ±0.20 m\n"
        "Orthographic projection\n"
        "Origin marked with +\n"
        "H0 blue, H1 orange,\n"
        "H2 green, H3 vermillion\n\n"
        "SIMULATION\n"
        "Identical scale on every panel.\n"
        "Units are metres.",
        fontsize=11,
        va="center",
        family="sans-serif",
    )
    fig.suptitle("Five four-hydrophone array geometries (SIMULATION)", fontsize=15)
    fig.tight_layout()
    _save(fig, path)


def plot_propagation(
    array: HydrophoneArray,
    source_m: np.ndarray,
    distances_m: np.ndarray,
    tdoas_us: np.ndarray,
    path: Path,
) -> None:
    _apply_style()
    fig = plt.figure(figsize=(8.4, 7.2))
    ax = fig.add_subplot(111, projection="3d")
    coords = array.coordinates_m
    source_m = np.asarray(source_m, dtype=float)
    for index in range(4):
        ax.plot(
            [source_m[0], coords[index, 0]],
            [source_m[1], coords[index, 1]],
            [source_m[2], coords[index, 2]],
            color=HYDRO_COLORS[index],
            linewidth=1.2,
            alpha=0.85,
        )
        ax.scatter(
            [coords[index, 0]],
            [coords[index, 1]],
            [coords[index, 2]],
            c=HYDRO_COLORS[index],
            s=36,
            depthshade=False,
            label=f"H{index}: {distances_m[index]:.3f} m, TDOA {tdoas_us[index]:+.1f} us",
        )
    ax.scatter([0.0], [0.0], [0.0], c="black", marker="+", s=50, depthshade=False, label="array origin")
    ax.scatter(
        [source_m[0]],
        [source_m[1]],
        [source_m[2]],
        c="black",
        marker="*",
        s=90,
        depthshade=False,
        label="source",
    )
    # Coordinates stay in the title. A 3D text label sits on top of the
    # source marker and becomes unreadable at this scale.
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_box_aspect((1.0, 1.0, 1.0))
    ax.view_init(elev=18, azim=-58)
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title(
        f"{array.name}: source at ({source_m[0]:.2f}, {source_m[1]:.2f}, {source_m[2]:.2f}) m\n"
        "SIMULATION — lines are geometric paths from the source to each hydrophone"
    )
    _save(fig, path)


def plot_waveforms(
    array: HydrophoneArray,
    window: np.ndarray,
    fs: float,
    path: Path,
) -> None:
    _apply_style()
    energy = np.mean(window**2, axis=0)
    peak = float(np.max(energy))
    if peak > 0:
        above = np.flatnonzero(energy >= 0.2 * peak)
        edge = int(above[0]) if above.size else int(np.argmax(energy))
    else:
        edge = window.shape[1] // 3
    time_ms = np.arange(window.shape[1]) / fs * 1e3
    edge_ms = time_ms[edge]

    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.2), sharey=False)
    spans = (
        (edge_ms - 0.25, edge_ms + 2.4, "Arrival of the shared chirp"),
        (edge_ms - 0.04, edge_ms + 0.28, "Leading edge, expanded"),
    )
    for ax, (start_ms, stop_ms, subtitle) in zip(axes, spans):
        for index in range(window.shape[0]):
            ax.plot(
                time_ms,
                window[index],
                color=HYDRO_COLORS[index],
                linewidth=1.15,
                label=f"H{index}",
            )
        ax.set_xlim(start_ms, stop_ms)
        ax.set_ylabel("Amplitude")
        ax.set_title(subtitle)
        ax.grid(True, alpha=0.35)
    axes[0].legend(loc="upper right", ncol=4)
    axes[1].set_xlabel("Time from start of the common window (ms)")
    fig.suptitle(
        f"{array.name}: four preprocessed channels, one common window\n"
        "SIMULATION — channels were not shifted to line up; the time offsets are the arrivals",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, path)


def plot_gcc(
    array: HydrophoneArray,
    diagnostics: list,
    true_tdoa_s: np.ndarray,
    estimated_tdoa_s: np.ndarray,
    path: Path,
) -> None:
    _apply_style()
    fig, axes = plt.subplots(3, 1, figsize=(10.2, 8.0), sharex=True)
    for axis_index, channel in enumerate((1, 2, 3)):
        ax = axes[axis_index]
        result = diagnostics[channel]
        lags_us = result.lags_seconds * 1e6
        ax.plot(lags_us, result.correlation, color="#0072B2", linewidth=1.0, label="GCC-PHAT")
        true_us = float(true_tdoa_s[channel] * 1e6)
        est_us = float(estimated_tdoa_s[channel] * 1e6)
        ax.axvline(true_us, color="#000000", linestyle="--", linewidth=1.2, label="true TDOA")
        ax.axvline(est_us, color="#D55E00", linestyle="-", linewidth=1.2, label="estimated peak")
        ax.scatter([est_us], [result.peak_value], color="#D55E00", s=28, zorder=3)
        ax.set_ylabel(f"H{channel}−H0")
        ax.grid(True, alpha=0.35)
        ax.set_title(
            f"true {true_us:+.2f} us, estimated {est_us:+.2f} us, "
            f"absolute error {abs(est_us - true_us):.2f} us",
            fontsize=10,
            loc="left",
        )
    axes[0].legend(loc="upper right")
    axes[-1].set_xlabel("Lag (microseconds)")
    fig.suptitle(
        f"{array.name}: GCC-PHAT against H0\n"
        "SIMULATION — positive lag means that channel arrives later than H0",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, path)


def _rows_for(rows: list[dict[str, Any]], geometry: str, snr_db: float | None = None) -> list[dict[str, Any]]:
    selected = [row for row in rows if row["geometry"] == geometry]
    if snr_db is not None:
        selected = [row for row in selected if float(row["snr_db"]) == float(snr_db)]
    return selected


def plot_true_vs_estimated(rows: list[dict[str, Any]], arrays: list[HydrophoneArray], path: Path) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(7.6, 7.2))
    limit = 0.0
    for array in arrays:
        true_values = []
        est_values = []
        for row in _rows_for(rows, array.key):
            for suffix in ("h1", "h2", "h3"):
                true_us = float(row[f"true_tdoa_{suffix}_us"])
                est_us = float(row[f"est_tdoa_{suffix}_us"])
                if np.isfinite(true_us) and np.isfinite(est_us):
                    true_values.append(true_us)
                    est_values.append(est_us)
        ax.scatter(
            true_values,
            est_values,
            s=10,
            alpha=0.28,
            c=GEOM_COLORS[array.key],
            linewidths=0,
            label=array.name,
            zorder=2,
        )
        if true_values:
            limit = max(limit, float(np.max(np.abs(true_values))), float(np.max(np.abs(est_values))))
    limit = max(limit * 1.05, 1.0)
    ax.plot([-limit, limit], [-limit, limit], color="black", linewidth=1.2, label="y = x", zorder=3)
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("True TDOA (us)")
    ax.set_ylabel("Estimated TDOA (us)")
    ax.set_title("True versus estimated TDOA, all geometries and SNRs\nSIMULATION — outliers are included")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.35)
    _save(fig, path)


def _boxplot_with_gaps(
    arrays: list[HydrophoneArray],
    series: list[np.ndarray],
    ylabel: str,
    title: str,
    path: Path,
    value_format: str,
    log_y: bool = False,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(10.4, 6.2))
    drawable = []
    positions = []
    labels = []
    finite_values = []
    for index, (array, values) in enumerate(zip(arrays, series)):
        finite = values[np.isfinite(values)] if values.size else values
        if finite.size:
            drawable.append(finite)
            positions.append(index)
            finite_values.append(finite)
            median = float(np.median(finite))
            labels.append(f"{array.name}\nmedian {median:{value_format}}\nn={finite.size}")
        else:
            labels.append(f"{array.name}\nnot observable")
    if drawable:
        ax.boxplot(
            drawable,
            positions=positions,
            widths=0.55,
            showfliers=True,
            patch_artist=True,
            medianprops={"color": "black", "linewidth": 1.4},
            boxprops={"facecolor": "#f4f4f4"},
        )
    if log_y and drawable:
        ax.set_yscale("log")
        title = title + "\nVertical axis is logarithmic; outliers are still plotted."
    ax.set_xticks(range(len(arrays)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.35)
    _save(fig, path)


def plot_tdoa_error_by_geometry(
    rows: list[dict[str, Any]],
    arrays: list[HydrophoneArray],
    snr_db: float,
    path: Path,
) -> None:
    series = []
    for array in arrays:
        errors = []
        for row in _rows_for(rows, array.key, snr_db):
            errors.extend(tdoa_abs_errors_us(row))
        series.append(np.asarray(errors, dtype=float))
    _boxplot_with_gaps(
        arrays,
        series,
        ylabel="Absolute TDOA error (us)",
        title=(
            f"Absolute TDOA error by geometry at {snr_db:.0f} dB SNR\n"
            "SIMULATION — each point is one non-reference pair; the line inside the box is the median"
        ),
        path=path,
        value_format=".3f",
    )


def plot_angular_error_by_geometry(
    rows: list[dict[str, Any]],
    arrays: list[HydrophoneArray],
    snr_db: float,
    path: Path,
) -> None:
    series = []
    for array in arrays:
        values = [
            float(row["angular_error_deg"])
            for row in _rows_for(rows, array.key, snr_db)
            if is_success(row)
        ]
        series.append(np.asarray(values, dtype=float))
    _boxplot_with_gaps(
        arrays,
        series,
        ylabel="Angular error (deg)",
        title=(
            f"Angular error by geometry at {snr_db:.0f} dB SNR\n"
            "SIMULATION — only successful solves; failed and degenerate trials are not drawn as 0 deg"
        ),
        path=path,
        value_format=".2f",
    )


def plot_position_error_by_geometry(
    rows: list[dict[str, Any]],
    arrays: list[HydrophoneArray],
    snr_db: float,
    path: Path,
) -> None:
    series = []
    for array in arrays:
        values = [
            float(row["position_error_m"])
            for row in _rows_for(rows, array.key, snr_db)
            if is_success(row)
        ]
        series.append(np.asarray(values, dtype=float))
    _boxplot_with_gaps(
        arrays,
        series,
        ylabel="Position error (m)",
        title=(
            f"Position error by geometry at {snr_db:.0f} dB SNR\n"
            "SIMULATION — only successful solves; failed trials are omitted here and counted in the success-rate figure"
        ),
        path=path,
        value_format=".2f",
        log_y=True,
    )


def _snr_axis(ax: plt.Axes, snr_levels: list[float]) -> None:
    ordered = sorted(float(snr) for snr in snr_levels)
    ax.set_xlim(ordered[-1] + 3.0, ordered[0] - 3.0)
    ax.set_xticks(ordered)
    ax.set_xlabel("SNR (dB) — noise increases to the right")


def plot_tdoa_error_vs_snr(
    rows: list[dict[str, Any]],
    arrays: list[HydrophoneArray],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(9.4, 6.0))
    for array in arrays:
        medians = []
        tails = []
        for snr in snr_levels:
            errors = []
            for row in _rows_for(rows, array.key, snr):
                errors.extend(error for error in tdoa_abs_errors_us(row) if np.isfinite(error))
            values = np.asarray(errors, dtype=float)
            medians.append(float(np.median(values)) if values.size else np.nan)
            tails.append(float(np.percentile(values, 95)) if values.size else np.nan)
        color = GEOM_COLORS[array.key]
        ax.plot(snr_levels, medians, marker="o", color=color, linewidth=1.8, label=array.name)
        ax.plot(snr_levels, tails, marker=None, color=color, linewidth=1.0, linestyle="--")
    _snr_axis(ax, snr_levels)
    ax.set_ylabel("Absolute TDOA error (us)")
    ax.set_title(
        "TDOA error versus SNR\n"
        "SIMULATION — solid line is the median, dashed line is the 95th percentile"
    )
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.35)
    _save(fig, path)


def plot_localization_error_vs_snr(
    rows: list[dict[str, Any]],
    arrays: list[HydrophoneArray],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.4))
    metrics = (
        (axes[0], "angular_error_deg", "Angular error (deg)"),
        (axes[1], "position_error_m", "Position error (m)"),
    )
    for ax, key, ylabel in metrics:
        for array in arrays:
            medians = []
            tails = []
            for snr in snr_levels:
                values = np.asarray(
                    [
                        float(row[key])
                        for row in _rows_for(rows, array.key, snr)
                        if is_success(row) and np.isfinite(float(row[key]))
                    ],
                    dtype=float,
                )
                medians.append(float(np.median(values)) if values.size else np.nan)
                tails.append(float(np.percentile(values, 95)) if values.size else np.nan)
            if not np.any(np.isfinite(medians)):
                continue
            color = GEOM_COLORS[array.key]
            ax.plot(snr_levels, medians, marker="o", color=color, linewidth=1.8, label=array.name)
            ax.plot(snr_levels, tails, color=color, linewidth=1.0, linestyle="--")
        _snr_axis(ax, snr_levels)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.35)
        ax.legend(loc="best")
    axes[0].set_title("Direction")
    axes[1].set_title("Position")
    fig.suptitle(
        "Localization error versus SNR\n"
        "SIMULATION — curves are drawn only where a solve succeeded; solid = median, dashed = 95th percentile",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, path)


def plot_success_rate(
    rows: list[dict[str, Any]],
    arrays: list[HydrophoneArray],
    snr_levels: list[float],
    path: Path,
) -> None:
    _apply_style()
    fig, ax = plt.subplots(figsize=(10.6, 5.8))
    x = np.arange(len(arrays), dtype=float)
    width = 0.12
    offsets = (np.arange(len(snr_levels)) - (len(snr_levels) - 1) / 2.0) * width
    for offset, snr in zip(offsets, snr_levels):
        rates = []
        for array in arrays:
            selected = _rows_for(rows, array.key, snr)
            if not selected:
                rates.append(np.nan)
            else:
                rates.append(sum(is_success(row) for row in selected) / len(selected))
        ax.bar(x + offset, rates, width=width * 0.92, label=f"{snr:.0f} dB")
    for index, array in enumerate(arrays):
        rates = []
        for snr in snr_levels:
            selected = _rows_for(rows, array.key, snr)
            rates.append(0.0 if not selected else sum(is_success(row) for row in selected) / len(selected))
        if rates and max(rates) == 0.0:
            ax.text(index, 0.06, "0 at\nevery SNR", ha="center", va="bottom", fontsize=8, color="0.25")
    ax.set_xticks(x)
    ax.set_xticklabels([array.name for array in arrays])
    ax.set_ylim(0.0, 1.08)
    ax.set_ylabel("Solver success rate")
    ax.set_title(
        "Localization solver success rate by geometry\n"
        "SIMULATION — a rate of 0 is a reported failure, not a zero-error solution"
    )
    ax.legend(title="SNR", ncol=3, loc="upper right")
    ax.grid(True, axis="y", alpha=0.35)
    _save(fig, path)


def plot_error_vs_distance(
    rows: list[dict[str, Any]],
    arrays: list[HydrophoneArray],
    snr_db: float,
    path: Path,
) -> None:
    _apply_style()
    edges = np.array([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    centers = 0.5 * (edges[:-1] + edges[1:])
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.4))

    for array in arrays:
        selected = _rows_for(rows, array.key, snr_db)
        tdoa_medians = []
        angular_medians = []
        for low, high in zip(edges[:-1], edges[1:]):
            if high == edges[-1]:
                in_bin = [row for row in selected if low <= float(row["source_range_m"]) <= high]
            else:
                in_bin = [row for row in selected if low <= float(row["source_range_m"]) < high]
            errors = []
            for row in in_bin:
                errors.extend(error for error in tdoa_abs_errors_us(row) if np.isfinite(error))
            angular = [
                float(row["angular_error_deg"])
                for row in in_bin
                if is_success(row) and np.isfinite(float(row["angular_error_deg"]))
            ]
            tdoa_medians.append(float(np.median(errors)) if errors else np.nan)
            angular_medians.append(float(np.median(angular)) if angular else np.nan)
        color = GEOM_COLORS[array.key]
        axes[0].plot(centers, tdoa_medians, marker="o", color=color, label=array.name)
        if np.any(np.isfinite(angular_medians)):
            axes[1].plot(centers, angular_medians, marker="o", color=color, label=array.name)

    axes[0].set_ylabel("Median absolute TDOA error (us)")
    axes[0].set_title("TDOA, all geometries")
    axes[0].set_ylim(bottom=0.0)
    axes[1].set_ylabel("Median angular error (deg)")
    axes[1].set_title("Direction, successful solves only")
    axes[1].set_ylim(bottom=0.0)
    for ax in axes:
        ax.set_xlabel("Source distance from array center (m)")
        ax.grid(True, alpha=0.35)
        ax.legend(loc="best", fontsize=8)
    fig.suptitle(
        f"Error versus source distance at {snr_db:.0f} dB SNR\n"
        "SIMULATION — 1 m bins; the last bin includes 8 m. This is not an interpolated map.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, path)


def plot_spatial_error(
    rows: list[dict[str, Any]],
    array: HydrophoneArray,
    snr_db: float,
    path: Path,
    vmax_deg: float | None,
) -> None:
    _apply_style()
    selected = _rows_for(rows, array.key, snr_db)
    fig, ax = plt.subplots(figsize=(7.4, 6.4))
    success_x = []
    success_y = []
    success_err = []
    fail_x = []
    fail_y = []
    for row in selected:
        if is_success(row) and np.isfinite(float(row["angular_error_deg"])):
            success_x.append(float(row["source_x_m"]))
            success_y.append(float(row["source_y_m"]))
            success_err.append(float(row["angular_error_deg"]))
        else:
            fail_x.append(float(row["source_x_m"]))
            fail_y.append(float(row["source_y_m"]))

    if success_err:
        scatter = ax.scatter(
            success_x,
            success_y,
            c=success_err,
            cmap="viridis",
            s=28,
            vmin=0.0,
            vmax=vmax_deg if vmax_deg is not None else max(success_err),
            linewidths=0,
        )
        colorbar = fig.colorbar(scatter, ax=ax)
        colorbar.set_label("Angular error (deg)")
        caption = (
            f"{array.name} at {snr_db:.0f} dB SNR\n"
            "SIMULATION — XY projection of the 3D sources. Z is not an axis. Points are not interpolated.\n"
            "Color is 3D angular error. The scale ends at the volumetric 95th percentile; larger errors share that color."
        )
    else:
        ax.scatter(fail_x, fail_y, c="0.55", marker="x", s=28, label="solver did not return a position")
        ax.legend(loc="best")
        caption = (
            f"{array.name} at {snr_db:.0f} dB SNR\n"
            "SIMULATION — XY positions of the 3D source set. Z is not an axis of this plot.\n"
            "No unique 3D solution was reported, so these points are not colored by an error."
        )
    if success_err and fail_x:
        ax.scatter(fail_x, fail_y, c="black", marker="x", s=32, label="solver failed")
        ax.legend(loc="best")
    ax.scatter([0.0], [0.0], c="red", marker="+", s=80, zorder=3)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Source X (m)")
    ax.set_ylabel("Source Y (m)")
    ax.set_title(caption, fontsize=11)
    ax.grid(True, alpha=0.35)
    _save(fig, path)


def spatial_color_limit(rows: list[dict[str, Any]], arrays: list[HydrophoneArray], snr_db: float) -> float:
    """Shared color maximum so the volumetric maps can be compared.

    The limit is the 95th percentile of successful angular errors at this SNR,
    and at least 1 degree. Larger errors still appear at the top color; they
    are not removed from the scatter.
    """
    values = []
    volumetric = {array.key for array in arrays if array.expected_class == "volumetric"}
    for row in rows:
        if row["geometry"] not in volumetric:
            continue
        if float(row["snr_db"]) != float(snr_db):
            continue
        if is_success(row) and np.isfinite(float(row["angular_error_deg"])):
            values.append(float(row["angular_error_deg"]))
    if not values:
        return 1.0
    return max(1.0, float(np.percentile(values, 95)))
