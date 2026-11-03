# Software readiness audit

Audit date: 2026-11-01, laptop only. No oscilloscope, Arduino board, conditioner, hydrophone, amplifier, or transducer was connected. No file was deleted. Historical result folders were not regenerated.

This document records commands that were run in this audit and the files they wrote or read. Simulation tables below are synthetic. They are not tank or bench measurements.

## What exists

| Area | Path | Role |
| --- | --- | --- |
| Signal processing | `src/` | Chirp and pinger synthesis, DC removal, zero-phase bandpass, shared-event window, GCC-PHAT, geometry catalog, least-squares localization |
| Acquisition | `acquisition/` | Keysight MSOX2014A reader, in-memory mock, NPZ/CSV. Live VISA is imported only when a real session is opened |
| Acquisition-to-localization | `simulations/scope_validation/` | Stated 3+1 coordinates, `FourChannelRecord` in, existing filter / GCC-PHAT / solver out |
| Pinger firmware | `arduino_pinger/robosub_pinger/` | One sketch, `robosub_pinger.ino`, plus `pinger_logic.h` |
| Pinger host checks | `arduino_pinger/test_pinger_logic.cpp`, `run_host_verification.ps1` | Logic tests and Uno compile. The script does not upload |
| Pinger hardware notes | `PINGER_HARDWARE_REQUIREMENTS.md`, `PINGER_INTERFACE.md`, `PINGER_VALIDATION_CHECKLIST.md` | Requirements only. No amplifier or transducer is selected |
| Frame CAD | `robosub_pvc_cad_v2/robosub_pvc_cad_v2/` | STEP/STL prototype. The CAD README says it is not fit-tested |
| Older simulations | `simulations/geometry_study`, `noise_study`, `waveform_study`, `hydrophone_count_study`, `geometry_pair`, `h4_height_study`, `joint_geometry_study` | Preserved studies. Their result directories were not rerun |
| Tests | `tests/` | 100 collected tests |

GCC-PHAT and `localize_from_tdoa` each have one implementation, in `src/tdoa.py` and `src/localization.py`. The scope-validation pipeline calls those functions. There is one pinger sketch.

## Commands run for this audit

From the repository root, Python 3.11.7, pytest 7.4.0:

```powershell
python -m pytest tests -q --tb=line
powershell -ExecutionPolicy Bypass -File arduino_pinger\run_host_verification.ps1
python -m simulations.scope_validation.run_virtual_validation
```

Results:

- Pytest: **99 passed, 1 failed**, 4.18 s. The failure is `tests/test_localization.py::test_volumetric_arrays_recover_a_known_source_from_true_tdoas`.
- Pinger host binary printed `ok`. `arduino_pinger/HOST_VERIFICATION.md` was regenerated at 2026-11-01 23:23:13 -05:00. Assertion failures: 0. Uno compile: PASS, 6936 bytes flash (21%), 403 bytes RAM (19%). The script did not upload.
- Scope-validation runner finished at 2026-11-01 23:26:36 -05:00. Geometry trials: 96. Solver successes: 72. Reliable: 38. Output stayed in `results_scope_validation/`. `physical_measurement` in `run_manifest.json` is false.

A separate laptop check built a 10 000-point synthetic record, quantized it into the mock scope, captured it with `KeysightMSOX2014A`, saved NPZ, and localized both the original record and the mock record. Details are under the acquisition section. That check is not a pytest and did not write into a result folder.

These full experiment scripts were **not** executed, so their saved CSVs stay as historical simulation output:

- `simulations/geometry_study/run_geometry_study.py`
- `simulations/noise_study/run_noise_experiment.py`
- `simulations/waveform_study/run_waveform_experiment.py`
- `simulations/hydrophone_count_study/run_hydrophone_count_study.py`
- `simulations/geometry_pair/run_change1.py` and `run_change2.py`
- `simulations/h4_height_study/run_h4_height_study.py`
- `simulations/joint_geometry_study/run_joint_geometry_study.py`

Their unit tests, which do not rewrite those folders, are included in the 99 passes.

## PASS / FAIL / NOT TESTED

