"""Plots for the H4 height study. Nothing here writes outside the study folder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers the 3d projection)

from simulations.h4_height_study.directions import DIRECTION_ORDER, INSUFFICIENT
from simulations.h4_height_study.geometry import REQUESTED_LABELS
from simulations.h4_height_study.metrics import noise_free
from simulations.h4_height_study.paths import assert_output_path

NEGATIVE_COLOR = "#0072B2"
POSITIVE_COLOR = "#D55E00"
HYDRO_COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00")


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "savefig.dpi": 160,
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    path = assert_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _sorted_heights(rows: list[dict[str, Any]]) -> list[float]:
    return sorted({float(row["h4_height_m"]) for row in rows})


def _row_at(rows: list[dict[str, Any]], height: float) -> dict[str, Any] | None:
    for row in rows:
        if np.isclose(float(row["h4_height_m"]), height):
            return row
    return None


def plot_metric_vs_height(
    rows: list[dict[str, Any]],
    key: str,
    ylabel: str,
    title: str,
    path: Path,
    *,
    percent: bool = False,
) -> None:
    """Split the curve at zero so positive and negative H4 heights stay distinct."""
    _style()
    heights = _sorted_heights(rows)
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    for sign, color, label in (
        (-1.0, NEGATIVE_COLOR, "H4 below the H1/H2/H3 plane"),
        (1.0, POSITIVE_COLOR, "H4 above the H1/H2/H3 plane"),
    ):
        selected = [height for height in heights if np.sign(height) == sign]
        values = []
        for height in selected:
            match = _row_at(rows, height)
            value = float(match[key]) if match is not None else float("nan")
            values.append(100.0 * value if percent else value)
        ax.plot(
            [height * 100.0 for height in selected],
            values,
            color=color,
            marker="o" if sign < 0 else "s",
            linewidth=1.8,
            label=label,
        )
    ax.axvline(0.0, color="0.6", linestyle=":", linewidth=1.0, label="0 cm not tested")
    ax.set_xlabel("H4 height relative to the H1/H2/H3 plane (cm)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False)
    fig.tight_layout()
    _save(fig, path)


def plot_direction_vs_height(
    directional: list[dict[str, Any]],
    direction: str,
    path: Path,
    study_title: str,
) -> None:
    rows = [row for row in directional if row["direction"] == direction and row["flag"] != INSUFFICIENT]
    if not rows:
        return
    plot_metric_vs_height(
        rows,
        "median_localization_error_m",
        "Median localization error (m)",
        f"{study_title}\n{direction} — median error versus H4 height\nSIMULATION — successful solves only",
        path,
    )


def _snr_order(rows: list[dict[str, Any]]) -> list[str]:
    labels = []
    if any(noise_free(row) or str(row.get("noise_free", "")).lower() == "true" for row in rows):
        labels.append("noise-free")
    levels = sorted(
        {
            float(row["snr_db"])
            for row in rows
            if str(row.get("noise_free", "")).lower() != "true" and np.isfinite(float(row.get("snr_db", float("nan"))))
        },
        reverse=True,
    )
    labels.extend(f"{level:.0f} dB" for level in levels)
    return labels


def plot_heatmap(
    rows: list[dict[str, Any]],
    row_labels: list[str],
    row_key: str,
    value_key: str,
    title: str,
    colorbar: str,
    path: Path,
    *,
    percent: bool = False,
    insufficient_rows: set[str] | None = None,
) -> None:
    _style()
    heights = _sorted_heights(rows)
    matrix = np.full((len(row_labels), len(heights)), np.nan)
    for row_index, label in enumerate(row_labels):
        for column, height in enumerate(heights):
            match = [
                row
                for row in rows
                if str(row[row_key]) == label and np.isclose(float(row["h4_height_m"]), height)
            ]
            if not match:
                continue
            value = float(match[0][value_key])
            matrix[row_index, column] = 100.0 * value if percent else value
    fig_height = max(4.8, 0.42 * len(row_labels) + 1.8)
    fig, ax = plt.subplots(figsize=(10.4, fig_height))
    finite = matrix[np.isfinite(matrix)]
    if finite.size == 0:
        plt.close(fig)
        return
    image = ax.imshow(
        matrix,
        aspect="auto",
        cmap="viridis_r" if not percent else "viridis",
        interpolation="nearest",
    )
    ax.set_xticks(range(len(heights)))
    ax.set_xticklabels([f"{height * 100:.0f}" for height in heights])
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)
    ax.set_xlabel("H4 height (cm) — negative is below the triangle plane")
    colorbar_artist = fig.colorbar(image, ax=ax)
    colorbar_artist.set_label(colorbar)
    if insufficient_rows:
        for row_index, label in enumerate(row_labels):
            if label not in insufficient_rows:
                continue
            for column in range(len(heights)):
                ax.plot(column, row_index, marker="x", color="white", markersize=5)
    ax.set_title(title)
    _save(fig, path)


def present_directions(directional: list[dict[str, Any]]) -> list[str]:
    present = {str(row["direction"]) for row in directional}
    ordered = [name for name in DIRECTION_ORDER if name in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def insufficient_directions(directional: list[dict[str, Any]]) -> set[str]:
    return {str(row["direction"]) for row in directional if row["flag"] == INSUFFICIENT}


def plot_geometry(coordinates_m: np.ndarray, title: str, path: Path) -> None:
    _style()
    fig = plt.figure(figsize=(6.4, 5.6))
    ax = fig.add_subplot(111, projection="3d")
    coordinates = np.asarray(coordinates_m, dtype=float)
    for index in range(coordinates.shape[0]):
        ax.scatter(
            coordinates[index, 0],
            coordinates[index, 1],
            coordinates[index, 2],
            color=HYDRO_COLORS[index],
            s=60,
        )
        ax.text(
            coordinates[index, 0],
            coordinates[index, 1],
            coordinates[index, 2],
            f"  {REQUESTED_LABELS[index]}",
            fontsize=10,
        )
    for edge in ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)):
        pair = coordinates[list(edge)]
        ax.plot(pair[:, 0], pair[:, 1], pair[:, 2], color="0.45", linewidth=1.0)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title(title)
    _equal_3d(ax, coordinates)
    _save(fig, path)


def plot_all_h4_positions(triangles: np.ndarray, h4_positions: list[tuple[float, np.ndarray]], path: Path) -> None:
    """Fixed H1/H2/H3 and every tested H4 on the vertical line through the centroid."""
    _style()
    fig = plt.figure(figsize=(7.2, 6.2))
    ax = fig.add_subplot(111, projection="3d")
    for index in range(3):
        ax.scatter(
            triangles[index, 0],
            triangles[index, 1],
            triangles[index, 2],
            color=HYDRO_COLORS[index],
            s=70,
        )
        ax.text(triangles[index, 0], triangles[index, 1], triangles[index, 2], f"  {REQUESTED_LABELS[index]}")
    for edge in ((0, 1), (1, 2), (2, 0)):
        pair = triangles[list(edge)]
        ax.plot(pair[:, 0], pair[:, 1], pair[:, 2], color="0.35", linewidth=1.2)
    points = []
    for height, xyz in h4_positions:
        color = NEGATIVE_COLOR if height < 0 else POSITIVE_COLOR
        ax.scatter(xyz[0], xyz[1], xyz[2], color=color, s=40)
        label_y = 0.03 if height > 0.0 else -0.03
        ax.text(xyz[0], xyz[1] + label_y, xyz[2], f"{height * 100:.0f} cm", fontsize=8)
        points.append(xyz)
    stack = np.vstack([triangles, np.asarray(points)])
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title("SIMULATION — H1/H2/H3 fixed, every tested H4 height")
    _equal_3d(ax, stack)
    _save(fig, path)


def _equal_3d(ax: plt.Axes, coordinates: np.ndarray) -> None:
    mins = coordinates.min(axis=0)
    maxs = coordinates.max(axis=0)
    center = 0.5 * (mins + maxs)
    radius = 0.5 * float(np.max(maxs - mins))
    radius = max(radius, 0.05)
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
