# Joint H4 height and base-scale study

Synthetic Change #2 localization only. This folder is separate from `results/` and from `results_h4_height_study/`.

## Purpose

The earlier H4 sweep stopped at ±30 cm, where the larger vertical separation localized better. This run asks whether going past 30 cm still helps, and whether a larger H1/H2/H3 triangle helps, without a large brute-force search.

## Geometries

Nine layouts. H4 is above the triangle plane, the same side as the previous +30 cm array. The base is the catalog triangle scaled in x and y about its centroid. H4 stays centered on that centroid.

| H4 height | Base scale |
| --- | --- |
| 30 cm | 1.00×, 1.25×, 1.50× |
| 40 cm | 1.00×, 1.25×, 1.50× |
| 50 cm | 1.00×, 1.25×, 1.50× |

Control: `h30_b1.00`, H4 at 30 cm and base scale 1.00×. Its coordinates match the previous +30 cm array.

## Simulation

Same Change #2 pipeline as the H4-height study: 40 kHz carrier, 4 ms pulse, 256 kHz sampling, sound speed 1480 m/s, attenuation off, GCC-PHAT, and the existing solver. Sources are the first 100 rows of the geometry-study source table. SNR conditions are noise-free, 30, 20, 10, 5, and 0 dB. The random seed is 20261004 plus the source index, shared by every geometry, so the nine layouts see the same cases.

A solve is catastrophic when the solver rejects it or the accepted position error exceeds 20 m. A huge accepted range still counts as a success. Error statistics use successful solves only.

## Metrics and ranking

The comparison table reports median, mean, and 95th-percentile localization error, median angular error, success rate, catastrophic rate, and median absolute TDOA error, with the trial and success counts.

Best accuracy is the lowest sum of ranks on median error, 95th-percentile error, and median angular error. Best reliability is the lowest sum of ranks on success rate and catastrophic rate. Best balanced adds those five ranks. Median error alone does not select the layout. A layout is Pareto-optimal when no other layout is at least as good on all five and better on one.

## Results

| Geometry | H4 (cm) | Base | Median (m) | P95 (m) | Angle (deg) | Success | Catastrophic | TDOA (µs) | Roles |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| h30_b1.00 | 30 | 1.00× | 1.245 | 7.747 | 0.148 | 73.2% | 28.5% | 0.343 | control |
| h30_b1.25 | 30 | 1.25× | 1.494 | 7.048 | 0.255 | 78.5% | 22.3% | 0.324 | best_reliability;best_balanced |
| h30_b1.50 | 30 | 1.50× | 1.780 | 8.806 | 0.258 | 78.2% | 23.3% | 0.336 | — |
| h40_b1.00 | 40 | 1.00× | 0.704 | 7.658 | 0.155 | 75.2% | 27.3% | 0.389 | — |
| h40_b1.25 | 40 | 1.25× | 0.716 | 7.406 | 0.129 | 74.2% | 27.8% | 0.394 | — |
| h40_b1.50 | 40 | 1.50× | 1.451 | 7.065 | 0.423 | 76.3% | 24.8% | 0.431 | — |
| h50_b1.00 | 50 | 1.00× | 0.763 | 8.030 | 0.223 | 76.8% | 26.5% | 0.376 | — |
| h50_b1.25 | 50 | 1.25× | 0.700 | 7.251 | 0.148 | 74.8% | 26.8% | 0.407 | — |
| h50_b1.50 | 50 | 1.50× | 0.563 | 7.091 | 0.108 | 73.5% | 27.8% | 0.409 | best_accuracy |

Best accuracy: `h50_b1.50` (median 0.563 m, success 73.5%, catastrophic 27.8%).

Best reliability: `h30_b1.25` (median 1.494 m, success 78.5%, catastrophic 22.3%).

Best balanced: `h30_b1.25` (median 1.494 m, success 78.5%, catastrophic 22.3%).

Control `h30_b1.00`: median 1.245 m, 95th percentile 7.747 m, median angle 0.148 deg, success 73.2%, catastrophic 28.5%.

### Does raising H4 from 30 to 50 cm keep helping?

