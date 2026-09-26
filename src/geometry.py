"""Four-hydrophone array geometries and geometry-derived propagation.

Coordinates live here and nowhere else. Experiment scripts import these
arrays; they do not restate the XYZ values.

All arrays are centered at the origin and use a maximum pairwise baseline
of 0.25 m where that is the natural scale of the shape. The cross is an
unequal-arm plus, not a rotated copy of the square: four equal arms on the
coordinate axes would be the square rotated by 45 degrees.

Propagation times and TDOAs in this module are ground truth from path
length. They are not GCC-PHAT estimates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Reference speed of sound used for geometry-derived travel times.
# Matches ``src.tdoa.DEFAULT_SOUND_SPEED_MPS``.
SOUND_SPEED_MPS = 1480.0

# Nominal maximum array dimension used to keep the five shapes comparable.
TARGET_BASELINE_M = 0.25


@dataclass(frozen=True)
class HydrophoneArray:
    """One named four-hydrophone geometry.

    ``coordinates_m`` has shape ``(4, 3)`` and is stored in channel order
    H0, H1, H2, H3. ``edges`` are index pairs drawn in the geometry figures.
    ``expected_class`` is the geometric rank the localization module should
    report: ``collinear``, ``coplanar``, or ``volumetric``.
    """

    key: str
    name: str
    description: str
    coordinates_m: np.ndarray
    edges: tuple[tuple[int, int], ...]
    figure_stem: str
    expected_class: str

    def __post_init__(self) -> None:
        coords = np.array(self.coordinates_m, dtype=float, copy=True)
        if coords.shape != (4, 3):
            raise ValueError(f"{self.key} coordinates must have shape (4, 3)")
        if not np.all(np.isfinite(coords)):
            raise ValueError(f"{self.key} coordinates must be finite")
        object.__setattr__(self, "coordinates_m", coords)

    @property
    def center_m(self) -> np.ndarray:
        """Centroid of the four hydrophones, shape ``(3,)``."""
        return np.mean(self.coordinates_m, axis=0)

    def max_pairwise_distance_m(self) -> float:
        """Longest distance between any two hydrophones, in metres."""
        return float(np.max(pairwise_distances(self.coordinates_m)))


def _square_coordinates(diagonal_m: float = TARGET_BASELINE_M) -> np.ndarray:
    """Corners of a square in the XY plane. The diagonal is ``diagonal_m``."""
    half_diagonal = diagonal_m / 2.0
    corner = half_diagonal / np.sqrt(2.0)
    return np.array(
        [
            [corner, corner, 0.0],
            [-corner, corner, 0.0],
            [-corner, -corner, 0.0],
            [corner, -corner, 0.0],
        ],
        dtype=float,
    )


def _tetrahedron_coordinates(edge_m: float = TARGET_BASELINE_M) -> np.ndarray:
    """Regular tetrahedron centered at the origin, edge length ``edge_m``.

    The unscaled vertices ``(1,1,1)``, ``(1,-1,-1)``, ``(-1,1,-1)``,
    ``(-1,-1,1)`` already have centroid zero and equal edges of length
    ``2*sqrt(2)``. Scaling by ``edge_m / (2*sqrt(2))`` sets the edge length.
    """
    raw = np.array(
        [
            [1.0, 1.0, 1.0],
            [1.0, -1.0, -1.0],
            [-1.0, 1.0, -1.0],
            [-1.0, -1.0, 1.0],
        ],
        dtype=float,
    )
    raw_edge = float(np.linalg.norm(raw[0] - raw[1]))
    return raw * (edge_m / raw_edge)


def _three_plus_one_coordinates(
    side_m: float = TARGET_BASELINE_M,
    mast_height_m: float = 0.15,
) -> np.ndarray:
    """Equilateral triangle in a horizontal plane plus one elevated phone.

    The triangle side is ``side_m``. The fourth hydrophone sits
    ``mast_height_m`` above the triangle centroid. The returned array is
    then translated so the four-phone centroid is the origin.
    """
    radius = side_m / np.sqrt(3.0)
    raw = np.array(
        [
            [radius, 0.0, 0.0],
            [-radius / 2.0, side_m / 2.0, 0.0],
            [-radius / 2.0, -side_m / 2.0, 0.0],
            [0.0, 0.0, mast_height_m],
        ],
        dtype=float,
    )
    return raw - raw.mean(axis=0)


def _build_geometries() -> tuple[HydrophoneArray, ...]:
    length = TARGET_BASELINE_M
    linear = np.array(
        [
            [-length / 2.0, 0.0, 0.0],
            [-length / 6.0, 0.0, 0.0],
            [length / 6.0, 0.0, 0.0],
            [length / 2.0, 0.0, 0.0],
        ],
        dtype=float,
    )

    # Unequal arms so this is not a 45-degree rotation of the square.
    # X baseline = 0.25 m, Y baseline = 0.15 m. Both axes pass through
    # the origin. Maximum pairwise separation remains the X baseline.
    cross = np.array(
        [
            [length / 2.0, 0.0, 0.0],
            [0.0, 0.075, 0.0],
            [-length / 2.0, 0.0, 0.0],
            [0.0, -0.075, 0.0],
        ],
        dtype=float,
    )

    tetra_edges = tuple((i, j) for i in range(4) for j in range(i + 1, 4))

    return (
        HydrophoneArray(
            key="linear",
            name="Linear",
            description=(
                "Four hydrophones equally spaced on the X axis from "
                "-0.125 m to +0.125 m. Included as a geometrically limited "
                "reference: a collinear array does not determine a unique "
                "3D source position."
            ),
            coordinates_m=linear,
            edges=((0, 1), (1, 2), (2, 3)),
            figure_stem="01_linear",
            expected_class="collinear",
        ),
        HydrophoneArray(
            key="square_planar",
            name="Square planar",
            description=(
                "Four hydrophones at the corners of a square in the XY "
                "plane (z = 0). The square diagonal is 0.25 m. A planar "
                "array has a reflection ambiguity through its plane."
            ),
            coordinates_m=_square_coordinates(),
            edges=((0, 1), (1, 2), (2, 3), (3, 0)),
            figure_stem="02_square_planar",
            expected_class="coplanar",
        ),
        HydrophoneArray(
            key="cross_planar",
            name="Cross planar",
            description=(
                "Four hydrophones on the coordinate axes: ±0.125 m on X "
                "and ±0.075 m on Y, all z = 0. The unequal arms keep this "
                "distinct from the square (an equal-arm cross would be the "
                "square rotated by 45 degrees). The array is still planar."
            ),
            coordinates_m=cross,
            edges=((0, 1), (1, 2), (2, 3), (3, 0)),
            figure_stem="03_cross_planar",
            expected_class="coplanar",
        ),
        HydrophoneArray(
            key="tetrahedral",
            name="Tetrahedral",
            description=(
                "Regular tetrahedron centered at the origin with edge "
                "length 0.25 m. The four hydrophones are not coplanar."
            ),
            coordinates_m=_tetrahedron_coordinates(),
            edges=tetra_edges,
            figure_stem="04_tetrahedral",
            expected_class="volumetric",
        ),
        HydrophoneArray(
            key="three_plus_one",
            name="Three plus one",
            description=(
                "Equilateral triangle of side 0.25 m in a horizontal "
                "plane, plus a fourth hydrophone 0.15 m above the triangle "
                "centroid. Coordinates are then shifted so the four-phone "
                "centroid is the origin. This is a non-coplanar alternative "
                "to a regular tetrahedron."
            ),
            coordinates_m=_three_plus_one_coordinates(),
            edges=((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)),
            figure_stem="05_three_plus_one",
            expected_class="volumetric",
        ),
    )


GEOMETRIES: tuple[HydrophoneArray, ...] = _build_geometries()
GEOMETRY_BY_KEY: dict[str, HydrophoneArray] = {array.key: array for array in GEOMETRIES}


def list_geometries() -> tuple[HydrophoneArray, ...]:
    """Return the five study geometries in figure order."""
    return GEOMETRIES


def get_geometry(key: str) -> HydrophoneArray:
    """Return one geometry by its stable key."""
    try:
        return GEOMETRY_BY_KEY[key]
    except KeyError as exc:
        known = ", ".join(GEOMETRY_BY_KEY)
        raise KeyError(f"unknown geometry {key!r}; known keys: {known}") from exc


def pairwise_distances(hydrophones_m: np.ndarray) -> np.ndarray:
    """Return the 4×4 matrix of distances between hydrophones, in metres."""
    hydrophones_m = np.asarray(hydrophones_m, dtype=float)
    delta = hydrophones_m[:, np.newaxis, :] - hydrophones_m[np.newaxis, :, :]
    return np.linalg.norm(delta, axis=2)


def max_pairwise_distance_m(hydrophones_m: np.ndarray) -> float:
    """Longest hydrophone-hydrophone separation, in metres."""
    return float(np.max(pairwise_distances(hydrophones_m)))


def max_pairwise_tdoa_s(
    hydrophones_m: np.ndarray,
    sound_speed_mps: float = SOUND_SPEED_MPS,
) -> float:
    """Largest physically possible |TDOA| for this array, in seconds.

    ``|Δt|_max = d_max / c``, where ``d_max`` is the longest hydrophone pair.
    """
    if sound_speed_mps <= 0:
        raise ValueError("sound_speed_mps must be positive")
    return max_pairwise_distance_m(hydrophones_m) / float(sound_speed_mps)


def source_distances_m(source_m: np.ndarray, hydrophones_m: np.ndarray) -> np.ndarray:
    """Euclidean distances from one source to each hydrophone, in metres.

    ``d_i = ||p - h_i||``.
    """
    source_m = np.asarray(source_m, dtype=float).reshape(3)
    hydrophones_m = np.asarray(hydrophones_m, dtype=float)
    if hydrophones_m.ndim != 2 or hydrophones_m.shape[1] != 3:
        raise ValueError("hydrophones_m must have shape (n, 3)")
    return np.linalg.norm(hydrophones_m - source_m, axis=1)


def propagation_times_s(
    source_m: np.ndarray,
    hydrophones_m: np.ndarray,
    sound_speed_mps: float = SOUND_SPEED_MPS,
) -> np.ndarray:
    """Absolute travel times ``t_i = d_i / c``, in seconds."""
    if sound_speed_mps <= 0:
        raise ValueError("sound_speed_mps must be positive")
    return source_distances_m(source_m, hydrophones_m) / float(sound_speed_mps)


def true_tdoas_s(
    source_m: np.ndarray,
    hydrophones_m: np.ndarray,
    sound_speed_mps: float = SOUND_SPEED_MPS,
    reference_channel: int = 0,
) -> np.ndarray:
    """Geometry-derived TDOAs relative to the reference hydrophone, in seconds.

    ``Δt_i,ref = (d_i - d_ref) / c``.

    The reference entry is exactly 0. A negative value means hydrophone i
    is closer to the source than the reference (earlier arrival). These
    values are ground truth. They are not waveform estimates.
    """
    if sound_speed_mps <= 0:
        raise ValueError("sound_speed_mps must be positive")
    distances = source_distances_m(source_m, hydrophones_m)
    n = distances.shape[0]
    if not 0 <= reference_channel < n:
        raise ValueError("reference_channel out of range")
    tdoas = (distances - distances[reference_channel]) / float(sound_speed_mps)
    tdoas[reference_channel] = 0.0
    return tdoas


def tdoas_to_delay_samples(tdoas_s: np.ndarray, fs: float) -> np.ndarray:
    """Convert geometry TDOAs to the delay vector consumed by the simulator.

    ``delay_samples[i] = fs * Δt_i,ref``. The reference delay is 0.
    Negative delays are earlier arrivals. ``delay_signal`` already
    implements that sign, and the default capture has enough lead-in that
    a common nonnegative offset is not required. Relative delays are exactly
    the geometry TDOAs; a later common offset would not change them.
    """
    if fs <= 0:
        raise ValueError("fs must be positive")
    delays = np.asarray(tdoas_s, dtype=float) * float(fs)
    return delays


def sampling_sanity(
    fs: float,
    sound_speed_mps: float = SOUND_SPEED_MPS,
    reference_baseline_m: float = TARGET_BASELINE_M,
) -> dict[str, float]:
    """Physical scales used as scientific sanity checks.

    At 256 kHz and 1480 m/s these are:

    * sample period = 3.90625 microseconds
    * distance per sample ≈ 5.78125 mm
    * travel time across 0.25 m ≈ 168.92 microseconds
    """
    if fs <= 0:
        raise ValueError("fs must be positive")
    if sound_speed_mps <= 0:
        raise ValueError("sound_speed_mps must be positive")
    sample_period_s = 1.0 / float(fs)
    return {
        "fs_hz": float(fs),
        "sample_period_s": sample_period_s,
        "sample_period_us": sample_period_s * 1e6,
        "metres_per_sample": float(sound_speed_mps) * sample_period_s,
        "millimetres_per_sample": float(sound_speed_mps) * sample_period_s * 1e3,
        "reference_baseline_m": float(reference_baseline_m),
        "reference_max_tdoa_s": float(reference_baseline_m) / float(sound_speed_mps),
        "reference_max_tdoa_us": 1e6 * float(reference_baseline_m) / float(sound_speed_mps),
    }


def generate_source_positions(
    n_sources: int,
    seed: int,
    range_min_m: float,
    range_max_m: float,
    elevation_min_deg: float,
    elevation_max_deg: float,
) -> np.ndarray:
    """Draw a deterministic set of source XYZ positions, shape ``(n, 3)``.

    Sampling, which is intentionally simple and documented:

    * azimuth uniform on ``[0, 360)`` degrees
    * elevation uniform on ``[elevation_min_deg, elevation_max_deg]``
      (uniform in angle, not uniform in solid angle)
    * range uniform on ``[range_min_m, range_max_m]``
      (uniform in radius, not uniform in volume)

    The same seed reproduces the same coordinates. Callers must reuse one
    draw for every geometry.
    """
    if n_sources < 1:
        raise ValueError("n_sources must be positive")
    if range_min_m <= 0 or range_max_m <= range_min_m:
        raise ValueError("require 0 < range_min_m < range_max_m")
    if elevation_max_deg < elevation_min_deg:
        raise ValueError("elevation_max_deg must be >= elevation_min_deg")
    if abs(elevation_min_deg) > 89.0 or abs(elevation_max_deg) > 89.0:
        raise ValueError("elevation limits must stay within ±89 degrees")

    rng = np.random.default_rng(int(seed))
    azimuth = rng.uniform(0.0, 2.0 * np.pi, size=n_sources)
    elevation = np.deg2rad(rng.uniform(elevation_min_deg, elevation_max_deg, size=n_sources))
    radius = rng.uniform(range_min_m, range_max_m, size=n_sources)

    positions = np.column_stack(
        (
            radius * np.cos(elevation) * np.cos(azimuth),
            radius * np.cos(elevation) * np.sin(azimuth),
            radius * np.sin(elevation),
        )
    )
    return positions


def minimum_source_hydrophone_distance_m(
    sources_m: np.ndarray,
    hydrophones_m: np.ndarray,
) -> float:
    """Smallest distance from any source to any hydrophone, in metres."""
    sources_m = np.asarray(sources_m, dtype=float)
    hydrophones_m = np.asarray(hydrophones_m, dtype=float)
    delta = sources_m[:, np.newaxis, :] - hydrophones_m[np.newaxis, :, :]
    return float(np.min(np.linalg.norm(delta, axis=2)))
