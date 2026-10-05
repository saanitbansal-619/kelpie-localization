"""The short plot set for the joint geometry study."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from simulations.h4_height_study.geometry import REQUESTED_LABELS
from simulations.joint_geometry_study.geometry import BASE_SCALES, HEIGHTS_M, EDGES
from simulations.joint_geometry_study.paths import assert_output_path

HYDRO_COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00")
CONTROL_COLOR = "#D55E00"


def plot_geometries(layouts: list[tuple[float, float, np.ndarray, str, bool]], path: Path) -> None:
    """One panel per layout. ``layouts`` is (height, scale, coordinates, id, control)."""
    _style()
    fig = plt.figure(figsize=(12.2, 11.2))
    for index, (height, scale, coordinates, name, control) in enumerate(layouts):
        ax = fig.add_subplot(3, 3, index + 1, projection="3d")
        coordinates = np.asarray(coordinates, dtype=float)
        for phone in range(4):
            ax.scatter(
                coordinates[phone, 0],
                coordinates[phone, 1],
                coordinates[phone, 2],
                color=HYDRO_COLORS[phone],
                s=28,
            )
            ax.text(
                coordinates[phone, 0],
                coordinates[phone, 1],
                coordinates[phone, 2],
                REQUESTED_LABELS[phone],
                fontsize=7,
            )
        for edge in EDGES:
            pair = coordinates[list(edge)]
            ax.plot(pair[:, 0], pair[:, 1], pair[:, 2], color="0.45", linewidth=0.8)
        title = f"{name}"
        if control:
            title += "  control"
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("X", fontsize=8)
        ax.set_ylabel("Y", fontsize=8)
        ax.set_zlabel("Z", fontsize=8)
        ax.tick_params(labelsize=7)
        _equal_3d(ax, coordinates)
        del height, scale
    fig.suptitle("SIMULATION — nine 3+1 layouts, H4 above the triangle", fontsize=13)
    fig.tight_layout()
    _save(fig, path)


def plot_design_heatmap(
    summary: list[dict[str, Any]],
    value_key: str,
    title: str,
    colorbar: str,
    path: Path,
    *,
    percent: bool = False,
    lower_is_better: bool = True,
) -> None:
    """H4 height on the rows, base scale on the columns."""
    _style()
    matrix = np.full((len(HEIGHTS_M), len(BASE_SCALES)), np.nan)
    annotations = [["" for _ in BASE_SCALES] for _ in HEIGHTS_M]
    control_cell = None
    for row in summary:
        height_index = _index(HEIGHTS_M, float(row["h4_height_m"]))
        scale_index = _index(BASE_SCALES, float(row["base_scale"]))
        value = float(row[value_key])
        shown = 100.0 * value if percent else value
        matrix[height_index, scale_index] = shown
        annotations[height_index][scale_index] = _cell_text(shown, percent)
        if row["is_control"]:
            control_cell = (height_index, scale_index)
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    image = ax.imshow(
        matrix,
        aspect="auto",
        cmap="viridis_r" if lower_is_better else "viridis",
        interpolation="nearest",
    )
    ax.set_xticks(range(len(BASE_SCALES)))
    ax.set_xticklabels([f"{scale:.2f}×" for scale in BASE_SCALES])
    ax.set_yticks(range(len(HEIGHTS_M)))
    ax.set_yticklabels([f"{height * 100:.0f} cm" for height in HEIGHTS_M])
    ax.set_xlabel("H1/H2/H3 base scale")
    ax.set_ylabel("H4 height above the triangle plane")
    for row_index in range(len(HEIGHTS_M)):
        for column in range(len(BASE_SCALES)):
            ax.text(
                column,
                row_index,
                annotations[row_index][column],
                ha="center",
                va="center",
                color="white",
                fontsize=10,
                path_effects=[path_effects.withStroke(linewidth=2, foreground="black")],
            )
    if control_cell is not None:
        ax.add_patch(
            plt.Rectangle(
                (control_cell[1] - 0.5, control_cell[0] - 0.5),
                1,
                1,
                fill=False,
                edgecolor="black",
                linewidth=2.0,
            )
        )
    fig.colorbar(image, ax=ax).set_label(colorbar)
    ax.set_title(title)
    fig.tight_layout()
    _save(fig, path)


def plot_accuracy_reliability(summary: list[dict[str, Any]], path: Path) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    for row in summary:
        x = float(row["median_localization_error_m"])
        y = 100.0 * float(row["success_rate"])
        if row["is_control"]:
            ax.scatter([x], [y], s=160, marker="*", color=CONTROL_COLOR, zorder=3, label="control 30 cm / 1.00×")
        else:
            ax.scatter([x], [y], s=55, color="#0072B2", zorder=2)
        ax.annotate(str(row["geometry_id"]), (x, y), textcoords="offset points", xytext=(6, 6), fontsize=8)
    ax.set_xlabel("Median localization error (m)")
    ax.set_ylabel("Localization success rate (%)")
    ax.set_title("SIMULATION — accuracy versus reliability")
    ax.grid(True, alpha=0.35)
    ax.legend(frameon=False)
    fig.tight_layout()
    _save(fig, path)


def plot_snr_heatmap(
    snr_rows: list[dict[str, Any]],
    value_key: str,
    title: str,
    colorbar: str,
    path: Path,
    *,
    percent: bool = False,
    lower_is_better: bool = True,
) -> None:
    """All nine geometries against the shared SNR list."""
    _style()
    geometry_ids = list(dict.fromkeys(str(row["geometry_id"]) for row in snr_rows))
    snr_labels = list(dict.fromkeys(str(row["snr_label"]) for row in snr_rows))
    matrix = np.full((len(geometry_ids), len(snr_labels)), np.nan)
    lookup = {(str(row["geometry_id"]), str(row["snr_label"])): row for row in snr_rows}
    for row_index, geometry_id in enumerate(geometry_ids):
        for column, label in enumerate(snr_labels):
            match = lookup.get((geometry_id, label))
            if match is None or not np.isfinite(float(match[value_key])):
                continue
            value = float(match[value_key])
            matrix[row_index, column] = 100.0 * value if percent else value
    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    image = ax.imshow(
        matrix,
        aspect="auto",
        cmap="viridis_r" if lower_is_better else "viridis",
        interpolation="nearest",
    )
    ax.set_xticks(range(len(snr_labels)))
    ax.set_xticklabels(snr_labels, rotation=30, ha="right")
    ax.set_yticks(range(len(geometry_ids)))
    ax.set_yticklabels(geometry_ids)
    ax.set_xlabel("SNR")
    ax.set_ylabel("Geometry")
    fig.colorbar(image, ax=ax).set_label(colorbar)
    ax.set_title(title)
    fig.tight_layout()
    _save(fig, path)


def _cell_text(value: float, percent: bool) -> str:
    if not np.isfinite(value):
        return ""
    if percent:
        return f"{value:.1f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _index(choices: tuple[float, ...], value: float) -> int:
    for index, choice in enumerate(choices):
        if np.isclose(choice, value):
            return index
    raise KeyError(value)


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


def _equal_3d(ax: plt.Axes, coordinates: np.ndarray) -> None:
    mins = coordinates.min(axis=0)
    maxs = coordinates.max(axis=0)
    center = 0.5 * (mins + maxs)
    radius = max(0.5 * float(np.max(maxs - mins)), 0.05)
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
