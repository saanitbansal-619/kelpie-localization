"""RoboSub 4-hydrophone localization — Python signal processing package.

This package currently covers the offline preprocessing foundation:

1. Synthetic 4-channel capture generation
2. DC removal and zero-phase bandpass filtering
3. Common-event detection and shared-window extraction

TDOA / GCC-PHAT and 3D localization are intentionally not implemented yet.
"""

from .detection import (
    combined_energy,
    detect_event,
    extract_common_window,
    signal_envelope,
)
from .preprocessing import (
    bandpass_filter,
    normalize_signal,
    preprocess_channel,
    preprocess_multichannel,
    remove_dc,
)
from .simulation import (
    add_dc_offsets,
    add_gaussian_noise,
    apply_channel_delays,
    generate_chirp,
    generate_synthetic_capture,
)

__all__ = [
    "add_dc_offsets",
    "add_gaussian_noise",
    "apply_channel_delays",
    "bandpass_filter",
    "combined_energy",
    "detect_event",
    "extract_common_window",
    "generate_chirp",
    "generate_synthetic_capture",
    "normalize_signal",
    "preprocess_channel",
    "preprocess_multichannel",
    "remove_dc",
    "signal_envelope",
]
