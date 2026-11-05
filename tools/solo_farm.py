"""A one-person Atlantean farm with one backhoe: digging the ponds, earth-berm shelters, and the best mix.

    python3 tools/solo_farm.py

1. THE DIG. The owner buys a used backhoe loader and digs the rings in the off-seasons, instead of hiring
   the pond crew. Hours come from the backhoe-loader estimate in ring_engine/conventional.py
   (via tools/homestead_numbers.py); the owner's cash cost is fuel and wear, not rental.
2. THE SHELTERS. An owner's earth-berm home dug into the island pad or the orchard berm, backfilled with
   spoil: what it costs against a conventional small house, and what it saves in heating.
3. THE MIX. tools/synergy_sweep.py in solo mode: one owner works up to OWNER_H_MONTH hours a month for
   free (the farm's income is the owner's pay), and paid help is capped. The local search picks the best
   mix of features for a small budget and one or two buildings.

Writes docs/solo_farm.json. Every figure is a screening ASSUMPTION.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

import homestead_numbers as hn  # noqa: E402
import ring_count as rc  # noqa: E402
import synergy_sweep as sw  # noqa: E402

BACKHOE = {"buy_usd": 55000, "resale_after_5y_usd": 35000, "fuel_l_h": 11.0, "fuel_usd_l": 1.05, "wear_usd_h": 15.0,
           "dig_h_per_year": 600}          # shoulder seasons and winter thaws, around the farm work
HOME = {"ft2": 800, "conventional_usd_ft2": 200, "owner_built_usd_ft2": 140, "berm_premium": 0.05,
        "heat_kwh_th": 9000, "heat_saving": 0.5, "cop": 3.0, "usd_kwh": 0.30}
SOLO = {"owner_h_month": 170, "help_max_h": 500, "overhead_h": 60}   # 60 h a year of books, marketing, permits per line


def dig(n_rings, soil):
    if n_rings == 2:
        r = hn.numbers("outer_deep", soil)
    else:
        hn.LAYOUTS["_rings"] = rc.layout(n_rings)
        r = hn.numbers("_rings", soil, res=448)
    bh, crew = r["build"]["backhoe_loader"], r["build"]["excavator_dozer"]
    hours = bh["days"] * 8
    b = BACKHOE
    cash = hours * (b["fuel_l_h"] * b["fuel_usd_l"] + b["wear_usd_h"])
    return {"rings": n_rings, "soil": r["soil"], "cut_bank_m3": r["cut_bank_m3"], "backhoe_hours": hours,
            "years_at_600h": hours / b["dig_h_per_year"], "owner_cash_usd": cash,
            "machine_net_usd": b["buy_usd"] - b["resale_after_5y_usd"],
            "hired_backhoe_usd": bh["cost_usd"], "pond_crew_usd": crew["cost_usd"], "pond_crew_days": crew["days"]}


def home():
    h = HOME
    conv = h["ft2"] * h["conventional_usd_ft2"]
    owner = h["ft2"] * h["owner_built_usd_ft2"]
    berm = owner * (1 + h["berm_premium"])
    heat_saved = h["heat_kwh_th"] * h["heat_saving"] / h["cop"] * h["usd_kwh"]
    return {"conventional_usd": conv, "owner_built_usd": owner, "owner_built_berm_usd": berm,
            "berm_extra_usd": berm - owner, "heat_saved_usd_year": heat_saved,
            "payback_years": (berm - owner) / heat_saved}


def mix():
    out = []
    for market in sw.MARKETS:
        for cell in ((0, 150000), (1, 150000), (1, 300000), (2, 300000)):
            r, n = sw.search(market, cell, solo=SOLO, require=("backhoe",))
            out.append({"market": market, "buildings_max": cell[0], "budget": cell[1], "best": r})
    return out


def main():
    digs = [dig(n, s) for s in ("ne_flat", "ne_till", "florida") for n in (1, 2)]
    print("Digging with an owned backhoe:")
    for d in digs:
        print("  %-28s %d ring%s: %s m3, %4.0f backhoe h = %.1f years at 600 h; fuel and wear $%s (machine $%s net)"
              " | hired backhoe $%s, pond crew $%s in %.0f days"
              % (d["soil"], d["rings"], "" if d["rings"] == 1 else "s", "{:,.0f}".format(d["cut_bank_m3"]), d["backhoe_hours"],
                 d["years_at_600h"], "{:,.0f}".format(d["owner_cash_usd"]), "{:,.0f}".format(d["machine_net_usd"]),
                 "{:,.0f}".format(d["hired_backhoe_usd"]), "{:,.0f}".format(d["pond_crew_usd"]), d["pond_crew_days"]))
    h = home()
    print("Owner's earth-berm home, 800 ft2: conventional $%s, owner-built $%s, owner-built into the berm $%s;"
          " saves $%s a year in heat; the extra pays back in %.0f years"
          % ("{:,.0f}".format(h["conventional_usd"]), "{:,.0f}".format(h["owner_built_usd"]),
             "{:,.0f}".format(h["owner_built_berm_usd"]), "{:,.0f}".format(h["heat_saved_usd_year"]), h["payback_years"]))
    res = mix()
    print("Best one-person mix (owner up to %d h a month, paid help up to %d h a year):" % (SOLO["owner_h_month"], SOLO["help_max_h"]))
    for g in res:
        b = g["best"]
        print("  %-8s bld<=%d $%7s: owner's income $%7s a year (after a capital charge $%7s); capex $%7s; owner %4.0f h, help %3.0f h | %s + %s + %s"
              % (g["market"], g["buildings_max"], "{:,}".format(g["budget"]), "{:,.0f}".format(b["net"]),
                 "{:,.0f}".format(b["score"]), "{:,.0f}".format(b["capex"]), b["crew"]["owner_h"], b["crew"]["seasonal_h"],
                 ", ".join(b["features"]), b["animal"], b["aqua"]))
        g["hours_by_month"] = b["hours_by_month"]
    with open(os.path.join(ROOT, "docs", "solo_farm.json"), "w") as fh:
        json.dump({"backhoe": BACKHOE, "home": HOME, "solo": SOLO, "digs": digs, "home_result": h, "mix": res},
                  fh, indent=1, default=float)


if __name__ == "__main__":
    main()
