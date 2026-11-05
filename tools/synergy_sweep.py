"""Which features belong together on an Atlantean site? An exhaustive sweep with synergies.

    python3 tools/synergy_sweep.py

The homestead core (rings, fish, orchard berm, pasture berm) is always there. On top of it the site
can add FEATURES: art studios (a glass hot shop, ceramics, a forge, metals and jewelry, fiber), a
teaching kitchen and cafe, a gallery and shop, high tunnels, heat recovery, a biochar kiln, a laying
flock, festivals, artist residencies, guard llamas and five crops (pick-your-own berries, cut flowers,
log-grown mushrooms, a dye garden, willow coppice on the ring banks), plus ONE grazing species on the
pasture (none, sheep, goats, llamas or alpacas), and fish in two places: the deep ring (none, yellow
perch, catfish, or trout for fee fishing from autumn to spring) and the shallow inner ring (none,
freshwater prawns in summer, or tilapia in a 100 m2 greenhouse bay).

Each feature has its own capex, running costs, labour hours and income. SYNERGIES are pairwise or
conditional: the hot-arts cluster shares gas, ventilation and a technician; the glass furnace's waste
heat keeps tunnels frost-free; the fiber studio turns the herd's fleece into yarn; the kitchen buys
the tunnels' produce and the flock eats its scraps; guard llamas cut lamb losses; potters make the
cafe's bowls and a bowls-and-soup benefit dinner; the gallery sells what every studio makes.

The search is a quadratic knapsack: pick the set that maximises yearly net value (income less costs,
paid labour and a capital charge) within a building limit, a capex budget and a labour cap. With 14
binary features (now 23), 5 herds and 4 x 3 fish choices there are about 500 million combinations,
too many to score one by one, so each cell is solved by iterated local search. The search is checked
against the exhaustive optimum of the earlier 19-feature run, which it must reproduce.

Labour is costed on a CALENDAR: each feature spreads its hours over the months, a year-round resident
crew is paid every month, and seasonal help at a premium covers the peaks. Features whose busy months
fall in each other's quiet ones (camps in summer studios, maple in March, trout in winter) cost less
labour together than apart: a seasonal synergy.
Writes docs/synergy_sweep.json. Every figure is a screening ASSUMPTION; class prices follow the
Guilford Art Center's fall 2026 catalog.
"""
import itertools
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WAGE = 22.0                  # $/h for all labour, so features compare on equal terms
CRF = 0.07 / (1 - 1.07 ** -20)   # capital charge: 7 % over 20 years
MARKETS = {"affluent": {"fill": 1.0, "price": 1.0, "visitors": 1.0},     # a Guilford-like shoreline town
           "rural": {"fill": 0.7, "price": 0.8, "visitors": 0.6}}
BASE_VISITORS = 2000

