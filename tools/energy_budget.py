"""Energy budget for the Atlantean homestead: solar PV, solar thermal and ground-source loops.

Screening sizes for docs/energy.md. Every assumption is in ASSUME / CLIMATES below, so
edit them for a real site and rerun:

    python3 tools/energy_budget.py

Sources for the rules of thumb are listed in docs/energy.md.
"""
import json
import math
import os

KWH_PER_TON_HR = 3.517          # 1 ton of heat pump = 3.517 kW

ASSUME = {
    "panel_w": 430, "panel_m2": 1.95, "ground_m2_per_panel": 3.5,      # row spacing on a fixed ground mount
    "collector_m2": 2.4,                                               # one flat-plate solar thermal collector
    "heat_pump_cop_heat": 3.5, "heat_pump_cop_cool": 5.0, "heat_pump_cop_dhw": 3.0,
    "pond_loop_ft_per_ton": 300, "pond_loop_coil_ft": 300,             # coils laid on the deep-ring bed
    "trench_ft_per_ton": 200,                                          # slinky trench in a berm core, ~6 ft deep
    "eox_pack_kwh": 4.1,                                               # one eOx powerbox, usable
    "inner_ring_m2": 1103, "deep_ring_m2": 4488,                       # from tools/homestead_numbers.py
    "warm_bay_m2": 100,                                                # greenhouse-covered bay of the inner ring
    # lumped heat-loss coefficients of a water surface (evaporation + convection + radiation), W/m2K
    "u_open": 15.0, "u_floating_cover": 5.0, "u_greenhouse_bay": 3.0,
    "spoke_length_m": 26, "panels_per_m_of_spoke": 0.88,               # one row of panels, short side along it
    "design_gust_m_s": 50,                                             # roughly the ASCE 7 wind for CT / central FL
}

CLIMATES = {
    "new_england": {
        "label": "New England (Hartford, CT)",
        "pv_kwh_per_kwp": 1200, "pv_dec_fraction": 0.045, "heat_dec_fraction": 0.16,
        "thermal_kwh_per_m2": 450, "dhw_solar_fraction": 0.65,
        "loads_kwh": {                         # electric unless marked _th (thermal, before the heat pump)
            "household (lights, appliances, cooking, well)": 5000,
            "house heating _th (150 m2, well insulated)": 6750,
            "house cooling _th": 800,
            "hot water _th (family of 4)": 3000,
            "barn (heated troughs, lights)": 900,
            "workshop + eOx charging": 1500,
            "farm (irrigation pump, spoke drive)": 350,
            "winter aerator (optional)": 600,
        },
        "house_design_heat_kw": 5.0,
        "warm_seasons": {"shoulder_days": 90, "shoulder_dT": 8, "winter_days": 180, "winter_dT": 15,
                         "summer_days": 95, "summer_dT": 3},
    },
    "florida": {
        "label": "Florida (Orlando)",
        "pv_kwh_per_kwp": 1450, "pv_dec_fraction": 0.065, "heat_dec_fraction": 0.30,
        "thermal_kwh_per_m2": 650, "dhw_solar_fraction": 0.8,
        "loads_kwh": {
            "household (lights, appliances, cooking, well)": 5000,
            "house heating _th (150 m2, well insulated)": 500,
            "house cooling _th": 9000,
            "hot water _th (family of 4)": 2500,
            "barn (fans, lights)": 500,
            "workshop + eOx charging": 1500,
            "farm (irrigation pump, spoke drive)": 350,
            "winter aerator (optional)": 0,
        },
        "house_design_heat_kw": 3.0,           # sized on cooling: ~2.5 tons
        "warm_seasons": {"shoulder_days": 60, "shoulder_dT": 4, "winter_days": 60, "winter_dT": 8,
                         "summer_days": 245, "summer_dT": 0},
    },
}


