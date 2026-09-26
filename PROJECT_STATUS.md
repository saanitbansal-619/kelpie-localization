# Project status

## Current phase

Two simulation studies. Neither is a hardware validation.

1. The hydrophone geometry study is complete and preserved. Its 9000-trial results were not rerun for the later work.
2. A separate hydrophone-count study compares 4, 5, and 6 hydrophones. Professor-facing plots of the geometry study were added from the saved CSVs.

## What is done

* Synthetic 4-channel chirp, noise, and DC offsets
* DC removal and a shared zero-phase bandpass that preserve relative timing
* One combined-energy event index and one common multichannel window
* GCC-PHAT TDOA relative to H0, including an earlier SNR sweep on hand-set delays
* Five array geometries with coordinates stored only in `src/geometry.py`
* Geometry-derived propagation delays (`d_i / c`) used as waveform ground truth
* Nonlinear least-squares localization and direction error for volumetric arrays
* Explicit failure, with no estimated XYZ, for the linear array and both planar arrays
* 9000-trial comparison: 300 sources, SNRs 40 / 30 / 20 / 10 / 5 / 0 dB, five geometries, one shared noise seed per source and SNR
* Figures, raw CSV, and `simulations/geometry_study/PROFESSOR_SUMMARY.md`

The full study script took 291.9 s. The trial loop took 279 s.

## What the simulation actually showed

* Median absolute TDOA error at 20 dB is about 0.08–0.10 microseconds on all five geometries. The SNR curves overlap. Geometry is not distinguishable from timing error in microseconds in this run.
* Linear and planar success rates are 0/300 at every SNR, including 40 dB, because the 3D problem is degenerate. Their TDOAs are still estimated.
* Tetrahedral and three-plus-one success at 20 dB is 299/300 and 298/300. Median angular error is 0.14° and 0.17°. Median position error is 1.53 m and 1.62 m.
* Position error has a long tail (occasional errors above 100 m). The mean is larger than the median and is not the typical trial.
* Neither volumetric array is selected as the one to build. The medians agree; the tails do not tell a single story.

## Hydrophone-count study

Separate folder: `simulations/hydrophone_count_study/`. It does not write into the geometry-study results.

* 4 hydrophones: the existing tetrahedron
* 5 hydrophones: triangular bipyramid
* 6 hydrophones: regular octahedron
* Same 300 sources, same six SNRs, same 0.25 m maximum baseline, 5400 trials
* Summary and interpretation: `PROFESSOR_SUMMARY.md` in that folder
* A channel-loss test was not run

## What is not done

* Physical hydrophone or DAQ measurements
* ROS, Jetson, or any embedded integration
* Multipath, absorption, or spreading loss
* Hydrophone-coordinate error or sound-speed error
* A half-space-constrained planar solver (intentionally not added, so planar degeneracy stays visible)

## Next phase

Depends on a review of this simulation and on which shapes are practical to build.

The useful next engineering work is still simulation until hardware arrives: coordinate uncertainty, sound-speed uncertainty, and, only if operations assume the source stays on one side of a plane, a separately labeled half-space test. Hardware validation starts when synchronized recordings exist, by comparing those recordings with this direct-path prediction.
