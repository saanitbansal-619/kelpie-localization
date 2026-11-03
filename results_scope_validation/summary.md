# Offline scope-record localization

Every waveform in this run was synthesized in Python and wrapped in `FourChannelRecord`, the same object the Keysight reader returns. No oscilloscope, tank, or transducer measurement was made.

## Geometry

Coordinates are the stated metres, with H1 on channel 0. They are not the recentered catalog array.

| Hydrophone | x (m) | y (m) | z (m) |
| --- | ---: | ---: | ---: |
| H1 | 0.1443376 | 0.0000000 | 0.0000000 |
| H2 | -0.0721688 | 0.1250000 | 0.0000000 |
| H3 | -0.0721688 | -0.1250000 | 0.0000000 |
| H4 | 0.0000000 | 0.0000000 | -0.4000000 |

Longest pair is 0.425245 m. At 1480 m/s the physical |TDOA| limit is 287.33 µs. The GCC search adds one sample at 256000 Hz.

## Method

The record is bandpass-filtered at 15–45 kHz, the same cuts as the waveform study, then a shared event window is cut and GCC-PHAT estimates the delays. `localize_from_tdoa` solves the 3+1 array. A trial is reliable only when that solver accepts a position and none of these waveform flags is set: non-finite TDOA, delay outside the physical limit, correlation peak on the search edge, GCC argmax more than half a carrier cycle from the correlation envelope, or correlation contrast below 6. Those flags do not use the known source. The contrast floor was raised from 3 to 6 after one pass of this same grid: the lower floor marked a 0 dB, 25 kHz solve reliable when the position error was 131 m and the weakest channel contrast was 3.09. Clean pulses in that pass stayed above 6.9. A synthetic position error above 20 m is recorded as `huge_localization_error` and stays in the table. It does not change the reliable bit, so a reliable trial with a large error is visible as false confidence.

Sample rate 256000 Hz is the virtual rate. Pulse length is 4 ms with the existing Tukey taper. Noise uses `noise_std_from_snr_db` on that pulse. Seeds start at 20261101 and follow `base + source*1000 + frequency*100 + snr*10 + offset`.

Geometry grid: 6 sources, frequencies 25000, 30000, 35000, 40000 Hz, SNR levels noise-free, 20 dB, 10 dB, and 0 dB. That is 96 trials. Timing-offset trials add a delay on H2 at 30 kHz for the source (2, 1, 1.5): 0.5 sample, 2 samples, and one carrier period (8.5333 samples), each noise-free and at 20 dB (6 trials).

## Geometry-trial results

| SNR | Trials | Solver success | Reliable | Solver failures |
| --- | ---: | ---: | ---: | ---: |
| noise-free | 24 | 24 (100.0%) | 21 (87.5%) | 0 |
| 20 dB | 24 | 23 (95.8%) | 17 (70.8%) | 1 |
| 10 dB | 24 | 12 (50.0%) | 0 (0.0%) | 12 |
| 0 dB | 24 | 13 (54.2%) | 0 (0.0%) | 11 |
| All | 96 | 72 (75.0%) | 38 (39.6%) | 24 |

3 noise-free solver successes were flagged unreliable even though the position error was under 0.1 m (largest of those errors 0.084 m). The flag on those rows is the carrier-envelope check. The delay estimate was still close, so that check is cautious on a clean pulse.

Median position error, in metres, among solver successes. An empty cell has no accepted solver position.

| SNR | 25 kHz | 30 kHz | 35 kHz | 40 kHz |
| --- | ---: | ---: | ---: | ---: |
| noise-free | 0.0607 | 0.0607 | 0.0607 | 0.0607 |
| 20 dB | 0.0845 | 0.1489 | 0.0607 | 0.0757 |
| 10 dB | 2.2727 | 2.0676 | 2.3419 | 2.4816 |
| 0 dB | 2.5892 | 3.7449 | 2.2660 | 3.0218 |

Median angular error from the four-phone centroid, in degrees, among solver successes.