# Studios: (sections, seats, price, fill) per class type; instructor share of tuition; consumables share;
# energy $/yr; capex; staff/tech hours; is it a "hot" art?  Prices from the GAC fall 2026 catalog.
STUDIOS = {
    "ceramics": {"label": "Ceramics studio (wheels, kilns, glaze lab)", "classes": [(24, 10, 450, 0.85), (12, 10, 55, 0.9)],
                 "consumables": 0.08, "energy": 8000, "capex": 90000, "hours": 400, "hot": True},
    "glass": {"label": "Glass hot shop (furnace, glory hole, annealers)", "classes": [(24, 4, 400, 0.85), (120, 4, 95, 0.8)],
              "consumables": 0.12, "energy": 36000, "capex": 200000, "hours": 600, "hot": True},
    "forge": {"label": "Forge (blacksmithing, semi-enclosed shed)", "classes": [(30, 6, 330, 0.85), (9, 6, 300, 0.85), (20, 8, 75, 0.9)],
              "consumables": 0.08, "energy": 6000, "capex": 60000, "hours": 300, "hot": True},
    "metals": {"label": "Metals and jewelry studio", "classes": [(12, 8, 420, 0.8), (10, 8, 150, 0.8)],
               "consumables": 0.10, "energy": 1500, "capex": 40000, "hours": 250, "hot": True},
    "fiber": {"label": "Fiber studio (looms, wheels, dye kitchen)", "classes": [(8, 8, 350, 0.75), (30, 10, 60, 0.8)],
              "consumables": 0.10, "energy": 500, "capex": 35000, "hours": 250, "hot": False},
}
INSTRUCTOR_SHARE = 0.45
BUILDING = set(STUDIOS) | {"kitchen", "gallery"}
OTHER = ["tunnels", "heat_recovery", "biochar", "flock", "festival", "residency", "guard_llamas"]
CROPS = {   # small plots on the border and berm edges; income at direct prices
    "berries": {"label": "Pick-your-own berries, 0.5 acre", "capex": 15000, "hours": 300, "revenue": 12000, "costs": 2500, "visitors": 2000},
    "flowers": {"label": "Cut flowers, 0.25 acre", "capex": 6000, "hours": 600, "revenue": 16000, "costs": 4800, "visitors": 300},
    "mushrooms": {"label": "Log-grown shiitake, 300 logs", "capex": 3000, "hours": 120, "revenue": 4500, "costs": 1000, "visitors": 0},
    "dye_garden": {"label": "Dye garden (indigo, madder, marigold), 0.1 acre", "capex": 2000, "hours": 120, "revenue": 1500, "costs": 300, "visitors": 100},
    "willow": {"label": "Willow coppice on the ring banks, 0.25 acre", "capex": 3000, "hours": 100, "revenue": 2000, "costs": 200, "visitors": 0},
}
DEEP_HA, INNER_HA = 0.449, 0.110     # ring water areas from docs/homestead_numbers.json (recommended layout)
AQUA = {   # one fish crop in the rings; the tunnels' drip lines get its nutrients
    "none": {},
    "perch": {"label": "Yellow perch in the deep ring, fed", "kg": 800 * DEEP_HA, "usd_kg": 11, "fcr": 1.5, "feed_usd_kg": 1.2,
              "seed": 500, "capex": 6000, "hours": 150, "visitors": 200, "activity": 0},
    "trout": {"label": "Trout fee fishing in the deep ring, autumn to spring", "kg": 1500, "usd_kg": 13, "fcr": 0, "feed_usd_kg": 0,
              "seed": 1500 * 9, "capex": 4000, "hours": 300, "visitors": 1500, "activity": 1500 * 10},
    "catfish": {"label": "Channel catfish in the deep ring, fed", "kg": 1500 * DEEP_HA, "usd_kg": 8, "fcr": 1.8, "feed_usd_kg": 1.0,
                "seed": 700, "capex": 6000, "hours": 150, "visitors": 200, "activity": 0},
    "tilapia": {"label": "Tilapia in a 100 m2 greenhouse bay, intensive", "kg": 1200, "usd_kg": 9, "fcr": 1.6, "feed_usd_kg": 1.2,
                "seed": 300, "capex": 38000, "hours": 300, "visitors": 300, "activity": 0, "heat_usd": 2300},
    "prawns": {"label": "Freshwater prawns in the inner ring, June to September", "kg": 600 * INNER_HA, "usd_kg": 33, "fcr": 0,
               "feed_usd_kg": 0, "seed": 4 * 1103 * 0.12 + 300, "capex": 2000, "hours": 100, "visitors": 1500,
               "activity": 1500 * 5},                       # a harvest day
}
NEW = ["youth", "membership", "maple", "bees"]
FEATURES = list(STUDIOS) + ["kitchen", "gallery"] + OTHER + list(CROPS) + NEW
CREW_H_MONTH, SEASONAL_WAGE = 160.0, 28.0      # a resident crew member's month; seasonal help costs more


def _norm(v):
    t = float(sum(v))
    return [x / t for x in v]


# Share of each feature's yearly hours by month, January to December (ASSUMED from the crop and class calendars).
PROFILES = {k: _norm(v) for k, v in {
    "flat": [1] * 12,
    "studio": [9, 9, 9, 9, 9, 5, 4, 4, 9, 11, 11, 11],          # fall and winter-spring semesters, a short summer
    "kitchen": [6, 6, 7, 8, 9, 10, 10, 10, 9, 10, 8, 7],         # follows visitors
    "gallery": [7, 6, 6, 7, 8, 8, 8, 8, 8, 9, 12, 13],           # holiday season
    "tunnels": [4, 3, 5, 7, 10, 11, 13, 14, 12, 9, 6, 6],        # tomatoes peak July to September
    "biochar": [20, 20, 15, 5, 0, 0, 0, 0, 0, 5, 15, 20],        # prunings in the dormant season
    "festival": [0, 0, 0, 0, 5, 5, 5, 10, 15, 35, 5, 20],        # an October harvest fair and a December market
    "herd": [8, 8, 10, 12, 9, 8, 8, 8, 8, 7, 7, 7],              # spring lambing or kidding
    "berries": [0, 0, 0, 5, 15, 35, 30, 10, 5, 0, 0, 0],
    "flowers": [0, 0, 5, 10, 15, 15, 15, 15, 13, 10, 2, 0],
    "mushrooms": [0, 0, 15, 25, 15, 5, 5, 5, 10, 15, 5, 0],
    "dye_garden": [0, 0, 0, 10, 20, 20, 20, 20, 10, 0, 0, 0],
    "willow": [30, 30, 15, 5, 0, 0, 0, 0, 0, 0, 10, 10],         # cut in winter
    "trout": [14, 12, 12, 12, 10, 0, 0, 0, 0, 12, 14, 14],       # cold season only
    "prawns": [0, 0, 0, 0, 10, 25, 20, 20, 25, 0, 0, 0],         # stock in June, harvest in September
    "perch": [2, 2, 4, 10, 14, 14, 14, 14, 12, 10, 2, 2],
    "catfish": [2, 2, 4, 10, 14, 14, 14, 14, 12, 10, 2, 2],
    "tilapia": [1] * 12,
    "youth": [4, 4, 4, 4, 4, 20, 25, 25, 3, 3, 4, 0],            # summer camp
    "maple": [10, 40, 40, 0, 0, 0, 0, 0, 0, 0, 10, 0],           # tap in winter, boil in February and March
    "bees": [0, 0, 5, 15, 20, 20, 15, 15, 10, 0, 0, 0],
}.items()}

