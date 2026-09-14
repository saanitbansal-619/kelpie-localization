# Preprocessing notes

These notes explain the choices in the current offline pipeline. The goal is
not to invent a fancy denoiser. The goal is to clean each hydrophone channel
just enough that a later TDOA estimator can still see the *relative* arrival
times.

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
(later) GCC-PHAT / TDOA
        ↓
(later) 3D direction / position
```

## Why DC removal matters

Hydrophone amplifiers and ADCs often sit at a non-zero mid-scale voltage.
That constant bias is not sound. If you leave it in:

- the mean value dominates simple energy detectors
- a bandpass filter has to "spend" its startup transient killing the offset
- plots look like four stacked DC lines with a tiny wiggle on top

Subtracting the per-channel mean is a linear, memoryless operation. It does
not delay the waveform and it does not change the time difference between
channels.

## Why bandpass filtering is useful

The synthetic ping used here occupies roughly 18–42 kHz. Everything outside
that band is either:

- low-frequency flow / handling noise
- 60 Hz-ish electrical pickup (and harmonics)
- high-frequency ADC noise and out-of-band interference

A Butterworth bandpass keeps the ping frequencies and attenuates the rest.
The default demo band is a little wider than the chirp (15–45 kHz) so the
filter does not chew up the chirp edges.

The same cutoff frequencies are used on every channel. If you ever filtered
each hydrophone with a *different* cutoff, the group delay would differ and
you would invent a fake TDOA.

## Why zero-phase filtering is used offline

`scipy.signal.sosfiltfilt` runs a second-order-section Butterworth filter
forward and then backward. The two passes cancel the filter's group delay,
so the output event stays at the same sample index as the input event.

That property is convenient for:

- debugging against known synthetic delays
- detecting one common event time
- later cross-correlation, which should see only the *physical* delay

`filtfilt` is non-causal: it needs the whole recording (or at least a long
buffer) before it can emit a sample. That is acceptable for this offline
Python pipeline. It would be the wrong default for a sample-by-sample
realtime firmware loop.

A footnote: applying the *same* causal filter to every channel would add the
*same* group delay to every channel, so relative TDOA would still be
preserved. Zero-phase is still preferred here because it avoids phase
distortion of the chirp and keeps plots / event indices aligned with ground
truth.

## Why aggressive denoising is intentionally avoided right now

Wavelet shrinkage, spectral subtraction, and many "AI denoisers" can:

- warp phase
- slightly time-shift onsets
- apply a different effective delay to a loud channel than to a quiet one

Those artifacts look harmless on a spectrogram and then quietly break
GCC-PHAT. Until the localization math is in place and we can measure TDOA
error, the conservative choice is:

- DC removal
- a linear zero-phase bandpass
- nothing that reshapes the ping in a nonlinear way

## Why all channels must use one common event window

TDOA is the difference in arrival time *between* hydrophones. That
difference only exists if you look at the same slice of time on every
channel.

If you independently peak-pick four envelopes, you get four timestamps.
Those timestamps already *are* a (bad) TDOA estimate, and they throw away
the rest of the waveform. GCC-PHAT needs the waveforms, aligned on a shared
sample grid, with the relative delay still sitting inside the window.

So the detector here builds **one** energy trace from all channels, chooses
**one** index, and copies **the same** `[start, end)` range from every
hydrophone. Channels are never independently time-aligned in preprocessing.

## Why continuous single-frequency tones create ambiguous cross-correlation peaks

The autocorrelation of a pure sine of frequency `f` is another sine. Two
hydrophones receiving the same tone produce a periodic GCC-PHAT surface
with peaks every `1/f` seconds.

At 30 kHz that spacing is about 33 microseconds, which is only ~8.5 samples
at 256 kHz — the same order of magnitude as a real hydrophone-array TDOA.
You cannot tell which peak is the true delay.

A tone is still useful later for hardware SNR checks. It is a poor signal
for developing a TDOA pipeline.

## Why a short chirp / burst is useful during development

A linear chirp that sweeps 18 → 42 kHz in ~4 ms has a sharp autocorrelation
peak: only one lag matches the whole sweep. That gives GCC-PHAT a unique
delay estimate and makes synthetic tests easy to judge by eye.

It is also closer to the short acoustic pingers used in RoboSub tasks than a
continuous laboratory tone is. Once the preprocessor, windowing, and (later)
TDOA math work on this chirp, swapping in a recorded pinger burst should be
mostly a parameter change, not a rewrite.
