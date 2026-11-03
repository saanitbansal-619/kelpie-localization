# Acquisition-record localization check

`pipeline.py` takes a `FourChannelRecord` (the Keysight reader's in-memory and NPZ layout) and calls the existing bandpass, shared-event window, GCC-PHAT, and `localize_from_tdoa`. Hydrophone coordinates are the stated 3+1 array, with H4 0.400 m below the triangle. The catalog geometry is left unchanged because that catalog recenters the array.

The virtual runner builds pulsed 25–40 kHz recordings with `generate_pinger_pulse` and `synthesize_pinger_capture`, wraps them in `FourChannelRecord`, and writes a new folder:

```
python -m simulations.scope_validation.run_virtual_validation
```

Outputs go to `results_scope_validation/`. The command refuses to write into `results/`, `results_h4_height_study/`, or `results_joint_geometry_optimization/`. Re-running replaces this study's own files.

`summary.md` in that folder is the numerical report. It is produced from the trial table. No oscilloscope or in-water measurement is part of this command.
