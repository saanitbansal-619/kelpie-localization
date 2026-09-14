"""Offline preprocessing for multi-channel hydrophone recordings.

The functions here clean each channel without changing relative timing.
That rule is intentional: later TDOA / GCC-PHAT localization depends on the
sample-level arrival-time differences between hydrophones.

Pipeline per channel:

1. Remove DC (subtract the mean)
2. Zero-phase Butterworth bandpass (`sosfiltfilt`)

Channels are processed independently, but with the same filter and no cropping,
resampling, or per-channel time alignment.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def remove_dc(signal: np.ndarray) -> np.ndarray:
    """Subtract the mean of a 1-D signal.

    A constant offset is not acoustic energy. Leaving it in would dominate a
    bandpass filter's transient and inflate energy detectors.
    """
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1:
        raise ValueError("remove_dc expects a 1-D array")
    return signal - np.mean(signal)


def bandpass_filter(
    signal: np.ndarray,
    fs: float,
    lowcut: float,
    highcut: float,
    order: int = 4,
) -> np.ndarray:
    """Zero-phase Butterworth bandpass using second-order sections.

    `sosfiltfilt` runs the filter forward and backward, so the output has no
    group delay. That keeps the acoustic event at the same sample index, which
    is what we want for offline TDOA work.

    The returned array has the same length as ``signal``.
    """
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1:
        raise ValueError("bandpass_filter expects a 1-D array")
    if fs <= 0:
        raise ValueError("fs must be positive")
    if not 0 < lowcut < highcut:
        raise ValueError("require 0 < lowcut < highcut")
    nyquist = 0.5 * fs
    if highcut >= nyquist:
        raise ValueError("highcut must be below the Nyquist frequency")
    if order < 1:
        raise ValueError("order must be >= 1")

    sos = butter(order, [lowcut, highcut], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, signal)


def normalize_signal(signal: np.ndarray) -> np.ndarray:
    """Scale a 1-D signal so its peak absolute amplitude is 1.

    An all-zero input is returned unchanged so callers do not divide by zero.
    Normalization is useful for plots and detection thresholds; it is not part
    of the default per-channel preprocess, because a common scale across
    channels can still be useful later.
    """
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1:
        raise ValueError("normalize_signal expects a 1-D array")

    peak = np.max(np.abs(signal))
    if peak == 0:
        return signal.copy()
    return signal / peak


def preprocess_channel(
    signal: np.ndarray,
    fs: float,
    lowcut: float,
    highcut: float,
    order: int = 4,
) -> np.ndarray:
    """Remove DC, then bandpass one channel.

    No time shifting, cropping, or resampling is performed.
    """
    cleaned = remove_dc(signal)
    return bandpass_filter(cleaned, fs=fs, lowcut=lowcut, highcut=highcut, order=order)


def preprocess_multichannel(
    channels: np.ndarray,
    fs: float,
    lowcut: float,
    highcut: float,
    order: int = 4,
) -> np.ndarray:
    """Preprocess each channel independently, preserving sample alignment.

    Parameters
    ----------
    channels:
        Array of shape ``(num_channels, num_samples)``.
    fs, lowcut, highcut, order:
        Forwarded to :func:`preprocess_channel`.

    Returns
    -------
    np.ndarray
        Processed array with the same shape as ``channels``.

    Notes
    -----
    Do not independently time-align channels here. Relative delays are the
    signal we will later estimate with GCC-PHAT.
    """
    channels = np.asarray(channels, dtype=float)
    if channels.ndim != 2:
        raise ValueError("channels must have shape (num_channels, num_samples)")

    processed = np.empty_like(channels, dtype=float)
    for i in range(channels.shape[0]):
        processed[i] = preprocess_channel(
            channels[i],
            fs=fs,
            lowcut=lowcut,
            highcut=highcut,
            order=order,
        )
    return processed
