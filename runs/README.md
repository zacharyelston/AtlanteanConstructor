# Kept simulation runs

Outputs kept for historical review. `ring_engine/output/` is scratch space and
gitignored. When a run is worth keeping, it is copied here under a dated name,
and never edited afterwards. To reproduce a run, check out the code version
listed for it and rerun its command from `ring_engine/`.

| Run | What | Command | Code |
|---|---|---|---|
| [`2026-11-04_pivot_rig`](2026-11-04_pivot_rig/) | 410 m centre-pivot rig, 3 moats / 3 berms, 512² grid, 8 lifts. Fill/cut = Sf = 1.25 exactly; moats 99.8 % complete. | `python3 simulation_runner.py --png-every 60`; Blender stills with `-b --python simulation_runner.py -- --still-frame 150 --render-still ...` (and frame 300) | [`73f7d6c`](https://github.com/zacharyelston/AtlanteanConstructor/commit/73f7d6c) (the pivot rig is unchanged since; the flat-site regression reproduces the same volumes) |
| [`2026-11-04_compare_v1`](2026-11-04_compare_v1/) | First tethered-trencher matrix: 6 vehicles (Home 2WD; 4WD 15:1 and 24.8:1, ±ballast; 6WD 24.8:1, ±ballast) × 3 scenarios (NE till slope, NE till wet spring, Florida sand), 448² grid. | `python3 compare_sites.py --res 448 --max-hours 25000 --jobs 7` | Pre-release working tree, superseded by the commit that adds this folder. **Known issue:** the "Pull limit" column reads "grip 100 %" for every run because heat-limited cutting was counted as grip. v2 fixes the label, and the hours are unchanged. |
| [`2026-11-04_compare_v2`](2026-11-04_compare_v2/) | Final matrix: 9 vehicles (v1's set plus fan-cooled 6WD, train 3 × 4WD and train 2 × 6WD) × 3 scenarios, plus the tractor loader-backhoe baseline, fleet makespans and per-moat hours. Source of the README results. | `python3 compare_sites.py --res 448 --max-hours 25000 --jobs 7 --out output/compare_v2` | The commit that adds this folder |

Each `compare_*/<scenario>__<vehicle>/` folder holds:

- `report.json`: design, achieved volumes, mass-balance error, time breakdown,
  energy, limits, and the vehicle specification;
- `telemetry.csv`: state at every 10 % of progress;
- `log.txt`: the run's console summary;
- `existing.png`, `design.png`, `progress_*.png`, `final.png`: top-down
  hillshades (blue = cut, orange = fill against existing ground);
- `section.svg`: a section through the pivot along the slope, from the low
  side to the high side.

`COMPARISON.md` and `comparison.json` in each `compare_*` folder hold the
combined tables and every report.

**Naming:** these runs were made before the project was relabelled to "eOx",
so their reports and tables say "EOx". They are left unedited.

**Not kept:** an interrupted rerun between v1 and v2. It was stopped after 3
runs, when the loader-backhoe baseline and eOx trains were added.

All figures are screening estimates. Soil values are handbook figures, and the
machine rates and the fan-cooling factor are assumed. See the main
[README](../README.md#results-tractor-loader-backhoes-vs-eox-trenchers).
