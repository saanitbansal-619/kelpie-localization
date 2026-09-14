"""Generate a synthetic 4-channel hydrophone capture and save it to disk.

Run from the project root:

    python scripts/generate_synthetic_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from src.simulation import generate_synthetic_capture


def main() -> None:
    output_dir = PROJECT_ROOT / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "synthetic_4ch_capture.npz"

    delays_samples = np.array([0.0, 6.0, 13.5, 21.0])
    dc_offsets = np.array([0.35, -0.22, 0.18, -0.40])

    channels, info = generate_synthetic_capture(
        n_channels=4,
        delays_samples=delays_samples,
        dc_offsets=dc_offsets,
        noise_std=0.08,
        seed=0,
    )

    np.savez(
        output_path,
        channels=channels,
        fs=np.array(info["fs"]),
        delays_samples=info["delays_samples"],
        delays_seconds=info["delays_seconds"],
        dc_offsets=info["dc_offsets"],
        noise_std=np.array(info["noise_std"]),
        event_index=np.array(info["event_index"]),
        chirp_duration_s=np.array(info["chirp_duration_s"]),
        f_start_hz=np.array(info["f_start_hz"]),
        f_end_hz=np.array(info["f_end_hz"]),
        seed=np.array(-1 if info["seed"] is None else info["seed"]),
    )

    print("Saved synthetic capture:")
    print(f"  path            : {output_path.relative_to(PROJECT_ROOT)}")
    print(f"  sample rate     : {info['fs']:.1f} Hz")
    print(f"  channels shape  : {channels.shape}")
    print("  known delays (samples):")
    for i, delay in enumerate(info["delays_samples"]):
        microseconds = 1e6 * delay / info["fs"]
        print(f"    ch{i}: {delay:7.2f} samples  ({microseconds:7.2f} us)")
    print("  DC offsets:")
    for i, offset in enumerate(info["dc_offsets"]):
        print(f"    ch{i}: {offset:+.3f}")
    print(f"  noise std       : {info['noise_std']}")


if __name__ == "__main__":
    main()
