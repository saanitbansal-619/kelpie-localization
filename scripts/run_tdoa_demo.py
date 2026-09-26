"""Recover known synthetic TDOAs with GCC-PHAT and plot the correlations.

Run from the project root:

    python scripts/run_tdoa_demo.py

Figures are written under ``plots/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.detection import detect_event, extract_common_window
from src.preprocessing import preprocess_multichannel
from src.simulation import generate_chirp, generate_synthetic_capture
from src.tdoa import (
    DEFAULT_INTERPOLATION,
    DEFAULT_SOUND_SPEED_MPS,
    estimate_tdoas,
    max_tau_from_baseline,
)

LOWCUT_HZ = 15_000.0
HIGHCUT_HZ = 45_000.0
PRE_SAMPLES = 1024
POST_SAMPLES = 1536
INTERPOLATION = DEFAULT_INTERPOLATION
BASELINE_M = 0.25
SNR_DB = 20.0

# Mixed-sign delays, all inside |Δt|max ≈ 0.25 m / 1480 m/s ≈ 169 µs.
DELAYS_SAMPLES = np.array([0.0, 10.5, -8.0, 18.25])
DC_OFFSETS = np.array([0.35, -0.22, 0.18, -0.40])


def _noise_std_for_snr(snr_db: float) -> float:
    chirp = generate_chirp()
    signal_rms = float(np.sqrt(np.mean(chirp**2)))
    return signal_rms / (10.0 ** (snr_db / 20.0))


def _print_table(true_us: np.ndarray, estimated_us: np.ndarray) -> None:
    error_us = np.abs(estimated_us - true_us)
    header = (
        f"{'Channel':<8}| {'True TDOA (us)':<16}| "
        f"{'Estimated TDOA (us)':<21}| {'Absolute Error (us)':<20}"
    )
    rule = "-" * len(header)
    print(header)
    print(rule)
    for i, (true, est, err) in enumerate(zip(true_us, estimated_us, error_us)):
        print(f"{'CH' + str(i):<8}| {true:>14.2f}  | {est:>19.2f}  | {err:>18.2f}")
    print()


def _plot_gcc_phat(
    diagnostics: list,
    true_tdoas: np.ndarray,
    output_path: Path,
    plot_limit_us: float,
) -> None:
    pairs = [(i, diagnostics[i]) for i in range(1, 4) if diagnostics[i] is not None]
    fig, axes = plt.subplots(len(pairs), 1, sharex=True, figsize=(11, 8))
    if len(pairs) == 1:
        axes = [axes]

    for ax, (channel, result) in zip(axes, pairs):
        lags_us = result.lags_seconds * 1e6
        ax.plot(lags_us, result.correlation, linewidth=0.9, color="C0", label="GCC-PHAT")
        est_us = result.tau * 1e6
        true_us = true_tdoas[channel] * 1e6
        ax.axvline(est_us, color="C1", linestyle="-", linewidth=1.2, label="estimated peak")
        ax.axvline(true_us, color="C3", linestyle="--", linewidth=1.2, label="true TDOA")
        ax.scatter([est_us], [result.peak_value], color="C1", zorder=3, s=28)
        ax.set_ylabel(f"CH{channel} vs CH0")
        ax.grid(True, alpha=0.3)
        ax.set_xlim(-plot_limit_us, plot_limit_us)

    axes[0].legend(loc="upper right")
    axes[-1].set_xlabel("Lag (us)")
    fig.suptitle("GCC-PHAT correlation versus lag (positive = later than CH0)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def main() -> None:
    plots_dir = PROJECT_ROOT / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    fs = 256_000.0
    sample_period_s = 1.0 / fs
    noise_std = _noise_std_for_snr(SNR_DB)
    max_tau = max_tau_from_baseline(BASELINE_M, DEFAULT_SOUND_SPEED_MPS)

    raw, info = generate_synthetic_capture(
        n_channels=4,
        fs=fs,
        delays_samples=DELAYS_SAMPLES,
        dc_offsets=DC_OFFSETS,
        noise_std=noise_std,
        seed=0,
    )
    processed = preprocess_multichannel(raw, fs=fs, lowcut=LOWCUT_HZ, highcut=HIGHCUT_HZ)
    event_idx = detect_event(processed, threshold_ratio=0.5)
    window = extract_common_window(
        processed,
        center_idx=event_idx,
        pre_samples=PRE_SAMPLES,
        post_samples=POST_SAMPLES,
    )

    tdoas, diagnostics = estimate_tdoas(
        window,
        fs=fs,
        reference_channel=0,
        max_taus=max_tau,
        interpolation=INTERPOLATION,
    )

    true_tdoas = np.asarray(info["delays_seconds"], dtype=float)
    true_us = true_tdoas * 1e6
    estimated_us = tdoas * 1e6
    abs_error_us = np.abs(estimated_us - true_us)
    lag_resolution_s = 1.0 / (INTERPOLATION * fs)

    _plot_gcc_phat(
        diagnostics,
        true_tdoas,
        plots_dir / "tdoa_gcc_phat.png",
        plot_limit_us=min(200.0, max_tau * 1e6 * 1.15),
    )

    print("TDOA demo (GCC-PHAT)")
    print("====================")
    print(f"sample rate                         : {fs:.1f} Hz")
    print(f"original sample period              : {sample_period_s * 1e6:.5f} us")
    print(f"interpolation factor                : {INTERPOLATION}")
    print(f"effective correlation lag resolution: {lag_resolution_s * 1e6:.5f} us")
    print(
        "  Interpolation only refines the numerical peak of the correlation "
        "function. It does not increase ADC bandwidth or create new physical "
        "information."
    )
    print(f"bandpass                            : {LOWCUT_HZ:.0f}-{HIGHCUT_HZ:.0f} Hz")
    print(f"SNR (chirp RMS / noise std)         : {SNR_DB:.1f} dB")
    print(f"noise std                           : {noise_std:.4f}")
    print(f"assumed baseline / sound speed      : {BASELINE_M:.2f} m / {DEFAULT_SOUND_SPEED_MPS:.0f} m/s")
    print(f"max_tau search limit                : {max_tau * 1e6:.2f} us")
    print(f"detected event index                : {event_idx}")
    print(f"common window shape                 : {window.shape}")
    print()
    _print_table(true_us, estimated_us)
    print(f"maximum absolute TDOA error         : {float(np.max(abs_error_us)):.2f} us")
    print("saved figure")
    print("  plots/tdoa_gcc_phat.png")


if __name__ == "__main__":
    main()
