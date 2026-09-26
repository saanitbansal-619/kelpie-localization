# Hydrophone Geometry Simulation Study

This document describes a **simulation**. None of the numbers below are hardware measurements.

## 1. Objective

The question is how four-hydrophone array geometry affects TDOA observability and acoustic source localization.

Five arrays were given the same sources, the same waveform, the same noise draws, the same preprocessing, the same GCC-PHAT estimator, and the same localization solver. The hydrophone coordinates changed. The study does not adjust any configuration after the fact to favor one shape.

## 2. Current System

The simulated chain is the repository pipeline:

4 hydrophones
→ synchronized synthetic channels
→ DC removal and a shared zero-phase bandpass
→ one combined-energy event index
→ one common multichannel window
→ GCC-PHAT
→ TDOA relative to H0
→ nonlinear least squares for source position, then direction from the array centroid

There is no ROS node, Jetson process, or hydrophone front-end in this run.

## 3. Physics

For a source at `p` and hydrophone `h_i`, with sound speed `c = 1480 m/s`:

```
d_i = ||p - h_i||
t_i = d_i / c
Δt_i0 = (d_i - d_0) / c
```

`Δt_i0` is the ground-truth TDOA. H0 is exactly 0 by that definition. A negative value means hydrophone i is closer to the source than H0.

The waveform generator delays channel i by `fs * Δt_i0` samples. Those delays are the path differences, not hand-picked integers. GCC-PHAT then estimates the same differences from the waveforms. The estimate is never copied back and treated as truth.

At `fs = 256000 Hz` the sample period is `3.90625 microseconds`, and sound travels `5.78125 mm` in one sample. The largest hydrophone separation in every array below is `0.25 m`, so the largest physically possible pairwise TDOA is `d/c = 168.92 microseconds`. Every geometry-derived TDOA in the 9000-trial table stays inside that bound (`results/geometry_physical_bounds.csv`).

## 4. Five Array Geometries

Coordinates are defined once, in `src/geometry.py`, and written to `results/hydrophone_coordinates.csv`. All five arrays are centered at the origin. Each has a maximum hydrophone separation of 0.25 m. Figures use the same ±0.20 m axes.

| Geometry | Class | What it is |
| --- | --- | --- |
| Linear | collinear | H0–H3 equally spaced on the X axis from −0.125 m to +0.125 m |
| Square planar | coplanar | Corners of a square in the XY plane. Diagonal 0.25 m. All z = 0 |
| Cross planar | coplanar | ±0.125 m on X and ±0.075 m on Y, all z = 0. Unequal arms, so this is not the square rotated by 45° |
| Tetrahedral | volumetric | Regular tetrahedron, edge 0.25 m |
| Three plus one | volumetric | Equilateral triangle of side 0.25 m, plus one hydrophone 0.15 m above the triangle centroid, then shifted so the four-phone centroid is the origin |

Figures: `figures/geometries/01_linear.png` through `05_three_plus_one.png`, and `figures/geometries/all_geometries_comparison.png`.

## 5. Simulation Method

Held constant:

* 300 source coordinates, seed `20260926`, reused for every geometry
* range uniform from 2 m to 8 m, azimuth uniform on a full circle, elevation uniform from −50° to +50° (not uniform in volume or solid angle)
* chirp 18 kHz → 42 kHz, about 4 ms
* sample rate 256 kHz, sound speed 1480 m/s
* SNR levels 40, 30, 20, 10, 5, and 0 dB
* the same noise seed for a given source and SNR on every geometry
* the same DC offsets
* the same bandpass, common window, GCC-PHAT settings, and solver

Changed: hydrophone XYZ only.

Trial count: 300 sources × 6 SNRs × 5 geometries = **9000** waveform trials. A separate representative source at `(2.0, 1.0, 1.5)` m and 30 dB is used only for the explanation figures. It is not inside the 9000-row summary.

The full script took **291.9 s**. The 9000-trial loop itself took **279 s**.

## 6. Signal Processing

