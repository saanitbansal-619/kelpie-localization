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

## Localization versus SNR

Separate folder: `simulations/noise_study/`. It does not write into the geometry-study or hydrophone-count results.

* Array: the existing 4-hydrophone tetrahedron
* Same waveform, preprocessing, GCC-PHAT, and solver as the geometry study
* SNR from chirp power: `P_noise = P_signal / 10^(SNR_dB / 10)`, independent Gaussian noise on each channel
* Levels: noise-free, then 30, 25, 20, 15, 10, 5, 0 dB
* 100 shared sources and one shared noise pattern per source, scaled to each SNR
* Trial table, summary, and figures are under that folder
* On the recorded 100-source run, median position error rose from 0.35 m with no added noise to 1.44 m at 0 dB. Success fell from 100/100 to 90/100. The mean is larger than the median because a few accepted ranges are tens or hundreds of metres off. Median angular error stayed below 0.3°.

## Pulsed-pinger waveforms

Separate folder: `simulations/waveform_study/`. It does not write into the noise-study, geometry-study, or hydrophone-count results.

* Array and sources: the existing tetrahedron and the first 100 geometry-study sources
* Signal: 40 kHz pulsed sinusoid, 4 ms, sampled at 256 kHz. A smaller comparison uses 25, 30, 35, and 40 kHz
* Arrival time is `distance / 1480`, applied with fractional-sample interpolation. The solver receives GCC-PHAT delays, not the geometric times
* Optional `1/distance` attenuation is implemented and left off, so the SNR label matches the noise study
* On the recorded 100-source, 40 kHz run, noise-free median position error is 0.50 m and median absolute TDOA error is 0.071 µs, with 99/100 successes. At 0 dB those medians are 5.27 m and 70 µs, with 68/100 successes. Below 20 dB the typical TDOA error jumps by about one 40 kHz period
* Noise-free carrier comparison is similar from 25 to 40 kHz. At 20 dB, on 25 sources, 25 and 30 kHz kept higher success than 40 kHz

## Tetrahedral versus 3+1

Separate output tree: `results/`. The original noise-study and waveform-study files are unchanged.

* Both arrays have four hydrophones and a 0.25 m maximum baseline
* 3+1 is the existing equilateral triangle of side 0.25 m plus one hydrophone 0.15 m above the triangle centroid, then centered. `make_three_plus_one(-0.15)` mirrors it
* Change #1 and Change #2 each use one shared source list and one shared noise seed for both arrays
* On Change #1, the tetrahedral median position error is lower at every SNR, and it rejects fewer solves. Median angular error stays below 0.4° for both
* On Change #2, noise-free TDOA error is about 0.08 µs for both. At 10 dB and below, both show carrier-cycle TDOA errors. The tetrahedron accepts more solves; those accepts include a heavier position-error tail
* The ±50° source elevation leaves too few axis-dominant ABOVE and BELOW sources to rank those directions

## What is not done

* Physical hydrophone or DAQ measurements
* ROS, Jetson, or any embedded integration
* Multipath and absorption. Optional `1/distance` spreading exists in the waveform study and is off in the reported sweep
* Hydrophone-coordinate error or sound-speed error
* A half-space-constrained planar solver (intentionally not added, so planar degeneracy stays visible)

## Next phase

Hardware readiness and real-data integration. Hardware integration is not done.

Future work:

* Load real DAQ captures
* Hardware sanity checks on those recordings
* Real hydrophone recordings
* Experimental TDOA validation against the direct-path simulation

Simulation follow-ups that remain useful before or alongside hardware: coordinate uncertainty, sound-speed uncertainty, and, only if operations assume the source stays on one side of a plane, a separately labeled half-space test.