At 1.00× the medians are 30 cm 1.245 m, 40 cm 0.704 m, 50 cm 0.763 m. From 30 cm to 50 cm that is -38.7%. At 1.25× the medians are 30 cm 1.494 m, 40 cm 0.716 m, 50 cm 0.700 m. From 30 cm to 50 cm that is -53.2%. At 1.50× the medians are 30 cm 1.780 m, 40 cm 1.451 m, 50 cm 0.563 m. From 30 cm to 50 cm that is -68.4%.

### Does a larger base triangle help?

At 30 cm the medians are 1.00× 1.245 m, 1.25× 1.494 m, 1.50× 1.780 m. From 1.00× to 1.50× that is +42.9%. At 40 cm the medians are 1.00× 0.704 m, 1.25× 0.716 m, 1.50× 1.451 m. From 1.00× to 1.50× that is +106.3%. At 50 cm the medians are 1.00× 0.763 m, 1.25× 0.700 m, 1.50× 0.563 m. From 1.00× to 1.50× that is -26.2%.

### Do height and base scale interact?

The base scale with the lowest median depends on H4 height. 30 cm prefers 1.00× (`h30_b1.00`), 40 cm prefers 1.00× (`h40_b1.00`), 50 cm prefers 1.50× (`h50_b1.50`). That is an interaction: the useful base size is not the same at every height.

### Does a larger array buy accuracy at the cost of successful solves?

The largest layout, `h50_b1.50`, changes median error by -54.8% relative to the control, success by +0.3 percentage points, and the catastrophic rate by -0.7 percentage points. The larger aperture does not show up here as a loss of successful solves.

### Where does extra size stop paying off?

At 1.00×, 30→40 cm changes the median by -0.542 m and 40→50 cm changes it by +0.059 m. At 1.25×, 30→40 cm changes the median by -0.778 m and 40→50 cm changes it by -0.017 m. At 1.50×, 30→40 cm changes the median by -0.329 m and 40→50 cm changes it by -0.888 m. A negative number means the median error decreased.

### Hardware recommendation

The practical layout is `h40_b1.00`: median 0.704 m (43% below the control), success 75.2%, maximum baseline 0.425 m. It is the smallest array that clears that bar. `h50_b1.50` has the lowest median, 0.563 m, which is 20% below the practical layout, at maximum baseline 0.545 m and success 73.5%. Use it only if the vehicle can carry that mast and triangle. The balanced rank pick (`h30_b1.25`) is the reliability corner. Its typical error is not what should be built.

## Directional check

Directional bins use the same rule as the H4-height study, measured from the H1/H2/H3 centroid. That centroid does not move when the triangle is scaled. Bins with fewer than 5 unique sources are kept and flagged `INSUFFICIENT_SAMPLE_COUNT`.

Directional summaries were computed for `h30_b1.00`, `h30_b1.25`, `h50_b1.25`, `h50_b1.50`: the control, the best balanced layout, and the second-best balanced layout. Ties are included.

## Limitations

- Only the positive H4 side was tested.
- The grid is three heights by three scales, so it locates a region rather than a continuous optimum.
- Sources and elevation limits match Change #2. Pure above and below bins can be empty.
- A larger baseline widens the GCC-PHAT search window. That is a consequence of the array, not a second experiment setting.
- Attenuation, mounting error, flow noise, and vehicle scattering are not in this model.
- This study does not compare the layouts with the tetrahedron.

## Recommended next step

The next check is the opposite H4 sign at 40 cm with the current triangle, and at 50 cm with the 1.50× triangle. A finer grid is only useful between 40 and 50 cm, and only at base scales from 1.00× to 1.50×. Widening the triangle at 30 cm made the median worse, so that corner does not need a finer sweep. Compare the chosen 3+1 layout with the tetrahedron after the sign check.

## Files

- `geometries/geometry_coordinates.csv`
- `data/experiment_results.csv`
- `summaries/geometry_comparison_summary.csv`
- `summaries/snr_comparison_summary.csv`
- `directional/directional_comparison_summary.csv`
- `plots/`
- `run_manifest.json`

## Reproduce

```bash
python simulations/joint_geometry_study/run_joint_geometry_study.py
```

This run used 100 sources and finished in 7.1 minutes.
