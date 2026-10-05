# Tetrahedral versus 3+1

This folder runs the existing Change #1 noise study and the existing Change #2 waveform study on two arrays. The trial code is still `simulations/noise_study` and `simulations/waveform_study`. Only the hydrophone coordinates change.

The original result files stay where they are:

* `simulations/noise_study/results/`
* `simulations/waveform_study/results/`

New runs are written under `results/tetrahedral/`, `results/three_plus_one/`, and `results/geometry_comparison/`.

## Coordinates

Channels are stored as H0, H1, H2, H3. Those are the requested H1, H2, H3, H4 in that order. Both arrays are centered at the origin. The maximum hydrophone spacing is 0.25 m for both. Sound speed is 1480 m/s.

Tetrahedron, edge 0.25 m:

| Channel | Requested | x (m) | y (m) | z (m) |
| --- | --- | ---: | ---: | ---: |
| H0 | H1 | 0.088388347648 | 0.088388347648 | 0.088388347648 |
| H1 | H2 | 0.088388347648 | -0.088388347648 | -0.088388347648 |
| H2 | H3 | -0.088388347648 | 0.088388347648 | -0.088388347648 |
| H3 | H4 | -0.088388347648 | -0.088388347648 | 0.088388347648 |

3+1. H0, H1, and H2 are an equilateral triangle of side 0.25 m. Before centering, H3 is 0.15 m above the triangle centroid (`z_offset = +0.15`). After the four-phone centroid is moved to the origin, the triangle lies at z = -0.0375 m and H3 is at z = 0.1125 m, still 0.15 m above that plane.

| Channel | Requested | x (m) | y (m) | z (m) |
| --- | --- | ---: | ---: | ---: |
| H0 | H1 | 0.144337567297 | 0.000000000000 | -0.037500000000 |
| H1 | H2 | -0.072168783649 | 0.125000000000 | -0.037500000000 |
| H2 | H3 | -0.072168783649 | -0.125000000000 | -0.037500000000 |
| H3 | H4 | 0.000000000000 | 0.000000000000 | 0.112500000000 |

`make_three_plus_one(-0.15)` mirrors every z coordinate. The reported comparison uses the +0.15 m catalog array, which is the same geometry as `get_geometry("three_plus_one")`.

## What is held fixed

* Four hydrophones and a 0.25 m maximum baseline
* Change #1: 100 sources from `generate_source_positions`, seed 20261004, range 2–8 m, elevation -50° to 50°
* Change #2: the first 100 rows of `simulations/geometry_study/results/source_positions.csv` (first 25 for the carrier comparison)
* The same noise seed per trial, `20261004 + trial_index`, independent of geometry and SNR
* The same chirp or 40 kHz, 4 ms pulse, 256 kHz sample rate, 1480 m/s, preprocessing, GCC-PHAT, and solver

Change #2 still does not give the solver the geometric arrival times.

## Commands

From the project root:

```bash
python simulations/geometry_pair/run_change1.py --geometry tetrahedral
python simulations/geometry_pair/run_change1.py --geometry three_plus_one
python simulations/geometry_pair/run_change2.py --geometry tetrahedral
python simulations/geometry_pair/run_change2.py --geometry three_plus_one
python simulations/geometry_pair/compare.py
```

## This run

Change #1, 100 trials. Localization columns use successful solves. A rejected solve is a failure, not a zero error.

| SNR | Tetra median (m) | 3+1 median (m) | Tetra 95th (m) | 3+1 95th (m) | Tetra angle (deg) | 3+1 angle (deg) | Tetra success | 3+1 success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| noise-free | 0.347 | 0.757 | 3.024 | 6.877 | 0.057 | 0.087 | 100% | 99% |
| 30 dB | 0.382 | 0.658 | 3.988 | 6.215 | 0.060 | 0.078 | 100% | 96% |
| 25 dB | 0.424 | 0.634 | 3.010 | 13.123 | 0.065 | 0.087 | 99% | 95% |
| 20 dB | 0.771 | 0.921 | 4.294 | 14.691 | 0.093 | 0.110 | 99% | 96% |
| 15 dB | 0.835 | 1.084 | 4.056 | 9.172 | 0.110 | 0.131 | 98% | 91% |
| 10 dB | 1.178 | 1.407 | 5.939 | 10.604 | 0.140 | 0.214 | 98% | 88% |
| 5 dB | 1.309 | 1.841 | 5.696 | 12.083 | 0.183 | 0.249 | 94% | 89% |
| 0 dB | 1.444 | 2.084 | 10.571 | 19.608 | 0.258 | 0.371 | 90% | 83% |

The tetrahedral median is lower at every SNR, and it rejects fewer solves (22 versus 63, all `no_bounded_solution`). Median direction error stays below 0.4° for both. Means and RMSE are much larger than the medians. At 0 dB the means are 6.48 m and 6.40 m. The tetrahedron's RMSE is higher there because it accepts a small number of very large ranges, including one of 191 m. Across the 800 trials it has 11 accepted errors above 20 m. 3+1 has 22, the largest 165 m.

Change #2, 40 kHz, 4 ms, 100 trials. TDOA is GCC-PHAT. The mean absolute TDOA column includes failed solves.

| SNR | Tetra median (m) | 3+1 median (m) | Tetra 95th (m) | 3+1 95th (m) | Tetra mean \|TDOA\| (µs) | 3+1 mean \|TDOA\| (µs) | Tetra success | 3+1 success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| noise-free | 0.498 | 0.601 | 3.593 | 13.787 | 0.082 | 0.079 | 99% | 99% |
| 30 dB | 0.626 | 0.664 | 4.533 | 7.115 | 0.087 | 0.080 | 99% | 99% |
| 20 dB | 1.819 | 1.792 | 7.124 | 7.018 | 5.276 | 5.184 | 82% | 80% |
| 10 dB | 4.855 | 3.685 | 84.738 | 7.327 | 23.992 | 27.027 | 62% | 56% |
| 5 dB | 4.777 | 4.505 | 22.293 | 7.835 | 45.601 | 50.946 | 68% | 63% |
| 0 dB | 5.275 | 5.093 | 121.741 | 9.304 | 77.719 | 84.695 | 68% | 58% |

Noise-free, the waveform TDOA error matches between the arrays: mean absolute error is about 0.08 µs, and the medians are 0.071 µs and 0.068 µs. At 20 dB the median position errors agree. From 10 dB down, both mean TDOA errors jump by about one or more 40 kHz periods (25 µs). The tetrahedron accepts more of those trials, and its accepted tail is heavier (95th percentile 85 m at 10 dB and 122 m at 0 dB). 3+1 rejects more trials, and the trials it accepts have a lower 95th percentile. That is not a single ranking.

Rejected solves: tetrahedron 122, 3+1 145, all `no_bounded_solution`. Accepted errors above 20 m: 19 and 7. Largest accepted errors: 199 m and 163 m.

Directions are relative to the array center. A label is cardinal only when one axis is at least 1.5 times the next. The source elevation stops at ±50°, so almost no source is axis-dominant in Z. ABOVE and BELOW therefore do not have enough trials to rank. Bins with at least five sources are in `results/geometry_comparison/plots/directional_localization_error.png`. On Change #1, RIGHT favors the tetrahedron's median (0.90 m versus 1.56 m, 11 sources). FRONT and LEFT favor 3+1 by a smaller margin, and BACK is within 10%. On Change #2 the medians are close on RIGHT, and 3+1's median is lower on FRONT, BACK, and LEFT, with lower success in those bins.

The 25/30/35/40 kHz check is stored with each geometry. It is not used as a winner between arrays.
