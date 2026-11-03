"""Four-channel acquisition records in, existing TDOA localization out.

Synthetic and Keysight records share ``FourChannelRecord``. This module does
not reimplement filtering, detection, GCC-PHAT, or the least-squares solver.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from acquisition.waveform import CHANNEL_IDS, HYDROPHONE_IDS, FourChannelRecord
from simulations.geometry_study.pipeline import process_capture
from src.detection import signal_envelope
from src.geometry import (
    SOUND_SPEED_MPS,
    max_pairwise_tdoa_s,
    propagation_times_s,
    source_distances_m,
    true_tdoas_s,
)
from src.localization import localize_from_tdoa
from src.simulation import (
    DEFAULT_DC_OFFSETS,
    add_dc_offsets,
    add_gaussian_noise,
    delay_signal,
    generate_pinger_pulse,
    noise_std_from_snr_db,
    synthesize_pinger_capture,
)
from src.tdoa import GCCPHATResult

# Stated hardware coordinates, in metres. H1..H4 are channels 0..3.
# The catalog 3+1 geometry recenters the array; these values are not recentered.
STATED_HYDROPHONE_ROWS = (
    (0.1443376, 0.0, 0.0),
    (-0.0721688, 0.125, 0.0),
    (-0.0721688, -0.125, 0.0),
    (0.0, 0.0, -0.400),
)

VIRTUAL_SAMPLE_RATE_HZ = 256_000.0
CAPTURE_DURATION_S = 0.04
PULSE_DURATION_S = 0.004
PULSE_TAPER_ALPHA = 0.1
# Same cuts as simulations/waveform_study/configs/experiment.json.
# 25 kHz and 40 kHz both sit inside this passband.
BANDPASS_LOW_HZ = 15_000.0
BANDPASS_HIGH_HZ = 45_000.0
BANDPASS_ORDER = 4
CARRIER_MIN_HZ = 25_000.0
CARRIER_MAX_HZ = 40_000.0
WINDOW_PRE_S = 1024.0 / VIRTUAL_SAMPLE_RATE_HZ
WINDOW_POST_S = 1536.0 / VIRTUAL_SAMPLE_RATE_HZ
GCC_INTERPOLATION = 16
SEARCH_MARGIN_SAMPLES = 1.0
# A GCC argmax more than half a carrier cycle from the correlation envelope
# is a competing cycle, not a unique delay.
ENVELOPE_CYCLE_LIMIT = 0.5
# peak / median(|correlation|). A flat search window sits near 1.
# 6 is the reporting floor. A floor of 3, tried on this same synthetic grid,
# still marked a 0 dB solve reliable when its position error was 131 m and
# its weakest channel contrast was 3.09. Clean pulses on that grid stayed
# above 6.9.
CONTRAST_MINIMUM = 6.0
REFERENCE_CHANNEL = 0


def stated_hydrophones_m() -> np.ndarray:
    """Return a copy of the stated H1..H4 coordinates, shape (4, 3)."""
    return np.array(STATED_HYDROPHONE_ROWS, dtype=float)


@dataclass(frozen=True)
class WaveformLocalization:
    """Solver output plus quality flags that do not use a known source."""

    solver_success: bool
    reliable: bool
    position_m: np.ndarray
    residual_rms_s: float
    geometry_class: str
    failure_reason: str
    flags: tuple[str, ...]
    tdoa_s: np.ndarray
    sample_rate_hz: float
    physical_max_tdoa_s: float
    search_max_tau_s: float
    sidelobe_ratio: np.ndarray
    correlation_contrast: np.ndarray
    envelope_cycles: np.ndarray
    event_index: int
    carrier_hz: float
    bandpass_hz: tuple[float, float]


def localize_record(
    record: FourChannelRecord,
    hydrophones_m: np.ndarray,
    carrier_hz: float,
    sound_speed_mps: float = SOUND_SPEED_MPS,
) -> WaveformLocalization:
    """Estimate a source from one synchronized four-channel record.

    ``carrier_hz`` selects the ambiguity check. The bandpass is the fixed
    15–45 kHz waveform-study band, so every carrier from 25 kHz to 40 kHz
    passes. Metadata on the record is ignored.
    """
    hydrophones_m = np.asarray(hydrophones_m, dtype=float)
    if hydrophones_m.shape != (4, 3):
        raise ValueError("hydrophones_m must have shape (4, 3)")
    carrier = float(carrier_hz)
    if not np.isfinite(carrier) or not CARRIER_MIN_HZ <= carrier <= CARRIER_MAX_HZ:
        raise ValueError("carrier_hz must be finite and inside 25–40 kHz")
    if sound_speed_mps <= 0:
        raise ValueError("sound_speed_mps must be positive")

    fs = _sample_rate_hz(record)
    if BANDPASS_HIGH_HZ >= 0.5 * fs:
        raise ValueError(
            f"sample rate {fs} Hz is too low for the {BANDPASS_HIGH_HZ:.0f} Hz high cut"
        )

    pre_samples = int(round(WINDOW_PRE_S * fs))
    post_samples = int(round(WINDOW_POST_S * fs))
    physical_max = max_pairwise_tdoa_s(hydrophones_m, sound_speed_mps)
    search_max = physical_max + SEARCH_MARGIN_SAMPLES / fs

    _processed, _window, diagnostics, event_index, tdoas = process_capture(
        np.asarray(record.samples, dtype=float),
        fs=fs,
        lowcut_hz=BANDPASS_LOW_HZ,
        highcut_hz=BANDPASS_HIGH_HZ,
        order=BANDPASS_ORDER,
        pre_samples=pre_samples,
        post_samples=post_samples,
        max_tau_s=search_max,
        interpolation=GCC_INTERPOLATION,
    )
    tdoas = np.asarray(tdoas, dtype=float)

    sidelobe = np.full(4, np.nan)
    contrast = np.full(4, np.nan)
    cycles = np.full(4, np.nan)
    flags: list[str] = []
    if record.samples.shape[1] < pre_samples + post_samples:
        flags.append("record_shorter_than_window")
    if not np.all(np.isfinite(tdoas)):
        flags.append("non_finite_tdoa")
    elif np.any(np.abs(tdoas) > physical_max + 1e-9):
        flags.append("tdoa_outside_physical_limit")

    for index, diagnostic in enumerate(diagnostics):
        if diagnostic is None:
            continue
        quality = gcc_quality(diagnostic, carrier)
        sidelobe[index] = quality["sidelobe_ratio"]
        contrast[index] = quality["contrast"]
        cycles[index] = quality["envelope_cycles"]
        if quality["on_search_edge"]:
            flags.append("correlation_peak_at_search_edge")
        if quality["envelope_disagreement"]:
            flags.append("narrowband_ambiguity")
        if quality["low_contrast"]:
            flags.append("low_correlation_contrast")

    if np.all(np.isfinite(tdoas)):
        localization = localize_from_tdoa(
            hydrophones_m,
            tdoas,
            sound_speed_mps=sound_speed_mps,
            reference_channel=REFERENCE_CHANNEL,
        )
        solver_success = bool(localization.success)
        position = np.asarray(localization.position_m, dtype=float).copy()
        residual = float(localization.residual_rms_s)
        geometry_class = localization.geometry_class
        failure_reason = localization.failure_reason
    else:
        solver_success = False
        position = np.full(3, np.nan)
        residual = float("nan")
        geometry_class = ""
        failure_reason = "non_finite_tdoa"

    if not solver_success:
        flags.append("solver_rejected")

    unique_flags = tuple(sorted(set(flags)))
    reliable = solver_success and not unique_flags
    return WaveformLocalization(
        solver_success=solver_success,
        reliable=reliable,
        position_m=position,
        residual_rms_s=residual,
        geometry_class=geometry_class,
        failure_reason=failure_reason,
        flags=unique_flags,
        tdoa_s=tdoas,
        sample_rate_hz=fs,
        physical_max_tdoa_s=physical_max,
        search_max_tau_s=search_max,
        sidelobe_ratio=sidelobe,
        correlation_contrast=contrast,
        envelope_cycles=cycles,
        event_index=int(event_index),
        carrier_hz=carrier,
        bandpass_hz=(BANDPASS_LOW_HZ, BANDPASS_HIGH_HZ),
    )


def gcc_quality(diagnostic: GCCPHATResult, carrier_hz: float) -> dict[str, float | bool]:
    """Score one existing GCC-PHAT trace. Does not change the chosen lag."""
    correlation = np.asarray(diagnostic.correlation, dtype=float)
    lags = np.asarray(diagnostic.lags_seconds, dtype=float)
    peak = float(diagnostic.peak_value)
    peak_index = int(diagnostic.peak_index)
    period = 1.0 / float(carrier_hz)

    on_edge = correlation.size >= 3 and (peak_index == 0 or peak_index == correlation.size - 1)
    median_abs = float(np.median(np.abs(correlation))) if correlation.size else 0.0
    if peak > 0.0 and median_abs > 0.0:
        contrast = peak / median_abs
    elif peak > 0.0 and median_abs == 0.0:
        contrast = float("inf")
    else:
        contrast = float("nan")
    low_contrast = (not np.isfinite(contrast)) or contrast < CONTRAST_MINIMUM

    sidelobe_ratio = _sidelobe_ratio(correlation, lags, peak_index, peak, period)
    envelope_cycles = _envelope_cycles(correlation, lags, peak_index, period)
    disagreement = bool(np.isfinite(envelope_cycles) and envelope_cycles > ENVELOPE_CYCLE_LIMIT)
    return {
        "sidelobe_ratio": sidelobe_ratio,
        "contrast": contrast,
        "envelope_cycles": envelope_cycles,
        "on_search_edge": on_edge,
        "envelope_disagreement": disagreement,
        "low_contrast": low_contrast,
    }


def synthetic_record(
    source_m: np.ndarray,
    carrier_hz: float,
    *,
    snr_db: float | None,
    noise_seed: int,
    channel_offset_samples: np.ndarray | None = None,
    fs: float = VIRTUAL_SAMPLE_RATE_HZ,
    capture_duration_s: float = CAPTURE_DURATION_S,
    hydrophones_m: np.ndarray | None = None,
    sound_speed_mps: float = SOUND_SPEED_MPS,
) -> FourChannelRecord:
    """Build a FourChannelRecord with the same constructor a scope capture uses.

    Sample 0 is emission time. ``snr_db=None`` leaves the pulse noise-free.
    A positive ``channel_offset_samples`` entry delays that hydrophone.
    """
    hydrophones = stated_hydrophones_m() if hydrophones_m is None else np.asarray(hydrophones_m, dtype=float)
    source = np.asarray(source_m, dtype=float).reshape(3)
    carrier = float(carrier_hz)
    arrivals = propagation_times_s(source, hydrophones, sound_speed_mps)
    distances = source_distances_m(source, hydrophones)
    pulse = generate_pinger_pulse(
        fs=fs,
        frequency_hz=carrier,
        duration_s=PULSE_DURATION_S,
        amplitude=1.0,
        taper=True,
        taper_alpha=PULSE_TAPER_ALPHA,
    )
    channels = synthesize_pinger_capture(
        pulse,
        arrivals,
        fs=fs,
        capture_duration_s=capture_duration_s,
        distances_m=distances,
        apply_attenuation=False,
    )
    offsets = np.zeros(channels.shape[0], dtype=float)
    if channel_offset_samples is not None:
        offsets = np.asarray(channel_offset_samples, dtype=float).reshape(channels.shape[0])
        for index, extra in enumerate(offsets):
            if extra != 0.0:
                channels[index] = delay_signal(channels[index], float(extra))
    if snr_db is None:
        noise_std = 0.0
    else:
        noise_std = float(noise_std_from_snr_db(pulse, float(snr_db)))
    channels = add_gaussian_noise(channels, noise_std=noise_std, seed=int(noise_seed))
    channels = add_dc_offsets(channels, DEFAULT_DC_OFFSETS.copy())

    n_samples = channels.shape[1]
    time_s = np.arange(n_samples, dtype=np.float64) / float(fs)
    metadata = {
        "source": "synthetic",
        "physical_measurement": False,
        "instrument_verified": False,
        "sample_rate_hz": float(fs),
        "carrier_hz_annotation": carrier,
        "noise_seed": int(noise_seed),
        "snr_db": None if snr_db is None else float(snr_db),
        "channel_offset_samples": [float(item) for item in offsets],
        "annotation": (
            "Synthetic voltages in the FourChannelRecord layout. "
            "localize_record does not read metadata."
        ),
    }
    return FourChannelRecord(
        samples=np.asarray(channels, dtype=np.float64),
        time_s=time_s,
        sample_interval_s=1.0 / float(fs),
        channel_ids=CHANNEL_IDS,
        hydrophone_ids=HYDROPHONE_IDS,
        metadata=metadata,
    )


def expected_tdoas_s(
    source_m: np.ndarray,
    channel_offset_samples: np.ndarray | None = None,
    *,
    fs: float = VIRTUAL_SAMPLE_RATE_HZ,
    hydrophones_m: np.ndarray | None = None,
    sound_speed_mps: float = SOUND_SPEED_MPS,
) -> np.ndarray:
    """Geometry TDOAs plus any extra delay injected into the synthetic record."""
    hydrophones = stated_hydrophones_m() if hydrophones_m is None else np.asarray(hydrophones_m, dtype=float)
    tdoas = true_tdoas_s(
        np.asarray(source_m, dtype=float),
        hydrophones,
        sound_speed_mps=sound_speed_mps,
        reference_channel=REFERENCE_CHANNEL,
    )
    if channel_offset_samples is not None:
        extra = np.asarray(channel_offset_samples, dtype=float) / float(fs)
        tdoas = tdoas + extra - extra[REFERENCE_CHANNEL]
        tdoas[REFERENCE_CHANNEL] = 0.0
    return tdoas


def _sample_rate_hz(record: FourChannelRecord) -> float:
    interval = float(record.sample_interval_s)
    if interval <= 0 or not np.isfinite(interval):
        raise ValueError("sample_interval_s must be a positive finite number")
    if record.time_s.size < 2:
        raise ValueError("record needs at least two samples")
    steps = np.diff(np.asarray(record.time_s, dtype=float))
    if not np.allclose(steps, interval, rtol=1e-6, atol=1e-12):
        raise ValueError("time_s is not uniform at sample_interval_s")
    return 1.0 / interval


def _sidelobe_ratio(
    correlation: np.ndarray,
    lags: np.ndarray,
    peak_index: int,
    peak: float,
    period_s: float,
) -> float:
    if peak <= 0.0 or correlation.size < 3:
        return float("nan")
    chosen = float(lags[peak_index])
    away = np.abs(lags - chosen) >= 0.5 * period_s
    if not np.any(away):
        return 0.0
    return float(np.max(correlation[away]) / peak)


def _envelope_cycles(
    correlation: np.ndarray,
    lags: np.ndarray,
    peak_index: int,
    period_s: float,
) -> float:
    if correlation.size < 4 or period_s <= 0:
        return float("nan")
    centered = correlation - float(np.mean(correlation))
    envelope = signal_envelope(centered)
    envelope_index = int(np.argmax(envelope))
    return abs(float(lags[peak_index]) - float(lags[envelope_index])) / period_s
