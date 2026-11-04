"""Where does the Atlantean homestead make sense? Sweeps the economics model's main drivers.

    python3 tools/homestead_numbers.py && python3 tools/energy_budget.py   # inputs, if stale
    python3 tools/economics_explore.py

Writes docs/economics_explore.json and three light/dark SVG charts in docs/img/:
  econ-npv-vs-fill   homeowner NPV vs the local fill price, per site
  econ-tornado       which drivers move NPV most (New England, flat)
  econ-builder       builder: sites per year needed to cover overhead, vs fill price
plus a relief sweep (how the slope changes the answer) in the JSON and on the console.

The model and every base price are in tools/homestead_economics.py; the sweep ranges and
the builder's overhead are ASSUMPTIONS below.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

import homestead_economics as he  # noqa: E402
import make_figs as mf  # noqa: E402

FILL_PRICES = [-10, -5, 0, 2.5, 5, 7.5, 10, 12.5, 15]           # $/yd3 net to the builder, buyer hauls
BUILDER = {"overhead_usd_per_yr": 150000,                        # PM/design, office, insurance, marketing
           "season_days": {"new_england": 150, "florida": 220},  # working days a crew can dig per year
           "margin": 0.25}
SITES = [("NE 6 ft slope", "New England till, 6 ft slope"), ("NE flat", "New England till, flat"),
         ("Florida", "Florida sand, flat")]
LAYOUT = "Shallow 0.9 m inner ring, 8 ft"


# ----------------------------------------------------------------------------- model wrapper
class Knobs:
    """Temporarily change the economics model's inputs; restores them on exit."""

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.saved = (copy.deepcopy(he.PRICES), copy.deepcopy(he.FARM), copy.deepcopy(he.STONE),
                      he.DISCOUNT, he.PRODUCT_MARGIN)
        k = self.kw
        if "produce_x" in k:
            for key in ("fruit_usd_per_lb", "fish_usd_per_lb"):
                he.FARM[key] *= k["produce_x"]
            for key in ("duck_eggs_usd", "goats_net_usd", "greens_usd"):
                he.FARM[key] *= k["produce_x"]
        if "elec_ne" in k:
            he.PRICES["electricity_usd_per_kwh"]["new_england"] = k["elec_ne"]
        if "pv_w" in k:
            he.PRICES["pv_usd_per_w"] = k["pv_w"]
        if "discount" in k:
            he.DISCOUNT = k["discount"]
        if "upkeep" in k:
            he.FARM["upkeep_pct_of_capex"] = k["upkeep"]
        if "stone" in k:
            he.STONE["new_england"]["usd_per_t"] = k["stone"]
        if "margin" in k:
            he.PRODUCT_MARGIN = k["margin"]
        return self

    def __exit__(self, *a):
        he.PRICES, he.FARM, he.STONE, he.DISCOUNT, he.PRODUCT_MARGIN = self.saved


def run(r, eb, fill, screen=False, fed=False, hire_x=1.0, uplift=0.0, greenhouse=None, **knobs):
    """One evaluation. ``uplift`` = fraction of the build cost that shows up as land value at once."""
    r = copy.deepcopy(r)
    r["build"]["excavator_dozer"]["cost_usd"] *= hire_x
    he.SCENARIOS["_sweep"] = {"label": "sweep", "fill_usd_per_yd3": fill, "screen": screen}
    with Knobs(**knobs):
        s = he.site_economics(r, eb, "_sweep", fed_fish=fed, greenhouse=greenhouse)
    s["npv_with_uplift"] = s["npv_25y_5pct"] + uplift * s["total_capex"]
    return s


def crossing(xs, ys):
    """First x where y crosses zero (linear interpolation), or None."""
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if (y0 <= 0 <= y1) or (y0 >= 0 >= y1):
            return x0 if y1 == y0 else x0 + (0 - y0) * (x1 - x0) / (y1 - y0)
    return None


