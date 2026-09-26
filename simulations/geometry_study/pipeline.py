"""One geometry-study trial, using the existing signal-processing modules.

This file does not reimplement chirp generation, preprocessing, detection,
or GCC-PHAT. It only connects those functions to geometry-derived delays.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.detection import detect_event, extract_common_window
from src.geometry import (
    HydrophoneArray,
    max_pairwise_tdoa_s,
    propagation_times_s,
    source_distances_m,
    tdoas_to_delay_samples,
    true_tdoas_s,
)
from src.localization import (
    angular_error_between_points_deg,
    array_center_m,
    direction_angles_deg,
    localize_from_tdoa,
)
from src.preprocessing import preprocess_multichannel
from src.simulation import (
    DEFAULT_DC_OFFSETS,
    add_dc_offsets,
    add_gaussian_noise,
    apply_channel_delays,
    generate_chirp,
)
from src.tdoa import estimate_tdoas


def noise_std_for_snr(snr_db: float, fs: float) -> float:
    """Match the existing TDOA SNR experiment: noise_std = RMS(chirp) / 10^(SNR/20)."""
    chirp = generate_chirp(fs=fs)
    signal_rms = float(np.sqrt(np.mean(chirp**2)))
    return signal_rms / (10.0 ** (float(snr_db) / 20.0))


def noise_seed(source_id: int, snr_db: float) -> int:
    """Seed shared by every geometry for the same source and SNR.

    The seed does not depend on geometry, so the additive noise sequence is
    the same realization for all five arrays.
    """
    return int(1_000_000 + int(source_id) * 100 + int(round(float(snr_db) * 10.0)))


def prepare_reference_waveform(
    fs: float,
    capture_duration_s: float,
    event_time_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Place one chirp in a capture buffer. Reused for every trial."""
    chirp = generate_chirp(fs=fs)
    n_capture = int(round(capture_duration_s * fs))
    event_index = int(round(event_time_s * fs))
    reference = np.zeros(n_capture, dtype=float)
    stop = min(n_capture, event_index + chirp.size)
    reference[event_index:stop] = chirp[: stop - event_index]
    return chirp, reference


