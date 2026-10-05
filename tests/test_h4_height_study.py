"""Checks for the separate H4-height study. No result files are written."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from simulations.h4_height_study.directions import classify_direction
from simulations.h4_height_study.geometry import (
    array_for_height,
    h4_coordinate_m,
    height_name,
    original_h4_m,
    plane_z_m,
    triangle_centroid_m,
    triangle_coordinates_m,
)
from simulations.h4_height_study.paths import OUTPUT_ROOT, assert_output_path
from src.geometry import get_geometry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_h1_h2_h3_stay_on_the_catalog_triangle_when_h4_moves() -> None:
    catalog = get_geometry("three_plus_one").coordinates_m
    low = array_for_height(-0.30).coordinates_m
    high = array_for_height(0.30).coordinates_m
    np.testing.assert_allclose(low[:3], catalog[:3])
    np.testing.assert_allclose(high[:3], catalog[:3])
    np.testing.assert_allclose(low[:3], high[:3])
    assert not np.allclose(low[3], high[3])


def test_positive_15_cm_reproduces_the_original_h4() -> None:
    np.testing.assert_allclose(h4_coordinate_m(0.15), original_h4_m())
    assert h4_coordinate_m(0.15)[2] - plane_z_m() == pytest.approx(0.15)
    centroid = triangle_centroid_m()
    for height in (-0.30, -0.05, 0.05, 0.30):
        h4 = h4_coordinate_m(height)
        np.testing.assert_allclose(h4[:2], centroid[:2])
        assert h4[2] - plane_z_m() == pytest.approx(height)


def test_zero_height_is_rejected_and_signs_get_distinct_names() -> None:
    with pytest.raises(ValueError):
        array_for_height(0.0)
    assert height_name(-0.05) == "h4_neg_05cm"
    assert height_name(0.30) == "h4_pos_30cm"
    assert height_name(-0.30) == "h4_neg_30cm"


def test_direction_rule_keeps_partial_axes_and_orders_x_then_y_then_z() -> None:
    center = triangle_centroid_m()
    front = center + np.array([5.0, 0.2, 0.1])
    diagonal = center + np.array([4.0, 3.0, 0.2])
    octant = center + np.array([3.0, 2.5, 2.0])
    above = center + np.array([0.2, 0.1, 5.0])
    assert classify_direction(front, center) == "FRONT"
    assert classify_direction(diagonal, center) == "FRONT-RIGHT"
    assert classify_direction(octant, center) == "FRONT-RIGHT-ABOVE"
    assert classify_direction(above, center) == "ABOVE"
    assert classify_direction(front, center) == classify_direction(front, center)


def test_outputs_cannot_enter_existing_result_directories() -> None:
    allowed = assert_output_path(OUTPUT_ROOT / "change_1_noise" / "raw" / "h4_pos_15cm.csv")
    assert allowed.parent.parent.parent.name == "results_h4_height_study"
    with pytest.raises(RuntimeError):
        assert_output_path(PROJECT_ROOT / "results" / "tetrahedral" / "change_1_noise" / "noise_experiment_results.csv")
    with pytest.raises(RuntimeError):
        assert_output_path(PROJECT_ROOT / "results" / "geometry_comparison" / "geometry_comparison_summary.csv")
    with pytest.raises(RuntimeError):
        assert_output_path(PROJECT_ROOT / "simulations" / "noise_study" / "results" / "noise_experiment_results.csv")
    with pytest.raises(RuntimeError):
        assert_output_path(PROJECT_ROOT / "simulations" / "waveform_study" / "results" / "waveform_experiment_results.csv")


def test_triangle_matches_the_catalog_plane() -> None:
    triangle = triangle_coordinates_m()
    assert triangle.shape == (3, 3)
    assert triangle[:, 2] == pytest.approx(triangle[0, 2])
