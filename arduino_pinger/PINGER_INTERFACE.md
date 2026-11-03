# Pinger electrical interface

Electrical boundary between the existing firmware and a transmitter that has not been designed. Pin behavior below is what the sketch does. Everything on the far side of D8, D9, and GND is **TBD**.

No amplifier, series resistor, pull-down value, or transducer is selected here. A 10 kΩ pull-down mentioned in older notes is only a placeholder to compare with a future driver datasheet. It is not a chosen part.

## Pins

| Pin | MCU | Driven after `setup()` | During reset and the bootloader |
| --- | --- | --- | --- |
| D9 | PB1 / OC1A | Square-wave carrier while a burst is on. Forced low when idle and on `STOP` | High-impedance input |
| D8 | PB0 | High only during a burst. Low when idle and on `STOP` | High-impedance input |
| GND | GND | Logic reference for a ground-referenced driver input | Same copper, but the external supply may be off |

D9 high is Arduino `VCC`, about 5 V when the pin is unloaded. D9 low is near 0 V. These are logic levels. They are not a power output, and they do not set acoustic source level.

The firmware's enable polarity is active-high: idle and `STOP` are low. A driver that is active-low, or that only accepts 3.3 V, is not compatible with this sketch as it stands. Change the firmware and re-check the fail-safe before wiring that part. Do not invert a live amplifier on the vehicle as a field experiment.

`TEST_MODE` does not change these pins and does not disable an external amplifier.

## D9 carrier

Timer1 toggles OC1A in CTC mode, prescaler 1:

```text
f = 16000000 / (2 * (OCR1A + 1))
```

`OCR1A` is chosen so the divider is the integer nearest the requested frequency. The first half-cycle of a burst is low. `STOP` clears the toggle and drives the pin low before it drops D8, so the carrier is not left frozen at a high level while enable is still asserted.

The only load that is acceptable on D9 before a driver datasheet exists is a scope probe or another high-impedance input already known to accept 5 V. Do not connect D9 to a transducer, to an Aquarian S1f, or to the PCB 482C05.

| Driver-input question | Status |
| --- | --- |
| Legal input voltage, and whether 5 V CMOS is inside it | **TBD** |
| Input current at 5 V | **TBD**. Must stay within the Arduino pin limit |
| Need for a series resistor, buffer, or filter between D9 and the amplifier | **TBD** |
| What the amplifier does with odd harmonics of a 50% square wave | **TBD** |

## D8 enable

D8 is the burst gate.

- Low: amplifier must be off and must not deliver power to the transducer.
- High: amplifier may produce the carrier for that burst.
- Open or high-Z: must mean off. The pin is high-Z from reset until `setup()` finishes, including the Uno bootloader. Firmware cannot cover that window. `outputIdle()` has not run, and `TEST_MODE` does not run either.

| Driver-input question | Status |
| --- | --- |
| Enable threshold and polarity | **TBD**. Required polarity is idle-low, burst-high |
| Enable input current | **TBD** |
| Behavior if enable is open | **TBD** until the datasheet shows that open is off. If it does not, this firmware cannot be connected as-is |
| Time from enable high to a valid output, and from enable low to output off | **TBD**. Firmware `STOP` latency is about one serial line at 115200 baud plus the loop, not a hardware blanking time |

## Pull-downs and fail-safe enable

Both pins need an external pull-down to Arduino GND before a driver is attached.

- The D8 pull-down is the fail-safe. While the pin is high-Z, the resistor holds the enable line low so a floating input cannot turn the amplifier on.
- The D9 pull-down keeps the carrier input from drifting during that same window.
- Resistor values are **TBD**. They have to be large enough that a driven-high pin does not exceed the ATmega328P pin current, and small enough that the driver's input leakage still reads as a solid low. That tradeoff needs the driver input spec, which does not exist yet.
- The driver itself must treat a low input as disabled. A pull-down on an active-low enable would force the amplifier on during reset. That combination is not allowed with this firmware.

The pull-downs do not limit current into a low-impedance amplifier input, and they do not clamp a fault coming back from the power stage. Those parts are **TBD**.

## Power sequencing

Supplies:

- Arduino logic: USB is acceptable for firmware and bench probing.
- Acoustic power supply: **TBD**, and separate from the Arduino 5 V pin and from USB.
- Quiescent current and burst current of that supply: **TBD**.

Order while the circuit is still unknown:

1. Upload firmware. Confirm serial `STATUS` shows stopped. Driver supply off. Transducer disconnected.
2. Pull-downs fitted on D8 and D9.
3. Scope D8 and D9 at the Arduino. They must sit low after `setup()`. Note any high-Z interval during reset. That interval is expected. It is not a firmware pass.
4. `START`, then `STOP`. Carrier and enable only while started. `STOP` returns both pins low.
5. Connect the driver input with the driver supply still off. Repeat the scope check at the driver input.
6. Apply the driver supply only after enable is known low and the datasheet says the output may be powered with the transducer connected or explicitly disconnected. Which of those the part allows is **TBD**.
7. Transducer connection stays blocked until `PINGER_HARDWARE_REQUIREMENTS.md` is filled from datasheets and `TEST_PLAN.md` has real electrical measurements.

Power-down: send `STOP`, confirm D8 low, then remove the acoustic supply. Leaving the acoustic supply on while the Arduino is in reset is safe only because of the hardware fail-safe, and only after that fail-safe has been checked against the real driver. That check is **TBD**.

## Grounding

- Share Arduino GND with the driver input reference when the driver datasheet says the input is ground-referenced. Whether it is, is **TBD**.
- Isolation between logic ground, the acoustic supply, and the vehicle hull is **TBD**.
- Do not bond the transmitter ground to the receive-hydrophone ground in the water until a written grounding plan exists. That plan is **TBD**.
- A scope probe ground clips to Arduino GND. It does not clip to a hull or to an amplifier output.

## Protection

Required behavior, with the implementation **TBD**:

| Threat | Required behavior | Implementation |
| --- | --- | --- |
| High-Z enable at reset | Amplifier stays off | Pull-down on D8, value **TBD**, plus a driver that treats low or open as off |
| GPIO over-current | D8 and D9 stay inside the pin current limit | Series element or buffer, **TBD** |
| Amplifier fault back into the GPIO | Pin voltage stays inside the ATmega328P absolute maximum | Clamp and series element, **TBD** |
| DC into a transducer that cannot take it | No DC at the element | Coupling method **TBD** after the transducer DC rating is known |
| Over-voltage or over-current at the element | Stay under the transducer maximum | Amplifier limit and/or series protection, **TBD** |
| Thermal overload of the amplifier | Output disables without asserting itself on | **TBD** from the amplifier datasheet |
| Transmit energy into the IEPE receiver | No copper path from D8, D9, or the PA output to an S1f or the 482C05 | Wiring rule, not a part |

Do not draw a final schematic until the transducer impedance, voltage, current, duty cycle, and isolation rows in `PINGER_HARDWARE_REQUIREMENTS.md` are no longer **TBD**.
