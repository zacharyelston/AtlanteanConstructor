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
binary features, 5 herds and 4 x 3 fish choices there are about 31 million combinations; they are scored
exhaustively in parallel (multiprocessing), so the best set in each cell is exact, not a heuristic.
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
FEATURES = list(STUDIOS) + ["kitchen", "gallery"] + OTHER + list(CROPS)

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


def evaluate(chosen, animal, market, synergies=True, aqua="none+none"):
    """Yearly value of a set of features. Returns a dict with the parts and the synergy credits."""
    m = MARKETS[market]
    has = set(chosen)
    rev, cost, capex, hours, notes = {}, {}, 0.0, 0.0, {}
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
        hours += st["hours"]
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
        hours += herd * a["hours"]
        visitors += a["visitors"]
    if "guard_llamas" in has:
        capex += 3000
        cost["guard llamas"] = 2 * (0.4 * HAY_USD_T + 80)
        hours += 16
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
        hours += t["n"] * t["hours"]
    if "heat_recovery" in has:
        capex += 25000
        hours += 50
        heat = 1.0 if "glass" in has else (0.3 if "ceramics" in has else 0.0)
        val = heat * ((2 * 2700 if "tunnels" in has else 0) + 4000)
        rev["heat recovery: frost-free tunnels and warm fish bay"] = val if synergies else 0.0
        if synergies:
            syn["furnace/kiln waste heat"] = val
    if "biochar" in has:
        capex += 8000
        hours += 80
        rev["biochar bags"] = 2000
        if synergies and "willow" in has:
            rev["biochar bags"] += 1000
            syn["willow feeds the biochar kiln"] = 1000
    if "flock" in has:
        capex += 6000
        hours += 180
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
        hours += 60
    if "festival" in has:
        ok = "gallery" in has or len(studios) >= 2
        if ok:
            rev["festival booths and tickets"] = (2 * 50 * 150 + 2 * 1500 * 5) * m["visitors"] * (1 + 0.1 * len(studios) if synergies else 1)
            if synergies:
                syn["festival grows with each studio"] = (2 * 50 * 150 + 2 * 1500 * 5) * m["visitors"] * 0.1 * len(studios)
            cost["festival marketing"] = 6000
            hours += 200
            visitors += 3000
    for c_ in CROPS:
        if c_ not in has:
            continue
        cr = CROPS[c_]
        r = cr["revenue"] * (m["visitors"] if c_ == "berries" else m["price"])
        rev[cr["label"]] = r
        cost[cr["label"]] = cr["costs"]
        capex += cr["capex"]
        hours += cr["hours"]
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
        hours += q["hours"]
        visitors += q["visitors"]
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
        hours += 400 + covers * 0.1
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
        farm_goods = visitors * 0.25 * 20 * 0.4
        rev["gallery commission (40 %)"] = art * 0.4
        rev["shop margin on farm goods"] = farm_goods
        if synergies and studios:
            syn["gallery sells what the studios make"] = art * 0.4
        elif not synergies:
            rev["gallery commission (40 %)"] = 0.0
        capex += 60000
        hours += 1000
    buildings = len(has & BUILDING)
    income = sum(rev.values())
    costs = sum(cost.values())
    net = income - costs - hours * WAGE
    return {"features": sorted(has), "animal": animal, "aqua": aqua, "market": market, "buildings": buildings, "capex": capex,
            "hours": hours, "visitors": visitors, "income": income, "costs": costs, "labour": hours * WAGE,
            "net": net, "score": net - capex * CRF, "synergies": syn, "revenue": rev, "cost_lines": cost}


DEEP, INNER = ["none", "perch", "catfish", "trout"], ["none", "prawns", "tilapia"]
ANIMAL_KEYS = list(ANIMALS)
AQUA_KEYS = ["%s+%s" % (d, i) for d in DEEP for i in INNER]
NB = len(FEATURES)
TOTAL = (1 << NB) * len(ANIMAL_KEYS) * len(AQUA_KEYS)
CELLS = [(blim, budget, hcap) for blim in (2, 3, 4, 6) for budget in (300000, 600000, 1200000) for hcap in (6000, 12000)]
REF = (4, 600000, 12000)


