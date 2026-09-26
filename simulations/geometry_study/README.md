# Hydrophone geometry simulation study

This folder is a **simulation** study. It does not contain hardware measurements.

The question is how four-hydrophone array geometry affects TDOA observability and acoustic source localization. Five geometries are compared under the same source positions, waveform, sample rate, sound speed, SNR levels, preprocessing, GCC-PHAT settings, localization solver, and trial count. The quantity that changes is the hydrophone XYZ coordinates.

Signal-processing code is not copied here. The study imports `src.simulation`, `src.preprocessing`, `src.detection`, `src.tdoa`, `src.geometry`, and `src.localization`.

## Reproduce

From the project root, with the virtual environment activated and dependencies installed:

```bash
python simulations/geometry_study/run_geometry_study.py
```

To rebuild figures from an existing Monte Carlo table without repeating the 9 000 waveform trials:

```bash
python simulations/geometry_study/run_geometry_study.py --plots-only
```

Professor-facing figures that explain the saved results, without repeating the Monte Carlo, are in `figures/professor/`. Generate them with:

```bash
python simulations/geometry_study/make_professor_figures.py
```

That script only reads the result CSVs and writes under `figures/professor/`. It does not replace the CSVs, the run manifest, or the earlier comparison figures.

Settings are in `configs/experiment.json`. Hydrophone coordinates are defined only in `src/geometry.py`.

The full script, including figures, took 291.9 s on the run recorded in `results/run_manifest.json`. The 9000-trial loop itself took 279 s. Rebuilding figures from the saved CSV (`--plots-only`) took 12.2 s and does not replace that timing.

## What is held constant

| Quantity | Value |
| --- | --- |
| Sample rate | 256 000 Hz (`src.simulation.DEFAULT_FS`) |
| Sound speed | 1480 m/s |
| Waveform | Existing 18–42 kHz chirp, about 4 ms, Tukey taper |
| Capture | 40 ms, event placed at 15 ms on the H0 delay |
| Noise | Gaussian, `noise_std = RMS(chirp) / 10^(SNR/20)`, same seed for every geometry |
| DC offsets | `[0.35, -0.22, 0.18, -0.40]` on H0–H3 |
| Preprocessing | Per-channel mean removal, then the same zero-phase 15–45 kHz Butterworth |
| Event window | One shared index, 1024 samples before and 1536 after |
| TDOA | GCC-PHAT, interpolation factor 16, reference H0 |
| Localization | Nonlinear least squares on the TDOA model, same initial-guess set |
| Sources | One deterministic draw, seed `20260926` |

Channel delays in the waveform generator are `fs * (d_i - d_0) / c`. They are not hand-picked sample shifts. A negative delay is an earlier arrival. The 15 ms lead-in keeps those shifts inside the capture, so no extra common offset is added.

## Source region

300 sources, used for every geometry and every SNR:

* range uniform from 2 m to 8 m (not uniform in volume)
* azimuth uniform on a full circle
* elevation uniform from −50° to +50° (not uniform in solid angle)

The closest source-to-hydrophone distance is above 1 m. The same coordinates are stored in `results/source_positions.csv`.

SNR levels, in dB: 40, 30, 20, 10, 5, 0.

Total waveform trials: 300 × 6 × 5 = 9000.

An additional representative source at `(2.0, 1.0, 1.5)` m and 30 dB SNR is used only for the propagation, waveform, and GCC-PHAT explanation figures. It is not mixed into the summary statistics.

## Outputs

### Results

| File | Contents |
| --- | --- |
| `results/hydrophone_coordinates.csv` | H0–H3 coordinates for each geometry |
| `results/sampling_sanity.csv` | Sample period, millimetres per sample, 0.25 m transit time |
| `results/propagation_ground_truth.csv` | Path length, travel time, and true TDOA for the representative source |
| `results/representative_tdoa.csv` | GCC-PHAT versus geometry TDOA for that source |
| `results/source_positions.csv` | The 300 shared source coordinates |
| `results/experiment_results.csv` | One row per geometry, source, and SNR |
| `results/geometry_summary.csv` | Error statistics and success rate by geometry and SNR |
| `results/geometry_physical_bounds.csv` | Actual maximum baseline and maximum pairwise TDOA |
| `results/run_manifest.json` | Trial count and measured runtime |

`geometry_summary.csv` has one row per geometry and SNR. TDOA statistics use the three non-reference pairs. Angular and position statistics use successful localizations only. If none succeeded, those cells are `nan`. Failures are not entered as zero error.

### Figures

| Path | What it shows |
| --- | --- |
| `figures/geometries/01_linear.png` through `05_three_plus_one.png` | Each array, identical ±0.20 m axes |
| `figures/geometries/all_geometries_comparison.png` | All five arrays on that same scale |
| `figures/propagation/` | Representative source, hydrophones, and path lines |
| `figures/waveforms/` | Four preprocessed channels in one common window |
| `figures/gcc_phat/` | GCC-PHAT lag in microseconds, true TDOA and estimated peak |
| `figures/tdoa/true_vs_estimated_tdoa.png` | All geometries, with the line y = x |
| `figures/comparisons/` | TDOA error, angular error, position error, success rate, error versus distance and SNR |
| `figures/localization/` | XY projection of the 3D source set at 20 dB |

Comparison box plots that show a distribution use the **median** as the line inside the box. Outliers are drawn. The 20 dB SNR is the distribution comparison; the SNR figures use every noise level. Solid lines there are medians and dashed lines are 95th percentiles.

## Geometries

All five are centered at the origin. Each has a maximum hydrophone separation of 0.25 m. Exact coordinates are in `src/geometry.py` and `results/hydrophone_coordinates.csv`.

1. **Linear** — equal spacing on the X axis from −0.125 m to +0.125 m. Collinear.
2. **Square planar** — square in the XY plane, diagonal 0.25 m, z = 0.
3. **Cross planar** — ±0.125 m on X and ±0.075 m on Y, z = 0. The arms are unequal so this is not a 45° rotation of the square. Still planar.
4. **Tetrahedral** — regular tetrahedron, edge 0.25 m.
5. **Three plus one** — equilateral triangle of side 0.25 m with a fourth hydrophone 0.15 m above the triangle centroid, then shifted so the four-phone centroid is the origin.

Linear and planar arrays are reported as localization failures. The solver does not apply a half-space constraint to turn the reflection ambiguity into an apparently unique 3D point.

## Reading the numbers

True TDOAs come from path length. Estimated TDOAs come from GCC-PHAT. Localization uses the estimates and the known coordinates. Error is estimated minus ground truth. Estimated values are never used as ground truth.
