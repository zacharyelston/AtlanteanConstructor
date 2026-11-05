"""Hybrid build: one excavator with its operator by day, a train of three eOx by night.

    python3 tools/hybrid_build.py

The homestead layout (homestead_params.json: inner ring, orchard berm, deep ring, pasture berm).
The pond crew baseline is an excavator plus a dozer (ring_engine/conventional.py). Here the
dozer is replaced by a tethered train of three eOx 4WD cars (eox_vehicle.py, train_3x4wd) towing
5 ft box pans, and the work is split by what each does best:

- DAY (operator on site): the excavator digs the rings to grade and piles spoil in a windrow along
  the ring edge, or loads trucks with the surplus when fill is sold. The operator checks the eOx's
  night work and sets the next night's jobs.
- NIGHT (unattended, alarms to a phone): the eOx train strips topsoil ahead of the dig, carries the
  windrows to the berms and the island, spreads and tracks them in thin lifts, and at the end
  respreads topsoil and finish-grades.
- THE LEASH RULE: the train is tethered to a mast on the island, so by day it may work only on a
  ring inside the one the excavator is digging; its leash then never crosses the dig.

A day-by-day schedule, with rain days, a six-day excavator week and a windrow that can fill up
(the excavator then has to cast its own spoil, slowly). Writes docs/hybrid_build.json.
Every rate is a screening ASSUMPTION; the eOx haul cycle is a hand model, not yet run in tether_sim.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

from config import load_config  # noqa: E402
from conventional import estimate, load_machines, moat_geometry  # noqa: E402
from eox_vehicle import load_fleet  # noqa: E402
from terrain_engine import Terrain  # noqa: E402

PARAMS = os.path.join(ROOT, "ring_engine", "homestead_params.json")
SITES = {
    "ne_slope": {"label": "New England till, 6 ft slope", "overrides": ['soil.preset="ne_glacial_till"'], "rain_every": 5},
    "ne_flat": {"label": "New England till, flat", "overrides": ['soil.preset="ne_glacial_till"', 'site={"type": "flat"}'],
                "rain_every": 5},
    "florida": {"label": "Florida sand, flat", "overrides": ['soil.preset="florida_sand"', 'site={"type": "flat"}'],
                "rain_every": 6},
}
KEEP = ['soil.canal_side_slope_deg=26.57', 'soil.angle_of_repose_deg=18.43', "grid.resolution=384"]

SCHEDULE = {"excavator_day_h": 10, "excavator_days_per_week": 6, "eox_night_h": 11, "eox_day_h": 8,
            "eox_head_start_days": 3,          # the train starts stripping topsoil before the excavator arrives
            "windrow_m2": 3.0,                 # loose cross-section the ring edge can hold
            "self_cast_factor": 0.6,           # excavator productivity when it must cast its own spoil
            "island_raise_m": 1.0}
EOX = {"fill_factor": 0.85, "load_s": 12, "spread_s": 9, "turn_s": 20, "radial_m_s": 0.5, "path_factor": 1.3,
       "efficiency": 0.83, "spread_compact_factor": 1.15,
       "pull_loaded_n": 3400, "pull_empty_n": 1000, "drive_eff": 0.65, "hotel_w": 240,
       "grade_width_m": 1.5, "grade_speed_m_s": 1.0, "grade_passes": 3,
       "topsoil_m": 0.2, "topsoil_haul_m": 8.0, "usd_kwh": 0.25}
COSTS = {"fill_sold": True}
# Excavator sizes. 14 t is the pond crew's machine (vehicles/conventional_machines.json); 21 t is ASSUMED
# from typical spec sheets: 1.0 m3 bucket, slightly slower cycle, higher rental.
EXCAVATORS = {"14t": {},
              "21t": {"label": "Excavator (~21 t)", "backhoe_bucket_m3": 1.0, "backhoe_cycle_s": 19,
                      "rate_usd_per_h": 230, "fuel_l_per_h": 22.0, "mobilization_usd": 2000}}
RUN = {"excavator": "14t"}


def site(key):
    cfg = load_config(PARAMS, SITES[key]["overrides"] + KEEP)
    T = Terrain(cfg)
    data = load_machines()
    crew = data["machines"]["excavator_dozer"]
    machine = dict(crew, **EXCAVATORS[RUN["excavator"]])
    geo = moat_geometry(T, cfg)
    base = estimate(cfg, T, crew, data["job"], geo)          # the pond-crew baseline
    dig = estimate(cfg, T, machine, data["job"], geo)        # the excavator this run uses
    A, sf = T.cell_area, cfg.swell_factor
    rings = []
    for g, pm in zip(geo, dig["per_moat"]):
        k = g["berm"]
        bm = T.berm_id == k
        berm_loose = float((T.design - T.z0)[bm].clip(min=0).sum() * A)
        mask = T.moat_id == g["moat"]
        area = float(mask.sum() * A + bm.sum() * A)
        r_out = float(T.R[mask].max())
        rings.append({"ring": g["moat"], "V_bank": g["V_bank_m3"], "loose": g["V_bank_m3"] * sf,
                      "rate_bank_h": g["V_bank_m3"] / (pm["dig_h"] + pm["rock_h"]),
                      "berm_loose": berm_loose, "haul_m": g["haul_m"], "r_out": r_out, "strip_area": area})
    island_loose = math.pi * cfg.hub_radius ** 2 * SCHEDULE["island_raise_m"]
    return cfg, T, machine, data["job"], base, rings, island_loose


def eox_rate(d):
    """Loose m3 an hour the 3-car train carries over a radial haul of d metres, and kWh per m3."""
    e, car = EOX, load_fleet()["train_3x4wd"]
    cap = car["tool"]["capacity_loose_m3"] * e["fill_factor"]
    path = d * e["path_factor"]
    cycle = (e["load_s"] + e["spread_s"] + e["turn_s"] + 2 * path / e["radial_m_s"]) * e["spread_compact_factor"]
    rate = cap * 3600.0 / cycle * e["efficiency"]
    j = (e["pull_loaded_n"] * path + e["pull_empty_n"] * path) / e["drive_eff"] + e["hotel_w"] * cycle
    return rate, j / 3.6e6 / cap


def simulate(key):
    cfg, T, machine, job, base, rings, island_loose = site(key)
    S, rain_every = SCHEDULE, SITES[key]["rain_every"]
    order = sorted(range(len(rings)), key=lambda i: -rings[i]["r_out"])        # the deep outer ring first
    # where each ring's spoil goes: its berm, then (inner ring) the island, then trucks or the bund
    for i, r in enumerate(rings):
        r["to_place"] = min(r["loose"], r["berm_loose"])
        r["to_island"] = 0.0
    inner = min(range(len(rings)), key=lambda i: rings[i]["r_out"])
    need_island = island_loose
    for i in sorted(range(len(rings)), key=lambda i: rings[i]["r_out"]):
        spare = rings[i]["loose"] - rings[i]["to_place"]
        take = min(spare, need_island)
        rings[i]["to_island"] = take
        need_island -= take
    for r in rings:
        r["surplus"] = r["loose"] - r["to_place"] - r["to_island"]
        r["pile_cap"] = 2 * math.pi * r["r_out"] * S["windrow_m2"]
        r["dug"], r["pile"], r["placed"], r["stripped"] = 0.0, 0.0, 0.0, 0.0
        r["strip_m3"] = r["strip_area"] * EOX["topsoil_m"]
    bund_haul = 30.0
    respread = sum(r["strip_m3"] for r in rings)
    grade_area = sum(r["strip_area"] for r in rings)
    grade_h = grade_area * EOX["grade_passes"] / (EOX["grade_width_m"] * EOX["grade_speed_m_s"]) / 3600.0
    log, day = [], -S["eox_head_start_days"]
    exc_h = exc_days = eox_h = kwh = 0.0
    respread_left, grade_left = respread, grade_h
    cur = 0
    exc_done = piles_done = None
    while True:
        rain = (day % rain_every) == rain_every - 1
        dow = (day + S["eox_head_start_days"]) % 7
        exc_on = day >= 0 and not rain and dow < S["excavator_days_per_week"] and cur < len(order)
        exc_ring = order[cur] if cur < len(order) else None
        note = {"day": day, "rain": rain, "excavator": exc_on}
        # ---------------- day: the excavator digs
        if exc_on:
            i = exc_ring
            r = rings[i]
            hours = S["excavator_day_h"]
            exc_days += 1
            if r["stripped"] < r["strip_m3"] - 1e-6:
                hours *= 0.85                      # it strips the rest itself, slowly, before digging
                r["stripped"] = r["strip_m3"]
            while hours > 1e-6 and r["dug"] < r["loose"] - 1e-6:
                pile_bound = r["to_place"] + r["to_island"] + (0 if COSTS["fill_sold"] else r["surplus"])
                to_trucks = r["dug"] >= pile_bound - 1e-6
                rate = r["rate_bank_h"] * cfg.swell_factor
                if not to_trucks and r["pile"] >= r["pile_cap"]:
                    rate *= S["self_cast_factor"]
                    left = pile_bound - r["dug"]
                    dt = min(hours, left / rate)
                    r["dug"] += rate * dt
                    r["placed"] += rate * dt
                else:
                    left = (r["loose"] - r["dug"]) if to_trucks else min(pile_bound - r["dug"], r["pile_cap"] - r["pile"] + 1e-9)
                    dt = min(hours, max(left, 1e-9) / rate)
                    r["dug"] += rate * dt
                    if not to_trucks:
                        r["pile"] += rate * dt
                hours -= dt
                exc_h += dt
            if r["dug"] >= r["loose"] - 1e-6:
                cur += 1
            note["exc_ring"] = i
        # ---------------- the eOx shifts: by day if the leash rule allows, and every night
        shifts = []
        if not rain:
            if exc_on:
                shifts.append(("day", S["eox_day_h"], rings[exc_ring]["r_out"]))
            shifts.append(("night", S["eox_night_h"], None))
        for name, h, limit in shifts:
            while h > 1e-6:
                ok = [i for i in range(len(rings)) if limit is None or rings[i]["r_out"] < limit - 1.0]
                strip = [i for i in ok if rings[i]["stripped"] < rings[i]["strip_m3"] - 1e-6]
                piles = [i for i in ok if rings[i]["pile"] > 1e-6]
                if strip:                                    # strip the ring the excavator needs next
                    i = min(strip, key=lambda i: order.index(i))
                    rate, e_m3 = eox_rate(EOX["topsoil_haul_m"])
                    v = min(rings[i]["strip_m3"] - rings[i]["stripped"], rate * h)
                    rings[i]["stripped"] += v
                elif piles:
                    i = max(piles, key=lambda i: rings[i]["pile"])
                    r = rings[i]
                    d = r["haul_m"] if r["placed"] < r["to_place"] else (8.0 if r["placed"] < r["to_place"] + r["to_island"] else bund_haul)
                    rate, e_m3 = eox_rate(d)
                    v = min(r["pile"], rate * h)
                    r["pile"] -= v
                    r["placed"] += v
                elif cur >= len(order) and respread_left > 1e-6 and limit is None:
                    rate, e_m3 = eox_rate(EOX["topsoil_haul_m"])
                    v = min(respread_left, rate * h)
                    respread_left -= v
                elif cur >= len(order) and respread_left <= 1e-6 and grade_left > 1e-6 and limit is None:
                    dt = min(h, grade_left)
                    grade_left -= dt
                    eox_h += dt
                    kwh += dt * 2.5
                    h -= dt
                    continue
                else:
                    break
                dt = v / rate
                eox_h += dt
                kwh += v * e_m3
                h -= dt
        log.append(note)
        if exc_done is None and cur >= len(order):
            exc_done = day + 1 + S["eox_head_start_days"]
        if piles_done is None and cur >= len(order) and all(r["pile"] <= 1e-6 for r in rings):
            piles_done = day + 1 + S["eox_head_start_days"]
        done = (cur >= len(order) and all(r["pile"] <= 1e-6 for r in rings)
                and respread_left <= 1e-6 and grade_left <= 1e-6)
        day += 1
        if done or day > 400:
            break
    calendar = day + S["eox_head_start_days"]
    # baseline: the pond crew (excavator + dozer) on the same calendar rules
    crew_days = base["hours"] / S["excavator_day_h"]
    weeks, d, worked = 0, 0, 0.0
    while worked < crew_days:
        if not ((d % rain_every) == rain_every - 1) and d % 7 < S["excavator_days_per_week"]:
            worked += 1
        d += 1
    exc_cost = (exc_h * (machine["rate_usd_per_h"] + machine["fuel_l_per_h"] * job["fuel_usd_per_l"])
                + machine["mobilization_usd"])
    return {"site": SITES[key]["label"], "swell": cfg.swell_factor, "excavator": RUN["excavator"],
            "excavator_done_day": exc_done, "spoil_placed_day": piles_done,
            "rings": [{k: v for k, v in r.items() if isinstance(v, (int, float))} for r in rings],
            "island_loose": island_loose, "fill_sold": COSTS["fill_sold"],
            "calendar_days": calendar, "excavator_days": exc_days, "excavator_hours": exc_h,
            "eox_hours": eox_h, "eox_kwh": kwh, "eox_energy_usd": kwh * EOX["usd_kwh"],
            "excavator_cost": exc_cost, "hybrid_cost": exc_cost + kwh * EOX["usd_kwh"],
            "baseline_hours": base["hours"], "baseline_working_days_10h": crew_days, "baseline_calendar_days": d,
            "baseline_cost": base["cost_usd"], "baseline_dig_h": base["dig_h"], "baseline_carry_h": base["carry_h"],
            "eox_rate_berm_m3_h": eox_rate(sum(r["haul_m"] for r in rings) / len(rings))[0],
            "grade_h": grade_h, "respread_m3": respread}


def main():
    out = {}
    for ex in EXCAVATORS:
        RUN["excavator"] = ex
        for fs in (True, False):
            COSTS["fill_sold"] = fs
            for key in SITES:
                res = simulate(key)
                out["%s_%s%s" % (key, ex, "" if fs else "_no_fill_market")] = res
                print("%-28s %s fill %-4s | excavator done day %3d (%2d days, %3.0f h), spoil placed day %3d, finished day %3d;"
                      " eOx %4.0f h %4.0f kWh; $%s | pond crew: %3d days, $%s"
                      % (res["site"], ex, "sold" if fs else "kept", res["excavator_done_day"], res["excavator_days"],
                         res["excavator_hours"], res["spoil_placed_day"], res["calendar_days"], res["eox_hours"], res["eox_kwh"],
                         "{:,.0f}".format(res["hybrid_cost"]), res["baseline_calendar_days"], "{:,.0f}".format(res["baseline_cost"])))
    r = out["ne_flat_14t"]
    print("\nNE flat detail: eOx carries ~%.0f loose m3/h to the berms; rings:" % r["eox_rate_berm_m3_h"])
    for g in r["rings"]:
        print("  ring %d: %s bank m3 (%s loose) at %.0f bank m3/h; berm %s, island %s, surplus %s; haul %.0f m; windrow %s m3"
              % (g["ring"], "{:,.0f}".format(g["V_bank"]), "{:,.0f}".format(g["loose"]), g["rate_bank_h"],
                 "{:,.0f}".format(g["to_place"]), "{:,.0f}".format(g["to_island"]), "{:,.0f}".format(g["surplus"]),
                 g["haul_m"], "{:,.0f}".format(g["pile_cap"])))
    with open(os.path.join(ROOT, "docs", "hybrid_build.json"), "w") as fh:
        json.dump({"schedule": SCHEDULE, "eox": EOX, "results": out}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