def decode(idx):
    bits, rest = idx % (1 << NB), idx >> NB
    animal, aqua = ANIMAL_KEYS[rest % len(ANIMAL_KEYS)], AQUA_KEYS[rest // len(ANIMAL_KEYS)]
    chosen = [f for k, f in enumerate(FEATURES) if bits >> k & 1]
    return chosen, animal, aqua


def valid(chosen, animal):
    if "heat_recovery" in chosen and not ({"glass", "ceramics"} & set(chosen)):
        return False
    if "residency" in chosen and not (set(STUDIOS) & set(chosen)):
        return False
    if "guard_llamas" in chosen and animal not in ("sheep", "goats"):
        return False
    return True


def work(args):
    """Score a slice of the index space for both markets; keep the best per cell and the top 50 of REF."""
    lo, hi = args
    best = {(mk,) + c: (-1e18, -1) for mk in MARKETS for c in CELLS}
    top = {mk: [] for mk in MARKETS}
    n = 0
    for idx in range(lo, hi):
        chosen, animal, aqua = decode(idx)
        if not valid(chosen, animal):
            continue
        n += 1
        for mk in MARKETS:
            r = evaluate(chosen, animal, mk, aqua=aqua)
            sc, b, cap, h = r["score"], r["buildings"], r["capex"], r["hours"]
            for c in CELLS:
                if b <= c[0] and cap <= c[1] and h <= c[2] and sc > best[(mk,) + c][0]:
                    best[(mk,) + c] = (sc, idx)
            if b <= REF[0] and cap <= REF[1] and h <= REF[2]:
                t = top[mk]
                if len(t) < 50:
                    t.append((sc, idx))
                    t.sort()
                elif sc > t[0][0]:
                    t[0] = (sc, idx)
                    t.sort()
    return best, top, n


def main():
    import multiprocessing as mp
    chunks = 128
    step = TOTAL // chunks + 1
    with mp.Pool() as pool:
        parts = pool.map(work, [(i * step, min((i + 1) * step, TOTAL)) for i in range(chunks)])
    best, top, n = {}, {mk: [] for mk in MARKETS}, 0
    for b, t, k in parts:
        n += k
        for key, v in b.items():
            if v > best.get(key, (-1e18, -1)):
                best[key] = v
        for mk in MARKETS:
            top[mk].extend(t[mk])
    for mk in MARKETS:
        top[mk] = sorted(top[mk], reverse=True)[:50]
    print("combinations scored: %s per market (of %s)" % ("{:,}".format(n), "{:,}".format(TOTAL)))
    grid = []
    for mk in MARKETS:
        for c in CELLS:
            sc, idx = best[(mk,) + c]
            chosen, animal, aqua = decode(idx)
            r = evaluate(chosen, animal, mk, aqua=aqua)
            r0 = evaluate(chosen, animal, mk, synergies=False, aqua=aqua)
            grid.append({"market": mk, "buildings_max": c[0], "budget": c[1], "hours_max": c[2],
                         "best": r, "score_without_synergies": r0["score"]})
            if c[2] == 12000:
                print("%-8s bld<=%d budget $%9s: $%8s (synergies $%7s) capex $%8s %5.0f h | %s + %s + %s"
                      % (mk, c[0], "{:,}".format(c[1]), "{:,.0f}".format(r["score"]),
                         "{:,.0f}".format(r["score"] - r0["score"]), "{:,.0f}".format(r["capex"]), r["hours"],
                         ", ".join(r["features"]), animal, aqua))
    freq, afreq, qfreq = {}, {}, {}
    sets = [decode(i) for _, i in top["affluent"]]
    for f in FEATURES:
        freq[f] = sum(f in ch for ch, _, _ in sets) / len(sets)
    for a_ in ANIMALS:
        afreq[a_] = sum(a_ == an for _, an, _ in sets) / len(sets)
    for q in AQUA_KEYS:
        qfreq[q] = sum(q == aq for _, _, aq in sets) / len(sets)
    print("\nIn the top 50 (affluent, 4 buildings, $600k, 12,000 h):")
    for f, v in sorted(freq.items(), key=lambda kv: -kv[1]):
        print("  %-14s %3.0f %%" % (f, 100 * v))
    print("  herds:", {k: "%.0f %%" % (100 * v) for k, v in afreq.items()})
    print("  fish:", {k: "%.0f %%" % (100 * v) for k, v in qfreq.items()})
    ref = [g for g in grid if g["market"] == "affluent" and (g["buildings_max"], g["budget"], g["hours_max"]) == REF][0]["best"]
    print("\nAnimals added to the best set (affluent):")
    mat = {}
    for animal in ANIMALS:
        base = [f for f in ref["features"] if f != "guard_llamas" or animal in ("sheep", "goats")]
        r = evaluate(base, animal, "affluent", aqua=ref["aqua"])
        mat["herd:" + animal] = r["score"] - ref["score"]
        print("  %-8s %+9.0f" % (animal, r["score"] - ref["score"]))
    print("Fish in the best set, against none (affluent):")
    noaqua = evaluate(ref["features"], ref["animal"], "affluent", aqua="none+none")["score"]
    for q in AQUA_KEYS:
        r = evaluate(ref["features"], ref["animal"], "affluent", aqua=q)
        alone = evaluate([], "none", "affluent", aqua=q)["score"] - evaluate([], "none", "affluent")["score"]
        mat["fish:" + q] = {"in_best_set": r["score"] - noaqua, "alone": alone}
        print("  %-16s in the best set %+8.0f   alone %+8.0f" % (q, r["score"] - noaqua, alone))
    print("Crops: added to or removed from the best set (affluent):")
    for c_ in CROPS:
        ch = [f for f in ref["features"] if f != c_] if c_ in ref["features"] else ref["features"] + [c_]
        r = evaluate(ch, ref["animal"], "affluent", aqua=ref["aqua"])
        alone = evaluate([c_], "none", "affluent")["score"] - evaluate([], "none", "affluent")["score"]
        d = (ref["score"] - r["score"]) if c_ in ref["features"] else (r["score"] - ref["score"])
        mat["crop:" + c_] = {"in_best_set": d, "alone": alone}
        print("  %-11s worth %+8.0f in the best set   alone %+8.0f" % (c_, d, alone))
    print("\nBest GAC-like set, synergies:")
    for k, v in sorted(ref["synergies"].items(), key=lambda kv: -kv[1]):
        print("  %-55s $%8s" % (k, "{:,.0f}".format(v)))
    with open(os.path.join(ROOT, "docs", "synergy_sweep.json"), "w") as fh:
        json.dump({"features": FEATURES, "animals": ANIMALS, "aqua": AQUA, "crops": CROPS, "markets": MARKETS,
                   "combinations_per_market": n, "grid": grid, "top50_frequency": freq, "top50_herds": afreq,
                   "top50_fish": qfreq, "matrix": mat}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
