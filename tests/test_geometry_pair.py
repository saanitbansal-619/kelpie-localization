"""Tetrahedral versus 3+1 geometry checks for the paired experiments."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from simulations.geometry_pair.directions import classify_direction
from simulations.geometry_pair.paths import assert_rows_match_geometry, assert_safe_output, result_dir
from simulations.noise_study.run_noise_experiment import load_config as load_noise_config
from simulations.waveform_study.run_waveform_experiment import load_sources
from src.geometry import (
    TARGET_BASELINE_M,
    generate_source_positions,
    get_geometry,
    make_three_plus_one,
    pairwise_distances,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_tetrahedral_has_four_hydrophones_and_the_shared_baseline() -> None:
    array = get_geometry("tetrahedral")
    assert array.coordinates_m.shape == (4, 3)
    distances = pairwise_distances(array.coordinates_m)
    off_diagonal = distances[~np.eye(4, dtype=bool)]
    assert off_diagonal == pytest.approx(TARGET_BASELINE_M)


def test_three_plus_one_has_four_hydrophones_with_a_coplanar_triangle() -> None:
    array = get_geometry("three_plus_one")
    assert array.coordinates_m.shape == (4, 3)
    triangle = array.coordinates_m[:3]
    assert triangle[:, 2] == pytest.approx(triangle[0, 2])
    edge_a = triangle[1] - triangle[0]
    edge_b = triangle[2] - triangle[0]
    normal = np.cross(edge_a, edge_b)
    normal = normal / np.linalg.norm(normal)
    assert abs(normal[2]) == pytest.approx(1.0)
    assert array.coordinates_m[3, 2] != pytest.approx(triangle[0, 2])


def test_maximum_baselines_match() -> None:
    tetra = get_geometry("tetrahedral").max_pairwise_distance_m()
    three = get_geometry("three_plus_one").max_pairwise_distance_m()
    assert tetra == pytest.approx(TARGET_BASELINE_M)
    assert three == pytest.approx(TARGET_BASELINE_M)
    assert three == pytest.approx(tetra, rel=0.01)


def test_z_offset_flips_the_three_plus_one_orientation() -> None:
    catalog = get_geometry("three_plus_one")
    upright = make_three_plus_one(0.15)
    inverted = make_three_plus_one(-0.15)
    np.testing.assert_allclose(upright.coordinates_m, catalog.coordinates_m)
    np.testing.assert_allclose(inverted.coordinates_m[:, :2], upright.coordinates_m[:, :2])
    np.testing.assert_allclose(inverted.coordinates_m[:, 2], -upright.coordinates_m[:, 2])
    assert upright.coordinates_m[3, 2] > upright.coordinates_m[0, 2]
    assert inverted.coordinates_m[3, 2] < inverted.coordinates_m[0, 2]
    with pytest.raises(ValueError):
        make_three_plus_one(0.0)


def test_direction_labels_keep_diagonals_out_of_the_cardinal_bins() -> None:
    center = np.zeros(3)
    assert classify_direction(np.array([5.0, 0.2, 0.1]), center) == "FRONT"
    assert classify_direction(np.array([-5.0, 0.2, 0.1]), center) == "BACK"
    assert classify_direction(np.array([0.1, 5.0, 0.2]), center) == "RIGHT"
    assert classify_direction(np.array([0.1, -5.0, 0.2]), center) == "LEFT"
    assert classify_direction(np.array([0.2, 0.1, 5.0]), center) == "ABOVE"
    assert classify_direction(np.array([0.2, 0.1, -5.0]), center) == "BELOW"
    assert classify_direction(np.array([4.0, 3.0, 0.2]), center) == "FRONT-RIGHT"


def test_both_studies_draw_the_same_sources_twice() -> None:
    config = load_noise_config()
    kwargs = dict(
        n_sources=int(config["n_trials"]),
        seed=int(config["random_seed"]),
        range_min_m=float(config["range_min_m"]),
        range_max_m=float(config["range_max_m"]),
        elevation_min_deg=float(config["elevation_min_deg"]),
        elevation_max_deg=float(config["elevation_max_deg"]),
    )
    first = generate_source_positions(**kwargs)
    second = generate_source_positions(**kwargs)
    np.testing.assert_allclose(first, second)
    ids_a, xyz_a = load_sources(100)
    ids_b, xyz_b = load_sources(100)
    np.testing.assert_array_equal(ids_a, ids_b)
    np.testing.assert_allclose(xyz_a, xyz_b)


def test_result_paths_cannot_overwrite_another_geometry_or_preserved_results() -> None:
    tetra = result_dir("tetrahedral", "change_1_noise")
    three = result_dir("three_plus_one", "change_2_waveform")
    assert tetra.parent.name == "tetrahedral"
    assert three.parent.name == "three_plus_one"
    assert tetra != three
    with pytest.raises(RuntimeError):
        assert_safe_output(three, "tetrahedral")
    preserved = PROJECT_ROOT / "simulations" / "noise_study" / "results" / "noise_experiment_results.csv"
    with pytest.raises(RuntimeError):
        assert_safe_output(preserved, "tetrahedral")
    waveform = PROJECT_ROOT / "simulations" / "waveform_study" / "results" / "waveform_experiment_results.csv"
    with pytest.raises(RuntimeError):
        assert_safe_output(waveform, "three_plus_one")
    with pytest.raises(RuntimeError):
        assert_rows_match_geometry(
            [{"hydrophone_configuration": "tetrahedral"}],
            "three_plus_one",
        )
    assert_rows_match_geometry(
        [{"hydrophone_configuration": "three_plus_one"}],
        "three_plus_one",
    )
