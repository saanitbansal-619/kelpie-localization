# Effect of Hydrophone Count on Underwater Acoustic Localization

This document reports a **simulation**. It is not a hardware measurement.

The geometry study under `simulations/geometry_study/` was not rerun and its result files were not modified.

## Question

Would using five or six hydrophones instead of four improve localization?

## Experimental Design

Sensor count is the primary variable. The following were held the same for 4, 5, and 6 hydrophones:

- the geometry study's 300 source positions, read from `simulations/geometry_study/results/source_positions.csv`
- six SNR levels: 40, 30, 20, 10, 5, and 0 dB
- the existing chirp waveform
- sample rate 256 000 Hz
- sound speed 1480 m/s
- a maximum pairwise baseline of 0.25 m
- the same preprocessing, GCC-PHAT settings, and nonlinear least-squares localizer
- matched noise: for each source and SNR, one six-channel Gaussian draw is generated from the shared seed, and each array uses that draw's leading channels

The trial count is 300 × 6 × 3 = 5400. The trial loop took 327.9 s. The primary comparison SNR is 20 dB.

Each array is volumetric and centered at the origin.

| Array | Geometry | Max pairwise baseline | Max physical TDOA (`baseline / c`) | Reference TDOAs used | Unordered pairs |
| --- | --- | --- | --- | --- | --- |
| 4 | Existing regular tetrahedron | 0.250000 m | 168.919 µs | 3 | 6 |
| 5 | Triangular bipyramid | 0.250000 m | 168.919 µs | 4 | 10 |
| 6 | Regular octahedron | 0.250000 m | 168.919 µs | 5 | 15 |

Unordered pairs are not independent equations. The solver uses only the H0-referenced TDOAs. For five and six hydrophones that system is overdetermined.

At 256 000 Hz the sample period is 3.90625 µs, and at 1480 m/s sound travels 5.78125 mm per sample.

## Why Four Hydrophones?

With H0 as the reference, four hydrophones provide three reference TDOAs. The current 3D formulation estimates three spatial coordinates from those three delays, subject to geometry, ambiguity, and conditioning. Four is the smallest count for which this solver attempts a unique volumetric fix. Fewer than four is reported as underdetermined.

## Why Additional Hydrophones May Help

A fifth or sixth hydrophone adds a redundant reference TDOA. The localization problem becomes overdetermined least squares. A bad delay on one pair can be pulled toward the delays that still agree, which can reduce noise sensitivity.

## Why Additional Hydrophones May Not Always Help

Array shape still matters. The extra delays are measurements of one source through one noise field, so they are correlated; they are not five or fifteen independent looks. More channels add hydrophones, analog front ends, synchronized converters, wiring, calibration, and mechanical space. The gain from the fifth sensor need not repeat for the sixth.

## Results

Successful solves only are included in the angular and position statistics. Failures stay missing. They are not entered as zero error. TDOA error pools every finite H0-referenced pair.

### 20 dB

| Hydrophones | Trials | Median \|TDOA\| (µs) | 95th \|TDOA\| (µs) | Median angle (deg) | 95th angle (deg) | Median position (m) | 95th position (m) | Success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 300 | 0.083 | 0.256 | 0.139 | 7.15 | 1.53 | 6.95 | 299/300 (99.7%) |
| 5 | 300 | 0.094 | 0.269 | 0.077 | 0.205 | 0.551 | 3.91 | 298/300 (99.3%) |
| 6 | 300 | 0.094 | 0.267 | 0.065 | 0.147 | 0.491 | 3.56 | 300/300 (100%) |

### 0 dB

| Hydrophones | Median \|TDOA\| (µs) | Median angle (deg) | 95th angle (deg) | Median position (m) | 95th position (m) | Failures |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 0.314 | 0.462 | 7.42 | 2.83 | 7.82 | 14 |
| 5 | 0.308 | 0.258 | 0.649 | 1.79 | 32.2 | 17 |
| 6 | 0.295 | 0.207 | 0.482 | 1.33 | 16.5 | 15 |

Per-pair TDOA error barely changes with sensor count. The localization change comes from having more reference delays in the fit, not from a more accurate clock on each pair.

### Change at 20 dB

