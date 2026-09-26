"""TDOA localization and direction metrics for a known hydrophone array.

The measurement model, with hydrophone  ``ref`` as the time reference, is

    Δt_i,ref = (||p - h_i|| - ||p - h_ref||) / c

A nonlinear least-squares fit (SciPy) estimates ``p`` from measured TDOAs
when the array geometry makes that problem observable.

Collinear and coplanar arrays are reported as failures. A numerical solver
can still return a point for those arrays, but the point is not a unique
3D solution:

* collinear: TDOAs are unchanged by any rotation about the array axis
* coplanar: TDOAs are unchanged if the source is reflected through the plane

Those cases return a non-finite position and ``success=False``. They are
not filled in with a half-space assumption or a convenient initial guess.

Direction is computed from the array centroid to a position. Angular error
is the angle between two direction vectors. It is not a position error.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from .geometry import SOUND_SPEED_MPS

GEOMETRY_COLLINEAR = "collinear"
GEOMETRY_COPLANAR = "coplanar"
GEOMETRY_VOLUMETRIC = "volumetric"

# Singular values below this fraction of the largest are treated as zero
# when classifying the array. Built coordinates are exact, so the gap
# between a true zero and a real aperture is many orders of magnitude.
_RANK_TOL = 1e-8

# Solutions farther than this from the centroid are treated as numerical
# divergence, not as acoustic estimates. The study sources lie within a
# few metres; 200 m is only a guard against exploded iterates.
_MAX_RANGE_M = 200.0

# Two low-residual solutions separated by more than this angle are an
# ambiguous fit, not a unique position.
_AMBIGUITY_ANGLE_DEG = 20.0


@dataclass(frozen=True)
class LocalizationResult:
    """Outcome of one TDOA localization attempt.

    ``position_m`` is finite only when ``success`` is True. A failed solve
    does not carry a stand-in coordinate. ``residual_rms_s`` is the RMS
    TDOA residual of the accepted fit, in seconds, or NaN when no fit is
    reported. ``failure_reason`` is an empty string on success.
    """

    success: bool
    position_m: np.ndarray
    residual_rms_s: float
    geometry_class: str
    failure_reason: str

    def __post_init__(self) -> None:
        position = np.asarray(self.position_m, dtype=float).reshape(3).copy()
        object.__setattr__(self, "position_m", position)


def classify_array(hydrophones_m: np.ndarray, rank_tol: float = _RANK_TOL) -> str:
    """Classify an array as collinear, coplanar, or volumetric.

    The rank is the number of singular values of the centered coordinate
    matrix that exceed ``rank_tol`` times the largest singular value.
    """
    hydrophones_m = np.asarray(hydrophones_m, dtype=float)
    if hydrophones_m.ndim != 2 or hydrophones_m.shape[1] != 3:
        raise ValueError("hydrophones_m must have shape (n, 3)")
    if hydrophones_m.shape[0] < 2:
        raise ValueError("at least two hydrophones are required")

    centered = hydrophones_m - np.mean(hydrophones_m, axis=0)
    singular = np.linalg.svd(centered, compute_uv=False)
    scale = float(singular[0]) if singular[0] > 0 else 1.0
    rank = int(np.sum(singular > rank_tol * scale))
    if rank <= 1:
        return GEOMETRY_COLLINEAR
    if rank == 2:
        return GEOMETRY_COPLANAR
    return GEOMETRY_VOLUMETRIC


def array_center_m(hydrophones_m: np.ndarray) -> np.ndarray:
    """Centroid of the hydrophone coordinates."""
    hydrophones_m = np.asarray(hydrophones_m, dtype=float)
    return np.mean(hydrophones_m, axis=0)


def direction_angles_deg(origin_m: np.ndarray, point_m: np.ndarray) -> tuple[float, float]:
    """Azimuth and elevation of ``point_m`` as seen from ``origin_m``.

    Azimuth is ``atan2(y, x)`` in degrees, on ``(-180, 180]``.
    Elevation is ``atan2(z, horizontal range)`` in degrees.
    """
    vector = np.asarray(point_m, dtype=float).reshape(3) - np.asarray(origin_m, dtype=float).reshape(3)
    return vector_to_azimuth_elevation_deg(vector)


def vector_to_azimuth_elevation_deg(vector_m: np.ndarray) -> tuple[float, float]:
    """Azimuth and elevation of a direction vector, in degrees."""
    vector_m = np.asarray(vector_m, dtype=float).reshape(3)
    norm = float(np.linalg.norm(vector_m))
    if norm == 0.0 or not np.isfinite(norm):
        raise ValueError("direction vector must be finite and non-zero")
    azimuth = float(np.degrees(np.arctan2(vector_m[1], vector_m[0])))
    horizontal = float(np.hypot(vector_m[0], vector_m[1]))
    elevation = float(np.degrees(np.arctan2(vector_m[2], horizontal)))
    return azimuth, elevation


def angular_error_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    """Angle between two direction vectors, in degrees, on ``[0, 180]``.

    The vectors do not need to be unit length. Position error is a different
    quantity and is not computed here.
    """
    a = np.asarray(vector_a, dtype=float).reshape(-1)
    b = np.asarray(vector_b, dtype=float).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("direction vectors must have the same shape")
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0 or not np.isfinite(norm_a) or not np.isfinite(norm_b):
        raise ValueError("direction vectors must be finite and non-zero")
    cosine = float(np.dot(a, b) / (norm_a * norm_b))
    cosine = float(np.clip(cosine, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def angular_error_between_points_deg(
    origin_m: np.ndarray,
    point_a_m: np.ndarray,
    point_b_m: np.ndarray,
) -> float:
    """Angular separation of two points as viewed from ``origin_m``."""
    origin_m = np.asarray(origin_m, dtype=float).reshape(3)
    vector_a = np.asarray(point_a_m, dtype=float).reshape(3) - origin_m
    vector_b = np.asarray(point_b_m, dtype=float).reshape(3) - origin_m
    return angular_error_deg(vector_a, vector_b)


def _nan_position() -> np.ndarray:
    return np.full(3, np.nan, dtype=float)


def _failure(geometry_class: str, reason: str) -> LocalizationResult:
    return LocalizationResult(
        success=False,
        position_m=_nan_position(),
        residual_rms_s=float("nan"),
        geometry_class=geometry_class,
        failure_reason=reason,
    )


def _tdoa_residual_us(
    position_m: np.ndarray,
    hydrophones_m: np.ndarray,
    tdoas_s: np.ndarray,
    sound_speed_mps: float,
    reference_channel: int,
) -> np.ndarray:
    """Predicted-minus-measured TDOA residual, in microseconds, excluding the reference."""
    distances = np.linalg.norm(hydrophones_m - position_m.reshape(1, 3), axis=1)
    predicted = (distances - distances[reference_channel]) / sound_speed_mps
    mask = np.ones(hydrophones_m.shape[0], dtype=bool)
    mask[reference_channel] = False
    return (predicted[mask] - tdoas_s[mask]) * 1e6


def _far_field_direction(
    hydrophones_m: np.ndarray,
    tdoas_s: np.ndarray,
    sound_speed_mps: float,
    reference_channel: int,
) -> np.ndarray:
    """Unit vector used only to seed the nonlinear solver.

    Far-field model: ``c * Δt_i ≈ (h_ref - h_i) · u``.
    This is not the reported source direction.
    """
    rows = []
    targets = []
    for index in range(hydrophones_m.shape[0]):
        if index == reference_channel:
            continue
        rows.append(hydrophones_m[reference_channel] - hydrophones_m[index])
        targets.append(sound_speed_mps * tdoas_s[index])
    design = np.vstack(rows)
    direction, *_ = np.linalg.lstsq(design, np.asarray(targets, dtype=float), rcond=None)
    norm = float(np.linalg.norm(direction))
    if not np.isfinite(norm) or norm < 1e-9:
        return np.array([1.0, 0.0, 0.0])
    return direction / norm


def _initial_guesses(
    hydrophones_m: np.ndarray,
    tdoas_s: np.ndarray,
    sound_speed_mps: float,
    reference_channel: int,
) -> list[np.ndarray]:
    center = array_center_m(hydrophones_m)
    direction = _far_field_direction(hydrophones_m, tdoas_s, sound_speed_mps, reference_channel)
    ranges = (1.5, 3.0, 6.0, 12.0)
    guesses = [center + radius * direction for radius in ranges]
    guesses += [center - radius * direction for radius in ranges]
    for axis in np.eye(3):
        guesses.append(center + 4.0 * axis)
        guesses.append(center - 4.0 * axis)
    return guesses


def localize_from_tdoa(
    hydrophones_m: np.ndarray,
    tdoas_s: np.ndarray,
    sound_speed_mps: float = SOUND_SPEED_MPS,
    reference_channel: int = 0,
) -> LocalizationResult:
    """Estimate source position from TDOAs and known hydrophone coordinates.

    Parameters
    ----------
    hydrophones_m:
        Shape ``(n, 3)``. Four hydrophones are the intended case.
    tdoas_s:
        Shape ``(n,)``, in seconds, relative to ``reference_channel``.
        The reference entry is ignored and treated as zero.
    sound_speed_mps:
        Speed of sound in metres per second.
    reference_channel:
        Index of the reference hydrophone.

    Returns
    -------
    LocalizationResult
        ``success`` is True only for a volumetric array that produced one
        finite, unambiguous, bounded least-squares position. Degenerate
        geometries do not return a position.
    """
    hydrophones_m = np.asarray(hydrophones_m, dtype=float)
    tdoas_s = np.asarray(tdoas_s, dtype=float)
    if hydrophones_m.ndim != 2 or hydrophones_m.shape[1] != 3:
        raise ValueError("hydrophones_m must have shape (n, 3)")
    if tdoas_s.shape != (hydrophones_m.shape[0],):
        raise ValueError("tdoas_s must have one entry per hydrophone")
    if sound_speed_mps <= 0:
        raise ValueError("sound_speed_mps must be positive")
    n_hydrophones = hydrophones_m.shape[0]
    if not 0 <= reference_channel < n_hydrophones:
        raise ValueError("reference_channel out of range")
    if n_hydrophones < 4:
        return _failure("underdetermined", "fewer_than_four_hydrophones")
    if not np.all(np.isfinite(hydrophones_m)) or not np.all(np.isfinite(tdoas_s)):
        return _failure("invalid_input", "non_finite_input")

    geometry_class = classify_array(hydrophones_m)
    if geometry_class == GEOMETRY_COLLINEAR:
        return _failure(
            geometry_class,
            "geometric_degeneracy_collinear",
        )
    if geometry_class == GEOMETRY_COPLANAR:
        return _failure(
            geometry_class,
            "geometric_degeneracy_coplanar",
        )

    measured = tdoas_s.copy()
    measured[reference_channel] = 0.0

    def residual(position: np.ndarray) -> np.ndarray:
        return _tdoa_residual_us(
            position,
            hydrophones_m,
            measured,
            sound_speed_mps,
            reference_channel,
        )

    center = array_center_m(hydrophones_m)
    fits: list[tuple[np.ndarray, float]] = []
    for guess in _initial_guesses(hydrophones_m, measured, sound_speed_mps, reference_channel):
        solution = least_squares(
            residual,
            np.asarray(guess, dtype=float),
            method="lm",
            ftol=1e-12,
            xtol=1e-12,
            gtol=1e-12,
            max_nfev=80,
        )
        position = np.asarray(solution.x, dtype=float)
        if not np.all(np.isfinite(position)):
            continue
        residual_us = residual(position)
        if not np.all(np.isfinite(residual_us)):
            continue
        range_m = float(np.linalg.norm(position - center))
        if not np.isfinite(range_m) or range_m > _MAX_RANGE_M or range_m < 1e-3:
            continue
        residual_rms_s = float(np.sqrt(np.mean((residual_us * 1e-6) ** 2)))
        fits.append((position, residual_rms_s))

    if not fits:
        return _failure(geometry_class, "no_bounded_solution")

    fits.sort(key=lambda item: item[1])
    best_position, best_residual = fits[0]
    # 500 µs RMS is several times the ~169 µs physical maximum TDOA of a
    # 0.25 m array, so the measurements are not a usable localization.
    if best_residual > 5e-4:
        return _failure(geometry_class, "residual_above_physical_scale")

    tolerance_s = best_residual + max(5e-6, 0.25 * best_residual)
    similar = [item for item in fits if item[1] <= tolerance_s]
    for position, _residual in similar[1:]:
        try:
            separation = angular_error_between_points_deg(center, best_position, position)
        except ValueError:
            return _failure(geometry_class, "undefined_direction")
        if separation > _AMBIGUITY_ANGLE_DEG:
            return _failure(geometry_class, "ambiguous_local_minima")

    if not np.all(np.isfinite(best_position)):
        return _failure(geometry_class, "non_finite_solution")

    return LocalizationResult(
        success=True,
        position_m=best_position,
        residual_rms_s=best_residual,
        geometry_class=geometry_class,
        failure_reason="",
    )