# ----------------------------------------------------------------------------- sweeps
def sweeps(hn, eb):
    rec = {name: next(r for r in hn if r["layout"].startswith(LAYOUT) and r["soil"] == soil) for name, soil in SITES}
    out = {"fill_prices": FILL_PRICES, "sites": {}}
    for name, r in rec.items():
        rows = []
        for p in FILL_PRICES:
            raw = run(r, eb, p)
            scr = run(r, eb, p + 4.0, screen=True) if "NE" in name else None   # screened fill sells ~$4 more
            earth = lambda s: (s["capex"]["earthworks (pond crew)"] + sum(v for k, v in s["capex"].items() if "surplus" in k)  # noqa: E731
                               + s["capex"]["gravel bought"] + s["capex"]["sand bought"] - sum(s["onetime_returns"].values()))
            clim = he.climate_of(r["soil"])
            crew_days = r["build"]["excavator_dozer"]["days"]
            cap = BUILDER["season_days"][clim] / crew_days
            prof = raw["product"]["builder_profit"]
            rows.append({"fill": p, "npv": raw["npv_25y_5pct"], "npv_screened": scr["npv_25y_5pct"] if scr else None,
                         "earthworks_net": earth(raw), "net_capex": raw["net_capex"], "build_cost": raw["total_capex"],
                         "uplift_needed_pct": max(0.0, -raw["npv_25y_5pct"]) / raw["total_capex"] * 100,
                         "builder_profit_per_site": prof,
                         "sites_per_yr_to_break_even": BUILDER["overhead_usd_per_yr"] / prof if prof > 0 else None,
                         "sites_per_yr_per_crew": cap, "crew_days": crew_days})
        out["sites"][name] = {
            "rows": rows,
            "fill_price_for_npv_zero": crossing(FILL_PRICES, [x["npv"] for x in rows]),
            "fill_price_for_free_earthworks": crossing(FILL_PRICES, [x["earthworks_net"] for x in rows]),
            "fill_price_for_npv_zero_screened": (crossing(FILL_PRICES, [x["npv_screened"] for x in rows])
                                                 if "NE" in name else None),
        }
    return out, rec


def tornado(r, eb):
    base_kw = dict(fill=8.0)
    base = run(r, eb, **base_kw)["npv_with_uplift"]
    drivers = [
        ("Land value uplift (0 % / 50 % of build cost)", dict(uplift=0.0), dict(uplift=0.5)),
        ("Fill price ($0 / $15 per yd³)", dict(fill=0.0), dict(fill=15.0)),
        ("Produce prices (×0.6 farm-gate / ×2 direct sale)", dict(produce_x=0.6), dict(produce_x=2.0)),
        ("Discount rate (8 % / 3 %)", dict(discount=0.08), dict(discount=0.03)),
        ("Earthworks hire rates (×1.25 / ×0.8)", dict(hire_x=1.25), dict(hire_x=0.8)),
        ("Electricity price ($0.20 / $0.40 per kWh)", dict(elec_ne=0.20), dict(elec_ne=0.40)),
        ("Upkeep (2 % / 0.5 % of build cost a year)", dict(upkeep=2.0), dict(upkeep=0.5)),
        ("Fish (unfed / fed catfish)", dict(fed=False), dict(fed=True)),
        ("Solar installed cost ($3.5 / $2.2 per W)", dict(pv_w=3.5), dict(pv_w=2.2)),
    ]
    rows = []
    for label, lo, hi in drivers:
        a = run(r, eb, **{**base_kw, **lo})["npv_with_uplift"]
        b = run(r, eb, **{**base_kw, **hi})["npv_with_uplift"]
        rows.append({"driver": label, "low": a, "high": b, "span": abs(b - a)})
    rows.sort(key=lambda x: -x["span"])
    return {"base_npv": base, "base": "NE till, flat, 8 ft ring, fill sold at $8/yd³, no uplift", "rows": rows}


