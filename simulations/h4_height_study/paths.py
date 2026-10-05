"""Output guard. This study writes only under ``results_h4_height_study/``."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "results_h4_height_study"

PROTECTED_DIRS = (
    PROJECT_ROOT / "results",
    PROJECT_ROOT / "simulations" / "noise_study" / "results",
    PROJECT_ROOT / "simulations" / "noise_study" / "figures",
    PROJECT_ROOT / "simulations" / "waveform_study" / "results",
    PROJECT_ROOT / "simulations" / "waveform_study" / "figures",
    PROJECT_ROOT / "simulations" / "geometry_study" / "results",
    PROJECT_ROOT / "simulations" / "geometry_study" / "figures",
    PROJECT_ROOT / "simulations" / "hydrophone_count_study" / "results",
    PROJECT_ROOT / "simulations" / "hydrophone_count_study" / "figures",
)


def assert_output_path(path: Path) -> Path:
    """Refuse every existing result directory, including ``results/``."""
    resolved = Path(path).resolve()
    root = OUTPUT_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise RuntimeError(f"refusing to write outside {root}: {resolved}")
    for protected in PROTECTED_DIRS:
        protected_resolved = protected.resolve()
        if resolved == protected_resolved or protected_resolved in resolved.parents:
            raise RuntimeError(f"refusing to write into protected results: {resolved}")
    return resolved


def output_path(*parts: str) -> Path:
    return assert_output_path(OUTPUT_ROOT.joinpath(*parts))
