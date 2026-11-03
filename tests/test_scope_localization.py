"""Offline tests for acquisition records fed to the existing localizer.

No VISA resource is opened. The acoustic cases are synthetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquisition.waveform import CHANNEL_IDS, HYDROPHONE_IDS, FourChannelRecord, load_npz, save_npz
from simulations.scope_validation.paths import PROJECT_ROOT as STUDY_ROOT
from simulations.scope_validation.paths import assert_output_path
from simulations.scope_validation.pipeline import (
    VIRTUAL_SAMPLE_RATE_HZ,
    expected_tdoas_s,
    gcc_quality,
    localize_record,
    stated_hydrophones_m,
    synthetic_record,
)
from src.geometry import make_three_plus_one, max_pairwise_distance_m, pairwise_distances
from src.localization import classify_array
from src.tdoa import GCCPHATResult


def test_stated_coordinates_are_the_requested_array() -> None:
    expected = np.array(
        [
            [0.1443376, 0.0, 0.0],
            [-0.0721688, 0.125, 0.0],
            [-0.0721688, -0.125, 0.0],
            [0.0, 0.0, -0.400],
        ]
    )
    phones = stated_hydrophones_m()
    assert np.array_equal(phones, expected)
    assert classify_array(phones) == "volumetric"
    assert phones[3, 2] < phones[0, 2]
    assert pairwise_distances(phones)[1, 2] == pytest.approx(0.25)
    distances = pairwise_distances(phones)
    assert max_pairwise_distance_m(phones) == pytest.approx(distances[0, 3])
    catalog = make_three_plus_one(-0.4)
    assert not np.allclose(catalog.coordinates_m, phones)


def test_output_guard_refuses_historical_results() -> None:
    with pytest.raises(RuntimeError):
        assert_output_path(STUDY_ROOT / "results" / "virtual_trials.csv")
    with pytest.raises(RuntimeError):
        assert_output_path(STUDY_ROOT / "results_h4_height_study" / "summary.md")
    with pytest.raises(RuntimeError):
        assert_output_path(STUDY_ROOT / "results_joint_geometry_optimization" / "summary.md")


def test_single_correlation_peak_agrees_with_its_envelope() -> None:
    lags = np.linspace(-1e-4, 1e-4, 401)
    correlation = np.exp(-0.5 * (lags / 2e-5) ** 2)
    peak = int(np.argmax(correlation))
    diagnostic = GCCPHATResult(
        tau=float(lags[peak]),
        correlation=correlation,
        lags_seconds=lags,
        peak_index=peak,
        peak_value=float(correlation[peak]),
    )
    quality = gcc_quality(diagnostic, 30_000.0)
    assert quality["on_search_edge"] is False
    assert quality["envelope_disagreement"] is False
    assert quality["low_contrast"] is False


def test_argmax_a_carrier_cycle_from_the_envelope_is_ambiguous() -> None:
    lags = np.linspace(-2e-4, 2e-4, 2001)
    carrier_hz = 30_000.0
    correlation = np.exp(-0.5 * (lags / 4e-5) ** 2) * np.cos(2.0 * np.pi * carrier_hz * lags)
    index = int(np.argmin(np.abs(lags - 1.0 / carrier_hz)))
    diagnostic = GCCPHATResult(
        tau=float(lags[index]),
        correlation=correlation,
        lags_seconds=lags,
        peak_index=index,
        peak_value=float(correlation[index]),
    )
    quality = gcc_quality(diagnostic, carrier_hz)
    assert quality["envelope_disagreement"] is True
    assert float(quality["envelope_cycles"]) == pytest.approx(1.0, abs=0.05)


def test_search_edge_peak_is_flagged() -> None:
    correlation = np.array([4.0, 1.0, 0.2, 0.0])
    lags = np.array([-3e-5, -1e-5, 1e-5, 3e-5])
    diagnostic = GCCPHATResult(
        tau=float(lags[0]),
        correlation=correlation,
        lags_seconds=lags,
        peak_index=0,
        peak_value=float(correlation[0]),
    )
    quality = gcc_quality(diagnostic, 30_000.0)
    assert quality["on_search_edge"] is True


def test_synthetic_record_round_trips_and_ignores_a_false_source(tmp_path: Path) -> None:
    source = np.array([2.0, 1.0, 1.5])
    record = synthetic_record(source, 30_000.0, snr_db=None, noise_seed=20261101)
    assert record.samples.shape[0] == 4
    assert record.channel_ids == CHANNEL_IDS
    assert record.hydrophone_ids == HYDROPHONE_IDS
    assert record.sample_interval_s == pytest.approx(1.0 / VIRTUAL_SAMPLE_RATE_HZ)
    path = tmp_path / "capture.npz"
    save_npz(str(path), record)
    loaded = load_npz(str(path))
    loaded.metadata["true_source_m"] = [50.0, 50.0, 50.0]

    direct = localize_record(record, stated_hydrophones_m(), 30_000.0)
    replayed = localize_record(loaded, stated_hydrophones_m(), 30_000.0)
    assert np.array_equal(direct.tdoa_s, replayed.tdoa_s)
    assert direct.solver_success
    assert direct.reliable
    error = float(np.linalg.norm(direct.position_m - source))
    assert error < 0.25
    tdoa_error_us = np.max(np.abs(direct.tdoa_s - expected_tdoas_s(source))) * 1e6
    assert tdoa_error_us < 5.0
    assert float(np.linalg.norm(direct.position_m - np.array([50.0, 50.0, 50.0]))) > 5.0


def test_half_sample_offset_moves_the_h2_delay() -> None:
    source = np.array([2.0, 1.0, 1.5])
    offsets = np.array([0.0, 0.5, 0.0, 0.0])
    record = synthetic_record(
        source,
        30_000.0,
        snr_db=None,
        noise_seed=20261101,
        channel_offset_samples=offsets,
    )
    outcome = localize_record(record, stated_hydrophones_m(), 30_000.0)
    expected = expected_tdoas_s(source, offsets)
    assert outcome.solver_success
    assert np.max(np.abs(outcome.tdoa_s - expected)) * 1e6 < 5.0


def test_noise_only_record_is_not_reliable() -> None:
    rng = np.random.default_rng(1)
    n_samples = 8000
    samples = rng.normal(0.0, 0.05, size=(4, n_samples))
    record = FourChannelRecord(
        samples=samples,
        time_s=np.arange(n_samples, dtype=np.float64) / VIRTUAL_SAMPLE_RATE_HZ,
        sample_interval_s=1.0 / VIRTUAL_SAMPLE_RATE_HZ,
        channel_ids=CHANNEL_IDS,
        hydrophone_ids=HYDROPHONE_IDS,
        metadata={"source": "noise"},
    )
    outcome = localize_record(record, stated_hydrophones_m(), 30_000.0)
    assert outcome.reliable is False