ANIMALS = {   # per head on 3 acres of pasture (berm crown and border)
    "none": {"per_acre": 0},
    "sheep": {"per_acre": 4, "young": 1.4, "young_usd": 220, "fleece_lb": 7, "raw_usd_lb": 1.5, "hay_t": 0.5,
              "vet": 40, "shear": 8, "hours": 8, "fence_capex_acre": 1200, "visitors": 500, "orchard": 1500,
              "activity_usd": 0},
    "goats": {"per_acre": 6, "young": 1.6, "young_usd": 220, "fleece_lb": 0, "raw_usd_lb": 0, "hay_t": 0.5,
              "vet": 60, "shear": 0, "hours": 12, "fence_capex_acre": 2500, "visitors": 1500, "orchard": -3000,
              "activity_usd": 9000},                       # goat yoga and kid-season visits
    "llamas": {"per_acre": 2.5, "young": 0, "young_usd": 0, "fleece_lb": 4, "raw_usd_lb": 5, "hay_t": 0.4,
               "vet": 80, "shear": 40, "hours": 8, "fence_capex_acre": 1200, "visitors": 2500, "orchard": 0,
               "activity_usd": 5400},                      # llama walks
    "alpacas": {"per_acre": 5, "young": 0, "young_usd": 0, "fleece_lb": 6, "raw_usd_lb": 5, "hay_t": 0.25,
                "vet": 80, "shear": 35, "hours": 8, "fence_capex_acre": 1200, "visitors": 2500, "orchard": 0,
                "activity_usd": 3000},
}
PASTURE_ACRES, HAY_USD_T, ANIMAL_CAPEX_HEAD = 3.0, 250, 300
PREDATION = {"unguarded": 0.08, "guarded": 0.03}            # share of lambs or kids lost
YARN_NET_USD_LB = 30.0                                      # mini-mill yarn sold in the shop, less mill fees

TUNNEL = {"n": 4, "revenue": 20900, "costs": 4600, "capex": 8640 * 4 - 6500, "hours": 605}


