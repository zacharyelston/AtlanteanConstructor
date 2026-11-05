"""Simple structures for the homestead, each capped at $50,000: retail baseline vs engineered.

    python3 tools/structures_budget.py

The idea: take plumbing out of the private units. Kitchen and baths live in two shared
central buildings; the private units are identical dry cabins from standard panel sizes,
designed and permitted once, built twelve times. Each structure is costed line by line at
RETAIL (contractor-built, general contractor margin) and ENGINEERED (members' labour, kits,
bulk buying, licensed trades only where Connecticut requires them). The gap per line is
where to look for savings. Writes docs/structures_budget.json.

Every number is a screening ASSUMPTION built from published ranges (sources in the plan):
ADUs $150-300/ft2 retail; Quonset kits $11-15/ft2, finished $40-125/ft2; post-frame kits
$10-30/ft2; SIP panels $7-12 per ft2 of panel, $12-50 installed; MEP $35-75k per 1,000 ft2.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAP = 50000
GC_MARGIN = 0.20          # general contractor overhead and profit on retail builds

STRUCTURES = {
    "cabin": {
        "label": "Private cabin, 16 x 20 ft, SIP panels, no plumbing", "count": 12, "ft2": 320,
        "lines": [  # item, retail, engineered, how the saving is made
            ("Foundation", 5000, 2500, "helical piers or sonotubes, members dig and set"),
            ("SIP shell (956 ft2 of panel)", 23900, 9560, "panels bought direct at about $10/ft2 and set by members; one cut list for all 12"),
            ("Windows and doors", 5500, 3000, "standard sizes, bought 12 at a time"),
            ("Metal roof and trim", 3500, 2000, "stock panel lengths, members install"),
            ("Electrical", 4500, 3500, "licensed electrician connects; members pull wire under supervision"),
            ("Heat and cooling (mini-split)", 4500, 2500, "bulk order of 12 ductless units"),
            ("Interior finish", 7000, 2500, "finished plywood walls, sealed floor, no drywall"),
            ("Permits, design, delivery", 3000, 800, "one design approved once, built 12 times"),
        ],
    },
    "hall": {
        "label": "Common hall (kitchen and dining), 30 x 32 ft steel arch", "count": 1, "ft2": 960,
        "lines": [
            ("Insulated slab", 11500, 7500, "contractor pours, members place forms, foam and PEX"),
            ("Steel arch kit", 14500, 13000, "direct from the maker"),
            ("Erection", 6500, 1200, "members erect with a rented lift"),
            ("Spray-foam insulation (1,500 ft2 of arch)", 4600, 4200, "contractor; no cheaper safe option"),
            ("End walls, windows, doors", 8000, 4500, "framed by members; salvaged and stock glazing"),
            ("Electrical", 7500, 4500, "licensed electrician, members assist"),
            ("Radiant floor on the ground-source loop", 7000, 2500, "PEX in the slab; heat pump costed with the energy system"),
            ("Kitchen: cabinets, range, sinks, fridge", 20000, 6500, "restaurant-surplus equipment"),
            ("Kitchen plumbing", 6000, 2500, "hall and bath house built back to back on one shared wet wall"),
            ("Finishes", 7000, 2000, "sealed concrete floor, plywood"),
            ("Permits and engineering", 3500, 1500, "stamped arch drawings come with the kit"),
        ],
    },
    "bath": {
        "label": "Bath and laundry house, 20 x 24 ft, 3 showers, 3 WCs, laundry", "count": 1, "ft2": 480,
        "lines": [
            ("Slab", 6000, 4000, "poured with the hall"),
            ("SIP shell (1,312 ft2 of panel)", 32800, 13120, "same panels and crew as the cabins"),
            ("Windows and doors", 3500, 1500, "stock sizes"),
            ("Roof", 3000, 1800, "stock metal panels"),
            ("Plumbing, 9 fixtures", 27000, 12000, "licensed plumber; one wet wall, PEX manifold, prefab shower pans"),
            ("Wet-area finishes", 12000, 3500, "FRP wall panels instead of tile"),
            ("Electrical", 5000, 3000, "licensed electrician, members assist"),
            ("Ventilation (ERV) and heat", 5000, 2500, "one energy-recovery ventilator"),
            ("Heat-pump water heater", 3500, 2500, "one 80 gal unit"),
            ("Washers and dryers", 4000, 3000, "two pairs, heat-pump dryers"),
            ("Permits", 3000, 1000, "shared review with the cabins"),
        ],
    },
    "shop": {
        "label": "Workshop and barn, 30 x 40 ft steel arch, unheated", "count": 1, "ft2": 1200,
        "lines": [
            ("Floor", 14000, 3500, "compacted gravel instead of a slab; slab later if needed"),
            ("Steel arch kit", 18000, 16000, "direct from the maker"),
            ("Erection", 8000, 1500, "members erect with a rented lift"),
            ("End walls, roll-up door", 8000, 4500, "members frame; stock door"),
            ("Electrical", 6000, 3000, "licensed electrician, members assist"),
            ("Permits", 2000, 1000, "agricultural building"),
        ],
    },
}


# The conventional retail baseline: every resident gets a self-contained studio (cabin + its own
# bathroom and kitchenette), contractor-built, plus the same workshop. No shared hall or bath house.
STUDIO_WET_LINES = [("Bathroom: rough-in and fixtures", 12000), ("Kitchenette", 8000),
                    ("Water heater", 1500), ("Wet-area finishes", 4000)]


def cost(s, mode):
    i = 1 if mode == "retail" else 2
    base = sum(line[i] for line in s["lines"])
    return base * (1 + GC_MARGIN) if mode == "retail" else base


def summary():
    out = {"cap_usd": CAP, "structures": {}, "totals": {}}
    for mode in ("retail", "engineered"):
        out["totals"][mode] = 0.0
    for key, s in STRUCTURES.items():
        r, e = cost(s, "retail"), cost(s, "engineered")
        out["structures"][key] = {
            "label": s["label"], "count": s["count"], "ft2": s["ft2"],
            "retail_each": r, "engineered_each": e,
            "retail_usd_ft2": r / s["ft2"], "engineered_usd_ft2": e / s["ft2"],
            "under_cap": e <= CAP, "saving_each": r - e,
            "lines": [{"item": a, "retail": b, "engineered": c, "how": d, "saving": b - c} for a, b, c, d in s["lines"]],
        }
        out["totals"]["retail"] += r * s["count"]
        out["totals"]["engineered"] += e * s["count"]
    out["totals"]["ft2"] = sum(s["ft2"] * s["count"] for s in STRUCTURES.values())
    cab = STRUCTURES["cabin"]
    studio = cost(cab, "retail") + sum(v for _, v in STUDIO_WET_LINES) * (1 + GC_MARGIN)
    out["conventional"] = {"label": "12 self-contained studios with bath and kitchenette, retail, plus the workshop",
                           "studio_each": studio, "studio_usd_ft2": studio / cab["ft2"],
                           "total": studio * cab["count"] + cost(STRUCTURES["shop"], "retail")}
    # where the savings are, by kind of work, across the whole set
    kinds = {"labour (members build)": ("Erection", "SIP shell", "Foundation", "Interior finish", "Finishes",
                                       "End walls", "Metal roof", "Roof", "Floor", "Insulated slab", "Slab"),
             "plumbing and wet areas": ("Plumbing", "Kitchen plumbing", "Wet-area finishes"),
             "equipment and kits": ("Kitchen:", "Washers", "Heat-pump water", "Steel arch kit", "Heat and cooling",
                                    "Radiant", "Ventilation", "Windows"),
             "licensed trades (electrical, spray foam)": ("Electrical", "Spray-foam"),
             "design and permits": ("Permits",)}
    by_kind = {k: 0.0 for k in kinds}
    gc = 0.0
    for s in STRUCTURES.values():
        for a, b, c, _ in s["lines"]:
            for k, keys in kinds.items():
                if a.startswith(keys):
                    by_kind[k] += (b - c) * s["count"]
                    break
        gc += sum(line[1] for line in s["lines"]) * GC_MARGIN * s["count"]
    by_kind["no general contractor margin"] = gc
    out["savings_by_kind"] = by_kind
    return out


def main():
    s = summary()
    for k, v in s["structures"].items():
        print("%-62s x%-2d  retail $%7s ($%3.0f/ft2)  engineered $%7s ($%3.0f/ft2)  %s"
              % (v["label"], v["count"], "{:,.0f}".format(v["retail_each"]), v["retail_usd_ft2"],
                 "{:,.0f}".format(v["engineered_each"]), v["engineered_usd_ft2"],
                 "under $50k" if v["under_cap"] else "OVER CAP"))
    t = s["totals"]
    print("All structures: %s ft2; retail $%s; engineered $%s (saving $%s)"
          % ("{:,}".format(t["ft2"]), "{:,.0f}".format(t["retail"]), "{:,.0f}".format(t["engineered"]),
             "{:,.0f}".format(t["retail"] - t["engineered"])))
    c = s["conventional"]
    print("Conventional baseline: studios $%s each ($%.0f/ft2) -> $%s with the workshop"
          % ("{:,.0f}".format(c["studio_each"]), c["studio_usd_ft2"], "{:,.0f}".format(c["total"])))
    for k, v in sorted(s["savings_by_kind"].items(), key=lambda kv: -kv[1]):
        print("  saving from %-32s $%s" % (k, "{:,.0f}".format(v)))
    with open(os.path.join(ROOT, "docs", "structures_budget.json"), "w") as fh:
        json.dump(s, fh, indent=1)


if __name__ == "__main__":
    main()
