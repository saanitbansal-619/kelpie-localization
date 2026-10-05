"""Run manifests that record the exact array used for a result folder."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from src.geometry import (
    DEFAULT_THREE_PLUS_ONE_Z_OFFSET_M,
    HydrophoneArray,
    SOUND_SPEED_MPS,
)

CHANNEL_LABELS = ("H0", "H1", "H2", "H3")
# The project stores channels as H0–H3. The requested H1–H4 names follow
# that same order: requested H1 is channel H0, and requested H4 is H3.
REQUESTED_LABELS = ("H1", "H2", "H3", "H4")


def coordinate_records(array: HydrophoneArray) -> list[dict[str, Any]]:
    """One record per hydrophone, in channel order."""
    records = []
    for index, xyz in enumerate(np.asarray(array.coordinates_m, dtype=float)):
        records.append(
            {
                "channel": CHANNEL_LABELS[index],
                "requested_label": REQUESTED_LABELS[index],
                "x_m": float(xyz[0]),
                "y_m": float(xyz[1]),
                "z_m": float(xyz[2]),
            }
        )
    return records


def base_manifest(
    array: HydrophoneArray,
    *,
    study: str,
    n_trials: int,
    random_seed: int,
    snr_levels_db: list[float],
    include_noise_free: bool,
    source_position_dataset: str,
    n_rows: int,
    elapsed_s: float,
) -> dict[str, Any]:
    """Fields required for every geometry run."""
    manifest: dict[str, Any] = {
        "label": "SIMULATION",
        "study": study,
        "geometry_name": array.key,
        "hydrophone_count": int(array.coordinates_m.shape[0]),
        "hydrophone_coordinates": coordinate_records(array),
        "channel_order_note": (
            "Coordinates are stored as H0, H1, H2, H3. "
            "Those channels are the requested H1, H2, H3, H4 in that order."
        ),
        "maximum_baseline_m": float(array.max_pairwise_distance_m()),
        "array_center_m": [float(value) for value in array.center_m],
        "source_position_dataset": source_position_dataset,
        "number_of_trials": int(n_trials),
        "random_seed": int(random_seed),
        "SNR_conditions": _snr_conditions(snr_levels_db, include_noise_free),
        "speed_of_sound_mps": float(SOUND_SPEED_MPS),
        "n_rows": int(n_rows),
        "elapsed_s": round(float(elapsed_s), 3),
        "preserved_original_results": [
            "simulations/noise_study/results",
            "simulations/waveform_study/results",
        ],
    }
    if array.key == "three_plus_one":
        manifest["z_offset_m"] = float(DEFAULT_THREE_PLUS_ONE_Z_OFFSET_M)
        manifest["z_offset_note"] = (
            "z_offset_m is the H3 height above the H0/H1/H2 centroid before "
            "the four-phone centroid is shifted to the origin. "
            "make_three_plus_one(-z_offset_m) mirrors this array."
        )
    return manifest


def write_manifest(path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _snr_conditions(levels: list[float], include_noise_free: bool) -> list[str]:
    labels = ["noise-free"] if include_noise_free else []
    labels.extend(f"{float(level):.0f} dB" for level in levels)
    return labels
