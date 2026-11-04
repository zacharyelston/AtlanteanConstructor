# Atlantean Berm & Ring Engine

Parametric cut-and-fill simulator for concentric moats and berms built by a centre-pivot radial rig.
Pure Python + NumPy core; Blender 4.x/5.x front end (tested on Blender 5.0.1).

| File | Role |
|---|---|
| `params.json` | Geometry, soil (Sf, φ, β), rig, speeds, animation |
| `config.py` | Loads/validates params, `--set a.b=value` overrides, berm↔moat pairing |
| `terrain_engine.py` | 512² heightmap (bank + loose layers), design profiles, berm auto-sizing, cut / deposit / angle-of-repose relaxation, volumetrics, PNG output, Blender mesh I/O |
| `kinematics.py` | Archimedean-spiral or stepped-ring trajectory over multiple lifts, mass-haul chute mapping, cycle time, Blender rig hierarchy |
| `simulation_runner.py` | Main loop, telemetry, report, headless outputs, Blender scene/HUD/frame handler |

## Run

Headless (writes `output/`: `report.json`, `telemetry.csv`, top-down PNGs, `cross_section.svg/csv`):

```bash
python3 simulation_runner.py
python3 simulation_runner.py --res 256 --lifts 4 --path stepped --set soil.swell_factor=1.3 --png-every 30
```

Blender (opens the scene; scrub or play the timeline):

```bash
/Applications/Blender.app/Contents/MacOS/Blender --python simulation_runner.py
```

Background render or save:

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b --python simulation_runner.py -- --render-still out.png --still-frame 150 --save-blend rings.blend
/Applications/Blender.app/Contents/MacOS/Blender -b --python simulation_runner.py -- --render-anim ./frames/
```

The animation is driven by a `frame_change_pre` handler that holds the baked heightmaps in memory. A saved `.blend` file opens frozen on its saved frame. Re-run the script to animate it again.

## Model notes

- **Mass balance.** Each cell stores *bank* (in-situ) soil and *loose* spoil. Bank soil swells by Sf when cut. Re-scraped loose spoil does not swell again. The engine tracks `loose on ground + bucket = Sf × bank cut` at every step. The error is about 1e-9 m³.
- **Berm sizing.** Each berm's crown height is solved by bisection so that its volume equals Sf × the volume of the moat that feeds it. The flanks are capped at the angle of repose.
- **Mass-haul conveyor.** The discharge chute sits on the arm at the berm radius whose cumulative design-fill fraction equals the cumulative cut fraction at the scraper. This keeps the bucket from stalling.
- **Lifts.** Excavation goes down in `rig.lifts` layers. The path runs outward on odd lifts and inward on even ones.
- **Angle of repose.** A mass-conserving thermal-erosion pass moves only loose spoil, and only where the slope is steeper than tan φ.
- **Cycle time.** The kinematic time per step is `max(|Δθ|/v_θ, |Δr|/v_r, Δs/v_tool)`. The production-limited time also applies `production_rate_m3_hr`.
- **Display.** `animation.display_exaggeration` scales the relief in Blender only. Volumes always use true elevations.