def geometry_delays_samples(
    array: HydrophoneArray,
    source_m: np.ndarray,
    fs: float,
    sound_speed_mps: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return distances (m), true TDOAs (s), and simulator delays (samples).

    Delays are ``fs * true_tdoa`` relative to H0. They come from path length,
    not from a hand-picked sample shift.
    """
    distances = source_distances_m(source_m, array.coordinates_m)
    tdoas = true_tdoas_s(
        source_m,
        array.coordinates_m,
        sound_speed_mps=sound_speed_mps,
        reference_channel=0,
    )
    delays = tdoas_to_delay_samples(tdoas, fs=fs)
    return distances, tdoas, delays


def synthesize_delayed_capture(
    reference: np.ndarray,
    delays_samples: np.ndarray,
    noise_std: float,
    seed: int,
    dc_offsets: np.ndarray | None = None,
) -> np.ndarray:
    """Delay the shared source, then add one noise draw and the shared DC offsets."""
    if dc_offsets is None:
        dc_offsets = DEFAULT_DC_OFFSETS
    channels = apply_channel_delays(reference, delays_samples, n_channels=4)
    channels = add_gaussian_noise(channels, noise_std=noise_std, seed=seed)
    channels = add_dc_offsets(channels, np.asarray(dc_offsets, dtype=float))
    return channels


def process_capture(
    channels: np.ndarray,
    fs: float,
    lowcut_hz: float,
    highcut_hz: float,
    order: int,
    pre_samples: int,
    post_samples: int,
    max_tau_s: float,
    interpolation: int,
) -> tuple[np.ndarray, np.ndarray, list, int, np.ndarray]:
    """Preprocess, cut one common window, and estimate TDOAs with GCC-PHAT.

    Returns processed channels, the common window, GCC diagnostics, and the
    shared event index. Channels are not time-aligned individually.
    """
    processed = preprocess_multichannel(
        channels,
        fs=fs,
        lowcut=lowcut_hz,
        highcut=highcut_hz,
        order=order,
    )
    event_idx = detect_event(processed, threshold_ratio=0.5)
    window = extract_common_window(
        processed,
        center_idx=event_idx,
        pre_samples=pre_samples,
        post_samples=post_samples,
    )
    tdoas, diagnostics = estimate_tdoas(
        window,
        fs=fs,
        reference_channel=0,
        max_taus=max_tau_s,
        interpolation=interpolation,
        weighting="phat",
    )
    return processed, window, diagnostics, int(event_idx), tdoas


def search_max_tau_s(
    array: HydrophoneArray,
    sound_speed_mps: float,
    fs: float,
    margin_samples: float,
) -> float:
    """Physical maximum pairwise TDOA plus a one-sample search margin.

    The margin keeps a peak that lands on the last lag bin inside the
    search. It is not part of the physical bound used to check ground truth.
    """
    return max_pairwise_tdoa_s(array.coordinates_m, sound_speed_mps) + float(margin_samples) / float(fs)


def _nan_triple() -> list[float]:
    return [float("nan"), float("nan"), float("nan")]


def run_trial(
    array: HydrophoneArray,
    source_m: np.ndarray,
    source_id: int,
    snr_db: float,
    reference: np.ndarray,
    fs: float,
    sound_speed_mps: float,
    noise_std: float,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Simulate one source, one geometry, and one SNR. Return one result row."""
    source_m = np.asarray(source_m, dtype=float).reshape(3)
    distances, true_tdoa_s, delays = geometry_delays_samples(
        array,
        source_m,
        fs=fs,
        sound_speed_mps=sound_speed_mps,
    )
    seed = noise_seed(source_id, snr_db)
    channels = synthesize_delayed_capture(
        reference,
        delays,
        noise_std=noise_std,
        seed=seed,
        dc_offsets=np.asarray(settings["dc_offsets"], dtype=float),
    )

    max_tau = search_max_tau_s(
        array,
        sound_speed_mps,
        fs,
        margin_samples=float(settings["search_margin_samples"]),
    )
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
    except (FloatingPointError, ValueError) as exc:
        estimated_s = np.full(4, np.nan)
        estimated_s[0] = 0.0
        failure_reason = f"tdoa_failed:{type(exc).__name__}"

    true_us = true_tdoa_s * 1e6
    est_us = np.asarray(estimated_s, dtype=float) * 1e6
    err_us = est_us - true_us

    center = array_center_m(array.coordinates_m)
    true_az, true_el = direction_angles_deg(center, source_m)
    source_range = float(np.linalg.norm(source_m - center))

    if np.all(np.isfinite(estimated_s)):
        localization = localize_from_tdoa(
            array.coordinates_m,
            np.asarray(estimated_s, dtype=float),
            sound_speed_mps=sound_speed_mps,
            reference_channel=0,
        )
    else:
        localization = None

    row: dict[str, Any] = {
        "geometry": array.key,
        "geometry_name": array.name,
        "geometry_class": array.expected_class,
        "source_id": int(source_id),
        "source_x_m": float(source_m[0]),
        "source_y_m": float(source_m[1]),
        "source_z_m": float(source_m[2]),
        "source_range_m": source_range,
        "snr_db": float(snr_db),
        "noise_seed": int(seed),
        "true_tdoa_h0_us": 0.0,
        "true_tdoa_h1_us": float(true_us[1]),
        "true_tdoa_h2_us": float(true_us[2]),
        "true_tdoa_h3_us": float(true_us[3]),
        "est_tdoa_h0_us": 0.0 if np.isfinite(est_us[0]) else float("nan"),
        "est_tdoa_h1_us": float(est_us[1]),
        "est_tdoa_h2_us": float(est_us[2]),
        "est_tdoa_h3_us": float(est_us[3]),
        "tdoa_err_h1_us": float(err_us[1]),
        "tdoa_err_h2_us": float(err_us[2]),
        "tdoa_err_h3_us": float(err_us[3]),
        "true_azimuth_deg": float(true_az),
        "true_elevation_deg": float(true_el),
        "distance_h0_m": float(distances[0]),
        "distance_h1_m": float(distances[1]),
        "distance_h2_m": float(distances[2]),
        "distance_h3_m": float(distances[3]),
    }

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
        est_az = float("nan")
        est_el = float("nan")
        angular = float("nan")
        position_error = float("nan")
        if localization is None:
            residual_us = float("nan")
            reason = failure_reason or "tdoa_failed"
            geometry_class = array.expected_class
        else:
            residual_us = (
                float(localization.residual_rms_s * 1e6)
                if np.isfinite(localization.residual_rms_s)
                else float("nan")
            )
            reason = localization.failure_reason
            geometry_class = localization.geometry_class
        est_xyz = _nan_triple()

    row.update(
        {
            "est_x_m": est_xyz[0],
            "est_y_m": est_xyz[1],
            "est_z_m": est_xyz[2],
            "position_error_m": position_error,
            "est_azimuth_deg": est_az,
            "est_elevation_deg": est_el,
            "angular_error_deg": angular,
            "solver_success": bool(success),
            "solver_residual_us": residual_us,
            "failure_reason": reason,
            "solver_geometry_class": geometry_class,
        }
    )
    return row


def representative_waveforms(
    array: HydrophoneArray,
    source_m: np.ndarray,
    snr_db: float,
    reference: np.ndarray,
    fs: float,
    sound_speed_mps: float,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Build the signals and GCC traces used by the explanation figures."""
    distances, true_tdoa_s, delays = geometry_delays_samples(
        array,
        source_m,
        fs=fs,
        sound_speed_mps=sound_speed_mps,
    )
    noise_std = noise_std_for_snr(snr_db, fs)
    seed = noise_seed(source_id=0, snr_db=snr_db)
    channels = synthesize_delayed_capture(
        reference,
        delays,
        noise_std=noise_std,
        seed=seed,
        dc_offsets=np.asarray(settings["dc_offsets"], dtype=float),
    )
    max_tau = search_max_tau_s(
        array,
        sound_speed_mps,
        fs,
        margin_samples=float(settings["search_margin_samples"]),
    )
    processed, window, diagnostics, event_idx, estimated_s = process_capture(
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
    times = propagation_times_s(source_m, array.coordinates_m, sound_speed_mps=sound_speed_mps)
    return {
        "distances_m": distances,
        "propagation_times_s": times,
        "true_tdoa_s": true_tdoa_s,
        "estimated_tdoa_s": np.asarray(estimated_s, dtype=float),
        "delays_samples": delays,
        "channels": channels,
        "processed": processed,
        "window": window,
        "diagnostics": diagnostics,
        "event_idx": event_idx,
        "fs": fs,
        "max_tau_s": max_tau,
        "noise_seed": seed,
    }
