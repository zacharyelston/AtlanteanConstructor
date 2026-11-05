"""Scenario: every cabin comes with a tunnel, plus a resident crew that cooks and cleans.

    python3 tools/structures_budget.py && python3 tools/resident_economy.py

Builds on tools/lease_scenario.py. The site is maxed out:
- 12 resident cabins and 2 crew cabins, each leased with one high tunnel;
- the pasture berm's remaining tunnels go to residents who grow as their main work, as a second tunnel;
- a resident crew cooks the shared dinners and cleans the common buildings.

Residents' outside income (remote work, for example) pays for meals and produce from the site, so part of
the tunnels' market is the site itself. Writes docs/resident_economy.json. Every figure is a screening
ASSUMPTION.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

import commune_scenario as cs  # noqa: E402
import greenhouse_budget as gb  # noqa: E402
import homestead_economics as he  # noqa: E402
import lease_scenario as ls  # noqa: E402
import structures_budget as sb  # noqa: E402

RES = {
    "resident_cabins": 12, "crew_cabins": 2,
    "heated_tunnels": 1,
    "septic_extra_usd": 10000,                 # two more bedrooms on the system
    # the market for the tunnels' produce
    "external_direct_usd": {"cautious": 150000, "base": 200000, "strong": 300000},   # co-op CSA, stand, restaurants
    "internal_spend_per_person_usd": 2000,     # produce, eggs and fish residents buy for their own cooking
    # the shared kitchen
    "dinners_per_week": 6, "ingredients_usd_per_meal": 5.0, "site_produce_share": 0.4,
    "cook_h_week": 30,                         # menu, cooking, kitchen clean-up, preserving the surplus
    "clean_h_week": 13,                        # hall, laundry house, guest bath, cabin turnovers
    "crew_wage_usd_h": 20.0,
    # a tunnel's labour through the year: tomato hours fall in the ~26-week season, greens in the rest
    "tomato_season_weeks": 26, "peak_factor": 1.3,
    "remote_work_h_week": 40,
}


def tunnel_hours():
    ft2 = gb.TUNNEL["width_ft"] * gb.TUNNEL["length_ft"]
    tom = gb.COSTS["labour_h_ft2"]["tomato"] * ft2
    greens = gb.COSTS["labour_h_ft2"]["greens"] * ft2
    season = tom / RES["tomato_season_weeks"] + greens / 52
    return {"year": tom + greens, "avg_week": (tom + greens) / 52, "season_week": season,
            "peak_week": season * RES["peak_factor"]}


def kitchen(people):
    meals = people * RES["dinners_per_week"] * 52
    ingredients = meals * RES["ingredients_usd_per_meal"]
    cook = RES["cook_h_week"] * 52 * RES["crew_wage_usd_h"]
    board_month = (ingredients + cook) / people / 12
    return {"meals": meals, "ingredients": ingredients, "site_produce": ingredients * RES["site_produce_share"],
            "cook_wages": cook, "board_fee_month": board_month, "usd_per_meal": board_month * 12 / (RES["dinners_per_week"] * 52)}


def growers(n_tunnels, market):
    people = RES["resident_cabins"] + RES["crew_cabins"]
    k = kitchen(people)
    internal = people * RES["internal_spend_per_person_usd"] + k["site_produce"]
    saved = gb.COSTS["direct_market_cap_usd"]
    gb.COSTS["direct_market_cap_usd"] = RES["external_direct_usd"][market] + internal
    f = gb.farm(n_tunnels, RES["heated_tunnels"], hired_labour=False)
    one_each = gb.farm(people, RES["heated_tunnels"], hired_labour=False)
    gb.COSTS["direct_market_cap_usd"] = saved
    extra = n_tunnels - people
    return {"market": market, "direct_cap": RES["external_direct_usd"][market] + internal, "internal_market": internal,
            "tunnels": n_tunnels, "revenue": f["revenue"], "net": f["net_yearly"],
            "sold_wholesale": f.get("sold_wholesale_usd", 0.0),
            "avg_net_per_tunnel": f["net_yearly"] / n_tunnels,
            "one_each_net_per_tunnel": one_each["net_yearly"] / people,
            "second_tunnel_net": (f["net_yearly"] - one_each["net_yearly"]) / extra if extra else None}


def corporation(r, eb):
    people = RES["resident_cabins"] + RES["crew_cabins"]
    n_tunnels = gb.layout()["max_tunnels"]
    saved = (copy.deepcopy(ls.LEASE), sb.STRUCTURES["cabin"]["count"], cs.COMMUNE["septic_well_power_usd"])
    ls.LEASE.update({"cabins": people, "tunnels": n_tunnels})
    sb.STRUCTURES["cabin"]["count"] = people
    cs.COMMUNE["septic_well_power_usd"] += RES["septic_extra_usd"]
    try:
        res = ls.build(copy.deepcopy(r), eb, ls.VARIANTS["engineered"])
    finally:
        ls.LEASE.clear()
        ls.LEASE.update(saved[0])
        sb.STRUCTURES["cabin"]["count"] = saved[1]
        cs.COMMUNE["septic_well_power_usd"] = saved[2]
    cleaning = RES["clean_h_week"] * 52 * RES["crew_wage_usd_h"]
    res["costs"]["cleaning crew (residents)"] = cleaning
    res["net_to_investors"] -= cleaning
    res["cash_yield_pct"] = 100 * res["net_to_investors"] / res["equity"]
    res["tunnels"], res["cabins"] = n_tunnels, people
    return res


def households(g, k):
    L = ls.LEASE
    h = tunnel_hours()
    rent = L["cabin_rent_month"] * 12
    board = k["board_fee_month"] * 12
    per = g["one_each_net_per_tunnel"]
    second = g["second_tunnel_net"] or 0.0
    crew_h = (RES["cook_h_week"] + RES["clean_h_week"]) / RES["crew_cabins"]
    crew_pay = crew_h * 52 * RES["crew_wage_usd_h"]
    base = {"rent": rent, "board": board}
    return {
        "Remote worker, one tunnel": {**base, "tunnel_leases": L["tunnel_lease_year"], "tunnel_net": per,
                                      "crew_pay": 0.0, "hours_week_avg": h["avg_week"],
                                      "hours_week_peak": h["peak_week"], "other_work_h_week": RES["remote_work_h_week"]},
        "Grower, two tunnels": {**base, "tunnel_leases": 2 * L["tunnel_lease_year"], "tunnel_net": per + second,
                                "crew_pay": 0.0, "hours_week_avg": 2 * h["avg_week"],
                                "hours_week_peak": 2 * h["peak_week"], "other_work_h_week": 0},
        "Crew member, one tunnel": {**base, "tunnel_leases": L["tunnel_lease_year"], "tunnel_net": per,
                                    "crew_pay": crew_pay, "hours_week_avg": h["avg_week"] + crew_h,
                                    "hours_week_peak": h["peak_week"] + crew_h, "other_work_h_week": crew_h},
    }


def main():
    hn = he.load("homestead_numbers.json")
    eb = he.load("energy_budget.json")
    r = next(x for x in hn if x["layout"].startswith("Shallow 0.9 m inner ring, 8 ft")
             and x["soil"] == "New England till, flat")
    people = RES["resident_cabins"] + RES["crew_cabins"]
    n_tunnels = gb.layout()["max_tunnels"]
    k = kitchen(people)
    h = tunnel_hours()
    print("%d cabins (%d crew), %d tunnels: one per cabin + %d second tunnels" % (people, RES["crew_cabins"], n_tunnels,
                                                                                 n_tunnels - people))
    print("A tunnel takes %.0f h a year: %.0f h/week on average, %.0f in the tomato season, ~%.0f at the peak"
          % (h["year"], h["avg_week"], h["season_week"], h["peak_week"]))
    print("Kitchen: %d dinners a year, board $%.0f/month per person ($%.2f a dinner); crew cooking $%s, cleaning $%s"
          % (k["meals"], k["board_fee_month"], k["usd_per_meal"], "{:,.0f}".format(k["cook_wages"]),
             "{:,.0f}".format(RES["clean_h_week"] * 52 * RES["crew_wage_usd_h"])))
    grow = {m: growers(n_tunnels, m) for m in RES["external_direct_usd"]}
    for m, g in grow.items():
        print("  market %-8s direct cap $%s (site itself $%s): revenue $%s, wholesale $%s, one-each net/tunnel $%s, "
              "second tunnel adds $%s"
              % (m, "{:,.0f}".format(g["direct_cap"]), "{:,.0f}".format(g["internal_market"]), "{:,.0f}".format(g["revenue"]),
                 "{:,.0f}".format(g["sold_wholesale"]), "{:,.0f}".format(g["one_each_net_per_tunnel"]),
                 "{:,.0f}".format(g["second_tunnel_net"])))
    corp = corporation(r, eb)
    print("Corporation: build $%s, loan $%s, net to investors $%s = %.1f %%"
          % ("{:,.0f}".format(corp["total_capex"]), "{:,.0f}".format(corp["loan"]),
             "{:,.0f}".format(corp["net_to_investors"]), corp["cash_yield_pct"]))
    hh = {m: households(g, k) for m, g in grow.items()}
    for name, x in hh["base"].items():
        cost = x["rent"] + x["board"] + x["tunnel_leases"]
        earn = x["tunnel_net"] + x["crew_pay"]
        print("  %-26s pays $%s (rent, board, tunnels); earns $%s on site -> %s$%s; %.0f h/wk on site avg, %.0f peak"
              % (name, "{:,.0f}".format(cost), "{:,.0f}".format(earn), "+" if earn >= cost else "-",
                 "{:,.0f}".format(abs(earn - cost)), x["hours_week_avg"], x["hours_week_peak"]))
    with open(os.path.join(ROOT, "docs", "resident_economy.json"), "w") as fh:
        json.dump({"assumptions": RES, "tunnel_hours": h, "kitchen": k, "growers": grow,
                   "corporation": corp, "households": hh}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
