"""Does making more rings add value? 0 to 5 rings, built outward in the homestead's pattern.

    python3 tools/ring_count.py

Each ring is a moat and the berm its spoil builds, alternating a shallow ring (0.9 m deep, 8 m wide,
a 10-12 m berm) and a deep ring (2.44 m deep, 14 m wide, a 14 m berm), starting from the homestead's
18 m island. Rings 1 and 2 are exactly the recommended homestead. The terrain engine gives each
layout's cut, water, berm crowns and spoil; ring_engine/conventional.py the pond-crew cost.

What a ring costs: digging, topsoil, causeway and culverts, more land, a longer arm, upkeep.
What it gives: berm crowns to farm, water for fish and visitors, and fill to sell. Every yearly value
has diminishing steps, because the first acre of crops or the first trout pond is worth far more than
the fifth. Writes docs/ring_count.json. Every figure is a screening ASSUMPTION.
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

ACRE = 4046.9
RINGS = [   # (moat r_in, r_out, depth), (berm r_in, r_out)
    ((18.0, 26.0, 0.9), (30.0, 40.0)),
    ((44.0, 58.0, 2.44), (62.0, 76.0)),
    ((80.0, 88.0, 0.9), (92.0, 104.0)),
    ((108.0, 122.0, 2.44), (126.0, 140.0)),
    ((144.0, 152.0, 0.9), (156.0, 168.0)),
]
SITES = {"ne_flat": "New England till, flat", "ne_till": "New England till, 6 ft slope"}
COST = {"design_permits": 18000, "topsoil_usd_m3": 3.0, "loading_usd_m3": 2.0, "bund_usd_m3": 2.5,
        "fill_usd_yd3": 8.0, "causeway_usd_m": 110.0, "culvert_usd_per_ring": 3000,
        "land_usd_acre": 14400, "land_margin_m": 15.0,             # a border round the outer berm
        "arm_usd_m": 1500.0,                                       # the powered arm grows with the radius
        "contingency": 0.10, "upkeep_pct": 1.0}
VALUE = {   # yearly net value, in steps (acres, $/acre/yr); the first acres go to the best use
    "crown_steps": [(1.0, 4000.0), (3.0, 600.0), (1e9, 150.0)],    # crops and orchard, then pasture, then hay
    # water by kind: the first deep ring hosts trout fee fishing, the first shallow ring a prawn crop;
    # every further acre of water grows fed fish (homestead_economics: 600 lb/acre at $4 less $1 feed)
    "first_deep_usd": 14000.0, "first_shallow_usd": 5000.0, "more_water_usd_acre": 1800.0,
}
# Selling the spoil at retail through a landscape yard (tools/synergy_sweep.py YARD): screened loam and
# fieldstone go out at what the yard can sell each year, so a bigger dig takes longer to sell.
YARD_SALES = {"loam_share": 0.85, "loam_net_yd3": 28.0, "loam_yd3_per_year": 1500,
              "stone_fraction_of_bank": 0.15, "stone_t_per_m3": 2.6, "stone_net_t": 90.0, "stone_t_per_year": 150,
              "swell": 1.4}
HOMES = {"frontage_m": 30.0, "waterfront_premium_usd": 40000.0, "max_homes": 40}
YEARS, RATE = 25, 0.05


def layout(n):
    if n == 0:
        return None
    moats = [{"r_in": m[0], "r_out": m[1], "depth": m[2]} for m, _ in RINGS[:n]]
    berms = [{"r_in": b[0], "r_out": b[1], "height": 0.9, "source_moat": k} for k, (_, b) in enumerate(RINGS[:n])]
    extent = RINGS[n - 1][1][1] + 8.0
    return {"label": "%d ring%s" % (n, "" if n == 1 else "s"), "holes": 0,
            "overrides": ["moats=%s" % json.dumps(moats), "berms=%s" % json.dumps(berms), "grid.extent_m=%.1f" % extent]}


def stepped(area_acres, steps):
    v, left = 0.0, area_acres
    for size, rate in steps:
        take = min(left, size)
        v += take * rate
        left -= take
        if left <= 0:
            break
    return v


def yard_value(surplus_loose_m3):
    """Present value of selling the surplus through the yard, at the yard's yearly volumes."""
    y = YARD_SALES
    bank = surplus_loose_m3 / y["swell"]
    stone_t = bank * y["stone_fraction_of_bank"] * y["stone_t_per_m3"]
    loam_yd3 = surplus_loose_m3 * (1 - y["stone_fraction_of_bank"]) * y["loam_share"] * 1.308
    pv, yr = 0.0, 1
    while (loam_yd3 > 1 or stone_t > 1) and yr <= 40:
        lo, st = min(loam_yd3, y["loam_yd3_per_year"]), min(stone_t, y["stone_t_per_year"])
        pv += (lo * y["loam_net_yd3"] + st * y["stone_net_t"]) / (1 + RATE) ** yr
        loam_yd3 -= lo
        stone_t -= st
        yr += 1
    return pv, yr - 1


