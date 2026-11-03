# Pinger validation and transducer selection

Checklist for choosing a 25–40 kHz transmitting transducer and for proving the transmitter later. No transducer is selected. No measurement in this file has been made. A filled cell needs a datasheet citation or a recorded measurement. Do not copy timer-formula frequencies into a results column and call them scope readings. `TEST_PLAN.md` is the bench procedure. `HOST_VERIFICATION.md` is a PC logic run, not a hardware result.

The Aquarian S1f stays on the receive side. It can listen to a future projector during an acoustic test. It is not a candidate transmitter.

## Datasheets that have to exist before construction

| Document | What it must contain | Status |
| --- | --- | --- |
| Transmitting transducer datasheet | Impedance versus frequency from below 25 kHz through the 5th harmonic of 40 kHz, resonance, bandwidth, transmit response, maximum voltage and current, power, duty cycle, capacitance, isolation, depth, connector, allowed drive waveform | **TBD** |
| Cable and wet-connector datasheet | Length, capacitance, voltage rating, shield connection, depth | **TBD** |
| Amplifier or driver datasheet | Input voltage range, input current, enable polarity and threshold, behavior when enable is open, gain, bandwidth, output voltage and current, supply, protection, behavior with a square wave | **TBD** |
| Matching network, if the transducer needs one | Topology and ratings taken from the two datasheets above | **TBD**. May be "not required" only after the impedance curve says so |
| ATmega328P and Arduino Uno or Nano pin data | Already the basis for the D8/D9 limits in `PINGER_INTERFACE.md` | In hand as the MCU documentation. Not a substitute for the rows above |
| Grounding plan | Logic ground, acoustic supply return, hull, and receive-hydrophone ground | **TBD** |

## Measurements required to validate the design

Each row stays **NOT RUN** until the evidence exists. Electrical rows happen with the transducer disconnected unless that row explicitly says otherwise. Acoustic rows wait until the electrical table has real numbers and the datasheet rows above are filled.

| Measurement | Evidence | Proves | Status |
| --- | --- | --- | --- |
| D8 and D9 during reset and after `setup()` | Scope, Arduino GND | High-Z window exists; pins are low once the sketch runs; pull-down holds enable low | **NOT RUN** |
| `START` / `STOP` at the Arduino pins | Scope of D9 and D8 | Carrier only during the burst; `STOP` forces both low | **NOT RUN** |
| D9 frequency at 25000, 30000, 35000, and 40000 Hz requests | Scope or counter, plus the serial "actual" line | Pin rate matches `f = 16000000 / (2 * (OCR1A + 1))`, including the known offset at 30 kHz and 35 kHz | **NOT RUN** |
| Burst length and repetition | Scope of D8 | 10 ms / 1000 ms default, then the intended mission timing | **NOT RUN**. Intended timing **TBD** |
| Extra length while `HELP` or `STATUS` prints | Scope | Jitter and one-line stretch | **NOT RUN** |
| Driver input with the acoustic supply off | Scope at the interface | 5 V levels are legal for that input | **NOT RUN**. Driver **TBD** |
| Enable fail-safe: Arduino in reset, acoustic supply on, transducer connected only if the datasheet allows | Scope or current measurement at the transducer | No acoustic power while D8 is high-Z | **NOT RUN** |
| Amplifier output voltage and current into the real load | Differential scope and current probe | Under the transducer maximum, at the commanded duty | **NOT RUN** |
| Impedance of the element plus cable across 25–40 kHz and the odd harmonics | Impedance analyzer or equivalent | Matches the datasheet well enough to finalize the amplifier and any match | **NOT RUN** |
| Received waveform on an Aquarian S1f used only as a hydrophone | Recorded waveform, known range | What the water actually contains: fundamental, harmonics, burst shape | **NOT RUN** |
| Source level and directivity | Calibrated receive measurement | Acoustic output, which D9 voltage does not provide | **NOT RUN**. Method **TBD** |
| `micros()` wrap, `START` longer than 72 minutes | Serial log and scope or a receive record | Bursts continue across timer wrap | **NOT RUN** |

## Decision checklist for a 25–40 kHz transmitting transducer

Answer every line from a datasheet or a measurement before the part is treated as selected. "Unknown" means it is not selected.

| # | Question | Required answer | Status |
| --- | --- | --- | --- |
| 1 | Is this a transmitting projector, rather than an IEPE receive hydrophone? | Yes. An Aquarian S1f is an automatic no | **TBD** |
| 2 | Does the usable transmit band cover the carrier the vehicle will command? | Yes, at a stated resonance. The commanded carrier inside 25–40 kHz is **TBD** | **TBD** |
| 3 | Is impedance versus frequency published for the element and for the cable that will be used? | Curve in hand, including 75–200 kHz if a square wave may reach the element | **TBD** |
| 4 | Are maximum drive voltage, current, and power stated? | Numbers in hand. Do not infer them from a 5 V GPIO | **TBD** |
| 5 | Are burst length and duty cycle stated, and do they cover the intended 1–100 ms burst? | Yes for the intended duty. Intended duty is **TBD**. Firmware maximum is 20% | **TBD** |
| 6 | Is the transmit response stated, so a source-level goal can be turned into volts? | Response in hand. Source-level goal is **TBD** | **TBD** |
| 7 | Does the vendor allow the drive waveform we will actually use? | Square, sine, or either, in writing. Waveform choice is **TBD** | **TBD** |
| 8 | Is DC blocking required? | Yes or no from the datasheet | **TBD** |
| 9 | Is electrical isolation, shield wiring, and the wet connector specified? | Yes, including how the shield ties to the vehicle | **TBD** |
| 10 | Do depth rating, mounting, and connector fit the vehicle? | Yes for the planned depth. Depth requirement is **TBD** | **TBD** |
| 11 | Is directivity acceptable for a localization pinger? | Pattern in hand. Acceptable beam is **TBD** | **TBD** |
| 12 | Can an amplifier be specified from items 3–8 without guessing? | No amplifier selection until this is yes | **TBD** |

Reject the candidate if item 1 is no, or if items 3, 4, or 5 cannot be answered. A part without an impedance curve and a voltage limit is not enough information to build the power stage.

## Gate before any physical build

Construction of the driver, amplifier, match, or transducer cable waits until all of the following are true:

- The transducer checklist above is filled from documents, not from assumptions.
- Amplifier input levels accept a 5 V active-high enable and a 5 V square wave, or the firmware has been changed and re-verified for a different level or polarity.
- Pull-down values are calculated from the driver input leakage and the Arduino pin current, and written down. They are **TBD** today.
- The acoustic supply voltage and current are written down. They are **TBD** today.
- `TEST_PLAN.md` electrical steps are still planned with the transducer disconnected for the first power-up.

Host logic tests and the Uno compile do not satisfy this gate.
