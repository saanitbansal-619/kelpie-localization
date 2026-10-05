"""SNR definition, reproducibility, and noise-free behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_study.pipeline import noise_std_for_snr, prepare_reference_waveform, run_trial
from simulations.noise_study.analysis import (
    RESULT_FIELDS,
    failed_measurement_row,
    summarize_results,
)
from simulations.noise_study.figures import save_noise_figures
from simulations.noise_study.pipeline import (
    execute_trial,
    noise_std_for_condition,
    trial_noise_seed,
)
from src.geometry import get_geometry
from src.simulation import (
    DEFAULT_CAPTURE_DURATION_S,
    DEFAULT_DC_OFFSETS,
    DEFAULT_DELAYS_SAMPLES,
    DEFAULT_EVENT_TIME_S,
    DEFAULT_FS,
    add_dc_offsets,
    add_gaussian_noise,
    apply_channel_delays,
    estimate_snr_db,
    generate_chirp,
    generate_synthetic_capture,
    noise_power_for_snr_db,
    noise_std_from_snr_db,
    signal_power,
)

CONFIG = json.loads(
    (PROJECT_ROOT / "simulations" / "noise_study" / "configs" / "experiment.json").read_text(
        encoding="utf-8"
    )
)
SNR_LEVELS = (30.0, 25.0, 20.0, 15.0, 10.0, 5.0, 0.0)


def _reference() -> tuple[float, np.ndarray]:
    fs = float(CONFIG["sample_rate_hz"])
    _, reference = prepare_reference_waveform(
        fs,
        float(CONFIG["capture_duration_s"]),
        float(CONFIG["event_time_s"]),
    )
    return fs, reference


def _execute(
    *,
    geometry: str,
    seed: int,
    snr_db: float,
    noise_free: bool,
    source: np.ndarray | None = None,
) -> dict:
    fs, reference = _reference()
    if source is None:
        source = np.array([3.0, 1.5, 1.0])
    return execute_trial(
        get_geometry(geometry),
        source,
        0,
        1,
        snr_db,
        noise_free,
        reference,
        fs,
        float(CONFIG["sound_speed_mps"]),
        noise_std_for_condition(snr_db, fs, noise_free),
        CONFIG,
        seed,
    )


def test_snr_definition_sets_noise_power_from_signal_power() -> None:
    chirp = generate_chirp()
    power = signal_power(chirp)
    for snr in SNR_LEVELS:
        noise_power = noise_power_for_snr_db(power, snr)
        assert 10.0 * np.log10(power / noise_power) == pytest.approx(snr)
        std = noise_std_from_snr_db(chirp, snr)
        assert std**2 == pytest.approx(noise_power)
        legacy = float(np.sqrt(power) / (10.0 ** (snr / 20.0)))
        assert noise_std_for_snr(snr, DEFAULT_FS) == pytest.approx(legacy)
        assert std == pytest.approx(legacy, rel=1e-12)


def test_realized_noise_is_near_the_requested_snr() -> None:
    chirp = generate_chirp()
    clean = np.vstack([chirp, chirp, chirp, chirp])
    std = noise_std_from_snr_db(chirp, 20.0)
    noisy = add_gaussian_noise(clean, std, seed=1)
    for channel in range(4):
        noise = noisy[channel] - clean[channel]
        assert estimate_snr_db(clean[channel], noise) == pytest.approx(20.0, abs=1.5)
        assert not np.allclose(noise, noisy[(channel + 1) % 4] - clean[(channel + 1) % 4])

    tone = np.sin(2.0 * np.pi * np.arange(100_000) / 40.0)
    tone_std = noise_std_from_snr_db(tone, 12.0)
    tone_noise = np.random.default_rng(0).normal(0.0, tone_std, size=tone.shape)
    assert estimate_snr_db(tone, tone_noise) == pytest.approx(12.0, abs=0.15)


def test_lower_snr_increases_noise_power() -> None:
    chirp = generate_chirp()
    powers = [noise_std_from_snr_db(chirp, snr) ** 2 for snr in SNR_LEVELS]
    assert all(earlier < later for earlier, later in zip(powers, powers[1:]))

    silence = np.zeros((4, 20_000))
    measured = []
    for snr in (30.0, 10.0, 0.0):
        draw = add_gaussian_noise(silence, noise_std_from_snr_db(chirp, snr), seed=99)
        measured.append(float(np.mean(draw**2)))
    assert measured[0] < measured[1] < measured[2]

    fs = float(CONFIG["sample_rate_hz"])
    assert noise_std_for_condition(30.0, fs, noise_free=False) < noise_std_for_condition(
        0.0, fs, noise_free=False
    )
    assert noise_std_for_condition(0.0, fs, noise_free=True) == 0.0


def test_same_seed_reproduces_and_scales_independent_channel_noise() -> None:
    shape = (4, 1500)
    first = add_gaussian_noise(np.zeros(shape), 0.25, seed=3)
    repeat = add_gaussian_noise(np.zeros(shape), 0.25, seed=3)
    doubled = add_gaussian_noise(np.zeros(shape), 0.50, seed=3)
    other = add_gaussian_noise(np.zeros(shape), 0.25, seed=4)
    assert np.array_equal(first, repeat)
    assert np.array_equal(doubled, first * 2.0)
    assert not np.array_equal(first, other)
    assert not np.array_equal(first[0], first[1])
    assert abs(float(np.corrcoef(first[0], first[1])[0, 1])) < 0.2
    assert trial_noise_seed(20261004, 7) == trial_noise_seed(20261004, 7)
    assert trial_noise_seed(20261004, 7) != trial_noise_seed(20261004, 8)


def test_noise_free_capture_matches_existing_delay_and_dc_path() -> None:
    channels, _info = generate_synthetic_capture(noise_std=0.0, seed=1)
    again, _info2 = generate_synthetic_capture(noise_std=0.0, seed=99)
    assert np.array_equal(channels, again)

    chirp = generate_chirp()
    n_capture = int(round(DEFAULT_CAPTURE_DURATION_S * DEFAULT_FS))
    event_index = int(round(DEFAULT_EVENT_TIME_S * DEFAULT_FS))
    reference = np.zeros(n_capture, dtype=float)
    stop = min(n_capture, event_index + chirp.shape[0])
    reference[event_index:stop] = chirp[: stop - event_index]
    expected = apply_channel_delays(reference, DEFAULT_DELAYS_SAMPLES, n_channels=4)
    expected = add_dc_offsets(expected, DEFAULT_DC_OFFSETS)
    assert np.array_equal(channels, expected)


def test_noise_free_localization_matches_direct_zero_noise_trial() -> None:
    fs, reference = _reference()
    source = np.array([2.0, 1.0, 1.5])
    direct = run_trial(
        get_geometry("tetrahedral"),
        source,
        source_id=3,
        snr_db=40.0,
        reference=reference,
        fs=fs,
        sound_speed_mps=float(CONFIG["sound_speed_mps"]),
        noise_std=0.0,
        settings=CONFIG,
    )
    wrapped = _execute(geometry="tetrahedral", seed=123, snr_db=float("nan"), noise_free=True, source=source)
    other_seed = _execute(
        geometry="tetrahedral",
        seed=456,
        snr_db=float("nan"),
        noise_free=True,
        source=source,
    )
    assert direct["solver_success"] is True
    assert wrapped["success"] is True
    assert wrapped["noise_free"] is True
    assert math_isnan(wrapped["snr_db"])
    assert wrapped["hydrophone_configuration"] == "tetrahedral"
    assert wrapped["n_hydrophones"] == 4
    for key in ("est_x_m", "est_y_m", "est_z_m"):
        assert wrapped[key] == direct[key]
        assert other_seed[key] == direct[key]
    assert wrapped["localization_error_m"] == direct["position_error_m"]
    assert wrapped["angular_error_deg"] == direct["angular_error_deg"]


def test_same_seed_reproduces_localization() -> None:
    source = np.array([2.0, 1.0, 1.5])
    first = _execute(geometry="tetrahedral", seed=50, snr_db=20.0, noise_free=False, source=source)
    second = _execute(geometry="tetrahedral", seed=50, snr_db=20.0, noise_free=False, source=source)
    assert first["success"] is True
    assert first["est_x_m"] == second["est_x_m"]
    assert first["est_y_m"] == second["est_y_m"]
    assert first["est_z_m"] == second["est_z_m"]
    assert first["localization_error_m"] == second["localization_error_m"]
    assert first["angular_error_deg"] == second["angular_error_deg"]
    assert first["noise_seed"] == 50


def test_degenerate_array_is_recorded_as_a_failure() -> None:
    row = _execute(geometry="linear", seed=1, snr_db=float("nan"), noise_free=True)
    assert row["success"] is False
    assert row["failure_reason"] == "geometric_degeneracy_collinear"
    assert not np.isfinite(row["localization_error_m"])
    assert not np.isfinite(row["angular_error_deg"])
    assert not np.isfinite(row["est_x_m"])


def test_exception_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("solver blew up")

    monkeypatch.setattr("simulations.noise_study.pipeline.run_trial", boom)
    row = _execute(geometry="tetrahedral", seed=8, snr_db=15.0, noise_free=False)
    assert row["success"] is False
    assert row["failure_reason"] == "RuntimeError: solver blew up"
    assert row["source_x_m"] == 3.0
    assert not np.isfinite(row["localization_error_m"])
    assert set(row) == set(RESULT_FIELDS)


def test_summary_ignores_failed_trials_in_the_error_statistics() -> None:
    rows = [
        _row(30.0, False, 1, True, 2.0, 1.0),
        _row(30.0, False, 2, True, 4.0, 3.0),
        _row(30.0, False, 3, False, float("nan"), float("nan")),
        _row(float("nan"), True, 1, False, float("nan"), float("nan")),
    ]
    summary = summarize_results(rows)
    noisy = summary[0]
    assert noisy["n_trials"] == 3
    assert noisy["n_successful"] == 2
    assert noisy["localization_success_rate"] == pytest.approx(2.0 / 3.0)
    assert noisy["mean_localization_error_m"] == pytest.approx(3.0)
    assert noisy["median_localization_error_m"] == pytest.approx(3.0)
    assert noisy["std_localization_error_m"] == pytest.approx(np.sqrt(2.0))
    assert noisy["rmse_localization_error_m"] == pytest.approx(np.sqrt(10.0))
    assert noisy["min_localization_error_m"] == pytest.approx(2.0)
    assert noisy["max_localization_error_m"] == pytest.approx(4.0)
    assert noisy["p95_localization_error_m"] == pytest.approx(float(np.percentile([2.0, 4.0], 95)))
    assert summary[1]["noise_free"] is True
    assert summary[1]["localization_success_rate"] == 0.0
    assert np.isnan(summary[1]["mean_localization_error_m"])

    string_row = _row(10.0, False, 1, True, 1.5, 0.4)
    string_row["success"] = "true"
    string_row["noise_free"] = "false"
    parsed = summarize_results([string_row])
    assert parsed[0]["mean_localization_error_m"] == pytest.approx(1.5)
    assert parsed[0]["n_successful"] == 1
    assert np.isnan(parsed[0]["std_localization_error_m"])


def test_figures_write_without_raising(tmp_path: Path) -> None:
    rows = [
        _row(float("nan"), True, 1, True, 0.8, 0.2),
        _row(float("nan"), True, 2, True, 1.1, 0.3),
        _row(30.0, False, 1, True, 1.0, 0.4),
        _row(30.0, False, 2, True, 1.4, 0.6),
        _row(30.0, False, 3, False, float("nan"), float("nan")),
        _row(0.0, False, 1, True, 2.0, 1.5),
        _row(0.0, False, 2, True, 8.0, 4.0),
    ]
    summary = summarize_results(rows)
    paths = save_noise_figures(rows, summary, tmp_path, [30.0, 0.0])
    assert [path.name for path in paths] == [
        "localization_error_vs_snr.png",
        "localization_error_distribution_vs_snr.png",
        "success_rate_vs_snr.png",
        "angular_error_vs_snr.png",
    ]
    for path in paths:
        assert path.is_file()
        assert path.stat().st_size > 1000


def test_failed_measurement_row_keeps_the_true_source() -> None:
    row = failed_measurement_row(
        trial_number=4,
        noise_free=False,
        snr_db=5.0,
        source_m=np.array([1.0, 2.0, 3.0]),
        configuration="tetrahedral",
        n_hydrophones=4,
        noise_seed=9,
        failure_reason="RuntimeError: broken\nsolver",
    )
    assert row["trial"] == 4
    assert row["source_z_m"] == 3.0
    assert row["success"] is False
    assert row["failure_reason"] == "RuntimeError: broken solver"
    assert not np.isfinite(row["est_y_m"])


def _row(
    snr_db: float,
    noise_free: bool,
    trial: int,
    success: bool,
    position_error: float,
    angular_error: float,
) -> dict:
    return {
        "snr_db": snr_db,
        "noise_free": noise_free,
        "trial": trial,
        "source_x_m": 1.0,
        "source_y_m": 2.0,
        "source_z_m": 3.0,
        "est_x_m": 1.1 if success else float("nan"),
        "est_y_m": 2.1 if success else float("nan"),
        "est_z_m": 3.1 if success else float("nan"),
        "est_azimuth_deg": 10.0 if success else float("nan"),
        "est_elevation_deg": 5.0 if success else float("nan"),
        "localization_error_m": position_error,
        "angular_error_deg": angular_error,
        "hydrophone_configuration": "tetrahedral",
        "n_hydrophones": 4,
        "success": success,
        "failure_reason": "" if success else "no_bounded_solution",
        "noise_seed": 20261004 + trial,
    }


def math_isnan(value: float) -> bool:
    return bool(np.isnan(value))
