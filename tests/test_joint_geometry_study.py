"""Coordinate and ranking checks for the joint geometry study."""

from __future__ import annotations

import numpy as np
import pytest

from simulations.h4_height_study.geometry import array_for_height, triangle_centroid_m
from simulations.joint_geometry_study.geometry import (
    CONTROL_HEIGHT_M,
    CONTROL_SCALE,
    HEIGHTS_M,
    BASE_SCALES,
    array_for,
    assert_layouts_match_catalog,
    geometry_id,
    h4_coordinate_m,
    iter_geometries,
    scaled_triangle_m,
    triangle_side_m,
)
from simulations.joint_geometry_study.paths import OUTPUT_ROOT, assert_output_path
from simulations.joint_geometry_study.ranking import rank_layouts


def test_nine_layouts_and_control_match_previous_plus_30cm() -> None:
    assert_layouts_match_catalog()
    layouts = iter_geometries()
    assert len(layouts) == 9
    assert [geometry_id(height, scale) for height, scale, _ in layouts] == [
        "h30_b1.00",
        "h30_b1.25",
        "h30_b1.50",
        "h40_b1.00",
        "h40_b1.25",
        "h40_b1.50",
        "h50_b1.00",
        "h50_b1.25",
        "h50_b1.50",
    ]
    control = array_for(CONTROL_HEIGHT_M, CONTROL_SCALE)
    assert np.allclose(control.coordinates_m, array_for_height(0.30).coordinates_m)


def test_scaling_keeps_centroid_shape_and_h4_height() -> None:
    centroid = triangle_centroid_m()
    catalog_side = triangle_side_m(scaled_triangle_m(1.0))
    for scale in BASE_SCALES:
        triangle = scaled_triangle_m(scale)
        assert np.allclose(triangle.mean(axis=0), centroid)
        assert np.isclose(triangle_side_m(triangle), catalog_side * scale)
    for height in HEIGHTS_M:
        for scale in BASE_SCALES:
            h4 = h4_coordinate_m(height, scale)
            assert np.allclose(h4[:2], centroid[:2])
            assert np.isclose(h4[2] - centroid[2], height)


def test_output_guard_rejects_previous_result_folders(tmp_path) -> None:
    with pytest.raises(RuntimeError):
        assert_output_path(OUTPUT_ROOT.parent / "results" / "joint_geometry_optimization" / "x.csv")
    with pytest.raises(RuntimeError):
        assert_output_path(OUTPUT_ROOT.parent / "results_h4_height_study" / "x.csv")
    allowed = assert_output_path(OUTPUT_ROOT / "summaries" / "geometry_comparison_summary.csv")
    assert allowed.name == "geometry_comparison_summary.csv"


def test_ranking_does_not_use_median_alone() -> None:
    rows = [
        _summary("accurate", median=0.20, p95=0.50, angle=0.05, success=0.50, catastrophic=0.50),
        _summary("reliable", median=0.90, p95=2.50, angle=0.40, success=0.98, catastrophic=0.02),
        _summary("balanced", median=0.40, p95=1.00, angle=0.10, success=0.85, catastrophic=0.15),
        _summary("dominated", median=0.70, p95=1.50, angle=0.30, success=0.70, catastrophic=0.30),
    ]
    ranked = rank_layouts(rows)
    by_id = {row["geometry_id"]: row for row in ranked}
    assert "best_accuracy" in by_id["accurate"]["roles"]
    assert "best_reliability" in by_id["reliable"]["roles"]
    assert "best_balanced" in by_id["balanced"]["roles"]
    assert by_id["dominated"]["pareto"] is False
    assert by_id["accurate"]["pareto"] is True
    assert by_id["reliable"]["pareto"] is True


def _summary(name: str, *, median: float, p95: float, angle: float, success: float, catastrophic: float) -> dict:
    return {
        "geometry_id": name,
        "h4_height_m": 0.3,
        "base_scale": 1.0,
        "is_control": name == "balanced",
        "triangle_side_m": 0.25,
        "max_baseline_m": 0.4,
        "median_localization_error_m": median,
        "p95_localization_error_m": p95,
        "median_angular_error_deg": angle,
        "success_rate": success,
        "catastrophic_failure_rate": catastrophic,
    }
