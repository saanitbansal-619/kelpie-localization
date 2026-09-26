"""Measure GCC-PHAT TDOA error as synthetic SNR decreases.

Run from the project root:

    python scripts/run_tdoa_snr_experiment.py

Writes:

* data/processed/tdoa_snr_results.csv
* plots/tdoa_error_vs_snr.png
"""

from __future__ import annotations

import csv
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

SNR_LEVELS_DB = (40.0, 30.0, 20.0, 10.0, 5.0, 0.0)
N_TRIALS = 50
LOWCUT_HZ = 15_000.0
HIGHCUT_HZ = 45_000.0
PRE_SAMPLES = 1024
POST_SAMPLES = 1536
INTERPOLATION = DEFAULT_INTERPOLATION
BASELINE_M = 0.25
FS = 256_000.0

# Mixed-sign, physically plausible for a ~0.25 m baseline.
DELAYS_SAMPLES = np.array([0.0, 10.5, -8.0, 18.25])
DC_OFFSETS = np.array([0.35, -0.22, 0.18, -0.40])
TRUE_TDOAS_S = DELAYS_SAMPLES / FS


def _noise_std_for_snr(snr_db: float) -> float:
    chirp = generate_chirp(fs=FS)
    signal_rms = float(np.sqrt(np.mean(chirp**2)))
    return signal_rms / (10.0 ** (snr_db / 20.0))


def _trial_abs_errors_us(
    snr_db: float,
    trial: int,
    max_tau: float,
    weighting: str,
) -> np.ndarray:
    seed = int(1_000_000 + 1_000 * snr_db + trial)
    channels, info = generate_synthetic_capture(
        n_channels=4,
        fs=FS,
        delays_samples=DELAYS_SAMPLES,
        dc_offsets=DC_OFFSETS,
        noise_std=_noise_std_for_snr(snr_db),
        seed=seed,
    )
    processed = preprocess_multichannel(
        channels,
        fs=float(info["fs"]),
        lowcut=LOWCUT_HZ,
        highcut=HIGHCUT_HZ,
    )
    event_idx = detect_event(processed, threshold_ratio=0.5)
    window = extract_common_window(
        processed,
        center_idx=event_idx,
        pre_samples=PRE_SAMPLES,
        post_samples=POST_SAMPLES,
    )
    tdoas, _ = estimate_tdoas(
        window,
        fs=float(info["fs"]),
        reference_channel=0,
        max_taus=max_tau,
        interpolation=INTERPOLATION,
        weighting=weighting,
    )
    abs_error_s = np.abs(tdoas[1:] - TRUE_TDOAS_S[1:])
    return abs_error_s * 1e6


def _summarize(errors_us: np.ndarray) -> dict[str, float]:
    return {
        "mean_abs_error_us": float(np.mean(errors_us)),
        "median_abs_error_us": float(np.median(errors_us)),
        "std_abs_error_us": float(np.std(errors_us, ddof=1)) if errors_us.size > 1 else 0.0,
        "p25_abs_error_us": float(np.percentile(errors_us, 25)),
        "p75_abs_error_us": float(np.percentile(errors_us, 75)),
        "p95_abs_error_us": float(np.percentile(errors_us, 95)),
        "max_abs_error_us": float(np.max(errors_us)),
    }


def _write_csv(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "method",
        "snr_db",
        "n_trials",
        "n_error_samples",
        "mean_abs_error_us",
        "median_abs_error_us",
        "std_abs_error_us",
        "p25_abs_error_us",
        "p75_abs_error_us",
        "p95_abs_error_us",
        "max_abs_error_us",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _plot_error_vs_snr(
    snr_levels: np.ndarray,
    gcc_rows: list[dict[str, float | int | str]],
    ncc_rows: list[dict[str, float | int | str]],
    output_path: Path,
) -> None:
    gcc_median = np.array([row["median_abs_error_us"] for row in gcc_rows], dtype=float)
    gcc_p25 = np.array([row["p25_abs_error_us"] for row in gcc_rows], dtype=float)
    gcc_p75 = np.array([row["p75_abs_error_us"] for row in gcc_rows], dtype=float)
    ncc_median = np.array([row["median_abs_error_us"] for row in ncc_rows], dtype=float)

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ax.fill_between(
        snr_levels,
        gcc_p25,
        gcc_p75,
        color="C0",
        alpha=0.22,
        label="GCC-PHAT IQR",
    )
    ax.plot(snr_levels, gcc_median, marker="o", color="C0", label="GCC-PHAT median")
    ax.plot(
        snr_levels,
        ncc_median,
        marker="s",
        color="C1",
        linestyle="--",
        label="ordinary NCC median",
    )
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("Absolute TDOA error (us)")
    ax.set_title("TDOA error versus SNR (non-reference channels, 50 trials each)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.invert_xaxis()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def main() -> None:
    max_tau = max_tau_from_baseline(BASELINE_M, DEFAULT_SOUND_SPEED_MPS)
    if np.max(np.abs(TRUE_TDOAS_S)) >= max_tau:
        raise RuntimeError("synthetic delays are not physically plausible for the assumed baseline")

    gcc_rows: list[dict[str, float | int | str]] = []
    ncc_rows: list[dict[str, float | int | str]] = []

    print("TDOA SNR experiment")
    print("===================")
    print(f"trials per SNR     : {N_TRIALS}")
    print(f"true TDOAs (us)    : {TRUE_TDOAS_S * 1e6}")
    print(f"max_tau (us)       : {max_tau * 1e6:.2f}")
    print(f"interpolation      : {INTERPOLATION}")
    print()

    for snr_db in SNR_LEVELS_DB:
        gcc_errors = []
        ncc_errors = []
        for trial in range(N_TRIALS):
            gcc_errors.append(_trial_abs_errors_us(snr_db, trial, max_tau, "phat"))
            ncc_errors.append(_trial_abs_errors_us(snr_db, trial, max_tau, "none"))
        gcc_errors_us = np.concatenate(gcc_errors)
        ncc_errors_us = np.concatenate(ncc_errors)
        gcc_summary = _summarize(gcc_errors_us)
        ncc_summary = _summarize(ncc_errors_us)
        gcc_row: dict[str, float | int | str] = {
            "method": "gcc_phat",
            "snr_db": snr_db,
            "n_trials": N_TRIALS,
            "n_error_samples": int(gcc_errors_us.size),
            **gcc_summary,
        }
        ncc_row: dict[str, float | int | str] = {
            "method": "ncc",
            "snr_db": snr_db,
            "n_trials": N_TRIALS,
            "n_error_samples": int(ncc_errors_us.size),
            **ncc_summary,
        }
        gcc_rows.append(gcc_row)
        ncc_rows.append(ncc_row)
        print(
            f"SNR {snr_db:5.1f} dB | GCC-PHAT median {gcc_summary['median_abs_error_us']:7.2f} us "
            f"p95 {gcc_summary['p95_abs_error_us']:7.2f} us max {gcc_summary['max_abs_error_us']:7.2f} us "
            f"| NCC median {ncc_summary['median_abs_error_us']:7.2f} us"
        )

    csv_path = PROJECT_ROOT / "data" / "processed" / "tdoa_snr_results.csv"
    _write_csv(csv_path, gcc_rows + ncc_rows)
    plot_path = PROJECT_ROOT / "plots" / "tdoa_error_vs_snr.png"
    _plot_error_vs_snr(np.asarray(SNR_LEVELS_DB), gcc_rows, ncc_rows, plot_path)

    print()
    print(f"saved CSV   : {csv_path.relative_to(PROJECT_ROOT)}")
    print(f"saved plot  : {plot_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
