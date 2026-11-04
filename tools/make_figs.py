"""README figures for AtlanteanConstructor, light + dark, in EOx's SVG conventions."""
import json, math, os, re, sys
from html import escape

REPO = "/Users/zacelston/code/AtlanteanConstructor"
OUT = os.path.join(REPO, "docs", "img")
V1 = os.path.join(REPO, "runs", "2026-11-04_compare_v1")

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9",
                  base="#c3c2b7", series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a",
                 base="#383835", series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]),
}
FONT = 'system-ui, -apple-system, &quot;Segoe UI&quot;, sans-serif'


class Svg:
    def __init__(self, w, h, theme):
        self.w, self.h, self.t, self.el = w, h, THEMES[theme], []

    def add(self, s):
        self.el.append(s)

    def text(self, x, y, s, size=12, fill=None, anchor="start", weight=400):
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{fill or self.t["ink"]}" text-anchor="{anchor}">{escape(str(s))}</text>')

    def line(self, x1, y1, x2, y2, stroke, width=1.0, dash=None, cap="butt", extra=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" '
                 f'stroke-width="{width}" stroke-linecap="{cap}"{d}{extra}/>')

    def poly(self, pts, stroke="none", width=1.0, fill="none", dash=None, closed=False, fo=None, join="round"):
        tag = "polygon" if closed else "polyline"
        d = f' stroke-dasharray="{dash}"' if dash else ""
        f = f' fill-opacity="{fo}"' if fo is not None else ""
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<{tag} points="{p}" fill="{fill}"{f} stroke="{stroke}" stroke-width="{width}" '
                 f'stroke-linejoin="{join}"{d}/>')

    def badge(self, x, y, n):
        t = self.t
        self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{t["ink"]}"/>')
        self.text(x, y + 4, n, 11, t["surface"], "middle", 600)

    def render(self, title, desc):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w:.0f} {self.h:.0f}" '
                f'width="{self.w:.0f}" height="{self.h:.0f}" role="img" aria-labelledby="t d" '
                f'font-family="{FONT}">\n<title id="t">{escape(title)}</title>\n<desc id="d">{escape(desc)}</desc>\n'
                f'<rect width="100%" height="100%" rx="8" fill="{self.t["surface"]}"/>\n'
                + "\n".join(self.el) + "\n</svg>\n")


def write(name, theme, svg):
    with open(os.path.join(OUT, f"{name}-{theme}.svg"), "w") as fh:
        fh.write(svg)


def arrowhead(s, x, y, ang, col, size=7):
    a1, a2 = ang + math.radians(150), ang - math.radians(150)
    s.poly([(x, y), (x + size * math.cos(a1), y + size * math.sin(a1)),
            (x + size * math.cos(a2), y + size * math.sin(a2))], fill=col, closed=True)


# ---------------------------------------------------------------------------
# 1. Sections from the tethered sims (NE till vs Florida sand), common scale
# ---------------------------------------------------------------------------
def read_section(run):
    """Recover metres from the sim's section.svg (tether_sim.section_svg): W 1000, H 340, pad 50,
    s over +-(r_max + 4) = +-56.5 m; vertical scale from the water levels in report.json."""
    svg = open(os.path.join(V1, run, "section.svg")).read()
    rep = json.load(open(os.path.join(V1, run, "report.json")))
    lines = {}
    for m in re.finditer(r'<polyline[^>]*stroke="([^"]*)"[^>]*points="([^"]*)"', svg):
        lines[m.group(1)] = [tuple(map(float, p.split(","))) for p in m.group(2).split()]
    z0, zd, za = lines["#8a8a8a"], lines["#1f4e8c"], lines["#c2741f"]
    L = 56.5
    sx = 900 / (2 * L)
    # zmin + 0.3 is the lowest plotted point, zmax - 0.3 the highest: 240 px = (zmax - zmin)
    ys = [p[1] for p in zd + za + z0]
    sy = (min(ys) - max(ys) + 240) / 0.6       # 0.6 m of margin, rest is the data span
    sy = 240 / ((max(ys) - min(ys)) / sy + 0.6) if False else sy
    # robust: span_px = (span_m) * sy and 240 = (span_m + 0.6) * sy  ->  sy = (240 - span_px) / 0.6
    span_px = max(ys) - min(ys)
    sy = (240 - span_px) / 0.6
    ylo = max(ys)                                # pixel of zmin + 0.3
    wl = rep["design"]["water_levels_m"]
    # anchor: the lowest design point is the deepest moat bed = its water level - depth
    beds = [w - m["depth"] for w, m in zip(wl, rep["design"]["moats"])]
    zbed = min(beds)

    def conv(pts):
        return [(-L + (x - 50) / sx, zbed + (ylo - y) / sy) for x, y in pts]
    return dict(z0=conv(z0), zd=conv(zd), za=conv(za), wl=wl, rep=rep, sy=sy, sx=sx)


