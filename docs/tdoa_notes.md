# TDOA notes

These notes explain the GCC-PHAT estimator. A later geometry study
(`simulations/geometry_study/`) uses this same estimator on delays that come
from hydrophone and source coordinates, then attempts localization. Linear
and planar arrays are reported there as geometrically non-unique. The notes
below still describe the estimator itself: recover inter-hydrophone arrival
times from one preprocessed multichannel event, and see how that estimate
moves as noise increases.

Current chain:

```
synthetic 4-channel chirp
        ↓
configurable delays + noise + DC
        ↓
remove DC
        ↓
zero-phase Butterworth bandpass
        ↓
one combined-energy event index
        ↓
one common multi-channel window
        ↓
GCC-PHAT  →  TDOA relative to CH0
        ↓
direction and 3D localization when geometry allows
```

## What is TDOA?

The instant a pinger emits a pulse is unknown. Hydrophones do not share a
timestamp with the source, so the software cannot measure an *absolute*
travel time.

What it can measure is a **time difference of arrival** (TDOA): how much
later (or earlier) one hydrophone hears the same event than another. Those
differences still contain geometry. A source closer to hydrophone A than to
hydrophone B produces a shorter path to A, so A receives the ping first.

In this project every TDOA is defined as

```
TDOA_i = arrival_time_i - arrival_time_reference
```

- positive TDOA: channel i received the signal later than the reference
- negative TDOA: channel i received the signal earlier than the reference
- the reference channel TDOA is exactly zero

## Basic equation

For hydrophones `i` and `j`,

```
Δt_ij = (||p - h_i|| - ||p - h_j||) / c
```

| Symbol | Meaning |
| --- | --- |
| `p` | unknown source position |
| `h_i`, `h_j` | known hydrophone positions |
| `||p - h_i||` | Euclidean path length from the source to hydrophone i |
| `c` | speed of sound in the water |
| `Δt_ij` | arrival time at i minus arrival time at j |

If `j` is the reference hydrophone, `Δt_ij` is exactly `TDOA_i` above. GCC-PHAT
estimates the left-hand side from waveforms. Inverting the right-hand side
for `p` is a separate step in `src/localization.py`, and it is reported as
unsuccessful when the hydrophones are collinear or coplanar.

## Why GCC-PHAT?

Ordinary **cross-correlation** slides one waveform against another and asks
which lag makes them line up. In the frequency domain that is

```
r_xy = IFFT( X(f) Y*(f) )
```

The lag of the correlation peak is the delay estimate.

A loud low-frequency band, a spectral peak, or a colored noise floor can
dominate `X(f) Y*(f)` and pull the peak. **PHAT** (phase transform)
weighting flattens the magnitude:

```
R_xy(f) = X(f) Y*(f) / |X(f) Y*(f)|
```

Only the phase — the part that encodes delay — remains. The inverse FFT of
`R_xy` is the PHAT-weighted cross-correlation used here.

A practical detail: after a bandpass, many FFT bins are almost empty. Naive
division by `|X Y*|` would give those noise-only bins the same unit weight
as the chirp band and can move the peak. The implementation floors the
denominator at a small fraction of the peak cross-spectrum magnitude so
in-band bins still receive PHAT weighting and stopband bins do not.

GCC-PHAT is a standard, readable time-delay estimator for broadband bursts
such as the synthetic chirp. It is **not** a complete solution for:

- strong multipath (extra peaks from reflections)
- very low SNR (the phase estimate becomes random)
- narrowband periodic signals (many equivalent peaks)

Those remain known limitations, not bugs to hide.

## Sampling limitation

The acquisition sample rate is

```
fs = 256000 Hz
```

so one original ADC sample lasts

```
Ts = 1 / fs = 3.90625 microseconds
```

Using a reference sound speed of approximately `c = 1480 m/s`, sound travels

```
c * Ts = 1480 / 256000 ≈ 5.78 mm
```

during one original sample. A 0.25 m hydrophone baseline is only about 43
original samples across. A one-sample timing error is already several
millimetres of equivalent path error, and that error grows when it is later
turned into a direction. Timing accuracy matters before geometry is even
introduced.

## Interpolation

The implementation oversamples the correlation function by zero-padding the
PHAT spectrum before the inverse FFT. The default factor is 16, so the
*numerical* lag grid spacing is

```
Ts / 16 = 0.244140625 microseconds
```

That is a finer estimate of where the already-computed correlation peak
sits. It does **not**:

- increase ADC bandwidth
- recover frequencies above the original Nyquist limit
- create new physical measurements between ADC samples

The analog waveform existed between samples; interpolation of the
correlation is a numerical peak-location trick, not extra sensor
information.

## Physical TDOA bounds

Two hydrophones separated by distance `d` cannot observe an arbitrary delay.
The largest possible magnitude is the travel time along the baseline:

```
|Δt|_max ≈ d / c
```

For the future array assumption used in the experiments,

```
d ≈ 0.25 m
c ≈ 1480 m/s
|Δt|_max ≈ 169 microseconds
```

`gcc_phat` does not hardcode `d` or `c`. The caller supplies `max_tau`,
typically `hydrophone_baseline / sound_speed`, and the peak search is
restricted to `[-max_tau, max_tau]`. That rejects physically impossible
correlation peaks. It does not invent a correct delay if the true peak was
outside the window.

All synthetic pairwise TDOAs used in this phase are kept inside that bound.

## Known limitations

- **Low SNR.** Phase at each frequency becomes noisy; the correlation peak
  can hop to a sidelobe or to a noise spike inside `max_tau`.
- **Multipath.** A reflection is another delayed copy. GCC-PHAT may lock
  onto the wrong arrival. The current simulator does not include multipath.
- **Narrowband periodic signals.** A pure tone has a periodic correlation.
  Peaks repeat every `1/f`, which at 30 kHz is ~33 µs — the same scale as a
  real array TDOA.
- **Inaccurate hydrophone geometry.** This phase does not use geometry
  except as a `max_tau` cap. Later direction estimation will be only as good
  as the surveyed array.
- **Inaccurate sound-speed assumption.** `c` scales every future range
  difference. 1480 m/s is a convenient freshwater/reference value, not a
  measured in-situ speed.
- **Source far from a small array.** Path differences become small compared
  with `Ts`. Direction is then poorly conditioned even if TDOA error is a
  fraction of a sample.
- **Clipping.** A saturated ADC destroys waveform shape and phase.
- **Channel synchronization errors.** If the four ADC channels do not share
  a common sample clock, software TDOA will report the cable/clock error as
  if it were acoustics.

Ordinary normalized cross-correlation (unweighted GCC) is included only as
a baseline. It is not claimed to be better than GCC-PHAT; the SNR
experiment reports both methods as measured.
