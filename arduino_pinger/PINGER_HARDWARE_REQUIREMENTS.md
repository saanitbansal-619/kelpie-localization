# Pinger transmitter hardware requirements

Requirements for a future underwater transmitter driven by the existing Arduino pinger firmware. No transmitting transducer, matching network, or power amplifier has been selected. Every part parameter that is not a property of the firmware or of the Arduino pin is **TBD**. This document does not choose parts and does not define a finished circuit.

The sketch has been compiled for an Uno. It has not been run on a board, and it has not been connected to a driver or a transducer.

Related notes: `PINGER_INTERFACE.md` (D8 and D9), `PINGER_VALIDATION_CHECKLIST.md` (what has to be measured), `HARDWARE_INTERFACE.md`, `TEST_PLAN.md`.

## System

```text
Logic, already specified                         Power path, not designed

Arduino Uno R3 or classic Nano                   Protected driver interface     TBD
ATmega328P, 16 MHz                               (level, current limit,
D9  carrier, Timer1 OC1A square wave  -------->  fail-safe enable, fault
D8  active-high burst enable                     isolation from the PA)
GND logic reference                              |
USB 5 V powers the Arduino only                  v
                                                 Power amplifier               TBD
                                                 supply separate from USB      TBD
                                                 |
                                                 v
                                                 Matching network              TBD
                                                 include only if the
                                                 transducer requires it
                                                 |
                                                 v
                                                 Transmitting transducer       TBD
                                                 |
                                                 v
                                                 Underwater acoustic output
                                                 source level, pattern,
                                                 and spectrum                  TBD

Not in this path:

Four Aquarian S1f hydrophones -> PCB 482C05 IEPE conditioner -> existing receiver
```

The protected driver interface, amplifier, matching network, and transducer are separate decisions. None of them is a resistor value, IC, or projector model yet.

The Aquarian S1f is a receive hydrophone. The PCB 482C05 is the receive-path IEPE conditioner. Neither one is a transmitting element or a transmit amplifier. Do not drive an S1f from D9 or from the power amplifier.

## What the firmware already fixes

| Item | Value |
| --- | --- |
| Carrier pin | D9, Timer1 OC1A, toggle, about 50% logic square wave |
| Enable pin | D8, HIGH only during a burst, LOW when idle and after `STOP` |
| Requested carrier | 25000–40000 Hz, steps of 500 Hz. Default 30000 Hz |
| Timer frequency | `16000000 / (2 * (OCR1A + 1))`. Serial prints truncated hundredths. 30000 Hz request produces 29962.54 Hz on the wire |
| Burst length | 1–100 ms. Default 10 ms |
| Repetition | 500–2000 ms, start to start. Default 1000 ms |
| Burst must be shorter than the period | Enforced. With these limits the longest commandable on-time fraction is 100 ms / 500 ms = 20%. The default is 10 ms / 1000 ms = 1% |
| First half-cycle of each burst | Low, because OC1A is armed while the pin is held low |
| `STOP` | Disconnects OC1A, drives D9 low, then drives D8 low |
| `TEST_MODE` | Serial warning only. `START` still drives D8 and D9 |

The mission carrier, burst length, and repetition, inside those limits, are **TBD**. The amplifier and transducer have to be rated for the duty cycle that will actually be commanded, and that duty cycle is **TBD**.

A burst can run long by about one serial line while a reply is printing, and the last carrier cycle is cut when the burst ends. The transmitter timing budget has to tolerate that. It is not a reason to add a second timer until a scope measurement says the stretch matters.

## Logic square wave and the sound in the water

D9 is a logic square wave. A 50% square wave is the fundamental plus odd harmonics (3rd, 5th, …) whose amplitudes fall as 1/n. For a carrier in 25–40 kHz, the 3rd harmonic sits in 75–120 kHz and the 5th in 125–200 kHz.

A resonant transmitting transducer is a mechanical filter. It radiates most strongly near its resonance and much less far from that resonance. Energy at the fundamental and energy at the harmonics are not radiated in the same proportion as they exist on D9. If the resonance is narrow and is tuned to the carrier, the pressure waveform can look closer to a sine than to the GPIO square wave. How close, and which harmonics remain, depends on the transducer's transmit response and on whatever filtering or matching sits in front of it. Those responses are **TBD**.

Consequences for the parts that are not chosen yet:

- Source level is a property of drive voltage, transducer response, and direction. It is not the 5 V edge on D9.
- A later stage may need to attenuate harmonics before the amplifier, or the transducer's own resonance may do that. The topology is **TBD**. Do not assume a sine-output amplifier, and do not assume the element can accept a square wave.
- The receiver's processing (including the localization experiments) assumes an acoustic ping near the commanded carrier. Harmonic energy that the transducer does radiate can matter in the water. Whether it does is **TBD**.

## Specifications required before an amplifier is selected

Fill every row from a transducer datasheet or from a measurement of the actual element and cable. Do not select an amplifier against a guessed impedance or a guessed voltage.

| Specification | Why it gates the amplifier | Status |
| --- | --- | --- |
| Impedance versus frequency over 25–40 kHz, and at the 3rd and 5th harmonics | Sets output voltage, current, and whether a match is required | **TBD** |
| Resonance frequency and bandwidth | Chooses the carrier the vehicle will actually use, and how much of the square wave is radiated | **TBD** |
| Transmit response (pressure per volt, or the vendor's equivalent) | Turns a source-level goal into a drive voltage | **TBD**. Source-level goal is also **TBD** |
| Required drive voltage and current at that response | Amplifier output rating | **TBD** |
| Maximum allowed voltage and current | Amplifier must stay under this, not only meet a target | **TBD** |
| Power rating | Continuous and burst ratings are different | **TBD** |
| Allowed duty cycle and maximum burst length | Must cover the commanded 1–100 ms bursts at the intended repetition. Intended duty is **TBD**. Firmware can command up to 20% | **TBD** |
| Capacitance, and cable type, length, and capacitance | The amplifier load is the element plus the cable | **TBD** |
| Electrical isolation of the element, shield, and wet connector | Grounding and shock hazard once the vehicle is in the water | **TBD** |
| DC tolerance | Whether a series capacitor or a transformer is required | **TBD** |
| Drive waveform the vendor allows | Square, sine, or either | **TBD** |
| Depth, mounting, and connector | Mechanical, not an amplifier gain setting, but it decides if the part can go on the vehicle | **TBD** |

Until that table is filled, amplifier gain, supply voltage, output current, and matching network stay **TBD**. USB 5 V and the Arduino 5 V pin are logic power only. They are not candidates for the acoustic supply.

## Protected driver interface, still unbuilt

This block sits between the Arduino and the amplifier. Its job is fixed even though its circuit is not:

- Present a legal logic input to D8 and D9. Voltage range, input impedance, and 3.3 V versus 5 V are **TBD** until a driver exists.
- Hold the amplifier disabled when D8 is low, open, or high-impedance.
- Keep Arduino pin current inside the ATmega328P pin limit already recorded in `HARDWARE_INTERFACE.md` (40 mA absolute maximum per pin, 20 mA recommended continuous). The current this interface will actually draw is **TBD**.
- Stop an amplifier fault from back-driving D8 or D9. The clamp, series element, and voltage limit are **TBD**.
- Use a supply for the power stage that is separate from USB. Voltage and current are **TBD**.

Series resistors, TVS diodes, DC blocking, and filters are requirements to satisfy after the datasheets exist. They are not selected parts.
