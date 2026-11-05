"""Scenario: one farm-hub dome on the island, a permanent powered arm, and homes for sale outside the rings.

    python3 tools/structures_budget.py && python3 tools/farm_hub.py

A mixed-use site, an "agrihood" with an Atlantean core:
- the FARM COMPANY owns the rings, tunnels, the arm and one 60 ft dome on the island: farm store, market,
  cafe kitchen, wash-pack and cold room, and the arm's pivot and control room;
- the ARM is permanent: a floating truss from the island edge over the rings to the pasture berm, driven
  by eOx 48 V wheel modules on the berm crowns, powered through a slip ring at the pivot. A tool carriage
  runs along it (watering, fish feeding, harvest bins, a mower deck), and it hauls loads to every tunnel
  door. It is the farm's tender and the site's support vehicle;
- HOMES on the outer border are sold. Every home pays a farm membership (a weekly produce share plus
  access dues), and any homeowner can also buy shares in the farm company, separately from the home;
- VISITORS buy at the store and the cafe.

Writes docs/farm_hub.json. Every figure is a screening ASSUMPTION.
"""
import json
import math
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
import structures_budget as sb  # noqa: E402

HUB = {"label": "Farm hub: 60 ft dome, store, market, cafe (40 seats), wash-pack, arm control",
       "diameter_ft": 60, "guests": 99, "sprinklers": False, "parking": 30, "wc": 3, "fee_factor": 0}
HUB_EXTRA = [  # item, retail, engineered, how; on top of the dome shell and its systems
    ("Cold room and wash-pack station", 40000, 23000, "walk-in cooler kit; stainless sinks and a barrel washer"),
    ("Store fixtures, coolers and point of sale", 25000, 12000, "used display coolers; members build the shelving"),
    ("Arm pivot bearing, slip ring and foundation", 15000, 9000, "a slewing ring on a concrete pier at the hub's edge"),
]
ARM = [
    ("Truss, 58 m from the island edge to the pasture berm", 70000, 40000, "galvanised steel sections, bolted"),
    ("Floats, ice-rated HDPE pontoons", 18000, 12000, "stay in the water through the winter, parked at the island"),
    ("Drive: three eOx 48 V wheel modules on the berm crowns", 24000, 12000, "the eOx drive module, reused"),
    ("Tool carriage running the length of the arm, with hoist", 20000, 10000, "a gantry trolley on the bottom chord"),
    ("Tools: watering boom, fish feeder, harvest bins, mower deck", 15000, 9000, "each a carriage attachment"),
    ("Controls, sensors, cameras, battery buffer", 12000, 7000, "48 V bus shared with the eOx"),
    ("Structural and marine engineering", 15000, 12000, "stamped design for wind and ice"),
]
# What the arm saves: hauling to and from tunnel doors, and most of the ring, orchard and fish work.
ARM_SAVES = {"tunnel_hours_pct": 10, "other_field_h": 2000, "other_field_saved_pct": 40, "maintenance_pct": 3}

HOMES = {
    "count": 16, "ft2": 768, "label": "Cottage, 24 x 32 ft, 2 bedrooms, own kitchen, bath and laundry",
    "scale_factor": 0.9,                 # a bigger plan of the cabin's $/ft2, less per ft2 for fixed items
    "acres": 6, "land_usd_acre": 14400,
    "septic_well_power_usd": 110000,     # 32 bedrooms on a shared system, a well and service
    "trench_usd": None,                  # from event_venue.outside_trench
    "roads_parking_usd_each": 3000, "subdivision_legal_usd": 40000, "contingency_pct": 10,
    "sale_price_usd": 325000,            # below Branford's ~$360k median sale (2026), for a small new 2-bed
    "selling_cost_pct": 6,
    "member_share_usd_month": 130,       # retail value of the weekly produce share
    "member_dues_usd_month": 120,        # access: cafe and store discount, grounds, the arm's upkeep of the commons
    "invest_homes": 8, "invest_each_usd": 25000,   # half the owners buy farm shares
}
VISITORS = {   # cafe covers a day (5 days, 50 weeks), store sales to visitors
    "cautious": {"cafe_covers": 35, "store_produce": 60000, "store_goods": 40000},
    "base": {"cafe_covers": 60, "store_produce": 100000, "store_goods": 80000},
    "strong": {"cafe_covers": 90, "store_produce": 160000, "store_goods": 120000},
}
CAFE = {"days": 250, "check_usd": 18, "food_pct": 30, "site_share_of_food": 0.5, "other_pct": 12}
STORE = {"goods_margin_pct": 35}
OUTSIDE_DIRECT = 80000               # CSA shares and restaurants beyond the site
STAFF = [("Farm manager and head grower", 1, 55000), ("Growers", 4, 40000), ("Arm and machine technician", 1, 45000),
         ("Chef", 1, 55000), ("Cook", 1, 40000), ("Store and front of house", 2, 36000)]
