# Klipper speed limiter (Creality K1)

Klipper side of the speed-limit display: a Klipper "extra" that works out
**why the printer isn't printing faster** and publishes it as the
`speed_limiter` object. The patched Mainsail in this fork shows it under the
ETA row.

Built for the Creality K1 with the Guilouz Creality Helper Script: Klipper in
`/usr/share/klipper/klippy` (Creality fork, Python 3.8), config in
`/usr/data/printer_data/config`, Mainsail in `/usr/data/mainsail`.

## What it reports
`speed_limiter.py` wraps `toolhead.move` to tag each move as it is queued
(requested speed, M220 factor, E/XY ratio, Z/extruder caps). When Klipper
finalizes the move, a timing callback records its planned `cruise_v` and end
time. A 0.25 s timer classifies every move in the last 1.5 s of motion
(`speed_limiter_core.py`) and shows the reason covering most of that time,
with its share when mixed.

Reasons, in priority order: paused, G-code starvation, Z velocity cap,
extruder velocity cap, other kinematic cap, acceleration (short segments),
cornering, max velocity, speed override (M220), max volumetric flow, minimum
layer time, slicer feature speed (nothing printer-side is limiting).

Volumetric flow and minimum layer time are applied by the slicer, so Klipper
only sees a lower F. These two are heuristics and are shown with `~`. There
is nothing to configure: the flow cap is found per print, in this order:
1. `max_volumetric_flow` in `speed_limiter.cfg`, if you set it (0 turns flow
   detection off).
2. The per-filament `filament_max_volumetric_speed` that PrusaSlicer,
   OrcaSlicer and Creality Print write into the gcode file.
3. Inferred from the print: if a few seconds of extrusion sit at the same
   highest flow while the feedrate varies, that flow is treated as a cap. This
   is the least certain source and is for slicers that don't write the value.

The row says which source was used (for example "24.1 of 16.0 mm³/s, slicer
file"). Minimum layer time is read from the slicer settings in the gcode file
(PrusaSlicer, OrcaSlicer, Cura), or from `min_layer_time` if you set it.

## Install on the K1
1. Copy this folder to the printer, e.g.
   `scp -r klipper-speed-limiter root@<k1-ip>:/usr/data/`.
2. Run `sh install-k1.sh install`. It creates
   `/usr/data/printer_data/config/speed_limiter.cfg` (nothing in it needs
   setting), backs up `printer.cfg` and adds `[include speed_limiter.cfg]`
   above SAVE_CONFIG.
3. Restart Klipper when not printing. `install --restart` does this and
   refuses to restart mid-print.
4. Patched Mainsail: see the repository README.
   `sh install-k1.sh mainsail mainsail.zip` deploys a downloaded release zip
   (the old build is kept as `mainsail.bak`).
5. `sh install-k1.sh status` shows the Klipper/Python versions and any
   `speed_limiter` log lines. `sh install-k1.sh uninstall` removes everything.

## Caveats
- The internals used exist in upstream Klipper v0.10.0 and v0.11.0, but
  Creality's fork is unverified, and none of this has been run on a live
  printer.
- If the per-move hook fails, the extra logs the error and falls back to
  coarse polling (requested speed, max velocity and speed override only).
- If Creality's stock Klipper service rewrites `printer.cfg` on restart, check
  the include survived. The helper script's "prevent updating Klipper files"
  tool addresses that.

## Tests
- `python3 tests/test_core.py` runs the classifier tests.
- `KLIPPER_DIR=/path/to/klipper python3 tests/test_integration.py` runs
  against Klipper's real Move/lookahead classes.