Percent change in an error is `(new − baseline) / baseline × 100`. A negative number is a smaller error. Success is in percentage points. No significance test was run.

| Comparison | Median angular error | Median position error | Success rate |
| --- | --- | --- | --- |
| 5 versus 4 | −44.9% | −64.1% | −0.33 percentage points |
| 6 versus 4 | −53.3% | −68.0% | +0.33 percentage points |
| 6 versus 5 | −15.2% | −10.9% | +0.67 percentage points |

## Main Figures

- `figures/arrays/4_hydrophones.png`
- `figures/arrays/5_hydrophones.png`
- `figures/arrays/6_hydrophones.png`
- `figures/arrays/4_vs_5_vs_6_arrays.png`
- `figures/localization/localization_error_vs_hydrophone_count.png`
- `figures/localization/angular_error_vs_hydrophone_count.png`
- `figures/localization/position_error_vs_hydrophone_count.png`
- `figures/localization/success_rate_vs_hydrophone_count.png`
- `figures/comparisons/angular_error_vs_snr.png`
- `figures/comparisons/position_error_vs_snr.png`
- `figures/tdoa/tdoa_error_vs_snr.png`
- `figures/comparisons/success_rate_vs_snr.png`

Tables: `results/hydrophone_count_summary.csv`, `results/count_comparison_summary.csv`, and `results/run_manifest.json`.

## Interpretation

At 20 dB, five hydrophones reduced the median angular error and the median position error relative to four. Six hydrophones also reduced both medians relative to four. Most of that median reduction is already present at five hydrophones. Going from five to six trims the medians further, by about 15% in angle and 11% in range, which is a smaller step than four to five.

The four-hydrophone angular distribution is wide: the median is 0.14°, but the upper quartile is 3.27° and the 95th percentile stays near 7° at every SNR. Five and six hydrophones pull that 95th percentile below 0.3° at 20 dB. That tail, more than the median, is where the extra reference delay changes the result.

Localization success does not show a useful change. At 20 dB the rates are 299/300, 298/300, and 300/300. At 0 dB they are 286/300, 283/300, and 285/300. Extra sensors did not remove the failures.

At 0 dB the medians still fall as the count rises (angle 0.46°, 0.26°, 0.21°; position 2.83 m, 1.79 m, 1.33 m), and the angular 95th percentile drops sharply after four hydrophones. The position 95th percentile does not: it is 7.8 m with four hydrophones, 32 m with five, and 16 m with six. Typical trials improve in noise. The worst position errors do not.

Per-pair TDOA error is about 0.08–0.09 µs at 20 dB for all three counts, and about 0.3 µs at 0 dB. Adding hydrophones did not make each delay estimate more accurate.

## Hardware Tradeoff

A simulated reduction in error still has to be weighed against another hydrophone, another analog front-end channel, another synchronized ADC channel, wiring, calibration, mechanical integration, and a higher data rate. This simulation does not make a purchasing recommendation.

## Limitations

- The waveforms are synthetic.
- The noise is independent Gaussian sample noise, not a measured ocean or tank spectrum.
- Sound speed is a single constant, 1480 m/s.
- There is no hardware validation.
- Multipath, absorption, and spreading loss are not simulated.
- Hydrophone coordinates are treated as exact.
- Channels are treated as synchronized.
- The comparison uses one volumetric family (tetrahedron, bipyramid, octahedron) inside a 0.25 m envelope. A different shape could change the count comparison.
- The sample rate is finite (256 000 Hz).
- GCC-PHAT peak interpolation is finite (factor 16) and the search is limited to the physical baseline plus one sample.
- A channel-dropout test, such as running the six-hydrophone geometry with one channel removed, was not run. That is future work.

## Conclusion

In this simulation, five hydrophones improved median direction and median range relative to the four-hydrophone tetrahedron, under the same 0.25 m envelope and the same 300 sources. Six hydrophones improved those medians a bit more. The step from five to six is smaller than the step from four to five for both median angular error and median position error at 20 dB. Success rate stayed near 100% at 20 dB and near 95% at 0 dB for all three counts. Individual TDOA error did not improve with count. At 0 dB, extra hydrophones reduced typical position error and did not reduce the heavy position-error tail.