Each trial builds four channels from the existing chirp, delayed by the geometry TDOAs, then adds Gaussian noise and the shared DC offsets. Noise standard deviation is `RMS(chirp) / 10^(SNR/20)`, the same definition as the earlier SNR experiment.

Preprocessing subtracts each channel mean and applies one zero-phase Butterworth bandpass (15–45 kHz, order 4) to every channel. Channels are not shifted into alignment. Detection uses one combined-energy index. The window is 1024 samples before that index and 1536 after, copied from all four channels.

GCC-PHAT uses H0 as the reference and an interpolation factor of 16. The lag search is limited to the array's maximum baseline travel time plus one sample. Interpolation refines the peak location on the correlation grid. It does not increase the ADC bandwidth.

The primary waveform is the chirp, not a pure sine.

## 7. Localization

The solver fits `p` in

```
Δt_i0 = (||p - h_i|| - ||p - h_0||) / c
```

with SciPy nonlinear least squares, started from several ranges along a far-field direction and from the coordinate axes. The reported direction is the direction from the array centroid to that position. Angular error is the angle between the true and estimated direction vectors. It is not the position error.

Before the fit, the centered hydrophone coordinates are classified by singular-value rank.

* **Collinear** (the linear array): TDOAs are unchanged by rotation about the array axis. A unique 3D position is not observable. The solver returns no position. Failure reason: `geometric_degeneracy_collinear`.
* **Coplanar** (square and cross): TDOAs are unchanged if the source is reflected through the plane. A unique 3D position is not observable. No half-space constraint is applied. Failure reason: `geometric_degeneracy_coplanar`.
* **Volumetric** (tetrahedral and three plus one): the fit is attempted. Success means a finite position inside a 200 m guard, with no second low-residual solution pointing more than 20° away. A large position error can still be a success. The few volumetric failures in this run are `no_bounded_solution`: the iterates did not stay inside that guard. They are not recorded as zero error.

## 8. Experiments

1. **Representative source.** Geometry-only path lengths and travel times, then waveforms and GCC-PHAT at 30 dB. Tables: `results/propagation_ground_truth.csv`, `results/representative_tdoa.csv`.
2. **Multi-source factorial.** The 300 sources at all six SNRs, all five geometries. Raw rows: `results/experiment_results.csv`.
3. **Summary.** One row per geometry and SNR: `results/geometry_summary.csv`.

Distribution plots in section 9 use **20 dB** unless the figure is explicitly versus SNR. The line inside each box is the **median**. Outliers are drawn. On the SNR curves, the solid line is the median and the dashed line is the 95th percentile.

## 9. Results

### Representative source, 30 dB

GCC-PHAT absolute errors on `(2.0, 1.0, 1.5)` m, in microseconds:

| Geometry | H1−H0 | H2−H0 | H3−H0 |
| --- | ---: | ---: | ---: |
| Linear | 0.149 | 0.076 | 0.079 |
| Square planar | 0.092 | 0.030 | 0.025 |
| Cross planar | 0.082 | 0.165 | 0.051 |
| Tetrahedral | 0.048 | 0.097 | 0.044 |
| Three plus one | 0.158 | 0.134 | 0.047 |

All fifteen pairs are under 0.17 microseconds. That is one example, not the statistical result.

### TDOA error

At 20 dB, median absolute TDOA error over the three non-reference pairs (900 pair-errors per geometry):

| Geometry | Median (us) | Mean (us) | 95th percentile (us) |
| --- | ---: | ---: | ---: |
| Linear | 0.094 | 0.111 | 0.261 |
| Square planar | 0.097 | 0.112 | 0.268 |
| Cross planar | 0.097 | 0.109 | 0.252 |
| Tetrahedral | 0.083 | 0.102 | 0.256 |
| Three plus one | 0.093 | 0.108 | 0.266 |

The largest pair error at 20 dB, on any geometry, is 0.47 microseconds. No pair exceeds 5 microseconds.

