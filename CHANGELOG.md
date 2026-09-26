# Changelog

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