def evaluate(chosen, animal, market, synergies=True, aqua="none+none", calendar=True):
    """Yearly value of a set of features. Returns a dict with the parts and the synergy credits.

    calendar=True costs labour month by month: a year-round resident crew sized to the work, plus
    seasonal help at a premium in the months the crew can't cover. calendar=False is the old flat
    $22 for every hour, kept to check the search against the exhaustive run."""
    m = MARKETS[market]
    has = set(chosen)
    rev, cost, capex, hours, notes = {}, {}, 0.0, 0.0, {}
    hl = []
    syn = {}
    studios = [s for s in STUDIOS if s in has]
    hot = [s for s in studios if STUDIOS[s]["hot"]]
    cluster = synergies and len(hot) >= 2
    resid = synergies and "residency" in has and studios
    seat_visits = 0.0
    for s in studios:
        st = STUDIOS[s]
        tuition = sum(n * seats * price * m["price"] * min(fill * m["fill"], 1.0) for n, seats, price, fill in st["classes"])
        seat_visits += sum(n * seats * min(fill * m["fill"], 1.0) * (10 if price >= 250 else 1)
                           for n, seats, price, fill in st["classes"])
        share = INSTRUCTOR_SHARE
        if resid:
            share = 0.75 * INSTRUCTOR_SHARE + 0.25 * 0.30          # residents teach a quarter of the classes for less
            syn["residents teach (%s)" % s] = tuition * (INSTRUCTOR_SHARE - share)
        energy = st["energy"]
        if synergies and s == "forge" and "biochar" in has:
            syn["biochar charcoal fuels the forge"] = energy * 0.5
            energy *= 0.5
        if synergies and s == "fiber" and animal in ("sheep", "llamas", "alpacas"):
            tuition *= 1.15
            syn["farm-to-yarn classes fill better"] = tuition * 0.15 / 1.15
        if synergies and s == "fiber" and "dye_garden" in has:
            syn["natural-dye classes from the dye garden"] = tuition * 0.10
            tuition *= 1.10
        if synergies and s == "fiber" and "willow" in has:
            syn["willow basketry workshops"] = 6 * 10 * 100 * m["price"] * min(0.8 * m["fill"], 1) * (1 - INSTRUCTOR_SHARE)
            tuition += 6 * 10 * 100 * m["price"] * min(0.8 * m["fill"], 1)
        rev["%s tuition" % s] = tuition
        cost["%s instructors" % s] = tuition * share
        cost["%s consumables" % s] = tuition * st["consumables"]
        cost["%s energy" % s] = energy * (0.9 if cluster else 1.0)
        c = st["capex"] * (0.85 if cluster else 1.0)
        if cluster:
            syn["hot-arts cluster shares gas, venting, a tech (%s)" % s] = (st["capex"] * 0.15 * CRF + energy * 0.1)
        capex += c
        hl.append(("studio", st["hours"]))
    visitors = BASE_VISITORS + seat_visits
    # animals
    a = ANIMALS[animal]
    herd = PASTURE_ACRES * a["per_acre"]
    if herd:
        loss = PREDATION["guarded" if (synergies and "guard_llamas" in has and animal in ("sheep", "goats")) else "unguarded"]
        young = herd * a["young"] * (1 - loss) * a["young_usd"]
        if synergies and "guard_llamas" in has and animal in ("sheep", "goats"):
            syn["guard llamas cut lamb/kid losses"] = herd * a["young"] * (PREDATION["unguarded"] - loss) * a["young_usd"]
        fleece_lb = herd * a["fleece_lb"]
        if synergies and "fiber" in has and fleece_lb:
            fleece = fleece_lb * YARN_NET_USD_LB * (1.1 if "dye_garden" in has else 1.0)
            syn["the herd's fleece becomes yarn"] = fleece_lb * (YARN_NET_USD_LB - a["raw_usd_lb"])
        else:
            fleece = fleece_lb * a["raw_usd_lb"]
        rev["%s: young stock" % animal] = young
        rev["%s: fleece" % animal] = fleece
        rev["%s: visits (walks, yoga)" % animal] = a["activity_usd"] * m["visitors"]
        rev["%s: orchard grazing" % animal] = a["orchard"]
        if synergies and a["orchard"]:
            syn["%s in the orchard" % animal] = a["orchard"]
        elif not synergies:
            rev["%s: orchard grazing" % animal] = 0.0
        cost["%s: hay, vet, shearing" % animal] = herd * (a["hay_t"] * HAY_USD_T + a["vet"] + a["shear"])
        capex += PASTURE_ACRES * a["fence_capex_acre"] + herd * ANIMAL_CAPEX_HEAD
        hl.append(("herd", herd * a["hours"]))
        visitors += a["visitors"]
    if "guard_llamas" in has:
        capex += 3000
        cost["guard llamas"] = 2 * (0.4 * HAY_USD_T + 80)
        hl.append(("herd", 16))
        visitors += 300
    # tunnels, flock, biochar, heat recovery
    if "tunnels" in has:
        t = TUNNEL
        r = t["n"] * t["revenue"]
        if synergies and "biochar" in has:
            syn["biochar in the tunnel beds"] = r * 0.05
            r *= 1.05
        rev["tunnels"] = r
        c = t["n"] * t["costs"]
        if aqua == "none+none":
            c += t["n"] * 1728 * 0.25                       # no fish: the drip lines need the full fertiliser
        elif synergies:
            syn["fish feed the tunnels' drip lines"] = t["n"] * 1728 * 0.25
        else:
            c += t["n"] * 1728 * 0.25
        if synergies and "kitchen" in has:
            syn["kitchen buys produce (no market costs)"] = r * 0.25 * 0.15
            c -= r * 0.25 * 0.15
        cost["tunnels"] = c
        capex += t["capex"]
        hl.append(("tunnels", t["n"] * t["hours"]))
    if "heat_recovery" in has:
        capex += 25000
        hl.append(("flat", 50))
        heat = 1.0 if "glass" in has else (0.3 if "ceramics" in has else 0.0)
        val = heat * ((2 * 2700 if "tunnels" in has else 0) + 4000)
        rev["heat recovery: frost-free tunnels and warm fish bay"] = val if synergies else 0.0
        if synergies:
            syn["furnace/kiln waste heat"] = val
    if "biochar" in has:
        capex += 8000
        hl.append(("biochar", 80))
        rev["biochar bags"] = 2000
        if synergies and "willow" in has:
            rev["biochar bags"] += 1000
            syn["willow feeds the biochar kiln"] = 1000
    if "flock" in has:
        capex += 6000
        hl.append(("flat", 180))
        rev["eggs"] = 667 * 7.0
        feed = 2500
        if synergies and "kitchen" in has:
            syn["kitchen scraps feed the flock; eggs to the cafe"] = 1000 + 667 * 7.0 * 0.15
            feed -= 1000
            rev["eggs"] *= 1.15
        cost["flock feed"] = feed
        visitors += 300
    if "residency" in has:
        cost["residency rent discount (4 cabins)"] = 4 * 650 * 12
        hl.append(("flat", 60))
    if "festival" in has:
        ok = "gallery" in has or len(studios) >= 2
        if ok:
            rev["festival booths and tickets"] = (2 * 50 * 150 + 2 * 1500 * 5) * m["visitors"] * (1 + 0.1 * len(studios) if synergies else 1)
            if synergies:
                syn["festival grows with each studio"] = (2 * 50 * 150 + 2 * 1500 * 5) * m["visitors"] * 0.1 * len(studios)
            cost["festival marketing"] = 6000
            hl.append(("festival", 200))
            visitors += 3000
    for c_ in CROPS:
        if c_ not in has:
            continue
        cr = CROPS[c_]
        r = cr["revenue"] * (m["visitors"] if c_ == "berries" else m["price"])
        rev[cr["label"]] = r
        cost[cr["label"]] = cr["costs"]
        capex += cr["capex"]
        hl.append((c_, cr["hours"]))
        visitors += cr["visitors"]
        if synergies and c_ == "flowers" and "gallery" in has:
            syn["flowers sold in the shop (no market costs)"] = r * 0.15
            rev[cr["label"]] += r * 0.15
        if synergies and c_ == "flowers" and "festival" in has:
            syn["festival bouquets"] = 2000
            rev[cr["label"]] += 2000
        if synergies and c_ == "mushrooms" and "kitchen" in has:
            syn["mushrooms go to the cafe at retail"] = r * 0.15
            rev[cr["label"]] += r * 0.15
        if synergies and c_ == "mushrooms" and "willow" in has:
            syn["willow and orchard poles become mushroom logs"] = 1000
            cost[cr["label"]] -= 1000
        if c_ == "willow":
            rev["willow: ring banks need less upkeep"] = 1000
        if synergies and c_ == "berries" and "kitchen" in has:
            syn["berries for cafe pies and jam"] = 2500
            rev[cr["label"]] += 2500
        if synergies and c_ == "berries" and "festival" in has:
            syn["a berry festival weekend"] = 3000
            rev[cr["label"]] += 3000
    for part in aqua.split("+"):
        if part == "none":
            continue
        q = AQUA[part]
        r = q["kg"] * q["usd_kg"] * m["price"] + q["activity"] * m["visitors"]
        if synergies and "kitchen" in has:
            syn["ring-to-table %s in the cafe" % part] = q["kg"] * q["usd_kg"] * m["price"] * 0.2
            r += q["kg"] * q["usd_kg"] * m["price"] * 0.2
        if synergies and "festival" in has and part in ("prawns", "trout"):
            syn["%s day at the festival" % part] = 3000 if part == "prawns" else 2000
            r += 3000 if part == "prawns" else 2000
        rev[q["label"]] = r
        heat = q.get("heat_usd", 0)
        if heat and synergies and "heat_recovery" in has and ({"glass", "ceramics"} & has):
            syn["waste heat keeps the tilapia bay warm"] = heat
            heat = 0
        cost[q["label"]] = q["kg"] * q["fcr"] * q["feed_usd_kg"] + q["seed"] + heat + (0.15 * r if part != "trout" else 0)
        capex += q["capex"]
        hl.append((part, q["hours"]))
        visitors += q["visitors"]
    if "youth" in has and studios:
        camp = 8 * 20 * 450 * 0.85 + 30 * 8 * 250 * 0.85
        camp *= m["price"] * min(m["fill"], 1.0)
        if synergies and animal in ("llamas", "goats", "alpacas"):
            syn["farm camp: kids come for the animals"] = camp * 0.10
            camp *= 1.10
        share = INSTRUCTOR_SHARE
        if synergies and "membership" in has:
            share -= 0.05
            syn["studio members help teach the camps"] = camp * 0.05
        rev["youth classes and summer camp"] = camp
        cost["youth instructors and materials"] = camp * (share + 0.08)
        capex += 10000
        hl.append(("youth", 300))
        visitors += 3000
    if "membership" in has and studios:
        members = min(12 * len(studios), 30)
        fees = members * 150 * 12 * m["price"] * min(m["fill"], 1.0)
        rev["studio memberships"] = fees
        cost["member firings, energy, consumables"] = fees * 0.10 + 0.2 * sum(STUDIOS[s_]["energy"] for s_ in studios)
        capex += 5000
        hl.append(("flat", 200))
    if "maple" in has:
        syrup = 300 * 0.25 * 70 * m["price"]
        if synergies and "gallery" in has:
            syn["syrup sold in the shop at retail"] = syrup * 0.15
            syrup *= 1.15
        rev["maple syrup, 300 taps"] = syrup
        cost["maple: tubing, filters, wood"] = 800
        capex += 12000
        hl.append(("maple", 250))
        visitors += 1500
        if synergies and "kitchen" in has:
            pancakes = 2 * 400 * 15 * m["visitors"]
            rev["maple weekend pancake breakfasts"] = pancakes
            cost["pancake breakfasts"] = pancakes * 0.35
            syn["maple weekend pancake breakfasts in the cafe"] = pancakes * 0.65
            hl.append(("maple", 60))
        if synergies and "festival" in has:
            syn["maple weekend joins the festival calendar"] = 3000
            rev["maple weekend booths"] = 3000
    if "bees" in has:
        honey = 10 * 40 * 12 * m["price"]
        if synergies and "kitchen" in has:
            syn["honey in the cafe at retail"] = honey * 0.15
            honey *= 1.15
        rev["honey, 10 hives"] = honey
        rev["orchard pollination"] = 1500
        cost["bees: equipment, treatments"] = 800
        capex += 6000
        hl.append(("bees", 150))
        if synergies and "berries" in has:
            syn["bees pollinate the berries"] = CROPS["berries"]["revenue"] * 0.10
            rev["berry pollination"] = CROPS["berries"]["revenue"] * 0.10
        if synergies and studios:
            wax = 10 * 10 * 45 * m["price"] * (1 - INSTRUCTOR_SHARE)
            syn["beeswax candle and encaustic workshops"] = wax
            rev["beeswax workshops (net)"] = wax
            hl.append(("studio", 40))
    if synergies and aqua == "trout+prawns":
        syn["one dock and one crowd for two fish seasons"] = 3000
        capex -= 2000
        rev["shared dock, signage and season passes"] = 1000
    visitors *= m["visitors"]
    # kitchen and gallery depend on visitors and on what else is here
    if "kitchen" in has:
        classes = 60 * 12 * 95 * m["price"] * min(0.85 * m["fill"], 1)
        covers = visitors * 0.35
        cafe = covers * 14.0
        rev["cooking classes"] = classes
        rev["cafe"] = cafe
        cost["kitchen food"] = (classes + cafe) * 0.32
        cost["kitchen instructors"] = classes * INSTRUCTOR_SHARE
        cost["kitchen energy"] = 6000
        capex += 150000
        hl.append(("kitchen", 400 + covers * 0.1))
        if synergies and "ceramics" in has:
            bowls = 2 * 150 * 45 * m["price"]
            rev["bowls-and-soup benefit dinners"] = bowls
            cost["bowls-and-soup costs"] = bowls * 0.4
            syn["potters make the cafe's bowls and a benefit dinner"] = bowls * 0.6 + 3000
            cost["kitchen food"] -= 3000
    if "gallery" in has:
        art = 25000 * math.sqrt(len(studios)) * m["price"] if studios else 0.0
        if resid:
            art += 10000
            syn["residents stock the gallery"] = 10000 * 0.4
        if synergies and "membership" in has and studios:
            art += 15000
            syn["studio members stock the gallery"] = 15000 * 0.4
        farm_goods = visitors * 0.25 * 20 * 0.4
        rev["gallery commission (40 %)"] = art * 0.4
        rev["shop margin on farm goods"] = farm_goods
        if synergies and studios:
            syn["gallery sells what the studios make"] = art * 0.4
        elif not synergies:
            rev["gallery commission (40 %)"] = 0.0
        capex += 60000
        hl.append(("gallery", 1000))
    buildings = len(has & BUILDING)
    hm = [0.0] * 12
    kinds = {}
    for k, h in hl:
        kinds[k] = kinds.get(k, 0.0) + h
        prof = PROFILES.get(k, PROFILES["flat"])
        for i in range(12):
            hm[i] += h * prof[i]
    hours = sum(hm)
    if calendar:
        labour, crew = crew_cost(hm)
    else:
        labour, crew = hours * WAGE, None
    income = sum(rev.values())
    costs = sum(cost.values())
    net = income - costs - labour
    return {"features": sorted(has), "animal": animal, "aqua": aqua, "market": market, "buildings": buildings, "capex": capex,
            "hours": hours, "hours_by_month": hm, "hours_by_kind": kinds, "crew": crew, "visitors": visitors, "income": income, "costs": costs,
            "labour": labour, "flat_labour": hours * WAGE,
            "net": net, "score": net - capex * CRF, "synergies": syn, "revenue": rev, "cost_lines": cost}


