"""Synthetic 4-channel hydrophone capture generator.

This module exists so the preprocessing pipeline can be developed and tested
before any hardware is available. A short linear chirp is treated as a single
acoustic source. Four channels are formed by delaying that source, then noise
and DC offsets are added to mimic a messy analog front-end.

Default sample rate: 256 kHz
Default chirp: 18 kHz → 42 kHz over about 4 ms
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.signal import chirp as scipy_chirp
from scipy.signal.windows import tukey

DEFAULT_FS = 256_000.0
DEFAULT_F_START_HZ = 18_000.0
DEFAULT_F_END_HZ = 42_000.0
DEFAULT_CHIRP_DURATION_S = 0.004
DEFAULT_CAPTURE_DURATION_S = 0.040
DEFAULT_EVENT_TIME_S = 0.015
DEFAULT_N_CHANNELS = 4

# Relative delays in samples, referenced to channel 0.
# These are small compared with a typical 15–20 cm hydrophone baseline at 256 kHz.
DEFAULT_DELAYS_SAMPLES = np.array([0.0, 6.0, 13.5, 21.0])
DEFAULT_DC_OFFSETS = np.array([0.35, -0.22, 0.18, -0.40])
DEFAULT_NOISE_STD = 0.08


def generate_chirp(
    fs: float = DEFAULT_FS,
    duration_s: float = DEFAULT_CHIRP_DURATION_S,
    f_start_hz: float = DEFAULT_F_START_HZ,
    f_end_hz: float = DEFAULT_F_END_HZ,
    amplitude: float = 1.0,
    taper: bool = True,
) -> np.ndarray:
    """Generate a short linear-frequency chirp.

    Parameters
    ----------
    fs:
        Sample rate in Hz.
    duration_s:
        Chirp length in seconds.
    f_start_hz, f_end_hz:
        Instantaneous start and end frequencies.
    amplitude:
        Peak amplitude before tapering.
    taper:
        If True, apply a Tukey window so the burst does not click on/off.

    Returns
    -------
    np.ndarray
        1-D chirp samples.
    """
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    if fs <= 0:
        raise ValueError("fs must be positive")

    n_samples = int(round(duration_s * fs))
    if n_samples < 2:
        raise ValueError("chirp is too short for the given sample rate")

    t = np.arange(n_samples, dtype=float) / fs
    t1 = t[-1]
    signal = amplitude * scipy_chirp(
        t,
        f0=f_start_hz,
        f1=f_end_hz,
        t1=t1,
        method="linear",
    )

    if taper:
        # Mild taper: mostly chirp, with short fade-in / fade-out.
        signal = signal * tukey(n_samples, alpha=0.25)

    return signal.astype(float)


def delay_signal(signal: np.ndarray, delay_samples: float) -> np.ndarray:
    """Shift a 1-D signal by a possibly fractional number of samples.

    A positive delay means the waveform arrives later (moves to the right).
    Linear interpolation is used so sub-sample delays can be represented.
    Samples that would come from outside the original array are filled with 0.

    The output length always matches the input length.
    """
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1:
        raise ValueError("delay_signal expects a 1-D array")

    n = signal.shape[0]
    sample_index = np.arange(n, dtype=float)
    delayed = np.interp(sample_index - delay_samples, sample_index, signal, left=0.0, right=0.0)
    return delayed


def apply_channel_delays(
    source: np.ndarray,
    delays_samples: np.ndarray,
    n_channels: int | None = None,
) -> np.ndarray:
    """Create a multi-channel array by delaying one source signal.

    Parameters
    ----------
    source:
        1-D source waveform, already placed in the capture buffer.
    delays_samples:
        Relative delay for each channel, in samples. Channel 0 is typically 0.
    n_channels:
        Optional channel count. Defaults to ``len(delays_samples)``.

    Returns
    -------
    np.ndarray
        Array of shape ``(num_channels, num_samples)``.
    """
    source = np.asarray(source, dtype=float)
    delays_samples = np.asarray(delays_samples, dtype=float)
    if source.ndim != 1:
        raise ValueError("source must be 1-D")
    if delays_samples.ndim != 1:
        raise ValueError("delays_samples must be 1-D")

    if n_channels is None:
        n_channels = int(delays_samples.shape[0])
    if delays_samples.shape[0] != n_channels:
        raise ValueError("delays_samples length must match n_channels")

    channels = np.zeros((n_channels, source.shape[0]), dtype=float)
    for i, delay in enumerate(delays_samples):
        channels[i] = delay_signal(source, float(delay))
    return channels


def add_gaussian_noise(
    signals: np.ndarray,
    noise_std: float,
    rng: np.random.Generator | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Add independent Gaussian noise to every sample.

    ``noise_std`` is the standard deviation of the noise, in the same units as
    the signal. A value of 0 leaves the input unchanged (still copied).
    """
    signals = np.asarray(signals, dtype=float)
    if noise_std < 0:
        raise ValueError("noise_std must be non-negative")

    if rng is None:
        rng = np.random.default_rng(seed)

    if noise_std == 0:
        return signals.copy()

    noise = rng.normal(loc=0.0, scale=noise_std, size=signals.shape)
    return signals + noise


