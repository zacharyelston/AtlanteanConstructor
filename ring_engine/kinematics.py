"""Kinematics of the centre-pivot radial sweep rig.

Trajectory generation is pure NumPy. ``build_rig`` / ``pose_rig`` create and
drive the Blender proxy geometry and only import ``bpy`` when called.

Rig topology (parent -> child):

    Pivot_Anchor (empty, origin)
      +- Mast                         static vertical mast
      +- Arm_Rotor (empty, rot_z = theta)
           +- Radial_Truss            fixed-length truss at mast height
           +- End_Tower               outer support leg, foot clamped to terrain
           +- Trolley                 runs along the truss, x = r
           |    +- Hoist_Cable        trolley -> scraper, length follows terrain
           +- Scraper_Carriage        x = r, z = f(r, theta) (terrain clamp)
           +- Radial_Conveyor         spans scraper -> chute
           +- Discharge_Chute         x = r_dump over the paired berm
                +- Spoil_Stream       chute -> berm surface
"""
import math
from dataclasses import dataclass

import numpy as np

from terrain_engine import berm_profile, canal_profile


@dataclass
class Trajectory:
    theta: np.ndarray     # rad, monotonically increasing (continuous rotation)
    r: np.ndarray         # scraper radial position, m
    r_dump: np.ndarray    # discharge chute radial position, m
    active: np.ndarray    # bool: scraper engaged (False on radial transits)
    moat: np.ndarray      # moat being cut (-1 on transit)
    berm: np.ndarray      # berm receiving spoil
    lift: np.ndarray      # 1-based lift (layer) index
    dt_kin: np.ndarray    # kinematic time from previous sample, s

    def __len__(self):
        return len(self.theta)

    @property
    def kinematic_time_s(self):
        return float(self.dt_kin.sum())


# --------------------------------------------------------------------------
# Path primitives
# --------------------------------------------------------------------------
def archimedean_spiral(r_a, r_b, revolutions, ds, theta0=0.0):
    """r(theta) = R_min + (R_max - R_min) / (2*pi*N) * theta, resampled at arc length ``ds``.

    ``r_b < r_a`` gives an inward spiral; rotation direction is always +theta.
    """
    t_max = 2.0 * math.pi * revolutions
    approx_len = t_max * max(r_a, r_b) + abs(r_b - r_a)
    m = max(256, int(approx_len / ds * 8))
    t = np.linspace(0.0, t_max, m)
    r = r_a + (r_b - r_a) * t / t_max
    rm = 0.5 * (r[1:] + r[:-1])
    seg = np.hypot(rm * np.diff(t), np.diff(r))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    st = np.append(np.arange(0.0, s[-1], ds), s[-1])
    return theta0 + np.interp(st, s, t), np.interp(st, s, r)


def stepped_rings(r_a, r_b, pitch, ds, theta0=0.0):
    """Concentric full circles every ``pitch`` metres with a short radial feed between them."""
    n = max(1, int(math.ceil(abs(r_b - r_a) / pitch)) + 1)
    radii = np.linspace(r_a, r_b, n)
    th, rr = [], []
    t = theta0
    for k, rad in enumerate(radii):
        steps = max(8, int(math.ceil(2.0 * math.pi * rad / ds)))
        tt = t + np.linspace(0.0, 2.0 * math.pi, steps + 1)
        th.append(tt)
        rr.append(np.full_like(tt, rad))
        t = tt[-1]
        if k + 1 < n:
            feed = max(2, int(math.ceil(abs(radii[k + 1] - rad) / ds)) + 1)
            th.append(np.full(feed, t))
            rr.append(np.linspace(rad, radii[k + 1], feed))
    return np.concatenate(th), np.concatenate(rr)


def radial_transit(r_from, r_to, theta, ds):
    steps = max(2, int(math.ceil(abs(r_to - r_from) / ds)) + 1)
    return np.full(steps, theta), np.linspace(r_from, r_to, steps)


# --------------------------------------------------------------------------
# Full multi-lift, multi-ring schedule
# --------------------------------------------------------------------------
def _cumulative(r_in, r_out, profile_fn, samples=2001):
    """(r, F(r)) where F is the normalised cumulative solid-of-revolution volume, strictly rising."""
    r = np.linspace(r_in, r_out, samples)
    w = 2.0 * np.pi * r * np.abs(profile_fn(r))
    c = np.concatenate([[0.0], np.cumsum(0.5 * (w[1:] + w[:-1]) * np.diff(r))])
    c = c / max(c[-1], 1e-12)
    c = c + np.linspace(0.0, 1e-9, samples)  # break ties so np.interp can invert
    return r, c


