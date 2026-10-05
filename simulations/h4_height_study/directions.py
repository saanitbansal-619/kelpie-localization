"""Direction labels from the source vector relative to the fixed triangle.

An axis enters the label when its absolute component is at least half the
largest component. Names are always ordered X, then Y, then Z, so a diagonal
is FRONT-RIGHT rather than whichever axis happens to be slightly larger.
A source is not forced into a single cardinal bin when a second or third
axis is comparable.

The center is the H1/H2/H3 centroid. It does not move when H4 changes height,
so a source stays in the same bin at every height.
"""

from __future__ import annotations

import numpy as np

CARDINALS = ("FRONT", "BACK", "RIGHT", "LEFT", "ABOVE", "BELOW")
HORIZONTAL_DIAGONALS = ("FRONT-RIGHT", "FRONT-LEFT", "BACK-RIGHT", "BACK-LEFT")
VERTICAL_DIAGONALS = (
    "FRONT-ABOVE",
    "FRONT-BELOW",
    "BACK-ABOVE",
    "BACK-BELOW",
    "RIGHT-ABOVE",
    "RIGHT-BELOW",
    "LEFT-ABOVE",
    "LEFT-BELOW",
)
OCTANTS = (
    "FRONT-RIGHT-ABOVE",
    "FRONT-RIGHT-BELOW",
    "FRONT-LEFT-ABOVE",
    "FRONT-LEFT-BELOW",
    "BACK-RIGHT-ABOVE",
    "BACK-RIGHT-BELOW",
    "BACK-LEFT-ABOVE",
    "BACK-LEFT-BELOW",
)
DIRECTION_ORDER = CARDINALS + HORIZONTAL_DIAGONALS + VERTICAL_DIAGONALS + OCTANTS

_AXIS_NAMES = (
    ("BACK", "FRONT"),
    ("LEFT", "RIGHT"),
    ("BELOW", "ABOVE"),
)
INCLUDE_RATIO = 0.5
MIN_SOURCES = 5
INSUFFICIENT = "INSUFFICIENT_SAMPLE_COUNT"


def classify_direction(source_m: np.ndarray, center_m: np.ndarray) -> str:
    """Label one source. Axes below half the dominant component are left out."""
    delta = np.asarray(source_m, dtype=float).reshape(3) - np.asarray(center_m, dtype=float).reshape(3)
    magnitudes = np.abs(delta)
    largest = float(np.max(magnitudes))
    if largest == 0.0 or not np.isfinite(largest):
        return "AT_ARRAY"
    names = []
    for axis in range(3):
        if magnitudes[axis] >= INCLUDE_RATIO * largest:
            negative, positive = _AXIS_NAMES[axis]
            names.append(positive if delta[axis] >= 0.0 else negative)
    return "-".join(names)


def is_sufficient(n_sources: int) -> bool:
    return int(n_sources) >= MIN_SOURCES
