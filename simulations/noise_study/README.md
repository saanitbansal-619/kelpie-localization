# Localization versus SNR

This folder is a **simulation**. It does not contain hardware measurements, and it does not replace the geometry study or the hydrophone-count study. Those result files are left as they are.

The question is how 3D localization error and success rate change as additive hydrophone noise gets stronger. The array, sources, waveform, sample rate, sound speed, preprocessing, GCC-PHAT settings, and solver stay fixed. The quantity that changes is the noise power.

## Why the noise is simulated

Hardware is not available, so the only way to see the noise dependence of this localizer is to add noise to the same synthetic captures the rest of the repository already uses. A single clean trial hides the failures and the long error tail that show up once the arrivals are hard to time.

## SNR

Signal-to-noise ratio is defined on the source chirp, before preprocessing:

```
SNR_dB = 10 * log10(P_signal / P_noise)
```

`P_signal` is the mean square of the chirp samples, `mean(chirp²)`. It is not the peak amplitude, and it is not the mean square of the whole capture. The capture is mostly silence; using it as the signal power would make the SNR depend on how long the recording is.

`P_noise` is solved from that definition:

```
P_noise = P_signal / 10^(SNR_dB / 10)
```

The noise is zero-mean Gaussian, so its power equals its variance. The standard deviation passed to the existing noise function is `sqrt(P_noise)`. That is the same number as `RMS(chirp) / 10^(SNR_dB / 20)`, which is the scale the earlier TDOA and geometry studies already used.

Each hydrophone gets its own noise sequence. Samples are independent across time and across channels. The noise is added to the raw delayed channels, then the existing DC offsets, DC removal, and 15–45 kHz zero-phase bandpass run unchanged. The labeled SNR is therefore the broadband ratio on the raw chirp. The bandpass removes noise outside that band, so the SNR inside the processing band is higher than the label.

A noise-free condition is separate from 0 dB. Noise-free sets the standard deviation to exactly 0, which is the existing `noise_std=0` path. 0 dB sets the noise power equal to the chirp power.

## Reproduce

From the project root:

```bash
python simulations/noise_study/run_noise_experiment.py
```

Optional overrides:

```bash
python simulations/noise_study/run_noise_experiment.py --seed 20261004 --trials 100
python simulations/noise_study/run_noise_experiment.py --skip-noise-free
python simulations/noise_study/run_noise_experiment.py --plots-only
```

Settings live in `configs/experiment.json`. Hydrophone coordinates stay in `src/geometry.py`. The default array is the existing tetrahedron: four hydrophones, edge 0.25 m. A collinear or planar array cannot return a unique 3D position, so the runner refuses those geometries rather than reporting a zero success rate that has nothing to do with noise.

## What is held constant

| Quantity | Value |
| --- | --- |
| Array | Tetrahedral, 4 hydrophones, from `src/geometry.py` |
| Trials per condition | 100 |
| Sources | One draw, seed `20261004`, reused at every SNR |
| Source region | Range 2–8 m, azimuth full circle, elevation −50° to +50° |
| SNR | Noise-free, then 30, 25, 20, 15, 10, 5, 0 dB |
| Noise seed | `random_seed + trial_index`, the same at every SNR |
| Sample rate | 256 000 Hz |
| Sound speed | 1480 m/s |
| Waveform | Existing 18–42 kHz chirp |
| DC offsets | `[0.35, -0.22, 0.18, -0.40]` |
| Preprocessing, GCC-PHAT, solver | The existing geometry-study settings |

Trial `k` uses source `k` at every SNR. The random seed for that trial does not include the SNR, and `Generator.normal` with a fixed seed scales with the requested standard deviation. The Gaussian pattern is therefore shared; only its amplitude changes. That keeps the comparison between SNR levels from mixing in a new spatial layout or a new noise shape.

The default run is 100 trials × 8 conditions = 800 localizations.

## Outputs

| File | Contents |
| --- | --- |
| `results/noise_experiment_results.csv` | One row per trial and SNR |
| `results/noise_experiment_summary.csv` | Error statistics and success rate per SNR |
| `results/source_positions.csv` | The shared source coordinates |
| `results/run_manifest.json` | Seed, trial count, and runtime |
| `figures/localization_error_vs_snr.png` | Mean localization error and ± 1 standard deviation |
| `figures/localization_error_distribution_vs_snr.png` | Box plots of localization error |
| `figures/success_rate_vs_snr.png` | Percent of trials the solver accepted |
| `figures/angular_error_vs_snr.png` | Mean angular error and ± 1 standard deviation |

