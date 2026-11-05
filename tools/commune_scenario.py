"""Scenario: a 10-member commune, $100k each, building the Atlantean homestead together.

    python3 tools/homestead_numbers.py && python3 tools/energy_budget.py   # inputs, if stale
    python3 tools/commune_scenario.py

Adds what the homestead model leaves out (land, buildings, septic, property tax, a household of
12) and replaces hired labour with members' time. Writes docs/commune_scenario.json.
Every figure in COMMUNE / VARIANTS is a screening ASSUMPTION; sources in the business plan.
"""
import copy
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

import greenhouse_budget as gb  # noqa: E402
import homestead_economics as he  # noqa: E402

COMMUNE = {
    "members": 10, "seed_each": 100000, "beds_central": 12,
    "acres": 15, "land_usd_per_acre": 14400,          # USDA NASS 2025 CT farm real estate average
    "dome_ft2_each": 1270,                              # ~33 ft dome: 845 ft2 ground floor + 4-bed loft
    "domes": 3,
    "dome_usd_ft2": {"owner_built": 120, "contractor": 175},
    "septic_well_power_usd": 50000 + 15000 + 20000,     # engineered septic for 12 beds, drilled well, service
    "formation_legal_usd": 15000,                       # LLC or co-op agreement, zoning and septic engineering
    "contingency_pct": 10,
    "kwh_per_person": 1200, "heat_kwh_th_per_dome": 6750, "dhw_kwh_th_per_person": 750,
    "pv_kwh_per_kwp": 1200, "pv_usd_per_w": 3.0, "elec_usd_kwh": 0.30, "cop_heat": 3.5, "cop_dhw": 3.0,
    "gshp_usd_per_ton": 7000, "trench_usd_per_ft": 4.0, "design_kw_per_dome": 5.0,
    "mill_rate": 21.49, "assess_ratio": 0.70,           # Branford FY2025-26; buildings at market, land at PA 490
    "pa490_land_usd_per_acre": 1500,                    # ASSUMED use-value assessment basis
    "insurance_usd": 6000, "maintenance_pct_buildings": 1.0,
    "farm_hours_per_member_week": 15, "weeks": 48,
    "direct_cap_usd": 200000,                           # ten people can sell more than one family
    "rent_equivalent_usd_month": 1000,                  # a room in shared housing, southern CT (ASSUMED)
    "loan_rate": 0.07, "loan_years": 25,                # the shortfall, as a farm or home mortgage (ASSUMED)
}
VARIANTS = {
    "lean": {"label": "Owner-built domes, fill sold at $8/yd3, 8 tunnels", "dome": "owner_built",
             "fill": 8.0, "tunnels": 8},
    "cautious": {"label": "Contractor domes, no fill market, 4 tunnels", "dome": "contractor",
                 "fill": 0.0, "tunnels": 4},
    "full": {"label": "Owner-built domes, fill at $8/yd3, as many tunnels as the members can work",
             "dome": "owner_built", "fill": 8.0, "tunnels": None},
}