def warming_options(c, a):
    """Heat to warm the inner ring three ways, kWh_th per year."""
    w = c["warm_seasons"]
    out = {}
    sh = w["shoulder_days"] * 24 * w["shoulder_dT"] / 1000.0                 # kWh per (W/K) over the shoulders
    out["whole inner ring, open, +%d K in spring and autumn" % w["shoulder_dT"]] = a["u_open"] * a["inner_ring_m2"] * sh
    out["whole inner ring, floating cover, same"] = a["u_floating_cover"] * a["inner_ring_m2"] * sh
    year = (w["shoulder_days"] * w["shoulder_dT"] + w["winter_days"] * w["winter_dT"]
            + w["summer_days"] * w["summer_dT"]) * 24 / 1000.0
    out["%d m2 greenhouse warm bay, warm all year (tilapia, greens)" % a["warm_bay_m2"]] = (
        a["u_greenhouse_bay"] * a["warm_bay_m2"] * year)
    return out


def budget(key, warm_bay=True):
    c, a = CLIMATES[key], ASSUME
    L = c["loads_kwh"]
    heat_th = L["house heating _th (150 m2, well insulated)"]
    cool_th = L["house cooling _th"]
    dhw_th = L["hot water _th (family of 4)"]
    warm = warming_options(c, a)
    bay_th = list(warm.values())[2] if warm_bay else 0.0
    plain = sum(v for k, v in L.items() if "_th" not in k)
    hp_e = heat_th / a["heat_pump_cop_heat"] + cool_th / a["heat_pump_cop_cool"] + bay_th / a["heat_pump_cop_heat"]
    dhw_e = dhw_th / a["heat_pump_cop_dhw"]
    total_e = plain + hp_e + dhw_e
    # Grid-tied, net-zero over the year
    kwp = total_e / c["pv_kwh_per_kwp"]
    panels = math.ceil(kwp * 1000 / a["panel_w"])
    # Off-grid: cover December. Heating-type loads peak then; the rest is spread evenly.
    dec_need = (plain + dhw_e) / 12 + (heat_th + bay_th) / a["heat_pump_cop_heat"] * c["heat_dec_fraction"]
    kwp_offgrid = dec_need / (c["pv_kwh_per_kwp"] * c["pv_dec_fraction"])
    battery_kwh = 2 * dec_need / 31                                            # two days of December use
    # Solar thermal for hot water (alternative to a heat-pump water heater)
    coll_m2 = dhw_th * c["dhw_solar_fraction"] / c["thermal_kwh_per_m2"]
    coll_n = math.ceil(coll_m2 / a["collector_m2"])
    bay_coll_n = math.ceil(bay_th * 0.4 / c["thermal_kwh_per_m2"] / a["collector_m2"]) if bay_th else 0
    # Ground-source heat pump and loops
    bay_kw = a["u_greenhouse_bay"] * a["warm_bay_m2"] * c["warm_seasons"]["winter_dT"] * 1.6 / 1000.0 if warm_bay else 0
    tons = (c["house_design_heat_kw"] + bay_kw) / KWH_PER_TON_HR
    tons_r = math.ceil(tons * 2) / 2
    pond_ft = tons_r * a["pond_loop_ft_per_ton"]
    # What the loop does to the deep ring
    extracted = (heat_th + bay_th + dhw_th) * (1 - 1 / a["heat_pump_cop_heat"])  # heat taken from the ring in winter
    ice_cm = extracted * 3.6e6 / (334e3 * 917) / a["deep_ring_m2"] * 100            # if all of it came out as ice
    rejected = cool_th * (1 + 1 / a["heat_pump_cop_cool"])                         # heat dumped into it in summer
    ring_m3 = 7132
    dT_summer = rejected * 3.6e6 / (ring_m3 * 4.18e6)
    # Spoke as a solar canopy
    spoke_panels = int(a["spoke_length_m"] * a["panels_per_m_of_spoke"])
    q = 0.5 * 1.2 * a["design_gust_m_s"] ** 2
    spoke_wind_kn = q * 1.2 * spoke_panels * a["panel_m2"] / 1000.0
    return {
        "climate": c["label"], "warm_bay": warm_bay,
        "loads": L, "warming_options_kwh_th": warm,
        "electric_kwh": {"plain loads": plain, "heat pump (house + bay)": hp_e, "hot water heat pump": dhw_e,
                         "total": total_e},
        "pv_grid_tied": {"kwp": kwp, "panels": panels, "ground_m2": panels * a["ground_m2_per_panel"]},
        "pv_off_grid": {"december_need_kwh": dec_need, "kwp": kwp_offgrid,
                        "panels": math.ceil(kwp_offgrid * 1000 / a["panel_w"]), "battery_kwh": battery_kwh,
                        "eox_packs": math.ceil(battery_kwh / a["eox_pack_kwh"])},
        "solar_thermal": {"hot_water_collectors": coll_n, "hot_water_m2": coll_m2,
                          "warm_bay_collectors_for_40pct": bay_coll_n},
        "ground_source": {"design_kw": c["house_design_heat_kw"] + bay_kw, "tons": tons_r,
                          "pond_loop_ft": pond_ft, "pond_coils": math.ceil(pond_ft / a["pond_loop_coil_ft"]),
                          "trench_ft": tons_r * a["trench_ft_per_ton"],
                          "winter_heat_from_ring_kwh": extracted, "as_ice_cm_over_deep_ring": ice_cm,
                          "summer_heat_into_ring_kwh": rejected, "summer_ring_rise_K_no_losses": dT_summer},
        "spoke_canopy": {"panels": spoke_panels, "kwp": spoke_panels * a["panel_w"] / 1000.0,
                         "design_gust_load_kN": spoke_wind_kn},
    }


