# MSOX2014A hardware validation

No row below has been run. The laptop tests in `tests/test_msox_acquisition.py` check parsing, scaling, and a mock instrument. They do not check the MSOX2014A, the PCB 482C05, or the Aquarian S1f hydrophones.

Do not connect the Arduino pinger or any transmitter output to the oscilloscope inputs. The S1f is a receive hydrophone. The 482C05 is an IEPE conditioner, not a transmit amplifier.

Fill the TBD cells from datasheets or from the measurement itself. Do not copy the timer-formula frequencies from the pinger firmware into this table and call them scope readings.

## Before the first capture

| Item | Required state | Status |
| --- | --- | --- |
| Scope | Keysight MSOX2014A, four analog channels | **NOT CHECKED** |
| VISA | `python -m acquisition.cli discover` lists the scope | **NOT RUN** |
| Identity | `identify` prints an `*IDN?` string whose model is MSOX2014A | **NOT RUN** |
| Conditioner | PCB 482C05 powered as its datasheet requires. Gain copied from that datasheet | **TBD** |
| Hydrophones | Four Aquarian S1f, IEPE, each on its own conditioner channel | **TBD** |
| Cable map | Which S1f is CH1, CH2, CH3, CH4. The software default H1..H4 is only a label | **TBD** |
| Geometry | H4 is 400 mm below the upper triangle. Triangle side and coordinates | **TBD** |
| Scope coupling and probe | Conditioner output into the scope. Set probe attenuation to match the cable (1 if there is no 10× probe). This module does not send `:CHANnel:PROBe` | **NOT SET** |
| Input impedance | Publication 9018-06893 only lists `ONEMeg` for `:CHANnel:IMPedance`. Confirm the conditioner datasheet expects a 1 MΩ input | **TBD** |
| Timebase and trigger | Operator sets s/div and the trigger before capture. The module only forces `:TIMebase:MODE MAIN` | **NOT SET** |
| Vertical scale | Operator sets V/div so the conditioner output stays on screen. The module does not send `:CHANnel:SCALe` | **NOT SET** |

The capture command will turn CH1..CH4 display on, set `:ACQuire:TYPE NORMal`, and request `:WAVeform:POINts:MODE RAW`. Those are intentional. It will not change the trigger or the volts per division.

## Electrical capture

Use a known electrical signal from the conditioner or a function generator into all four scope channels only if the conditioner datasheet allows a generator on that input. Otherwise use a quiet tank and a separate acoustic source. Do not drive an S1f as a speaker.

| Step | Pass condition | Status |
| --- | --- | --- |
| `capture --resource … -o bench.npz --timeout 30` | Returns, and the printed line says `instrument_verified=False`. This software flag stays false until a person compares the file with the scope screen | **NOT RUN** |
| Timeout with the trigger forced idle | The command fails with a timeout instead of returning an old record | **NOT RUN** |
| NPZ `samples` shape | `(4, N)`, one `time_s` vector of length N, same `sample_interval_s` as the preamble X increment | **NOT RUN** |
| Scope screen after the command | Acquisition is stopped. All four traces are present from that stop, not from four later single-channel runs | **NOT RUN** |
| Serial error path | A deliberately illegal command is not part of this module. If `:SYSTem:ERRor?` is non-zero, the capture raises and names the queue text | **NOT RUN** |
| Sample interval | Record X increment. Compare it with the array's maximum TDOA only after the triangle size is known | **TBD** |
| RAW versus screen length | Compare N with the scope's memory depth and with the on-screen point count. The guide contains both "displayed data" and "raw record" wording | **NOT RUN** |

## Acoustic check, after the electrical rows pass

| Step | Pass condition | Status |
| --- | --- | --- |
| One ping in the water, four hydrophones connected | One NPZ. The four traces show the same ping at four times. No second `:DIGitize` between channels | **NOT RUN** |
| Relative delay | The earliest and latest arrivals differ by less than the array's maximum acoustic delay. That delay is **TBD** until the coordinates are | **NOT RUN** |
| Pressure | Not computed. Sensitivity and conditioner gain are **TBD** | **NOT RUN** |
| Gap-free stream | Not a test. This module does not stream | **NOT CLAIMED** |
| Segmented memory | Not a test. SGM commands are not sent | **NOT CLAIMED** |

## Evidence to keep

Store notes next to the NPZ, not in `results/` or `results_h4_height_study/`.

- `*IDN?` text
- Conditioner gain from the datasheet, still labeled as a datasheet value
- Cable map
- Scope s/div, V/div, coupling, probe factor, and trigger
- The NPZ, and a photograph of the stopped four-channel screen from that same capture