def scenario(r, eb, v):
    c = COMMUNE
    hours = c["members"] * c["farm_hours_per_member_week"] * c["weeks"]
    per_tunnel_h = gb.per_tunnel()["labour_h"]
    n_tunnels = v["tunnels"] if v["tunnels"] is not None else min(int(hours // per_tunnel_h),
                                                                  gb.layout()["max_tunnels"])
    saved_cap = gb.COSTS["direct_market_cap_usd"]
    gb.COSTS["direct_market_cap_usd"] = c["direct_cap_usd"]
    he.SCENARIOS["_c"] = {"label": "commune", "fill_usd_per_yd3": v["fill"], "screen": False}
    s = he.site_economics(r, eb, "_c", greenhouse={"tunnels": n_tunnels, "heated": 1, "yields": "typical",
                                                    "channel": "direct", "hired_labour": False})
    gb.COSTS["direct_market_cap_usd"] = saved_cap
    capex = dict(s["capex"])
    # replace the single-household energy system with one sized for the commune
    capex.pop("solar PV (grid-tied)")
    capex.pop("ground-source heat pump + loop")
    people = c["beds_central"]
    heat_th = c["heat_kwh_th_per_dome"] * c["domes"]
    elec = (people * c["kwh_per_person"] + 2750 + heat_th / c["cop_heat"]
            + people * c["dhw_kwh_th_per_person"] / c["cop_dhw"])
    kwp = elec / c["pv_kwh_per_kwp"]
    tons = math.ceil(c["design_kw_per_dome"] * c["domes"] / 3.517 * 2) / 2
    capex["solar PV for 12 people (%.0f kW, %d panels)" % (kwp, math.ceil(kwp * 1000 / 430))] = kwp * 1000 * c["pv_usd_per_w"]
    capex["ground-source heat pump, %.1f ton, berm-core trench" % tons] = (tons * c["gshp_usd_per_ton"]
                                                                          + tons * 200 * c["trench_usd_per_ft"])
    dome_cost = c["domes"] * c["dome_ft2_each"] * c["dome_usd_ft2"][v["dome"]]
    capex["land, %d acres" % c["acres"]] = c["acres"] * c["land_usd_per_acre"]
    capex["3 central domes, %s (%s ft2)" % (v["dome"].replace("_", "-"), "{:,}".format(c["domes"] * c["dome_ft2_each"]))] = dome_cost
    capex["septic for 12 beds, well, power service"] = c["septic_well_power_usd"]
    capex["formation, legal, zoning and engineering"] = c["formation_legal_usd"]
    sub = sum(capex.values())
    capex["contingency (%d %%)" % c["contingency_pct"]] = sub * c["contingency_pct"] / 100
    total = sum(capex.values())
    returns = sum(s["onetime_returns"].values())
    seed = c["members"] * c["seed_each"]
    # yearly cash
    gh = s["yearly"].get("greenhouses (net of inputs, labour, selling, upkeep, heat)", 0.0)
    farm_other = sum(v_ for k, v_ in s["yearly"].items() if not k.startswith(("greenhouses", "electricity")))
    energy_value = elec * c["elec_usd_kwh"]
    tax = (dome_cost * c["assess_ratio"] + c["acres"] * c["pa490_land_usd_per_acre"] * c["assess_ratio"]) * c["mill_rate"] / 1000
    maint = (dome_cost + c["septic_well_power_usd"]) * c["maintenance_pct_buildings"] / 100
    upkeep = s["upkeep"]
    yearly_cash = gh + farm_other - tax - c["insurance_usd"] - maint - upkeep
    housing_value = people * c["rent_equivalent_usd_month"] * 12
    shortfall = max(total - returns - seed, 0.0)
    i, n = c["loan_rate"], c["loan_years"]
    debt = shortfall * i / (1 - (1 + i) ** -n) if shortfall else 0.0
    after_debt = yearly_cash - debt
    return {
        "variant": v["label"], "tunnels": n_tunnels, "member_farm_hours": hours,
        "tunnel_hours": n_tunnels * per_tunnel_h,
        "capex": capex, "total_capex": total, "soil_returns": returns, "net_capex": total - returns,
        "seed": seed, "reserve_after_build": seed - (total - returns),
        "yearly": {"greenhouses (members' labour)": gh, "other farm produce": farm_other,
                   "property tax": -tax, "insurance": -c["insurance_usd"],
                   "building maintenance": -maint, "site and farm upkeep": -upkeep},
        "yearly_cash": yearly_cash, "loan": shortfall, "debt_service": debt, "cash_after_debt": after_debt,
        "energy_bills_avoided": energy_value, "housing_value": housing_value,
        "per_member_cash": after_debt / c["members"],
        "per_member_cash_plus_avoided": (after_debt + energy_value + housing_value) / c["members"],
        "years_to_return_seed_from_cash": seed / after_debt if after_debt > 0 else None,
        "farm_hours_per_member": hours / c["members"],
        "cash_per_member_hour": after_debt / hours,
        "kwp": kwp, "elec_kwh": elec,
    }


def main():
    hn = he.load("homestead_numbers.json")
    eb = he.load("energy_budget.json")
    r = next(x for x in hn if x["layout"].startswith("Shallow 0.9 m inner ring, 8 ft")
             and x["soil"] == "New England till, flat")
    out = []
    for key, v in VARIANTS.items():
        res = scenario(copy.deepcopy(r), eb, v)
        res["key"] = key
        out.append(res)
        print("\n%s" % res["variant"])
        for k, val in res["capex"].items():
            print("  %-58s $%9s" % (k, "{:,.0f}".format(val)))
        print("  %-58s $%9s" % ("TOTAL BUILD", "{:,.0f}".format(res["total_capex"])))
        print("  %-58s $%9s" % ("less fill/stone sold", "{:,.0f}".format(-res["soil_returns"])))
        print("  %-58s $%9s" % ("seed $1M -> reserve after build", "{:,.0f}".format(res["reserve_after_build"])))
        print("  tunnels %d (%.0f h of %.0f member farm hours)" % (res["tunnels"], res["tunnel_hours"], res["member_farm_hours"]))
        for k, val in res["yearly"].items():
            print("    yearly %-30s $%9s" % (k, "{:,.0f}".format(val)))
        print("  loan $%s -> $%s/yr; cash after debt $%s" % ("{:,.0f}".format(res["loan"]), "{:,.0f}".format(res["debt_service"]),
                                                          "{:,.0f}".format(res["cash_after_debt"])))
        print("  per member: cash $%s/yr ($%.0f per farm hour); + energy bills avoided $%s + housing value $%s "
              "-> $%s/member; seed back from cash in %s y" % ("{:,.0f}".format(res["per_member_cash"]), res["cash_per_member_hour"],
                                               "{:,.0f}".format(res["energy_bills_avoided"]), "{:,.0f}".format(res["housing_value"]),
                                               "{:,.0f}".format(res["per_member_cash_plus_avoided"]),
                                               "%.1f" % res["years_to_return_seed_from_cash"] if res["years_to_return_seed_from_cash"] else "never"))
    with open(os.path.join(ROOT, "docs", "commune_scenario.json"), "w") as fh:
        json.dump({"assumptions": COMMUNE, "variants": out}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
