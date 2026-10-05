"""Nine 3+1 layouts: three positive H4 heights and three base scales.

The triangle is the catalog H1/H2/H3 set. Scaling is about that triangle's
centroid, in x and y only, so the array does not translate and the plane
stays at the catalog z. H4 stays on the centroid in x and y. Its height is
measured from the triangle plane, the same convention as the H4-height study.
"""

from __future__ import annotations

import numpy as np

from simulations.h4_height_study.geometry import (
    CHANNEL_LABELS,
    REQUESTED_LABELS,
    array_for_height,
    plane_z_m,
    triangle_centroid_m,
    triangle_coordinates_m,
)
from src.geometry import HydrophoneArray

HEIGHTS_M: tuple[float, ...] = (0.30, 0.40, 0.50)
BASE_SCALES: tuple[float, ...] = (1.00, 1.25, 1.50)
CONTROL_HEIGHT_M = 0.30
CONTROL_SCALE = 1.00
EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


def geometry_id(height_m: float, base_scale: float) -> str:
    """Short id such as ``h30_b1.00`` or ``h50_b1.50``."""
    centimeters = int(round(float(height_m) * 100.0))
    return f"h{centimeters}_b{float(base_scale):.2f}"


def is_control(height_m: float, base_scale: float) -> bool:
    return np.isclose(height_m, CONTROL_HEIGHT_M) and np.isclose(base_scale, CONTROL_SCALE)


def scaled_triangle_m(base_scale: float) -> np.ndarray:
    """Catalog triangle scaled in x and y about its centroid. Z is unchanged."""
    scale = float(base_scale)
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("base scale must be a positive finite number")
    triangle = triangle_coordinates_m()
    centroid = np.mean(triangle, axis=0)
    scaled = np.array(triangle, dtype=float, copy=True)
    scaled[:, 0] = centroid[0] + scale * (triangle[:, 0] - centroid[0])
    scaled[:, 1] = centroid[1] + scale * (triangle[:, 1] - centroid[1])
    return scaled


def h4_coordinate_m(height_m: float, base_scale: float) -> np.ndarray:
    """H4 above the triangle plane, centered on the scaled triangle."""
    height = float(height_m)
    if not np.isfinite(height) or height <= 0.0:
        raise ValueError("this study uses a positive H4 height above the triangle plane")
    centroid = np.mean(scaled_triangle_m(base_scale), axis=0)
    return np.array([float(centroid[0]), float(centroid[1]), plane_z_m() + height], dtype=float)


def array_for(height_m: float, base_scale: float) -> HydrophoneArray:
    """One tested layout. The key is the geometry id."""
    name = geometry_id(height_m, base_scale)
    coordinates = np.vstack([scaled_triangle_m(base_scale), h4_coordinate_m(height_m, base_scale)])
    control = " Control layout from the H4-height study." if is_control(height_m, base_scale) else ""
    return HydrophoneArray(
        key=name,
        name=name,
        description=(
            f"Catalog 3+1 triangle scaled by {float(base_scale):.2f} about its centroid. "
            f"H4 is {float(height_m):.2f} m above that plane and centered in x and y."
            f"{control}"
        ),
        coordinates_m=coordinates,
        edges=EDGES,
        figure_stem=name.replace(".", "p"),
        expected_class="volumetric",
    )


def iter_geometries() -> list[tuple[float, float, HydrophoneArray]]:
    """Height-major order: 30 cm at each scale, then 40 cm, then 50 cm."""
    layouts = []
    for height in HEIGHTS_M:
        for scale in BASE_SCALES:
            layouts.append((float(height), float(scale), array_for(height, scale)))
    return layouts


def triangle_side_m(coordinates_m: np.ndarray) -> float:
    """Mean H1-H2-H3 side. The triangle stays equilateral, so the three agree."""
    triangle = np.asarray(coordinates_m, dtype=float)[:3]
    sides = [float(np.linalg.norm(triangle[i] - triangle[j])) for i, j in ((0, 1), (1, 2), (2, 0))]
    return float(np.mean(sides))


def coordinate_rows(height_m: float, base_scale: float, array: HydrophoneArray) -> list[dict[str, float | str | bool]]:
    side = triangle_side_m(array.coordinates_m)
    baseline = float(array.max_pairwise_distance_m())
    rows = []
    for index, xyz in enumerate(array.coordinates_m):
        rows.append(
            {
                "geometry_id": array.key,
                "h4_height_m": float(height_m),
                "base_scale": float(base_scale),
                "is_control": is_control(height_m, base_scale),
                "channel": CHANNEL_LABELS[index],
                "label": REQUESTED_LABELS[index],
                "x_m": float(xyz[0]),
                "y_m": float(xyz[1]),
                "z_m": float(xyz[2]),
                "triangle_side_m": side,
                "max_baseline_m": baseline,
            }
        )
    return rows


def assert_layouts_match_catalog() -> None:
    """Fail before any trial if the control or the scaling rule is wrong."""
    catalog_centroid = triangle_centroid_m()
    catalog_side = triangle_side_m(triangle_coordinates_m())
    control = array_for(CONTROL_HEIGHT_M, CONTROL_SCALE)
    reference = array_for_height(CONTROL_HEIGHT_M)
    if not np.allclose(control.coordinates_m, reference.coordinates_m, atol=1e-12):
        raise RuntimeError("h30_b1.00 does not match the previous +30 cm H4 array")
    if len(iter_geometries()) != 9:
        raise RuntimeError("expected exactly 9 geometries")
    seen = set()
    for height, scale, array in iter_geometries():
        if array.key in seen:
            raise RuntimeError(f"duplicate geometry id {array.key}")
        seen.add(array.key)
        triangle = array.coordinates_m[:3]
        centroid = np.mean(triangle, axis=0)
        if not np.allclose(centroid, catalog_centroid, atol=1e-12):
            raise RuntimeError(f"{array.key} moved the H1/H2/H3 centroid")
        if not np.allclose(triangle[:, 2], plane_z_m(), atol=1e-12):
            raise RuntimeError(f"{array.key} moved the triangle out of its plane")
        h4 = array.coordinates_m[3]
        if not np.allclose(h4[:2], centroid[:2], atol=1e-12):
            raise RuntimeError(f"{array.key} moved H4 off the triangle centroid")
        if not np.isclose(h4[2], plane_z_m() + height, atol=1e-12):
            raise RuntimeError(f"{array.key} H4 height is not {height} m")
        side = triangle_side_m(array.coordinates_m)
        if not np.isclose(side, catalog_side * scale, rtol=0.0, atol=1e-12):
            raise RuntimeError(f"{array.key} side {side} is not {scale} times the catalog side")
        sides = [
            float(np.linalg.norm(triangle[i] - triangle[j]))
            for i, j in ((0, 1), (1, 2), (2, 0))
        ]
        if not np.allclose(sides, side, atol=1e-12):
            raise RuntimeError(f"{array.key} triangle is no longer equilateral")