def add_dc_offsets(channels: np.ndarray, dc_offsets: np.ndarray) -> np.ndarray:
    """Add a constant bias to each channel.

    Analog front-ends often sit at a non-zero mid-scale voltage. That offset
    is not acoustic information and should be removed before filtering.
    """
    channels = np.asarray(channels, dtype=float)
    dc_offsets = np.asarray(dc_offsets, dtype=float)

    if channels.ndim != 2:
        raise ValueError("channels must have shape (num_channels, num_samples)")
    if dc_offsets.shape != (channels.shape[0],):
        raise ValueError("dc_offsets must have one value per channel")

    return channels + dc_offsets[:, np.newaxis]


def generate_synthetic_capture(
    n_channels: int = DEFAULT_N_CHANNELS,
    fs: float = DEFAULT_FS,
    delays_samples: np.ndarray | None = None,
    noise_std: float = DEFAULT_NOISE_STD,
    dc_offsets: np.ndarray | None = None,
    capture_duration_s: float = DEFAULT_CAPTURE_DURATION_S,
    event_time_s: float = DEFAULT_EVENT_TIME_S,
    chirp_duration_s: float = DEFAULT_CHIRP_DURATION_S,
    f_start_hz: float = DEFAULT_F_START_HZ,
    f_end_hz: float = DEFAULT_F_END_HZ,
    amplitude: float = 1.0,
    seed: int | None = 0,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Generate a noisy 4-channel synthetic hydrophone capture.

    The chirp is placed at ``event_time_s`` on the delay-0 reference. Other
    channels receive the same waveform later, according to ``delays_samples``.
    Gaussian noise and per-channel DC offsets are applied last.

    Parameters
    ----------
    n_channels:
        Number of hydrophone channels.
    fs:
        Sample rate in Hz.
    delays_samples:
        Known relative delays in samples. If omitted, a small 4-channel set is used.
    noise_std:
        Standard deviation of additive Gaussian noise.
    dc_offsets:
        Constant bias per channel. If omitted, a default mixed-sign set is used.
    capture_duration_s:
        Total length of the simulated recording.
    event_time_s:
        Start time of the chirp on the delay-0 channel.
    chirp_duration_s, f_start_hz, f_end_hz, amplitude:
        Chirp parameters forwarded to :func:`generate_chirp`.
    seed:
        RNG seed for repeatable noise. ``None`` draws unpredictable noise.

    Returns
    -------
    channels:
        Array of shape ``(num_channels, num_samples)``.
    info:
        Dictionary of ground-truth parameters, including ``delays_samples``.
    """
    if n_channels < 1:
        raise ValueError("n_channels must be at least 1")

    if delays_samples is None:
        if n_channels == DEFAULT_N_CHANNELS:
            delays_samples = DEFAULT_DELAYS_SAMPLES.copy()
        else:
            delays_samples = np.zeros(n_channels, dtype=float)
    delays_samples = np.asarray(delays_samples, dtype=float)
    if delays_samples.shape != (n_channels,):
        raise ValueError("delays_samples must have shape (n_channels,)")

    if dc_offsets is None:
        if n_channels == DEFAULT_N_CHANNELS:
            dc_offsets = DEFAULT_DC_OFFSETS.copy()
        else:
            dc_offsets = np.zeros(n_channels, dtype=float)
    dc_offsets = np.asarray(dc_offsets, dtype=float)

    n_capture = int(round(capture_duration_s * fs))
    event_index = int(round(event_time_s * fs))
    if not 0 <= event_index < n_capture:
        raise ValueError("event_time_s must fall inside the capture duration")

    chirp_signal = generate_chirp(
        fs=fs,
        duration_s=chirp_duration_s,
        f_start_hz=f_start_hz,
        f_end_hz=f_end_hz,
        amplitude=amplitude,
    )

    reference = np.zeros(n_capture, dtype=float)
    stop = min(n_capture, event_index + chirp_signal.shape[0])
    n_copy = stop - event_index
    reference[event_index:stop] = chirp_signal[:n_copy]

    channels = apply_channel_delays(reference, delays_samples, n_channels=n_channels)
    channels = add_gaussian_noise(channels, noise_std=noise_std, seed=seed)
    channels = add_dc_offsets(channels, dc_offsets)

    info: dict[str, Any] = {
        "fs": float(fs),
        "n_channels": int(n_channels),
        "delays_samples": delays_samples,
        "delays_seconds": delays_samples / float(fs),
        "dc_offsets": dc_offsets,
        "noise_std": float(noise_std),
        "event_index": int(event_index),
        "capture_duration_s": float(capture_duration_s),
        "chirp_duration_s": float(chirp_duration_s),
        "f_start_hz": float(f_start_hz),
        "f_end_hz": float(f_end_hz),
        "seed": seed,
    }
    return channels, info
