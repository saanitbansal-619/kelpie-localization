"""Tests for the five array geometries and geometry-derived TDOAs."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.detection import detect_event, extract_common_window
from src.geometry import (
    SOUND_SPEED_MPS,
    TARGET_BASELINE_M,
    generate_source_positions,
    list_geometries,
    max_pairwise_distance_m,
    max_pairwise_tdoa_s,
    minimum_source_hydrophone_distance_m,
    pairwise_distances,
    propagation_times_s,
    sampling_sanity,
    source_distances_m,
    tdoas_to_delay_samples,
    true_tdoas_s,
)
from src.preprocessing import preprocess_multichannel
from src.simulation import DEFAULT_FS, generate_synthetic_capture
from src.tdoa import DEFAULT_SOUND_SPEED_MPS, estimate_tdoas


def test_five_geometries_are_unique_finite_four_phone_arrays() -> None:
    arrays = list_geometries()
    assert len(arrays) == 5
    keys = [array.key for array in arrays]
    names = [array.name for array in arrays]
    assert len(set(keys)) == 5
    assert len(set(names)) == 5
    for array in arrays:
        coords = array.coordinates_m
        assert coords.shape == (4, 3)
        assert np.all(np.isfinite(coords))
        assert array.center_m.shape == (3,)
        np.testing.assert_allclose(array.center_m, 0.0, atol=1e-12)


def test_cross_is_not_a_rotated_square() -> None:
    arrays = {array.key: array for array in list_geometries()}
    square = pairwise_distances(arrays["square_planar"].coordinates_m)
    cross = pairwise_distances(arrays["cross_planar"].coordinates_m)
    # Upper-triangle edge lengths. A rotated square would match the square.
    square_edges = np.sort(square[np.triu_indices(4, k=1)])
    cross_edges = np.sort(cross[np.triu_indices(4, k=1)])
    assert not np.allclose(square_edges, cross_edges, atol=1e-6)


def test_each_array_maximum_baseline_is_the_shared_scale() -> None:
    for array in list_geometries():
        baseline = array.max_pairwise_distance_m()
        assert baseline == pytest.approx(TARGET_BASELINE_M, rel=1e-9, abs=1e-12)
        assert baseline <= TARGET_BASELINE_M + 1e-12


def test_sound_speed_matches_tdoa_module() -> None:
    assert SOUND_SPEED_MPS == DEFAULT_SOUND_SPEED_MPS


def test_sampling_sanity_at_256_khz() -> None:
    sanity = sampling_sanity(fs=256_000.0, sound_speed_mps=1480.0)
    assert sanity["sample_period_us"] == pytest.approx(3.90625, abs=1e-12)
    assert sanity["millimetres_per_sample"] == pytest.approx(5.78125, abs=1e-9)
    assert sanity["reference_max_tdoa_us"] == pytest.approx(0.25 / 1480.0 * 1e6, abs=1e-9)
    assert sanity["reference_max_tdoa_us"] == pytest.approx(168.9189189, abs=1e-6)


def test_distance_and_tdoa_formula() -> None:
    hydrophones = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    source = np.array([0.0, 1.0, 0.0])
    distances = source_distances_m(source, hydrophones)
    np.testing.assert_allclose(distances, [1.0, np.sqrt(2.0), 0.0, np.sqrt(2.0)])

    c = 1480.0
    times = propagation_times_s(source, hydrophones, sound_speed_mps=c)
    np.testing.assert_allclose(times, distances / c)

    tdoas = true_tdoas_s(source, hydrophones, sound_speed_mps=c, reference_channel=0)
    assert tdoas[0] == 0.0
    np.testing.assert_allclose(tdoas, (distances - distances[0]) / c)
    # A 1480 m path at 1480 m/s is exactly one second. Units are seconds.
    long_path = propagation_times_s(
        np.array([1480.0, 0.0, 0.0]),
        np.array([[0.0, 0.0, 0.0]]),
        sound_speed_mps=c,
    )
    assert long_path[0] == pytest.approx(1.0)


def test_reference_tdoa_is_zero_and_pairwise_tdoas_obey_baseline() -> None:
    source = np.array([2.0, -1.0, 1.5])
    for array in list_geometries():
        coords = array.coordinates_m
        tdoas = true_tdoas_s(source, coords)
        assert tdoas.shape == (4,)
        assert tdoas[0] == 0.0
        assert np.all(np.isfinite(tdoas))
        physical_max = max_pairwise_tdoa_s(coords)
        assert np.max(np.abs(tdoas)) <= physical_max + 1e-12

        distances = source_distances_m(source, coords)
        separation = pairwise_distances(coords)
        for i in range(4):
            for j in range(4):
                assert abs(distances[i] - distances[j]) <= separation[i, j] + 1e-9


def test_delay_samples_preserve_relative_tdoa() -> None:
    source = np.array([3.0, 1.0, -0.5])
    array = list_geometries()[3]
    tdoas = true_tdoas_s(source, array.coordinates_m)
    delays = tdoas_to_delay_samples(tdoas, fs=DEFAULT_FS)
    assert delays[0] == 0.0
    np.testing.assert_allclose(delays / DEFAULT_FS, tdoas)


def test_source_seed_reproduces_positions_and_stays_clear_of_hydrophones() -> None:
    kwargs = dict(
        n_sources=40,
        seed=20260926,
        range_min_m=2.0,
        range_max_m=8.0,
        elevation_min_deg=-50.0,
        elevation_max_deg=50.0,
    )
    first = generate_source_positions(**kwargs)
    second = generate_source_positions(**kwargs)
    np.testing.assert_array_equal(first, second)
    assert first.shape == (40, 3)
    ranges = np.linalg.norm(first, axis=1)
    assert np.min(ranges) >= 2.0
    assert np.max(ranges) <= 8.0

    for array in list_geometries():
        closest = minimum_source_hydrophone_distance_m(first, array.coordinates_m)
        assert closest > 1.0


def test_geometry_capture_has_four_channels_and_preprocessing_preserves_shape() -> None:
    array = list_geometries()[0]
    tdoas = true_tdoas_s(np.array([2.5, 0.4, 1.0]), array.coordinates_m)
    delays = tdoas_to_delay_samples(tdoas, fs=DEFAULT_FS)
    channels, info = generate_synthetic_capture(
        n_channels=4,
        fs=DEFAULT_FS,
        delays_samples=delays,
        noise_std=0.0,
        seed=0,
    )
    assert channels.shape[0] == 4
    processed = preprocess_multichannel(channels, fs=float(info["fs"]), lowcut=15_000.0, highcut=45_000.0)
    assert processed.shape == channels.shape
    event = detect_event(processed)
    window = extract_common_window(processed, center_idx=event, pre_samples=256, post_samples=512)
    assert window.shape[0] == 4
    estimated, _ = estimate_tdoas(window, fs=float(info["fs"]), reference_channel=0)
    assert estimated.shape == (4,)
    assert np.all(np.isfinite(estimated))
    assert estimated[0] == 0.0
