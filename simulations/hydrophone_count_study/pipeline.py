"""One trial of the hydrophone-count study.

The waveform, sample rate, sound speed, preprocessing, GCC-PHAT, and
localizer match the geometry study. The differences are the sensor count
and a matched noise draw: every count uses the leading channels of one
six-channel noise sequence from the same seed.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from simulations.geometry_study.pipeline import (
    noise_seed,
    noise_std_for_snr,
    prepare_reference_waveform,
    process_capture,
)
from src.geometry import (
    max_pairwise_tdoa_s,
    source_distances_m,
    tdoas_to_delay_samples,
    true_tdoas_s,
)
from src.hydrophone_counts import SensorArray, reference_tdoa_count
from src.localization import (
    angular_error_between_points_deg,
    array_center_m,
    direction_angles_deg,
    localize_from_tdoa,
)
from src.simulation import add_dc_offsets, apply_channel_delays

NOISE_DRAW_CHANNELS = 6
REFERENCE_INDEXES = (1, 2, 3, 4, 5)


def matched_channel_noise(
    n_samples: int,
    noise_std: float,
    seed: int,
    n_draw: int = NOISE_DRAW_CHANNELS,
) -> np.ndarray:
    """Draw ``n_draw`` noise channels. Callers keep the first N rows.

    A four-channel trial and a six-channel trial that share ``seed`` therefore
    share the noise on H0–H3. The extra rows are used only by the larger arrays.
    """
    if n_draw < 1:
        raise ValueError("n_draw must be positive")
    rng = np.random.default_rng(int(seed))
    if noise_std < 0:
        raise ValueError("noise_std must be non-negative")
    if noise_std == 0:
        return np.zeros((n_draw, n_samples), dtype=float)
    return rng.normal(loc=0.0, scale=float(noise_std), size=(n_draw, n_samples))


def synthesize_count_capture(
    reference: np.ndarray,
    delays_samples: np.ndarray,
    noise_std: float,
    seed: int,
    dc_offsets: np.ndarray,
    n_draw: int = NOISE_DRAW_CHANNELS,
) -> np.ndarray:
    """Delay the shared chirp, add the matched noise prefix, then add DC."""
    delays_samples = np.asarray(delays_samples, dtype=float)
    n_channels = int(delays_samples.shape[0])
    dc_offsets = np.asarray(dc_offsets, dtype=float)
    if dc_offsets.shape[0] < n_channels:
        raise ValueError("dc_offsets must cover every channel")
    if n_draw < n_channels:
        raise ValueError("noise draw must cover every channel")
    channels = apply_channel_delays(reference, delays_samples)
    noise = matched_channel_noise(reference.shape[0], noise_std, seed, n_draw=n_draw)
    channels = channels + noise[:n_channels]
    return add_dc_offsets(channels, dc_offsets[:n_channels])


def _nan() -> float:
    return float("nan")


def run_count_trial(
    array: SensorArray,
    source_m: np.ndarray,
    source_id: int,
    snr_db: float,
    reference: np.ndarray,
    fs: float,
    sound_speed_mps: float,
    noise_std: float,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Simulate one source, one sensor count, and one SNR."""
    source_m = np.asarray(source_m, dtype=float).reshape(3)
    coords = array.coordinates_m
    n_channels = array.sensor_count
    distances = source_distances_m(source_m, coords)
    true_tdoa_s = true_tdoas_s(
        source_m,
        coords,
        sound_speed_mps=sound_speed_mps,
        reference_channel=0,
    )
    delays = tdoas_to_delay_samples(true_tdoa_s, fs=fs)
    seed = noise_seed(source_id, snr_db)
    channels = synthesize_count_capture(
        reference,
        delays,
        noise_std=noise_std,
        seed=seed,
        dc_offsets=np.asarray(settings["dc_offsets"], dtype=float),
        n_draw=int(settings.get("noise_draw_channels", NOISE_DRAW_CHANNELS)),
    )
    max_tau = max_pairwise_tdoa_s(coords, sound_speed_mps) + float(settings["search_margin_samples"]) / float(fs)
    failure_reason = ""
    try:
        _processed, _window, _diagnostics, _event_idx, estimated_s = process_capture(
            channels,
            fs=fs,
            lowcut_hz=float(settings["bandpass_low_hz"]),
            highcut_hz=float(settings["bandpass_high_hz"]),
            order=int(settings["bandpass_order"]),
            pre_samples=int(settings["pre_samples"]),
            post_samples=int(settings["post_samples"]),
            max_tau_s=max_tau,
            interpolation=int(settings["gcc_interpolation"]),
        )
        estimated_s = np.asarray(estimated_s, dtype=float)
    except (FloatingPointError, ValueError) as exc:
        estimated_s = np.full(n_channels, np.nan)
        estimated_s[0] = 0.0
        failure_reason = f"tdoa_failed:{type(exc).__name__}"

    if estimated_s.shape != (n_channels,):
        raise RuntimeError(f"expected {n_channels} TDOAs, got {estimated_s.shape}")
    if estimated_s.shape[0] - 1 != reference_tdoa_count(n_channels):
        raise RuntimeError("reference TDOA count is not N - 1")

    true_us = true_tdoa_s * 1e6
    est_us = estimated_s * 1e6
    err_us = est_us - true_us
    pair_abs = np.abs(err_us[1:])
    finite_abs = pair_abs[np.isfinite(pair_abs)]

    center = array_center_m(coords)
    true_az, true_el = direction_angles_deg(center, source_m)
    baseline_m = array.max_pairwise_distance_m()
    physical_tdoa_us = array.max_physical_tdoa_s(sound_speed_mps) * 1e6

    row: dict[str, Any] = {
        "sensor_count": n_channels,
        "configuration": array.key,
        "configuration_name": array.name,
        "source_id": int(source_id),
        "source_x_m": float(source_m[0]),
        "source_y_m": float(source_m[1]),
        "source_z_m": float(source_m[2]),
        "source_range_m": float(np.linalg.norm(source_m - center)),
        "snr_db": float(snr_db),
        "noise_seed": int(seed),
        "max_pairwise_baseline_m": float(baseline_m),
        "max_physical_tdoa_us": float(physical_tdoa_us),
        "true_azimuth_deg": float(true_az),
        "true_elevation_deg": float(true_el),
        "true_tdoa_h0_us": 0.0,
        "est_tdoa_h0_us": 0.0 if np.isfinite(est_us[0]) else _nan(),
        "trial_mean_abs_tdoa_us": float(np.mean(finite_abs)) if finite_abs.size else _nan(),
        "trial_median_abs_tdoa_us": float(np.median(finite_abs)) if finite_abs.size else _nan(),
    }
    for index in REFERENCE_INDEXES:
        if index < n_channels:
            row[f"true_tdoa_h{index}_us"] = float(true_us[index])
            row[f"est_tdoa_h{index}_us"] = float(est_us[index])
            row[f"tdoa_err_h{index}_us"] = float(err_us[index])
        else:
            row[f"true_tdoa_h{index}_us"] = _nan()
            row[f"est_tdoa_h{index}_us"] = _nan()
            row[f"tdoa_err_h{index}_us"] = _nan()

    if np.all(np.isfinite(estimated_s)):
        localization = localize_from_tdoa(
            coords,
            estimated_s,
            sound_speed_mps=sound_speed_mps,
            reference_channel=0,
        )
    else:
        localization = None

    success = localization is not None and localization.success
    if success:
        position = localization.position_m
        est_az, est_el = direction_angles_deg(center, position)
        angular = angular_error_between_points_deg(center, source_m, position)
        position_error = float(np.linalg.norm(position - source_m))
        residual_us = float(localization.residual_rms_s * 1e6)
        reason = ""
        geometry_class = localization.geometry_class
        est_xyz = [float(position[0]), float(position[1]), float(position[2])]
    else:
        est_az = _nan()
        est_el = _nan()
        angular = _nan()
        position_error = _nan()
        est_xyz = [_nan(), _nan(), _nan()]
        if localization is None:
            residual_us = _nan()
            reason = failure_reason or "tdoa_failed"
            geometry_class = "unknown"
        else:
            residual_us = (
                float(localization.residual_rms_s * 1e6)
                if np.isfinite(localization.residual_rms_s)
                else _nan()
            )
            reason = localization.failure_reason
            geometry_class = localization.geometry_class

    row.update(
        {
            "est_x_m": est_xyz[0],
            "est_y_m": est_xyz[1],
            "est_z_m": est_xyz[2],
            "est_azimuth_deg": est_az,
            "est_elevation_deg": est_el,
            "angular_error_deg": angular,
            "position_error_m": position_error,
            "solver_success": bool(success),
            "solver_residual_us": residual_us,
            "failure_reason": reason,
            "solver_geometry_class": geometry_class,
        }
    )
    # distances are kept so a later check can confirm the path lengths.
    row["distance_h0_m"] = float(distances[0])
    return row


def load_source_positions(path) -> list[dict[str, float]]:
    """Read the geometry-study source table without modifying it."""
    import csv
    from pathlib import Path

    rows = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                {
                    "source_id": int(record["source_id"]),
                    "x_m": float(record["x_m"]),
                    "y_m": float(record["y_m"]),
                    "z_m": float(record["z_m"]),
                    "range_m": float(record["range_m"]),
                }
            )
    return rows


__all__ = [
    "NOISE_DRAW_CHANNELS",
    "load_source_positions",
    "matched_channel_noise",
    "noise_seed",
    "noise_std_for_snr",
    "prepare_reference_waveform",
    "run_count_trial",
    "synthesize_count_capture",
]
