"""Common-event detection for multi-channel hydrophone recordings.

Future TDOA estimation needs the *same* sample range from every channel.
If each hydrophone picked its own timestamp, the relative delays would be
destroyed before GCC-PHAT ever ran.

This module therefore:

1. Builds one detector signal from all channels
2. Chooses a single event index
3. Extracts that same window from every channel
"""

from __future__ import annotations

import numpy as np
from scipy.signal import hilbert


def signal_envelope(signal: np.ndarray) -> np.ndarray:
    """Return the Hilbert-transform magnitude (instantaneous amplitude).

    The envelope follows the burst amplitude without oscillating at the
    carrier frequency, which makes thresholding much more stable.
    """
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1:
        raise ValueError("signal_envelope expects a 1-D array")
    return np.abs(hilbert(signal))


def combined_energy(channels: np.ndarray) -> np.ndarray:
    """Build one common detector trace from all channels.

    Each channel's Hilbert envelope is squared (instantaneous power), then
    the channels are averaged. Using a shared trace means a loud channel
    cannot pick a different timestamp than a quiet one.
    """
    channels = np.asarray(channels, dtype=float)
    if channels.ndim != 2:
        raise ValueError("channels must have shape (num_channels, num_samples)")

    analytic = hilbert(channels, axis=1)
    envelopes = np.abs(analytic)
    return np.mean(envelopes ** 2, axis=0)


def detect_event(channels: np.ndarray, threshold_ratio: float = 0.5) -> int:
    """Return one event sample index shared by every channel.

    Combined energy is thresholded at ``threshold_ratio * peak``. The event
    index is the midpoint of that high-energy region so the common window is
    centered on the burst, not on a single noisy sample at the leading edge.

    This function does **not** estimate a separate arrival time per channel.
    """
    if not 0 < threshold_ratio <= 1:
        raise ValueError("threshold_ratio must be in (0, 1]")

    energy = combined_energy(channels)
    peak = float(np.max(energy))
    if peak == 0:
        return 0

    above_idx = np.flatnonzero(energy >= (threshold_ratio * peak))
    if above_idx.size == 0:
        return int(np.argmax(energy))

    return int(round(0.5 * (int(above_idx[0]) + int(above_idx[-1]))))


def extract_common_window(
    channels: np.ndarray,
    center_idx: int,
    pre_samples: int,
    post_samples: int,
) -> np.ndarray:
    """Extract the same sample range from every channel.

    The window is ``[center_idx - pre_samples, center_idx + post_samples)``.
    If that range would run off either end of the recording, the missing
    samples are filled with zeros so the returned length is always
    ``pre_samples + post_samples``.

    Zero-padding at the edges does not shift one channel relative to another.
    """
    channels = np.asarray(channels, dtype=float)
    if channels.ndim != 2:
        raise ValueError("channels must have shape (num_channels, num_samples)")
    if pre_samples < 0 or post_samples < 0:
        raise ValueError("pre_samples and post_samples must be non-negative")
    if pre_samples + post_samples == 0:
        raise ValueError("window length must be positive")

    n_channels, n_samples = channels.shape
    start = int(center_idx) - int(pre_samples)
    end = int(center_idx) + int(post_samples)
    window_len = end - start

    window = np.zeros((n_channels, window_len), dtype=float)

    src_start = max(0, start)
    src_end = min(n_samples, end)
    if src_start >= src_end:
        return window

    dest_start = src_start - start
    dest_end = dest_start + (src_end - src_start)
    window[:, dest_start:dest_end] = channels[:, src_start:src_end]
    return window