def crew_cost(hm):
    """Cheapest mix of a year-round crew (paid every month) and seasonal help in the busy months."""
    best = None
    for n in range(0, int(max(hm) / CREW_H_MONTH) + 2):
        over = sum(max(h - n * CREW_H_MONTH, 0.0) for h in hm)
        c = n * CREW_H_MONTH * 12 * WAGE + over * SEASONAL_WAGE
        if best is None or c < best[0]:
            used = sum(min(h, n * CREW_H_MONTH) for h in hm)
            best = (c, {"crew": n, "seasonal_h": over, "crew_use": used / (n * CREW_H_MONTH * 12) if n else 1.0})
    return best


DEEP, INNER = ["none", "perch", "catfish", "trout"], ["none", "prawns", "tilapia"]
ANIMAL_KEYS = list(ANIMALS)
AQUA_KEYS = ["%s+%s" % (d, i) for d in DEEP for i in INNER]
CELLS = [(blim, budget) for blim in (2, 3, 4, 6) for budget in (300000, 600000)]
REF = (4, 600000)
EXACT_REF = 189830      # the exhaustive optimum for REF, flat labour, old features (commit c4f4795, 19.1 M sets)


def valid(chosen, animal):
    has = set(chosen)
    if "heat_recovery" in has and not ({"glass", "ceramics"} & has):
        return False
    if ({"residency", "youth", "membership"} & has) and not (set(STUDIOS) & has):
        return False
    if "guard_llamas" in has and animal not in ("sheep", "goats"):
        return False
    return True


