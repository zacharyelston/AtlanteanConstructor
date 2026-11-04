"""Terrain engine: heightmap, ring design profiles, cut/fill operators, volumetrics.

The ground is a Cartesian heightmap stored as two layers:

* ``bank``  - surface of undisturbed (in-situ, "bank") soil. Cutting lowers it.
* ``loose`` - thickness of loose (swelled) spoil sitting on top of ``bank``.

The visible surface is ``z = bank + loose``. Cutting removes loose material
first (already swelled, no further expansion) and then bank material, which
swells by ``Sf`` when it enters the bucket. Only loose material slumps under
the angle-of-repose relaxation, so the invariant

    loose_on_ground + bucket_contents == Sf * bank_volume_cut

holds to floating-point precision for the whole run.

Everything except the ``*_blender_*`` helpers is pure NumPy and runs anywhere.
"""
import math

import numpy as np

_trapz = getattr(np, "trapezoid", None) or np.trapz


# --------------------------------------------------------------------------
# Design cross-sections (polar, axisymmetric)
# --------------------------------------------------------------------------
def canal_profile(r, moat, tan_beta):
    """Trapezoidal canal: z(r) <= 0 with side slopes tan(beta) and flat bed at -depth."""
    r = np.asarray(r, dtype=float)
    depth = np.minimum(np.minimum((r - moat.r_in) * tan_beta, (moat.r_out - r) * tan_beta), moat.depth)
    return -np.clip(depth, 0.0, None)


def berm_profile(r, r_in, r_out, height, tan_phi):
    """Trapezoidal berm: z(r) >= 0, crown at ``height``, flanks at the angle of repose."""
    r = np.asarray(r, dtype=float)
    h = np.minimum(np.minimum((r - r_in) * tan_phi, (r_out - r) * tan_phi), height)
    return np.clip(h, 0.0, None)


def radial_volume(r_in, r_out, profile_fn, samples=20001):
    """Exact-ish solid-of-revolution volume: integral of 2*pi*r*|z(r)| dr."""
    r = np.linspace(r_in, r_out, samples)
    return float(_trapz(2.0 * np.pi * r * np.abs(profile_fn(r)), r))


# --------------------------------------------------------------------------
# Colour ramp shared by the PNG writer and the Blender colour attribute
# --------------------------------------------------------------------------
GROUND_RGB = np.array([0.43, 0.37, 0.26])
CUT_RGB = np.array([0.08, 0.22, 0.42])
FILL_RGB = np.array([0.66, 0.42, 0.17])


def cut_fill_rgb(delta, depth_ref, height_ref):
    """Map elevation change to colour: blue = cut, ochre = fill, tan = untouched."""
    c = np.clip(-delta / max(depth_ref, 1e-6), 0.0, 1.0)[..., None]
    f = np.clip(delta / max(height_ref, 1e-6), 0.0, 1.0)[..., None]
    return GROUND_RGB * (1.0 - c - f) + CUT_RGB * c + FILL_RGB * f


