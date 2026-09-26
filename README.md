# RoboSub Hydrophone Localization

Standalone Python pipeline for 4-hydrophone underwater acoustic localization.

The long-term system is:

* 4 hydrophones
* synchronized 4-channel acquisition
* Python signal processing
* TDOA / GCC-PHAT
* 3D direction and position estimation

This repository is **not** a ROS stack, Jetson image, or firmware project.
Those layers can be added later. Right now the code is an offline,
educational signal-processing foundation.

## Current phase

Hardware is not available yet. This milestone builds and validates **synthetic
TDOA estimation** on top of the existing preprocessing pipeline.

What works today:

1. Generate a 4-channel synthetic chirp capture with known delays
2. Add noise and DC offsets
3. Remove DC and bandpass each channel without shifting them relative to each other
4. Detect one shared acoustic event
5. Extract one common multi-channel window
6. Estimate TDOAs with GCC-PHAT and compare them to synthetic ground truth

What is intentionally missing:

* Direction estimation
* 3D localization
* ROS / Jetson / embedded hardware control
* Hardware validation

Status:

| Stage | Status |
| --- | --- |
| Preprocessing | IMPLEMENTED |
| Synthetic TDOA | IMPLEMENTED after validation |
| Direction estimation | NOT IMPLEMENTED |
| 3D localization | NOT IMPLEMENTED |

## Architecture overview

```
Synthetic 4-channel acoustic signal
        → add configurable channel delays
        → add noise / DC offsets
        → preprocessing (DC removal + zero-phase bandpass)
        → event detection (one index from all channels)
        → common multi-channel window extraction
        → GCC-PHAT
        → TDOA (relative to CH0)
        → later: direction estimation
        → later: 3D localization
```

Engineering rule: preprocessing must never destroy the relative arrival-time
differences between channels. Filters are identical, there is no per-channel
time alignment, and the event window uses the same sample indices on every
hydrophone.

Default simulation parameters:

| Parameter | Value |
| --- | --- |
| Sample rate | 256 000 Hz |
| Chirp | 18 kHz → 42 kHz |
| Chirp duration | ~4 ms |
| Channels | 4 |

## Folder structure

```
robosub-hydrophone-localization/
├── README.md
├── PROJECT_STATUS.md
├── CHANGELOG.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── simulation.py      # synthetic chirp + 4-channel delays
│   ├── preprocessing.py   # DC removal, bandpass, normalization
│   ├── detection.py       # shared event index + common window
│   └── tdoa.py            # GCC-PHAT and multichannel TDOA
├── scripts/
│   ├── generate_synthetic_data.py
│   ├── test_preprocessing.py
│   ├── run_tdoa_demo.py
│   └── run_tdoa_snr_experiment.py
├── tests/
│   ├── __init__.py
│   ├── test_preprocessing.py
│   └── test_tdoa.py
├── data/
│   ├── raw/               # generated .npz captures
│   └── processed/         # SNR experiment CSV
├── plots/                 # demo figures
└── docs/
    ├── preprocessing_notes.md
    └── tdoa_notes.md
```

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Linux / macOS
# source .venv/bin/activate

pip install -r requirements.txt
```

Dependencies: `numpy`, `scipy`, `matplotlib`, `pytest`.

Run commands from the project root so `src` imports resolve.

## How to run the preprocessing demo

Generate a synthetic capture (saved under `data/raw/`):

```bash
python scripts/generate_synthetic_data.py
```

Run the preprocessing visualization (figures saved under `plots/`):

```bash
python scripts/test_preprocessing.py
```

The demo prints sample rate, true delays, detected event index, window
indices, and array shapes. It writes:

* `plots/raw_channels.png`
* `plots/processed_channels.png`
* `plots/event_window.png`
* `plots/combined_energy.png`

Run the TDOA demo (table + GCC-PHAT figure under `plots/`):

```bash
python scripts/run_tdoa_demo.py
```

Run the SNR experiment (CSV under `data/processed/`, plot under `plots/`):

```bash
python scripts/run_tdoa_snr_experiment.py
```

Run unit tests:

```bash
python -m pytest -v
```

## Current milestone

**Synthetic TDOA estimation**

The repository can create a known-delay 4-channel chirp, clean it, find one
event, cut one shared window, and recover the inter-channel delays with
GCC-PHAT. Estimated TDOAs are compared with synthetic ground truth, including
an SNR sweep that reports how absolute error grows as noise increases.

See [docs/preprocessing_notes.md](docs/preprocessing_notes.md) for why DC
removal, zero-phase bandpass, and a common window are required.

See [docs/tdoa_notes.md](docs/tdoa_notes.md) for the TDOA sign convention,
GCC-PHAT, sampling limits, interpolation, and physical delay bounds.

## Future roadmap

1. Hydrophone array geometry + direction estimation from the TDOA vector
2. Geometric solver for 3D position from a known hydrophone array
3. Replace the simulator with recorded 4-channel captures
4. Only then: hardware acquisition, Jetson/ROS integration, and realtime constraints

Every meaningful code change is recorded in [CHANGELOG.md](CHANGELOG.md).
