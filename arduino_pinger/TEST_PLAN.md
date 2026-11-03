# Pinger bench test plan

This is a procedure. No Arduino, scope, or tank measurement was made when this plan was written. Do not fill the tables with expected-timer numbers and call them measurements. The "timer formula" column is arithmetic from the sketch, not a scope reading.

There are two different tests:

| Stage | What it proves | What it does not prove |
| --- | --- | --- |
| Electrical bench | D9 frequency, D8 burst length, repetition, idle levels | Sound in water, source level, range |
| Underwater acoustic | A real projector, heard by a receive hydrophone | Not part of this firmware bring-up |

Keep the transducer and any power amplifier disconnected for the electrical section. That is a bench procedure, not something the firmware enforces. `TEST` only prints notes. `#define TEST_MODE 1` only adds a boot warning. `START` still drives D8 and D9 in either setting, and neither one disables an amplifier.

## Equipment

- Arduino Uno R3 or classic Nano, this sketch uploaded, USB to the laptop.
- Serial monitor at 115200 baud, newline enabled.
- Keysight MSOX2014A. Bandwidth is sufficient for a 40 kHz logic square wave. Use a 10× probe.
- Optional: Keysight 33500B as a frequency reference or counter check. It is not the pinger. Do not replace D9 with the generator and then claim the Arduino was measured.
- Pull-downs on D8 and D9 if a driver board is already hanging on the wires. For a bare Arduino they are still a good idea.

Probe ground is Arduino GND. Do not clip the scope ground to a vehicle hull or a future amplifier output.

Channel setup: Ch1 on D9 (carrier), Ch2 on D8 (enable). Trigger on Ch2 rising edge for burst timing. Trigger on Ch1 for frequency.

## Startup safety

Do this before any other measurement.

1. Upload the sketch. Leave the serial monitor closed for the first power cycle if you want to see the pins with no `START` typed.
2. Probe D8 and D9 while the board resets.
3. Record whether both pins sit LOW after the boot message would have been sent (open the monitor only after the level is recorded, or record with the monitor open and confirm nobody sent `START`).
4. Send `STATUS`. Expect `STATE stopped` and `BURST off`.
5. Send `STOP` again. Pins must stay LOW.
6. Send `START`. D8 must go HIGH and D9 must show the carrier within one burst.
7. Send `STOP`. D8 and D9 must return LOW and stay LOW. The carrier must not finish the current burst.

Pass criterion: no carrier and no enable until `START`, and both pins forced LOW on `STOP` without a reset.

Bootloader interval: pins can float until `setup()` runs. Note that on the scope. A float is a firmware-start fact, not a pass. Pull-downs are the hardware fix.

## Frequency

Request each carrier, read the sketch's reported actual frequency, then measure D9.

```text
STOP
FREQ 25000
START
```

Repeat for 30000, 35000, and 40000. Measure several cycles in the middle of the 10 ms burst, not across the truncated last cycle. Use the scope's frequency measurement and, if wanted, the 33500B counter on the same pin.

| Requested Hz | OCR1A from firmware | Timer-formula Hz (not a measurement) | Scope Hz | Delta vs formula | Pass? |
| --- | ---: | ---: | ---: | ---: | --- |
| 25000 | 319 | 25000.00 | | | |
| 30000 | 266 | 29962.5468 (prints 29962.54) | | | |
| 35000 | 228 | 34934.4978 (prints 34934.49) | | | |
| 40000 | 199 | 40000.00 | | | |

Pass criterion: scope frequency agrees with the serial "actual" value within the scope's timebase accuracy, not necessarily with the nominal request. 30 kHz and 35 kHz are supposed to miss the nominal. A reading of 30000.00 Hz at the 30 kHz setting would be a failure.

Also send rejected values and record the `ERR` text: `FREQ 24000`, `FREQ 40500`, `FREQ 30500`, `FREQ 30000.5`, `FREQ`.

## Burst length and repetition

Defaults after a reset: period 1000 ms, pulse 10 ms.

1. `START`.
2. Measure D8 high time. Record it against 10 ms.
3. Measure rising edge of D8 to the next rising edge. Record it against 1000 ms.
4. Confirm D9 is toggling only while D8 is HIGH, and is LOW while D8 is LOW.

Then:

```text
STOP
PULSE 1
PERIOD 500
START
```

