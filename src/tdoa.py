"""TDOA estimation with GCC-PHAT.

This module estimates *relative* arrival times between hydrophone channels.
It does not estimate source position or direction.

Sign convention
---------------
Every delay in this project is:

    TDOA_i = arrival_time_i - arrival_time_reference

Therefore:

* positive TDOA  → channel i received the signal *later* than the reference
* negative TDOA  → channel i received the signal *earlier* than the reference
* reference TDOA → exactly zero

``gcc_phat(signal, reference, ...)`` treats ``signal`` as channel i and
``reference`` as the reference channel. The returned ``tau`` follows the
convention above. That is not assumed from FFT ordering alone; unit tests
construct known positive and negative delays and check the sign.

GCC-PHAT
--------
The PHAT-weighted cross-spectrum is

    R_xy(f) = X(f) Y*(f) / |X(f) Y*(f)|

where ``X`` is the FFT of the signal (channel i) and ``Y`` is the FFT of the
reference. The inverse FFT of ``R_xy`` is the PHAT-weighted cross-correlation.
Its peak lag is the delay estimate.

Near-zero spectral magnitudes are floored so the normalization cannot
produce NaN or Inf, and so noise-only FFT bins do not receive the same
unit weight as the in-band chirp. The denominator is

    max(|X Y*|, ε_rel * max|X Y*|, ε_abs)

with a small relative floor (default ``1e-3`` of the peak cross-spectrum
magnitude) plus a tiny absolute epsilon. In-band bins still receive
ordinary PHAT weighting; bins at the numerical noise floor do not.

Physical bounds
---------------
Two hydrophones a distance ``d`` apart cannot observe an arbitrary TDOA.
Approximately:

    |Δt|_max = d / c

with ``c`` the speed of sound. That geometry is **not** hardcoded here.
The caller supplies ``max_tau`` (seconds), typically:

    max_tau = hydrophone_baseline / sound_speed

A later array-geometry module can compute that value. This function only
restricts the correlation-peak search to ``[-max_tau, max_tau]``.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

DEFAULT_INTERPOLATION = 16
DEFAULT_SOUND_SPEED_MPS = 1480.0
_PHAT_EPS = 1e-15
# Relative floor on |X Y*|: PHAT would otherwise give unit weight to
# noise-only frequency bins (for example the stopband after a bandpass).
_PHAT_REL_EPS = 1e-3


class GCCPHATResult(NamedTuple):
    """Delay estimate plus the correlation trace used to obtain it.

    Attributes
    ----------
    tau:
        Estimated delay in seconds, ``arrival(signal) - arrival(reference)``.
    correlation:
        PHAT-weighted (or unweighted) cross-correlation samples over the
        searched lag region, zero-lag at the centre.
    lags_seconds:
        Lag axis for ``correlation``, in seconds. Same sign convention as
        ``tau``: positive lag means ``signal`` is later than ``reference``.
    peak_index:
        Index of the selected peak inside ``correlation``.
    peak_value:
        Correlation value at ``peak_index``.
    """

    tau: float
    correlation: np.ndarray
    lags_seconds: np.ndarray
    peak_index: int
    peak_value: float


def max_tau_from_baseline(
    baseline_m: float,
    sound_speed_mps: float = DEFAULT_SOUND_SPEED_MPS,
) -> float:
    """Return the maximum physically possible |TDOA| in seconds.

    ``max_tau = baseline_m / sound_speed_mps``, i.e. ``d / c``.

    This helper is for callers. :func:`gcc_phat` never assumes a hydrophone
    spacing or a sound speed; pass the result in as ``max_tau``.
    """
    if baseline_m < 0:
        raise ValueError("baseline_m must be non-negative")
    if sound_speed_mps <= 0:
        raise ValueError("sound_speed_mps must be positive")
    return float(baseline_m) / float(sound_speed_mps)


def gcc_phat(
    signal: np.ndarray,
    reference: np.ndarray,
    fs: float,
    max_tau: float | None = None,
    interpolation: int = DEFAULT_INTERPOLATION,
) -> GCCPHATResult:
    """Estimate the delay of ``signal`` relative to ``reference`` with GCC-PHAT.

    Parameters
    ----------
    signal:
        1-D samples from channel i.
    reference:
        1-D samples from the reference channel.
    fs:
        Sample rate in Hz.
    max_tau:
        Optional search limit in seconds. Only lags in ``[-max_tau, max_tau]``
        are considered. The caller should set this from geometry, e.g.
        ``max_tau = hydrophone_baseline / sound_speed``. ``None`` searches
        the full correlation (up to half the FFT length).
    interpolation:
        Spectral oversampling factor for the correlation function. The lag
        grid spacing becomes ``1 / (interpolation * fs)`` instead of one
        original ADC sample. This refines the *numerical* peak location; it
        does not increase ADC bandwidth or create new physical information.

    Returns
    -------
    GCCPHATResult
        ``tau`` is the estimated TDOA in seconds. ``correlation`` and
        ``lags_seconds`` are the searched cross-correlation, intended for
        plots and debugging.

    Notes
    -----
    Implementation (NumPy FFT, no black-box TDOA library):

    1. FFT both signals (zero-padded to linear-correlation length)
    2. Cross-power spectrum ``X(f) Y*(f)``
    3. PHAT normalize: divide by ``|X(f) Y*(f)|``, with a relative
       magnitude floor so noise-only bins are not unit-weighted
    4. Inverse FFT → PHAT-weighted cross-correlation
    5. Locate the peak inside the allowed lag window
    6. Convert that lag to seconds

    If ``x(t) = y(t - τ)`` with ``τ > 0`` (x arrives later than y), the
    cross-spectrum ``X(f) Y*(f)`` has phase ``e^{-j 2 π f τ}`` and the
    inverse FFT peaks at lag ``+τ``.
    """
    return generalized_cross_correlation(
        signal,
        reference,
        fs,
        max_tau=max_tau,
        interpolation=interpolation,
        weighting="phat",
    )


def normalized_cross_correlation(
    signal: np.ndarray,
    reference: np.ndarray,
    fs: float,
    max_tau: float | None = None,
    interpolation: int = DEFAULT_INTERPOLATION,
) -> GCCPHATResult:
    """Ordinary FFT cross-correlation, globally normalized.

    Same lag search and sign convention as :func:`gcc_phat`, but without PHAT
    weighting: the IFFT of ``X(f) Y*(f)`` is divided by
    ``||signal|| * ||reference||``. This is a simple baseline, not a
    competing production estimator.
    """
    return generalized_cross_correlation(
        signal,
        reference,
        fs,
        max_tau=max_tau,
        interpolation=interpolation,
        weighting="none",
    )


def generalized_cross_correlation(
    signal: np.ndarray,
    reference: np.ndarray,
    fs: float,
    max_tau: float | None = None,
    interpolation: int = DEFAULT_INTERPOLATION,
    weighting: str = "phat",
) -> GCCPHATResult:
    """FFT generalized cross-correlation with optional PHAT weighting.

    ``weighting="phat"`` implements GCC-PHAT:

        R_xy(f) = X(f) Y*(f) / |X(f) Y*(f)|

    ``weighting="none"`` implements ordinary GCC (unweighted cross-spectrum)
    and then divides the time-domain correlation by the product of L2 norms.
    """
    signal = np.asarray(signal, dtype=float)
    reference = np.asarray(reference, dtype=float)
    if signal.ndim != 1 or reference.ndim != 1:
        raise ValueError("signal and reference must be 1-D")
    if signal.size < 2 or reference.size < 2:
        raise ValueError("signal and reference must contain at least 2 samples")
    if fs <= 0:
        raise ValueError("fs must be positive")
    if interpolation < 1:
        raise ValueError("interpolation must be >= 1")
    interpolation = int(interpolation)
    if max_tau is not None and max_tau < 0:
        raise ValueError("max_tau must be non-negative")
    if weighting not in ("phat", "none"):
        raise ValueError("weighting must be 'phat' or 'none'")

    # Length that realises linear (acyclic) correlation rather than circular wrap.
    n = int(signal.size + reference.size)

    spectrum_x = np.fft.rfft(signal, n=n)
    spectrum_y = np.fft.rfft(reference, n=n)
    # Cross-power: X(f) Y*(f). Phase of e^{-j 2 π f τ} peaks at lag +τ after IFFT.
    cross = spectrum_x * np.conj(spectrum_y)

    if weighting == "phat":
        # PHAT: flatten in-band magnitude so the peak is driven by phase.
        # A relative floor keeps stopband / noise-only bins from receiving
        # the same unit weight as the chirp. Conceptual form:
        #   R_xy(f) = X(f) Y*(f) / |X(f) Y*(f)|
        magnitude = np.abs(cross)
        peak = float(np.max(magnitude)) if magnitude.size else 0.0
        denom = np.maximum(magnitude, _PHAT_REL_EPS * peak)
        denom = np.maximum(denom, _PHAT_EPS)
        cross_spectrum = cross / denom
    else:
        cross_spectrum = cross

    # Zero-pad the spectrum via a longer IFFT. Lag spacing becomes
    # 1 / (interpolation * fs). This interpolates the correlation function;
    # it does not invent information above the original Nyquist frequency.
    n_interp = n * interpolation
    correlation_full = np.fft.irfft(cross_spectrum, n=n_interp)

    if weighting == "none":
        denom = float(np.linalg.norm(signal) * np.linalg.norm(reference))
        if denom > 0:
            correlation_full = correlation_full / denom

    max_shift = n_interp // 2
    if max_tau is not None:
        max_shift = min(max_shift, int(round(max_tau * fs * interpolation)))

    correlation, lags_seconds = _center_correlation(correlation_full, max_shift, fs, interpolation)
    peak_index = int(np.argmax(correlation))
    peak_value = float(correlation[peak_index])
    tau = float(lags_seconds[peak_index])

    if not np.isfinite(tau) or not np.isfinite(peak_value):
        raise FloatingPointError("GCC produced a non-finite delay or peak value")
    if not np.all(np.isfinite(correlation)):
        raise FloatingPointError("GCC correlation contains NaN or Inf")

    return GCCPHATResult(
        tau=tau,
        correlation=correlation,
        lags_seconds=lags_seconds,
        peak_index=peak_index,
        peak_value=peak_value,
    )


def estimate_tdoas(
    channels: np.ndarray,
    fs: float,
    reference_channel: int = 0,
    max_taus: float | np.ndarray | None = None,
    interpolation: int = DEFAULT_INTERPOLATION,
    weighting: str = "phat",
) -> tuple[np.ndarray, list[GCCPHATResult | None]]:
    """Estimate TDOA of every channel relative to a reference channel.

    Parameters
    ----------
    channels:
        Array of shape ``(num_channels, num_samples)``. This function does
        not crop, shift, or otherwise modify the input waveforms.
    fs:
        Sample rate in Hz.
    reference_channel:
        Index of the reference hydrophone. Its TDOA is exactly 0.
    max_taus:
        Optional peak-search limit in seconds. A scalar applies to every
        pair. An array of shape ``(num_channels,)`` sets a per-channel
        limit (the reference entry is ignored). ``None`` imposes no
        physical bound.
    interpolation:
        Forwarded to :func:`gcc_phat`.
    weighting:
        ``"phat"`` (default) or ``"none"`` for ordinary GCC.

    Returns
    -------
    tdoas:
        Array of shape ``(num_channels,)`` in seconds.
        ``tdoas[i] = arrival_i - arrival_reference``.
        For four channels and reference 0 this is
        ``[0, Δt10, Δt20, Δt30]``.
    diagnostics:
        Per-channel :class:`GCCPHATResult`. The reference entry is ``None``.
    """
    channels = np.asarray(channels, dtype=float)
    if channels.ndim != 2:
        raise ValueError("channels must have shape (num_channels, num_samples)")

    n_channels = channels.shape[0]
    if not 0 <= reference_channel < n_channels:
        raise ValueError("reference_channel out of range")

    max_tau_list = _broadcast_max_taus(max_taus, n_channels)
    reference = channels[reference_channel]

    tdoas = np.zeros(n_channels, dtype=float)
    diagnostics: list[GCCPHATResult | None] = [None] * n_channels

    for i in range(n_channels):
        if i == reference_channel:
            continue
        result = generalized_cross_correlation(
            channels[i],
            reference,
            fs,
            max_tau=max_tau_list[i],
            interpolation=interpolation,
            weighting=weighting,
        )
        tdoas[i] = result.tau
        diagnostics[i] = result

    return tdoas, diagnostics


def _broadcast_max_taus(
    max_taus: float | np.ndarray | None,
    n_channels: int,
) -> list[float | None]:
    if max_taus is None:
        return [None] * n_channels

    values = np.asarray(max_taus, dtype=float)
    if values.ndim == 0:
        return [float(values)] * n_channels
    if values.shape != (n_channels,):
        raise ValueError("max_taus must be a scalar or have shape (num_channels,)")
    return [float(v) for v in values]


def _center_correlation(
    correlation_full: np.ndarray,
    max_shift: int,
    fs: float,
    interpolation: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Restrict a circular IFFT correlation to ``[-max_shift, +max_shift]``.

    ``correlation_full[0]`` is lag 0. Positive lags occupy the start of the
    array; negative lags wrap to the end. After centering, index
    ``max_shift`` is lag 0 and the lag axis (seconds) shares the TDOA sign
    convention.
    """
    if max_shift < 0:
        raise ValueError("max_shift must be non-negative")
    if max_shift == 0:
        return np.array([float(correlation_full[0])]), np.array([0.0])

    centered = np.concatenate(
        (correlation_full[-max_shift:], correlation_full[: max_shift + 1])
    )
    lags_seconds = np.arange(-max_shift, max_shift + 1, dtype=float) / float(
        interpolation * fs
    )
    return centered, lags_seconds
