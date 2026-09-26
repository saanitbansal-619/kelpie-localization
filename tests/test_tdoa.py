"""Unit tests for GCC-PHAT TDOA estimation and its sign convention."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.detection import detect_event, extract_common_window
from src.preprocessing import preprocess_multichannel
from src.simulation import DEFAULT_FS, delay_signal, generate_chirp, generate_synthetic_capture
from src.tdoa import (
    DEFAULT_INTERPOLATION,
    DEFAULT_SOUND_SPEED_MPS,
    estimate_tdoas,
    gcc_phat,
    max_tau_from_baseline,
    normalized_cross_correlation,
)

FS = DEFAULT_FS
LOWCUT = 15_000.0
HIGHCUT = 45_000.0
PRE_SAMPLES = 1024
POST_SAMPLES = 1536

# Future ~0.25 m baseline at ~1480 m/s → |Δt|max ≈ 169 µs ≈ 43.3 samples.
# All synthetic pairwise TDOAs used here stay inside that bound.
PHYS_BASELINE_M = 0.25
PHYS_MAX_TAU_S = PHYS_BASELINE_M / DEFAULT_SOUND_SPEED_MPS

# Mixed-sign, physically plausible delays (samples at 256 kHz).
# 10.5 → +41.02 µs, -8.0 → -31.25 µs, 18.25 → +71.29 µs.
MULTI_DELAYS_SAMPLES = np.array([0.0, 10.5, -8.0, 18.25])


def _delayed_pair(delay_samples: float, noise_std: float = 0.0, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Build (signal, reference) where ``signal`` is ``reference`` delayed by ``delay_samples``.

    Positive ``delay_samples`` means the signal channel arrives later.
    """
    chirp = generate_chirp(fs=FS)
    reference = np.zeros(4096, dtype=float)
    start = 800
    reference[start : start + chirp.size] = chirp
    signal = delay_signal(reference, delay_samples)
    if noise_std > 0:
        rng = np.random.default_rng(seed)
        signal = signal + rng.normal(0.0, noise_std, size=signal.shape)
        reference = reference + rng.normal(0.0, noise_std, size=reference.shape)
    return signal, reference


def _pipeline_window(
    delays_samples: np.ndarray,
    noise_std: float = 0.0,
    seed: int = 0,
) -> tuple[np.ndarray, dict]:
    channels, info = generate_synthetic_capture(
        n_channels=int(delays_samples.size),
        delays_samples=delays_samples,
        noise_std=noise_std,
        seed=seed,
    )
    processed = preprocess_multichannel(channels, fs=float(info["fs"]), lowcut=LOWCUT, highcut=HIGHCUT)
    event_idx = detect_event(processed)
    window = extract_common_window(
        processed,
        center_idx=event_idx,
        pre_samples=PRE_SAMPLES,
        post_samples=POST_SAMPLES,
    )
    return window, info


def test_sampling_and_geometry_sanity() -> None:
    """Documented physical numbers must stay consistent."""
    sample_period_s = 1.0 / 256_000.0
    assert sample_period_s * 1e6 == pytest.approx(3.90625, abs=1e-12)

    metres_per_sample = DEFAULT_SOUND_SPEED_MPS * sample_period_s
    assert metres_per_sample * 1e3 == pytest.approx(5.78125, abs=1e-9)

    max_tau = max_tau_from_baseline(0.25, DEFAULT_SOUND_SPEED_MPS)
    assert max_tau * 1e6 == pytest.approx(1e6 * 0.25 / 1480.0, abs=1e-9)
    assert max_tau * 1e6 == pytest.approx(168.9189, abs=0.01)

    assert np.max(np.abs(MULTI_DELAYS_SAMPLES / FS)) < max_tau


def test_exact_zero_delay() -> None:
    signal, reference = _delayed_pair(0.0)
    result = gcc_phat(signal, reference, fs=FS)
    assert result.tau == pytest.approx(0.0, abs=1e-6)
    assert np.all(np.isfinite(result.correlation))


def test_positive_delay_sign_convention() -> None:
    """CH1 later than CH0 → TDOA must be positive and close to truth."""
    delay_samples = 10.0
    signal, reference = _delayed_pair(delay_samples)
    result = gcc_phat(signal, reference, fs=FS)
    true_tau = delay_samples / FS
    assert result.tau > 0.0
    assert result.tau == pytest.approx(true_tau, abs=2e-6)


def test_negative_delay_sign_convention() -> None:
    """CH1 earlier than CH0 → TDOA must be negative and close to truth."""
    delay_samples = -8.0
    signal, reference = _delayed_pair(delay_samples)
    result = gcc_phat(signal, reference, fs=FS)
    true_tau = delay_samples / FS
    assert result.tau < 0.0
    assert result.tau == pytest.approx(true_tau, abs=2e-6)


