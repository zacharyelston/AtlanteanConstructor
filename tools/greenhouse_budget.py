"""High tunnels on the pasture berm: layout, season, yields, energy, labour and return.

    python3 tools/greenhouse_budget.py

Writes docs/greenhouse_budget.json. Reads the berm geometry from docs/homestead_numbers.json
and ring_engine/homestead_params.json. Every rate is in TUNNEL / CROPS / COSTS / HEAT below;
sources are in docs/greenhouse.md. Screening figures, not a crop plan.
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FT2_PER_M2 = 10.764

TUNNEL = {"width_ft": 24, "length_ft": 72, "gap_m": 3.0, "causeway_gap_m": 8.0,
          "cover_to_floor": 1.7}                     # gothic arch + end walls: cover area / floor area

# Yields and prices per square foot of tunnel floor per year.
CROPS = {
    "tomato_lb_ft2": {"typical": 1.78, "optimal": 3.0},   # UVM survey of 47 NE growers; top growers 3-5
    "tomato_usd_lb": {"direct": 4.56, "wholesale": 2.50},
    "winter_greens_usd_ft2": {"unheated": 3.0, "heated": 5.9},   # heated: ~97 % more late kale (SARE FNC21-1277)
    "shoulder_greens_usd_ft2": 1.0,                       # spring greens before tomatoes go in
    "wholesale_greens_factor": 0.55,
}
COSTS = {
    "installed_usd_ft2": 5.0,              # kit, end walls, roll-up sides, drip, labour (basic: $3-6/ft2)
    "eqip_usd_ft2": 3.76, "eqip_cap_ft2": 2178,           # NRCS EQIP high-tunnel practice, one producer
    "inputs_usd_ft2": 1.0,                 # seed, transplants, trellis, plastic reserve, amendments
    "aquaponic_input_saving": 0.25,        # ring water through the drip lines replaces some fertiliser
    "labour_h_ft2": {"tomato": 0.25, "greens": 0.10},     # ASSUMED: ~600 h a 24x72 tunnel; checked against
                                                          # Iowa's $1.1-2.6/ft2 net (Practical Farmers)
    "labour_usd_h": 18.0,
    "selling_cost_pct_of_direct": 15.0,    # market fees, stand, packaging, time at market
    "upkeep_pct": 2.0,                     # of the tunnel's installed cost per year
    "direct_market_cap_usd": 80000,        # what one homestead can sell retail a year (stand, CSA, restaurants);
                                           # anything beyond sells wholesale
}
HEAT = {
    "u_btu_hr_ft2_f": 0.75,                # double inflated poly
    "frost_free_degree_days_f": {"new_england": 1500, "florida": 0},   # below 40 F, Hartford-ish
    "solar_credit": 0.35,                  # daytime gain offsets part of the night loss
    "heat_pump_cop": 3.0, "pv_kwh_per_kwp": {"new_england": 1200, "florida": 1450}, "pv_usd_per_w": 3.0,
    "electricity_usd_per_kwh": {"new_england": 0.30, "florida": 0.15},
}
SEASON = {   # what a tunnel adds over open ground on the berm, weeks of harvest
    "new_england": {"open_field": 20, "unheated_tunnel": 36, "frost_free_tunnel": 52,
                    "notes": "Tunnels plant tomatoes ~4 weeks early and pick ~4 weeks late; winter greens "
                             "grow slowly Nov-Feb under row cover, much faster frost-free."},
    "florida": {"open_field": 30, "unheated_tunnel": 44, "frost_free_tunnel": 44,
                "notes": "Florida's prime season is winter; tunnels protect from rain, pests and the odd "
                         "freeze, and need shade cloth and full ventilation in summer."},
}


def layout():
    with open(os.path.join(ROOT, "docs", "homestead_numbers.json")) as fh:
        hn = json.load(fh)
    with open(os.path.join(ROOT, "ring_engine", "homestead_params.json")) as fh:
        p = json.load(fh)
    r = next(x for x in hn if x["layout"].startswith("Shallow 0.9 m inner ring, 8 ft") and "flat" in x["soil"]
             and "New England" in x["soil"])
    crown = r["berms"][1]["flat_crown_width_m"]
    b = p["berms"][1]
    rc = 0.5 * (b["r_in"] + b["r_out"])
    w, l = TUNNEL["width_ft"] * 0.3048, TUNNEL["length_ft"] * 0.3048
    bow = l * l / (8 * rc)
    n_max = int((2 * math.pi * rc - TUNNEL["causeway_gap_m"]) / (l + TUNNEL["gap_m"]))
    return {"berm_crown_width_m": crown, "ring_radius_m": rc, "tunnel_ft": [TUNNEL["width_ft"], TUNNEL["length_ft"]],
            "tunnel_floor_ft2": TUNNEL["width_ft"] * TUNNEL["length_ft"], "footprint_with_bow_m": w + bow,
            "fits": w + bow <= crown - 0.3, "max_tunnels": n_max,
            "max_floor_ft2": n_max * TUNNEL["width_ft"] * TUNNEL["length_ft"]}


def per_tunnel(climate="new_england", channel="direct", yields="typical", heated=False, hired_labour=True,
               first_tunnel=False):
    """One 24x72 ft tunnel for a year, $ (positive = income)."""
    ft2 = TUNNEL["width_ft"] * TUNNEL["length_ft"]
    tom = CROPS["tomato_lb_ft2"][yields] * CROPS["tomato_usd_lb"][channel]
    greens = CROPS["winter_greens_usd_ft2"]["heated" if heated else "unheated"] + CROPS["shoulder_greens_usd_ft2"]
    if channel == "wholesale":
        greens *= CROPS["wholesale_greens_factor"]
    if climate == "florida":                # winter-season crops; summer tomatoes are hard under plastic
        tom *= 0.7
    revenue = (tom + greens) * ft2
    inputs = COSTS["inputs_usd_ft2"] * (1 - COSTS["aquaponic_input_saving"]) * ft2
    labour_h = (COSTS["labour_h_ft2"]["tomato"] + COSTS["labour_h_ft2"]["greens"]) * ft2
    labour = labour_h * COSTS["labour_usd_h"] if hired_labour else 0.0
    selling = revenue * COSTS["selling_cost_pct_of_direct"] / 100 if channel == "direct" else 0.0
    capex = COSTS["installed_usd_ft2"] * ft2
    grant = COSTS["eqip_usd_ft2"] * min(ft2, COSTS["eqip_cap_ft2"]) if first_tunnel else 0.0
    upkeep = capex * COSTS["upkeep_pct"] / 100
    heat_kwh_th = heat_kwh_e = pv_capex = 0.0
    if heated:
        dd = HEAT["frost_free_degree_days_f"][climate]
        btu = HEAT["u_btu_hr_ft2_f"] * TUNNEL["cover_to_floor"] * ft2 * dd * 24 * (1 - HEAT["solar_credit"])
        heat_kwh_th = btu / 3412.0
        heat_kwh_e = heat_kwh_th / HEAT["heat_pump_cop"]
        pv_capex = heat_kwh_e / HEAT["pv_kwh_per_kwp"][climate] * 1000 * HEAT["pv_usd_per_w"]
    energy = heat_kwh_e * HEAT["electricity_usd_per_kwh"][climate]
    net = revenue - inputs - labour - selling - upkeep - energy
    return {"floor_ft2": ft2, "revenue": revenue, "inputs": inputs, "labour": labour, "labour_h": labour_h,
            "selling": selling, "upkeep": upkeep, "energy": energy, "net_yearly": net,
            "capex": capex + pv_capex, "grant": grant, "net_capex": capex + pv_capex - grant,
            "payback_years": (capex + pv_capex - grant) / net if net > 0 else None,
            "heat_kwh_th": heat_kwh_th, "heat_kwh_e": heat_kwh_e,
            "pv_panels_for_heat": math.ceil(heat_kwh_e / HEAT["pv_kwh_per_kwp"][climate] * 1000 / 430) if heated else 0,
            "revenue_ft2": revenue / ft2, "net_ft2": net / ft2}


def farm(n, n_heated=0, **kw):
    """n tunnels, the first n_heated of them frost-free; the first gets the EQIP cost-share."""
    tot = {}
    for i in range(n):
        t = per_tunnel(heated=i < n_heated, first_tunnel=(i == 0), **kw)
        for k, v in t.items():
            if isinstance(v, (int, float)) and v is not None:
                tot[k] = tot.get(k, 0.0) + v
    tot["tunnels"], tot["heated"] = n, n_heated
    cap = COSTS["direct_market_cap_usd"]
    if kw.get("channel", "direct") == "direct" and tot["revenue"] > cap:
        excess = tot["revenue"] - cap
        whole = farm(1, 0, **{**kw, "channel": "wholesale"})
        direct = per_tunnel(**{**kw, "heated": False})
        ratio = whole["revenue"] / direct["revenue"]           # wholesale is worth this fraction of direct
        lost = excess * (1 - ratio)
        tot["revenue"] -= lost
        tot["selling"] -= excess * COSTS["selling_cost_pct_of_direct"] / 100   # no market costs on wholesale
        tot["net_yearly"] -= lost - excess * COSTS["selling_cost_pct_of_direct"] / 100
        tot["sold_wholesale_usd"] = excess * ratio
    tot["payback_years"] = tot["net_capex"] / tot["net_yearly"] if tot.get("net_yearly", 0) > 0 else None
    tot["fte"] = tot.get("labour_h", 0) / 2000.0
    return tot


def main():
    lay = layout()
    print("Layout: %d x %d ft tunnels, footprint %.2f m on a %.2f m crown (%s); up to %d tunnels = %s ft2"
          % (*lay["tunnel_ft"], lay["footprint_with_bow_m"], lay["berm_crown_width_m"],
             "fits" if lay["fits"] else "too wide", lay["max_tunnels"], "{:,}".format(lay["max_floor_ft2"])))
    cases = []
    print("\nOne tunnel, New England (hired labour):")
    for label, kw in (("unheated, typical yield, wholesale", dict(channel="wholesale")),
                      ("unheated, typical yield, direct", dict()),
                      ("unheated, optimal yield, direct", dict(yields="optimal")),
                      ("frost-free, optimal yield, direct", dict(yields="optimal", heated=True)),
                      ("unheated, optimal yield, direct, family labour", dict(yields="optimal", hired_labour=False))):
        t = per_tunnel(**kw)
        cases.append({"case": label, **t})
        print("  %-46s revenue $%6s ($%5.2f/ft2)  net $%6s/yr ($%5.2f/ft2)  capex $%6s  payback %s  labour %3.0f h%s"
              % (label, "{:,.0f}".format(t["revenue"]), t["revenue_ft2"], "{:,.0f}".format(t["net_yearly"]),
                 t["net_ft2"], "{:,.0f}".format(t["capex"]),
                 "%.1f y" % t["payback_years"] if t["payback_years"] else "never", t["labour_h"],
                 ("  heat %s kWh_th -> %s kWh_e, +%d panels" % ("{:,.0f}".format(t["heat_kwh_th"]),
                                                               "{:,.0f}".format(t["heat_kwh_e"]),
                                                               t["pv_panels_for_heat"])) if kw.get("heated") else ""))
    print("\nScaling (New England, optimal yield, direct, hired labour):")
    scale = []
    for n, h in ((2, 0), (4, 1), (8, 2), (lay["max_tunnels"], 2)):
        f = farm(n, h, yields="optimal")
        scale.append(f)
        print("  %2d tunnels (%d frost-free): %6s ft2, revenue $%7s, net $%7s/yr, capex $%7s, payback %.1f y, "
              "labour %4.0f h (%.1f FTE)" % (n, h, "{:,.0f}".format(f["floor_ft2"]), "{:,.0f}".format(f["revenue"]),
                                             "{:,.0f}".format(f["net_yearly"]), "{:,.0f}".format(f["net_capex"]),
                                             f["payback_years"] or 0, f["labour_h"], f["fte"]))
    fl = per_tunnel(climate="florida", yields="optimal")
    print("\nFlorida, one unheated tunnel, optimal, direct: revenue $%s, net $%s/yr, payback %.1f y"
          % ("{:,.0f}".format(fl["revenue"]), "{:,.0f}".format(fl["net_yearly"]), fl["payback_years"] or 0))
    with open(os.path.join(ROOT, "docs", "greenhouse_budget.json"), "w") as fh:
        json.dump({"layout": lay, "one_tunnel_new_england": cases, "scaling_new_england": scale,
                   "florida_one_tunnel": fl, "season_weeks": SEASON,
                   "assumptions": {"tunnel": TUNNEL, "crops": CROPS, "costs": COSTS, "heat": HEAT}}, fh, indent=1)


if __name__ == "__main__":
    main()
