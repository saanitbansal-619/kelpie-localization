"""RoboSub 4-hydrophone localization — Python signal processing package.

This package currently covers the offline preprocessing foundation and
synthetic TDOA estimation:

1. Synthetic 4-channel capture generation
2. DC removal and zero-phase bandpass filtering
3. Common-event detection and shared-window extraction
4. GCC-PHAT TDOA relative to a reference channel

Direction estimation and 3D localization are intentionally not implemented yet.
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
from .tdoa import (
    GCCPHATResult,
    estimate_tdoas,
    gcc_phat,
    max_tau_from_baseline,
    normalized_cross_correlation,
)

__all__ = [
    "GCCPHATResult",
    "add_dc_offsets",
    "add_gaussian_noise",
    "apply_channel_delays",
    "bandpass_filter",
    "combined_energy",
    "detect_event",
    "estimate_tdoas",
    "extract_common_window",
    "gcc_phat",
    "generate_chirp",
    "generate_synthetic_capture",
    "max_tau_from_baseline",
    "normalize_signal",
    "normalized_cross_correlation",
    "preprocess_channel",
    "preprocess_multichannel",
    "remove_dc",
    "signal_envelope",
]