def section_fig(theme):
    t = THEMES[theme]
    ne, fl = read_section("ne_till__t6_25"), read_section("florida_sand__t6_25")
    W = 920
    left, right = 64, 24
    px_m = (W - left - right) / 113.0          # horizontal
    exag = 6
    pz = px_m * exag
    s = Svg(W, 0, theme)
    s.text(16, 26, "Section through the pivot: New England till on a 6 ft slope vs a flat Florida lot", 16, weight=600)
    # legend
    lx, ly = 16, 48
    items = [("existing ground", t["muted"], "3,3", 1.5), ("design", t["series"][0], "7,4", 1.5),
             ("as built (6WD trencher)", t["series"][1], None, 2.2)]
    for lab, col, dash, w in items:
        s.line(lx, ly - 4, lx + 22, ly - 4, col, w, dash)
        s.text(lx + 28, ly, lab, 11, t["ink2"])
        lx += 40 + 6.2 * len(lab)
    s.add(f'<rect x="{lx:.1f}" y="{ly - 10}" width="22" height="10" fill="{t["series"][0]}" fill-opacity="0.22"/>')
    s.text(lx + 28, ly, "water at the design waterline", 11, t["ink2"])
    s.text(W - right, ly, f"vertical exaggeration {exag}×", 11, t["muted"], "end")

    y_cursor = 70
    panels = [("New England glacial till, 6 ft slope", ne), ("Florida fine sand, flat lot", fl)]
    for title, d in panels:
        zs = [p[1] for p in d["zd"] + d["za"] + d["z0"]]
        zmin, zmax = min(zs) - 0.2, max(zs) + 0.2
        top = y_cursor + 26
        h = (zmax - zmin) * pz
        X = lambda v: left + (v + 56.5) * px_m          # noqa: E731
        Y = lambda z, top=top, zmax=zmax: top + (zmax - z) * pz   # noqa: E731
        s.text(16, y_cursor + 14, title, 13, weight=600)
        # elevation grid every 0.5 m
        g = math.ceil(zmin * 2) / 2
        while g <= zmax:
            s.line(left, Y(g), W - right, Y(g), t["grid"], 1)
            s.text(left - 6, Y(g) + 4, f"{g:+.1f} m" if g else "0 m", 10, t["muted"], "end")
            g += 0.5
        # water: under each moat's level where the as-built surface is below it
        rep = d["rep"]["design"]
        for wl, m in zip(d["wl"], rep["moats"]):
            for sign in (-1, 1):
                run = []
                for sv, zv in d["za"]:
                    r = abs(sv)
                    inside = (sv * sign > 0) and m["cut_r_min"] - 0.5 <= r <= m["cut_r_max"] + 0.5 and zv < wl
                    if inside:
                        run.append((sv, zv))
                    elif run:
                        break
                if len(run) > 2:
                    pts = [(X(a), Y(b)) for a, b in run] + [(X(run[-1][0]), Y(wl)), (X(run[0][0]), Y(wl))]
                    s.poly(pts, fill=t["series"][0], fo=0.22, closed=True)
                    s.line(X(run[0][0]), Y(wl), X(run[-1][0]), Y(wl), t["series"][0], 1)
        s.poly([(X(a), Y(b)) for a, b in d["z0"]], t["muted"], 1.5, dash="3,3")
        s.poly([(X(a), Y(b)) for a, b in d["zd"]], t["series"][0], 1.5, dash="7,4")
        s.poly([(X(a), Y(b)) for a, b in d["za"]], t["series"][1], 2.2)
        # pivot marker
        s.line(X(0), top - 4, X(0), top + h, t["base"], 1, "2,3")
        s.text(X(0), top - 8, "pivot", 10, t["muted"], "middle")
        y_cursor = top + h + 6
        if d is ne:
            s.text(left, y_cursor + 10, "low side", 11, t["ink2"])
            s.text(W - right, y_cursor + 10, "high side (uphill)", 11, t["ink2"], "end")
            dm = rep["moats"][1]
            s.text(W / 2, y_cursor + 10,
                   f"outer moat: one waterline, cut {dm['max_cut_m']:.2f} m deep on the high side", 11, t["ink2"], "middle")
            y_cursor += 22
        else:
            s.text(W / 2, y_cursor + 10, "flat ground: both banks the same depth; water table 0.9 m down", 11,
                   t["ink2"], "middle")
            y_cursor += 22
    # scale bar
    yb = y_cursor + 14
    s.line(left, yb, left + 10 * px_m, yb, t["ink2"], 2)
    s.line(left, yb - 4, left, yb + 4, t["ink2"], 1)
    s.line(left + 10 * px_m, yb - 4, left + 10 * px_m, yb + 4, t["ink2"], 1)
    s.text(left + 10 * px_m + 8, yb + 4, "10 m", 11, t["ink2"])
    s.text(W - right, yb + 4, "tether_sim.py, compare_v1 run, EOx trencher 6WD 24.8:1", 10, t["muted"], "end")
    s.h = yb + 18
    write("section-ne-fl", theme, s.render(
        "Section through the pivot, New England vs Florida",
        "Existing ground, design and as-built surface along a diameter through the pivot for the sloped "
        "New England till site and the flat Florida sand lot, drawn to the same scale."))