Across SNR, the five median curves and the five 95th-percentile curves lie on top of each other (`figures/comparisons/tdoa_error_vs_snr.png`). Median absolute error is about 0.06 microseconds at 40 dB and about 0.29–0.32 microseconds at 0 dB.

At 0 dB the **mean** rises to between 1.77 and 2.48 microseconds even though the median stays near 0.3. About 2% of pairs have absolute error greater than 5 microseconds, and the largest pair errors are 164 microseconds (linear) to 310 microseconds (tetrahedral). Those are wrong correlation peaks inside the search window. The mean is not the typical trial. The median and the 95th percentile (0.94–0.99 microseconds at 0 dB) describe the bulk; the maximum describes the tail. The tail is not removed from the scatter plot.

**What this supports:** under matched SNR, this experiment does not separate the five geometries by GCC-PHAT error in microseconds. Timing error here is set by the waveform, the sample rate, and the noise, not by which of these 0.25 m shapes is used.

**What this does not support:** a ranking of the arrays by TDOA accuracy. The medians differ by a few hundredths of a microsecond, which is a small fraction of the 3.91 microsecond sample period.

At 20 dB, median TDOA error stays between about 0.07 and 0.11 microseconds from 2 m to 8 m (`figures/comparisons/error_vs_source_distance.png`). There is no strong monotonic trend with range in that figure.

### Localization success

| Geometry | 40 dB | 20 dB | 0 dB | Failure reason |
| --- | ---: | ---: | ---: | --- |
| Linear | 0/300 | 0/300 | 0/300 | `geometric_degeneracy_collinear` on every trial |
| Square planar | 0/300 | 0/300 | 0/300 | `geometric_degeneracy_coplanar` on every trial |
| Cross planar | 0/300 | 0/300 | 0/300 | `geometric_degeneracy_coplanar` on every trial |
| Tetrahedral | 300/300 | 299/300 | 286/300 | the misses are `no_bounded_solution` |
| Three plus one | 299/300 | 298/300 | 277/300 | the misses are `no_bounded_solution` |

The linear and planar rates are zero at 40 dB as well as at 0 dB. That is the geometry classification, not a noise outage. Their GCC-PHAT TDOAs are still computed and are included in the TDOA table above.

Volumetric failures increase as SNR falls: 1 and 2 trials at 20 dB, 14 and 23 trials at 0 dB. Angular and position statistics below skip those trials. They are not filled with zero.

### Direction and position, volumetric arrays only

At 20 dB, successful solves only:

| Geometry | Solved | Median angular (deg) | Upper quartile (deg) | Mean angular (deg) | 95th percentile (deg) | Median position (m) | Mean position (m) | 95th percentile (m) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tetrahedral | 299 | 0.14 | 3.27 | 1.83 | 7.15 | 1.53 | 3.74 | 6.95 |
| Three plus one | 298 | 0.17 | 1.51 | 1.09 | 4.62 | 1.62 | 3.01 | 6.80 |

The medians of angular error are both a fraction of a degree. The tetrahedral upper quartile is wider (3.27° versus 1.51°) in this source set. The position medians are both about 1.5–1.6 m. Both geometries also produce rare position errors above 100 m (maximum 177 m and 150 m at 20 dB). Those outliers are why the mean sits above the median. They are plotted, on a logarithmic axis, in `figures/comparisons/position_error_by_geometry.png`.

At 0 dB the median angular errors are 0.46° (tetrahedral) and 0.53° (three plus one). The 95th percentiles are 7.4° and 5.9°. A few successful solves are far worse than that percentile: the maximum angular errors among successes are 132° and 119°. Median position error is 2.83 m and 2.48 m. The 95th percentiles are 7.8 m and 14.3 m.

**What this supports:**

* A collinear or planar four-phone array does not determine a unique 3D source from TDOAs alone. Forcing a point would have hidden that.
* Both non-coplanar arrays usually return a direction. For most trials the angular error is well under a degree, including at 0 dB, while a minority of trials are several degrees off and a few are badly wrong.
* Position error is typically metres on a 0.25 m array with sources 2–8 m away. Direction error and position error are not interchangeable. Range is weakly constrained by wavefront curvature at this baseline.

