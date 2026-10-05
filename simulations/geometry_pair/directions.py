"""Direction labels relative to the array centroid.

A source is a cardinal direction when one axis dominates. Otherwise the
label names the two strongest axes, so a diagonal source is not forced
into FRONT, BACK, LEFT, RIGHT, ABOVE, or BELOW.
"""

from __future__ import annotations

from typing import Any

import numpy as np

CARDINALS = ("FRONT", "BACK", "RIGHT", "LEFT", "ABOVE", "BELOW")
_AXIS_NAMES = (
    ("BACK", "FRONT"),
    ("LEFT", "RIGHT"),
    ("BELOW", "ABOVE"),
)
_DOMINANCE = 1.5


def classify_direction(source_m: np.ndarray, center_m: np.ndarray) -> str:
    """Label one source relative to ``center_m``."""
    delta = np.asarray(source_m, dtype=float).reshape(3) - np.asarray(center_m, dtype=float).reshape(3)
    magnitudes = np.abs(delta)
    if not np.any(magnitudes > 0.0):
        return "AT_ARRAY"
    order = np.argsort(magnitudes)[::-1]
    primary = int(order[0])
    secondary = int(order[1])

    def _name(axis: int) -> str:
        negative, positive = _AXIS_NAMES[axis]
        return positive if delta[axis] >= 0.0 else negative

    if magnitudes[primary] >= _DOMINANCE * magnitudes[secondary]:
        return _name(primary)
    return f"{_name(primary)}-{_name(secondary)}"


def _success(row: dict[str, Any]) -> bool:
    value = row["success"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _finite(row: dict[str, Any], key: str) -> float:
    value = row.get(key, "")
    if value is None or value == "":
        return float("nan")
    return float(value)


def directional_summary(
    rows: list[dict[str, Any]],
    geometry: str,
    study: str,
    center_m: np.ndarray,
) -> list[dict[str, Any]]:
    """Per-direction error and success, pooled and by SNR."""
    labeled: list[tuple[str, str, dict[str, Any]]] = []
    for row in rows:
        direction = classify_direction(
            np.array([row["source_x_m"], row["source_y_m"], row["source_z_m"]], dtype=float),
            center_m,
        )
        scope = "noise-free" if _is_noise_free(row) else f"{float(row['snr_db']):.0f} dB"
        labeled.append((direction, scope, row))

    scopes = ["all", *dict.fromkeys(scope for _, scope, _ in labeled)]
    directions = list(dict.fromkeys(direction for direction, _, _ in labeled))
    summary: list[dict[str, Any]] = []
    for scope in scopes:
        for direction in directions:
            group = [
                row
                for recorded_direction, recorded_scope, row in labeled
                if recorded_direction == direction and (scope == "all" or recorded_scope == scope)
            ]
            if not group:
                continue
            summary.append(_summarize_group(group, geometry, study, direction, scope))
    return summary


def _is_noise_free(row: dict[str, Any]) -> bool:
    value = row["noise_free"]
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _summarize_group(
    group: list[dict[str, Any]],
    geometry: str,
    study: str,
    direction: str,
    scope: str,
) -> dict[str, Any]:
    successes = [row for row in group if _success(row)]
    position = np.array([_finite(row, "localization_error_m") for row in successes], dtype=float)
    position = position[np.isfinite(position)]
    angular = np.array([_finite(row, "angular_error_deg") for row in successes], dtype=float)
    angular = angular[np.isfinite(angular)]
    sources = {
        (
            round(float(row["source_x_m"]), 6),
            round(float(row["source_y_m"]), 6),
            round(float(row["source_z_m"]), 6),
        )
        for row in group
    }
    return {
        "study": study,
        "geometry": geometry,
        "direction": direction,
        "snr_scope": scope,
        "number_of_trials": len(group),
        "n_sources": len(sources),
        "n_successful": len(successes),
        "median_localization_error": float(np.median(position)) if position.size else float("nan"),
        "95th_percentile_error": float(np.percentile(position, 95)) if position.size else float("nan"),
        "median_angular_error": float(np.median(angular)) if angular.size else float("nan"),
        "success_rate": len(successes) / len(group) if group else float("nan"),
    }


DIRECTION_FIELDS = [
    "study",
    "geometry",
    "direction",
    "snr_scope",
    "number_of_trials",
    "n_sources",
    "n_successful",
    "median_localization_error",
    "95th_percentile_error",
    "median_angular_error",
    "success_rate",
]