| Subsystem | Result | Evidence |
| --- | --- | --- |
| Python package imports (`src`, `acquisition`, scope-validation, geometry and waveform pipelines) | PASS | Import check, no failures. `acquisition` imports without PyVISA |
| Preprocessing, detection, GCC-PHAT, geometry formulas, pinger waveform, noise definition | PASS | Included in the 99 passing tests |
| Catalog localization, tetrahedron, exact TDOAs for source (3, −1.2, 2) m | PASS | Error about 2e-13 m, residual 0 |
| Catalog localization, `three_plus_one`, same exact TDOAs | FAIL | Solver returned success at (2.001, −0.809, 1.329) m. Position error 1.266 m. Reported residual 0. The returned point's geometry TDOAs match the source TDOAs at printed microsecond precision |
| Stated hardware coordinates, exact TDOAs | PASS | Same source error about 1e-13 m. All six scope-validation sources recovered with error 0 at printed precision |
| Stated-geometry synthetic waveforms through `FourChannelRecord` | PASS | `tests/test_scope_localization.py` (8 tests) and the virtual runner |
| Keysight mock versus the real record interface | PASS | Mock capture is a `FourChannelRecord`: shape (4, N), one `time_s`, one `sample_interval_s`. NPZ reload kept samples, time, and interval bit-for-bit on the 10 000-point bridge |
| Four-channel timing metadata | PASS | Bridge: interval 3.90625 µs, time steps matched that interval, time origin 0, channel ids CH1..CH4, hydrophone ids H1..H4. One `:DIGitize CHANnel1,CHANnel2,CHANnel3,CHANnel4` |
| Mock record into the localizer | PASS | After byte scaling, solver success and reliable were true. Position error 0.037 m and max TDOA error 0.090 µs, the same figures as the unquantized synthetic record |
| Live MSOX2014A / VISA | NOT TESTED | PyVISA is not installed. No resource was opened. `instrument_verified` remains false |
| Pinger command logic, Timer1 arithmetic, mocked `micros()` | PASS | Host report, 0 failures. Largest divider error on the 500 Hz grid: 39500 Hz requested, timer 39408.8669 Hz, −0.2307%. This is integer arithmetic at 16 MHz, not a scope reading |
| Pinger Uno compile | PASS | arduino-cli  compile of `arduino:avr:uno`, 6936 / 403 bytes. CLI path is the Arduino IDE 2 bundle, not a `PATH` entry |
| Pinger on a board, pins, jitter, acoustics | NOT TESTED | Host report physical checklist is NOT RUN. No upload |
| Transmit amplifier and projector | NOT TESTED | Requirements documents only. Component values are still TBD |
| PVC frame fit and in-water geometry | NOT TESTED | CAD README: not fit-tested. Tip coordinates are targets |
| Preserved Monte Carlo studies | NOT TESTED this audit | Folders were left in place. Their own manifests remain the record of those runs |
| ROS, Jetson, realtime | NOT TESTED | No such software is in the repo |

## Geometry check

The localization study uses these metres, channel 0 = H1:

| Hydrophone | x (m) | y (m) | z (m) |
| --- | ---: | ---: | ---: |
| H1 | 0.1443376 | 0 | 0 |
| H2 | −0.0721688 | 0.125 | 0 |
| H3 | −0.0721688 | −0.125 | 0 |
| H4 | 0 | 0 | −0.400 |

Checked in this audit:

- The array in `simulations/scope_validation/pipeline.py` matches those literals.
- Classification is volumetric.
- H2–H3 is 0.250 m. H1–H4 is the longest pair, 0.425245 m.
- At 1480 m/s the physical |TDOA| limit is 287.33 µs.
- The triangle centroid of H1..H3 is at the origin. The four-phone centroid is not. The catalog helper `make_three_plus_one` recenters the array and places H4 on the positive side of the shifted triangle. It is a different coordinate list. The scope-validation tests reject that substitution.
- CAD tip targets in `robosub_pvc_cad_v2/robosub_pvc_cad_v2/README.md` are (144.338, 0, 0), (−72.169, 125, 0), (−72.169, −125, 0), and (0, 0, −400) mm. Those match the table at the CAD note's 0.001 mm rounding. The CAD note still says the acoustic center of the real S1f has to be measured.

`acquisition/waveform.py` still stores `absolute_coordinates_m` and `triangle_side_m` as the string `TBD` inside every capture's metadata. `localize_record` does not read metadata. A scope file does not, by itself, select the coordinate table above. The caller has to pass `stated_hydrophones_m()`.