def one(n, soil, fill_market=True):
    if n == 0:
        r_out = 18.0
        land_acres = math.pi * (r_out + COST["land_margin_m"]) ** 2 / ACRE
        capex = {"land": land_acres * COST["land_usd_acre"]}
        return {"rings": 0, "years_to_sell": 0, "waterfront_lots": 0, "capex": capex, "total_capex": sum(capex.values()), "fill_value": 0.0, "yearly": {},
                "net_yearly": 0.0, "crown_acres": 0.0, "water_acres": 0.0, "land_acres": land_acres, "r_out": r_out,
                "cut_bank_m3": 0.0, "shoreline_m": 0.0, "crew_days": 0.0, "npv": -sum(capex.values())}
    hn.LAYOUTS["_rings"] = layout(n)
    res = 448 if n <= 3 else 560
    r = hn.numbers("_rings", soil, res=res)
    r_out = RINGS[n - 1][1][1]
    crown = sum(b["flat_crown_m2"] for b in r["berms"]) / ACRE
    water = r["water_area_m2"] / ACRE
    shore = sum(2 * math.pi * (m[0] + m[1]) for m, _ in RINGS[:n])
    surplus = max(r["spoil"]["to_bund_m3"], 0.0)
    land_acres = math.pi * (r_out + COST["land_margin_m"]) ** 2 / ACRE
    capex = {"design and permits": COST["design_permits"],
             "earthworks (pond crew)": r["build"]["excavator_dozer"]["cost_usd"],
             "topsoil strip and respread": (r["site_area_m2"] - r["water_area_m2"]) * 0.2 * COST["topsoil_usd_m3"],
             "causeway and culverts": (r_out - 18.0) * COST["causeway_usd_m"] + n * COST["culvert_usd_per_ring"],
             "land": land_acres * COST["land_usd_acre"],
             "arm reaching every ring": (r_out - 18.0) * COST["arm_usd_m"]}
    years_to_sell = 0
    if fill_market == "yard":
        fill_value, years_to_sell = yard_value(surplus)
    elif fill_market:
        capex["surplus fill: loading trucks"] = surplus * COST["loading_usd_m3"]
        fill_value = surplus * 1.308 * COST["fill_usd_yd3"]
    else:
        capex["surplus fill: dozed into a bund"] = surplus * COST["bund_usd_m3"]
        fill_value = 0.0
    capex["contingency"] = sum(v for k, v in capex.items() if k != "land") * COST["contingency"]
    total = sum(capex.values())
    deep = [g for g, (m, _) in zip(r["rings"], RINGS[:n]) if m[2] > 2.0]
    shallow = [g for g, (m, _) in zip(r["rings"], RINGS[:n]) if m[2] <= 2.0]
    fish = (VALUE["first_deep_usd"] if deep else 0.0) + (VALUE["first_shallow_usd"] if shallow else 0.0)
    extra = sum(g["water_area_m2"] for g in deep[1:] + shallow[1:]) / ACRE
    fish += extra * VALUE["more_water_usd_acre"]
    yearly = {"berm crowns farmed": stepped(crown, VALUE["crown_steps"]),
              "water: fish and fishing": fish,
              "upkeep": -(total - capex["land"]) * COST["upkeep_pct"] / 100}
    net_yearly = sum(yearly.values())
    annuity = (1 - (1 + RATE) ** -YEARS) / RATE
    npv = -total + fill_value + net_yearly * annuity
    # homes round the outermost water: one lot per frontage on the outer berm's edge
    outer_water_r = RINGS[n - 1][0][1]
    lots = min(int(2 * math.pi * (outer_water_r + 6.0) / HOMES["frontage_m"]), HOMES["max_homes"])
    return {"rings": n, "years_to_sell": years_to_sell, "waterfront_lots": lots, "capex": capex, "total_capex": total, "fill_value": fill_value, "yearly": yearly,
            "net_yearly": net_yearly, "crown_acres": crown, "water_acres": water, "land_acres": land_acres,
            "r_out": r_out, "cut_bank_m3": r["cut_bank_m3"], "surplus_m3": surplus, "shoreline_m": shore,
            "water_m3": sum(g["water_m3"] for g in r["rings"]), "crew_days": r["build"]["excavator_dozer"]["days"],
            "npv": npv}


def main():
    out = {}
    for soil, label in SITES.items():
        for fm in (True, False, "yard"):
            key = "%s%s" % (soil, {True: "", False: "_no_fill_market", "yard": "_through_a_yard"}[fm])
            rows = [one(n, soil, fm) for n in range(0, 6)]
            out[key] = rows
            print("\n%s, %s" % (label, {True: "fill sold at $8/yd3", False: "no fill market (bund on site)",
                                     "yard": "spoil sold as loam and stone through a landscape yard"}[fm]))
            print("  rings  across  land ac  cut m3    crew d  crown ac  water ac  shore m  build $     fill $    yearly $   NPV $      added NPV  per yr to pay  lots")
            prev = None
            annuity = (1 - (1 + RATE) ** -YEARS) / RATE
            for x in rows:
                add = x["npv"] - prev["npv"] if prev else 0.0
                x["added_npv"] = add
                x["yearly_needed_to_pay"] = max(-add, 0.0) / annuity
                x["added_lots"] = x["waterfront_lots"] - (prev["waterfront_lots"] if prev else 0)
                print("  %d      %4.0f m  %5.1f   %7s   %5.0f   %5.2f     %5.2f     %5.0f    %9s  %8s  %8s  %10s  %+10s"
                      % (x["rings"], 2 * x["r_out"], x["land_acres"], "{:,.0f}".format(x["cut_bank_m3"]), x["crew_days"],
                         x["crown_acres"], x["water_acres"], x["shoreline_m"], "{:,.0f}".format(x["total_capex"]),
                         "{:,.0f}".format(x["fill_value"]), "{:,.0f}".format(x["net_yearly"]), "{:,.0f}".format(x["npv"]),
                         "{:,.0f}".format(add)) + "  %10s  %3d  %2d y" % ("{:,.0f}".format(x["yearly_needed_to_pay"]), x["waterfront_lots"], x["years_to_sell"]))
                prev = x
    with open(os.path.join(ROOT, "docs", "ring_count.json"), "w") as fh:
        json.dump({"rings": RINGS, "cost": COST, "value": VALUE, "yard_sales": YARD_SALES, "results": out}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