The noise-free SNR cell is blank. `noise_free` is `true` on that condition. `localization_success_rate` is a fraction from 0 to 1. `1` means every trial succeeded.

A failed solve stores a blank estimated position, a blank localization error, and a blank angular error, with `success` false and a `failure_reason`. An exception inside one trial is recorded the same way. It does not stop the run. Failures are not written as zero error.

Summary error statistics use successful solves only. The sample standard deviation uses `n - 1`. RMSE is the square root of the mean of the squared errors. If a condition has no successes, those cells are blank. If it has one success, the standard deviation is blank.

## Reading the figures

Horizontal axes on the line plots are SNR in dB, with the high-SNR end on the left, so noise increases to the right. That matches the geometry-study SNR figures. The dotted horizontal line is the noise-free result: the error or success rate with the additive noise turned off. It is the floor set by sampling, the 0.25 m aperture, and the estimator.

**Localization error versus SNR.** The circles are the mean Euclidean position error of accepted solves. The dashed line is the median. The shaded band is the 25th–75th percentile. The vertical axis is logarithmic. A mean that sits above the band means a few accepted trials with very large range error are pulling the mean; the median is the typical accepted trial. The standard deviation is stored in the summary CSV and is not drawn as a bar: in this run it is larger than the mean at every SNR, so a ±1 standard-deviation interval would cross zero. The box plot shows the outliers that produce that standard deviation. The dotted line is the noise-free mean, the error already present with the additive noise turned off.

**Distribution.** Each box is the accepted localization errors at that condition. The line inside the box is the median. The whiskers follow the usual 1.5-IQR rule, and the points beyond them are the outliers the mean is sensitive to. `n` on the tick label is the number of accepted solves, not the number of trials. A condition can have a tight box and still be a poor operating point if the success-rate figure shows that many trials were rejected.

**Success rate.** This is the percentage of trials that returned a position. A rejected solve (degenerate geometry, no bounded solution, residual past the physical scale, or ambiguous local minima) is a failure. It is omitted from the error plots, so a falling success rate is easy to miss if you only read the error curves. Those curves describe the trials the solver was willing to report.

**Angular error.** This is the angle between the true direction and the estimated direction, from the array centroid, in degrees. It is not the position error. The circles, dashed line, and band are again the mean, the median, and the 25th–75th percentile of accepted solves. A small angle with a large position error means the direction is usable and the range is not, which is expected for a 0.25 m array observing sources several metres away.

## This run

100 sources, seed `20261004`, tetrahedral array. The trial loop took 20.2 s. Accepted-solve position error:

| SNR | Median (m) | Mean (m) | 95th % (m) | Success |
| --- | ---: | ---: | ---: | ---: |
| noise-free | 0.35 | 1.05 | 3.02 | 100/100 |
| 30 dB | 0.38 | 1.23 | 3.99 | 100/100 |
| 25 dB | 0.42 | 0.95 | 3.01 | 99/100 |
| 20 dB | 0.77 | 1.34 | 4.29 | 99/100 |
| 15 dB | 0.84 | 3.42 | 4.06 | 98/100 |
| 10 dB | 1.18 | 3.57 | 5.94 | 98/100 |
| 5 dB | 1.31 | 2.00 | 5.70 | 94/100 |
| 0 dB | 1.44 | 6.48 | 10.57 | 90/100 |

The median rises as SNR falls, from 0.35 m with no added noise to 1.44 m at 0 dB. The mean does not rise at every step. At 15 dB and 0 dB it is pulled up by accepted solutions whose error reaches about 190 m; those points are the open circles on the box plot. The 95th percentile stays near a few metres until 0 dB, so the typical and even the high-but-not-extreme trial degrades much less than the mean suggests.

Success stays at 100/100 with no noise and at 30 dB, then falls to 90/100 at 0 dB. The 22 rejected trials are all `no_bounded_solution`. They are missing from the error columns. Median angular error stays below 0.3° at every labeled SNR, including 0.26° at 0 dB. The mean angular error at 0 dB is 1.6° because of a few large angles. Direction estimates degrade much more slowly than range.

These figures describe this simulator and this 0.25 m tetrahedron. They are not a hardware measurement.
