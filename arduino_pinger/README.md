# RoboSub pinger transmitter firmware

Logic-level burst controller for a future underwater acoustic pinger. It runs on an Arduino Uno R3 or a classic Nano (ATmega328P, 16 MHz). It produces a square-wave carrier on D9 and a burst-enable signal on D8.

An Arduino pin cannot power an underwater transducer. D9 must feed an external driver or power amplifier that has not been selected. This sketch is not a Python acoustic simulator and it is not receiver firmware.

Transmitter requirements, the D8/D9 interface, and the transducer selection checklist are in `PINGER_HARDWARE_REQUIREMENTS.md`, `PINGER_INTERFACE.md`, and `PINGER_VALIDATION_CHECKLIST.md`. Those notes do not select a transducer or an amplifier.

No hardware was exercised to produce this folder. Compile and scope checks below are procedures, not recorded results.

## Compatibility

| Item | Requirement |
| --- | --- |
| Board | Arduino Uno R3 or classic Nano |
| MCU | ATmega328P |
| Clock | 16 MHz. The sketch refuses other `F_CPU` values. |
| Carrier pin | D9, hardware Timer1 OC1A |
| Enable pin | D8 |
| Serial | 115200 baud, newline or carriage return |

Do not upload this sketch to an Uno-shaped board with a different chip, a Mega, or a 32-bit Arduino. Those parts do not use PB1 as D9 / OC1A in this way.

## Pin assignments

| Arduino pin | ATmega328P | Function when running | Idle, boot, and STOP |
| --- | --- | --- | --- |
| D9 | PB1 / OC1A | ~50% square wave at the programmed carrier | Driven LOW |
| D8 | PB0 | HIGH for the burst (active-high enable assumption) | Driven LOW |
| GND | GND | Logic reference for the driver input | Same |

From reset until `setup()` runs, including the Uno bootloader, D8 and D9 are high-impedance inputs. Firmware cannot pull them low in that window. Before a driver is connected, D8 needs a hardware pull-down so an open pin cannot enable the amplifier. Details are in `HARDWARE_INTERFACE.md`.

D8 high-during-burst matches the requirement that enable is LOW when idle. If the chosen driver is active-low, or wants 3.3 V logic, do not connect it until the firmware polarity and level are changed. That driver does not exist yet.

## Upload with the Arduino IDE

1. Install the Arduino IDE (2.x is fine) and the Arduino AVR core it uses for Uno.
2. Open `arduino_pinger/robosub_pinger/robosub_pinger.ino`.
3. Tools → Board → Arduino Uno. A classic Nano with the ATmega328P uses Tools → Board → Arduino Nano and Tools → Processor → ATmega328P. The old Nano bootloader is a separate Tools → Processor choice if a new upload fails to start.
4. Tools → Port → the board's serial port.
5. Optional boot warning: in the sketch, set `#define TEST_MODE 1`, then upload again. This flag only changes the boot text. `START` still drives D8 and D9. It does not mute the pins and it does not disable an amplifier.
6. Sketch → Upload.
7. Tools → Serial Monitor. Set 115200 baud and a newline ending (New Line or Both NL & CR).

The sketch was compiled for `arduino:avr:uno` with Arduino CLI 1.4.1 and the `arduino:avr` 1.8.8 core. That was a build check only. It did not program a board, and the firmware has not been run on hardware. Arduino IDE 2 keeps `arduino-cli` inside the IDE install, so it may be absent from `PATH`. From a shell where the CLI is available:

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:uno arduino_pinger/robosub_pinger
arduino-cli upload -p COM5 --fqbn arduino:avr:uno arduino_pinger/robosub_pinger
```

Replace `COM5` with the port shown by `arduino-cli board list`.

## Default settings

| Setting | Default | Allowed |
| --- | --- | --- |
| Carrier request | 30000 Hz | 25000 to 40000 Hz, multiples of 500 Hz |
| Repetition period | 1000 ms | 500 to 2000 ms |
| Burst length | 10 ms | 1 to 100 ms, and strictly shorter than the period |

The timer cannot hit every requested frequency. With a 16 MHz clock and prescaler 1:

| Requested | OCR1A | Frequency the timer actually toggles |
| --- | ---: | --- |
| 25000 Hz | 319 | 25000.00 Hz |
| 30000 Hz | 266 | 29962.54 Hz |
| 35000 Hz | 228 | 34934.49 Hz |
| 40000 Hz | 199 | 40000.00 Hz |

`STATUS` and a successful `FREQ` command print the actual rate for the current request. Formula: `f = 16000000 / (2 * (OCR1A + 1))`, with `OCR1A + 1` equal to the integer nearest to `16000000 / (2 * f_request)`. The serial hundredths are truncated, not rounded: 30000 Hz is exactly 16000000/534 = 29962.5468… Hz and prints as 29962.54 Hz.

On boot the pins stay LOW and the pinger does not transmit until `START`.

## Serial examples

```text
HELP
STATUS
FREQ 30000
PERIOD 1000
PULSE 10
START
STOP
TEST
```

`FREQ`, `PERIOD`, and `PULSE` can be sent while the pinger is running. A new carrier is loaded on the next burst, not in the middle of the current one. Period and pulse update the scheduler immediately. The sketch rejects a pulse that is longer than or equal to the period, values outside the ranges above, unknown commands, and junk after a number.

`START` while already running is rejected so the burst is not restarted by accident. `STOP` forces D9 and D8 LOW before it prints `OK`, and it is safe to send more than once. If a reply is already printing, `STOP` is applied between lines, so the extra wait is one serial line (a few milliseconds at 115200), not the whole reply. A command typed ahead of that `STOP` is kept and run afterward. A burst can also run long by that same one-line transmit time, because the end check runs between lines and once per `loop()`, not inside the UART shift register.

`TEST` only prints bench-probe notes. It does not start the carrier.

## What the waveform is

Timer1 toggles D9, so the carrier is a logic square wave, not a sine. A 50% square wave contains the fundamental and odd harmonics (3rd, 5th, …) with amplitudes that fall as 1/n. What the water actually hears depends on the driver, any matching network, and the transducer resonance. None of those parts are selected. Do not treat this GPIO edge as acoustic source level.

Stopping the timer freezes OC1A at whatever level it had. The stop path therefore disconnects OC1A and drives PB1 low before it drops the enable pin.

## Limitations

- No transducer, power amplifier, matching network, or wet connector is specified.
- USB 5 V cannot be the acoustic power source.
- Burst timing uses `micros()` in the main loop. Timer1 stays dedicated to the carrier. With a quiet serial port, edge jitter is the loop time, typically tens of microseconds. While a line is printing, a burst can run long by that line's transmit time.
- A 1 ms burst is within `micros()` resolution, but the last cycle is cut when the burst ends, so the edge count is not a perfect 50% symbol over the whole burst.
- The Uno bootloader leaves D8 and D9 high-Z until this sketch starts. A pull-down on D8 is a required hardware fail-safe before a driver is attached. `TEST_MODE` does not replace it.
- Host checks, not hardware tests: `powershell -ExecutionPolicy Bypass -File arduino_pinger\run_host_verification.ps1` from the repository root. It reruns `test_pinger_logic.cpp` and, when Arduino CLI is available, compiles the sketch for Uno. The written result is `arduino_pinger/HOST_VERIFICATION.md`. That file is not a scope or acoustic measurement. The test source sits outside the sketch folder so the Arduino IDE does not upload it.
- This folder does not change the localization simulations, CAD, or experiment results.
