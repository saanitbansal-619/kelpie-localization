"""Tests for N-channel processing and the 4/5/6 hydrophone arrays."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.detection import detect_event, extract_common_window
from src.geometry import get_geometry, list_geometries, true_tdoas_s
from src.hydrophone_counts import (
    get_count_array,
    list_count_arrays,
    reference_tdoa_count,
    unordered_pair_count,
)
from src.localization import _tdoa_residual_us, classify_array, localize_from_tdoa
from src.preprocessing import preprocess_multichannel
from src.simulation import DEFAULT_FS, generate_synthetic_capture
from src.tdoa import estimate_tdoas
from simulations.hydrophone_count_study.pipeline import (
    matched_channel_noise,
    prepare_reference_waveform,
    run_count_trial,
)

SOURCE_CSV = (
    PROJECT_ROOT
    / "simulations"
    / "geometry_study"
    / "results"
    / "source_positions.csv"
)


def test_existing_geometry_catalog_is_still_five_arrays() -> None:
    assert len(list_geometries()) == 5


def test_count_arrays_match_the_envelope_and_are_volumetric() -> None:
    arrays = list_count_arrays()
    assert [array.sensor_count for array in arrays] == [4, 5, 6]
    tetra = get_geometry("tetrahedral").coordinates_m
    np.testing.assert_allclose(arrays[0].coordinates_m, tetra)
    for array in arrays:
        coords = array.coordinates_m
        assert coords.shape == (array.sensor_count, 3)
        assert np.all(np.isfinite(coords))
        np.testing.assert_allclose(coords.mean(axis=0), 0.0, atol=1e-12)
        assert classify_array(coords) == "volumetric"
        baseline = array.max_pairwise_distance_m()
        assert baseline == pytest.approx(0.25, rel=0, abs=1e-12)
        assert array.max_physical_tdoa_s(1480.0) == pytest.approx(0.25 / 1480.0)
        assert reference_tdoa_count(array.sensor_count) == array.sensor_count - 1


def test_pair_counts_are_not_independent_equations() -> None:
    assert unordered_pair_count(4) == 6
    assert unordered_pair_count(5) == 10
    assert unordered_pair_count(6) == 15
    assert reference_tdoa_count(4) == 3
    assert reference_tdoa_count(5) == 4
    assert reference_tdoa_count(6) == 5


def test_pipeline_accepts_five_and_six_channels() -> None:
    for count in (4, 5, 6):
        array = get_count_array(count)
        source = np.array([3.0, -1.2, 2.0])
        tdoas = true_tdoas_s(source, array.coordinates_m)
        assert tdoas.shape == (count,)
        assert tdoas[0] == 0.0
        delays = tdoas * DEFAULT_FS
        channels, info = generate_synthetic_capture(
            n_channels=count,
            fs=DEFAULT_FS,
            delays_samples=delays,
            noise_std=0.0,
            dc_offsets=np.linspace(-0.2, 0.2, count),
            seed=0,
        )
        assert channels.shape[0] == count
        processed = preprocess_multichannel(
            channels, fs=float(info["fs"]), lowcut=15_000.0, highcut=45_000.0
        )
        assert processed.shape == channels.shape
        window = extract_common_window(
            processed,
            center_idx=detect_event(processed),
            pre_samples=256,
            post_samples=512,
        )
        estimated, _ = estimate_tdoas(window, fs=float(info["fs"]), reference_channel=0)
        assert estimated.shape == (count,)
        assert estimated[0] == 0.0
        assert np.all(np.isfinite(estimated))
        assert np.count_nonzero(np.arange(count) != 0) == reference_tdoa_count(count)


def test_localization_residual_length_and_perfect_recovery() -> None:
    source = np.array([3.0, -1.2, 2.0])
    for count in (4, 5, 6):
        coords = get_count_array(count).coordinates_m
        tdoas = true_tdoas_s(source, coords)
        residual = _tdoa_residual_us(source, coords, tdoas, 1480.0, 0)
        assert residual.shape == (count - 1,)
        np.testing.assert_allclose(residual, 0.0, atol=1e-6)
        result = localize_from_tdoa(coords, tdoas)
        assert result.success, result.failure_reason
        np.testing.assert_allclose(result.position_m, source, atol=1e-3)


def test_matched_noise_shares_the_leading_channels() -> None:
    four = matched_channel_noise(32, noise_std=0.2, seed=17, n_draw=4)
    six = matched_channel_noise(32, noise_std=0.2, seed=17, n_draw=6)
    np.testing.assert_allclose(six[:4], four)
    assert np.all(np.isfinite(six))


def test_count_trial_keeps_failures_explicit(tmp_path: Path) -> None:
    array = get_count_array(4)
    _chirp, reference = prepare_reference_waveform(DEFAULT_FS, 0.04, 0.015)
    settings = {
        "dc_offsets": [0.35, -0.22, 0.18, -0.40, 0.27, -0.15],
        "noise_draw_channels": 6,
        "search_margin_samples": 1.0,
        "bandpass_low_hz": 15000.0,
        "bandpass_high_hz": 45000.0,
        "bandpass_order": 4,
        "pre_samples": 1024,
        "post_samples": 1536,
        "gcc_interpolation": 16,
    }
    row = run_count_trial(
        array,
        np.array([3.0, -1.2, 2.0]),
        source_id=0,
        snr_db=40.0,
        reference=reference,
        fs=DEFAULT_FS,
        sound_speed_mps=1480.0,
        noise_std=0.0,
        settings=settings,
    )
    assert row["sensor_count"] == 4
    assert row["est_tdoa_h0_us"] == 0.0
    assert np.isfinite(row["est_tdoa_h3_us"])
    assert np.isnan(row["est_tdoa_h4_us"])
    assert np.isnan(row["tdoa_err_h5_us"])
    assert row["solver_success"] is True
    assert np.isfinite(row["position_error_m"])
    assert np.isfinite(row["angular_error_deg"])
    assert not (tmp_path / "experiment_results.csv").exists()


def test_geometry_study_sources_are_reused_unchanged() -> None:
    text = SOURCE_CSV.read_text(encoding="utf-8").splitlines()
    assert text[0].startswith("source_id,")
    assert len(text) - 1 == 300
    first = text[1].split(",")
    assert first[0] == "0"
    assert float(first[1]) == pytest.approx(3.154983962, abs=1e-8)