def conditions_grid(rec, eb):
    """Homeowner NPV for combinations of the three big levers, per site."""
    out = []
    for fill in (0.0, 8.0, 15.0):
        for produce_x, channel in ((1.0, "farm-gate"), (2.0, "direct sale")):
            for uplift in (0.0, 0.25):
                row = {"fill": fill, "produce": channel, "uplift_pct": uplift * 100}
                for name, r in rec.items():
                    row[name] = run(r, eb, fill, produce_x=produce_x, uplift=uplift)["npv_with_uplift"]
                out.append(row)
    return out


def greenhouse_grid(rec, eb):
    """Homeowner NPV with 0-8 high tunnels on the pasture berm (typical yield, hired labour, sold direct)."""
    out = []
    for n in (0, 2, 4, 8):
        for fill in (0.0, 8.0):
            row = {"tunnels": n, "fill": fill}
            for name, r in rec.items():
                g = {"tunnels": n, "heated": 0, "yields": "typical", "channel": "direct", "hired_labour": True}
                s = run(r, eb, fill, greenhouse=g)
                row[name] = s["npv_25y_5pct"]
                row[name + " payback"] = s["payback_years"]
            out.append(row)
    return out


def relief_sweep(eb):
    import homestead_numbers as hnm
    out = []
    for ft in (0, 2, 4, 6, 7, 8, 10):
        key = "relief_%d" % ft
        site = '{"type": "flat"}' if ft == 0 else (
            '{"type": "slope", "relief_ft": %d, "uphill_azimuth_deg": 30.0, "undulation": 0.25, "seed": 7}' % ft)
        hnm.SOILS[key] = {"label": "NE till, %d ft" % ft, "rain_m": 1.2, "evap_m": 0.65,
                          "overrides": ['soil.preset="ne_glacial_till"', "site=%s" % site]}
        try:
            r = hnm.numbers("outer_deep", key, res=320)
        except ValueError as exc:                   # the layout's gaps are too narrow for this slope
            out.append({"relief_ft": ft, "fits": False, "why": str(exc)})
            continue
        r["soil"] = "New England till, %d ft" % ft
        row = {"relief_ft": ft, "fits": True, "cut_m3": r["cut_bank_m3"], "surplus_m3": r["spoil"]["surplus_m3"]}
        for p in (0.0, 8.0):
            s = run(r, eb, p)
            row["npv_fill_%g" % p] = s["npv_25y_5pct"]
            row["builder_profit_fill_%g" % p] = s["product"]["builder_profit"]
        out.append(row)
    return out


# ----------------------------------------------------------------------------- charts
W, H = 760, 420
PAD = dict(l=78, r=150, t=56, b=58)


def axes(s, x0, x1, y0, y1, xt, yt, xlab, ylab, yfmt):
    t = s.t
    px = lambda x: PAD["l"] + (x - x0) / (x1 - x0) * (W - PAD["l"] - PAD["r"])  # noqa: E731
    py = lambda y: H - PAD["b"] - (y - y0) / (y1 - y0) * (H - PAD["t"] - PAD["b"])  # noqa: E731
    for y in yt:
        s.line(PAD["l"], py(y), W - PAD["r"], py(y), t["grid"], 1)
        s.text(PAD["l"] - 8, py(y) + 4, yfmt(y), 11, t["ink2"], "end")
    for x in xt:
        s.text(px(x), H - PAD["b"] + 18, "%g" % x if x >= 0 else "−%g" % -x, 11, t["ink2"], "middle")
    s.line(PAD["l"], H - PAD["b"], W - PAD["r"], H - PAD["b"], t["base"], 1)
    s.text((PAD["l"] + W - PAD["r"]) / 2, H - 14, xlab, 12, t["ink2"], "middle")
    s.add('<text x="18" y="%.1f" font-size="12" fill="%s" text-anchor="middle" transform="rotate(-90 18 %.1f)">%s</text>'
          % ((PAD["t"] + H - PAD["b"]) / 2, t["ink2"], (PAD["t"] + H - PAD["b"]) / 2, ylab))
    return px, py