## Acquisition interface

The mock answers the same SCPI strings the driver sends, including one digitize of CH1..CH4 and IEEE 488.2 blocks. `tests/test_msox_acquisition.py` passed inside the full suite (scaling, preamble, alignment, timeout, NPZ/CSV, illegal point count).

The 10 000-point bridge used a legal `:WAVeform:POINts` value, sample interval `1/256000` s, and the driver class pointed at `ScriptedMSOX`. Reload through `save_npz` / `load_npz` preserved `samples`, `time_s`, and `sample_interval_s`. `instrument_verified` was false and `backend` was `mock`.

The stock demo mock is 4×8 samples. That record is a valid `FourChannelRecord`, and it is shorter than the localizer's 4 ms + 6 ms window. The bridge above is the compatibility check that uses a capture long enough to localize.

Caller-chosen point counts are limited to the programmer's-guide list. A count reported by the instrument is not checked against that list before the driver sends `:WAVeform:POINts`. That path is untested on hardware.

## Virtual localization, this audit's rerun

Synthetic only. Seed base 20261101. Sample rate 256 kHz. Bandpass 15–45 kHz. Six sources, carriers 25/30/35/40 kHz, SNR noise-free / 20 / 10 / 0 dB.

| SNR | Trials | Solver success | Reliable |
| --- | ---: | ---: | ---: |
| noise-free | 24 | 24 | 21 |
| 20 dB | 24 | 23 | 17 |
| 10 dB | 24 | 12 | 0 |
| 0 dB | 24 | 13 | 0 |
| All | 96 | 72 | 38 |

All 24 rejections are `no_bounded_solution`. Reliable means the solver accepted a position and the waveform flags were clear. Those flags do not use the known source. On the reliable subset the median position error is 0.068 m, the 95th percentile is 0.186 m, and the maximum is 0.526 m. Across every solver success the maximum is 131.2 m, and that trial is flagged unreliable. Three noise-free successes were flagged for envelope disagreement with position error still under 0.084 m.

The contrast floor is 6. The study report states that a floor of 3 was tried on this same grid first and left the 131 m solve marked reliable. The numbers above are from the rerun with the floor at 6.

Injected H2 delays at 30 kHz, source (2, 1, 1.5) m, stayed reliable. One carrier period (8.5333 samples) moved the position by about 0.86 m noise-free and 0.86 m at 20 dB, with mean |TDOA| error 0.055 µs and 0.205 µs against the delayed ground truth.

Full tables and plots: `results_scope_validation/summary.md`.

## Pinger firmware configuration

From `pinger_logic.h`, compiled into the sketch that passed the Uno build:

| Setting | Value |
| --- | --- |
| CPU assumed by the divider math | 16 MHz |
| Carrier | 25–40 kHz, step 500 Hz, default 30 kHz |
| Period | 500–2000 ms, default 1000 ms |
| Burst | 1–100 ms, default 10 ms |
| Serial commands | START, STOP, HELP, STATUS, FREQ, PERIOD, PULSE, TEST |

Host tests cover anchor OCR values, the full 31-point grid, rejected signs, overflow, trailing junk, START/STOP state, and a mocked microsecond rollover. They do not toggle D8 or D9.

## Defect left in place

`test_volumetric_arrays_recover_a_known_source_from_true_tdoas` fails on the catalog `three_plus_one` array only. Tetrahedron passes. For source (3, −1.2, 2) m the solver reports success and residual 0 at a second point whose own geometry TDOAs match the input. The ambiguity check can reject two low-residual basins only when both basins are among the multi-start results. In this case it returned one exact-fit basin and treated it as unique.

The stated hardware array, which is not the recentered catalog array, recovers that source and the six virtual-test sources from exact TDOAs. The solver was not modified in this audit. Changing the multi-start would change later reruns of the preserved studies, and those studies were not rerun here.

## Documentation and dependencies

Out of date relative to the code that is actually present:

- `README.md` still says the repository is not a firmware project, and the current-phase section stops at the geometry, hydrophone-count, and noise studies. Hardware validation is listed as not done, which remains true, while the pinger, acquisition module, and scope-validation runner are easy to miss.
- `PROJECT_STATUS.md` ends at the same older phase.
- `acquisition/HARDWARE_VALIDATION.md` still marks triangle side and absolute coordinates TBD. The design targets now exist in the CAD note and in `stated_hydrophones_m()`, and they are still not a survey.
- `src/__init__.py` still says hardware acquisition is outside that package. That sentence matches the layout.