def feasible(r, cell, hours_max=None):
    return r["buildings"] <= cell[0] and r["capex"] <= cell[1] and (hours_max is None or r["hours"] <= hours_max)


def search(market, cell, calendar=True, features=None, hours_max=None, restarts=24, kicks=30, seed=1):
    """Iterated local search: from random starts, climb by the best single change (add or drop a feature,
    change the herd, change either fish), then kick the best set with three random flips and climb again.
    Exact search is no longer possible (23 features, 5 herds, 12 fish pairs: about 500 million sets)."""
    import random
    feats = list(features or FEATURES)
    rng = random.Random(seed + hash((market, cell, calendar)) % 1000)
    cache = {}

    def score(state):
        key = (frozenset(state[0]), state[1], state[2])
        if key not in cache:
            chosen, animal, aqua = state
            if not valid(chosen, animal):
                cache[key] = (-1e18, None)
            else:
                r = evaluate(sorted(chosen), animal, market, aqua=aqua, calendar=calendar)
                cache[key] = (r["score"] if feasible(r, cell, hours_max) else -1e18, r)
        return cache[key]

    def neighbours(state):
        chosen, animal, aqua = state
        for f in feats:
            yield (chosen ^ {f}, animal, aqua)
        for a_ in ANIMAL_KEYS:
            if a_ != animal:
                yield (chosen, a_, aqua)
        d, i = aqua.split("+")
        for d2 in DEEP:
            if d2 != d:
                yield (chosen, animal, d2 + "+" + i)
        for i2 in INNER:
            if i2 != i:
                yield (chosen, animal, d + "+" + i2)

    def climb(state):
        cur = score(state)[0]
        while True:
            best_n, best_s = None, cur
            for n in neighbours(state):
                sc = score(n)[0]
                if sc > best_s + 1e-6:
                    best_n, best_s = n, sc
            if best_n is None:
                return state, cur
            state, cur = best_n, best_s

    best = (frozenset(), "none", "none+none")
    best_s = score(best)[0]
    for _ in range(restarts):
        st = (frozenset(f for f in feats if rng.random() < 0.3), rng.choice(ANIMAL_KEYS), rng.choice(AQUA_KEYS))
        if score(st)[0] < -1e17:
            st = (frozenset(), st[1], st[2])
        st, sc = climb(st)
        for _ in range(kicks):
            ch = set(st[0])
            for f in rng.sample(feats, 3):
                ch ^= {f}
            cand, csc = climb((frozenset(ch), st[1] if rng.random() < 0.7 else rng.choice(ANIMAL_KEYS), st[2]))
            if csc > sc:
                st, sc = cand, csc
        if sc > best_s:
            best, best_s = st, sc
    r = score(best)[1]
    return r, len(cache)


