# MSOX2014A four-channel acquisition

Laptop-side capture for the Keysight MSOX2014A. The intended bench chain is:

```text
Aquarian S1f (receive hydrophone, four of them)
    -> PCB 482C05 IEPE conditioner, one output per hydrophone
    -> MSOX2014A CH1..CH4
    -> this module, one NPZ record
```

H4 is 400 mm below the upper triangle. The triangle side and the absolute coordinates are **TBD**. CH1..CH4 are stored as H1..H4 by convention. That cable map has not been checked. Volts are not converted to pascals. Conditioner gain and hydrophone sensitivity are **TBD**.

The Arduino pinger firmware is a separate transmitter controller. It is not used by this module. Do not wire the transmitter into the oscilloscope inputs.

## What a capture is

One call to `capture` sends one

```text
:DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4
```

and then reads `:WAVeform:PREamble?` and `:WAVeform:DATA?` for each channel. The guide says `:DIGitize` acquires the listed channels and then stops. The four traces are accepted only when they share the same sample count, X increment, X origin, and X reference. That is one acquisition record, not four separate runs.

It is not gap-free streaming. The guide says the instrument is not acquiring while it answers the controller, and `:DIGitize` stops when the record is full. Segmented-memory commands exist in the guide only with the SGM license. This module does not send them.

Command text is taken from Keysight publication **9018-06893**, *Programmer's Guide for InfiniiVision 2000 X-Series Oscilloscopes*:

https://www.keysight.com/us/en/assets/9018-06893/programming-guides/9018-06893.pdf

No MSOX2014A was connected while this module was written. `metadata["instrument_verified"]` is false on every file this code saves.

## Laptop commands

From the repository root:

```powershell
python -m pytest tests/test_msox_acquisition.py -v
python -m acquisition.cli capture --mock -o capture.npz --csv capture.csv
python -m acquisition.cli replay capture.npz -o capture-copy.npz
```

Mock capture does not need PyVISA. A real scope does:

```powershell
python -m pip install pyvisa
python -m acquisition.cli discover
python -m acquisition.cli identify USB0::0x2A8D::...::INSTR
python -m acquisition.cli capture --resource USB0::0x2A8D::...::INSTR -o capture.npz --timeout 30
```

`discover` and `identify` also need a VISA backend (Keysight IO Libraries or NI-VISA). `--timeout` is the whole wait for `:DIGitize`. If the trigger never arrives, the call fails with a timeout instead of hanging.

The NPZ holds `samples` with shape `(4, N)` in volts, `time_s` with shape `(N,)`, `sample_interval_s`, channel ids, hydrophone ids, and a JSON metadata blob. `time_s` is trigger-relative from the preamble. The laptop UTC in the metadata is not an oscilloscope clock. The optional CSV is `time_s,CH1_V,CH2_V,CH3_V,CH4_V` and does not repeat the metadata.

## Commands the driver sends

Verified as present in publication 9018-06893:

| Command | Role |
| --- | --- |
| `*IDN?` | Manufacturer, model, serial, firmware |
| `:SYSTem:ERRor?` | Read the error queue until `0` |
| `:TIMebase:MODE MAIN` | Required before `:DIGitize` and waveform queries |
| `:CHANnel1` … `:CHANnel4:DISPlay ON` | Waveform queries only work when the source is displayed |
| `:ACQuire:TYPE NORMal` | One value per time bucket. Avoids PEAK min/max pairs |
| `:WAVeform:FORMat BYTE` | 8-bit block |
| `:WAVeform:UNSigned ON` and `?` | Codes are unsigned |
| `:WAVeform:BYTeorder LSBFirst` and `?` | Used if the format is WORD |
| `:WAVeform:POINts:MODE RAW` | Ask for the raw record rather than the short measurement record |
| `:DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4` | One acquisition, then the scope stops |
| `:WAVeform:SOURce CHANnel<n>` | Select which buffer to read |
| `:WAVeform:POINts? MAXimum` and `:WAVeform:POINts <n>` | Same count for all four channels |
| `:WAVeform:PREamble?` | Ten scaling fields |
| `:WAVeform:DATA?` | IEEE 488.2 definite-length block |

Voltage and time:

```text
voltage = [(code - yreference) * yincrement] + yorigin
time    = [(index - xreference) * xincrement] + xorigin
```

The driver does not change V/div, time/div, trigger, coupling, or probe attenuation. Set those on the scope before capturing. `:TIMebase:MODE MAIN` does leave roll, XY, or zoom.

## Unverified

- No physical MSOX2014A, conditioner, or hydrophone was used.
- The guide's preamble summary uses ASCii format code 2 and AVERage type code 3. The return-format section and the example use format 4 and type 2. The parser accepts both and keeps the raw integer.
- `:WAVeform:POINts` says only data visible on the display is returned. `:WAVeform:POINts:MODE RAW` says the raw record can be read when the scope is stopped. Both sentences are in the guide. Which one the MSOX2014A does has not been measured.
- BYTE value 0 is also the guide's code for a hole in the record. This module cannot tell those apart.
- Streaming and segmented memory are not implemented.

The bench procedure is `HARDWARE_VALIDATION.md`.