| SNR | 25 kHz | 30 kHz | 35 kHz | 40 kHz |
| --- | ---: | ---: | ---: | ---: |
| noise-free | 0.035 | 0.036 | 0.036 | 0.036 |
| 20 dB | 0.101 | 0.111 | 0.057 | 0.036 |
| 10 dB | 15.936 | 5.177 | 9.787 | 15.130 |
| 0 dB | 42.125 | 87.948 | 36.886 | 47.488 |

Median of the mean absolute TDOA error across H2, H3, and H4, in microseconds, among solver successes.

| SNR | 25 kHz | 30 kHz | 35 kHz | 40 kHz |
| --- | ---: | ---: | ---: | ---: |
| noise-free | 0.054 | 0.054 | 0.054 | 0.054 |
| 20 dB | 0.175 | 0.186 | 0.072 | 0.056 |
| 10 dB | 13.750 | 11.582 | 28.500 | 25.001 |
| 0 dB | 98.510 | 130.966 | 78.078 | 117.496 |

Solver rejection counts:

| Failure reason | Count |
| --- | ---: |
| no_bounded_solution | 24 |

Flag counts. A trial can carry more than one flag.

| Flag | Trials |
| --- | ---: |
| low_correlation_contrast | 48 |
| narrowband_ambiguity | 34 |
| solver_rejected | 24 |
| huge_localization_error | 2 |
| tdoa_outside_physical_limit | 1 |

Position error on the subsets the flags define:

| Subset | Trials | Median error (m) | 95th percentile (m) | Max error (m) |
| --- | ---: | ---: | ---: | ---: |
| Solver success | 72 | 0.1007 | 4.0877 | 131.1818 |
| Reliable | 38 | 0.0679 | 0.1861 | 0.5260 |

Reliable trials with position error above 20 m: 0.

## Timing-offset trials

These rows inject a known extra delay on H2. TDOA error is scored against the geometry delay plus that offset. Position error is still scored against the original source, so a one-period shift is expected to move the estimate.

| SNR | H2 offset (samples) | Solver success | Reliable | Mean |TDOA error| (µs) | Position error (m) | Flags |
| --- | ---: | --- | --- | ---: | ---: | --- |
| noise-free | 0.5000 | True | True | 0.056 | 0.0860 | — |
| noise-free | 2.0000 | True | True | 0.056 | 0.3346 | — |
| noise-free | 8.5333 | True | True | 0.055 | 0.8759 | — |
| 20 dB | 0.5000 | True | True | 0.099 | 0.0998 | — |
| 20 dB | 2.0000 | True | True | 0.120 | 0.4089 | — |
| 20 dB | 8.5333 | True | True | 0.205 | 0.8600 | — |

## Files

- `virtual_trials.csv` — one row per trial
- `example_record.npz` — one synthetic record in the acquisition NPZ layout. Reloading it reproduced the same TDOAs
- `figures/position_error_vs_snr.png`
- `figures/reliability_vs_snr.png`
- `figures/tdoa_error_vs_snr.png`
- `run_manifest.json`

## Remaining physical validation

Still required before this pipeline can be treated as a hardware result:

- Connect the MSOX2014A and capture one four-channel record with `:DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4`. This run did not.
- Survey H1..H4 in the solver frame. The coordinates above are the stated values, not a measurement.
- Confirm which conditioner output is plugged into which scope channel. The CH1=H1 … CH4=H4 map is a convention.
- Measure the sound speed for the test water. The solver used 1480 m/s.
- Calibrate volts to pascals for the Aquarian S1f and PCB 482C05 chain. Synthetic channels are unitless voltages with the simulator's DC offsets.
- Record a real 25–40 kHz burst from a known in-water position and compare the estimate with that position. Multipath, transducer response, and electrical crosstalk are absent from these waveforms.
- Measure cable and trigger skew. The timing offsets here were inserted with `delay_signal`.
- Confirm the scope timebase and record length against the 4 ms pre-window and 6 ms post-window used at 256 kHz.
