"""Scenario: a site corporation owns and runs the homestead; residents lease cabins, growers lease tunnels.

    python3 tools/structures_budget.py && python3 tools/lease_scenario.py

Ten investors put in $100k each (they may also be residents). The corporation (an LLC or a
cooperative) owns the land, rings, buildings and tunnels, borrows any shortfall, and earns
from leases. Writes docs/lease_scenario.json. Every figure in LEASE is a screening ASSUMPTION.
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

import commune_scenario as cs  # noqa: E402
import greenhouse_budget as gb  # noqa: E402
import homestead_economics as he  # noqa: E402
import structures_budget as sb  # noqa: E402

LEASE = {
    "investors": 10, "equity_each": 100000,
    "cabins": 12, "cabin_rent_month": 1300,          # private bath and kitchenette; shared hall, laundry, energy, internet
    "vacancy_pct": 5,
    "tunnels": 11, "tunnel_lease_year": 3000,         # a grower keeps the rest (about $13k a tunnel, own labour)
    "site_manager_year": 24000,                       # part-time; or a resident's rent credit
    "insurance_year": 8000, "grid_internet_year": 4000,
    "maintenance_pct_structures": 1.5, "reserve_pct_site": 0.5,
    "studio_rent_branford": (1500, 2200),             # 2026 studio asking rents
}
VARIANTS = {
    "engineered": {"label": "Engineered structures, fill sold at $8/yd3", "structures": "engineered", "fill": 8.0},
    "retail_ours": {"label": "Same design at retail prices, no fill market", "structures": "retail", "fill": 0.0},
    "conventional": {"label": "Conventional: 12 turnkey contractor ADUs, no common hall, no fill market",
                     "structures": "conventional", "fill": 0.0},
}


def build(r, eb, v):
    c, L = cs.COMMUNE, LEASE
    he.SCENARIOS["_l"] = {"label": "lease", "fill_usd_per_yd3": v["fill"], "screen": False}
    s = he.site_economics(r, eb, "_l", greenhouse={"tunnels": L["tunnels"], "heated": 1, "yields": "typical",
                                                    "channel": "direct", "hired_labour": False})
    capex = dict(s["capex"])
    capex.pop("solar PV (grid-tied)")
    capex.pop("ground-source heat pump + loop")
    people = L["cabins"]
    heat_th = c["heat_kwh_th_per_dome"] * 2 + 1500 * L["cabins"]      # hall + laundry house + cabins
    elec = people * c["kwh_per_person"] + 2750 + heat_th / c["cop_heat"] + people * c["dhw_kwh_th_per_person"] / c["cop_dhw"]
    kwp = elec / c["pv_kwh_per_kwp"]
    capex["solar PV (%.0f kW)" % kwp] = kwp * 1000 * c["pv_usd_per_w"]
    capex["ground-source heat pump for hall and laundry house, 3 ton"] = 3 * c["gshp_usd_per_ton"] + 600 * c["trench_usd_per_ft"]
    st = sb.summary()
    if v["structures"] == "conventional":
        structures = st["conventional"]["total"]
        capex["12 turnkey ADUs + workshop, retail"] = structures
    else:
        mode = "retail_each" if v["structures"] == "retail" else "engineered_each"
        structures = 0.0
        for key, x in st["structures"].items():
            capex["%s (x%d), %s" % (x["label"], x["count"], v["structures"])] = x[mode] * x["count"]
            structures += x[mode] * x["count"]
    capex["land, %d acres" % c["acres"]] = c["acres"] * c["land_usd_per_acre"]
    capex["septic, well, power service"] = c["septic_well_power_usd"]
    capex["formation, leases, zoning and engineering"] = c["formation_legal_usd"]
    capex["contingency (10 %)"] = sum(capex.values()) * 0.10
    total = sum(capex.values())
    returns = sum(s["onetime_returns"].values())
    equity = L["investors"] * L["equity_each"]
    loan = max(total - returns - equity, 0.0)
    debt = loan * c["loan_rate"] / (1 - (1 + c["loan_rate"]) ** -c["loan_years"]) if loan else 0.0
    rent = L["cabins"] * L["cabin_rent_month"] * 12 * (1 - L["vacancy_pct"] / 100)
    tunnels = L["tunnels"] * L["tunnel_lease_year"]
    other_farm = sum(v_ for k, v_ in s["yearly"].items() if not k.startswith(("greenhouses", "electricity")))
    tax = (structures * c["assess_ratio"] + c["acres"] * c["pa490_land_usd_per_acre"] * c["assess_ratio"]) * c["mill_rate"] / 1000
    costs = {"debt service": debt, "property tax": tax, "insurance": L["insurance_year"],
             "site manager": L["site_manager_year"], "grid and internet": L["grid_internet_year"],
             "building maintenance": structures * L["maintenance_pct_structures"] / 100,
             "site and farm upkeep": s["upkeep"] + total * L["reserve_pct_site"] / 100}
    income = {"cabin leases (5 % vacancy)": rent, "tunnel leases": tunnels, "orchard, fish, eggs, goats": other_farm}
    net = sum(income.values()) - sum(costs.values())
    # rent that gives investors a 5 % cash yield
    need = 0.05 * equity - (net - rent)
    rent_for_5 = need / (L["cabins"] * 12 * (1 - L["vacancy_pct"] / 100))
    return {"variant": v["label"], "capex": capex, "total_capex": total, "soil_returns": returns,
            "equity": equity, "loan": loan, "income": income, "costs": costs, "net_to_investors": net,
            "cash_yield_pct": 100 * net / equity, "rent_for_5pct_yield": rent_for_5,
            "structures_cost": structures, "kwp": kwp,
            "grower_net_per_tunnel": gb.per_tunnel(hired_labour=False)["net_yearly"] - L["tunnel_lease_year"]}


def main():
    hn = he.load("homestead_numbers.json")
    eb = he.load("energy_budget.json")
    r = next(x for x in hn if x["layout"].startswith("Shallow 0.9 m inner ring, 8 ft")
             and x["soil"] == "New England till, flat")
    out = []
    for key, v in VARIANTS.items():
        res = build(copy.deepcopy(r), eb, v)
        res["key"] = key
        out.append(res)
        print("\n%s" % res["variant"])
        print("  build $%s (structures $%s), fill sold $%s, equity $1M, loan $%s"
              % ("{:,.0f}".format(res["total_capex"]), "{:,.0f}".format(res["structures_cost"]),
                 "{:,.0f}".format(res["soil_returns"]), "{:,.0f}".format(res["loan"])))
        for k, v_ in res["income"].items():
            print("    + %-34s $%9s" % (k, "{:,.0f}".format(v_)))
        for k, v_ in res["costs"].items():
            print("    - %-34s $%9s" % (k, "{:,.0f}".format(v_)))
        print("  net to investors $%s/yr = %.1f %% cash yield on $1M; rent for a 5 %% yield: $%s/month"
              % ("{:,.0f}".format(res["net_to_investors"]), res["cash_yield_pct"], "{:,.0f}".format(res["rent_for_5pct_yield"])))
    print("\nA grower leasing a tunnel keeps about $%s a year (typical yield, sold direct, own labour)"
          % "{:,.0f}".format(out[0]["grower_net_per_tunnel"]))
    with open(os.path.join(ROOT, "docs", "lease_scenario.json"), "w") as fh:
        json.dump({"assumptions": LEASE, "variants": out}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
