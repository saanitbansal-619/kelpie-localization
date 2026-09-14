# Changelog

## 2026-09-14

### Added

* Initial repository structure for the standalone 4-hydrophone localization project
* Synthetic 4-channel chirp generator with configurable relative delays, Gaussian noise, and DC offsets
* Preprocessing functions: DC removal, zero-phase Butterworth bandpass, peak normalization, and aligned multichannel processing
* Combined-energy event detection and common-window extraction that uses the same sample indices on every channel
* Scripts to save a synthetic `.npz` capture and to run a preprocessing visualization demo
* Pytest coverage for DC removal, normalization, bandpass length, shape preservation, and identical common-window indices
* README, preprocessing notes, and this changelog