Measure a 1 ms burst at a 500 ms period. Then `PULSE 100` and `PERIOD 2000` and measure those.

| Setting | Expected | Scope | Delta | Pass? |
| --- | --- | ---: | ---: | --- |
| Pulse 10 ms | 10 ms high on D8 | | | |
| Period 1000 ms | 1000 ms start to start | | | |
| Pulse 1 ms | 1 ms | | | |
| Period 500 ms | 500 ms | | | |
| Pulse 100 ms | 100 ms | | | |
| Period 2000 ms | 2000 ms | | | |

Pass criterion: D8 width within about 0.1 ms plus one carrier period of the request, and the period within about 1 ms, while serial is quiet. A 1 ms burst will show a partial final cycle. That is expected. Write the measured edge count in the notes.

Rejected timing, record the error and confirm the previous setting did not change (`STATUS`):

- `PULSE 0`, `PULSE 101`
- `PERIOD 499`, `PERIOD 2001`
- `PULSE 100` while `PERIOD` is 100, or `PERIOD 500` while `PULSE` is 500

## Commands while running

1. `START` at 30 kHz, 10 ms, 1000 ms.
2. During a burst, send `FREQ 40000`. The current burst must keep the old carrier. The next burst must match the new actual frequency (40000 Hz).
3. Send `PULSE 20` while running. The following burst, or the current one if it has not ended, must use 20 ms. Confirm with the scope.
4. Send `PERIOD 1500` and confirm the gap changes without a reset.
5. Send `START` again. Expect `ERR already running` and no glitch that leaves D9 stuck HIGH.
6. Send `STOP` during a burst. D9 must not remain HIGH.

## Rounding and jitter

Frequency rounding is the table above. The sketch prints `OCR1A` so the scope number can be checked against `16000000 / (2 * (OCR1A + 1))`.

Jitter:

1. Trigger on D8 rising edge, persistence on, serial monitor idle for 30 seconds.
2. Record the spread of the next D8 rising edge around 1000 ms.
3. Repeat while the monitor is printing. Send `STATUS` every few seconds. The period may stretch by the print time. Record that separately from the quiet result.

Pass criterion: quiet-serial jitter is small compared with the 500 ms minimum period (a few milliseconds would be worth investigating; tens of microseconds is the expected loop slack). While a status or help reply is printing, the burst may run long by about one serial line. There is no numeric pass limit until the first real capture sets a baseline. Do not invent one.

Host logic tests (`arduino_pinger/test_pinger_logic.cpp`, summarized in `HOST_VERIFICATION.md`) check frequency rounding, rejected commands, and a mocked `uint32_t` clock. They do not exercise Timer1 or the pins. A passing host test is not a scope result.

`micros()` wrap is about 71.6 minutes. The host suite checks the unsigned subtraction with synthetic timestamps. That does not replace a board run: `START` for longer than 72 minutes, with bursts still continuing, is still unmeasured. Do not report the board run as done unless the Uno actually ran that long.

## Evidence to keep

For each passing setup, save:

- A scope screenshot of D9 and D8 over one burst.
- A screenshot of several carrier cycles with the frequency readout visible.
- The serial `STATUS` line from the same minute.
- A one-line note of board type, IDE version, and sketch `TEST_MODE` value.

Suggested file names, stored outside the simulation result folders (for example `arduino_pinger/evidence/`, created only when a real test happens):

```text
YYYYMMDD_freq_30kHz.png
YYYYMMDD_burst_10ms.png
YYYYMMDD_stop_during_burst.png
YYYYMMDD_notes.txt
```

Do not put those captures in `results/` or `results_h4_height_study/`.

Blank log:

| Date | Operator | Board / port | Sketch TEST_MODE | Step | Result | Evidence file |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## Underwater acoustic validation

Do not start this until the electrical table has real scope numbers and `HARDWARE_INTERFACE.md` no longer has TBD on the driver and transducer that are actually in the water.

Acoustic validation needs a transmitting element, its amplifier, a receive hydrophone (the Aquarian S1f is a receiver and is legal on the receive side only), a known range, and a way to record the receive waveform. It measures arrival, level, and distortion. It does not replace the D9 frequency check.

Fail the acoustic test, and do not "fix" it in this sketch, if the only problem is driver voltage, impedance, or a destroyed receive element used as a speaker.
