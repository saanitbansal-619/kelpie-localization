# Pulsed-pinger waveform simulation

This folder is a **simulation**. It does not replace the chirp pipeline or the localization-versus-SNR study in `simulations/noise_study/`. Those results are left as they are.

The question is whether the existing localizer can recover a pinger position when the arrival times have to be estimated from sampled hydrophone waveforms. The solver never receives the geometric travel times. Those times are kept only for scoring.

```
pinger position
    → 40 kHz pulsed sinusoid
    → fractional propagation delay to each hydrophone
    → optional 1/distance attenuation
    → optional Gaussian noise
    → existing DC removal and 15–45 kHz bandpass
    → GCC-PHAT TDOA, search limited to the array baseline
    → existing nonlinear least-squares solver
    → estimated position and direction
```

## Why 40 kHz and 4 ms

40 kHz is the initial carrier, with 25, 30, and 35 kHz kept as a comparison. A 4 ms burst is the same length as the repository's existing chirp, so the 40 ms capture and the shared event window still cover the pulse. All four carriers sit inside the existing 15–45 kHz processing band. This is not a claim about a particular hardware pinger.

## Sampling rate

The sample rate is **256 kHz**, the project default (`src.simulation.DEFAULT_FS`).

Nyquist is 128 kHz, so a 40 kHz tone has 6.4 samples per cycle. 256 kHz is above the 192 kHz floor and is the rate the bandpass, event detector, and GCC-PHAT interpolation were already built around. A lower rate would be a different experiment.

## Propagation delay

Travel time is the existing geometric model, `t_i = ||p - h_i|| / c`, with `c = 1480 m/s`.

Each channel is the pulse shifted by `fs * t_i` samples. That shift is not rounded to an integer sample. `src.simulation.delay_signal` linearly interpolates between samples. Relative TDOA is still `(t_i - t_0)`, which is what GCC-PHAT is asked to recover.

## Attenuation

Optional spherical spreading multiplies channel `i` by `1 / distance_i`. The configured pulse amplitude is then the amplitude at 1 m.

The reported SNR sweep leaves attenuation **off**. With it off, the labeled SNR is the same definition as Change #1: noise power is set from the mean square of the pulse,

```
SNR_dB = 10 * log10(P_pulse / P_noise)
```

and the same noise standard deviation is added independently on every channel. Turning attenuation on would scale the received pulse down by `1/d` and make the labeled SNR no longer the SNR at the hydrophone. At these ranges the four path lengths differ by at most the 0.25 m baseline, so the relative `1/d` effect across the array is a few percent. The switch is `apply_attenuation` in `configs/experiment.json`.

## GCC-PHAT

TDOA estimation is the existing `src.tdoa.estimate_tdoas` GCC-PHAT path used by the geometry study: one shared event window, interpolation factor 16, reference H0. The lag search is limited to the maximum pairwise baseline divided by `c`, plus one sample. Peaks outside that window are not eligible.

Estimated delays are then passed to `src.localization.localize_from_tdoa`. A rejected solve is stored with a blank position and a blank localization error. It is counted as a failure.

## Reproduce

From the project root:

```bash
python simulations/waveform_study/run_waveform_experiment.py
```

The 40 kHz sweep uses the first 100 sources in `simulations/geometry_study/results/source_positions.csv`. Every SNR sees those same sources. The noise seed is `20261004 + trial_index` and does not depend on SNR, so each SNR scales one shared noise pattern.

Conditions: noise-free, 30 dB, 20 dB, 10 dB, 5 dB, 0 dB. That is 600 trials.

The carrier comparison repeats the first 25 of those sources at 25, 30, 35, and 40 kHz, noise-free and at 20 dB.

## Outputs

| File | Contents |
| --- | --- |
| `results/waveform_experiment_results.csv` | One row per 40 kHz trial |
| `results/waveform_experiment_summary.csv` | Error, TDOA error, and success rate per SNR |
| `results/waveform_frequency_comparison.csv` | The smaller carrier comparison |
| `results/waveform_frequency_summary.csv` | Summary of that comparison |
| `figures/hydrophone_waveforms.png` | Four channels of one noise-free pulse |
| `figures/gcc_phat_example.png` | Correlation peak for H1 versus H0 |
| `figures/tdoa_error_vs_snr.png` | Absolute TDOA error versus SNR |
| `figures/localization_error_vs_snr.png` | Localization error versus SNR |
| `figures/success_rate_vs_snr.png` | Success rate versus SNR |
| `figures/angular_error_vs_snr.png` | Angular error versus SNR |
| `figures/frequency_comparison.png` | Median error versus carrier |

