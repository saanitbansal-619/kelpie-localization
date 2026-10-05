"""Comparison plots. Individual geometry plots stay in each geometry folder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

TETRA_COLOR = "#0072B2"
THREE_COLOR = "#D55E00"
DISPLAY = {"tetrahedral": "Tetrahedral", "three_plus_one": "3+1"}
CARDINAL_ORDER = {name: index for index, name in enumerate(("FRONT", "BACK", "RIGHT", "LEFT", "ABOVE", "BELOW"))}


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _ordered_labels(rows: list[dict[str, Any]]) -> list[str]:
    labels = []
    if any(str(row["noise_free"]).lower() == "true" for row in rows):
        labels.append("noise-free")
    levels = sorted({float(row["snr_db"]) for row in rows if str(row["noise_free"]).lower() != "true"}, reverse=True)
    labels.extend(f"{level:.0f} dB" for level in levels)
    return labels


def _match(rows: list[dict[str, Any]], geometry: str, label: str) -> dict[str, Any] | None:
    for row in rows:
        if row["geometry"] != geometry:
            continue
        if label == "noise-free" and str(row["noise_free"]).lower() == "true":
            return row
        if label != "noise-free" and str(row["noise_free"]).lower() != "true":
            if f"{float(row['snr_db']):.0f} dB" == label:
                return row
    return None


def _series(rows: list[dict[str, Any]], geometry: str, labels: list[str], key: str) -> list[float]:
    values = []
    for label in labels:
        match = _match(rows, geometry, label)
        values.append(float(match[key]) if match is not None else float("nan"))
    return values


def plot_metric(
    rows: list[dict[str, Any]],
    key: str,
    ylabel: str,
    title: str,
    path: Path,
    *,
    log_y: bool = False,
    percent: bool = False,
) -> None:
    """One metric versus SNR, tetrahedral and 3+1 on the same axes."""
    _style()
    labels = _ordered_labels(rows)
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    for geometry, color, marker in (
        ("tetrahedral", TETRA_COLOR, "o"),
        ("three_plus_one", THREE_COLOR, "s"),
    ):
        values = np.array(_series(rows, geometry, labels, key), dtype=float)
        if percent:
            values = 100.0 * values
        ax.plot(
            x,
            values,
            color=color,
            marker=marker,
            linewidth=1.8,
            markersize=7,
            label=DISPLAY[geometry],
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("SNR — noise increases to the right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if log_y:
        positive = [value for value in ax.lines[0].get_ydata() if np.isfinite(value) and value > 0]
        positive += [value for value in ax.lines[1].get_ydata() if np.isfinite(value) and value > 0]
        if positive:
            ax.set_yscale("log")
    if percent:
        ax.set_ylim(0.0, 112.0)
    ax.legend(loc="best", title="Hydrophone geometry")
    ax.grid(True, which="both", alpha=0.35)
    _save(fig, path)


def plot_directions(rows: list[dict[str, Any]], path: Path) -> None:
    """Median localization error by direction, both geometries, both studies."""
    _style()
    studies = (
        ("change_1_noise", "Change #1 — noise study, all SNR conditions"),
        ("change_2_waveform", "Change #2 — 40 kHz waveform study, all SNR conditions"),
    )
    fig, axes = plt.subplots(2, 1, figsize=(10.4, 7.2))
    for ax, (study, title) in zip(axes, studies):
        selected = [row for row in rows if row["study"] == study and row["snr_scope"] == "all"]
        counts: dict[str, int] = {}
        for row in selected:
            counts[row["direction"]] = min(counts.get(row["direction"], int(row["n_sources"])), int(row["n_sources"]))
        directions = [name for name, count in counts.items() if count >= 5]
        directions.sort(key=lambda name: (0, CARDINAL_ORDER[name]) if name in CARDINAL_ORDER else (1, name))
        y = np.arange(len(directions))
        height = 0.36
        for offset, geometry, color in (
            (-height / 2, "tetrahedral", TETRA_COLOR),
            (height / 2, "three_plus_one", THREE_COLOR),
        ):
            values = []
            for direction in directions:
                match = [
                    row
                    for row in selected
                    if row["direction"] == direction and row["geometry"] == geometry
                ]
                values.append(float(match[0]["median_localization_error"]) if match else float("nan"))
            ax.barh(
                y + offset,
                values,
                height=height,
                color=color,
                label=DISPLAY[geometry],
            )
        ax.set_yticks(y)
        ax.set_yticklabels([f"{direction} (n={counts[direction]})" for direction in directions])
        ax.invert_yaxis()
        ax.set_xlabel("Median localization error (m)")
        ax.set_title(title)
        ax.grid(True, axis="x", alpha=0.35)
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            title="Hydrophone geometry",
            frameon=False,
        )
    fig.suptitle(
        "SIMULATION — localization by source direction\n"
        "Bins with at least 5 sources. Hyphenated labels are diagonal.",
        fontsize=12,
    )
    fig.tight_layout()
    _save(fig, path)


def save_comparison_figures(
    change1: list[dict[str, Any]],
    change2: list[dict[str, Any]],
    directions: list[dict[str, Any]],
    plots_dir: Path,
) -> list[Path]:
    """Write the additional comparison plots. Returns their paths."""
    specs = [
        (
            change1,
            "mean_localization_error_m",
            "Mean localization error (m)",
            "Change #1 — mean localization error versus SNR\nSIMULATION — successful solves only",
            plots_dir / "change1_localization_error_vs_snr.png",
            True,
        ),
        (
            change1,
            "median_localization_error_m",
            "Median localization error (m)",
            "Change #1 — median localization error versus SNR\nSIMULATION — successful solves only",
            plots_dir / "change1_median_localization_error_vs_snr.png",
            True,
        ),
        (
            change1,
            "median_angular_error_deg",
            "Median angular error (deg)",
            "Change #1 — median angular error versus SNR\nSIMULATION — successful solves only",
            plots_dir / "change1_angular_error_vs_snr.png",
            True,
        ),
        (
            change1,
            "localization_success_rate",
            "Successful localizations (%)",
            "Change #1 — localization success rate versus SNR\nSIMULATION — a rejected solve is a failure, not a zero error",
            plots_dir / "change1_success_rate_vs_snr.png",
            False,
        ),
        (
            change2,
            "mean_localization_error_m",
            "Mean localization error (m)",
            "Change #2 — mean localization error versus SNR\nSIMULATION — 40 kHz pulse; successful solves only",
            plots_dir / "change2_localization_error_vs_snr.png",
            True,
        ),
        (
            change2,
            "median_localization_error_m",
            "Median localization error (m)",
            "Change #2 — median localization error versus SNR\nSIMULATION — 40 kHz pulse; successful solves only",
            plots_dir / "change2_median_localization_error_vs_snr.png",
            True,
        ),
        (
            change2,
            "median_angular_error_deg",
            "Median angular error (deg)",
            "Change #2 — median angular error versus SNR\nSIMULATION — 40 kHz pulse; successful solves only",
            plots_dir / "change2_angular_error_vs_snr.png",
            True,
        ),
        (
            change2,
            "localization_success_rate",
            "Successful localizations (%)",
            "Change #2 — localization success rate versus SNR\nSIMULATION — 40 kHz pulse; a rejected solve is a failure",
            plots_dir / "change2_success_rate_vs_snr.png",
            False,
        ),
        (
            change2,
            "mean_abs_tdoa_error_us",
            "Mean absolute TDOA error (µs)",
            "Change #2 — mean TDOA estimation error versus SNR\nSIMULATION — GCC-PHAT versus geometric TDOA; every finite pair",
            plots_dir / "change2_tdoa_error_vs_snr.png",
            True,
        ),
    ]
    paths: list[Path] = []
    for rows, key, ylabel, title, path, log_y in specs:
        plot_metric(
            rows,
            key,
            ylabel,
            title,
            path,
            log_y=log_y,
            percent=key == "localization_success_rate",
        )
        paths.append(path)
    direction_path = plots_dir / "directional_localization_error.png"
    plot_directions(directions, direction_path)
    paths.append(direction_path)
    return paths
