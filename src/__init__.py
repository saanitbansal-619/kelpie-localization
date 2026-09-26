"""RoboSub 4-hydrophone localization — Python signal processing package.

Offline pipeline:

1. Synthetic 4-channel capture generation
2. DC removal and zero-phase bandpass filtering
3. Common-event detection and shared-window extraction
4. GCC-PHAT TDOA relative to a reference channel
5. Array geometry and geometry-derived propagation delays
6. TDOA localization / direction estimation, with degenerate arrays reported
   as unsuccessful rather than forced to a 3D point

Hardware acquisition, ROS, and Jetson integration are not part of this package.
"""

from .detection import (
    combined_energy,
    detect_event,
    extract_common_window,
    signal_envelope,
)
from .geometry import (
    GEOMETRIES,
    SOUND_SPEED_MPS,
    generate_source_positions,
    get_geometry,
    list_geometries,
    max_pairwise_tdoa_s,
    propagation_times_s,
    source_distances_m,
    true_tdoas_s,
)
from .localization import (
    LocalizationResult,
    angular_error_deg,
    classify_array,
    localize_from_tdoa,
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
    "GEOMETRIES",
    "GCCPHATResult",
    "LocalizationResult",
    "SOUND_SPEED_MPS",
    "add_dc_offsets",
    "add_gaussian_noise",
    "angular_error_deg",
    "apply_channel_delays",
    "bandpass_filter",
    "classify_array",
    "combined_energy",
    "detect_event",
    "estimate_tdoas",
    "extract_common_window",
    "gcc_phat",
    "generate_chirp",
    "generate_source_positions",
    "generate_synthetic_capture",
    "get_geometry",
    "list_geometries",
    "localize_from_tdoa",
    "max_pairwise_tdoa_s",
    "max_tau_from_baseline",
    "normalize_signal",
    "normalized_cross_correlation",
    "preprocess_channel",
    "preprocess_multichannel",
    "propagation_times_s",
    "remove_dc",
    "signal_envelope",
    "source_distances_m",
    "true_tdoas_s",
]