# ---------------------------------------------------------------------------
# 2. Tethered trencher concept: plan view + side view
# ---------------------------------------------------------------------------
def concept_fig(theme):
    t = THEMES[theme]
    W, H = 920, 560
    s = Svg(W, H, theme)
    s.text(16, 26, "Tethered EOx trencher: one leash, no steering", 16, weight=600)
    s.text(16, 46, "Plan view of the garden-scale site (2 moats, 2 berms, ~105 m across), and the trencher in the cut",
           12, t["ink2"])
    cx, cy, k = 270, 300, 4.4          # px per m
    water, earth = t["series"][0], t["series"][3]
    rings = [("moat", 10, 16), ("berm", 19.5, 27), ("moat", 30.5, 37.5), ("berm", 41.5, 52.5)]
    for kind, a, b in rings:
        col, fo = (water, 0.20) if kind == "moat" else (earth, 0.28)
        rm, w = (a + b) / 2 * k, (b - a) * k
        s.add(f'<circle cx="{cx}" cy="{cy}" r="{rm:.1f}" fill="none" stroke="{col}" stroke-opacity="{fo}" '
              f'stroke-width="{w:.1f}"/>')
    # ring labels along the right-hand radius
    names = {0: "moat", 1: "berm", 2: "moat", 3: "berm"}
    for i, (kind, a, b) in enumerate(rings):
        rm = (a + b) / 2 * k
        s.text(cx + rm, cy + 4, names[i], 10, t["ink2"], "middle")
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{10 * k:.1f}" fill="{t["grid"]}" fill-opacity="0.5"/>')

    def P(r, deg):
        a = math.radians(deg)
        return cx + r * k * math.cos(a), cy + r * k * math.sin(a)

    rv, av = 34.0, -40.0                 # vehicle in the outer moat, angle in screen degrees (clockwise)
    vx, vy = P(rv, av)
    # leash
    s.line(cx, cy, vx, vy, t["ink"], 1.6)
    # pivot + winch
    s.add(f'<circle cx="{cx}" cy="{cy}" r="9" fill="{t["surface"]}" stroke="{t["ink"]}" stroke-width="2"/>')
    s.add(f'<circle cx="{cx}" cy="{cy}" r="3" fill="{t["ink"]}"/>')
    # travel: vehicle drives counter-clockwise on screen (decreasing angle); pan trails at larger angle
    def rect_at(r, deg, ln, wd, fill, stroke):
        x, y = P(r, deg)
        rot = deg + 90
        s.add(f'<rect x="{x - ln / 2:.1f}" y="{y - wd / 2:.1f}" width="{ln:.1f}" height="{wd:.1f}" rx="2" '
              f'fill="{fill}" stroke="{stroke}" stroke-width="1.2" transform="rotate({rot:.1f} {x:.1f} {y:.1f})"/>')
    pan_deg = av + 4.2
    px_, py_ = P(rv, pan_deg)
    s.line(vx, vy, px_, py_, t["ink2"], 1.2)
    rect_at(rv, pan_deg, 9, 8, t["base"], t["ink2"])                 # pan
    rect_at(rv, av, 11, 8, t["series"][2], t["ink"])                 # trencher
    # travel arrow along the ring, ahead of the vehicle
    arc = [P(rv, av - 6 - i) for i in range(0, 26)]
    s.poly(arc, t["series"][2], 2)
    x2, y2 = arc[-1]
    x1, y1 = arc[-2]
    arrowhead(s, x2, y2, math.atan2(y2 - y1, x2 - x1), t["series"][2], 8)
    # spiral ramp out to the outer berm, leaving in the direction of travel (decreasing angle)
    def spiral(r0, r1, a0, a1, n=48):
        return [P(r0 + (r1 - r0) * i / n, a0 + (a1 - a0) * i / n) for i in range(n + 1)]
    sp = spiral(37.0, 46.5, -70.0, -155.0)
    s.poly(sp, t["series"][1], 2, dash="6,4")
    (xa, ya), (xb, yb) = sp[-2], sp[-1]
    arrowhead(s, xb, yb, math.atan2(yb - ya, xb - xa), t["series"][1], 8)
    # spreading zone on the berm
    sz = [P(47, d) for d in range(-160, -209, -3)]
    s.poly(sz, t["series"][1], 9)
    s.el[-1] = s.el[-1].replace('stroke-width="9"', 'stroke-width="9" stroke-opacity="0.45" stroke-linecap="round"')
    # return spiral (faint), back down to the cut
    rs = spiral(47.0, 37.5, 145.0, 55.0)
    s.poly(rs, t["muted"], 1.4, dash="2,4")
    (xa, ya), (xb, yb) = rs[-2], rs[-1]
    arrowhead(s, xb, yb, math.atan2(yb - ya, xb - xa), t["muted"], 7)
    s.text(*P(50.5, 100), "return", 10, t["muted"], "middle")

    # badges
    s.badge(cx - 16, cy - 16, "1")
    bx, by = P(rv + 4.5, av - 9)
    s.badge(bx, by, "2")
    bx, by = P(46, -112)
    s.badge(bx, by - 14, "3")
    bx, by = P(47, 180)
    s.badge(bx - 22, by, "4")

    # right column: steps
    tx = 560
    steps = [
        ("1", "Pivot and winch", ["A winch on the centre post sets the radius.",
                                  "The leash also carries tether power, so",
                                  "there is no steering and no battery swap."]),
        ("2", "Cut laps", ["The trencher drives around the ring towing",
                           "a box scraper. Each lap cuts whatever depth",
                           "the pull budget (grip or motor) allows."]),
        ("3", "Spiral ramp out", ["When the pan is full, the winch walks the",
                                  "vehicle out on a spiral ramp to the paired",
                                  "berm. Ramp grade is limited by grip."]),
        ("4", "Spread and return", ["It spreads the load in thin layers where",
                                    "the berm is lowest, grades it now and",
                                    "then, and spirals back to the cut."]),
    ]
    y = 84
    for n, head, body in steps:
        s.badge(tx + 10, y - 4, n)
        s.text(tx + 28, y, head, 13, weight=600)
        for i, ln in enumerate(body):
            s.text(tx + 28, y + 18 + 16 * i, ln, 12, t["ink2"])
        y += 30 + 16 * len(body) + 8

    # side view inset: trencher towing the pan in the cut
    oy = 470
    ox = tx
    s.text(ox, oy - 52, "In the cut (side view, not to scale)", 12, t["ink2"], weight=600)
    ground = [(ox, oy - 20), (ox + 90, oy - 20), (ox + 116, oy), (ox + 340, oy)]
    s.poly(ground + [(ox + 340, oy + 30), (ox, oy + 30)], fill=earth, fo=0.28, closed=True)
    s.poly(ground, t["ink2"], 1.4)
    # cut layer removed by the pan, shown dashed over the vehicle's track
    s.line(ox + 116, oy + 6, ox + 340, oy + 6, t["muted"], 1, "3,3")
    s.text(ox + 340, oy + 20, "next lap cuts to here", 10, t["muted"], "end")
    # trencher body + 3 driven wheels (6WD)
    bx0 = ox + 160
    s.add(f'<rect x="{bx0}" y="{oy - 34}" width="90" height="20" rx="3" fill="{t["series"][2]}" '
          f'stroke="{t["ink"]}" stroke-width="1.2"/>')
    for i in range(3):
        s.add(f'<circle cx="{bx0 + 15 + 30 * i}" cy="{oy - 9}" r="9" fill="{t["ink2"]}"/>')
    s.text(bx0 + 45, oy - 40, "6WD trencher", 10, t["ink2"], "middle")
    # pan behind (left), blade slightly below surface
    p0 = ox + 122
    s.poly([(p0, oy - 30), (p0 + 28, oy - 30), (p0 + 28, oy - 2), (p0 + 4, oy + 3)], t["ink2"], 1.2,
           fill=t["base"], closed=True)
    s.line(p0 + 28, oy - 20, bx0, oy - 20, t["ink2"], 1.4)
    s.text(p0 + 14, oy - 36, "pan", 10, t["ink2"], "middle")
    # direction
    s.line(bx0 + 100, oy - 24, bx0 + 140, oy - 24, t["series"][2], 2)
    arrowhead(s, bx0 + 142, oy - 24, 0, t["series"][2], 8)
    s.text(bx0 + 120, oy - 30, "travel", 10, t["ink2"], "middle")
    # leash goes into the page
    s.add(f'<circle cx="{bx0 + 45}" cy="{oy - 24}" r="3.5" fill="{t["surface"]}" stroke="{t["ink"]}" stroke-width="1.4"/>')
    s.text(ox, oy + 48, "Leash runs into the page, to the pivot.", 11, t["muted"])

    write("tether-concept", theme, s.render(
        "Tethered EOx trencher concept",
        "Plan view: a winch at the pivot holds the trencher on a leash in the outer moat; it tows a pan around the "
        "ring, climbs a spiral ramp to the outer berm, spreads the load and spirals back. Inset: side view of the "
        "trencher towing the pan."))