Dependencies in `requirements.txt`: numpy, scipy, matplotlib, pytest, pyvisa. The first four imported and the suite ran. **PyVISA is not installed** in this Anaconda environment (`ModuleNotFoundError`). The mock path does not need it. `python -m acquisition.cli discover` and any `--resource` capture will fail until PyVISA and a VISA backend are installed.

No second copy of the sketch, the solver, or GCC-PHAT turned up. The CAD directory is nested (`robosub_pvc_cad_v2/robosub_pvc_cad_v2/`). That is one design, not two competing trees. Nothing was deleted.

## Simulation versus measurement

| Record | Kind |
| --- | --- |
| `results/`, `results_h4_height_study/`, `results_joint_geometry_optimization/`, and the study folders under `simulations/*/results` | Earlier synthetic experiments. Not rerun here |
| `results_scope_validation/` | Synthetic rerun during this audit, 2026-11-01 23:26 |
| `arduino_pinger/HOST_VERIFICATION.md` | Host logic plus an Uno compile. Pin and acoustic rows are NOT RUN |
| `acquisition/HARDWARE_VALIDATION.md` | Every hardware row is NOT RUN or TBD |
| Scope `instrument_verified` | False on mock captures and on synthetic records |

## Blockers before physical testing

1. Install PyVISA and a working VISA backend. Confirm `python -m acquisition.cli discover` lists the MSOX2014A. This machine cannot open the scope today.
2. Do not upload the sketch until the bench plan in `arduino_pinger/TEST_PLAN.md` is in front of the operator. The compile does not program the board. D8 still needs the hardware pull-down described in the interface notes before a driver is attached. Amplifier, supply, and transducer are unspecified.
3. Do not connect a transmitter output to the scope inputs, and do not drive an Aquarian S1f as a speaker. The S1f and PCB 482C05 are the receive chain.
4. Survey the four acoustic centers. The metres in this audit are the design target, including the CAD tip targets, not a measurement of the built frame.
5. Confirm which conditioner output is plugged into CH1..CH4. The software labels are a convention.
6. Measure the sound speed used for that water. The solver default is 1480 m/s.
7. Leave volts-to-pascals as TBD until the S1f sensitivity and the 482C05 gain are taken from their datasheets or a calibration.
8. The pytest suite is red on one catalog `three_plus_one` case. The stated array's checked exact-TDOA cases passed. Decide whether that second exact-fit basin must be rejected before field fixes are trusted. This audit did not change the solver.
9. A saved scope NPZ does not carry the stated XYZ. The first hardware localization has to pass `stated_hydrophones_m()` into `localize_record` explicitly.
10. There is no automated capture-to-position command. That is a missing operator step, not a failed test.

## Next actions, in order

1. Keep the historical result folders as they are.
2. Decide the catalog `three_plus_one` failure: reject the solve when a second exact TDOA fit exists, or document that source as an ambiguous catalog case and narrow the test. Do that in its own change, then rerun only the tests that cover the solver.
3. Install PyVISA. Run `discover` and `identify` on the MSOX2014A. Leave `instrument_verified` false until a person compares the NPZ with the scope screen.
4. On the bench, with the amplifier disconnected, upload the existing sketch and work the NOT RUN rows in `HOST_VERIFICATION.md`.
5. Update `README.md` and `PROJECT_STATUS.md` so the current phase includes the pinger, the acquisition module, and the synthetic scope-validation run.
6. After a surveyed array and a known in-water source exist, localize that NPZ with the stated coordinates and compare it with the surveyed source. That will be the first physical localization. It has not happened.

## Verdict

The repository is software-ready to **start** first hardware integration. The pinger sketch compiles, the host logic tests pass, the mock scope produces a `FourChannelRecord` the localizer can consume, and the stated four-hydrophone geometry recovers the synthetic cases that were checked.

It is not ready for a physical localization claim. PyVISA is missing, the scope and the board are untested, the transmitter is still a requirements document, and the coordinates are design targets. The test suite has one real failure on the catalog 3+1 array. That failure is a software caveat for the solver, and it is separate from the stated hardware coordinate list, which passed the exact-TDOA checks run here.
