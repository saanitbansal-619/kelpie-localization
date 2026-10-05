"""3+1 arrays whose triangle is frozen and whose fourth phone moves in z.

H1, H2, and H3 are channels H0, H1, and H2 of the catalog 3+1 array.
They are not recentered when H4 moves. H4 stays at the triangle centroid
in x and y. Its height is measured from the H1/H2/H3 plane, not from the
origin.
"""

from __future__ import annotations

import numpy as np

from src.geometry import HydrophoneArray, get_geometry

HEIGHTS_M: tuple[float, ...] = (
    -0.30,
    -0.20,
    -0.15,
    -0.10,
    -0.05,
    0.05,
    0.10,
    0.15,
    0.20,
    0.30,
)

AXIS_CONVENTION = {
    "+X": "FRONT",
    "-X": "BACK",
    "+Y": "RIGHT",
    "-Y": "LEFT",
    "+Z": "ABOVE",
    "-Z": "BELOW",
}

REQUESTED_LABELS = ("H1", "H2", "H3", "H4")
CHANNEL_LABELS = ("H0", "H1", "H2", "H3")


def height_name(height_m: float) -> str:
    """Stable folder name such as ``h4_neg_15cm`` or ``h4_pos_05cm``."""
    if height_m == 0.0 or not np.isfinite(height_m):
        raise ValueError("H4 height must be a non-zero finite offset from the triangle plane")
    sign = "pos" if height_m > 0.0 else "neg"
    centimeters = int(round(abs(float(height_m)) * 100.0))
    return f"h4_{sign}_{centimeters:02d}cm"


def triangle_coordinates_m() -> np.ndarray:
    """Catalog H1/H2/H3, shape ``(3, 3)``. These coordinates are not shifted."""
    return np.array(get_geometry("three_plus_one").coordinates_m[:3], dtype=float, copy=True)


def original_h4_m() -> np.ndarray:
    """Catalog H4, shape ``(3,)``."""
    return np.array(get_geometry("three_plus_one").coordinates_m[3], dtype=float, copy=True)


def plane_z_m() -> float:
    triangle = triangle_coordinates_m()
    if not np.allclose(triangle[:, 2], triangle[0, 2]):
        raise RuntimeError("catalog H1/H2/H3 are not in one horizontal plane")
    return float(triangle[0, 2])


def triangle_centroid_m() -> np.ndarray:
    return np.mean(triangle_coordinates_m(), axis=0)


def h4_coordinate_m(height_m: float) -> np.ndarray:
    """H4 at ``height_m`` above the fixed triangle plane."""
    if float(height_m) == 0.0 or not np.isfinite(height_m):
        raise ValueError("H4 height must be a non-zero finite offset from the triangle plane")
    centroid = triangle_centroid_m()
    return np.array(
        [float(centroid[0]), float(centroid[1]), plane_z_m() + float(height_m)],
        dtype=float,
    )


def array_for_height(height_m: float) -> HydrophoneArray:
    """Four-phone array with the catalog triangle and one moved H4."""
    name = height_name(height_m)
    triangle = triangle_coordinates_m()
    coordinates = np.vstack([triangle, h4_coordinate_m(height_m)])
    side = "above" if height_m > 0.0 else "below"
    return HydrophoneArray(
        key=name,
        name=name,
        description=(
            "Catalog 3+1 triangle held fixed. "
            f"H4 is {abs(height_m):.2f} m {side} the H1/H2/H3 plane, "
            "centered on that triangle in x and y."
        ),
        coordinates_m=coordinates,
        edges=((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)),
        figure_stem=name,
        expected_class="volumetric",
    )


def coordinate_records(coordinates_m: np.ndarray) -> list[dict[str, float | str]]:
    records = []
    for index, xyz in enumerate(np.asarray(coordinates_m, dtype=float)):
        records.append(
            {
                "channel": CHANNEL_LABELS[index],
                "label": REQUESTED_LABELS[index],
                "x_m": float(xyz[0]),
                "y_m": float(xyz[1]),
                "z_m": float(xyz[2]),
            }
        )
    return records
