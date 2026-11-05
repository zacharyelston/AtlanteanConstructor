"""Scenario: a host farm sets aside 10 acres for an Atlantean site run as a farm-to-table co-op.

    python3 tools/structures_budget.py && python3 tools/farm_coop.py

There are no investors here. The host farm leases the land to the co-op on a long ground lease; the
co-op borrows to build and is run by its staff, who live in the cabins as farm workforce housing.
The site is the maxed-out design with the event dome (tools/event_venue.py): 14 cabins, 17 tunnels,
the dome on the island, the homes outside the rings.

The co-op earns from produce (CSA, stand, restaurants and its own kitchen), events, ticketed farm
dinners and staff rents, and pays its staff wages. The test is the lender's: does the net operating
income cover the debt service with margin (DSCR >= 1.25)? Writes docs/farm_coop.json.
Every figure is a screening ASSUMPTION.
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
import event_venue as ev  # noqa: E402
import greenhouse_budget as gb  # noqa: E402
import homestead_economics as he  # noqa: E402
import resident_economy as re_  # noqa: E402

COOP = {
    "acres": 10, "ground_lease_usd_acre_year": 200,          # paid to the host farm
    "member_equity_usd": 100000,                             # e.g. 250 community members at $300 + staff buy-ins
    "contingency_pct": 10,
    "housing_share_of_utilities": 0.6,                       # septic, well, power that serve the homes
    # staff, all housed on site; wages before a 12 % payroll burden (taxes, workers' comp)
    "staff": [("Farm manager and head grower", 1, 55000), ("Growers (tunnels, fish, goats, orchard)", 7, 40000),
              ("Chef", 1, 55000), ("Cooks", 2, 40000), ("Events and sales coordinator", 1, 50000),
              ("Site and machine maintenance (eOx, rings, buildings)", 1, 45000), ("Housekeeping and dish", 1, 36000)],
    "payroll_burden_pct": 12,
    "staff_rent_month": 700,                                 # below market, part of the pay package
    "staff_meals_per_week": 6, "meal_food_usd": 5.0,
    # ticketed farm-to-table dinners in the dome, weeknights in the growing season
    "dinners": 26, "seats": 50, "ticket_usd": 110, "dinner_food_pct": 30, "dinner_other_pct": 8,
    "dinner_site_produce_share": 0.5,
    "external_direct_usd": 200000,                           # CSA, stand, restaurants beyond the co-op's own kitchen
    "event_insurance_usd": 10000,
}
# Two ways to run it. "staffed": every cabin houses a salaried employee. "lean": ten staff sized to the
# work (tunnels ~10,300 h + animals and orchard ~2,000 h = about six growers' worth), event days staffed by
# the hour, four cabins leased at market rent (with a tunnel each) to residents who work elsewhere, and
# more dinners.
VARIANTS = {
    "staffed": {"label": "Fully staffed: 14 employees housed on site, 26 dinners a year"},
    "lean": {"label": "Lean: 10 staff, 4 cabins leased at market rent, 40 dinners a year",
             "staff": [("Farm manager and head grower", 1, 55000), ("Growers (tunnels, fish, goats, orchard)", 5, 40000),
                       ("Chef", 1, 55000), ("Cook", 1, 40000), ("Events and sales coordinator", 1, 50000),
                       ("Site and machine maintenance (eOx, rings, buildings)", 1, 45000)],
             "market_cabins": 4, "market_rent_month": 1300, "market_tunnel_lease": 3000,
             "dinners": 40, "event_day_staff": True},
}
RAMP = {"events": {1: 0.4, 2: 0.7, 3: 1.0}, "dinners": {1: 0.6, 2: 0.85, 3: 1.0}, "produce": {1: 0.7, 2: 0.9, 3: 1.0}}
FINANCE = {
    "conventional": {"label": "All from a farm lender at 7 % over 25 years",
                     "tranches": [("Farm lender", None, 0.07, 25)]},
    "usda_mix": {"label": "Housing on a USDA Section 514 loan (1 %, 33 years); $600k FSA direct farm "
                          "ownership (6 %, 40 years); the rest from a farm lender (7 %, 25 years)",
                 "tranches": [("USDA Section 514 farm labor housing", "housing", 0.01, 33),
                              ("FSA direct farm ownership", 600000, 0.06, 40),
                              ("Farm lender", None, 0.07, 25)]},
}


def annuity(p, rate, years):
    return p * rate / (1 - (1 + rate) ** -years) if p > 0 else 0.0


def capex(corp):
    c = COOP
    lines = {k: v for k, v in corp["capex"].items() if not k.startswith(("land", "contingency"))}
    hall_key = next(k for k in lines if k.startswith("Common hall"))
    dome = ev.dome_capex(ev.VENUES["full"])
    lines.pop(hall_key)
    lines["event dome, 60 ft, 150 guests (also the staff dining hall)"] = dome["engineered"]
    trench_ft, trench = ev.outside_trench()
    lines["utility trench to homes outside the rings"] = trench
    sub = sum(lines.values())
    lines["contingency (%d %%)" % c["contingency_pct"]] = sub * c["contingency_pct"] / 100
    total = sum(lines.values())
    homes = sum(v for k, v in lines.items() if k.startswith(("Private cabin", "Laundry")))
    util = next(v for k, v in lines.items() if k.startswith("septic"))
    housing = (homes + util * c["housing_share_of_utilities"] + trench) * (1 + c["contingency_pct"] / 100)
    return {"lines": lines, "total": total, "housing": housing, "dome": dome["engineered"]}


def operations(year=3, variant="staffed"):
    c = {**COOP, **VARIANTS[variant]}
    people = sum(n for _, n, _ in c["staff"])
    market = c.get("market_cabins", 0)
    residents = people + market
    payroll = sum(n * w for _, n, w in c["staff"]) * (1 + c["payroll_burden_pct"] / 100)
    meals_food = residents * c["staff_meals_per_week"] * 52 * c["meal_food_usd"]
    rd = RAMP["dinners"][year]
    dinner_rev = c["dinners"] * c["seats"] * c["ticket_usd"] * rd
    dinner_food = dinner_rev * c["dinner_food_pct"] / 100
    # the venue, base bookings, full dome; its labour is on the staff roster
    e = ev.events(ev.VENUES["full"], "base")
    re_ev = RAMP["events"][year]
    ev_rev = e["revenue"] * re_ev
    skip = ("coordinator",) if c.get("event_day_staff") else ("coordinator", "event-day")
    ev_costs = {k: v * re_ev for k, v in e["costs"].items() if not k.startswith(skip)}
    ev_costs["insurance"] = c["event_insurance_usd"]
    # produce: the co-op's own kitchen and caterers are part of the direct market
    internal = (meals_food * re_.RES["site_produce_share"] + dinner_food * c["dinner_site_produce_share"]
                + e["produce_sold_to_caterers"] * re_ev)
    saved = gb.COSTS["direct_market_cap_usd"]
    gb.COSTS["direct_market_cap_usd"] = c["external_direct_usd"] * RAMP["produce"][year] + internal
    n_t = gb.layout()["max_tunnels"] - market               # residents' own tunnels are theirs to work and sell
    f = gb.farm(n_t, 1, hired_labour=False)
    gb.COSTS["direct_market_cap_usd"] = saved
    revenue = {"produce from %d tunnels" % n_t: f["revenue"], "events (full dome, base bookings)": ev_rev,
               "farm-to-table dinners": dinner_rev, "staff rents": people * c["staff_rent_month"] * 12,
               "orchard, fish, eggs, goats": 9044.0}
    if market:
        revenue["%d cabins leased at market rent, with a tunnel each" % market] = market * (
            c["market_rent_month"] * 12 * 0.95 + c["market_tunnel_lease"])
        revenue["board from the market-rent residents"] = market * re_.kitchen(residents)["board_fee_month"] * 12
    return {"variant": variant, "label": c["label"], "people": people, "market_cabins": market,
            "revenue": revenue, "payroll": payroll,
            "costs": {"payroll (%d staff, with burden)" % people: payroll,
                      "tunnel inputs, selling, upkeep, heat": f["revenue"] - f["net_yearly"],
                      "staff meals (food)": meals_food,
                      "dinners: food and supplies": dinner_food + dinner_rev * c["dinner_other_pct"] / 100,
                      "events: running costs": sum(ev_costs.values())},
            "internal_market": internal, "sold_wholesale": f.get("sold_wholesale_usd", 0.0)}


def site_costs(corp, cap):
    c, k = cs.COMMUNE, corp["costs"]
    dome_tax = (cap["dome"] - 49900) * c["assess_ratio"] * c["mill_rate"] / 1000
    return {"property tax": k["property tax"] + dome_tax, "insurance": k["insurance"],
            "grid and internet": k["grid and internet"], "building maintenance": k["building maintenance"],
            "site and farm upkeep": k["site and farm upkeep"],
            "ground lease to the host farm": COOP["acres"] * COOP["ground_lease_usd_acre_year"]}


def finance(loan, housing, key):
    out, left = [], loan
    for name, amount, rate, years in FINANCE[key]["tranches"]:
        p = min(housing if amount == "housing" else (amount if amount else left), left)
        out.append({"lender": name, "principal": p, "rate": rate, "years": years, "payment": annuity(p, rate, years)})
        left -= p
    return out


def main():
    hn = he.load("homestead_numbers.json")
    eb = he.load("energy_budget.json")
    r = next(x for x in hn if x["layout"].startswith("Shallow 0.9 m inner ring, 8 ft")
             and x["soil"] == "New England till, flat")
    corp = re_.corporation(copy.deepcopy(r), eb)
    cap = capex(corp)
    sc = site_costs(corp, cap)
    loan0 = cap["total"] - corp["soil_returns"] - COOP["member_equity_usd"]
    out = {"assumptions": COOP, "variants": VARIANTS, "ramp": RAMP, "capex": cap, "site_costs": sc, "runs": {}}
    print("Build: $%s (housing $%s), fill sold $%s, member equity $%s"
          % ("{:,.0f}".format(cap["total"]), "{:,.0f}".format(cap["housing"]), "{:,.0f}".format(corp["soil_returns"]),
             "{:,.0f}".format(COOP["member_equity_usd"])))
    for vk in VARIANTS:
        years = {}
        for y in (1, 2, 3):
            o = operations(y, vk)
            years[y] = {**o, "noi": sum(o["revenue"].values()) - sum(o["costs"].values()) - sum(sc.values())}
        y3 = years[3]
        print("\n%s" % y3["label"])
        for k, v in y3["revenue"].items():
            print("  + %-50s $%9s" % (k, "{:,.0f}".format(v)))
        for k, v in list(y3["costs"].items()) + list(sc.items()):
            print("  - %-50s $%9s" % (k, "{:,.0f}".format(v)))
        print("  NOI year 1 $%s, year 2 $%s, year 3 on $%s; site market $%s, wholesale $%s"
              % tuple("{:,.0f}".format(x) for x in (years[1]["noi"], years[2]["noi"], y3["noi"], y3["internal_market"],
                                                     y3["sold_wholesale"])))
        run = {"years": years, "finance": {}}
        for key, f in FINANCE.items():
            t = finance(loan0, cap["housing"], key)
            ds = sum(x["payment"] for x in t)
            reserve = sum(max(ds - years[y]["noi"], 0) for y in (1, 2))
            t = finance(loan0 + reserve, cap["housing"], key)
            ds = sum(x["payment"] for x in t)
            surplus = y3["noi"] - ds
            run["finance"][key] = {"label": f["label"], "loan": loan0 + reserve, "reserve": reserve, "tranches": t,
                                   "debt_service": ds, "dscr": y3["noi"] / ds, "surplus": surplus,
                                   "surplus_per_staff": surplus / y3["people"]}
            print("  %s: loan $%s (incl. $%s start-up reserve), debt service $%s, DSCR %.2f, surplus $%s"
                  % (key, "{:,.0f}".format(loan0 + reserve), "{:,.0f}".format(reserve), "{:,.0f}".format(ds),
                     y3["noi"] / ds, "{:,.0f}".format(surplus)))
        out["runs"][vk] = run
    with open(os.path.join(ROOT, "docs", "farm_coop.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