BURDEN_PCT = 12
# Levers that make the farm pay its way: homeowners trade work for credit, and the hub holds ticketed
# farm dinners after the cafe closes.
LEVERS = {"work_share_h_week_per_home": 3, "weeks": 50,
          "dinners": 24, "seats": 40, "ticket_usd": 110, "dinner_food_pct": 30, "dinner_other_pct": 8,
          "dinner_staff_h": 24}
FARM_LAND_ACRES = 9
FARM_PV_KW = 12
LOAN = (0.07, 25)


def lines_total(lines, retail):
    base = sum(x[1] if retail else x[2] for x in lines)
    return base * (1 + sb.GC_MARGIN) if retail else base


def hub_capex():
    d = ev.dome_capex(HUB)
    return {"retail": d["retail"] + lines_total(HUB_EXTRA, True), "engineered": d["engineered"] + lines_total(HUB_EXTRA, False),
            "ft2": d["ft2"], "lines": d["lines"] + [{"item": i, "retail": r, "engineered": e, "how": h} for i, r, e, h in HUB_EXTRA]}


def arm_capex():
    return {"retail": lines_total(ARM, True), "engineered": lines_total(ARM, False),
            "lines": [{"item": i, "retail": r, "engineered": e, "how": h} for i, r, e, h in ARM]}


def arm_savings():
    t = re_.tunnel_hours()["year"] * gb.layout()["max_tunnels"]
    saved_h = t * ARM_SAVES["tunnel_hours_pct"] / 100 + ARM_SAVES["other_field_h"] * ARM_SAVES["other_field_saved_pct"] / 100
    return {"field_hours": t + ARM_SAVES["other_field_h"], "saved_hours": saved_h, "saved_fte": saved_h / 2000,
            "saved_usd": saved_h * gb.COSTS["labour_usd_h"] * (1 + BURDEN_PCT / 100)}


def homes():
    h = HOMES
    cab = sb.summary()["structures"]["cabin"]
    each = {m: cab["%s_usd_ft2" % m] * h["ft2"] * h["scale_factor"] for m in ("retail", "engineered")}
    _, trench = ev.outside_trench("retail")
    shared = (h["acres"] * h["land_usd_acre"] + h["septic_well_power_usd"] + trench + h["subdivision_legal_usd"]) / h["count"]
    out = {}
    for m in ("retail", "engineered"):
        allin = (each[m] + shared + h["roads_parking_usd_each"]) * (1 + h["contingency_pct"] / 100)
        net_sale = h["sale_price_usd"] * (1 - h["selling_cost_pct"] / 100)
        out[m] = {"cottage": each[m], "site_share": shared + h["roads_parking_usd_each"], "all_in": allin,
                  "margin_each": net_sale - allin, "margin_total": (net_sale - allin) * h["count"]}
    return out


def farm_capex(corp):
    keep = ("design", "earthworks", "topsoil", "surplus spoil", "gravel", "sand", "culverts", "farm:", "greenhouses",
            "ground-source", "Workshop", "formation")
    lines = {k: v for k, v in corp["capex"].items() if k.startswith(keep) and "floating spoke" not in k}
    lines["farm hub dome (store, cafe, wash-pack, arm control)"] = hub_capex()["engineered"]
    lines["the arm (permanent, powered)"] = arm_capex()["engineered"]
    lines["solar PV for the hub and tunnels (%d kW)" % FARM_PV_KW] = FARM_PV_KW * 1000 * cs.COMMUNE["pv_usd_per_w"]
    lines["land, %d acres" % FARM_LAND_ACRES] = FARM_LAND_ACRES * cs.COMMUNE["land_usd_per_acre"]
    lines["septic, well and power for the hub and cafe"] = 45000
    lines["contingency (10 %)"] = sum(lines.values()) * 0.10
    return lines


