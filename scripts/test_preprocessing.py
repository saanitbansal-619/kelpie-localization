"""Visualize the synthetic capture → preprocess → common-window pipeline.

Run from the project root:

    python scripts/test_preprocessing.py

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

from src.detection import combined_energy, detect_event, extract_common_window
from src.preprocessing import preprocess_multichannel
from src.simulation import generate_synthetic_capture

LOWCUT_HZ = 15_000.0
HIGHCUT_HZ = 45_000.0
PRE_SAMPLES = 1024
POST_SAMPLES = 1536


def _time_axis(n_samples: int, fs: float) -> np.ndarray:
    return np.arange(n_samples, dtype=float) / fs * 1_000.0


def _plot_channels(
    channels: np.ndarray,
    fs: float,
    title: str,
    output_path: Path,
    event_idx: int | None = None,
    ylabel: str = "Amplitude",
) -> None:
    n_channels, n_samples = channels.shape
    t_ms = _time_axis(n_samples, fs)
    fig, axes = plt.subplots(n_channels, 1, sharex=True, figsize=(11, 8))
    if n_channels == 1:
        axes = [axes]

    for i, ax in enumerate(axes):
        ax.plot(t_ms, channels[i], linewidth=0.8)
        ax.set_ylabel(f"ch{i}\n{ylabel}")
        ax.grid(True, alpha=0.3)
        if event_idx is not None:
            ax.axvline(event_idx / fs * 1_000.0, color="red", linestyle="--", linewidth=1)

    axes[-1].set_xlabel("Time (ms)")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def main() -> None:
    plots_dir = PROJECT_ROOT / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    delays_samples = np.array([0.0, 6.0, 13.5, 21.0])
    dc_offsets = np.array([0.35, -0.22, 0.18, -0.40])

    raw, info = generate_synthetic_capture(
        n_channels=4,
        delays_samples=delays_samples,
        dc_offsets=dc_offsets,
        noise_std=0.08,
        seed=0,
    )
    fs = float(info["fs"])

    processed = preprocess_multichannel(raw, fs=fs, lowcut=LOWCUT_HZ, highcut=HIGHCUT_HZ)
    event_idx = detect_event(processed, threshold_ratio=0.5)
    window = extract_common_window(
        processed,
        center_idx=event_idx,
        pre_samples=PRE_SAMPLES,
        post_samples=POST_SAMPLES,
    )
    window_start = event_idx - PRE_SAMPLES
    window_end = event_idx + POST_SAMPLES
    energy = combined_energy(processed)

    _plot_channels(
        raw,
        fs,
        title="Raw 4-channel synthetic capture (noise + DC offsets)",
        output_path=plots_dir / "raw_channels.png",
    )
    _plot_channels(
        processed,
        fs,
        title="Preprocessed channels (DC removed, 15–45 kHz zero-phase bandpass)",
        output_path=plots_dir / "processed_channels.png",
        event_idx=event_idx,
    )
    _plot_channels(
        window,
        fs,
        title="Common multi-channel event window (identical indices on every channel)",
        output_path=plots_dir / "event_window.png",
        ylabel="Amplitude",
    )

    fig, ax = plt.subplots(figsize=(11, 3.5))
    t_ms = _time_axis(energy.shape[0], fs)
    ax.plot(t_ms, energy, linewidth=0.9)
    ax.axvline(event_idx / fs * 1_000.0, color="red", linestyle="--", label="detected event")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Combined energy")
    ax.set_title("Shared detector: mean Hilbert-envelope power across channels")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots_dir / "combined_energy.png", dpi=120)
    plt.close(fig)

    print("Preprocessing demo")
    print("==================")
    print(f"sample rate           : {fs:.1f} Hz")
    print(f"bandpass              : {LOWCUT_HZ:.0f}-{HIGHCUT_HZ:.0f} Hz")
    print("true delays (samples) :")
    for i, delay in enumerate(info["delays_samples"]):
        print(f"  ch{i}: {delay:.2f}")
    print(f"detected event index  : {event_idx}")
    print(f"window indices        : [{window_start}, {window_end})  (half-open)")
    print(f"window center in win  : {PRE_SAMPLES}")
    print("array shapes")
    print(f"  raw                 : {raw.shape}")
    print(f"  processed           : {processed.shape}")
    print(f"  combined energy     : {energy.shape}")
    print(f"  common window       : {window.shape}")
    print("saved figures")
    for name in ("raw_channels.png", "processed_channels.png", "event_window.png", "combined_energy.png"):
        print(f"  plots/{name}")


if __name__ == "__main__":
    main()
