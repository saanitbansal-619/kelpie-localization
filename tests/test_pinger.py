"""Pulsed-pinger waveform, fractional delay, and noise-free TDOA recovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.waveform_study.pipeline import execute_trial, trial_noise_seed
from src.detection import signal_envelope
from src.geometry import get_geometry, propagation_times_s, source_distances_m, true_tdoas_s
from src.simulation import (
    DEFAULT_FS,
    delay_signal,
    generate_pinger_pulse,
    noise_std_from_snr_db,
    signal_power,
    synthesize_pinger_capture,
)
from src.tdoa import gcc_phat

CONFIG = json.loads(
    (PROJECT_ROOT / "simulations" / "waveform_study" / "configs" / "experiment.json").read_text(
        encoding="utf-8"
    )
)
FS = float(CONFIG["sample_rate_hz"])


def _dominant_hz(samples: np.ndarray, fs: float) -> float:
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / fs)
    return float(freqs[int(np.argmax(spectrum))])


def test_carrier_frequencies_and_pulse_duration() -> None:
    for frequency in (25_000.0, 30_000.0, 35_000.0, 40_000.0):
        pulse = generate_pinger_pulse(
            fs=FS,
            frequency_hz=frequency,
            duration_s=0.004,
            taper=False,
        )
        assert pulse.size / FS == pytest.approx(0.004, abs=1.0 / FS)
        assert _dominant_hz(pulse, FS) == pytest.approx(frequency, abs=1.0)
        tapered = generate_pinger_pulse(fs=FS, frequency_hz=frequency, duration_s=0.004, taper=True)
        assert _dominant_hz(tapered, FS) == pytest.approx(frequency, abs=FS / tapered.size)


def test_fractional_delay_is_not_integer_rounding() -> None:
    frequency = 10_000.0
    n = 500
    t = np.arange(n, dtype=float) / FS
    tone = np.sin(2.0 * np.pi * frequency * t)
    delay = 0.5
    shifted = delay_signal(tone, delay)
    expected = np.sin(2.0 * np.pi * frequency * (t - delay / FS))
    middle = slice(30, -30)
    half_error = float(np.max(np.abs(shifted[middle] - expected[middle])))
    rounded = delay_signal(tone, 1.0)
    rounding_error = float(np.max(np.abs(shifted[middle] - rounded[middle])))
    assert half_error < 0.02
    assert half_error < rounding_error


def test_propagation_delay_increases_with_distance_and_matches_geometry() -> None:
    hydrophones = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.5, 0.0, 0.0],
        ],
        dtype=float,
    )
    source = np.array([-1.0, 0.2, 0.0])
    distances = source_distances_m(source, hydrophones)
    arrivals = propagation_times_s(source, hydrophones, sound_speed_mps=1480.0)
    assert np.all(np.diff(distances) > 0)
    assert np.all(np.diff(arrivals) > 0)
    assert arrivals == pytest.approx(distances / 1480.0)

    array = get_geometry("tetrahedral")
    origin = np.array([2.0, 1.0, 1.5])
    path = source_distances_m(origin, array.coordinates_m)
    tdoa = true_tdoas_s(origin, array.coordinates_m, sound_speed_mps=1480.0)
    assert tdoa[0] == 0.0
    assert tdoa[1:] == pytest.approx((path[1:] - path[0]) / 1480.0)

    pulse = generate_pinger_pulse(fs=FS, frequency_hz=40_000.0, duration_s=0.004)
    channels = synthesize_pinger_capture(pulse, arrivals, fs=FS, capture_duration_s=0.04)
    peaks = [int(np.argmax(signal_envelope(channel))) for channel in channels]
    assert peaks[0] < peaks[1] < peaks[2]


def test_attenuation_scales_amplitude_by_inverse_distance() -> None:
    distances = np.array([1.0, 2.0, 4.0])
    arrivals = distances / 1480.0
    pulse = generate_pinger_pulse(fs=FS, frequency_hz=40_000.0, duration_s=0.004, taper=False)
    plain = synthesize_pinger_capture(pulse, arrivals, fs=FS, capture_duration_s=0.02)
    attenuated = synthesize_pinger_capture(
        pulse,
        arrivals,
        fs=FS,
        capture_duration_s=0.02,
        distances_m=distances,
        apply_attenuation=True,
        attenuation_reference_m=1.0,
    )
    assert np.allclose(attenuated[0], plain[0] / distances[0])
    assert np.allclose(attenuated[1], plain[1] / distances[1])
    assert np.allclose(attenuated[2], plain[2] / distances[2])


def test_gcc_phat_recovers_a_known_fractional_pinger_delay() -> None:
    pulse = generate_pinger_pulse(fs=FS, frequency_hz=40_000.0, duration_s=0.004, taper=False)
    reference = np.zeros(6000, dtype=float)
    reference[: pulse.size] = pulse
    delay_samples = 2.5
    shifted = delay_signal(reference, delay_samples)
    estimated = gcc_phat(shifted, reference, FS, max_tau=20.0 / FS, interpolation=16)
    assert estimated.tau == pytest.approx(delay_samples / FS, abs=0.5 / FS)


def test_noise_free_waveform_tdoa_approaches_geometry() -> None:
    source = np.array(CONFIG["representative_source_m"], dtype=float)
    row = execute_trial(
        get_geometry("tetrahedral"),
        source,
        trial_number=1,
        source_id=0,
        snr_db=float("nan"),
        noise_free=True,
        carrier_hz=40_000.0,
        fs=FS,
        sound_speed_mps=float(CONFIG["sound_speed_mps"]),
        settings=CONFIG,
        noise_seed_value=1,
    )
    other = execute_trial(
        get_geometry("tetrahedral"),
        source,
        trial_number=1,
        source_id=0,
        snr_db=float("nan"),
        noise_free=True,
        carrier_hz=40_000.0,
        fs=FS,
        sound_speed_mps=float(CONFIG["sound_speed_mps"]),
        settings=CONFIG,
        noise_seed_value=99,
    )
    assert row["success"] is True
    assert row["failure_reason"] == ""
    for key in ("tdoa_err_h1_us", "tdoa_err_h2_us", "tdoa_err_h3_us"):
        assert abs(float(row[key])) < 1.0
        assert row[key] == other[key]
    assert row["localization_error_m"] < 0.5
    assert row["localization_error_m"] == other["localization_error_m"]
    assert np.isfinite(row["angular_error_deg"])


def test_same_seed_reproduces_a_noisy_waveform_trial() -> None:
    source = np.array([3.0, -1.2, 2.0])
    kwargs = dict(
        trial_number=4,
        source_id=3,
        snr_db=20.0,
        noise_free=False,
        carrier_hz=40_000.0,
        fs=FS,
        sound_speed_mps=float(CONFIG["sound_speed_mps"]),
        settings=CONFIG,
        noise_seed_value=trial_noise_seed(20261004, 3),
    )
    first = execute_trial(get_geometry("tetrahedral"), source, **kwargs)
    second = execute_trial(get_geometry("tetrahedral"), source, **kwargs)
    assert first["success"] is True
    assert first["est_x_m"] == second["est_x_m"]
    assert first["est_y_m"] == second["est_y_m"]
    assert first["est_z_m"] == second["est_z_m"]
    assert first["mean_abs_tdoa_error_us"] == second["mean_abs_tdoa_error_us"]
    pulse = generate_pinger_pulse(fs=FS, frequency_hz=40_000.0, duration_s=0.004)
    assert 10.0 * np.log10(signal_power(pulse) / noise_std_from_snr_db(pulse, 20.0) ** 2) == pytest.approx(20.0)


def test_rejected_solve_is_not_stored_as_zero_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("waveform failed")

    monkeypatch.setattr("simulations.waveform_study.pipeline._execute_trial", boom)
    row = execute_trial(
        get_geometry("tetrahedral"),
        np.array([2.0, 1.0, 1.5]),
        trial_number=2,
        source_id=1,
        snr_db=0.0,
        noise_free=False,
        carrier_hz=40_000.0,
        fs=FS,
        sound_speed_mps=1480.0,
        settings=CONFIG,
        noise_seed_value=5,
    )
    assert row["success"] is False
    assert "RuntimeError: waveform failed" in row["failure_reason"]
    assert not np.isfinite(row["localization_error_m"])
    assert not np.isfinite(row["angular_error_deg"])
    assert row["source_x_m"] == 2.0
