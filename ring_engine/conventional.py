"""Construction baseline: tractor loader-backhoes (TLBs) digging the same Atlantean site.

Classic production estimating, applied moat by moat to the design from terrain_engine:

    backhoe  (bank m3/h) = bucket x fill factor / Sf x 3600 / (cycle x soil cycle factor) x efficiency
    loader   (loose m3/h) = 0.9 x loader bucket x 3600 / (fixed + 2 d / v) x efficiency

* Volume deeper than the machine's dig depth is dug from a bench in the moat (productivity x0.6).
* Volume below the water table is dug at x0.75, with a pump on site.
* If the berm is within the backhoe's reach the spoil is cast straight onto it; otherwise the
  backhoe piles it at the trench edge and the loader carries it (d = moat-to-berm centroid
  distance x path factor), then spreads it.
* Refusal stones (soils.json rate) cost each class its own delay; small machines can't lift big
  ones and lose extra time on them.

    python3 conventional.py --soil ne_glacial_till
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

MACHINES_PATH = os.path.join(HERE, "vehicles", "conventional_machines.json")


def load_machines(path=None):
    with open(path or MACHINES_PATH) as fh:
        return json.load(fh)


def moat_geometry(T, cfg):
    """Per moat: bank volume, deepest cut, volume by depth, haul distance to its berm."""
    A, soil = T.cell_area, cfg.soil
    wt = soil.get("water_table_depth_m")
    out = []
    for m in range(len(cfg.moats)):
        mask = T.moat_id == m
        depth = (T.z0 - T.design)[mask]
        r = T.R[mask]
        V = float(depth.sum() * A)
        k = cfg.moat_to_berm()[m][0]
        bmask = T.berm_id == k
        fill = (T.design - T.z0)[bmask]
        r_cut = float((r * depth).sum() / depth.sum())
        r_fill = float((T.R[bmask] * fill).sum() / fill.sum())
        bwt = 0.0
        if wt is not None:
            bwt = float(np.clip(depth - wt, 0.0, None).sum() * A)
        out.append({"moat": m, "berm": k, "V_bank_m3": V, "max_depth_m": float(depth.max()),
                    "depth": depth, "r_cut": r_cut, "r_fill": r_fill,
                    "haul_m": abs(r_fill - r_cut), "V_below_water_m3": bwt,
                    "edge_to_berm_m": float(T.R[bmask].min() - r.max()) if r_fill > r_cut
                    else float(r.min() - T.R[bmask].max())})
    return out


def estimate(cfg, T, machine, job, geometry=None):
    soil = cfg.soil
    sf = cfg.swell_factor
    A = T.cell_area
    eff = job["efficiency"]
    geo = geometry or moat_geometry(T, cfg)
    fill = soil.get("bucket_fill_factor", 0.8)
    cyc = machine["backhoe_cycle_s"] * soil.get("dig_cycle_factor", 1.0)
    P_dig = machine["backhoe_bucket_m3"] * fill / sf * 3600.0 / cyc * eff           # bank m3/h
    v_load = machine["loader_speed_m_s"] * soil.get("loader_speed_factor", 1.0)
    per_moat = []
    tot = dict(dig_h=0.0, carry_h=0.0, rock_h=0.0, bench_m3=0.0, bwt_m3=0.0, rocks=0.0)
    for g in geo:
        V = g["V_bank_m3"]
        deep = float(np.clip(g["depth"] - machine["dig_depth_m"], 0.0, None).sum() * A)
        V_eff = (V + deep * (1.0 / job["bench_productivity"] - 1.0)
                 + g["V_below_water_m3"] * (1.0 / job["below_water_table_factor"] - 1.0))
        t_dig = V_eff / P_dig
        cast = g["haul_m"] <= machine["reach_m"]          # the berm's centre of fill is within reach
        t_carry = 0.0
        d = g["haul_m"] * job["haul_path_factor"]
        if not cast:
            cycle = machine["loader_fixed_s"] + 2.0 * d / v_load
            P_carry = 0.9 * machine["loader_bucket_m3"] * 3600.0 / cycle * eff         # loose m3/h
            t_carry = V * sf / P_carry * (1.0 + job["spread_and_compact_factor"])
        rocks = soil.get("rock_refusals_per_bank_m3", 0.0) * V
        t_rock = rocks * machine["rock_delay_min"] * (1.0 + 2.0 * machine["oversize_rock_fraction"]) / 60.0
        hours = (t_dig + t_carry) * (1.0 + (job["mode_switch_overhead"] if t_carry else 0.0)) + t_rock
        per_moat.append({"moat": g["moat"], "V_bank_m3": V, "hours": hours, "dig_h": t_dig,
                         "carry_h": t_carry, "rock_h": t_rock, "cast_direct": cast, "haul_m": d,
                         "bench_m3": deep, "below_water_m3": g["V_below_water_m3"]})
        tot["dig_h"] += t_dig
        tot["carry_h"] += t_carry
        tot["rock_h"] += t_rock
        tot["bench_m3"] += deep
        tot["bwt_m3"] += g["V_below_water_m3"]
        tot["rocks"] += rocks
    hours = sum(p["hours"] for p in per_moat)
    days = hours / job["hours_per_day"]
    V = sum(g["V_bank_m3"] for g in geo)
    pump_days = days * tot["bwt_m3"] / max(V, 1e-9) if tot["bwt_m3"] > 0 else 0.0
    cost = (hours * machine["rate_usd_per_h"] + hours * machine["fuel_l_per_h"] * job["fuel_usd_per_l"]
            + machine["mobilization_usd"] + pump_days * job["pump_usd_per_day"])
    max_depth = max(g["max_depth_m"] for g in geo)
    return {
        "machine": machine["label"], "V_bank_m3": V, "hours": hours, "working_days": days,
        "hours_per_day": job["hours_per_day"], "m3_per_hour": V / max(hours, 1e-9),
        "dig_m3_per_hour": P_dig, "dig_h": tot["dig_h"], "carry_h": tot["carry_h"],
        "rock_h": tot["rock_h"], "rocks": tot["rocks"], "fuel_l": hours * machine["fuel_l_per_h"],
        "cost_usd": cost, "usd_per_bank_m3": cost / max(V, 1e-9),
        "reaches_full_depth": machine["dig_depth_m"] >= max_depth, "max_cut_m": max_depth,
        "dig_depth_m": machine["dig_depth_m"], "bench_m3": tot["bench_m3"],
        "below_water_m3": tot["bwt_m3"], "per_moat": per_moat,
    }


def fleet_makespan(moat_hours, n, share_eff=0.85):
    """Hours until done with n identical machines. Up to one machine per moat, whole moats are
    shared out longest-first; beyond that, each extra machine joins the moat that would finish
    last and adds ``share_eff`` of a machine (they get in each other's way)."""
    h = [float(x) for x in moat_hours]
    if n <= len(h):
        loads = [0.0] * n
        for x in sorted(h, reverse=True):
            loads[loads.index(min(loads))] += x
        return max(loads)
    crews = [1] * len(h)

    def finish(i):
        return h[i] / (1.0 + (crews[i] - 1) * share_eff)
    for _ in range(n - len(h)):
        crews[max(range(len(h)), key=finish)] += 1
    return max(finish(i) for i in range(len(h)))


def main():
    import tether_sim as ts
    from config import load_config
    from terrain_engine import Terrain
    p = argparse.ArgumentParser()
    p.add_argument("--soil", default="ne_glacial_till")
    p.add_argument("--site", choices=["flat", "slope"])
    p.add_argument("--res", type=int, default=448)
    a = p.parse_args()
    ov = ['soil.preset="%s"' % a.soil, "grid.resolution=%d" % a.res]
    if a.site == "flat":
        ov.append('site={"type": "flat"}')
    cfg = load_config(ts.DEFAULT_PARAMS, ov)
    T = Terrain(cfg)
    data = load_machines()
    print("%s: %s m3 bank, deepest cut %.2f m" % (cfg.soil["label"], "{:,.0f}".format(T.design_cut_total),
                                                  T.max_depth))
    for key, mach in data["machines"].items():
        e = estimate(cfg, T, mach, data["job"])
        print("  %-26s %6.0f h  %5.1f days  %5.1f m3/h  $%7s  $%5.1f/m3  %s"
              % (e["machine"], e["hours"], e["working_days"], e["m3_per_hour"],
                 "{:,.0f}".format(e["cost_usd"]), e["usd_per_bank_m3"],
                 "full depth" if e["reaches_full_depth"] else "bench %.0f m3" % e["bench_m3"]))


if __name__ == "__main__":
    main()