def operations(visitors, levers=False):
    v, h = VISITORS[visitors], HOMES
    cafe_rev = v["cafe_covers"] * CAFE["days"] * CAFE["check_usd"]
    cafe_food = cafe_rev * CAFE["food_pct"] / 100
    member_share = h["count"] * h["member_share_usd_month"] * 12
    cap = member_share + cafe_food * CAFE["site_share_of_food"] + v["store_produce"] + OUTSIDE_DIRECT
    saved = gb.COSTS["direct_market_cap_usd"]
    gb.COSTS["direct_market_cap_usd"] = cap
    f = gb.farm(gb.layout()["max_tunnels"], 1, hired_labour=False)
    gb.COSTS["direct_market_cap_usd"] = saved
    payroll = sum(n * w for _, n, w in STAFF) * (1 + BURDEN_PCT / 100)
    revenue = {"produce from 17 tunnels (shares, store, cafe, CSA)": f["revenue"],
               "cafe": cafe_rev, "store: other local goods": v["store_goods"],
               "member access dues (%d homes)" % h["count"]: h["count"] * h["member_dues_usd_month"] * 12,
               "orchard, fish, eggs, goats": 9044.0}
    costs = {"payroll (%d staff, with burden)" % sum(n for _, n, _ in STAFF): payroll,
             "tunnel inputs, selling, upkeep, heat": f["revenue"] - f["net_yearly"],
             "cafe food and supplies": cafe_food + cafe_rev * CAFE["other_pct"] / 100,
             "store goods bought in": v["store_goods"] * (1 - STORE["goods_margin_pct"] / 100)}
    if levers:
        L = LEVERS
        d_rev = L["dinners"] * L["seats"] * L["ticket_usd"]
        revenue["farm dinners in the hub"] = d_rev
        costs["farm dinners: food, supplies, extra staff"] = (d_rev * (L["dinner_food_pct"] + L["dinner_other_pct"]) / 100
                                                             + L["dinners"] * L["dinner_staff_h"] * gb.COSTS["labour_usd_h"])
        costs["payroll (%d staff, with burden)" % sum(n for _, n, _ in STAFF)] -= (
            h["count"] * L["work_share_h_week_per_home"] * L["weeks"] * gb.COSTS["labour_usd_h"] * (1 + BURDEN_PCT / 100))
    return {"revenue": revenue, "costs": costs, "direct_cap": cap, "wholesale": f.get("sold_wholesale_usd", 0.0),
            "member_share_value": member_share}


def site_costs(capex):
    c = cs.COMMUNE
    hub, arm = hub_capex()["engineered"], arm_capex()["engineered"]
    structures = hub + capex.get("Workshop and barn, 30 x 40 ft steel arch, unheated (x1), engineered", 29500)
    return {"property tax": (structures * c["assess_ratio"] + FARM_LAND_ACRES * c["pa490_land_usd_per_acre"]
                             * c["assess_ratio"]) * c["mill_rate"] / 1000,
            "insurance": 10000, "utilities and internet": 6000, "building maintenance (1.5 %)": structures * 0.015,
            "arm maintenance (%d %%)" % ARM_SAVES["maintenance_pct"]: arm * ARM_SAVES["maintenance_pct"] / 100,
            "site and farm upkeep": 10801.0}