**What this does not support:** naming either volumetric array the better geometry. The median angular errors agree. The tetrahedral angular tail is heavier at 20 dB. The three-plus-one array has more `no_bounded_solution` failures at 5 dB and 0 dB, and a heavier position-error 95th percentile at 0 dB. Those are different tails, not a single ranking.

No half-space prior was used. This run therefore does not say whether a planar array would be usable if the vehicle could assume the source stays on one side of the plane. It says that, without that assumption, the planar TDOA problem is not a unique 3D fix.

## 10. Key Figures

| Figure | What it shows |
| --- | --- |
| `figures/geometries/all_geometries_comparison.png` | All five arrays on identical ±0.20 m axes |
| `figures/propagation/04_tetrahedral.png` (and the other four) | Source, hydrophones, and path lines for `(2, 1, 1.5)` m |
| `figures/waveforms/01_linear.png` | Four channels in one window; the leading edge is not aligned |
| `figures/gcc_phat/04_tetrahedral.png` | Lag in microseconds, true TDOA and estimated peak |
| `figures/tdoa/true_vs_estimated_tdoa.png` | All geometries and SNRs against the line y = x, outliers included |
| `figures/comparisons/tdoa_error_by_geometry.png` | Median absolute TDOA error at 20 dB |
| `figures/comparisons/tdoa_error_vs_snr.png` | Median and 95th percentile versus SNR |
| `figures/comparisons/angular_error_by_geometry.png` | Direction error where a solve exists; degenerate arrays marked not observable |
| `figures/comparisons/position_error_by_geometry.png` | Position error on a log axis, outliers kept |
| `figures/comparisons/localization_error_vs_snr.png` | Median and 95th percentile for the two volumetric arrays |
| `figures/comparisons/solver_success_by_geometry.png` | Success rate; linear and planar are 0 at every SNR |
| `figures/comparisons/error_vs_source_distance.png` | Median error in 1 m range bins at 20 dB |
| `figures/localization/04_tetrahedral.png` | XY projection of the 3D sources, colored by angular error. Not an interpolated map |
| `figures/localization/01_linear.png` | Same sources, uncolored, because no unique 3D solution was reported |

## 11. Limitations

* Synthetic data only. These are not hydrophone recordings.
* Sound speed is a constant 1480 m/s. There is no temperature, salinity, or depth profile.
* No multipath or surface/bottom reflection model.
* No spreading loss or absorption. Every channel has the same chirp amplitude; only the delay changes.
* No hydrophone or DAQ hardware, and no check against a physical array.
* Hydrophone coordinates are treated as exact.
* Channels are treated as perfectly synchronized.
* Noise is independent Gaussian noise. It is not ocean ambient noise.
* The nonlinear solver can miss, or can return a bounded but poor position. Success is not accuracy. A 200 m guard rejects exploded iterates; it is not a physical prior.
* Linear and planar arrays are degenerate for unique 3D localization. A later half-space assumption would be a different experiment and would need to be labeled as such.
* The sample period is 3.91 microseconds. GCC-PHAT interpolation does not create new bandwidth above the original Nyquist frequency.
* Sources are uniform in radius, azimuth, and elevation angle, not uniform in volume or solid angle.
* The 0 dB mean is dominated by a small fraction of bad peaks. Report the median and the tail together.

## 12. Next Steps

* Review this simulation with the professor before choosing a build.
* Decide which non-coplanar layouts are physically buildable. The median direction errors of the tetrahedron and the three-plus-one array do not, by themselves, make that choice.
* If a planar array is still of interest, test it again under an explicit, documented half-space assumption. Do not present that constrained result as a unique 3D solution.
* Add hydrophone-coordinate error. This run assumes the XYZ values are perfect.
* Add sound-speed error.
* Add a multipath model only when it can be stated clearly, and keep it separate from this direct-path table.
* When synchronized hydrophone hardware exists, compare these predictions with measurements. Until then, do not describe this study as a hardware validation.
