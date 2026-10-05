"""One localization trial at a chosen SNR, using the geometry-study pipeline.

This module does not reimplement chirp generation, noise, preprocessing,
GCC-PHAT, or the TDOA solver. It only chooses the noise scale and records
a failure when that existing trial raises.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from simulations.geometry_study.pipeline import noise_std_for_snr, run_trial
from simulations.noise_study.analysis import failed_measurement_row, measurement_row
from src.geometry import HydrophoneArray


def trial_noise_seed(random_seed: int, trial_index: int) -> int:
    """Seed shared by every SNR level for one trial.

    The seed depends on the trial and not on the SNR, so each SNR scales one
    common Gaussian draw. ``trial_index`` is zero-based.
    """
    if trial_index < 0:
        raise ValueError("trial_index must be non-negative")
    return int(random_seed) + int(trial_index)


def execute_trial(
    array: HydrophoneArray,
    source_m: np.ndarray,
    source_id: int,
    trial_number: int,
    snr_db: float,
    noise_free: bool,
    reference: np.ndarray,
    fs: float,
    sound_speed_mps: float,
    noise_std: float,
    settings: dict[str, Any],
    noise_seed_value: int,
) -> dict[str, Any]:
    """Run one existing localization trial and always return a result row.

    A solver rejection is already a normal result of ``run_trial``. An
    unexpected exception is stored as ``success=False`` with the exception
    text in ``failure_reason``.
    """
    source_m = np.asarray(source_m, dtype=float).reshape(3)
    configuration = array.key
    n_hydrophones = int(array.coordinates_m.shape[0])
    stored_snr = float("nan") if noise_free else float(snr_db)
    try:
        raw = run_trial(
            array,
            source_m,
            source_id,
            stored_snr if np.isfinite(stored_snr) else 0.0,
            reference,
            fs,
            sound_speed_mps,
            float(noise_std),
            settings,
            noise_seed_value=int(noise_seed_value),
        )
    except Exception as exc:
        return failed_measurement_row(
            trial_number=trial_number,
            noise_free=noise_free,
            snr_db=stored_snr,
            source_m=source_m,
            configuration=configuration,
            n_hydrophones=n_hydrophones,
            noise_seed=int(noise_seed_value),
            failure_reason=f"{type(exc).__name__}: {exc}",
        )
    return measurement_row(
        raw,
        trial_number=trial_number,
        noise_free=noise_free,
        configuration=configuration,
        n_hydrophones=n_hydrophones,
    )


def noise_std_for_condition(snr_db: float, fs: float, noise_free: bool) -> float:
    """Noise standard deviation for one condition. Noise-free is exactly 0."""
    if noise_free:
        return 0.0
    return float(noise_std_for_snr(snr_db, fs))