def run_cell(args):
    market, cell, calendar = args
    r, n = search(market, cell, calendar=calendar)
    r0 = evaluate(r["features"], r["animal"], market, synergies=False, aqua=r["aqua"], calendar=calendar)
    return {"market": market, "buildings_max": cell[0], "budget": cell[1], "calendar": calendar, "best": r,
            "score_without_synergies": r0["score"], "sets_scored": n}


def main():
    import multiprocessing as mp
    old = [f for f in FEATURES if f not in NEW]
    chk, n = search("affluent", REF, calendar=False, features=old, hours_max=12000)
    print("check: local search finds $%s against the exhaustive optimum $%s (%s sets scored)"
          % ("{:,.0f}".format(chk["score"]), "{:,}".format(EXACT_REF), "{:,}".format(n)))
    jobs = [(mk, c, cal) for mk in MARKETS for c in CELLS for cal in (True, False)]
    with mp.Pool() as pool:
        grid = pool.map(run_cell, jobs)
    for g in grid:
        b = g["best"]
        print("%-8s bld<=%d $%7s %-8s: $%8s (synergies $%7s) crew %s, %5.0f h | %s + %s + %s"
              % (g["market"], g["buildings_max"], "{:,}".format(g["budget"]), "calendar" if g["calendar"] else "flat",
                 "{:,.0f}".format(b["score"]), "{:,.0f}".format(b["score"] - g["score_without_synergies"]),
                 b["crew"]["crew"] if b["crew"] else "-", b["hours"], ", ".join(b["features"]), b["animal"], b["aqua"]))
    ref = [g for g in grid if g["market"] == "affluent" and (g["buildings_max"], g["budget"]) == REF and g["calendar"]][0]["best"]
    print("\nBest set (affluent, 4 buildings, $600k, calendar): hours by month", [round(h) for h in ref["hours_by_month"]],
          ref["crew"])
    mat = {}
    print("New features, added to or removed from the best set (calendar):")
    for f in NEW + ["tunnels", "berries", "festival"]:
        ch = [x for x in ref["features"] if x != f] if f in ref["features"] else ref["features"] + [f]
        r = evaluate(ch, ref["animal"], "affluent", aqua=ref["aqua"])
        d = (ref["score"] - r["score"]) if f in ref["features"] else (r["score"] - ref["score"])
        dflat = ((evaluate(ref["features"], ref["animal"], "affluent", aqua=ref["aqua"], calendar=False)["score"]
                  - evaluate(ch, ref["animal"], "affluent", aqua=ref["aqua"], calendar=False)["score"])
                 * (1 if f in ref["features"] else -1))
        mat[f] = {"calendar": d, "flat": dflat}
        print("  %-11s worth %+8.0f with the calendar, %+8.0f with flat labour" % (f, d, dflat))
    groups = {"Studios, camps and members": ["studio", "youth"], "Kitchen and cafe": ["kitchen"], "Gallery and shop": ["gallery"],
              "Tunnels, crops and bees": ["tunnels", "berries", "flowers", "mushrooms", "dye_garden", "willow", "bees", "biochar"],
              "Fish, animals and maple": ["trout", "prawns", "perch", "catfish", "tilapia", "herd", "maple", "flat"],
              "Festivals": ["festival"]}
    by_group = {g: [0.0] * 12 for g in groups}
    for k, h in ref["hours_by_kind"].items():
        g = next(g for g, ks in groups.items() if k in ks)
        for i in range(12):
            by_group[g][i] += h * PROFILES.get(k, PROFILES["flat"])[i]
    print("Hours by month and group (best set):")
    for g, v_ in by_group.items():
        print("  %-28s %s" % (g, [round(x) for x in v_]))
    print("\nSynergies in the best set:")
    for k, v in sorted(ref["synergies"].items(), key=lambda kv: -kv[1]):
        print("  %-55s $%8s" % (k, "{:,.0f}".format(v)))
    with open(os.path.join(ROOT, "docs", "synergy_sweep.json"), "w") as fh:
        json.dump({"features": FEATURES, "animals": ANIMALS, "aqua": AQUA, "crops": CROPS, "markets": MARKETS,
                   "profiles": PROFILES, "crew_h_month": CREW_H_MONTH, "seasonal_wage": SEASONAL_WAGE,
                   "check": {"local_search": chk["score"], "exhaustive": EXACT_REF, "sets_scored": n},
                   "grid": grid, "matrix": mat, "best_hours_by_group": by_group}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
