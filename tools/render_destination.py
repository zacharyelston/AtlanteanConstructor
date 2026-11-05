"""Render the destination-scale Atlantean site (tools/destination.py) in Blender.

    /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/render_destination.py -- \
        --out docs/img --views aerial,plan,plaza [--turbines]

The ground, ring and berm come from terrain_engine.Terrain with the destination layout. The plaza
tiers, causeways, field quadrants, the dome, stalls, people, cars, solar field and turbines are simple
stand-ins placed by the rules in tools/destination.py. Helpers come from tools/render_homestead.py.
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import render_homestead as rh  # noqa: E402
import terrain_engine as te  # noqa: E402
from config import load_config  # noqa: E402

AXES = [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]          # the cross of causeways and roads
ISLAND, TIER, RING_IN, RING_OUT, BERM_IN, BERM_OUT, FIELD_OUT = 36.0, 24.0, 40.0, 62.0, 66.0, 80.0, 150.0
PLAZA_H, TIER_H = 1.5, 0.9
C = {"plaza": (0.42, 0.41, 0.38), "tier": (0.50, 0.49, 0.46), "grass": (0.10, 0.18, 0.04),
     "crop": (0.05, 0.13, 0.025), "crop_dark": (0.035, 0.11, 0.02), "bank": (0.11, 0.16, 0.045),
     "mud": (0.05, 0.04, 0.03), "field": (0.12, 0.17, 0.05), "gravel": (0.40, 0.37, 0.33)}


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=os.path.join(ROOT, "docs", "img"))
    p.add_argument("--views", default="aerial,plan,plaza")
    p.add_argument("--res", type=int, default=600)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--turbines", action="store_true")
    return p.parse_args(argv)


def near_axis(x, y, half_w):
    """Distance test: is (x, y) within half_w of any of the four axes?"""
    return (np.abs(x) < half_w) | (np.abs(y) < half_w)


def build_terrain(cfg):
    T = te.Terrain(cfg)
    z = T.design.copy()
    R, X, Y = T.R, T.X, T.Y
    base = T.z0
    # raised plaza with a near-vertical retaining wall; a second tier round the dome
    z = np.where(R < ISLAND, base + PLAZA_H, z)
    z = np.where(R < TIER + 3.0, np.maximum(z, base + PLAZA_H + TIER_H * np.clip((TIER + 3.0 - R) / 3.0, 0, 1)), z)
    # the cross of causeways over the ring, level a little above the water
    wl = T.water_levels[0]
    cz = wl + 0.7
    cross = near_axis(X, Y, 4.0) & (R > ISLAND - 1.0) & (R < BERM_IN + 1.0)
    side = near_axis(X, Y, 7.0) & ~near_axis(X, Y, 4.0) & (R > ISLAND) & (R < BERM_IN)
    slope_w = np.minimum(np.abs(np.abs(X) - 4.0), np.abs(np.abs(Y) - 4.0))
    z = np.where(cross, np.maximum(z, cz), z)
    z = np.where(side, np.maximum(z, cz - slope_w / 2.0), z)

    rgb = np.empty(z.shape + (3,))
    rgb[:] = C["field"]
    ang = np.arctan2(Y, X)
    rows = 0.5 + 0.5 * np.sin(R * 2 * math.pi / 1.6)                        # concentric crop rows
    field = (R > BERM_OUT + 4) & (R < FIELD_OUT - 4) & ~near_axis(X, Y, 6.0)
    rgb[field] = (np.array(C["crop"]) * (0.75 + 0.5 * rows[field, None]))
    berm = T.berm_id == 0
    rgb[berm] = C["bank"]
    crown = berm & ((T.design - T.z0) > 0.85)
    rgb[crown] = (np.array(C["crop_dark"]) * (0.8 + 0.6 * rows[crown, None]))
    moat = T.moat_id >= 0
    rgb[moat] = C["bank"]
    rgb[moat & (z < wl - 0.05)] = C["mud"]
    rgb[R < ISLAND] = C["plaza"]
    wedge = (R > TIER) & (R < TIER + 3.0) & (np.abs(np.sin(2 * ang)) > 0.35)    # grass slopes between the stairs
    rgb[wedge] = C["grass"]
    rgb[R < TIER] = C["tier"]
    rgb[cross] = C["gravel"]
    rgb[side] = C["bank"]
    del rgb  # replaced below so the far fields keep the same palette
    rgb2 = np.empty(z.shape + (3,))
    rgb2[:] = C["field"]
    rgb2[field] = (np.array(C["crop"]) * (0.75 + 0.5 * rows[field, None]))
    rgb2[berm] = C["bank"]
    rgb2[crown] = (np.array(C["crop_dark"]) * (0.8 + 0.6 * rows[crown, None]))
    rgb2[moat] = C["bank"]
    rgb2[moat & (z < wl - 0.05)] = C["mud"]
    rgb2[R < ISLAND] = C["plaza"]
    rgb2[wedge] = C["grass"]
    rgb2[R < TIER] = C["tier"]
    rgb2[cross] = C["gravel"]
    rgb2[side] = C["bank"]

    edge = np.concatenate([z[0], z[-1], z[:, 0], z[:, -1]])
    zf = edge.min() - 0.02
    e, far = T.extent - 0.3, 3000.0
    bm = bmesh.new()
    vin = [bm.verts.new(c) for c in ((-e, -e, zf), (e, -e, zf), (e, e, zf), (-e, e, zf))]
    vout = [bm.verts.new(c) for c in ((-far, -far, zf), (far, -far, zf), (far, far, zf), (-far, far, zf))]
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((vout[i], vout[j], vin[j], vin[i]))
    rh.mesh_obj("FieldFar", bm, rh.material("FieldFar", (0.16, 0.19, 0.06), rough=0.95))
    obj, co = te.build_blender_mesh(T, "Ground")
    te.update_blender_mesh(obj, co, z, rgb2)
    obj.data.materials.append(rh.material("Ground", (0.2, 0.3, 0.1), rough=0.95, use_attr=te.COLOR_ATTR, noise=0.15))
    return T, z


def instances(mesh, name, placements):
    for k, (loc, rot, sc) in enumerate(placements):
        o = rh.link(bpy.data.objects.new("%s_%d" % (name, k), mesh))
        o.location, o.rotation_euler, o.scale = loc, rot, sc


def unit_box(name, mats):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    return me


def add_roads(T, z):
    gravel = rh.material("Gravel", C["gravel"], rough=0.95)
    rh.drape_annulus(T, z, 1.0, "RingWalk", RING_OUT + 0.8, BERM_IN - 0.6, gravel, seg=900)
    rh.drape_annulus(T, z, 1.0, "BermRoad", BERM_OUT + 0.5, BERM_OUT + 4.0, gravel, seg=900)
    rh.drape_annulus(T, z, 1.0, "OuterRoad", FIELD_OUT - 4.0, FIELD_OUT, gravel, seg=1200)
    for a in AXES:
        rh.drape_strip(T, z, 1.0, "CrossRoad", a, BERM_IN - 1.0, FIELD_OUT + 30.0, 3.5, gravel)


def add_water(T):
    water = rh.material("Water", (0.01, 0.045, 0.06), rough=0.04)
    wb = water.node_tree.nodes.get("Principled BSDF")
    for nm, val in (("IOR", 1.33), ("Specular IOR Level", 0.25)):
        if nm in wb.inputs:
            wb.inputs[nm].default_value = val
    rh.annulus("Water", RING_IN - 2.5, RING_OUT + 2.5, T.water_levels[0], water, seg=720)


def add_island(T, z):
    base = float(np.median(T.z0))
    hedge = rh.material("Hedge", (0.05, 0.14, 0.03), rough=0.95)
    stone = rh.material("Stone", (0.45, 0.43, 0.40), rough=0.9)
    # hedge-faced wall: a planted band from the water up past the plaza edge (a parapet hedge)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=180, radius1=ISLAND + 0.6, radius2=ISLAND + 0.2, depth=PLAZA_H + 2.2)
    o = rh.mesh_obj("HedgeWall", bm, hedge)
    o.location = (0, 0, base + (PLAZA_H + 2.2) / 2 - 1.0)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=180, radius1=ISLAND - 1.2, radius2=ISLAND - 1.2, depth=1.0)
    o = rh.mesh_obj("HedgeInner", bm, hedge)
    o.location = (0, 0, base + PLAZA_H + 0.5)
    # gateways through the hedge at the four causeways
    for a in AXES:
        rh.box("Gate", (3.0, 6.5, 2.6), ((ISLAND + 0.4) * math.cos(a), (ISLAND + 0.4) * math.sin(a), base + PLAZA_H + 0.9),
               stone, (0, 0, a))


def add_dome(T, z):
    base = float(np.median(T.z0)) + PLAZA_H + TIER_H
    r = 18.3
    shell = rh.material("Monolithic", (0.82, 0.81, 0.77), rough=0.55)
    glass = rh.material("Glazing", (0.03, 0.05, 0.07), rough=0.08, metal=0.2)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=r)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < 2.6], context="VERTS")
    o = rh.mesh_obj("Dome", bm, shell, smooth=True)
    o.location = (0, 0, base)
    # glazed band round the base (entry, market frontage) and an oculus
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=96, radius1=r * 0.995, radius2=r * 0.985, depth=3.0)
    o = rh.mesh_obj("GlassBand", bm, glass)
    o.location = (0, 0, base + 1.4)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=3.2)
    o = rh.mesh_obj("Oculus", bm, glass)
    o.location = (0, 0, base + r - 0.25)
    # a ring of skylights
    for k in range(12):
        a = 2 * math.pi * k / 12
        el = math.radians(52)
        x, y, h = r * math.cos(el) * math.cos(a), r * math.cos(el) * math.sin(a), r * math.sin(el)
        rh.box("Skylight", (2.2, 1.4, 0.15), (x, y, base + h + 0.05), glass, (0, -(math.pi / 2 - el), a))
    for a in AXES:                                  # entrance canopies
        rh.box("Entry", (5.0, 5.0, 0.3), ((r + 1.5) * math.cos(a), (r + 1.5) * math.sin(a), base + 3.2), shell, (0, 0, a))


def add_stalls(T, z, rng):
    base = float(np.median(T.z0)) + PLAZA_H
    colours = [(0.85, 0.85, 0.82), (0.10, 0.30, 0.50), (0.08, 0.40, 0.38), (0.55, 0.12, 0.10), (0.85, 0.85, 0.82)]
    mats = [rh.material("Canopy%d" % i, c, rough=0.7) for i, c in enumerate(colours)]
    post = rh.material("Post", (0.2, 0.2, 0.2), rough=0.6)
    meshes = [unit_box("CanopyMesh%d" % i, [m]) for i, m in enumerate(mats)]
    k = 0
    for rr, n in ((28.5, 44), (32.5, 52)):
        for i in range(n):
            a = 2 * math.pi * (i + 0.5) / n
            if min(abs(math.atan2(math.sin(a - ax), math.cos(a - ax))) for ax in AXES) * rr < 4.0:
                continue
            x, y = rr * math.cos(a), rr * math.sin(a)
            o = rh.link(bpy.data.objects.new("Stall_%d" % k, meshes[int(rng.integers(len(meshes)))]))
            o.location, o.rotation_euler, o.scale = (x, y, base + 2.4), (0, 0, a), (3.0, 3.0, 0.35)
            rh.box("StallTable", (2.6, 0.8, 0.8), (x, y, base + 0.4), post, (0, 0, a + math.pi / 2))
            k += 1


def add_people(T, z, rng, n=650):
    cols = [(0.6, 0.1, 0.1), (0.1, 0.2, 0.5), (0.85, 0.85, 0.8), (0.15, 0.15, 0.15), (0.5, 0.4, 0.1), (0.2, 0.4, 0.2)]
    meshes = [unit_box("Person%d" % i, [rh.material("Clothes%d" % i, c, rough=0.8)]) for i, c in enumerate(cols)]
    k = 0
    while k < n:
        zone = rng.random()
        if zone < 0.55:                                     # plaza
            rr, a = rng.uniform(19.5, 35.0), rng.uniform(0, 2 * math.pi)
            x, y = rr * math.cos(a), rr * math.sin(a)
        elif zone < 0.75:                                   # causeways and cross roads
            a = AXES[int(rng.integers(4))]
            rr, off = rng.uniform(36.0, 140.0), rng.uniform(-2.5, 2.5)
            x, y = rr * math.cos(a) - off * math.sin(a), rr * math.sin(a) + off * math.cos(a)
        else:                                               # the ring walk
            rr, a = rng.uniform(63.0, 65.5), rng.uniform(0, 2 * math.pi)
            x, y = rr * math.cos(a), rr * math.sin(a)
        g = rh.ground_z(T, z, x, y)
        o = rh.link(bpy.data.objects.new("Person_%d" % k, meshes[int(rng.integers(len(meshes)))]))
        o.location, o.scale = (x, y, g + 0.85), (0.45, 0.35, 1.7)
        k += 1


def add_parking_solar(T, z, rng):
    cols = [(0.6, 0.6, 0.62), (0.08, 0.08, 0.09), (0.75, 0.75, 0.73), (0.35, 0.05, 0.05), (0.1, 0.15, 0.3)]
    meshes = [unit_box("Car%d" % i, [rh.material("Paint%d" % i, c, rough=0.3, metal=0.5)]) for i, c in enumerate(cols)]
    lot = rh.material("Lot", (0.33, 0.31, 0.28), rough=0.95)
    gz = float(np.median(T.z0))
    # parking along the north-east, outside the outer road
    cx, cy, w, h = 125.0, 135.0, 120.0, 60.0
    rh.box("ParkingLot", (w, h, 0.1), (cx, cy, gz + 0.05), lot, (0, 0, math.radians(-45)))
    ca, sa = math.cos(math.radians(-45)), math.sin(math.radians(-45))
    k = 0
    for row in range(6):
        for i in range(40):
            if rng.random() < 0.18:
                continue
            u, v = -w / 2 + 2 + i * 2.9, -h / 2 + 5 + row * 10.0
            x, y = cx + u * ca - v * sa, cy + u * sa + v * ca
            o = rh.link(bpy.data.objects.new("Car_%d" % k, meshes[int(rng.integers(len(meshes)))]))
            o.location, o.rotation_euler, o.scale = (x, y, gz + 0.75), (0, 0, math.radians(45)), (1.8, 4.4, 1.4)
            k += 1
    pv = rh.material("PV", (0.02, 0.03, 0.08), rough=0.15, metal=0.3)
    for row in range(10):                                   # 150 kW solar field to the north
        rh.box("PVRow", (90.0, 3.6, 0.08), (-20.0, FIELD_OUT + 40.0 + row * 7.0, gz + 1.6), pv, (math.radians(-30), 0, 0))
    shuttle = rh.material("Shuttle", (0.9, 0.9, 0.86), rough=0.4)
    for a, rr in ((AXES[3], 90.0), (AXES[3], 120.0), (AXES[0], 100.0), (AXES[2], 70.0)):
        x, y = rr * math.cos(a), rr * math.sin(a)
        rh.box("Shuttle", (2.0, 5.5, 2.2), (x + 1.5 * math.sin(a), y - 1.5 * math.cos(a), rh.ground_z(T, z, x, y) + 1.2),
               shuttle, (0, 0, a + math.pi / 2))


def add_turbines(T):
    """Three mid-size turbines on their own towers on the outer road (option in tools/destination.py)."""
    white = rh.material("Turbine", (0.85, 0.85, 0.84), rough=0.4)
    gz = float(np.median(T.z0))
    hub_h, blade = 37.0, 14.0
    for k_t, a in enumerate((math.radians(215), math.radians(325), math.radians(90))):
        rr = FIELD_OUT + 8.0
        x, y = rr * math.cos(a), rr * math.sin(a)
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=1.3, radius2=0.7, depth=hub_h)
        o = rh.mesh_obj("Tower", bm, white, smooth=True)
        o.location = (x, y, gz + hub_h / 2)
        face = math.atan2(-235.0 - y, 0.0 - x)              # rotor turned towards the camera side (south)
        rotor = rh.link(bpy.data.objects.new("Rotor_%d" % k_t, None))
        rotor.location = (x + 2.4 * math.cos(face), y + 2.4 * math.sin(face), gz + hub_h + 0.6)
        rotor.rotation_euler = (0, 0, face)
        rh.box("Nacelle", (4.5, 2.0, 2.0), (x + 0.8 * math.cos(face), y + 0.8 * math.sin(face), gz + hub_h + 0.6),
               white, (0, 0, face))
        for k in range(3):
            t = 2 * math.pi * k / 3 + 0.3 * k_t
            o = rh.box("Blade", (0.3, 0.9, blade), (0, 0, 0), white)
            o.parent = rotor
            o.location = (0.0, -math.sin(t) * blade / 2, math.cos(t) * blade / 2)
            o.rotation_euler = (t, 0, 0)


def add_woods(T, rng):
    meshes = rh.tree_mesh()
    gz = float(np.median(T.z0))
    for i in range(260):
        a = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(205, 260)
        x, y = rr * math.cos(a), rr * math.sin(a)
        if 70 < x < 190 and 70 < y < 190:
            continue
        o = rh.link(bpy.data.objects.new("Wood_%d" % i, meshes[int(rng.random() < 0.55)]))
        s = rng.uniform(2.5, 4.0)
        o.scale = (s, s, s)
        o.location = (x, y, gz)


def main():
    a = args()
    cfg = load_config(rh.PARAMS, ['site={"type": "flat"}', 'soil.preset="ne_glacial_till"', 'soil.canal_side_slope_deg=26.57',
                                  'hub={"radius_m": 36.0}', 'moats=[{"r_in": 40.0, "r_out": 62.0, "depth": 2.44}]',
                                  'berms=[{"r_in": 66.0, "r_out": 80.0, "height": 0.9, "source_moat": 0}]',
                                  'grid.extent_m=170.0', "grid.resolution=%d" % a.res])
    rh.clear()
    rng = np.random.default_rng(11)
    T, z = build_terrain(cfg)
    add_water(T)
    add_roads(T, z)
    add_island(T, z)
    add_dome(T, z)
    add_stalls(T, z, rng)
    add_people(T, z, rng)
    add_parking_solar(T, z, rng)
    add_woods(T, rng)
    if a.turbines:
        add_turbines(T)
    rh.lights_world()
    os.makedirs(a.out, exist_ok=True)
    views = a.views.split(",")
    if "aerial" in views:
        rh.render(rh.camera("Aerial", (0, -250, 125), (0, 5, 0), lens=26),
                  os.path.join(a.out, "destination-aerial.png"), 1600, 900, a.samples)
    if "plan" in views:
        rh.render(rh.camera("Plan", (0, 0, 600), (0, 0.001, 0), ortho=360),
                  os.path.join(a.out, "destination-plan.png"), 1200, 1200, a.samples)
    if "plaza" in views:
        rh.render(rh.camera("Plaza", (-52, -78, 22), (0, 0, 6), lens=32),
                  os.path.join(a.out, "destination-plaza.png"), 1600, 900, a.samples)


if __name__ == "__main__":
    main()