TDOA statistics are absolute errors in microseconds, so early and late errors do not cancel. They include every finite pair. Localization and angular statistics use successful solves only.

Rows can carry sanity flags: `huge_localization_error` (accepted error above 20 m), `correlation_peak_at_boundary`, `tdoa_outside_physical_limit`, and `non_finite_tdoa`. A flag does not by itself turn a success into a failure. The error value is kept.

## Limitations

* No multipath, absorption, Doppler, or reverberation.
* The only optional propagation loss is `1/d`. It is off in the reported sweep.
* Fractional delay is linear interpolation, not a band-limited fractional-delay filter.
* A pure tone has a periodic GCC-PHAT trace. The baseline limit keeps the search inside about ±169 µs, which still contains several carrier cycles. A wrong cycle would appear as a TDOA error near one period (25 µs at 40 kHz).
* The 15–45 kHz bandpass is the existing preprocessing, not a filter tuned to one carrier.
* This is not a hardware measurement.

## Reading the figures

High SNR is on the left. The dotted line is the noise-free result. On the error plots the circles are the mean, the dashed line is the median, and the band is the 25th–75th percentile. A mean above the band means a few large errors dominate the mean.

The waveform figure is the raw noise-free capture. The lower panel is the onset, where the four copies of the same pulse are shifted by the propagation delay. The GCC-PHAT figure is the trace the estimator actually searches. The orange line is the selected peak. The dashed line is the geometric TDOA for that same source.

## This run

100 sources, seed `20261004`, elapsed 20.3 s. Localization columns use successful solves. TDOA columns are the median absolute error over every finite pair, including failed solves. A rejected solve is a failure, not a zero error.

| Condition | Mean (m) | Median (m) | 95th (m) | RMSE (m) | Median \|TDOA\| (µs) | Median angle (deg) | Success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| noise-free | 3.007 | 0.498 | 3.593 | 19.310 | 0.071 | 0.059 | 99% |
| 30 dB | 4.902 | 0.626 | 4.533 | 26.785 | 0.075 | 0.066 | 99% |
| 20 dB | 6.678 | 1.819 | 7.124 | 27.801 | 0.155 | 0.180 | 82% |
| 10 dB | 15.052 | 4.855 | 84.738 | 43.584 | 24.829 | 16.986 | 62% |
| 5 dB | 9.173 | 4.777 | 22.293 | 24.746 | 26.587 | 33.747 | 68% |
| 0 dB | 16.589 | 5.275 | 121.741 | 45.236 | 70.136 | 62.930 | 68% |

One sample at 256 kHz is 3.906 µs. One 40 kHz period is 25 µs. Noise-free and 30 dB median TDOA error is about 0.07 µs, so the waveform estimate matches the geometric TDOA when the pulse is clean. At 10 dB the median jumps to 24.8 µs, one carrier period. At 0 dB it is 70 µs, about three periods. The GCC-PHAT trace of a tone has a peak every cycle, and the baseline window still contains several of them.

The representative noise-free example, source `[2, 1, 1.5]` m, selected a peak at 113.53 µs against a geometric TDOA of 113.57 µs.

Success is not monotonic: 5 dB and 0 dB both succeed on 68 of 100 trials, while 10 dB succeeds on 62. Every recorded failure is `no_bounded_solution`. On the 600-trial sweep the sanity flags are 1 noise-free huge error (>20 m), then more at lower SNR: 19 huge localization errors, 22 TDOA estimates outside the physical baseline limit, and 4 correlation peaks on the search boundary. Those rows stay in the CSV with their flags. They are not rewritten as zero error.

Carrier comparison, first 25 of the same sources:

| Carrier | Noise-free median \|TDOA\| (µs) | Noise-free median error (m) | 20 dB median \|TDOA\| (µs) | 20 dB median error (m) | 20 dB success |
| --- | ---: | ---: | ---: | ---: | ---: |
| 25 kHz | 0.054 | 0.258 | 0.129 | 0.862 | 96% |
| 30 kHz | 0.054 | 0.258 | 0.098 | 0.663 | 100% |
| 35 kHz | 0.063 | 0.421 | 0.102 | 0.732 | 84% |
| 40 kHz | 0.067 | 0.421 | 0.172 | 2.793 | 72% |

Noise-free, the four carriers are close. At 20 dB on this 25-source subset, 25 and 30 kHz keep sub-microsecond median TDOA error and higher success than 40 kHz. The 100-trial 40 kHz result at 20 dB is the more stable number for that carrier: 82% success and 1.82 m median position error. The 40 kHz tone also sits 5 kHz below the existing 45 kHz bandpass cutoff, while 25 kHz sits in the middle of the band.
