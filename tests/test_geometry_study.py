"""Integration checks for one geometry-study trial."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulations.geometry_study.pipeline import (
    noise_seed,
    noise_std_for_snr,
    prepare_reference_waveform,
    run_trial,
)
from src.geometry import get_geometry, max_pairwise_tdoa_s

CONFIG = json.loads(
    (PROJECT_ROOT / "simulations" / "geometry_study" / "configs" / "experiment.json").read_text(
        encoding="utf-8"
    )
)


def _settings_trial(array_key: str, snr_db: float) -> dict:
    fs = float(CONFIG["sample_rate_hz"])
    _, reference = prepare_reference_waveform(
        fs,
        float(CONFIG["capture_duration_s"]),
        float(CONFIG["event_time_s"]),
    )
    source = np.array(CONFIG["representative_source_m"], dtype=float)
    row = run_trial(
        get_geometry(array_key),
        source,
        source_id=7,
        snr_db=snr_db,
        reference=reference,
        fs=fs,
        sound_speed_mps=float(CONFIG["sound_speed_mps"]),
        noise_std=noise_std_for_snr(snr_db, fs),
        settings=CONFIG,
    )
    return row


def test_noise_seed_depends_on_source_and_snr_only() -> None:
    assert noise_seed(3, 20) == noise_seed(3, 20.0)
    assert noise_seed(3, 20) != noise_seed(4, 20)
    assert noise_seed(3, 20) != noise_seed(3, 10)


def test_shared_source_uses_one_seed_and_degenerate_arrays_fail() -> None:
    linear = _settings_trial("linear", 40.0)
    square = _settings_trial("square_planar", 40.0)
    assert linear["noise_seed"] == square["noise_seed"]
    assert linear["source_x_m"] == square["source_x_m"]
    assert linear["solver_success"] is False
    assert square["solver_success"] is False
    assert linear["failure_reason"] == "geometric_degeneracy_collinear"
    assert square["failure_reason"] == "geometric_degeneracy_coplanar"
    assert not np.isfinite(linear["position_error_m"])
    assert not np.isfinite(linear["angular_error_deg"])
    assert not np.isfinite(square["est_x_m"])
    physical_max_us = max_pairwise_tdoa_s(get_geometry("linear").coordinates_m) * 1e6
    for key in ("true_tdoa_h1_us", "true_tdoa_h2_us", "true_tdoa_h3_us"):
        assert abs(linear[key]) <= physical_max_us + 1e-6
    assert linear["true_tdoa_h0_us"] == 0.0
    assert np.isfinite(linear["est_tdoa_h1_us"])


def test_volumetric_trial_returns_a_finite_direction() -> None:
    row = _settings_trial("tetrahedral", 40.0)
    assert row["solver_success"] is True
    assert row["failure_reason"] == ""
    assert np.isfinite(row["angular_error_deg"])
    assert np.isfinite(row["position_error_m"])
    assert row["position_error_m"] > 0.0
    assert 0.0 <= row["angular_error_deg"] <= 180.0