def main():
    res = []
    for key in CLIMATES:
        for bay in (False, True):
            b = budget(key, bay)
            res.append(b)
            print("\n%s, %s" % (b["climate"], "with a warm bay" if bay else "no warm bay"))
            if not bay:
                for k, v in b["warming_options_kwh_th"].items():
                    print("  warming: %-62s %9s kWh_th/yr" % (k, "{:,.0f}".format(v)))
            e = b["electric_kwh"]
            print("  electricity %s kWh/yr (heat pump %s, hot water %s)" % (
                "{:,.0f}".format(e["total"]), "{:,.0f}".format(e["heat pump (house + bay)"]),
                "{:,.0f}".format(e["hot water heat pump"])))
            g, o = b["pv_grid_tied"], b["pv_off_grid"]
            print("  PV grid-tied: %.1f kWp = %d x 430 W panels, ~%.0f m2 of ground" % (g["kwp"], g["panels"], g["ground_m2"]))
            print("  PV off-grid: %.1f kWp = %d panels, battery %.0f kWh (%d eOx packs)" % (
                o["kwp"], o["panels"], o["battery_kwh"], o["eox_packs"]))
            t = b["solar_thermal"]
            print("  solar thermal: %d collectors for hot water (%.1f m2); %d more to give the bay 40 %%" % (
                t["hot_water_collectors"], t["hot_water_m2"], t["warm_bay_collectors_for_40pct"]))
            s = b["ground_source"]
            print("  ground source: %.1f kW -> %.1f ton heat pump; pond loop %d ft (%d coils) or %d ft of berm trench"
                  % (s["design_kw"], s["tons"], s["pond_loop_ft"], s["pond_coils"], s["trench_ft"]))
            print("    winter: %s kWh from the deep ring (= %.1f cm of ice over it); summer: %s kWh in (+%.2f K, no losses)"
                  % ("{:,.0f}".format(s["winter_heat_from_ring_kwh"]), s["as_ice_cm_over_deep_ring"],
                     "{:,.0f}".format(s["summer_heat_into_ring_kwh"]), s["summer_ring_rise_K_no_losses"]))
            sp = b["spoke_canopy"]
            print("  spoke canopy: %d panels (%.1f kWp), design-gust load ~%.0f kN" % (
                sp["panels"], sp["kwp"], sp["design_gust_load_kN"]))
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs",
                           "energy_budget.json"), "w") as fh:
        json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