def main():
    hn = he.load("homestead_numbers.json")
    eb = he.load("energy_budget.json")
    r = next(x for x in hn if x["layout"].startswith("Shallow 0.9 m inner ring, 8 ft")
             and x["soil"] == "New England till, flat")
    corp = re_.corporation(r, eb)
    hub, arm, sav, hm = hub_capex(), arm_capex(), arm_savings(), homes()
    cap = farm_capex(corp)
    total = sum(cap.values())
    print("Hub dome %s ft2: retail $%s, engineered $%s" % ("{:,.0f}".format(hub["ft2"]), "{:,.0f}".format(hub["retail"]),
                                                          "{:,.0f}".format(hub["engineered"])))
    print("Arm: retail $%s, engineered $%s; saves %.0f of %.0f field hours (%.1f FTE, $%s a year)"
          % ("{:,.0f}".format(arm["retail"]), "{:,.0f}".format(arm["engineered"]), sav["saved_hours"], sav["field_hours"],
             sav["saved_fte"], "{:,.0f}".format(sav["saved_usd"])))
    for m, x in hm.items():
        print("Homes (%s): cottage $%s + site $%s -> all-in $%s; sold at $%s -> margin $%s each, $%s total"
              % (m, "{:,.0f}".format(x["cottage"]), "{:,.0f}".format(x["site_share"]), "{:,.0f}".format(x["all_in"]),
                 "{:,}".format(HOMES["sale_price_usd"]), "{:,.0f}".format(x["margin_each"]), "{:,.0f}".format(x["margin_total"])))
    sc = site_costs(cap)
    returns = corp["soil_returns"]
    owners = HOMES["invest_homes"] * HOMES["invest_each_usd"]
    home_margin = hm["retail"]["margin_total"]           # contractor-built homes, sold turnkey
    equity = owners + home_margin
    loan = max(total - returns - equity, 0.0)
    i, n = LOAN
    debt = loan * i / (1 - (1 + i) ** -n) if loan else 0.0
    print("Farm build $%s; fill sold $%s; equity: homeowners' shares $%s + home-sale margin $%s; loan $%s ($%s/yr)"
          % tuple("{:,.0f}".format(x) for x in (total, returns, owners, home_margin, loan, debt)))
    runs = {}
    for lv in (False, True):
        for vk in VISITORS:
            o = operations(vk, lv)
            noi = sum(o["revenue"].values()) - sum(o["costs"].values()) - sum(sc.values())
            surplus = noi - debt
            dues_even = HOMES["member_dues_usd_month"] + max(-surplus, 0) / HOMES["count"] / 12
            key = vk + ("+levers" if lv else "")
            runs[key] = {**o, "noi": noi, "debt_service": debt, "surplus": surplus,
                         "yield_on_equity_pct": 100 * surplus / equity, "dues_to_break_even": dues_even}
            print("  %-16s revenue $%s, NOI $%s, surplus $%s = %.1f %% on $%s equity; wholesale $%s; dues to break even $%.0f"
                  % (key, "{:,.0f}".format(sum(o["revenue"].values())), "{:,.0f}".format(noi), "{:,.0f}".format(surplus),
                     100 * surplus / equity, "{:,.0f}".format(equity), "{:,.0f}".format(o["wholesale"]), dues_even))
    base = runs["base+levers"]
    for k, v in base["revenue"].items():
        print("    + %-52s $%9s" % (k, "{:,.0f}".format(v)))
    for k, v in list(base["costs"].items()) + list(sc.items()):
        print("    - %-52s $%9s" % (k, "{:,.0f}".format(v)))
    h = HOMES
    print("A homeowner pays $%d/month to the farm ($%d share + $%d dues); an investing owner's $%s earns $%s a year (base)"
          % (h["member_share_usd_month"] + h["member_dues_usd_month"], h["member_share_usd_month"], h["member_dues_usd_month"],
             "{:,}".format(h["invest_each_usd"]), "{:,.0f}".format(h["invest_each_usd"] * base["yield_on_equity_pct"] / 100)))
    with open(os.path.join(ROOT, "docs", "farm_hub.json"), "w") as fh:
        json.dump({"hub": hub, "arm": arm, "arm_savings": sav, "homes": hm, "homes_assumptions": HOMES,
                   "farm_capex": cap, "farm_total": total, "soil_returns": returns, "equity": equity,
                   "owner_shares": owners, "home_sale_margin": home_margin, "loan": loan, "site_costs": sc,
                   "visitors": VISITORS, "staff": STAFF, "levers": LEVERS, "runs": runs}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