# ---------------------------------------------------------------------------
# 3. Level-water design on a slope (schematic)
# ---------------------------------------------------------------------------
def level_water_fig(theme):
    t = THEMES[theme]
    W, H = 920, 410
    s = Svg(W, H, theme)
    s.text(16, 26, "Level-water moats on sloping ground", 16, weight=600)
    s.text(16, 46, "Section through one ring moat, on the low side and the high side of the pivot "
                   "(schematic, slope exaggerated)", 12, t["ink2"])
    left, right = 24, W - 24
    y_low, y_high = 285, 195               # existing ground at the left and right edges

    def gy(x):
        return y_low + (y_high - y_low) * (x - left) / (right - left)

    water_y, bed_y = 284, 330              # one waterline, one flat bed
    earth, water = t["series"][3], t["series"][0]

    def moat(xc, bw):
        """Flat bed at bed_y; banks rise at beta (45 deg on screen) until they meet ground."""
        xa, xb = xc - bw / 2, xc + bw / 2
        xl = xa
        while bed_y - (xa - xl) > gy(xl):
            xl -= 0.25
        xr = xb
        while bed_y - (xr - xb) > gy(xr):
            xr += 0.25
        return [(xl, gy(xl)), (xa, bed_y), (xb, bed_y), (xr, gy(xr))]

    def berm(xa, xb, hgt):
        fl = hgt * 1.3
        return [(xa, gy(xa)), (xa + fl, gy(xa + fl) - hgt), (xb - fl, gy(xb - fl) - hgt), (xb, gy(xb))]

    m_low, m_high = moat(250, 56), moat(640, 56)
    b_low = berm(max(left + 4, m_low[0][0] - 130), m_low[0][0] - 14, 30)
    b_high = berm(m_high[3][0] + 14, min(right - 4, m_high[3][0] + 144), 30)
    surf = [(left, gy(left))] + b_low + m_low + m_high + b_high + [(right, gy(right))]
    s.poly(surf + [(right, 356), (left, 356)], fill=earth, fo=0.22, closed=True)

    def at_y(x0, y0, x1, y1, y):
        return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    for m in (m_low, m_high):
        (xl, yl), (xa, _), (xb, _), (xr, yr) = m
        wl_l, wl_r = at_y(xl, yl, xa, bed_y, water_y), at_y(xb, bed_y, xr, yr, water_y)
        s.poly([(wl_l, water_y), (xa, bed_y), (xb, bed_y), (wl_r, water_y)], fill=water, fo=0.30, closed=True)
        s.line(wl_l, water_y, wl_r, water_y, water, 1.5)
    s.line(left, gy(left), right, gy(right), t["muted"], 1.5, "3,3")
    s.poly(surf, t["ink"], 2)
    s.line(left, water_y, right, water_y, water, 0.8, "6,4")
    xp = 395
    s.line(xp, 120, xp, gy(xp), t["base"], 1, "2,3")
    s.text(xp, 114, "pivot", 11, t["muted"], "middle")

    def note(x, y, lines, anchor="start", col=None):
        for i, ln in enumerate(lines):
            s.text(x, y + 15 * i, ln, 11.5, col or t["ink2"], anchor)

    def dim(x, y0, y1, label):
        s.line(x, y0 + 2, x, y1 - 2, t["ink"], 1)
        arrowhead(s, x, y0, -math.pi / 2, t["ink"], 6)
        arrowhead(s, x, y1, math.pi / 2, t["ink"], 6)
        s.text(x, y1 + 16, label, 11, t["ink"], "middle")
    dim(250, gy(250), bed_y, "shallow cut")
    dim(640, gy(640), bed_y, "deeper cut")
    # waterline rule
    note(left + 4, 378, ["Waterline = the lowest existing ground along the moat, less freeboard (0.3 m).",
                         "The bed and the water are level all the way round."])
    s.text(right, water_y + 14, "one waterline", 11, water, "end")
    # high side
    note(560, 150, ["High side: same bed and waterline,", "so the cut is deeper"])
    # daylight callout on the inner bank of the high-side moat
    xd, yd = m_high[0]
    s.line(xd, yd, xd - 40, yd - 40, t["ink2"], 1)
    s.add(f'<circle cx="{xd:.1f}" cy="{yd:.1f}" r="3" fill="{t["ink"]}"/>')
    note(xd - 44, yd - 60, ["banks rise at β until they", "daylight into existing ground"], "end")
    # berms
    for bm in (b_low, b_high):
        xm = (bm[1][0] + bm[2][0]) / 2
        note(xm, bm[1][1] - 12, ["berm follows ground"], "middle")
    # legend
    lx, ly = 16, 72
    s.line(lx, ly - 4, lx + 22, ly - 4, t["muted"], 1.5, "3,3")
    s.text(lx + 28, ly, "existing ground", 11, t["ink2"])
    s.line(lx + 140, ly - 4, lx + 162, ly - 4, t["ink"], 2)
    s.text(lx + 168, ly, "design surface", 11, t["ink2"])
    s.add(f'<rect x="{lx + 270}" y="{ly - 10}" width="22" height="10" fill="{water}" fill-opacity="0.30"/>')
    s.text(lx + 298, ly, "water", 11, t["ink2"])
    s.text(right, ly, "low side ← → high side", 11, t["muted"], "end")
    write("level-water", theme, s.render(
        "Level-water design on a slope",
        "Schematic section: each moat has one flat bed and one waterline, set from the lowest ground along the "
        "moat less freeboard. On the high side the cut is deeper, the banks rise at the side-slope angle until "
        "they meet existing ground, and the berms sit on top of existing ground."))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for th in THEMES:
        section_fig(th)
        concept_fig(th)
        level_water_fig(th)
    print("ok")