def stack(ys, gap=16):
    """Spread label y positions so none are closer than ``gap`` px, keeping their order."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for a, b in zip(order, order[1:]):
        if out[b] - out[a] < gap:
            out[b] = out[a] + gap
    return out


def legend(s, names, x, y):
    t = s.t
    for i, n in enumerate(names):
        s.line(x, y - 4, x + 18, y - 4, t["series"][i], 2)
        s.add('<circle cx="%.1f" cy="%.1f" r="4" fill="%s" stroke="%s" stroke-width="2"/>'
              % (x + 9, y - 4, t["series"][i], t["surface"]))
        s.text(x + 24, y, n, 11, t["ink"])
        x += 34 + 7 * len(n)


def money(v):
    a = abs(v)
    s = "$%.0fk" % (a / 1000) if a >= 1000 else "$%.0f" % a
    return ("−" + s) if v < 0 else s


def chart_npv(data, theme):
    s = mf.Svg(W, H, theme)
    t = s.t
    ys = [r["npv"] for site in data["sites"].values() for r in site["rows"]]
    y0, y1 = min(ys) * 1.1, max(max(ys) * 1.15, 50000)
    yt = [v for v in range(-300000, 300001, 100000) if y0 <= v <= y1]
    px, py = axes(s, -10, 15, y0, y1, FILL_PRICES[::2], yt, "Net price the surplus spoil sells for ($ per yd³; negative = paying to dispose)",
                  "Homeowner NPV, 25 years at 5 %", money)
    s.line(PAD["l"], py(0), W - PAD["r"], py(0), t["ink2"], 1.2)
    s.text(PAD["l"] + 4, py(0) - 6, "break-even", 11, t["ink2"])
    ends = []
    for i, (name, site) in enumerate(data["sites"].items()):
        col = t["series"][i]
        pts = [(px(r["fill"]), py(r["npv"])) for r in site["rows"]]
        s.poly(pts, stroke=col, width=2)
        for x, y in pts:
            s.add('<circle cx="%.1f" cy="%.1f" r="4" fill="%s" stroke="%s" stroke-width="2"/>' % (x, y, col, t["surface"]))
        ends.append((name, pts[-1]))
        z = site["fill_price_for_npv_zero"]
        if z is not None:
            s.add('<circle cx="%.1f" cy="%.1f" r="6" fill="none" stroke="%s" stroke-width="2"/>' % (px(z), py(0), t["ink"]))
    for (name, (lx, _)), ly in zip(ends, stack([e[1][1] for e in ends])):
        s.text(lx + 10, ly + 4, name, 12, t["ink"], weight=600)
    legend(s, [e[0] for e in ends], PAD["l"], H - PAD["b"] - 10)
    s.text(PAD["l"], 24, "When does the homestead pay for itself?", 15, t["ink"], weight=600)
    s.text(PAD["l"], 42, "8 ft outer ring, unfed fish, no land-value uplift; circles mark where each site breaks even", 11, t["ink2"])
    mf.write("econ-npv-vs-fill", theme, s.render(
        "Homeowner NPV vs fill price",
        "Net present value over 25 years at 5 percent for three sites, as the price received for surplus fill varies "
        "from minus 10 to plus 15 dollars per cubic yard. See the table in docs/where-it-pays.md."))


def chart_tornado(tor, theme):
    rows = tor["rows"]
    h = 70 + 34 * len(rows) + 50
    s = mf.Svg(W, h, theme)
    t = s.t
    lab_w = 320
    vals = [v for r in rows for v in (r["low"], r["high"])] + [tor["base_npv"]]
    v0, v1 = min(vals) * 1.08, max(vals) * 1.08
    x0, x1 = lab_w + 70, W - 50
    px = lambda v: x0 + (v - v0) / (v1 - v0) * (x1 - x0)  # noqa: E731
    top = 70
    for v in range(-400000, 400001, 50000):
        if v0 <= v <= v1:
            s.line(px(v), top - 8, px(v), top + 34 * len(rows), t["grid"], 1)
            s.text(px(v), top + 34 * len(rows) + 18, money(v), 11, t["ink2"], "middle")
    col = t["series"][0]
    for i, r in enumerate(rows):
        y = top + 34 * i
        s.text(lab_w + 8, y + 15, r["driver"], 12, t["ink"], "end")
        a, b = sorted((r["low"], r["high"]))
        s.add('<rect x="%.1f" y="%.1f" width="%.1f" height="20" rx="4" fill="%s"/>' % (px(a), y + 2, max(px(b) - px(a), 2), col))
        s.text(px(a) - 5, y + 16, money(r["low"] if r["low"] < r["high"] else r["high"]), 11, t["ink2"], "end")
        s.text(px(b) + 5, y + 16, money(r["high"] if r["high"] > r["low"] else r["low"]), 11, t["ink2"])
    s.line(px(tor["base_npv"]), top - 12, px(tor["base_npv"]), top + 34 * len(rows), t["ink"], 1.5)
    s.line(px(0), top - 12, px(0), top + 34 * len(rows), t["ink2"], 1, dash="4,3")
    s.text(px(tor["base_npv"]), top - 16, "base %s" % money(tor["base_npv"]), 11, t["ink"], "middle", 600)
    s.text(30, 24, "What moves the homeowner's NPV most", 15, t["ink"], weight=600)
    s.text(30, 42, "New England till, flat site, 8 ft ring, fill sold at $8/yd³ (base). Each bar: one driver at its low and high value; dashed = break-even", 11, t["ink2"])
    mf.write("econ-tornado", theme, s.render(
        "Sensitivity of homeowner NPV", "Tornado chart of NPV for nine drivers, low and high values. Table in docs/where-it-pays.md."))


def chart_builder(data, theme):
    s = mf.Svg(W, H, theme)
    t = s.t
    px, py = axes(s, -10, 15, 0, 12, FILL_PRICES[::2], [0, 2, 4, 6, 8, 10, 12],
                  "Net price the surplus spoil sells for ($ per yd³)", "Sites a year to cover $150k overhead", lambda v: "%g" % v)
    ends = []
    for i, (name, site) in enumerate(data["sites"].items()):
        col = t["series"][i]
        pts = [(px(r["fill"]), py(min(r["sites_per_yr_to_break_even"], 12)))
               for r in site["rows"] if r["sites_per_yr_to_break_even"] is not None]
        s.poly(pts, stroke=col, width=2)
        for x, y in pts:
            s.add('<circle cx="%.1f" cy="%.1f" r="4" fill="%s" stroke="%s" stroke-width="2"/>' % (x, y, col, t["surface"]))
        cap = site["rows"][0]["sites_per_yr_per_crew"]
        s.line(PAD["l"], py(cap), W - PAD["r"], py(cap), col, 1.2, dash="5,4")
        s.text(W - PAD["r"] + 10, py(cap) + 4, "%s: 1 crew = %.1f/yr" % (name, cap), 11, t["ink2"])
        ends.append((name, pts[-1]))
    for (name, (lx, _)), ly in zip(ends, stack([e[1][1] for e in ends], 15)):
        s.text(lx + 10, ly + 4, name, 12, t["ink"], weight=600)
    legend(s, [e[0] for e in ends], PAD["l"] + 260, PAD["t"] + 16)
    s.text(PAD["l"], 24, "When does building these as a business work?", 15, t["ink"], weight=600)
    s.text(PAD["l"], 42, "Solid: sites a year needed at cost + 25 % (no point = a site loses money). Dashed: one hired crew's season", 11, t["ink2"])
    mf.write("econ-builder", theme, s.render(
        "Builder break-even volume", "Sites per year needed to cover 150 thousand dollars of overhead, against fill price, for three "
        "sites, with one crew's seasonal capacity as dashed lines. Table in docs/where-it-pays.md."))


def main():
    hn = he.load("homestead_numbers.json")
    eb = he.load("energy_budget.json")
    data, rec = sweeps(hn, eb)
    tor = tornado(rec["NE flat"], eb)
    rel = relief_sweep(eb)
    grid = conditions_grid(rec, eb)
    ggrid = greenhouse_grid(rec, eb)
    res = {"fill_sweep": data, "tornado": tor, "relief_sweep": rel, "conditions_grid": grid,
           "greenhouse_grid": ggrid, "builder": BUILDER}
    with open(os.path.join(ROOT, "docs", "economics_explore.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    for th in mf.THEMES:
        chart_npv(data, th)
        chart_tornado(tor, th)
        chart_builder(data, th)
    # console summary
    print("Fill price sweep (8 ft ring): NPV | earthworks net | builder profit/site | sites/yr to break even | crew cap")
    for name, site in data["sites"].items():
        print(" %s: NPV=0 at fill $%s/yd3 (screened: %s); earthworks free at $%s/yd3" % (
            name, "%.1f" % site["fill_price_for_npv_zero"] if site["fill_price_for_npv_zero"] is not None else "-",
            "%.1f" % site["fill_price_for_npv_zero_screened"] if site["fill_price_for_npv_zero_screened"] is not None else "-",
            "%.1f" % site["fill_price_for_free_earthworks"] if site["fill_price_for_free_earthworks"] is not None else "-"))
        for r in site["rows"]:
            print("   fill %5.1f  NPV %9s  earth %9s  uplift needed %5.1f%%  builder %9s  sites/yr %5s  crew cap %.1f"
                  % (r["fill"], money(r["npv"]), money(r["earthworks_net"]), r["uplift_needed_pct"],
                     money(r["builder_profit_per_site"]),
                     "%.1f" % r["sites_per_yr_to_break_even"] if r["sites_per_yr_to_break_even"] else "-",
                     r["sites_per_yr_per_crew"]))
    print("\nTornado (base NPV %s):" % money(tor["base_npv"]))
    for r in tor["rows"]:
        print("  %-52s %9s .. %9s" % (r["driver"], money(r["low"]), money(r["high"])))
    print("\nConditions grid (homeowner NPV incl. uplift):")
    for g in grid:
        print("  fill $%4.1f  %-11s uplift %2.0f%%  " % (g["fill"], g["produce"], g["uplift_pct"])
              + "  ".join("%s %9s" % (n, money(g[n])) for n, _ in SITES))
    print("\nGreenhouse grid (typical yield, hired labour, direct):")
    for g in ggrid:
        print("  %d tunnels, fill $%4.1f  " % (g["tunnels"], g["fill"]) + "  ".join(
            "%s %9s (%s)" % (n, money(g[n]), "%.0f y" % g[n + " payback"] if g[n + " payback"] else "-") for n, _ in SITES))
    print("\nRelief sweep (NE till, 8 ft ring):")
    for r in rel:
        if not r["fits"]:
            print("  %2d ft: layout doesn't fit (%s)" % (r["relief_ft"], r["why"][:80]))
            continue
        print("  %2d ft: cut %6.0f m3, surplus %6.0f m3 | NPV fill $0 %9s, fill $8 %9s | builder fill $0 %9s, $8 %9s"
              % (r["relief_ft"], r["cut_m3"], r["surplus_m3"], money(r["npv_fill_0"]), money(r["npv_fill_8"]),
                 money(r["builder_profit_fill_0"]), money(r["builder_profit_fill_8"])))


if __name__ == "__main__":
    main()
