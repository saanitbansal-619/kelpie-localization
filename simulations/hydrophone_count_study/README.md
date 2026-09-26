# Hydrophone-count simulation study

This folder is a **simulation**. It is not a hardware measurement, and it does not replace the geometry study.

The question is whether five or six hydrophones improve 3D localization relative to four when the physical envelope, sources, waveform, sample rate, sound speed, noise seeds, preprocessing, GCC-PHAT, and localizer are held the same. The quantity that changes is the number of sensors.

## Reproduce

From the project root:

```bash
python simulations/hydrophone_count_study/run_hydrophone_count_study.py
```

Settings are in `configs/experiment.json`. Coordinates are defined only in `src/hydrophone_counts.py`. The four-hydrophone array is the existing tetrahedron from `src/geometry.py`. Source positions are read from `simulations/geometry_study/results/source_positions.csv` and are not modified.

Results are written only under this folder's `results/` and `figures/`.

## What is held constant

| Quantity | Value |
| --- | --- |
| Sources | The geometry study's 300 positions |
| SNR | 40, 30, 20, 10, 5, 0 dB |
| Sample rate | 256 000 Hz |
| Sound speed | 1480 m/s |
| Waveform | The existing 18–42 kHz chirp |
| Noise seed | `1_000_000 + source_id * 100 + round(snr_db * 10)` |
| Noise draw | Leading rows of one 6-channel Gaussian sequence, so H0–H3 share noise across the three arrays |
| DC offsets | `[0.35, -0.22, 0.18, -0.40]` on H0–H3, then `0.27` and `-0.15` |
| Preprocessing | Per-channel mean removal, then the same zero-phase 15–45 kHz Butterworth |
| Event window | One shared index, 1024 samples before and 1536 after |
| TDOA | GCC-PHAT, interpolation 16, reference H0 |
| Localization | The existing nonlinear least squares solver |

## Sensor count and equations

H0 is the reference. The solver uses `N - 1` reference TDOAs: 3, 4, and 5 for the three arrays. For `N > 4` that is an overdetermined least-squares problem.

Unordered pairs are a different count: 6, 10, and 15. Those pairs are not independent equations, and this study does not claim that they are. The primary solver does not switch to an all-pairs formulation.

## Envelope

Each array is volumetric and centered at the origin. The maximum pairwise baseline of each array is 0.25 m. The five- and six-hydrophone arrays are not given a longer baseline than the tetrahedron. The actual baselines are stored in `results/hydrophone_coordinates.csv` and `results/run_manifest.json`.

Maximum physical pairwise TDOA is `max_baseline / c`.

## Metrics

A failed solve is stored as missing position and angular error, with `solver_success` false. Failures are not converted to zero error. Summary statistics for angle and position use successful solves only. TDOA error uses every finite reference pair.

The primary comparison SNR is 20 dB. Percent change in an error is `(new - baseline) / baseline * 100`. A negative value is a smaller error. Success is compared in percentage points.

## Not in this run

A secondary test that removes one channel from the six-hydrophone array was not run. It is future work.