def test_fractional_sample_delay_uses_interpolation() -> None:
    """A delay that is not an integer multiple of 1/256000 should still be recovered."""
    delay_samples = 7.3
    assert delay_samples != round(delay_samples)
    signal, reference = _delayed_pair(delay_samples)
    result = gcc_phat(signal, reference, fs=FS, interpolation=DEFAULT_INTERPOLATION)
    true_tau = delay_samples / FS
    # Linear interpolation used to *create* the delay is imperfect; a few µs is OK.
    assert result.tau == pytest.approx(true_tau, abs=3e-6)
    lag_resolution = 1.0 / (DEFAULT_INTERPOLATION * FS)
    assert lag_resolution * 1e6 == pytest.approx(3.90625 / 16.0, abs=1e-9)


def test_multichannel_tdoas_match_known_signs_and_values() -> None:
    window, info = _pipeline_window(MULTI_DELAYS_SAMPLES, noise_std=0.0, seed=0)
    tdoas, diagnostics = estimate_tdoas(
        window,
        fs=float(info["fs"]),
        reference_channel=0,
        max_taus=PHYS_MAX_TAU_S,
    )
    true_tdoas = MULTI_DELAYS_SAMPLES / FS

    assert tdoas[0] == 0.0
    assert diagnostics[0] is None
    assert tdoas[1] > 0.0
    assert tdoas[2] < 0.0
    assert tdoas[3] > 0.0
    np.testing.assert_allclose(tdoas, true_tdoas, atol=3e-6)


def test_estimator_works_under_moderate_noise() -> None:
    true_tdoas = MULTI_DELAYS_SAMPLES / FS
    # Several seeds: unregularized PHAT can look fine on one draw and fail on another.
    for seed in (0, 3, 7, 11):
        window, info = _pipeline_window(MULTI_DELAYS_SAMPLES, noise_std=0.10, seed=seed)
        tdoas, _ = estimate_tdoas(
            window,
            fs=float(info["fs"]),
            reference_channel=0,
            max_taus=PHYS_MAX_TAU_S,
        )
        assert tdoas[0] == 0.0
        assert tdoas[1] > 0.0
        assert tdoas[2] < 0.0
        np.testing.assert_allclose(tdoas, true_tdoas, atol=10e-6)


def test_max_tau_rejects_peaks_outside_search_range() -> None:
    delay_samples = 30.0
    signal, reference = _delayed_pair(delay_samples)
    unconstrained = gcc_phat(signal, reference, fs=FS, max_tau=None)
    assert unconstrained.tau == pytest.approx(delay_samples / FS, abs=2e-6)

    max_tau = 5.0 / FS
    constrained = gcc_phat(signal, reference, fs=FS, max_tau=max_tau)
    half_bin = 0.5 / (DEFAULT_INTERPOLATION * FS)
    assert abs(constrained.tau) <= max_tau + half_bin
    assert abs(constrained.tau - delay_samples / FS) > max_tau
    assert np.max(np.abs(constrained.lags_seconds)) <= max_tau + half_bin


def test_near_zero_spectral_magnitudes_are_finite() -> None:
    rng = np.random.default_rng(3)
    signal = rng.normal(scale=1e-20, size=512)
    reference = rng.normal(scale=1e-20, size=512)
    result = gcc_phat(signal, reference, fs=FS)
    assert np.isfinite(result.tau)
    assert np.isfinite(result.peak_value)
    assert np.all(np.isfinite(result.correlation))
    assert not np.any(np.isnan(result.correlation))
    assert not np.any(np.isinf(result.correlation))


def test_estimate_tdoas_does_not_modify_or_shift_channels() -> None:
    window, info = _pipeline_window(MULTI_DELAYS_SAMPLES, noise_std=0.0, seed=1)
    original = window.copy()
    estimate_tdoas(window, fs=float(info["fs"]), reference_channel=0, max_taus=PHYS_MAX_TAU_S)
    np.testing.assert_array_equal(window, original)


def test_preprocessing_does_not_invent_a_relative_delay() -> None:
    """Zero-phase preprocessing must not change TDOA sign or invent a large shift."""
    delays = np.array([0.0, 12.0])
    channels, info = generate_synthetic_capture(
        n_channels=2,
        delays_samples=delays,
        noise_std=0.0,
        dc_offsets=np.array([0.3, -0.2]),
        seed=0,
    )
    raw_tdoas, _ = estimate_tdoas(channels, fs=float(info["fs"]), max_taus=PHYS_MAX_TAU_S)
    processed = preprocess_multichannel(channels, fs=float(info["fs"]), lowcut=LOWCUT, highcut=HIGHCUT)
    processed_tdoas, _ = estimate_tdoas(processed, fs=float(info["fs"]), max_taus=PHYS_MAX_TAU_S)
    assert raw_tdoas[1] > 0.0
    assert processed_tdoas[1] > 0.0
    assert processed_tdoas[1] == pytest.approx(raw_tdoas[1], abs=3e-6)
    assert processed_tdoas[1] == pytest.approx(delays[1] / FS, abs=3e-6)


def test_normalized_cross_correlation_shares_sign_convention() -> None:
    signal, reference = _delayed_pair(-8.0)
    ncc = normalized_cross_correlation(signal, reference, fs=FS)
    assert ncc.tau < 0.0
    assert ncc.tau == pytest.approx(-8.0 / FS, abs=2e-6)
