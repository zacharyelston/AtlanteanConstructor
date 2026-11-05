"""Scenario: the central island becomes an event dome; dwellings move outside the rings.

    python3 tools/structures_budget.py && python3 tools/event_venue.py

Builds on tools/resident_economy.py (14 cabins, 17 tunnels, resident crew). Changes:
- the steel-arch common hall on the island is replaced by one large dome. It is the residents' dining
  hall on ordinary nights and a rentable venue for weddings, parties and other events;
- the cabins, laundry house and workshop move to the outer border beyond the pasture berm, each cabin
  pair beside its tunnels, so the island is the public commons and the homes stay private;
- optionally, guest cabins on the border for wedding parties and farm stays.

Writes docs/event_venue.json. Every figure is a screening ASSUMPTION; venue prices are from Connecticut
farm-venue listings and The Knot's 2025 Real Weddings Study.
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
import homestead_economics as he  # noqa: E402
import resident_economy as re_  # noqa: E402
import structures_budget as sb  # noqa: E402

ISLAND_RADIUS_M = 18.0
GC_MARGIN = sb.GC_MARGIN

# Two venue sizes. Under 100 guests, an assembly hall under 5,000 ft2 needs no sprinkler system
# (IBC 903.2.1.2; check the Connecticut State Building Code), which is the biggest single line.
VENUES = {
    "intimate": {"label": "Intimate venue: 44 ft dome, up to 99 guests, no sprinklers", "diameter_ft": 44,
                 "guests": 99, "sprinklers": False, "parking": 35, "wc": 4, "fee_factor": 0.6},
    "full": {"label": "Full venue: 60 ft dome, up to 150 guests, sprinklered", "diameter_ft": 60,
             "guests": 150, "sprinklers": True, "parking": 50, "wc": 6, "fee_factor": 1.0},
}

# Line items: (item, retail, engineered, how). Per-ft2 items are multiplied by the dome's floor area.
DOME_FT2 = [
    ("Slab and ring foundation", 12.0, 8.0, "members place forms, insulation and PEX; contractor pours"),
    ("Dome shell (concrete or panel)", 60.0, 40.0, "shell crew hired direct; members do the interior foam and finish"),
    ("Interior finish and acoustic panels", 10.0, 4.0, "members install; sealed concrete floor"),
    ("Heat pump on the ground loop, ventilation for a crowd", 14.0, 9.0, "radiant floor plus an ERV sized for the guest count"),
    ("Electrical, lighting, sound", 12.0, 8.0, "licensed electrician, members assist"),
]
DOME_FIXED = [
    ("Glazing and wide doors to the terrace", 30000, 20000, "stock storefront sizes"),
    ("Catering prep kitchen (the residents' kitchen too)", 40000, 15000, "restaurant-surplus equipment; caterers bring the rest"),
    ("Fire alarm and egress lighting", 12000, 9000, "licensed installer"),
    ("Terrace, paths and ramps", 25000, 10000, "members build; gravel and pavers"),
    ("Causeway upgrade for a fire engine", 20000, 12000, "wider, compacted, rated culverts"),
    ("Permits, engineering and a special permit", 25000, 20000, "assembly use needs stamped drawings"),
    ("Tables and chairs", 15000, 10000, "bought used from venues that are refitting"),
]
PER_WC = (9000, 5000, "licensed plumber; one restroom block, back to back")
PER_PARKING = (800, 400, "gravel lot outside the rings, members grade it with the eOx")
SPRINKLERS = (60000, 45000, "licensed; 30,000 gal tank and pump, there is no hydrant")

# Moving the homes outside the rings: longer water, sewer and power runs around the border.
OUTSIDE = {"ring_radius_m": 85.0, "share_of_circle": 0.75, "trench_usd_per_ft": {"retail": 25.0, "engineered": 14.0}}

GUEST_CABINS = {"count": 4, "nightly_usd": 175, "occupancy": 0.45, "turnover_usd": 45, "nights_per_stay": 2.2,
                "platform_fee_pct": 15}

# A year of bookings once established (year 3 on); Connecticut farm venues ask about $5.5-18k for a
# peak-season Saturday, the state average venue spend is about $8-10k.
DEMAND = {
    "cautious": {"peak_sat": 10, "fri_sun": 6, "off_season": 4, "small": 15},
    "base": {"peak_sat": 18, "fri_sun": 10, "off_season": 6, "small": 25},
    "strong": {"peak_sat": 24, "fri_sun": 16, "off_season": 8, "small": 40},
}
FEES = {"peak_sat": 9000, "fri_sun": 5000, "off_season": 5000, "small": 1500}
EVENT_COSTS = {
    "coordinator_usd_year": 30000,           # a resident, part-time: tours, bookings, event days
    "event_staff_h": {"big": 20, "small": 6}, "staff_usd_h": 20.0,   # residents set up, park, clean
    "utilities_per_event": {"big": 150, "small": 50},
    "insurance_usd_year": 10000, "marketing_usd_year": 10000, "software_usd_year": 1000,
    "trash_per_event": {"big": 150, "small": 40},
    "card_fees_pct": 3.0, "wear_pct_of_revenue": 3.0,
    "produce_per_guest_usd": 8.0,            # caterers buy site produce for farm-to-table menus
}
RAMP = {"year 1": 0.4, "year 2": 0.7, "year 3 on": 1.0}   # bookings take about two seasons to build
LOAN_RATE, LOAN_YEARS = 0.07, 25


def area(v):
    return math.pi * (v["diameter_ft"] / 2) ** 2


def dome_capex(v):
    a = area(v)
    lines = [(i, r * a, e * a, h) for i, r, e, h in DOME_FT2] + list(DOME_FIXED)
    lines.append(("Restrooms (%d WC with sinks, accessible)" % v["wc"], PER_WC[0] * v["wc"], PER_WC[1] * v["wc"], PER_WC[2]))
    lines.append(("Parking, %d spaces" % v["parking"], PER_PARKING[0] * v["parking"], PER_PARKING[1] * v["parking"], PER_PARKING[2]))
    if v["sprinklers"]:
        lines.append(("Sprinklers, tank and pump",) + SPRINKLERS)
    retail = sum(x[1] for x in lines) * (1 + GC_MARGIN)
    eng = sum(x[2] for x in lines)
    return {"ft2": a, "lines": [{"item": i, "retail": r, "engineered": e, "how": h} for i, r, e, h in lines],
            "retail": retail, "engineered": eng, "engineered_ft2": eng / a,
            "fits_island": v["diameter_ft"] * 0.3048 / 2 < ISLAND_RADIUS_M - 4.0,
            "terrace_m": ISLAND_RADIUS_M - v["diameter_ft"] * 0.3048 / 2}


def outside_trench(mode="engineered"):
    ft = 2 * math.pi * OUTSIDE["ring_radius_m"] * OUTSIDE["share_of_circle"] / 0.3048
    return ft, ft * OUTSIDE["trench_usd_per_ft"][mode]


def events(v, demand):
    d, f, c = DEMAND[demand], FEES, EVENT_COSTS
    big = d["peak_sat"] + d["fri_sun"] + d["off_season"]
    revenue = sum(d[k] * f[k] for k in d) * v["fee_factor"]
    staff = (big * c["event_staff_h"]["big"] + d["small"] * c["event_staff_h"]["small"]) * c["staff_usd_h"]
    costs = {"coordinator (resident)": c["coordinator_usd_year"], "event-day staff (residents)": staff,
             "utilities": big * c["utilities_per_event"]["big"] + d["small"] * c["utilities_per_event"]["small"],
             "trash removal": big * c["trash_per_event"]["big"] + d["small"] * c["trash_per_event"]["small"],
             "insurance": c["insurance_usd_year"], "marketing and listings": c["marketing_usd_year"],
             "booking software": c["software_usd_year"], "card fees": revenue * c["card_fees_pct"] / 100,
             "wear and repairs": revenue * c["wear_pct_of_revenue"] / 100}
    guests = big * v["guests"] * 0.85 + d["small"] * 40
    return {"events_big": big, "events_small": d["small"], "revenue": revenue, "costs": costs,
            "net": revenue - sum(costs.values()), "guests": guests,
            "produce_sold_to_caterers": guests * c["produce_per_guest_usd"],
            "resident_pay": c["coordinator_usd_year"] + staff}


def guest_cabins(mode="engineered"):
    g = GUEST_CABINS
    cab = sb.summary()["structures"]["cabin"]
    capex = g["count"] * cab["engineered_each" if mode == "engineered" else "retail_each"]
    nights = g["count"] * 365 * g["occupancy"]
    revenue = nights * g["nightly_usd"]
    costs = {"cleaning turnovers (residents)": nights / g["nights_per_stay"] * g["turnover_usd"],
             "platform fees": revenue * g["platform_fee_pct"] / 100,
             "maintenance (1.5 %)": capex * 0.015, "supplies and utilities": nights * 12}
    return {"capex": capex, "nights": nights, "revenue": revenue, "costs": costs, "net": revenue - sum(costs.values()),
            "resident_pay": costs["cleaning turnovers (residents)"]}


def annuity(p):
    return p * LOAN_RATE / (1 - (1 + LOAN_RATE) ** -LOAN_YEARS)


def scenario(corp, venue, demand, with_guests):
    v = VENUES[venue]
    dome = dome_capex(v)
    hall = sb.summary()["structures"]["hall"]["engineered_each"]
    trench_ft, trench = outside_trench()
    ev = events(v, demand)
    gc = guest_cabins() if with_guests else None
    extra_capex = dome["engineered"] - hall + trench + (gc["capex"] if gc else 0.0)
    extra_debt = annuity(extra_capex)
    c = cs.COMMUNE
    extra_tax = (dome["engineered"] - hall + (gc["capex"] if gc else 0.0)) * c["assess_ratio"] * c["mill_rate"] / 1000
    added = ev["net"] + (gc["net"] if gc else 0.0) - extra_debt - extra_tax
    net = corp["net_to_investors"] + added
    return {"venue": venue, "demand": demand, "guest_cabins": with_guests, "dome": dome, "events": ev,
            "guests": gc, "trench_ft": trench_ft, "trench_usd": trench, "hall_replaced": hall,
            "extra_capex": extra_capex, "extra_debt_service": extra_debt, "extra_property_tax": extra_tax, "added_to_investors": added,
            "net_to_investors": net, "cash_yield_pct": 100 * net / corp["equity"],
            "total_capex": corp["total_capex"] + extra_capex, "loan": corp["loan"] + extra_capex,
            "venue_payback_years": (dome["engineered"] - hall) / ev["net"] if ev["net"] > 0 else None,
            "resident_pay": ev["resident_pay"] + (gc["resident_pay"] if gc else 0.0)}


def main():
    hn = he.load("homestead_numbers.json")
    eb = he.load("energy_budget.json")
    r = next(x for x in hn if x["layout"].startswith("Shallow 0.9 m inner ring, 8 ft")
             and x["soil"] == "New England till, flat")
    corp = re_.corporation(r, eb)
    print("Resident economy alone: build $%s, net to investors $%s (%.1f %%)"
          % ("{:,.0f}".format(corp["total_capex"]), "{:,.0f}".format(corp["net_to_investors"]), corp["cash_yield_pct"]))
    for k, v in VENUES.items():
        d = dome_capex(v)
        print("%s: %s ft2, retail $%s, engineered $%s ($%.0f/ft2); terrace %.1f m round it on the island"
              % (v["label"], "{:,.0f}".format(d["ft2"]), "{:,.0f}".format(d["retail"]), "{:,.0f}".format(d["engineered"]),
                 d["engineered_ft2"], d["terrace_m"]))
    ft, usd = outside_trench()
    print("Homes outside the rings: %s ft more utility trench, $%s" % ("{:,.0f}".format(ft), "{:,.0f}".format(usd)))
    g = guest_cabins()
    print("Guest cabins: %d, capex $%s, %d nights, revenue $%s, net $%s"
          % (GUEST_CABINS["count"], "{:,.0f}".format(g["capex"]), g["nights"], "{:,.0f}".format(g["revenue"]),
             "{:,.0f}".format(g["net"])))
    out = []
    for venue in VENUES:
        for demand in DEMAND:
            for wg in (False, True):
                s = scenario(corp, venue, demand, wg)
                out.append(s)
                print("  %-8s %-8s guests=%-5s events %2d+%2d revenue $%7s net $%7s payback %4s y | extra capex $%s "
                      "-> investors $%s (%.1f %%), residents earn $%s"
                      % (venue, demand, wg, s["events"]["events_big"], s["events"]["events_small"],
                         "{:,.0f}".format(s["events"]["revenue"]), "{:,.0f}".format(s["events"]["net"]),
                         "%.1f" % s["venue_payback_years"] if s["venue_payback_years"] else "never",
                         "{:,.0f}".format(s["extra_capex"]), "{:,.0f}".format(s["net_to_investors"]),
                         s["cash_yield_pct"], "{:,.0f}".format(s["resident_pay"])))
    with open(os.path.join(ROOT, "docs", "event_venue.json"), "w") as fh:
        json.dump({"base_corporation": {k: corp[k] for k in ("total_capex", "loan", "net_to_investors", "cash_yield_pct")},
                   "venues": VENUES, "demand": DEMAND, "fees": FEES, "event_costs": EVENT_COSTS,
                   "guest_cabins": GUEST_CABINS, "ramp": RAMP, "scenarios": out}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