def build_trajectory(cfg, berm_heights=None):
    fp = cfg.footprint_radius
    ds = cfg.path_step
    pitch = 2.0 * fp * (1.0 - cfg.pass_overlap)
    moat_to_berm = cfg.moat_to_berm()
    order = list(range(len(cfg.moats)))

    parts = []  # (theta, r, active, moat, berm, lift)
    theta, r_cur = 0.0, cfg.moats[0].r_in + 0.5 * fp
    for lift in range(1, cfg.lifts + 1):
        outward = lift % 2 == 1               # boustrophedon: out on odd lifts, in on even
        for m in (order if outward else order[::-1]):
            moat = cfg.moats[m]
            a, b = moat.r_in + 0.5 * fp, moat.r_out - 0.5 * fp
            if a > b:
                a = b = 0.5 * (moat.r_in + moat.r_out)
            if not outward:
                a, b = b, a
            berm = moat_to_berm[m][0]
            if abs(r_cur - a) > 1e-6:
                th, rr = radial_transit(r_cur, a, theta, ds)
                parts.append((th[1:], rr[1:], False, -1, berm, lift))
            if cfg.path_mode == "stepped":
                th, rr = stepped_rings(a, b, pitch, ds, theta)
            else:
                n_rev = cfg.revolutions_per_moat or max(1, int(math.ceil(abs(b - a) / pitch)))
                th, rr = archimedean_spiral(a, b, n_rev, ds, theta)
            parts.append((th, rr, True, m, berm, lift))
            theta, r_cur = float(th[-1]), float(rr[-1])

    theta_a = np.concatenate([p[0] for p in parts])
    r_a = np.concatenate([p[1] for p in parts])
    active = np.concatenate([np.full(len(p[0]), p[2]) for p in parts])
    moat_a = np.concatenate([np.full(len(p[0]), p[3], dtype=np.int16) for p in parts])
    berm_a = np.concatenate([np.full(len(p[0]), p[4], dtype=np.int16) for p in parts])
    lift_a = np.concatenate([np.full(len(p[0]), p[5], dtype=np.int16) for p in parts])

    # Chute radius (mass-haul mapping): the chute sits where the berm's cumulative design fill
    # fraction equals the moat's cumulative cut fraction at the scraper radius, so spoil is laid
    # where there is room for it. Without berm heights, fall back to a plain radial fraction.
    r_dump = np.zeros_like(r_a)
    for m, moat in enumerate(cfg.moats):
        sel = moat_a == m
        if not sel.any():
            continue
        k = moat_to_berm[m][0]
        bm = cfg.berms[k]
        lo = bm.r_in + 0.5 * cfg.chute_radius
        hi = max(lo, bm.r_out - 0.5 * cfg.chute_radius)
        if berm_heights is not None:
            frac = np.interp(r_a[sel], *_cumulative(
                moat.r_in, moat.r_out, lambda r: canal_profile(r, moat, cfg.tan_canal)))
            rb, cb = _cumulative(bm.r_in, bm.r_out, lambda r: berm_profile(
                r, bm.r_in, bm.r_out, berm_heights[k], cfg.tan_repose))
            r_dump[sel] = np.clip(np.interp(frac, cb, rb), lo, hi)
        else:
            frac = np.clip((r_a[sel] - moat.r_in) / moat.width, 0.0, 1.0)
            r_dump[sel] = lo + frac * (hi - lo)
    # Transit samples hold the last chute position.
    idx = np.where(active, np.arange(len(r_a)), 0)
    idx = np.maximum.accumulate(idx)
    first = int(np.argmax(active))
    idx[:first] = first
    r_dump = r_dump[idx]

    d_th = np.abs(np.diff(theta_a))
    d_r = np.abs(np.diff(r_a))
    d_s = np.hypot(0.5 * (r_a[1:] + r_a[:-1]) * d_th, d_r)
    dt = np.maximum.reduce([d_th / cfg.v_theta, d_r / cfg.v_r, d_s / cfg.v_tool_max])
    dt = np.concatenate([[0.0], dt])

    return Trajectory(theta_a, r_a, r_dump, active, moat_a, berm_a, lift_a, dt)


# --------------------------------------------------------------------------
# Blender proxy rig
# --------------------------------------------------------------------------
def _material(name, rgb, emission=0.0):
    import bpy
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    from terrain_engine import ensure_nodes
    ensure_nodes(mat)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.55
        if emission > 0:
            for key in ("Emission Color", "Emission"):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = (*rgb, 1.0)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = (*rgb, 1.0)
    return mat


def _mesh_obj(name, kind, size, offset=(0, 0, 0), mat=None, parent=None, segments=24):
    """Create a primitive mesh object. ``kind``: 'box' | 'cyl' | 'cone'."""
    import bmesh
    import bpy
    bm = bmesh.new()
    if kind == "box":
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x = v.co.x * size[0] + offset[0]
            v.co.y = v.co.y * size[1] + offset[1]
            v.co.z = v.co.z * size[2] + offset[2]
    else:
        r1, r2, depth = size
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                              radius1=r1, radius2=r2, depth=depth)
        for v in bm.verts:
            v.co.x += offset[0]
            v.co.y += offset[1]
            v.co.z += offset[2]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def _empty(name, parent=None, display="PLAIN_AXES", size=3.0):
    import bpy
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = display
    obj.empty_display_size = size
    bpy.context.scene.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj


