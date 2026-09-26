"""Volumetric arrays for the 4-, 5-, and 6-hydrophone count comparison.

The four-hydrophone array is the existing tetrahedron from ``src.geometry``.
Its coordinates are not restated here.

The five- and six-hydrophone arrays are new. Each is centered at the origin
and scaled so its longest hydrophone pair is 0.25 m, the same maximum
baseline as the tetrahedron. They are not larger arrays.

Reference TDOAs and all-pairs TDOAs are different counts:

* N hydrophones have ``N - 1`` TDOAs relative to H0. Those are the
  measurements the localizer uses.
* The number of unordered pairs is ``N(N-1)/2`` (6, 10, and 15). Those
  pairs are not independent equations. This module does not treat them as
  such.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import (
    SOUND_SPEED_MPS,
    TARGET_BASELINE_M,
    get_geometry,
    max_pairwise_distance_m,
    max_pairwise_tdoa_s,
)


@dataclass(frozen=True)
class SensorArray:
    """One sensor-count configuration. ``coordinates_m`` has shape ``(N, 3)``."""

    key: str
    name: str
    sensor_count: int
    coordinates_m: np.ndarray
    description: str

    def __post_init__(self) -> None:
        coords = np.array(self.coordinates_m, dtype=float, copy=True)
        if coords.ndim != 2 or coords.shape[1] != 3:
            raise ValueError(f"{self.key} coordinates must have shape (N, 3)")
        if coords.shape[0] != self.sensor_count:
            raise ValueError(f"{self.key} sensor_count does not match the coordinate rows")
        if not np.all(np.isfinite(coords)):
            raise ValueError(f"{self.key} coordinates must be finite")
        object.__setattr__(self, "coordinates_m", coords)

    def max_pairwise_distance_m(self) -> float:
        return max_pairwise_distance_m(self.coordinates_m)

    def max_physical_tdoa_s(self, sound_speed_mps: float = SOUND_SPEED_MPS) -> float:
        return max_pairwise_tdoa_s(self.coordinates_m, sound_speed_mps)


def reference_tdoa_count(n_hydrophones: int) -> int:
    """Number of H0-referenced TDOAs used by the solver: ``N - 1``."""
    if n_hydrophones < 2:
        raise ValueError("n_hydrophones must be at least 2")
    return int(n_hydrophones) - 1


def unordered_pair_count(n_hydrophones: int) -> int:
    """Number of unordered hydrophone pairs, ``N(N-1)/2``.

    These pairs are not independent TDOA equations.
    """
    if n_hydrophones < 2:
        raise ValueError("n_hydrophones must be at least 2")
    n = int(n_hydrophones)
    return n * (n - 1) // 2


def _five_hydrophone_coordinates(baseline_m: float = TARGET_BASELINE_M) -> np.ndarray:
    """Triangular bipyramid whose longest pairs are ``baseline_m``.

    Three phones form an equilateral triangle of side ``baseline_m`` in the
    XY plane. The other two sit on the Z axis, separated by ``baseline_m``.
    Apex-to-base distances are shorter than that baseline, so the array is
    not enlarged past the four-phone envelope.
    """
    side = float(baseline_m)
    radius = side / np.sqrt(3.0)
    half_polar = side / 2.0
    return np.array(
        [
            [radius, 0.0, 0.0],
            [-radius / 2.0, side / 2.0, 0.0],
            [-radius / 2.0, -side / 2.0, 0.0],
            [0.0, 0.0, half_polar],
            [0.0, 0.0, -half_polar],
        ],
        dtype=float,
    )


def _six_hydrophone_coordinates(baseline_m: float = TARGET_BASELINE_M) -> np.ndarray:
    """Regular octahedron scaled so opposite vertices are ``baseline_m`` apart.

    Adjacent vertices are closer (``baseline_m / sqrt(2)``). The array is
    not given a longer baseline than the four-phone tetrahedron.
    """
    arm = float(baseline_m) / 2.0
    return np.array(
        [
            [arm, 0.0, 0.0],
            [0.0, arm, 0.0],
            [-arm, 0.0, 0.0],
            [0.0, -arm, 0.0],
            [0.0, 0.0, arm],
            [0.0, 0.0, -arm],
        ],
        dtype=float,
    )


def list_count_arrays() -> tuple[SensorArray, ...]:
    """Return the 4-, 5-, and 6-hydrophone arrays in that order.

    The 4-hydrophone coordinates are the existing tetrahedron.
    """
    tetra = get_geometry("tetrahedral")
    four = SensorArray(
        key="n4_tetrahedral",
        name="4 hydrophones",
        sensor_count=4,
        coordinates_m=tetra.coordinates_m.copy(),
        description=(
            "The existing regular tetrahedron of edge 0.25 m from the "
            "geometry study. Coordinates are not redefined."
        ),
    )
    five = SensorArray(
        key="n5_bipyramid",
        name="5 hydrophones",
        sensor_count=5,
        coordinates_m=_five_hydrophone_coordinates(),
        description=(
            "Triangular bipyramid. Equatorial side 0.25 m and polar "
            "separation 0.25 m, centroid at the origin."
        ),
    )
    six = SensorArray(
        key="n6_octahedron",
        name="6 hydrophones",
        sensor_count=6,
        coordinates_m=_six_hydrophone_coordinates(),
        description=(
            "Regular octahedron centered at the origin. Opposite vertices "
            "are 0.25 m apart."
        ),
    )
    return (four, five, six)


def get_count_array(sensor_count: int) -> SensorArray:
    for array in list_count_arrays():
        if array.sensor_count == int(sensor_count):
            return array
    raise KeyError(f"no count-study array with {sensor_count} hydrophones")
