"""Key numbers for the simple homestead layouts (docs/simple-build.md).

For each layout x soil: earthwork, water held, deep-water area for fish to overwinter,
land vs water, a rough yearly water balance, and the build estimate for each machine.

    python3 tools/homestead_numbers.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "ring_engine")
sys.path.insert(0, ENGINE)

import numpy as np  # noqa: E402

from config import load_config  # noqa: E402
from conventional import estimate, load_machines, moat_geometry  # noqa: E402
from terrain_engine import Terrain  # noqa: E402

PARAMS = os.path.join(ENGINE, "homestead_params.json")

LAYOUTS = {
    "first_try": {"label": "First try: 15 m deep ring, berms sized to take all the spoil, 3:1 banks", "overrides": [
        'moats=[{"r_in": 18.0, "r_out": 33.0, "depth": 2.44}, {"r_in": 55.0, "r_out": 65.0, "depth": 1.2}]',
        'berms=[{"r_in": 39.0, "r_out": 49.0, "height": null, "source_moat": 0},'
        ' {"r_in": 71.0, "r_out": 85.0, "height": null, "source_moat": 1}]',
        'balance.auto_size_berms=true', 'soil.canal_side_slope_deg=18.43', 'grid.extent_m=92.0']},
    "simple": {"label": "Simple: 1.5 m fish ring + winter holes, 0.9 m plant ring, 0.9 m flat berms", "overrides": []},
}
WINTER_HOLES = {"count": 2, "depth_ft": 10, "top_m": 12.0, "side_slope_h": 2.0}
SOILS = {
    "ne_till": {"label": "New England till, 6 ft slope", "overrides": ['soil.preset="ne_glacial_till"'],
                "rain_m": 1.2, "evap_m": 0.65},
    "florida": {"label": "Florida sand, flat", "overrides": ['soil.preset="florida_sand"', 'site={"type": "flat"}'],
                "rain_m": 1.35, "evap_m": 1.3},
}
FT = 0.3048


def numbers(layout, soil, res=384):
    # keep the homestead's slopes when a soil preset is applied on top
    keep = ['soil.canal_side_slope_deg=26.57', 'soil.angle_of_repose_deg=18.43']
    ov = SOILS[soil]["overrides"] + keep + LAYOUTS[layout]["overrides"] + ["grid.resolution=%d" % res]
    cfg = load_config(PARAMS, ov)
    T = Terrain(cfg)
    A = T.cell_area
    out = {"layout": LAYOUTS[layout]["label"], "soil": SOILS[soil]["label"],
           "site_diameter_m": 2 * cfg.r_max, "site_area_m2": math.pi * cfg.r_max ** 2,
           "cut_bank_m3": T.design_cut_total, "fill_loose_m3": T.design_fill_total,
           "max_cut_m": T.max_depth, "rings": [], "berms": []}
    water_area = 0.0
    for m, wl in enumerate(T.water_levels):
        mask = T.moat_id == m
        depth = np.clip(wl - T.design[mask], 0.0, None)          # water depth at each cell
        wet = depth > 0
        area = float(wet.sum() * A)
        water_area += area
        out["rings"].append({
            "ring": m, "water_m3": float(depth.sum() * A), "water_area_m2": area,
            "max_water_depth_m": float(depth.max()),
            "area_deeper_6ft_pct": 100.0 * float((depth > 6 * FT).sum()) / max(wet.sum(), 1),
            "area_deeper_8ft_pct": 100.0 * float((depth > 7.9 * FT).sum()) / max(wet.sum(), 1)})
    for k, b in enumerate(T.design_report["berms"]):
        bm = T.berm_id == k
        h = (T.design - T.z0)[bm]
        crown = float((h >= 0.95 * h.max()).sum() * A)
        out["berms"].append({"berm": k, "crown_height_m": b["crown_height_m"], "footprint_m2": float(bm.sum() * A),
                             "flat_crown_m2": crown,
                             "flat_crown_width_m": crown / (2 * math.pi * 0.5 * (b["r_in"] + b["r_out"]))})
    island = math.pi * cfg.hub_radius ** 2
    land = island + sum(b["footprint_m2"] for b in out["berms"])
    out.update({"island_m2": island, "water_area_m2": water_area, "land_m2": land,
                "land_to_water": land / water_area})
    # Spoil the berms don't take raises the island, then goes to an uphill diversion bund.
    sf = cfg.swell_factor
    hole = WINTER_HOLES
    d_h = hole["depth_ft"] * FT - next(r for r in out["rings"])["max_water_depth_m"]   # extra below the ring bed
    bot = max(hole["top_m"] - 2 * hole["side_slope_h"] * d_h, 1.0)
    v_hole = d_h / 3.0 * (hole["top_m"] ** 2 + bot ** 2 + hole["top_m"] * bot) * hole["count"]
    loose = sf * (T.design_cut_total + v_hole)
    surplus = loose - T.design_fill_total
    raise_m = min(max(surplus, 0.0) / island, 1.0)
    out["spoil"] = {"winter_holes_bank_m3": v_hole, "loose_total_m3": loose, "berms_take_m3": T.design_fill_total,
                    "surplus_m3": surplus, "island_raise_m": raise_m,
                    "to_bund_m3": max(surplus - raise_m * island, 0.0)}
    rain, evap = SOILS[soil]["rain_m"], SOILS[soil]["evap_m"]
    out["water_balance"] = {"rain_on_site_m3_yr": rain * out["site_area_m2"],
                            "evaporation_from_rings_m3_yr": evap * water_area,
                            "rings_volume_m3": sum(r["water_m3"] for r in out["rings"])}
    data = load_machines()
    geo = moat_geometry(T, cfg)
    geo[0]["V_bank_m3"] += v_hole           # the excavator digs the winter holes too
    out["build"] = {}
    for key, mach in data["machines"].items():
        e = estimate(cfg, T, mach, data["job"], geo)
        out["build"][key] = {"machine": e["machine"], "days": e["working_days"], "cost_usd": e["cost_usd"],
                             "full_depth": e["reaches_full_depth"]}
    return out


def main():
    allres = []
    for lay in LAYOUTS:
        for soil in SOILS:
            r = numbers(lay, soil)
            allres.append(r)
            wb = r["water_balance"]
            print("\n%s | %s" % (r["layout"], r["soil"]))
            print("  site %.0f m across (%.2f ha); cut %s m3 bank, deepest cut %.2f m"
                  % (r["site_diameter_m"], r["site_area_m2"] / 1e4, "{:,.0f}".format(r["cut_bank_m3"]), r["max_cut_m"]))
            for g in r["rings"]:
                print("  ring %d: %s m3 water, %s m2 surface, max %.1f m deep; %.0f%% of area > 6 ft, %.0f%% > 8 ft"
                      % (g["ring"], "{:,.0f}".format(g["water_m3"]), "{:,.0f}".format(g["water_area_m2"]),
                         g["max_water_depth_m"], g["area_deeper_6ft_pct"], g["area_deeper_8ft_pct"]))
            for b in r["berms"]:
                print("  berm %d: crown %.2f m high, flat top %.1f m wide (%s m2)"
                      % (b["berm"], b["crown_height_m"], b["flat_crown_width_m"], "{:,.0f}".format(b["flat_crown_m2"])))
            print("  land %s m2 (island %s) : water %s m2 = %.2f : 1"
                  % ("{:,.0f}".format(r["land_m2"]), "{:,.0f}".format(r["island_m2"]),
                     "{:,.0f}".format(r["water_area_m2"]), r["land_to_water"]))
            sp = r["spoil"]
            print("  spoil %s m3 loose (incl. winter holes %s m3 bank); berms take %s; surplus %s -> island +%.2f m, bund %s m3"
                  % ("{:,.0f}".format(sp["loose_total_m3"]), "{:,.0f}".format(sp["winter_holes_bank_m3"]),
                     "{:,.0f}".format(sp["berms_take_m3"]), "{:,.0f}".format(sp["surplus_m3"]), sp["island_raise_m"],
                     "{:,.0f}".format(sp["to_bund_m3"])))
            print("  rain on site %s m3/yr, evaporation %s m3/yr, rings hold %s m3"
                  % ("{:,.0f}".format(wb["rain_on_site_m3_yr"]), "{:,.0f}".format(wb["evaporation_from_rings_m3_yr"]),
                     "{:,.0f}".format(wb["rings_volume_m3"])))
            for k, b in r["build"].items():
                print("  %-46s %6.0f days  $%9s  %s" % (b["machine"], b["days"], "{:,.0f}".format(b["cost_usd"]),
                                                       "" if b["full_depth"] else "(can't reach full depth)"))
    with open(os.path.join(os.path.dirname(HERE), "docs", "homestead_numbers.json"), "w") as fh:
        json.dump(allres, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