def _limit_x(obj, lo, hi):
    c = obj.constraints.new("LIMIT_LOCATION")
    c.name = "Clamp_Radial_Travel"
    c.use_min_x, c.min_x = True, lo
    c.use_max_x, c.max_x = True, hi
    c.owner_space = "LOCAL"
    return c


def build_rig(cfg):
    H = cfg.mast_height
    L = cfg.r_max + 6.0
    fp = cfg.footprint_radius
    steel = _material("Rig_Steel", (0.55, 0.57, 0.6))
    yellow = _material("Rig_Yellow", (0.95, 0.68, 0.05))
    orange = _material("Rig_Orange", (0.9, 0.32, 0.05))
    belt = _material("Rig_Belt", (0.08, 0.08, 0.09))
    spoil = _material("Rig_Spoil", (0.62, 0.42, 0.2))

    pivot = _empty("Pivot_Anchor", display="ARROWS", size=6.0)
    _mesh_obj("Mast", "cyl", (2.2, 1.4, H + 3.0), (0, 0, (H + 3.0) / 2), steel, pivot)
    _mesh_obj("Mast_Base", "cyl", (6.0, 6.0, 1.0), (0, 0, 0.5), steel, pivot)
    rotor = _empty("Arm_Rotor", pivot, display="SINGLE_ARROW", size=8.0)
    rotor.rotation_mode = "XYZ"
    _mesh_obj("Radial_Truss", "box", (L, 2.6, 2.4), (L / 2, 0, H), steel, rotor)
    _mesh_obj("Truss_Chord", "box", (L, 0.4, 0.4), (L / 2, 0, H + 2.2), steel, rotor)
    end_tower = _mesh_obj("End_Tower", "cyl", (0.6, 0.6, 1.0), (0, 0, -0.5), steel, rotor)
    end_tower.location = (L - 1.0, 0, H)
    bogie = _mesh_obj("End_Bogie", "box", (3.0, 4.0, 1.5), (0, 0, 0.75), belt, rotor)

    trolley = _mesh_obj("Trolley", "box", (3.2, 2.6, 1.2), (0, 0, -1.5), yellow, rotor)
    _limit_x(trolley, cfg.r_min - fp, L)
    cable = _mesh_obj("Hoist_Cable", "cyl", (0.35, 0.35, 1.0), (0, 0, -0.5), belt, trolley)
    cable.location = (0, 0, -2.1)
    carriage = _mesh_obj("Scraper_Carriage", "box", (2 * fp, 3.0, 1.6), (0, 0, 0.8), yellow, rotor)
    _mesh_obj("Scraper_Blade", "box", (2 * fp, 0.3, 0.9), (0, 1.6, 0.25), orange, carriage)
    _limit_x(carriage, cfg.r_min - fp, L)

    conveyor = _mesh_obj("Radial_Conveyor", "box", (1.0, 1.2, 0.35), (0, 0, 0), belt, rotor)
    chute = _mesh_obj("Discharge_Chute", "cone", (0.6, 1.6, 2.4), (0, 0, -1.2), orange, rotor)
    stream = _mesh_obj("Spoil_Stream", "cyl", (0.9, 0.5, 1.0), (0, 0, -0.5), spoil, chute, segments=12)
    stream.location = (0, 0, -2.4)

    return {
        "pivot": pivot, "rotor": rotor, "end_tower": end_tower, "bogie": bogie,
        "trolley": trolley, "cable": cable, "carriage": carriage,
        "conveyor": conveyor, "chute": chute, "stream": stream,
        "H": H, "L": L,
    }


def pose_rig(rig, theta, r, z_head, r_dump, z_dump, z_end, discharging):
    """Apply one kinematic state. Children inherit theta via the Arm_Rotor parent."""
    H, L = rig["H"], rig["L"]
    rig["rotor"].rotation_euler = (0.0, 0.0, theta)
    rig["trolley"].location = (r, 0.0, H)
    rig["carriage"].location = (r, 0.0, z_head)
    rig["cable"].scale = (1.0, 1.0, max(0.1, H - 2.1 - z_head - 1.6))
    rig["end_tower"].scale = (1.0, 1.0, max(0.1, H - z_end - 1.5))
    rig["bogie"].location = (L - 1.0, 0.0, z_end)
    mid = 0.5 * (r + r_dump)
    rig["conveyor"].location = (mid, 0.0, H - 1.3)
    rig["conveyor"].scale = (max(0.5, abs(r_dump - r)), 1.0, 1.0)
    rig["chute"].location = (r_dump, 0.0, H - 1.3)
    drop = (H - 1.3 - 2.4) - z_dump
    rig["stream"].scale = (1.0, 1.0, max(0.05, drop) if discharging else 0.05)
    rig["stream"].hide_render = not discharging
    rig["stream"].hide_viewport = not discharging
