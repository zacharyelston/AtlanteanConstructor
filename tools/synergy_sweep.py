"""Which features belong together on an Atlantean site? An exhaustive sweep with synergies.

    python3 tools/synergy_sweep.py

The homestead core (rings, fish, orchard berm, pasture berm) is always there. On top of it the site
can add FEATURES: art studios (a glass hot shop, ceramics, a forge, metals and jewelry, fiber), a
teaching kitchen and cafe, a gallery and shop, high tunnels, heat recovery, a biochar kiln, a laying
flock, festivals, artist residencies and guard llamas, plus ONE grazing species on the pasture
(none, sheep, goats, llamas or alpacas).

Each feature has its own capex, running costs, labour hours and income. SYNERGIES are pairwise or
conditional: the hot-arts cluster shares gas, ventilation and a technician; the glass furnace's waste
heat keeps tunnels frost-free; the fiber studio turns the herd's fleece into yarn; the kitchen buys
the tunnels' produce and the flock eats its scraps; guard llamas cut lamb losses; potters make the
cafe's bowls and a bowls-and-soup benefit dinner; the gallery sells what every studio makes.

The search is a quadratic knapsack: pick the set that maximises yearly net value (income less costs,
paid labour and a capital charge) within a building limit, a capex budget and a labour cap. With 14
binary features and 5 animal choices there are 81,920 combinations, few enough to score every one.
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
FEATURES = list(STUDIOS) + ["kitchen", "gallery"] + OTHER

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


def evaluate(chosen, animal, market, synergies=True):
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
            fleece = fleece_lb * YARN_NET_USD_LB
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
    return {"features": sorted(has), "animal": animal, "market": market, "buildings": buildings, "capex": capex,
            "hours": hours, "visitors": visitors, "income": income, "costs": costs, "labour": hours * WAGE,
            "net": net, "score": net - capex * CRF, "synergies": syn, "revenue": rev, "cost_lines": cost}


def all_sets():
    for bits in itertools.product((0, 1), repeat=len(FEATURES)):
        chosen = [f for f, b in zip(FEATURES, bits) if b]
        if "heat_recovery" in chosen and not ({"glass", "ceramics"} & set(chosen)):
            continue
        if "residency" in chosen and not (set(STUDIOS) & set(chosen)):
            continue
        for animal in ANIMALS:
            if "guard_llamas" in chosen and animal not in ("sheep", "goats"):
                continue
            yield chosen, animal


def main():
    scored = {mk: [] for mk in MARKETS}
    for chosen, animal in all_sets():
        for mk in MARKETS:
            r = evaluate(chosen, animal, mk)
            scored[mk].append((r["score"], r["buildings"], r["capex"], r["hours"], tuple(r["features"]), animal))
    print("combinations scored:", len(scored["affluent"]), "per market")
    grid = []
    for mk in MARKETS:
        for blim in (2, 3, 4, 6):
            for budget in (300000, 600000, 1200000):
                for hcap in (6000, 12000):
                    ok = [s for s in scored[mk] if s[1] <= blim and s[2] <= budget and s[3] <= hcap]
                    best = max(ok)
                    r = evaluate(best[4], best[5], mk)
                    r0 = evaluate(best[4], best[5], mk, synergies=False)
                    grid.append({"market": mk, "buildings_max": blim, "budget": budget, "hours_max": hcap,
                                 "best": r, "score_without_synergies": r0["score"]})
    for g in grid:
        if g["hours_max"] == 12000:
            b = g["best"]
            print("%-8s bld<=%d budget $%7s: score $%8s (synergies add $%6s) capex $%7s, %5.0f h; %s + %s"
                  % (g["market"], g["buildings_max"], "{:,}".format(g["budget"]), "{:,.0f}".format(b["score"]),
                     "{:,.0f}".format(b["score"] - g["score_without_synergies"]), "{:,.0f}".format(b["capex"]), b["hours"],
                     ", ".join(b["features"]), b["animal"]))
    # how often each feature is in the top 50 for the GAC-like case
    top = sorted([s for s in scored["affluent"] if s[1] <= 4 and s[2] <= 600000 and s[3] <= 12000], reverse=True)[:50]
    freq = {f: sum(f in s[4] for s in top) / len(top) for f in FEATURES}
    afreq = {a: sum(a == s[5] for s in top) / len(top) for a in ANIMALS}
    print("\nIn the top 50 (affluent, 4 buildings, $600k, 12,000 h):")
    for f, v in sorted(freq.items(), key=lambda kv: -kv[1]):
        print("  %-14s %3.0f %%" % (f, 100 * v))
    print("  animals:", {k: "%.0f %%" % (100 * v) for k, v in afreq.items()})
    # the animal matrix
    print("\nAnimals, alone and with their partners (affluent):")
    mat = {}
    for animal in ANIMALS:
        for partners in ([], ["fiber"], ["guard_llamas"], ["fiber", "gallery"], ["kitchen", "flock"]):
            if "guard_llamas" in partners and animal not in ("sheep", "goats"):
                continue
            base = evaluate(partners, "none", "affluent")["score"] if partners else 0.0
            r = evaluate(partners, animal, "affluent")
            mat["%s+%s" % (animal, "+".join(partners) or "alone")] = r["score"] - base
            print("  %-8s %-24s adds $%8s a year" % (animal, "+".join(partners) or "alone", "{:,.0f}".format(r["score"] - base)))
    best = [g for g in grid if g["market"] == "affluent" and g["buildings_max"] == 4 and g["budget"] == 600000
            and g["hours_max"] == 12000][0]["best"]
    print("\nBest GAC-like set, synergies:")
    for k, v in sorted(best["synergies"].items(), key=lambda kv: -kv[1]):
        print("  %-55s $%8s" % (k, "{:,.0f}".format(v)))
    with open(os.path.join(ROOT, "docs", "synergy_sweep.json"), "w") as fh:
        json.dump({"features": FEATURES, "animals": ANIMALS, "markets": MARKETS, "grid": grid,
                   "top50_frequency": freq, "top50_animals": afreq, "animal_matrix": mat}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
