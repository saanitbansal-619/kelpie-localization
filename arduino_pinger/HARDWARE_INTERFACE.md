# Pinger hardware interface

This document is the boundary between the Arduino sketch and a transmitter that has not been designed yet. Every transducer and driver parameter below is **TBD** unless it is a property of the Arduino pin itself.

The sketch was not connected to hardware when it was written.

## Signal path

```text
Arduino Uno / classic Nano                External driver / PA                         Transducer
ATmega328P 16 MHz                         (NOT SELECTED)                               (NOT SELECTED)

D9 PB1 OC1A  ---- logic square wave ----> driver logic input  ---- power stage ----> transmitting element
D8 PB0       ---- burst enable ---------> driver enable
GND          ---- logic reference ------> driver input ground

Driver DC supply  TBD, separate from the Arduino 5 V pin
```

D9 is the Timer1 carrier. D8 is HIGH only while a burst is running and LOW on boot, when idle, and after `STOP`. The firmware assumes an active-high enable because idle must be LOW. Confirm that against the chosen driver datasheet before wiring. If the driver is active-low, stop and change the firmware. Do not invert it with an untested guess in the field.

## What D9 can and cannot do

| Parameter | Value | Status |
| --- | --- | --- |
| High level | About 5 V when unloaded, Arduino `VCC` | Arduino I/O, not a power output |
| Low level | Near 0 V | Arduino I/O |
| Pin absolute max current | 40 mA per ATmega328P pin, 20 mA recommended continuous | Not enough to drive a projector |
| Wave shape | Square wave from OC1A toggle | Harmonics are part of the logic signal |
| Frequency | 25–40 kHz requested, actual rate reported on serial | See README table |

A 5 V GPIO must not be wired to the transducer terminals. It also must not be wired into the receiver chain.

## Driver input requirements to check later

When a driver or amplifier is chosen, record these before connecting D8 or D9:

| Item | Status |
| --- | --- |
| Input voltage range and whether 5 V GPIO is legal | TBD |
| 3.3 V versus 5 V logic | TBD |
| Input impedance | TBD |
| Enable polarity and enable threshold | TBD. Firmware is idle-LOW, burst-HIGH. |
| Quiescent and burst current from the driver supply | TBD |
| Gain, output voltage, and output current | TBD |
| Output impedance and transducer match | TBD |
| Bandwidth and what it does with square-wave harmonics | TBD |
| Fault, thermal, and output-disable behavior | TBD |
| Need for series resistor, DC block, or low-pass between D9 and the driver | TBD |

Until those rows are filled, the only safe electrical load on D9 is a scope probe or a high-impedance logic input that is known to accept 5 V.

## Power, ground, isolation, protection

- Power the Arduino from USB for firmware and bench probing only.
- The acoustic power supply is **TBD**. Do not plan to run the projector from the Arduino 5 V pin or from the USB port.
- Share a logic ground between Arduino GND and the driver input reference only if the driver datasheet says the input is ground-referenced. Isolation between that logic ground, the projector supply, and the vehicle hull is **TBD**.
- During reset and while the bootloader runs, D8 and D9 float. Before a driver is connected, fit pull-downs from D8 to GND and from D9 to GND so a floating pin cannot enable the amplifier. Resistor value is **TBD** (a starting point to check against the driver input spec is 10 kΩ; do not treat that as a final design).
- Series protection, TVS diodes, current limit, and DC blocking between the amplifier and the transducer are **TBD**.
- Do not connect the pinger and the receiver grounds together in the water without a written grounding plan. That plan is **TBD**.

## Impedance

Transducer impedance at 25–40 kHz, cable capacitance, and the matching network are **TBD**. Do not assume 50 Ω, and do not assume the logic square wave is what the element should see. Many projectors want a sine near resonance. A later filter or a gate-drive plus H-bridge may be required. That topology is **TBD**.

## Parts that are not the transmitter

The Aquarian S1f is an IEPE receive hydrophone. Do not use it as a transmitting element. Do not drive it from D9, from a power amplifier, or from a reversed receive channel. Transmitting into an IEPE sensor can destroy the hydrophone and the conditioner.

The PCB 482C05 is a signal conditioner for IEPE sensors in the receive path. It is not a transmit amplifier. Do not connect D8 or D9 to its sensor inputs or outputs.

The Keysight MSOX2014A is a measurement tool. It is not part of the underwater signal path. The Keysight 33500B, if used, is a bench reference or counter, not the vehicle pinger.

## Square wave versus acoustic output

OC1A toggle produces a near-50% logic square wave. Its spectrum is the fundamental plus odd harmonics. The transducer and driver will not radiate that spectrum unchanged. Source level, directivity, and harmonic content in the water are **TBD** and are not properties of this firmware.

## Suggested connection order, once a driver exists

1. Firmware uploaded, `STOP` state confirmed, pull-downs fitted, driver supply off.
2. Scope on D9 and D8 at the Arduino, transducer still disconnected.
3. Confirm idle LOW, then `START`, then `STOP`.
4. Only then connect the driver input, with the driver supply still off, and repeat the scope check at the driver input.
5. Transducer connection and acoustic tests stay blocked until the TBD rows above are filled and the bench test plan's electrical section has recorded measurements.
