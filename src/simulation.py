"""Synthetic 4-channel hydrophone capture generator.

This module exists so the preprocessing pipeline can be developed and tested
before any hardware is available. A short linear chirp is treated as a single
acoustic source. Four channels are formed by delaying that source, then noise
and DC offsets are added to mimic a messy analog front-end.

SNR, when requested, sets the noise power from the signal power:

    SNR_dB = 10 * log10(P_signal / P_noise)

``P_signal`` is the mean square of the source chirp. ``P_noise`` is the
variance of zero-mean Gaussian noise, so the noise standard deviation is
``sqrt(P_noise)``.

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


DEFAULT_PINGER_FREQUENCY_HZ = 40_000.0
DEFAULT_PINGER_DURATION_S = 0.004
DEFAULT_PINGER_TAPER_ALPHA = 0.1


def generate_pinger_pulse(
    fs: float = DEFAULT_FS,
    frequency_hz: float = DEFAULT_PINGER_FREQUENCY_HZ,
    duration_s: float = DEFAULT_PINGER_DURATION_S,
    amplitude: float = 1.0,
    taper: bool = True,
    taper_alpha: float = DEFAULT_PINGER_TAPER_ALPHA,
) -> np.ndarray:
    """Generate one pulsed sinusoid.

    The burst is ``amplitude * sin(2 π f t)`` for ``duration_s`` seconds.
    A short Tukey taper is on by default so the pulse does not start and
    stop with a click. ``taper_alpha`` is the Tukey fraction; 0.1 leaves
    most of a 4 ms burst at full amplitude.

    The configured amplitude is the amplitude of the sinusoid before the
    taper. When spherical spreading is applied later, this amplitude is the
    amplitude at the attenuation reference range (1 m by default).
    """
    if fs <= 0:
        raise ValueError("fs must be positive")
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    if frequency_hz >= 0.5 * fs:
        raise ValueError("frequency_hz must be below the Nyquist frequency")
    if not np.isfinite(amplitude):
        raise ValueError("amplitude must be finite")
    if not 0.0 <= taper_alpha <= 1.0:
        raise ValueError("taper_alpha must be in [0, 1]")

    n_samples = int(round(duration_s * fs))
    if n_samples < 2:
        raise ValueError("pulse is too short for the given sample rate")

    t = np.arange(n_samples, dtype=float) / float(fs)
    pulse = float(amplitude) * np.sin(2.0 * np.pi * float(frequency_hz) * t)
    if taper and taper_alpha > 0.0:
        pulse = pulse * tukey(n_samples, alpha=float(taper_alpha))
    return pulse.astype(float)


def synthesize_pinger_capture(
    pulse: np.ndarray,
    arrival_times_s: np.ndarray,
    fs: float,
    capture_duration_s: float,
    distances_m: np.ndarray | None = None,
    apply_attenuation: bool = False,
    attenuation_reference_m: float = 1.0,
) -> np.ndarray:
    """Place one pulse on each hydrophone at a fractional propagation delay.

    Sample 0 of the capture is emission time. Channel ``i`` is the pulse
    delayed by ``arrival_times_s[i]`` seconds. The delay is
    ``fs * arrival_time`` samples and is not rounded: :func:`delay_signal`
    uses linear interpolation.

    When ``apply_attenuation`` is True, each channel is multiplied by
    ``attenuation_reference_m / distance_i``, so amplitude falls as ``1/d``.
    ``distances_m`` is required in that case and must be positive.
    """
    pulse = np.asarray(pulse, dtype=float)
    arrival_times_s = np.asarray(arrival_times_s, dtype=float)
    if pulse.ndim != 1 or pulse.size < 2:
        raise ValueError("pulse must be a 1-D array with at least 2 samples")
    if arrival_times_s.ndim != 1 or arrival_times_s.size < 1:
        raise ValueError("arrival_times_s must contain one time per hydrophone")
    if fs <= 0 or capture_duration_s <= 0:
        raise ValueError("fs and capture_duration_s must be positive")
    if np.any(arrival_times_s < 0) or not np.all(np.isfinite(arrival_times_s)):
        raise ValueError("arrival times must be finite and non-negative")

    n_capture = int(round(capture_duration_s * fs))
    if pulse.size > n_capture:
        raise ValueError("pulse is longer than the capture")

    reference = np.zeros(n_capture, dtype=float)
    reference[: pulse.size] = pulse
    delay_samples = arrival_times_s * float(fs)
    channels = apply_channel_delays(reference, delay_samples)

    if apply_attenuation:
        if distances_m is None:
            raise ValueError("distances_m is required when attenuation is on")
        distances_m = np.asarray(distances_m, dtype=float)
        if distances_m.shape != arrival_times_s.shape:
            raise ValueError("distances_m must have one entry per hydrophone")
        if np.any(distances_m <= 0) or not np.all(np.isfinite(distances_m)):
            raise ValueError("distances must be finite and positive")
        if attenuation_reference_m <= 0:
            raise ValueError("attenuation_reference_m must be positive")
        scales = float(attenuation_reference_m) / distances_m
        channels = channels * scales[:, np.newaxis]
    return channels


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


def signal_power(samples: np.ndarray) -> float:
    """Mean-square amplitude of ``samples``.

    This is ``P_signal`` in ``SNR_dB = 10 * log10(P_signal / P_noise)``.
    Every sample in the array is included. The value is not a peak amplitude
    and it is not limited to a frequency band.
    """
    samples = np.asarray(samples, dtype=float)
    if samples.size == 0:
        raise ValueError("samples must be non-empty")
    power = float(np.mean(samples**2))
    if not np.isfinite(power) or power <= 0.0:
        raise ValueError("signal power must be finite and positive")
    return power


def noise_power_for_snr_db(signal_power_value: float, snr_db: float) -> float:
    """Return ``P_noise = P_signal / 10^(SNR_dB / 10)``.

    Rearrangement of ``SNR_dB = 10 * log10(P_signal / P_noise)``.
    """
    signal_power_value = float(signal_power_value)
    snr_db = float(snr_db)
    if not np.isfinite(signal_power_value) or signal_power_value <= 0.0:
        raise ValueError("signal_power_value must be finite and positive")
    if not np.isfinite(snr_db):
        raise ValueError("snr_db must be finite")
    return float(signal_power_value / (10.0 ** (snr_db / 10.0)))


def noise_std_from_snr_db(samples: np.ndarray, snr_db: float) -> float:
    """Standard deviation of zero-mean noise at the requested SNR.

    Power is the mean square. For zero-mean noise, power equals variance, so
    the standard deviation is ``sqrt(P_noise)``. That is the same number as
    ``rms(samples) / 10^(SNR_dB / 20)``.
    """
    return float(np.sqrt(noise_power_for_snr_db(signal_power(samples), snr_db)))


def estimate_snr_db(signal: np.ndarray, noise: np.ndarray) -> float:
    """SNR in dB from a signal and the noise that was added to it.

    Both arrays must have the same shape. Each is reduced with
    :func:`signal_power`.
    """
    signal = np.asarray(signal, dtype=float)
    noise = np.asarray(noise, dtype=float)
    if signal.shape != noise.shape:
        raise ValueError("signal and noise must have the same shape")
    return float(10.0 * np.log10(signal_power(signal) / signal_power(noise)))


def add_gaussian_noise(
    signals: np.ndarray,
    noise_std: float,
    rng: np.random.Generator | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Add independent Gaussian noise to every sample of every channel.

    The draw has the same shape as ``signals``, so hydrophone channels do not
    share a noise waveform. ``noise_std`` is the standard deviation of that
    noise, in the same units as the signal. A value of 0 leaves the input
    unchanged (still copied) and does not consume the random generator.

    The same ``seed`` reproduces the same standard-normal pattern. A different
    ``noise_std`` with that seed scales the pattern: ``std_2 / std_1``.
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