# --------------------------------------------------------------------------
# Heightmap terrain
# --------------------------------------------------------------------------
class Terrain:
    def __init__(self, cfg):
        self.cfg = cfg
        n = cfg.resolution
        self.n = n
        self.extent = cfg.extent
        self.axis = np.linspace(-cfg.extent, cfg.extent, n)
        self.dx = float(self.axis[1] - self.axis[0])
        self.cell_area = self.dx * self.dx
        self.X, self.Y = np.meshgrid(self.axis, self.axis)  # X[i, j] = axis[j]
        self.R = np.hypot(self.X, self.Y)

        self.z0 = np.zeros((n, n))          # flat datum z = 0
        self.bank = self.z0.copy()
        self.loose = np.zeros((n, n))
        self.design = np.zeros((n, n))
        self.moat_id = np.full((n, n), -1, dtype=np.int16)
        self.berm_id = np.full((n, n), -1, dtype=np.int16)
        self.berm_heights = []
        self.design_report = {"moats": [], "berms": []}
        self._build_design()

    # ---------------------------------------------------------------- design
    def _build_design(self):
        cfg, A = self.cfg, self.cell_area
        tb, tp, sf = cfg.tan_canal, cfg.tan_repose, cfg.swell_factor

        cut_grid = []
        for k, m in enumerate(cfg.moats):
            prof = canal_profile(self.R, m, tb)
            mask = prof < 0.0
            self.design[mask] = prof[mask]
            self.moat_id[mask] = k
            v_grid = float(-prof.sum() * A)
            v_exact = radial_volume(m.r_in, m.r_out, lambda r, m=m: canal_profile(r, m, tb))
            cut_grid.append(v_grid)
            self.design_report["moats"].append({
                "index": k, "r_in": m.r_in, "r_out": m.r_out, "depth": m.depth,
                "V_bank_grid_m3": v_grid, "V_bank_exact_m3": v_exact,
            })

        fed = cfg.moat_to_berm()
        for k, b in enumerate(cfg.berms):
            sel = (self.R >= b.r_in) & (self.R <= b.r_out)
            Rb = self.R[sel]
            h_peak = 0.5 * b.width * tp
            target = sf * cut_grid[b.source_moat] / len(fed[b.source_moat])

            def vol(h, Rb=Rb, b=b):
                return float(berm_profile(Rb, b.r_in, b.r_out, h, tp).sum() * A)

            if b.height is None or cfg.auto_size_berms:
                if vol(h_peak) < target:
                    cfg.warnings.append(
                        "Berm %d cannot hold its share of spoil even as a sharp ridge "
                        "(%.0f of %.0f m3); widen it. Excess will over-fill the crown."
                        % (k, vol(h_peak), target))
                    h = h_peak
                else:
                    lo, hi = 0.0, h_peak
                    for _ in range(60):
                        mid = 0.5 * (lo + hi)
                        if vol(mid) < target:
                            lo = mid
                        else:
                            hi = mid
                    h = 0.5 * (lo + hi)
            else:
                h = min(b.height, h_peak)
                if b.height > h_peak:
                    cfg.warnings.append("Berm %d height %.2f exceeds repose-limited peak %.2f; capped."
                                        % (k, b.height, h_peak))
            self.berm_heights.append(h)
            prof = np.zeros_like(self.R)
            prof[sel] = berm_profile(Rb, b.r_in, b.r_out, h, tp)
            mask = prof > 0.0
            self.design[mask] = prof[mask]
            self.berm_id[mask] = k
            self.design_report["berms"].append({
                "index": k, "r_in": b.r_in, "r_out": b.r_out, "source_moat": b.source_moat,
                "crown_height_m": h, "repose_peak_m": h_peak,
                "V_target_loose_m3": target, "V_design_grid_m3": vol(h),
                "V_design_exact_m3": radial_volume(
                    b.r_in, b.r_out, lambda r, b=b, h=h: berm_profile(r, b.r_in, b.r_out, h, tp)),
            })

        self.design_cut_total = float(sum(cut_grid))
        self.design_fill_total = float(sum(d["V_design_grid_m3"] for d in self.design_report["berms"]))
        self.max_depth = max(m.depth for m in cfg.moats)
        self.max_height = max(self.berm_heights) if self.berm_heights else 1.0

    # --------------------------------------------------------------- helpers
    @property
    def z(self):
        return self.bank + self.loose

    def _index(self, x, y):
        return (y + self.extent) / self.dx, (x + self.extent) / self.dx

    def _window(self, x, y, radius):
        fi, fj = self._index(x, y)
        rr = int(math.ceil(radius / self.dx)) + 1
        i0, i1 = max(0, int(fi) - rr), min(self.n, int(fi) + rr + 2)
        j0, j1 = max(0, int(fj) - rr), min(self.n, int(fj) + rr + 2)
        if i0 >= i1 or j0 >= j1:
            return None, None
        dys = self.axis[i0:i1] - y
        dxs = self.axis[j0:j1] - x
        mask = (dys[:, None] ** 2 + dxs[None, :] ** 2) <= radius * radius
        return (slice(i0, i1), slice(j0, j1)), mask

    def sample_z(self, x, y):
        """Bilinear sample of the current surface at world (x, y)."""
        fi, fj = self._index(x, y)
        fi = min(max(fi, 0.0), self.n - 1.001)
        fj = min(max(fj, 0.0), self.n - 1.001)
        i, j = int(fi), int(fj)
        ti, tj = fi - i, fj - j
        z = self.bank[i:i + 2, j:j + 2] + self.loose[i:i + 2, j:j + 2]
        return float((z[0, 0] * (1 - tj) + z[0, 1] * tj) * (1 - ti) +
                     (z[1, 0] * (1 - tj) + z[1, 1] * tj) * ti)

    # ------------------------------------------------------------- operators
    def cut_at(self, x, y, radius, lift_frac, max_loose):
        """Scrape the disc at (x, y) down toward ``design * lift_frac`` inside moat cells.

        ``max_loose`` caps the loose-equivalent volume taken (remaining bucket room).
        Returns (bank_m3_removed, loose_m3_removed).
        """
        if max_loose <= 0.0:
            return 0.0, 0.0
        sl, mask = self._window(x, y, radius)
        if sl is None:
            return 0.0, 0.0
        m = mask & (self.moat_id[sl] >= 0)
        if not m.any():
            return 0.0, 0.0
        b = self.bank[sl]
        L = self.loose[sl]
        target = self.design[sl] * lift_frac
        excess = np.where(m, np.maximum(b + L - target, 0.0), 0.0)
        if excess.max() <= 1e-9:
            return 0.0, 0.0
        l_rm = np.minimum(L, excess)
        b_rm = excess - l_rm
        A = self.cell_area
        loose_eq = A * (l_rm.sum() + self.cfg.swell_factor * b_rm.sum())
        if loose_eq > max_loose:
            f = max_loose / loose_eq
            l_rm *= f
            b_rm *= f
        L -= l_rm          # views -> modifies self.loose / self.bank in place
        b -= b_rm
        return float(b_rm.sum() * A), float(l_rm.sum() * A)

    def deposit_at(self, x, y, radius, berm, lift_frac, amount):
        """Drop up to ``amount`` m3 of loose spoil on berm ``berm`` inside the chute disc.

        Fills toward the current lift target first, then toward the final crown.
        Returns the volume actually placed.
        """
        if amount <= 0.0:
            return 0.0
        sl, mask = self._window(x, y, radius)
        if sl is None:
            return 0.0
        m = mask & (self.berm_id[sl] == berm)
        if not m.any():
            return 0.0
        A = self.cell_area
        L = self.loose[sl]
        d = self.design[sl]
        z = self.bank[sl] + L
        placed = 0.0
        for frac in (lift_frac, 1.0):
            deficit = np.where(m, np.maximum(d * frac - z, 0.0), 0.0)
            need = deficit.sum() * A
            if need <= 1e-12:
                continue
            f = min(1.0, (amount - placed) / need)
            add = deficit * f
            L += add
            z = z + add
            placed += need * f
            if placed >= amount - 1e-12:
                break
        return float(placed)

    def relax(self, iters=3, sl=None, rate=0.2):
        """Angle-of-repose relaxation (thermal-erosion style) on the loose layer only.

        Moves loose spoil downhill wherever the cell-to-cell slope exceeds tan(phi).
        Mass-conserving: no flux crosses the window boundary and a cell never
        sheds more loose material than it holds.
        """
        if sl is None:
            sl = (slice(None), slice(None))
        talus = self.cfg.tan_repose * self.dx
        b = self.bank[sl]
        L = self.loose[sl]
        for _ in range(iters):
            z = b + L
            dxz = z[:, :-1] - z[:, 1:]          # >0: flow toward +j
            dyz = z[:-1, :] - z[1:, :]          # >0: flow toward +i
            qx = np.maximum(np.abs(dxz) - talus, 0.0) * rate
            qy = np.maximum(np.abs(dyz) - talus, 0.0) * rate
            if not (qx.any() or qy.any()):
                break
            px, py = dxz > 0, dyz > 0
            out = np.zeros_like(z)
            out[:, :-1] += np.where(px, qx, 0.0)
            out[:, 1:] += np.where(px, 0.0, qx)
            out[:-1, :] += np.where(py, qy, 0.0)
            out[1:, :] += np.where(py, 0.0, qy)
            s = np.where(out > 0.0, np.minimum(1.0, L / np.maximum(out, 1e-12)), 0.0)
            fx = qx * np.where(px, s[:, :-1], s[:, 1:])
            fy = qy * np.where(py, s[:-1, :], s[1:, :])
            fx = np.where(px, fx, -fx)          # signed flux, + = toward +j
            fy = np.where(py, fy, -fy)
            delta = np.zeros_like(z)
            delta[:, :-1] -= fx
            delta[:, 1:] += fx
            delta[:-1, :] -= fy
            delta[1:, :] += fy
            L += delta
            np.maximum(L, 0.0, out=L)           # clamp float dust

    def relax_near(self, x, y, half_width, iters=3):
        fi, fj = self._index(x, y)
        h = int(math.ceil(half_width / self.dx))
        i0, i1 = max(0, int(fi) - h), min(self.n, int(fi) + h + 1)
        j0, j1 = max(0, int(fj) - h), min(self.n, int(fj) + h + 1)
        if i1 - i0 > 2 and j1 - j0 > 2:
            self.relax(iters, (slice(i0, i1), slice(j0, j1)))

    def cleanup_deposit(self, amount):
        """Final dressing: place any spoil left in the bucket onto the most deficient berm cells."""
        if amount <= 0.0:
            return 0.0
        A = self.cell_area
        berm = self.berm_id >= 0
        deficit = np.where(berm, np.maximum(self.design - self.z, 0.0), 0.0)
        need = deficit.sum() * A
        placed = 0.0
        if need > 0:
            f = min(1.0, amount / need)
            self.loose += deficit * f
            placed = need * f
        rest = amount - placed
        if rest > 1e-9:                         # berms full: crown over-fill, evenly
            self.loose[berm] += rest / (berm.sum() * A)
            placed = amount
        return placed

    # ------------------------------------------------------------ reporting
    def volumes(self):
        A = self.cell_area
        berm = self.berm_id >= 0
        moat = self.moat_id >= 0
        loose_total = float(self.loose.sum() * A)
        loose_on_berms = float(self.loose[berm].sum() * A)
        z = self.z
        moat_err = (z - self.design)[moat]
        berm_err = (z - self.design)[berm]
        return {
            "bank_cut_grid_m3": float(np.maximum(self.z0 - self.bank, 0.0).sum() * A),
            "loose_on_ground_m3": loose_total,
            "loose_on_berms_m3": loose_on_berms,
            "loose_spilled_m3": loose_total - loose_on_berms,
            "net_surface_change_m3": float((z - self.z0).sum() * A),
            "moat_rmse_m": float(np.sqrt(np.mean(moat_err ** 2))) if moat_err.size else 0.0,
            "berm_rmse_m": float(np.sqrt(np.mean(berm_err ** 2))) if berm_err.size else 0.0,
            "moat_completion_pct": 100.0 * float(np.maximum(self.z0 - self.bank, 0.0)[moat].sum() * A)
                                   / max(self.design_cut_total, 1e-9),
        }

    def radial_profile(self, nbins=None):
        """Azimuthally averaged achieved vs design elevation, for cross-section plots."""
        nbins = nbins or int(self.cfg.r_max / self.dx)
        rmax = self.cfg.r_max + 5.0
        edges = np.linspace(0.0, rmax, nbins + 1)
        idx = np.clip(np.digitize(self.R.ravel(), edges) - 1, 0, nbins - 1)
        inside = self.R.ravel() < rmax
        cnt = np.bincount(idx[inside], minlength=nbins)
        cnt = np.maximum(cnt, 1)
        za = np.bincount(idx[inside], weights=self.z.ravel()[inside], minlength=nbins) / cnt
        zd = np.bincount(idx[inside], weights=self.design.ravel()[inside], minlength=nbins) / cnt
        rc = 0.5 * (edges[1:] + edges[:-1])
        return rc, za, zd

    def colors(self, z=None):
        z = self.z if z is None else z
        return cut_fill_rgb(z - self.z0, self.max_depth, self.max_height)

    def hillshade_rgb(self, z=None, exaggeration=3.0):
        z = self.z if z is None else z
        gy, gx = np.gradient(z * exaggeration, self.dx)
        nrm = np.sqrt(gx * gx + gy * gy + 1.0)
        light = np.array([-1.0, 1.0, 1.4])
        light = light / np.linalg.norm(light)
        shade = np.clip((-gx * light[0] - gy * light[1] + light[2]) / nrm, 0.0, 1.0)
        return self.colors(z) * (0.35 + 0.75 * shade)[..., None]


