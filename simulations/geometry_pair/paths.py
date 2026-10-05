"""Output locations for the tetrahedral versus 3+1 comparison.

Existing Change #1 and Change #2 result files stay in their original
folders. This package never writes there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "results"
COMPARISON_DIR = RESULTS_ROOT / "geometry_comparison"

GEOMETRIES = ("tetrahedral", "three_plus_one")
CHANGES = ("change_1_noise", "change_2_waveform")

LEGACY_RESULT_DIRS = (
    PROJECT_ROOT / "simulations" / "noise_study" / "results",
    PROJECT_ROOT / "simulations" / "noise_study" / "figures",
    PROJECT_ROOT / "simulations" / "waveform_study" / "results",
    PROJECT_ROOT / "simulations" / "waveform_study" / "figures",
    PROJECT_ROOT / "simulations" / "geometry_study" / "results",
    PROJECT_ROOT / "simulations" / "geometry_study" / "figures",
    PROJECT_ROOT / "simulations" / "hydrophone_count_study" / "results",
    PROJECT_ROOT / "simulations" / "hydrophone_count_study" / "figures",
)


def result_dir(geometry: str, change: str) -> Path:
    """Return ``results/<geometry>/<change>`` after rejecting unsafe paths."""
    if geometry not in GEOMETRIES:
        raise ValueError(f"geometry must be one of {GEOMETRIES}")
    if change not in CHANGES:
        raise ValueError(f"change must be one of {CHANGES}")
    path = (RESULTS_ROOT / geometry / change).resolve()
    return assert_safe_output(path, geometry)


def assert_safe_output(path: Path, geometry: str) -> Path:
    """Refuse another geometry's folder and every preserved result folder."""
    if geometry not in GEOMETRIES:
        raise ValueError(f"geometry must be one of {GEOMETRIES}")
    resolved = Path(path).resolve()
    for legacy in LEGACY_RESULT_DIRS:
        legacy_resolved = legacy.resolve()
        if resolved == legacy_resolved or legacy_resolved in resolved.parents:
            raise RuntimeError(f"refusing to write into preserved results: {resolved}")
    allowed = (RESULTS_ROOT / geometry).resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise RuntimeError(f"refusing to write {geometry} results outside {allowed}")
    return resolved


def assert_rows_match_geometry(rows: list[dict[str, Any]], geometry: str) -> None:
    """Refuse a table whose rows belong to a different array."""
    for row in rows:
        recorded = str(row.get("hydrophone_configuration", "")).strip()
        if recorded != geometry:
            raise RuntimeError(
                f"refusing to write {recorded or 'unlabeled'} rows into the {geometry} results"
            )
