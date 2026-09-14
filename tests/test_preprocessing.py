"""Unit tests for DC removal, filtering, and common-window extraction."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.detection import extract_common_window
from src.preprocessing import (
    bandpass_filter,
    normalize_signal,
    preprocess_multichannel,
    remove_dc,
)
from src.simulation import DEFAULT_FS, generate_chirp

FS = DEFAULT_FS
LOWCUT = 15_000.0
HIGHCUT = 45_000.0


def test_dc_removal_leaves_approximately_zero_mean() -> None:
    rng = np.random.default_rng(1)
    signal = rng.normal(size=2048) + 2.7
    cleaned = remove_dc(signal)
    assert abs(float(np.mean(cleaned))) < 1e-10


def test_normalization_peak_is_approximately_one() -> None:
    signal = np.array([0.2, -0.5, 0.1, 0.4], dtype=float)
    normalized = normalize_signal(signal)
    assert pytest.approx(1.0, abs=1e-12) == float(np.max(np.abs(normalized)))


def test_zero_input_normalization_does_not_fail() -> None:
    zeros = np.zeros(32, dtype=float)
    normalized = normalize_signal(zeros)
    assert normalized.shape == zeros.shape
    assert np.all(normalized == 0)


def test_bandpass_output_keeps_the_same_number_of_samples() -> None:
    chirp = generate_chirp(fs=FS, duration_s=0.004)
    filtered = bandpass_filter(chirp, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT)
    assert filtered.shape == chirp.shape


def test_multichannel_preprocessing_preserves_shape() -> None:
    n_channels, n_samples = 4, 4096
    rng = np.random.default_rng(2)
    channels = rng.normal(size=(n_channels, n_samples))
    processed = preprocess_multichannel(channels, fs=FS, lowcut=LOWCUT, highcut=HIGHCUT)
    assert processed.shape == channels.shape


def test_common_window_has_expected_channel_count() -> None:
    channels = np.arange(4 * 200, dtype=float).reshape(4, 200)
    pre_samples, post_samples = 20, 30
    window = extract_common_window(channels, center_idx=100, pre_samples=pre_samples, post_samples=post_samples)
    assert window.shape[0] == channels.shape[0]
    assert window.shape[1] == pre_samples + post_samples


def test_common_window_extraction_uses_identical_indices_for_every_channel() -> None:
    # Distinct offsets per channel would reveal any per-channel index mismatch.
    n_samples = 100
    channels = np.vstack(
        [
            np.arange(n_samples, dtype=float),
            np.arange(n_samples, dtype=float) + 1000.0,
            np.arange(n_samples, dtype=float) + 2000.0,
            np.arange(n_samples, dtype=float) + 3000.0,
        ]
    )
    center_idx = 50
    pre_samples = 10
    post_samples = 20
    window = extract_common_window(channels, center_idx, pre_samples, post_samples)

    expected_slice = slice(center_idx - pre_samples, center_idx + post_samples)
    for channel in range(channels.shape[0]):
        np.testing.assert_array_equal(window[channel], channels[channel, expected_slice])
