# H4 height study

This study moves only H4 on the existing 3+1 array. H1, H2, and H3 stay at the catalog coordinates. Nothing is written into `results/`, `simulations/noise_study/`, or `simulations/waveform_study/`.

Output root: `results_h4_height_study/`.

## Geometry

Channels H0, H1, and H2 are the requested H1, H2, and H3. They lie in one horizontal plane at z = -0.0375 m. H4 is centered on that triangle in x and y. A tested height is the offset from that plane, not from the origin. The catalog H4 is the +0.15 m case.

`0 m` is not tested. A negative height puts H4 below the plane. The array is not recentered, so moving H4 does not move H1, H2, or H3.

Directions use the fixed triangle centroid:

| Axis | Direction |
| --- | --- |
| +X | FRONT |
| -X | BACK |
| +Y | RIGHT |
| -Y | LEFT |
| +Z | ABOVE |
| -Z | BELOW |

An axis is included when its absolute component is at least half the largest component. The label order is X, then Y, then Z. A bin with fewer than 5 unique sources is kept and flagged `INSUFFICIENT_SAMPLE_COUNT`.

## What stays fixed

Both changes use 100 trials, seed `20261004`, sound speed 1480 m/s, and the existing solver. Change #1 uses the Change #1 source draw and SNR list. Change #2 uses the first 100 geometry-study sources, a 40 kHz 4 ms pulse, 256 kHz sampling, attenuation off, and GCC-PHAT. The noise seed is `20261004 + trial_index` at every height.

A rejected solve is not stored as zero error. A trial is catastrophic when the solver rejects it or the accepted error exceeds 20 m. A huge accepted range still counts as a success.

## Ranking

Overall height is the lowest sum of ranks on median error, 95th percentile, median angular error, success rate, catastrophic rate, and the spread of per-direction medians. Change #2 also ranks median absolute TDOA error. Mean error is reported and is not the ranking key.

## Reproduce

```bash
python simulations/h4_height_study/run_h4_height_study.py
```
