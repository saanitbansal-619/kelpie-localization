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

Hardware is not available yet. This milestone only builds and validates the
**synthetic signal preprocessing pipeline** that will sit in front of TDOA /
GCC-PHAT.

What works today:

1. Generate a 4-channel synthetic chirp capture with known delays
2. Add noise and DC offsets
3. Remove DC and bandpass each channel without shifting them relative to each other
4. Detect one shared acoustic event
5. Extract one common multi-channel window

What is intentionally missing:

* GCC-PHAT
* TDOA solving
* 3D localization
* ROS / Jetson / embedded hardware control

## Architecture overview

```
Synthetic 4-channel acoustic signal
        → add configurable channel delays
        → add noise / DC offsets
        → preprocessing (DC removal + zero-phase bandpass)
        → event detection (one index from all channels)
        → common multi-channel window extraction
        → later: GCC-PHAT / TDOA
        → later: localization
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
├── CHANGELOG.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── simulation.py      # synthetic chirp + 4-channel delays
│   ├── preprocessing.py   # DC removal, bandpass, normalization
│   └── detection.py       # shared event index + common window
├── scripts/
│   ├── generate_synthetic_data.py
│   └── test_preprocessing.py
├── tests/
│   ├── __init__.py
│   └── test_preprocessing.py
├── data/
│   ├── raw/               # generated .npz captures
│   └── processed/
├── plots/                 # demo figures
└── docs/
    └── preprocessing_notes.md
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

Run unit tests:

```bash
python -m pytest tests/test_preprocessing.py -v
```

## Current milestone

**Synthetic preprocessing foundation**

The repository can create a known-delay 4-channel chirp, clean it, find one
event, and cut one shared window. That window is the intended input to a
future GCC-PHAT stage.

See [docs/preprocessing_notes.md](docs/preprocessing_notes.md) for why DC
removal, zero-phase bandpass, and a common window are required, and why a
short chirp is used instead of a continuous tone.

## Future roadmap

1. GCC-PHAT on the common window → per-pair TDOA estimates
2. Compare estimated delays against the synthetic ground truth
3. Geometric solver for 3D direction / position from a known hydrophone array
4. Replace the simulator with recorded 4-channel captures
5. Only then: hardware acquisition, Jetson/ROS integration, and realtime constraints

Every meaningful code change is recorded in [CHANGELOG.md](CHANGELOG.md).
