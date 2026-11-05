"""Scenario: a destination-scale Atlantean site, a regional farm market around a 120 ft dome.

    python3 tools/destination.py

After a concept render: a raised plaza island 72 m across with a hedge-faced retaining wall, a
120 ft (36.6 m) dome (a solid Monolithic-type concrete shell by default; clear ETFE and polycarbonate as options) at its centre holding an indoor market and food hall, outdoor
market stalls around it, one wide deep ring cut into four basins by a cross of causeways, crop rings
on a promenade berm, field quadrants outside, parking, a solar field and, as an option, three
mid-size wind turbines on their own towers on the outer road.

Earthworks come from the terrain engine (via tools/homestead_numbers.py). Money comes from vendor
stall fees, parking, a farm cafe, produce and pick-your-own, ticketed festival weekends and private
evening events. Writes docs/destination.json. Every figure is a screening ASSUMPTION; the dome
envelope and the turbines especially need quotes.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

import homestead_numbers as hn  # noqa: E402

LAYOUT = {"label": "Destination: 36 m plaza island, one 22 m wide deep ring, promenade berm", "holes": 0,
          "overrides": ['hub={"radius_m": 36.0}', 'moats=[{"r_in": 40.0, "r_out": 62.0, "depth": 2.44}]',
                        'berms=[{"r_in": 66.0, "r_out": 80.0, "height": 0.9, "source_moat": 0}]', 'grid.extent_m=96.0']}
M3_TO_YD3 = 1.308
FT2_PER_M2 = 10.764

DOME = {"diameter_m": 36.6}
ENVELOPES = {   # installed, frame included, per m2 of dome surface; U-value of the roof; daytime solar offset
    "monolithic": {"label": "Monolithic concrete dome: airform, foam, shotcrete, with skylights and a glazed entry band",
                   "usd_m2": 350, "range": (250, 500), "u_w_m2k": 0.3, "solar_offset": 0.10},
    "etfe": {"label": "Clear ETFE cushions on a steel frame (like the render)", "usd_m2": 900, "range": (600, 1500),
             "u_w_m2k": 1.9, "solar_offset": 0.35},
    "polycarbonate": {"label": "Polycarbonate panels on a steel geodesic frame", "usd_m2": 500, "range": (350, 700),
                      "u_w_m2k": 2.5, "solar_offset": 0.30},
}
SITE = {
    "acres": 22, "land_usd_acre": 14400,
    "design_permits_usd": 300000,             # site plan, traffic study, special permit, stamped drawings
    "topsoil_and_grading_usd": 40000,
    "fill_usd_yd3": 8.0,
    "retaining_wall_usd_ft2": 45, "wall_height_m": 1.5, "hedge_usd": 15000,
    "causeways": 4, "causeway_usd": 60000,    # each with a box culvert so the four basins stay one body of water
    "plaza_usd_ft2": 12,
    "dome_slab_usd_ft2": 12, "dome_mep_usd_ft2": 45, "dome_sprinkler_usd_ft2": 7, "sprinkler_tank_usd": 90000,
    "restroom_fixtures": 20, "fixture_usd": 12000, "market_fitout_usd": 250000, "fire_alarm_usd": 50000,
    "dome_design_pct": 8,
    "outdoor_stalls": 60, "stall_canopy_usd": 1500,
    "paths_m2": 3200, "paths_usd_ft2": 3,
    "parking_spaces": 400, "parking_usd_space": 1200,
    "shuttles": 4, "shuttle_usd": 18000,
    "septic_usd": 250000, "well_storage_usd": 80000, "power_service_usd": 100000,
    "pv_kw": 150, "pv_usd_w": 2.4,
    "farm_setup_usd": 170000,                 # berm-bed irrigation, pick-your-own berries and flowers, small equipment
    "contingency_pct": 15,
}
TURBINES = {"count": 3, "kw_each": 100, "usd_kw": 5500, "capacity_factor": 0.17, "export_usd_kwh": 0.10,
            "setback_note": "fall zone of 1.1-1.5 x tip height kept clear of paths and parking"}
ENERGY = {"heating_k_days": 1900, "cop": 3.0,
          "other_kwh": 60000, "pv_kwh_kw": 1200, "grid_usd_kwh": 0.25}

MARKET_DAYS = {"summer_weekend_days": 52, "winter_saturdays": 26}
VISITORS = {"cautious": 800, "base": 1500, "strong": 3000}          # per market day
FESTIVAL_DAY = {"cautious": 1500, "base": 2500, "strong": 4000}
PRIVATE_EVENTS = {"cautious": 10, "base": 20, "strong": 30}
REVENUE = {"stalls_summer": 90, "stalls_winter": 30, "stall_fee_day": 60, "stall_occupancy": 0.8,
           "people_per_car": 2.5, "parking_fee": 5,
           "cafe_spend": 5.0, "cafe_cogs_pct": 32,
           "farm_spend": 3.0, "farm_cogs_pct": 25,
           "festival_weekends": 4, "festival_ticket": 15, "festival_cost_pct": 35,
           "event_fee": 10000, "event_cost_pct": 30}
STAFF = [("General manager", 1, 90000), ("Market manager", 1, 60000), ("Events and festivals manager", 1, 60000),
         ("Farm manager", 1, 55000), ("Growers", 3, 40000), ("Cafe lead", 1, 50000), ("Cafe staff", 3, 35000),
         ("Maintenance", 2, 45000), ("Cleaning", 2, 36000)]
SEASONAL_H, SEASONAL_USD_H, BURDEN_PCT = 4000, 18.0, 12
OPEX = {"marketing": 100000, "insurance": 60000, "waste": 25000, "security_per_market_day": 300,
        "shuttle_ops": 15000, "maintenance_pct": 1.5, "mill_rate": 21.49, "assess_ratio": 0.70, "assessed_share": 0.6}
FINANCE = {"equity_pct": 35, "rate": 0.075, "years": 25}


def earthworks():
    hn.LAYOUTS["destination"] = LAYOUT
    r = hn.numbers("destination", "ne_flat", res=384)
    crew = r["build"]["excavator_dozer"]
    return {"cut_bank_m3": r["cut_bank_m3"], "water_m3": r["rings"][0]["water_m3"], "water_area_m2": r["water_area_m2"],
            "island_m2": r["island_m2"], "berm_crown_m2": r["berms"][0]["flat_crown_m2"],
            "island_raise_m": r["spoil"]["island_raise_m"], "fill_to_sell_m3": r["spoil"]["to_bund_m3"],
            "crew_days": crew["days"], "crew_usd": crew["cost_usd"]}


def dome_geometry():
    r = DOME["diameter_m"] / 2
    return {"floor_m2": math.pi * r * r, "floor_ft2": math.pi * r * r * FT2_PER_M2, "surface_m2": 2 * math.pi * r * r}


def energy(turbines, envelope="monolithic"):
    d = dome_geometry()
    e, v = ENERGY, ENVELOPES[envelope]
    heat = v["u_w_m2k"] * d["surface_m2"] * e["heating_k_days"] * 24 / 1000 * (1 - v["solar_offset"])
    load = heat / e["cop"] + e["other_kwh"]
    pv = SITE["pv_kw"] * e["pv_kwh_kw"]
    wind = TURBINES["count"] * TURBINES["kw_each"] * 8760 * TURBINES["capacity_factor"] if turbines else 0.0
    used = min(load, pv + wind)
    export = max(pv + wind - load, 0.0)
    bill = (load - used) * e["grid_usd_kwh"] - export * TURBINES["export_usd_kwh"]
    return {"dome_heat_kwh_th": heat, "load_kwh": load, "pv_kwh": pv, "wind_kwh": wind, "export_kwh": export,
            "net_energy_bill": bill}


def capex(ew, envelope, turbines):
    s, d = SITE, dome_geometry()
    island_edge_ft2 = 2 * math.pi * 36.0 * s["wall_height_m"] * FT2_PER_M2
    plaza_ft2 = (ew["island_m2"] - d["floor_m2"]) * FT2_PER_M2
    dome = {"envelope (%s)" % envelope: d["surface_m2"] * ENVELOPES[envelope]["usd_m2"],
            "slab": d["floor_ft2"] * s["dome_slab_usd_ft2"], "heating, ventilation, electrical, lighting": d["floor_ft2"] * s["dome_mep_usd_ft2"],
            "sprinklers and tank": d["floor_ft2"] * s["dome_sprinkler_usd_ft2"] + s["sprinkler_tank_usd"],
            "restrooms (%d fixtures)" % s["restroom_fixtures"]: s["restroom_fixtures"] * s["fixture_usd"],
            "indoor market and food-hall fit-out": s["market_fitout_usd"], "fire alarm and egress": s["fire_alarm_usd"]}
    dome["design and engineering"] = sum(dome.values()) * s["dome_design_pct"] / 100
    lines = {"land, %d acres" % s["acres"]: s["acres"] * s["land_usd_acre"],
             "design, permits, site plan, traffic study": s["design_permits_usd"],
             "earthworks (excavator and dozer crew, %d days)" % round(ew["crew_days"]): ew["crew_usd"],
             "topsoil and grading": s["topsoil_and_grading_usd"],
             "hedge-faced retaining wall round the island": island_edge_ft2 * s["retaining_wall_usd_ft2"] + s["hedge_usd"],
             "%d causeways with box culverts" % s["causeways"]: s["causeways"] * s["causeway_usd"],
             "plaza paving (%s ft2)" % "{:,.0f}".format(plaza_ft2): plaza_ft2 * s["plaza_usd_ft2"],
             "the dome, 120 ft (%s ft2)" % "{:,.0f}".format(d["floor_ft2"]): sum(dome.values()),
             "%d outdoor market stalls" % s["outdoor_stalls"]: s["outdoor_stalls"] * s["stall_canopy_usd"],
             "promenade and cross paths": s["paths_m2"] * FT2_PER_M2 * s["paths_usd_ft2"],
             "parking, %d spaces, with stormwater" % s["parking_spaces"]: s["parking_spaces"] * s["parking_usd_space"],
             "%d electric shuttles" % s["shuttles"]: s["shuttles"] * s["shuttle_usd"],
             "commercial septic": s["septic_usd"], "well and water storage": s["well_storage_usd"],
             "three-phase power service": s["power_service_usd"],
             "solar field, %d kW" % s["pv_kw"]: s["pv_kw"] * 1000 * s["pv_usd_w"],
             "farm: berm beds, pick-your-own, equipment": s["farm_setup_usd"]}
    if turbines:
        t = TURBINES
        lines["%d wind turbines, %d kW each" % (t["count"], t["kw_each"])] = t["count"] * t["kw_each"] * t["usd_kw"]
    lines["contingency (%d %%)" % s["contingency_pct"]] = sum(lines.values()) * s["contingency_pct"] / 100
    return {"lines": lines, "dome": dome, "total": sum(lines.values()), "plaza_ft2": plaza_ft2}


def operations(level, cap, en):
    v, R, M = VISITORS[level], REVENUE, MARKET_DAYS
    days = M["summer_weekend_days"] + M["winter_saturdays"]
    visitors = v * days
    stalls = (R["stalls_summer"] * M["summer_weekend_days"] + R["stalls_winter"] * M["winter_saturdays"]) * R["stall_occupancy"] * R["stall_fee_day"]
    fest_people = FESTIVAL_DAY[level] * 2 * R["festival_weekends"]
    revenue = {"vendor stall fees": stalls,
               "parking": visitors / R["people_per_car"] * R["parking_fee"],
               "farm cafe in the dome": visitors * R["cafe_spend"],
               "farm produce, flowers, pick-your-own": visitors * R["farm_spend"],
               "festival weekends (%d, ticketed)" % R["festival_weekends"]: fest_people * R["festival_ticket"],
               "private evening events (%d)" % PRIVATE_EVENTS[level]: PRIVATE_EVENTS[level] * R["event_fee"]}
    payroll = (sum(n * w for _, n, w in STAFF) + SEASONAL_H * SEASONAL_USD_H) * (1 + BURDEN_PCT / 100)
    built = cap["total"] - cap["lines"][next(k for k in cap["lines"] if k.startswith("land"))]
    costs = {"payroll (%d staff plus seasonal crew, with burden)" % sum(n for _, n, _ in STAFF): payroll,
             "cafe food": revenue["farm cafe in the dome"] * R["cafe_cogs_pct"] / 100,
             "farm inputs": revenue["farm produce, flowers, pick-your-own"] * R["farm_cogs_pct"] / 100,
             "festival costs (acts, security, extra toilets)": revenue["festival weekends (%d, ticketed)" % R["festival_weekends"]] * R["festival_cost_pct"] / 100,
             "private events: running costs": revenue["private evening events (%d)" % PRIVATE_EVENTS[level]] * R["event_cost_pct"] / 100,
             "marketing": OPEX["marketing"], "insurance": OPEX["insurance"], "waste": OPEX["waste"],
             "security on market days": OPEX["security_per_market_day"] * days, "shuttle running": OPEX["shuttle_ops"],
             "maintenance (%.1f %% of what's built)" % OPEX["maintenance_pct"]: built * OPEX["maintenance_pct"] / 100,
             "property tax": built * OPEX["assessed_share"] * OPEX["assess_ratio"] * OPEX["mill_rate"] / 1000,
             "energy (net of solar%s)" % (" and wind" if en["wind_kwh"] else ""): en["net_energy_bill"]}
    return {"visitors_year": visitors + fest_people, "market_days": days, "revenue": revenue, "costs": costs,
            "noi": sum(revenue.values()) - sum(costs.values())}


def financing(total, fill_credit, noi):
    f = FINANCE
    need = total - fill_credit
    equity = need * f["equity_pct"] / 100
    loan = need - equity
    ds = loan * f["rate"] / (1 - (1 + f["rate"]) ** -f["years"])
    return {"equity": equity, "loan": loan, "debt_service": ds, "dscr": noi / ds, "cash_to_equity": noi - ds,
            "cash_yield_pct": 100 * (noi - ds) / equity}


def visitors_for_dscr(cap, en, fill_credit, target=1.25):
    lo, hi = 100, 10000
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        VISITORS["_probe"], FESTIVAL_DAY["_probe"], PRIVATE_EVENTS["_probe"] = mid, FESTIVAL_DAY["base"], PRIVATE_EVENTS["base"]
        o = operations("_probe", cap, en)
        if financing(cap["total"], fill_credit, o["noi"])["dscr"] < target:
            lo = mid
        else:
            hi = mid
    for dct in (VISITORS, FESTIVAL_DAY, PRIVATE_EVENTS):
        dct.pop("_probe", None)
    return hi


def main():
    ew = earthworks()
    fill_credit = ew["fill_to_sell_m3"] * M3_TO_YD3 * SITE["fill_usd_yd3"]
    d = dome_geometry()
    print("Earthworks: cut %s m3, ring holds %s m3 over %s m2; island raised %.1f m; %s m3 loose fill to sell ($%s); "
          "crew %.0f days, $%s"
          % tuple(["{:,.0f}".format(ew["cut_bank_m3"]), "{:,.0f}".format(ew["water_m3"]), "{:,.0f}".format(ew["water_area_m2"]),
                   ew["island_raise_m"], "{:,.0f}".format(ew["fill_to_sell_m3"]), "{:,.0f}".format(fill_credit),
                   ew["crew_days"], "{:,.0f}".format(ew["crew_usd"])]))
    print("Dome: %s ft2 floor, %s m2 of roof" % ("{:,.0f}".format(d["floor_ft2"]), "{:,.0f}".format(d["surface_m2"])))
    out = {"earthworks": ew, "fill_credit": fill_credit, "dome": d, "envelopes": ENVELOPES, "site": SITE,
           "turbines": TURBINES, "visitors": VISITORS, "revenue_assumptions": REVENUE, "staff": STAFF, "runs": {}}
    for env in ENVELOPES:
        for turb in (False, True):
            en = energy(turb, env)
            cap = capex(ew, env, turb)
            key = env + ("+wind" if turb else "")
            out["runs"][key] = {"capex": cap, "energy": en, "levels": {}}
            print("\n%s%s: build $%s (dome $%s); energy load %s kWh, bill $%s"
                  % (ENVELOPES[env]["label"], " + 3 turbines" if turb else "", "{:,.0f}".format(cap["total"]),
                     "{:,.0f}".format(sum(cap["dome"].values())), "{:,.0f}".format(en["load_kwh"]),
                     "{:,.0f}".format(en["net_energy_bill"])))
            out["runs"][key]["visitors_per_market_day_for_dscr_1_25"] = visitors_for_dscr(cap, en, fill_credit)
            print("  market-day visitors needed for a lender's 1.25 cover: %.0f" % out["runs"][key]["visitors_per_market_day_for_dscr_1_25"])
            for lvl in ("cautious", "base", "strong"):
                o = operations(lvl, cap, en)
                fin = financing(cap["total"], fill_credit, o["noi"])
                out["runs"][key]["levels"][lvl] = {**o, **fin}
                print("  %-8s %s visitors/yr: revenue $%s, NOI $%s; equity $%s, loan $%s, DSCR %.2f, cash yield %.1f %%"
                      % (lvl, "{:,.0f}".format(o["visitors_year"]), "{:,.0f}".format(sum(o["revenue"].values())),
                         "{:,.0f}".format(o["noi"]), "{:,.0f}".format(fin["equity"]), "{:,.0f}".format(fin["loan"]),
                         fin["dscr"], fin["cash_yield_pct"]))
    base = out["runs"]["monolithic"]
    print("\nMonolithic, no turbines, build lines:")
    for k, v in base["capex"]["lines"].items():
        print("  %-62s $%10s" % (k, "{:,.0f}".format(v)))
    print("  dome:", {k: round(v) for k, v in base["capex"]["dome"].items()})
    b = base["levels"]["base"]
    for k, v in b["revenue"].items():
        print("  + %-55s $%9s" % (k, "{:,.0f}".format(v)))
    for k, v in b["costs"].items():
        print("  - %-55s $%9s" % (k, "{:,.0f}".format(v)))
    with open(os.path.join(ROOT, "docs", "destination.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
