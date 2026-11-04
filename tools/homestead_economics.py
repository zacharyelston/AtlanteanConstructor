"""Investment and return for the Atlantean homestead: what a site costs, what its soil,
stone, energy and produce return, and what it could sell for as a product.

Reads docs/homestead_numbers.json and docs/energy_budget.json, so run those first:

    python3 tools/homestead_numbers.py && python3 tools/energy_budget.py
    python3 tools/homestead_economics.py

Every price and rate is in PRICES / SCENARIOS / FARM below: screening values from the
sources listed in docs/economics.md. Edit them with local quotes.
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YD3_PER_M3 = 1.308
LB_PER_KG = 2.2046

PRICES = {
    "gravel_usd_per_t": 50.0,            # processed gravel / crushed stone, delivered (30-50 + 10-20 freight)
    "sand_usd_per_t": 40.0,              # concrete / bedding sand, delivered
    "gravel_t_per_m3": 1.8, "sand_t_per_m3": 1.6,
    "loading_usd_per_m3": 2.0,           # excavator loading buyers' trucks
    "bund_usd_per_m3": 2.5,              # dozing surplus into an on-site bund
    "screening_usd_per_m3": 6.0,         # rented screener + loader time, per loose m3 processed
    "topsoil_usd_per_m3": 3.0,           # strip, stockpile, respread (dozer)
    "design_permits_usd": {"new_england": 18000, "florida": 12000},
    "pv_usd_per_w": 3.0,                 # ground-mount, installed; no federal 25D credit after 2025
    "heat_pump_usd_per_ton": 7000,       # ground-source unit installed, loop excluded
    "pond_loop_usd_per_ft": 2.0, "trench_loop_usd_per_ft": 4.0, "bore_loop_usd_per_ton": 15000,
    "electricity_usd_per_kwh": {"new_england": 0.30, "florida": 0.15},
}

# What becomes of the spoil the berms can't take (per LOOSE m3 unless noted).
SCENARIOS = {
    "pay_to_dispose": {"label": "No market: pay to truck it away", "fill_usd_per_yd3": -10.0, "screen": False},
    "bund_on_site": {"label": "Keep it: windbreak bund on site", "fill_usd_per_yd3": None, "screen": False},
    "give_away": {"label": "Give it away: haulers take it free", "fill_usd_per_yd3": 0.0, "screen": False},
    "sell_fill": {"label": "Sell as common fill", "fill_usd_per_yd3": 8.0, "screen": False},
    "screen_and_sell": {"label": "Screen: sell stone + screened fill", "fill_usd_per_yd3": 12.0, "screen": True},
}
STONE = {"new_england": {"fraction_of_bank": 0.15, "t_per_bank_m3_of_stone": 2.6, "usd_per_t": 25.0,
                         "label": "fieldstone, sold rough to a stone yard (retail bulk is about $100/t)"},
         "florida": {"fraction_of_bank": 0.0, "t_per_bank_m3_of_stone": 2.6, "usd_per_t": 0.0, "label": "none"}}

# Bought aggregate: causeway, island drive and courtyard, berm-top paths, pipe bedding, footings.
MATERIALS = {
    "causeway_gravel_m3": 90, "island_gravel_m3": 90, "path_gravel_m3": 150, "drain_gravel_m3": 20,
    "bedding_sand_m3": 20, "footing_sand_m3": 50, "culverts_usd": 3000, "spillway_extras_usd": 3000,
}
# When the till is screened, its stone replaces bought causeway base and drainage stone.
SCREEN_REPLACES_M3 = 90

FARM = {
    "setup_usd": {"fruit trees (about 70)": 4200, "pasture fencing": 3500, "fish stocking": 1500,
                  "ducks and goats": 2000, "aquatic plants": 1000, "solar pump and drip lines": 2000,
                  "floating spoke (stage 2)": 15000},
    "fish_lb_per_acre_yr": {"unfed": 100, "fed": 600}, "fish_usd_per_lb": 4.0,
    "fish_feed_usd_per_lb_fish": 1.0,
    "fruit_lb": 70 * 30, "fruit_usd_per_lb": 2.0,
    "duck_eggs_usd": 1400, "goats_net_usd": 1500, "greens_usd": 1500,
    "upkeep_pct_of_capex": 1.0,
}
YEARS, DISCOUNT = 25, 0.05
PRODUCT_MARGIN = 0.25          # design-build price = build cost x (1 + margin); soil returns kept by the builder
# High tunnels on the pasture berm (tools/greenhouse_budget.py). 0 tunnels = off, which keeps every
# earlier result unchanged.
GREENHOUSE = {"tunnels": 0, "heated": 0, "yields": "typical", "channel": "direct", "hired_labour": True}


def load(name):
    with open(os.path.join(ROOT, "docs", name)) as fh:
        return json.load(fh)


def climate_of(soil_label):
    return "florida" if "Florida" in soil_label else "new_england"


def energy_for(eb, climate, warm_bay=False):
    want = "Florida" if climate == "florida" else "New England"
    return next(e for e in eb if want in e["climate"] and e["warm_bay"] == warm_bay)


def site_economics(r, eb, scenario, fed_fish=False, greenhouse=None):
    clim = climate_of(r["soil"])
    P = PRICES
    capex, onetime = {}, {}
    capex["design, survey, test pits, permits"] = P["design_permits_usd"][clim]
    capex["earthworks (pond crew)"] = r["build"]["excavator_dozer"]["cost_usd"]
    disturbed = r["site_area_m2"] - r["water_area_m2"]
    capex["topsoil strip and respread"] = disturbed * 0.2 * P["topsoil_usd_per_m3"]

    surplus = max(r["spoil"]["surplus_m3"], 0.0) - r["spoil"]["island_raise_m"] * r["island_m2"]
    surplus = max(surplus, 0.0)
    sc = SCENARIOS[scenario]
    mats = dict(MATERIALS)
    stone_t = 0.0
    if sc["fill_usd_per_yd3"] is None:
        capex["surplus spoil: dozed into a bund"] = surplus * P["bund_usd_per_m3"]
    else:
        capex["surplus spoil: loading trucks"] = surplus * P["loading_usd_per_m3"]
        fill_m3 = surplus
        if sc["screen"]:
            capex["surplus spoil: screening"] = surplus * P["screening_usd_per_m3"]
            st = STONE[clim]
            bank = surplus / r["spoil"]["loose_total_m3"] * (r["cut_bank_m3"] + r["spoil"]["winter_holes_bank_m3"])
            stone_bank = bank * st["fraction_of_bank"]
            stone_t = stone_bank * st["t_per_bank_m3_of_stone"]
            used_t = min(stone_t, SCREEN_REPLACES_M3 * P["gravel_t_per_m3"])
            mats["causeway_gravel_m3"] = max(mats["causeway_gravel_m3"] - used_t / P["gravel_t_per_m3"], 0)
            onetime["stone sold"] = (stone_t - used_t) * st["usd_per_t"]
            fill_m3 = surplus * (1 - st["fraction_of_bank"])
        onetime["fill sold (or paid to dispose, if negative)"] = fill_m3 * YD3_PER_M3 * sc["fill_usd_per_yd3"]
    gravel = (mats["causeway_gravel_m3"] + mats["island_gravel_m3"] + mats["path_gravel_m3"]
              + mats["drain_gravel_m3"]) * P["gravel_t_per_m3"] * P["gravel_usd_per_t"]
    sand = (mats["bedding_sand_m3"] + mats["footing_sand_m3"]) * P["sand_t_per_m3"] * P["sand_usd_per_t"]
    capex["gravel bought"] = gravel
    capex["sand bought"] = sand
    capex["culverts, spillway extras"] = mats["culverts_usd"] + mats["spillway_extras_usd"]

    e = energy_for(eb, clim)
    kwp = e["pv_grid_tied"]["kwp"]
    gs = e["ground_source"]
    capex["solar PV (grid-tied)"] = kwp * 1000 * P["pv_usd_per_w"]
    loop = (gs["pond_loop_ft"] * P["pond_loop_usd_per_ft"] if clim == "florida"
            else gs["trench_ft"] * P["trench_loop_usd_per_ft"])
    capex["ground-source heat pump + loop"] = gs["tons"] * P["heat_pump_usd_per_ton"] + loop
    avoided_bore = gs["tons"] * P["bore_loop_usd_per_ton"] - loop
    for k, v in FARM["setup_usd"].items():
        capex["farm: " + k] = v
    gh = dict(GREENHOUSE, **(greenhouse or {}))
    gh_farm = None
    if gh["tunnels"] > 0:
        import greenhouse_budget as gb
        gh_farm = gb.farm(gh["tunnels"], gh["heated"], climate=clim, channel=gh["channel"],
                          yields=gh["yields"], hired_labour=gh["hired_labour"])
        capex["greenhouses: %d tunnels on the pasture berm (after EQIP)" % gh["tunnels"]] = gh_farm["net_capex"]

    # Yearly value
    acres = r["rings"][-1]["water_area_m2"] / 4046.9
    fish_lb = acres * FARM["fish_lb_per_acre_yr"]["fed" if fed_fish else "unfed"]
    yearly = {
        "electricity (PV output at retail rate)": e["electric_kwh"]["total"] * P["electricity_usd_per_kwh"][clim],
        "fish": fish_lb * (FARM["fish_usd_per_lb"] - (FARM["fish_feed_usd_per_lb_fish"] if fed_fish else 0.0)),
        "fruit (mature orchard, year 6+)": FARM["fruit_lb"] * FARM["fruit_usd_per_lb"],
        "duck eggs": FARM["duck_eggs_usd"], "goats (net)": FARM["goats_net_usd"],
        "greens": FARM["greens_usd"],
    }
    total_capex = sum(capex.values())
    gh_capex = sum(v for k, v in capex.items() if k.startswith("greenhouses"))
    upkeep = (total_capex - gh_capex) * FARM["upkeep_pct_of_capex"] / 100.0   # tunnels carry their own upkeep
    if gh_farm:
        yearly["greenhouses (net of inputs, labour, selling, upkeep, heat)"] = gh_farm["net_yearly"]
    net_capex = total_capex - sum(onetime.values())
    net_yearly = sum(yearly.values()) - upkeep
    # NPV: the orchard ramps in over 5 years
    npv = -net_capex
    for y in range(1, YEARS + 1):
        fruit = yearly["fruit (mature orchard, year 6+)"] * min(1.0, y / 6.0)
        cash = net_yearly - yearly["fruit (mature orchard, year 6+)"] + fruit
        npv += cash / (1 + DISCOUNT) ** y
    price = total_capex * (1 + PRODUCT_MARGIN)
    product = {"price_to_buyer": price, "builder_cost": total_capex, "soil_returns_to_builder": sum(onetime.values()),
               "builder_profit": price - total_capex + sum(onetime.values()),
               "price_if_soil_returns_passed_on": price - sum(onetime.values())}
    return {"layout": r["layout"], "soil": r["soil"], "scenario": sc["label"], "fed_fish": fed_fish,
            "product": product,
            "capex": capex, "onetime_returns": onetime, "yearly": yearly, "upkeep": upkeep,
            "total_capex": total_capex, "net_capex": net_capex, "net_yearly": net_yearly,
            "payback_years": net_capex / net_yearly if net_yearly > 0 else None, "npv_25y_5pct": npv,
            "surplus_loose_m3": surplus, "stone_t": stone_t, "fish_lb": fish_lb,
            "avoided_vertical_bore_usd": avoided_bore, "pv_kwp": kwp}


def main():
    hn = load("homestead_numbers.json")
    eb = load("energy_budget.json")
    out = []
    print("Earthworks only, recommended layout (8 ft outer ring): cost after soil and stone returns\n")
    print("%-36s %16s %16s %16s" % ("", "NE 6 ft slope", "NE flat", "Florida"))
    rec = [r for r in hn if r["layout"].startswith("Shallow 0.9 m inner ring, 8 ft")]
    for key, sc in SCENARIOS.items():
        row = []
        for r in rec:
            s = site_economics(r, eb, key)
            earth = (s["capex"]["earthworks (pond crew)"] + sum(v for k, v in s["capex"].items() if "surplus" in k)
                     + s["capex"]["gravel bought"] + s["capex"]["sand bought"] - sum(s["onetime_returns"].values()))
            row.append(earth)
            out.append(s)
        print("%-36s %16s %16s %16s" % (sc["label"][:36], *["${:,.0f}".format(x) for x in row]))
    print("\nWhole homestead (no buildings), surplus screened and sold, unfed fish:")
    for r in hn:
        if r["layout"].startswith("First try"):
            continue
        s = site_economics(r, eb, "screen_and_sell")
        print("  %-60s %-30s capex $%8s  returns $%8s  net $%8s  yearly $%6s  payback %4.1f y  NPV $%8s"
              % (r["layout"][:60], r["soil"], "{:,.0f}".format(s["total_capex"]),
                 "{:,.0f}".format(sum(s["onetime_returns"].values())), "{:,.0f}".format(s["net_capex"]),
                 "{:,.0f}".format(s["net_yearly"]), s["payback_years"] or 0, "{:,.0f}".format(s["npv_25y_5pct"])))
    for fed in (False, True):
        s = site_economics(rec[1], eb, "screen_and_sell", fed_fish=fed)
        print("  NE flat, %s fish: %.0f lb/yr, yearly net $%s, payback %.1f y" % (
            "fed" if fed else "unfed", s["fish_lb"], "{:,.0f}".format(s["net_yearly"]), s["payback_years"] or 0))
    print("\nAs a product (design-build, no buildings, %d %% margin), recommended layout:" % (PRODUCT_MARGIN * 100))
    for key in ("give_away", "sell_fill", "screen_and_sell"):
        for r in rec:
            pr = site_economics(r, eb, key)["product"]
            print("  %-36s %-30s price $%8s  builder profit $%8s  or pass soil on: price $%8s"
                  % (SCENARIOS[key]["label"][:36], r["soil"], "{:,.0f}".format(pr["price_to_buyer"]),
                     "{:,.0f}".format(pr["builder_profit"]), "{:,.0f}".format(pr["price_if_soil_returns_passed_on"])))
    with open(os.path.join(ROOT, "docs", "homestead_economics.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    s = site_economics(rec[1], eb, "screen_and_sell")
    print("\nNE flat, screened: line items")
    for k, v in s["capex"].items():
        print("  %-44s $%9s" % (k, "{:,.0f}".format(v)))
    for k, v in s["onetime_returns"].items():
        print("  return: %-36s $%9s" % (k, "{:,.0f}".format(v)))
    for k, v in s["yearly"].items():
        print("  yearly: %-36s $%9s" % (k, "{:,.0f}".format(v)))
    print("  upkeep %s/yr; ground loop in the berm saves ~$%s vs drilled bores; stone %.0f t; surplus %.0f m3"
          % ("{:,.0f}".format(s["upkeep"]), "{:,.0f}".format(s["avoided_vertical_bore_usd"]), s["stone_t"],
             s["surplus_loose_m3"]))


if __name__ == "__main__":
    main()
