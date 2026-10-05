"""One pinger trial: waveform, GCC-PHAT TDOA, then the existing solver.

Arrival times are not passed to the solver. They are stored only so the
estimated delays and the estimated position can be scored.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from simulations.geometry_study.pipeline import process_capture, search_max_tau_s
from src.geometry import (
    HydrophoneArray,
    max_pairwise_tdoa_s,
    propagation_times_s,
    source_distances_m,
    true_tdoas_s,
)
from src.localization import (
    angular_error_between_points_deg,
    array_center_m,
    localize_from_tdoa,
)
from src.simulation import (
    add_dc_offsets,
    add_gaussian_noise,
    generate_pinger_pulse,
    noise_std_from_snr_db,
    synthesize_pinger_capture,
)
from src.tdoa import GCCPHATResult


def trial_noise_seed(random_seed: int, trial_index: int) -> int:
    """Seed shared by every SNR and carrier for one source index."""
    if trial_index < 0:
        raise ValueError("trial_index must be non-negative")
    return int(random_seed) + int(trial_index)


def execute_trial(
    array: HydrophoneArray,
    source_m: np.ndarray,
    trial_number: int,
    source_id: int,
    snr_db: float,
    noise_free: bool,
    carrier_hz: float,
    fs: float,
    sound_speed_mps: float,
    settings: dict[str, Any],
    noise_seed_value: int,
) -> dict[str, Any]:
    """Simulate one pinger and localize from the estimated TDOAs.

    A solver rejection or an exception becomes ``success=False`` with a
    blank position. The true position and the true TDOAs are still stored.
    """
    source_m = np.asarray(source_m, dtype=float).reshape(3)
    if array.coordinates_m.shape[0] != 4:
        raise ValueError("waveform trials record four hydrophones, H0 through H3")
    try:
        row = _execute_trial(
            array,
            source_m,
            trial_number,
            source_id,
            snr_db,
            noise_free,
            carrier_hz,
            fs,
            sound_speed_mps,
            settings,
            noise_seed_value,
        )
        row.pop("_diagnostics", None)
        return row
    except Exception as exc:
        arrivals = propagation_times_s(source_m, array.coordinates_m, sound_speed_mps)
        true_tdoa = true_tdoas_s(
            source_m,
            array.coordinates_m,
            sound_speed_mps=sound_speed_mps,
        )
        row = _row(
            array=array,
            source_m=source_m,
            trial_number=trial_number,
            source_id=source_id,
            snr_db=snr_db,
            noise_free=noise_free,
            carrier_hz=carrier_hz,
            true_tdoa_s=true_tdoa,
            estimated_tdoa_s=np.full(array.coordinates_m.shape[0], np.nan),
            success=False,
            position_m=None,
            angular_deg=float("nan"),
            failure_reason=f"{type(exc).__name__}: {exc}",
            flags="exception",
            noise_seed=noise_seed_value,
            settings=settings,
            diagnostics=None,
            physical_max_s=max_pairwise_tdoa_s(array.coordinates_m, sound_speed_mps),
            arrival_times_s=arrivals,
        )
        row.pop("_diagnostics", None)
        return row


def _execute_trial(
    array: HydrophoneArray,
    source_m: np.ndarray,
    trial_number: int,
    source_id: int,
    snr_db: float,
    noise_free: bool,
    carrier_hz: float,
    fs: float,
    sound_speed_mps: float,
    settings: dict[str, Any],
    noise_seed_value: int,
) -> dict[str, Any]:
    distances = source_distances_m(source_m, array.coordinates_m)
    arrivals = propagation_times_s(source_m, array.coordinates_m, sound_speed_mps)
    true_tdoa = true_tdoas_s(
        source_m,
        array.coordinates_m,
        sound_speed_mps=sound_speed_mps,
    )
    pulse = generate_pinger_pulse(
        fs=fs,
        frequency_hz=float(carrier_hz),
        duration_s=float(settings["pulse_duration_s"]),
        amplitude=float(settings["pulse_amplitude"]),
        taper=bool(settings["pulse_taper"]),
        taper_alpha=float(settings["pulse_taper_alpha"]),
    )
    channels = synthesize_pinger_capture(
        pulse,
        arrivals,
        fs=fs,
        capture_duration_s=float(settings["capture_duration_s"]),
        distances_m=distances,
        apply_attenuation=bool(settings["apply_attenuation"]),
        attenuation_reference_m=float(settings["attenuation_reference_m"]),
    )
    noise_std = 0.0 if noise_free else float(noise_std_from_snr_db(pulse, float(snr_db)))
    channels = add_gaussian_noise(channels, noise_std=noise_std, seed=int(noise_seed_value))
    channels = add_dc_offsets(channels, np.asarray(settings["dc_offsets"], dtype=float))

    max_tau = search_max_tau_s(
        array,
        sound_speed_mps,
        fs,
        margin_samples=float(settings["search_margin_samples"]),
    )
    _processed, _window, diagnostics, _event_idx, estimated = process_capture(
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
    estimated = np.asarray(estimated, dtype=float)
    physical_max = max_pairwise_tdoa_s(array.coordinates_m, sound_speed_mps)

    position = None
    angular = float("nan")
    success = False
    reason = ""
    if np.all(np.isfinite(estimated)):
        localization = localize_from_tdoa(
            array.coordinates_m,
            estimated,
            sound_speed_mps=sound_speed_mps,
            reference_channel=0,
        )
        success = bool(localization.success)
        reason = localization.failure_reason
        if success:
            position = np.asarray(localization.position_m, dtype=float)
            center = array_center_m(array.coordinates_m)
            angular = angular_error_between_points_deg(center, source_m, position)
    else:
        reason = "non_finite_tdoa"

    flags = _flags(
        estimated,
        true_tdoa,
        diagnostics,
        physical_max,
        success,
        position,
        source_m,
        float(settings["huge_localization_error_m"]),
    )
    return _row(
        array=array,
        source_m=source_m,
        trial_number=trial_number,
        source_id=source_id,
        snr_db=snr_db,
        noise_free=noise_free,
        carrier_hz=carrier_hz,
        true_tdoa_s=true_tdoa,
        estimated_tdoa_s=estimated,
        success=success,
        position_m=position,
        angular_deg=angular,
        failure_reason=reason,
        flags=flags,
        noise_seed=noise_seed_value,
        settings=settings,
        diagnostics=diagnostics,
        physical_max_s=physical_max,
        arrival_times_s=arrivals,
    )


def _flags(
    estimated_s: np.ndarray,
    true_s: np.ndarray,
    diagnostics: list[GCCPHATResult | None] | None,
    physical_max_s: float,
    success: bool,
    position_m: np.ndarray | None,
    source_m: np.ndarray,
    huge_error_m: float,
) -> str:
    found: list[str] = []
    if not np.all(np.isfinite(estimated_s)):
        found.append("non_finite_tdoa")
    else:
        outside = np.abs(estimated_s) > (float(physical_max_s) + 1e-9)
        if np.any(outside):
            found.append("tdoa_outside_physical_limit")
    if diagnostics is not None and _peak_on_boundary(diagnostics, true_s, physical_max_s):
        found.append("correlation_peak_at_boundary")
    if success and position_m is not None:
        error = float(np.linalg.norm(position_m - source_m))
        if not np.isfinite(error):
            found.append("non_finite_position")
        elif error > float(huge_error_m):
            found.append("huge_localization_error")
    return ";".join(found)


def _peak_on_boundary(
    diagnostics: list[GCCPHATResult | None],
    true_s: np.ndarray,
    physical_max_s: float,
) -> bool:
    """True when a correlation peak sits on the search edge away from the physical limit.

    A source near the end-fire direction can legitimately place the true
    delay near ``d_max / c``. That case is not flagged.
    """
    for index, diagnostic in enumerate(diagnostics):
        if diagnostic is None:
            continue
        n_lags = int(diagnostic.correlation.size)
        if n_lags < 3:
            continue
        on_edge = diagnostic.peak_index == 0 or diagnostic.peak_index == n_lags - 1
        true_is_interior = abs(float(true_s[index])) < 0.9 * float(physical_max_s)
        if on_edge and true_is_interior:
            return True
    return False


def _row(
    *,
    array: HydrophoneArray,
    source_m: np.ndarray,
    trial_number: int,
    source_id: int,
    snr_db: float,
    noise_free: bool,
    carrier_hz: float,
    true_tdoa_s: np.ndarray,
    estimated_tdoa_s: np.ndarray,
    success: bool,
    position_m: np.ndarray | None,
    angular_deg: float,
    failure_reason: str,
    flags: str,
    noise_seed: int,
    settings: dict[str, Any],
    diagnostics: list[GCCPHATResult | None] | None,
    physical_max_s: float,
    arrival_times_s: np.ndarray,
) -> dict[str, Any]:
    true_us = np.asarray(true_tdoa_s, dtype=float) * 1e6
    est_us = np.asarray(estimated_tdoa_s, dtype=float) * 1e6
    err_us = est_us - true_us
    pair_err = np.abs(err_us[1:])
    finite_pairs = pair_err[np.isfinite(pair_err)]
    mean_abs = float(np.mean(finite_pairs)) if finite_pairs.size else float("nan")
    if success and position_m is not None:
        error_m = float(np.linalg.norm(position_m - source_m))
        est_xyz = [float(position_m[0]), float(position_m[1]), float(position_m[2])]
    else:
        error_m = float("nan")
        est_xyz = [float("nan"), float("nan"), float("nan")]
        angular_deg = float("nan")
    reason = " ".join(str(failure_reason).split())
    return {
        "snr_db": float("nan") if noise_free else float(snr_db),
        "noise_free": bool(noise_free),
        "trial": int(trial_number),
        "source_id": int(source_id),
        "carrier_frequency_hz": float(carrier_hz),
        "pulse_duration_s": float(settings["pulse_duration_s"]),
        "sample_rate_hz": float(settings["sample_rate_hz"]),
        "apply_attenuation": bool(settings["apply_attenuation"]),
        "source_x_m": float(source_m[0]),
        "source_y_m": float(source_m[1]),
        "source_z_m": float(source_m[2]),
        "est_x_m": est_xyz[0],
        "est_y_m": est_xyz[1],
        "est_z_m": est_xyz[2],
        "true_tdoa_h1_us": float(true_us[1]),
        "true_tdoa_h2_us": float(true_us[2]),
        "true_tdoa_h3_us": float(true_us[3]),
        "est_tdoa_h1_us": float(est_us[1]),
        "est_tdoa_h2_us": float(est_us[2]),
        "est_tdoa_h3_us": float(est_us[3]),
        "tdoa_err_h1_us": float(err_us[1]),
        "tdoa_err_h2_us": float(err_us[2]),
        "tdoa_err_h3_us": float(err_us[3]),
        "mean_abs_tdoa_error_us": mean_abs,
        "localization_error_m": error_m,
        "angular_error_deg": float(angular_deg),
        "hydrophone_configuration": array.key,
        "n_hydrophones": int(array.coordinates_m.shape[0]),
        "success": bool(success),
        "failure_reason": reason,
        "flags": flags,
        "noise_seed": int(noise_seed),
        "physical_max_tdoa_us": float(physical_max_s * 1e6),
        "arrival_h0_us": float(arrival_times_s[0] * 1e6),
        "_diagnostics": diagnostics,
    }


def representative_capture(
    array: HydrophoneArray,
    source_m: np.ndarray,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Noise-free 40 kHz example used by the waveform and GCC-PHAT figures."""
    row = _execute_trial(
        array,
        np.asarray(source_m, dtype=float),
        trial_number=0,
        source_id=-1,
        snr_db=float("nan"),
        noise_free=True,
        carrier_hz=float(settings["carrier_frequency_hz"]),
        fs=float(settings["sample_rate_hz"]),
        sound_speed_mps=float(settings["sound_speed_mps"]),
        settings=settings,
        noise_seed_value=0,
    )
    fs = float(settings["sample_rate_hz"])
    distances = source_distances_m(source_m, array.coordinates_m)
    arrivals = propagation_times_s(source_m, array.coordinates_m, float(settings["sound_speed_mps"]))
    pulse = generate_pinger_pulse(
        fs=fs,
        frequency_hz=float(settings["carrier_frequency_hz"]),
        duration_s=float(settings["pulse_duration_s"]),
        amplitude=float(settings["pulse_amplitude"]),
        taper=bool(settings["pulse_taper"]),
        taper_alpha=float(settings["pulse_taper_alpha"]),
    )
    channels = synthesize_pinger_capture(
        pulse,
        arrivals,
        fs=fs,
        capture_duration_s=float(settings["capture_duration_s"]),
        distances_m=distances,
        apply_attenuation=bool(settings["apply_attenuation"]),
        attenuation_reference_m=float(settings["attenuation_reference_m"]),
    )
    return {
        "channels": channels,
        "fs": fs,
        "diagnostics": row.pop("_diagnostics"),
        "row": row,
        "arrival_times_s": arrivals,
    }