# --------------------------------------------------------------------------
# Image output without matplotlib
# --------------------------------------------------------------------------
def write_png(path, rgb):
    """Write an (H, W, 3) float [0,1] array as an 8-bit PNG (row 0 = +y edge)."""
    import struct
    import zlib
    img = (np.clip(rgb[::-1], 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    h, w = img.shape[:2]
    raw = b"".join(b"\x00" + img[r].tobytes() for r in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        fh.write(chunk(b"IEND", b""))


# --------------------------------------------------------------------------
# Blender mesh I/O (only imported inside Blender)
# --------------------------------------------------------------------------
COLOR_ATTR = "CutFill"


def ensure_nodes(idblock):
    """Enable node trees on Blender < 5 (always on, and the flag deprecated, from 5.0)."""
    import bpy
    if bpy.app.version < (5, 0, 0):
        idblock.use_nodes = True


def build_blender_mesh(terrain, name="Terrain"):
    import bpy
    n = terrain.n
    co = np.zeros((n * n, 3), dtype=np.float32)
    co[:, 0] = terrain.X.ravel()
    co[:, 1] = terrain.Y.ravel()
    co[:, 2] = terrain.z.ravel()
    idx = np.arange(n * n, dtype=np.int32).reshape(n, n)
    quads = np.stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(),
                      idx[1:, 1:].ravel(), idx[1:, :-1].ravel()], axis=1)
    nf = quads.shape[0]

    me = bpy.data.meshes.new(name)
    me.vertices.add(n * n)
    me.vertices.foreach_set("co", co.ravel())
    me.loops.add(nf * 4)
    me.loops.foreach_set("vertex_index", quads.ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 4, 4, dtype=np.int32))
    try:  # read-only (derived) in recent Blender versions
        me.polygons.foreach_set("loop_total", np.full(nf, 4, dtype=np.int32))
    except (AttributeError, TypeError, RuntimeError):
        pass
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(nf, dtype=bool))
    me.color_attributes.new(COLOR_ATTR, "FLOAT_COLOR", "POINT")

    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj, co


def update_blender_mesh(obj, co_cache, z, rgb):
    me = obj.data
    co_cache[:, 2] = z.ravel()
    me.vertices.foreach_set("co", co_cache.ravel())
    rgba = np.ones((z.size, 4), dtype=np.float32)
    rgba[:, :3] = rgb.reshape(-1, 3)
    me.color_attributes[COLOR_ATTR].data.foreach_set("color", rgba.ravel())
    me.update()
