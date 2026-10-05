# Changelog

## 2026-10-05 — joint H4 height and base scale

### Added

* `simulations/joint_geometry_study/`: Change #2 on nine 3+1 layouts, H4 at +30, +40, and +50 cm and the catalog triangle at 1.00×, 1.25×, and 1.50×. The 30 cm / 1.00× layout is the control
* `results_joint_geometry_optimization/` for the coordinates, trial table, comparison, SNR and directional summaries, and plots

### Preserved

* `results/`, `results_h4_height_study/`, and the noise-study and waveform-study results

## 2026-10-04 — 3+1 H4 height sweep

### Added

* `simulations/h4_height_study/`: the Change #1 and Change #2 experiments on the existing 3+1 triangle, with only H4's height changing. Heights are -30, -20, -15, -10, -5, +5, +10, +15, +20, and +30 cm from the triangle plane
* `results_h4_height_study/` for every table and figure from that sweep

### Preserved

* `results/`, the noise-study results, and the waveform-study results. This sweep does not read or write them

## 2026-10-04 — tetrahedral versus 3+1

### Added

* `make_three_plus_one(z_offset_m)` in `src/geometry.py`. The default offset, +0.15 m, is the existing catalog array. A negative offset mirrors it. The triangle side stays 0.25 m, the same maximum baseline as the tetrahedron
* `simulations/geometry_pair/`: the Change #1 noise study and the Change #2 waveform study, each run on the tetrahedron and on 3+1 with the same sources, seed, SNR list, and solver. Results go to `results/<geometry>/`
* `results/geometry_comparison/` with the side-by-side summary, directional table, and comparison plots

### Preserved

* `simulations/noise_study/results/`, `simulations/waveform_study/results/`, and their figures. The new tetrahedral runs reproduce those summaries and do not replace the files

## 2026-10-04 — pulsed pinger waveforms

### Added

* `generate_pinger_pulse` and `synthesize_pinger_capture` in `src/simulation.py`. A configurable pulsed sinusoid is placed at each hydrophone with a fractional propagation delay. Optional `1/distance` attenuation is off in the reported sweep
* `simulations/waveform_study/`: 100 trials of a 40 kHz, 4 ms pulse at noise-free, 30, 20, 10, 5, and 0 dB. TDOA is estimated with the existing GCC-PHAT path and passed to the existing solver. A 25-trial comparison repeats 25, 30, 35, and 40 kHz
* `results/waveform_experiment_results.csv`, `results/waveform_experiment_summary.csv`, the frequency-comparison tables, and the waveform, GCC-PHAT, SNR, and carrier figures
* Tests for carrier frequency, pulse length, geometric delay, fractional delay, GCC-PHAT on a known lag, noise-free agreement with geometry, and seed reproducibility

### Preserved

* The localization-versus-SNR study and its result files. That experiment was not rerun or replaced
* The chirp capture path, geometry study, and localization solver

## 2026-10-04 — localization versus SNR

### Added

* `signal_power`, `noise_power_for_snr_db`, `noise_std_from_snr_db`, and `estimate_snr_db` in `src/simulation.py`. Noise power comes from `SNR_dB = 10 * log10(P_signal / P_noise)` with power equal to mean square
* `simulations/noise_study/`: 100 trials at each of 30, 25, 20, 15, 10, 5, and 0 dB, plus a noise-free baseline, on the existing tetrahedral array. The geometry-study trial runner is reused. One source set and one noise pattern are scaled across SNR levels
* `results/noise_experiment_results.csv`, `results/noise_experiment_summary.csv`, and localization, distribution, success-rate, and angular-error figures
* Tests for the SNR definition, seed reproducibility, the increase of noise power at lower SNR, and the existing zero-noise capture path

### Preserved

* Geometry-study and hydrophone-count result files. Those Monte Carlo runs were not repeated
* The previous `noise_std = RMS(chirp) / 10^(SNR/20)` expression in the geometry-study helper, which matches the new power formula

## 2026-09-26 — repository cleanup

### Changed

* Added `.gitignore` for Python bytecode, pytest cache, the local virtual environment, and operating-system leftovers
* Stopped tracking `.venv/` and `*.pyc` files. The environment remains on disk and can be recreated with `python -m venv .venv` and `pip install -r requirements.txt`
* Removed `__pycache__/` directories and `.pytest_cache/`

### Preserved

* Synthetic capture, preprocessing, event detection, GCC-PHAT, geometry, localization, the five-geometry study, and the 4/5/6 hydrophone study
* Professor-facing figures, result CSVs, tests, and technical notes
* Hardware integration is not done. The next phase is hardware readiness and real-data loading

## 2026-09-26

### Added

* Five centered four-hydrophone geometries in `src/geometry.py` (linear, square planar, unequal-arm cross, regular tetrahedron, three-plus-one), with path-length propagation delays
* `src/localization.py`: nonlinear least-squares TDOA localization, direction angles, and an angular-error function. Collinear and coplanar arrays return no position
* Geometry simulation study under `simulations/geometry_study/`: 300 shared sources, six SNR levels, 9000 trials, CSV results, and the comparison figures
* `PROFESSOR_SUMMARY.md` for that study, written from the measured simulation output
* Tests for geometry, propagation, degeneracy, angular error, and one end-to-end trial

### Notes

* This phase is a simulation. Hardware validation is not done.
* The study does not rank a single winning geometry. TDOA error in microseconds is similar across the five arrays. Unique 3D localization is available only for the two non-coplanar arrays, and range error remains large for a 0.25 m baseline.

### Added later the same day

* Professor-facing figures for the completed geometry study, drawn from the saved CSVs into `simulations/geometry_study/figures/professor/`. The 9000-trial Monte Carlo was not rerun, and those result files were not modified.
* A separate hydrophone-count simulation in `simulations/hydrophone_count_study/`: 4, 5, and 6 volumetric hydrophones inside the same 0.25 m envelope, the same 300 sources, and the same six SNRs (5400 trials).
* `src/hydrophone_counts.py` for the five- and six-hydrophone coordinates. The four-hydrophone array is the existing tetrahedron. The five-geometry catalog is unchanged.

### Notes for the count study

* This is still a simulation. Hardware validation has not occurred.
* The count-study conclusion is taken from that run's CSV summaries, not assumed in advance. See `simulations/hydrophone_count_study/PROFESSOR_SUMMARY.md`.

## 2026-09-14

### Added

* Initial repository structure for the standalone 4-hydrophone localization project
* Synthetic 4-channel chirp generator with configurable relative delays, Gaussian noise, and DC offsets
* Preprocessing functions: DC removal, zero-phase Butterworth bandpass, peak normalization, and aligned multichannel processing
* Combined-energy event detection and common-window extraction that uses the same sample indices on every channel
* Scripts to save a synthetic `.npz` capture and to run a preprocessing visualization demo
* Pytest coverage for DC removal, normalization, bandpass length, shape preservation, and identical common-window indices
* README, preprocessing notes, and this changelog
