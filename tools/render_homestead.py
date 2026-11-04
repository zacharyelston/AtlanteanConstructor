"""Render the Atlantean homestead in Blender from the real design (homestead_params.json).

    /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/render_homestead.py -- \
        --out docs/img --views aerial,plan,island [--site flat] [--res 360] [--exaggeration 1.5]

The ground, rings, berms and water levels come straight from terrain_engine.Terrain, so the
picture changes when the design does. The buildings, hoops, trees, spoke and solar array are
simple stand-ins placed by the rules in docs/simple-build.md and docs/energy.md.
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "ring_engine"))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import terrain_engine as te  # noqa: E402
from config import load_config  # noqa: E402

PARAMS = os.path.join(ROOT, "ring_engine", "homestead_params.json")

# Zone colours (linear RGB)
C = {
    "field": (0.085, 0.15, 0.035), "grass": (0.10, 0.17, 0.04), "crown": (0.06, 0.15, 0.03),
    "pasture": (0.13, 0.18, 0.05), "gravel": (0.36, 0.33, 0.29), "mud": (0.05, 0.04, 0.03),
    "court": (0.30, 0.24, 0.16), "bank": (0.11, 0.16, 0.045),
}


def args_after_dashes():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=os.path.join(ROOT, "docs", "img"))
    p.add_argument("--views", default="aerial,plan,island")
    p.add_argument("--site", choices=["slope", "flat"], default="slope")
    p.add_argument("--res", type=int, default=520)
    p.add_argument("--exaggeration", type=float, default=1.5)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--prefix", default="homestead")
    p.add_argument("--tunnels", type=int, default=0, help="high tunnels on the pasture berm, from the south arc")
    return p.parse_args(argv)


# ----------------------------------------------------------------------------- helpers
def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.lights, bpy.data.cameras):
        for b in list(coll):
            if b.users == 0:
                coll.remove(b)


def material(name, rgb, rough=0.8, metal=0.0, emission=None, use_attr=None, noise=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    te.ensure_nodes(m)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if use_attr:
        a = nt.nodes.new("ShaderNodeAttribute")
        a.attribute_name = use_attr
        src = a.outputs["Color"]
        if noise:
            n = nt.nodes.new("ShaderNodeTexNoise")
            n.inputs["Scale"].default_value = 0.35
            n.inputs["Detail"].default_value = 6.0
            tc = nt.nodes.new("ShaderNodeTexCoord")
            nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.inputs["To Min"].default_value = 1.0 - noise
            mr.inputs["To Max"].default_value = 1.0 + noise
            nt.links.new(n.outputs["Fac"], mr.inputs["Value"])
            vm = nt.nodes.new("ShaderNodeVectorMath")
            vm.operation = "SCALE"
            nt.links.new(src, vm.inputs[0])
            nt.links.new(mr.outputs["Result"], vm.inputs["Scale"])
            src = vm.outputs["Vector"]
            bump = nt.nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = 0.25
            n2 = nt.nodes.new("ShaderNodeTexNoise")
            n2.inputs["Scale"].default_value = 6.0
            nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
            nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        nt.links.new(src, b.inputs["Base Color"])
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
    if hasattr(m, "use_backface_culling"):
        m.use_backface_culling = False
    m.diffuse_color = (*rgb, 1)
    return m


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mesh_obj(name, bm, mat=None, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    o = link(bpy.data.objects.new(name, me))
    if mat:
        o.data.materials.append(mat)
    return o


def box(name, size, loc, mat, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    o = mesh_obj(name, bm, mat)
    o.location = loc
    o.rotation_euler = rot
    return o


def annulus(name, r0, r1, z, mat, seg=256):
    bm = bmesh.new()
    outer = [bm.verts.new((r1 * math.cos(2 * math.pi * i / seg), r1 * math.sin(2 * math.pi * i / seg), z))
             for i in range(seg)]
    inner = [bm.verts.new((r0 * math.cos(2 * math.pi * i / seg), r0 * math.sin(2 * math.pi * i / seg), z))
             for i in range(seg)]
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((outer[i], outer[j], inner[j], inner[i]))     # counter-clockwise from above: faces up
    return mesh_obj(name, bm, mat)


# ----------------------------------------------------------------------------- terrain
def build_terrain(cfg, ex):
    T = te.Terrain(cfg)
    z = T.design.copy()
    R = T.R
    # island pad raised up to 1 m with spoil, tapering to the inner ring's bank
    island = np.clip((cfg.hub_radius - 2.0 - R) / 2.0, 0.0, 1.0)
    z = np.maximum(z, np.where(R < cfg.hub_radius - 0.5, T.z0 + 1.0 * island, z))
    # windbreak bund of surplus spoil, along the north-west border
    az = np.degrees(np.arctan2(T.Y, T.X)) % 360
    in_arc = np.clip(1.0 - np.abs(az - 140.0) / 45.0, 0.0, 1.0)
    bund = 2.5 * np.exp(-((R - 86.0) / 3.5) ** 2) * np.sqrt(in_arc)
    z = np.where(bund > 0.01, np.maximum(z, T.z0 + bund), z)
    # causeway on the uphill side (site.uphill_azimuth_deg), above every waterline
    up = math.radians((cfg.site or {}).get("uphill_azimuth_deg", 30.0))
    along = T.X * math.cos(up) + T.Y * math.sin(up)
    across = np.abs(-T.X * math.sin(up) + T.Y * math.cos(up))
    span = (along > cfg.hub_radius - 4) & (along < cfg.r_max + 4)
    wl_max = max(w for w in T.water_levels if w is not None)
    top = np.maximum(T.z0 + 0.5, wl_max + 0.6)
    bank = top - np.clip(across - 3.0, 0.0, None) / 3.0              # 3:1 embankment sides
    road = span & (across < 3.0)
    z = np.where(span, np.maximum(z, bank), z)

    # zone colours
    rgb = np.empty(z.shape + (3,))
    rgb[:] = C["field"]
    delta = T.design - T.z0
    for k, b in enumerate(cfg.berms):
        bm_ = T.berm_id == k
        rgb[bm_] = C["bank"]
        crown = bm_ & (delta >= 0.95 * max(delta[bm_].max(), 1e-6))
        rgb[crown] = C["crown"] if k == 0 else C["pasture"]
        mid = 0.5 * (b.r_in + b.r_out)
    moat = T.moat_id >= 0
    rgb[moat] = C["bank"]
    for m, wl in enumerate(T.water_levels):
        rgb[(T.moat_id == m) & (z < wl - 0.05)] = C["mud"]              # only what stays under water
    rgb[R < cfg.hub_radius - 2.5] = C["grass"]
    rgb[R < 9.5] = C["court"]
    rgb[road] = C["bank"]
    rgb[bund > 0.3] = C["grass"]

    # a wide field around the modelled area hides its square edge
    edge = np.concatenate([z[0], z[-1], z[:, 0], z[:, -1]])
    zf = (edge.min() - 0.02) * ex
    e, far = T.extent - 0.3, 1500.0
    bm = bmesh.new()
    vin = [bm.verts.new(c) for c in ((-e, -e, zf), (e, -e, zf), (e, e, zf), (-e, e, zf))]
    vout = [bm.verts.new(c) for c in ((-far, -far, zf), (far, -far, zf), (far, far, zf), (-far, far, zf))]
    for i in range(4):                                  # a square frame around the terrain, not under it
        j = (i + 1) % 4
        bm.faces.new((vout[i], vout[j], vin[j], vin[i]))
    mesh_obj("FieldFar", bm, material("FieldFar", C["field"], rough=0.95))
    obj, co = te.build_blender_mesh(T, "Ground")
    te.update_blender_mesh(obj, co, z, rgb)
    obj.scale = (1, 1, ex)
    obj.data.materials.append(material("Ground", (0.2, 0.3, 0.1), rough=0.95, use_attr=te.COLOR_ATTR, noise=0.22))
    return T, z, obj


def ground_z(T, z, x, y):
    return T._bilinear(z, x, y)


def drape_annulus(T, z, ex, name, r0, r1, mat, lift=0.07, seg=720, rings=3, skip=None):
    """A ring of surface (path, road) laid over the ground, with crisp edges."""
    bm = bmesh.new()
    grid = []
    for i in range(seg):
        t = 2 * math.pi * i / seg
        row = []
        for j in range(rings):
            r = r0 + (r1 - r0) * j / (rings - 1)
            x, y = r * math.cos(t), r * math.sin(t)
            row.append(bm.verts.new((x, y, ground_z(T, z, x, y) * ex + lift)))
        grid.append(row)
    for i in range(seg):
        k = (i + 1) % seg
        t = 2 * math.pi * (i + 0.5) / seg
        if skip and abs(math.atan2(math.sin(t - skip[0]), math.cos(t - skip[0]))) < skip[1]:
            continue
        for j in range(rings - 1):
            bm.faces.new((grid[i][j], grid[k][j], grid[k][j + 1], grid[i][j + 1]))
    return mesh_obj(name, bm, mat)


def drape_strip(T, z, ex, name, az, r0, r1, half_w, mat, lift=0.08, step=0.5):
    """A straight road; each cross-section is level at its centreline height."""
    bm = bmesh.new()
    ca, sa = math.cos(az), math.sin(az)
    rows = []
    n = int((r1 - r0) / step) + 1
    for i in range(n):
        r = r0 + (r1 - r0) * i / (n - 1)
        h = ground_z(T, z, r * ca, r * sa) * ex + lift
        row = []
        for w in (-half_w, 0.0, half_w):
            x, y = r * ca - w * sa, r * sa + w * ca
            row.append(bm.verts.new((x, y, h)))
        rows.append(row)
    for i in range(n - 1):
        for j in range(2):
            bm.faces.new((rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j]))
    return mesh_obj(name, bm, mat)


def add_paths(T, z, cfg, ex):
    gravel = material("Gravel", C["gravel"], rough=0.95)
    up = math.radians((cfg.site or {}).get("uphill_azimuth_deg", 30.0))
    for k, b in enumerate(cfg.berms):                       # a path along each berm crown's outer edge
        r = b.r_out - 0.9 * 3.0 - 1.2
        drape_annulus(T, z, ex, "Path_%d" % k, r - 0.8, r + 0.8, gravel)
    drape_annulus(T, z, ex, "PerimeterRoad", cfg.r_max + 2.0, cfg.r_max + 4.5, gravel)
    drape_strip(T, z, ex, "Causeway", up, cfg.hub_radius - 6.0, cfg.r_max + 3.0, 2.6, gravel)
    drape_annulus(T, z, ex, "Courtyard", 0.0, 9.0, gravel, lift=0.05, rings=6)
    pipe = material("Culvert", (0.05, 0.05, 0.05), rough=0.6)
    for m in range(len(cfg.moats)):
        lo, hi = T.zone_extent("moat", m)
        for rr in (lo + 0.6, hi - 0.6):
            x, y = rr * math.cos(up), rr * math.sin(up)
            g = T.water_levels[m] * ex + 0.25
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.45, radius2=0.45, depth=6.0)
            o = mesh_obj("Culvert", bm, pipe)
            o.location = (x, y, g)
            o.rotation_euler = (math.pi / 2, 0, up)


# ----------------------------------------------------------------------------- features
def add_water(T, cfg, ex):
    water = material("Water", (0.008, 0.04, 0.05), rough=0.05)
    wb = water.node_tree.nodes.get("Principled BSDF")
    for name, val in (("IOR", 1.33), ("Specular IOR Level", 0.22)):
        if name in wb.inputs:
            wb.inputs[name].default_value = val
    for m, wl in enumerate(T.water_levels):
        lo, hi = T.zone_extent("moat", m)
        o = annulus("Water_%d" % m, lo - 0.5, hi + 0.5, wl * ex, water)
        o.location.z = 0.0


def geodesic(name, radius, loc, mat, edge_mat, rot=0.0):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.05], context="VERTS")
    shell = mesh_obj(name, bm, mat)
    shell.location = loc
    shell.rotation_euler = (0, 0, rot)
    frame = shell.copy()
    frame.data = shell.data.copy()
    frame.data.materials.clear()
    frame.data.materials.append(edge_mat)
    w = frame.modifiers.new("struts", "WIREFRAME")
    w.thickness = 0.07
    w.use_replace = True
    link(frame)
    frame.name = name + "_struts"
    door = box(name + "_door", (1.0, 0.3, 2.1), (0, 0, 0), edge_mat)
    door.parent = shell
    door.location = (0, -radius * 0.97, 1.05)
    return shell


def add_buildings(T, z, cfg, ex):
    white = material("DomeShell", (0.80, 0.79, 0.74), rough=0.35)
    tan = material("DomeShellTan", (0.70, 0.60, 0.42), rough=0.45)
    struts = material("DomeStruts", (0.25, 0.25, 0.25), rough=0.5, metal=0.4)
    names = [("House", 5.2, white), ("Barn", 5.0, tan), ("Workshop", 4.8, white)]  # three domes, one courtyard
    for i, (n, r, mt) in enumerate(names):
        a = math.radians(90 + 120 * i + 15)
        x, y = 7.6 * math.cos(a), 7.6 * math.sin(a)
        g = ground_z(T, z, x, y) * ex
        geodesic(n, r, (x, y, g), mt, struts, rot=a + math.pi / 2)


def hoop_data():
    cu = bpy.data.curves.new("Hoop", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.025
    sp = cu.splines.new("POLY")
    pts = [(1.4 * math.cos(t), 0.0, 1.25 * math.sin(t)) for t in np.linspace(0, math.pi, 13)]
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1.0)
    return cu


def add_hoops_and_crops(T, z, cfg, ex):
    metal = material("Hoops", (0.75, 0.75, 0.74), rough=0.3, metal=0.9)
    crop = material("Crops", (0.05, 0.17, 0.025), rough=0.9)
    cu = hoop_data()
    cu.materials.append(metal)
    b = cfg.berms[0]
    r = 0.5 * (b.r_in + b.r_out)
    gz = np.median([ground_z(T, z, r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, 6.28, 36)])
    # crop bed under the hoops along the orchard crown centre
    bed = annulus("CropBed", r - 1.2, r + 1.2, 0, crop)
    n = int(2 * math.pi * r / 2.5)
    up = math.radians((cfg.site or {}).get("uphill_azimuth_deg", 30.0))
    for i in range(n):
        t = 2 * math.pi * i / n
        if abs(math.atan2(math.sin(t - up), math.cos(t - up))) < 0.12:     # leave the causeway gap
            continue
        x, y = r * math.cos(t), r * math.sin(t)
        o = link(bpy.data.objects.new("Hoop_%d" % i, cu))
        o.location = (x, y, ground_z(T, z, x, y) * ex + 0.05)
        o.rotation_euler = (0, 0, t)
    # drape the crop bed on the ground
    for v in bed.data.vertices:
        v.co.z = ground_z(T, z, v.co.x, v.co.y) * ex + 0.12
    del gz


def tree_mesh():
    leaf = material("Leaves", (0.07, 0.20, 0.035), rough=0.85)
    autumn = material("LeavesAutumn", (0.40, 0.18, 0.03), rough=0.85)
    bark = material("Bark", (0.12, 0.08, 0.05), rough=0.9)
    out = []
    for name, lm in (("Tree", leaf), ("TreeAutumn", autumn)):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.5)
        for v in bm.verts:
            v.co.z = v.co.z * 0.85 + 2.4
        trunk = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.16, radius2=0.12, depth=1.6)
        for v in trunk["verts"]:
            v.co.z += 0.8
        for f in bm.faces:
            f.material_index = 1 if f.calc_center_median().z < 1.0 else 0
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(lm)
        me.materials.append(bark)
        out.append(me)
    return out


def add_trees(T, z, cfg, ex):
    meshes = tree_mesh()
    rng = np.random.default_rng(3)
    b = cfg.berms[0]
    up = math.radians((cfg.site or {}).get("uphill_azimuth_deg", 30.0))
    k = 0
    for r in (b.r_in + 2.2, b.r_out - 2.2):                    # orchard on both water edges
        n = int(2 * math.pi * r / 6.0)
        for i in range(n):
            t = 2 * math.pi * (i + 0.5 * (r > 35)) / n
            if abs(math.atan2(math.sin(t - up), math.cos(t - up))) < 0.15:
                continue
            x, y = r * math.cos(t), r * math.sin(t)
            o = link(bpy.data.objects.new("Tree_%d" % k, meshes[int(rng.random() < 0.2)]))
            s = rng.uniform(0.8, 1.15)
            o.scale = (s, s, s)
            o.location = (x, y, ground_z(T, z, x, y) * ex)
            k += 1
    # woodland edge far outside, for scale
    for i in range(90):
        t = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(96, 108)
        x, y = rr * math.cos(t), rr * math.sin(t)
        if abs(x) > T.extent - 2 or abs(y) > T.extent - 2:
            continue
        o = link(bpy.data.objects.new("Wood_%d" % i, meshes[int(rng.random() < 0.6)]))
        s = rng.uniform(1.6, 2.6)
        o.scale = (s, s, s)
        o.location = (x, y, ground_z(T, z, x, y) * ex)


def add_tunnels(T, z, cfg, ex, n):
    """24 x 72 ft gothic high tunnels on the pasture berm crown (docs/greenhouse.md). The first ones sit on
    the south arc, where the ring runs east-west: the best orientation for winter light."""
    if n <= 0:
        return
    poly = material("TunnelPoly", (0.92, 0.94, 0.95), rough=0.3, alpha=0.45)
    pb = poly.node_tree.nodes.get("Principled BSDF")
    if "Transmission Weight" in pb.inputs:
        pb.inputs["Transmission Weight"].default_value = 0.5
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(poly, attr, val)
        except (AttributeError, TypeError):
            pass
    crop = material("TunnelCrop", (0.06, 0.20, 0.03), rough=0.9)
    b = cfg.berms[1]
    rc = 0.5 * (b.r_in + b.r_out)
    hw, h, wall, L = 0.5 * 24 * 0.3048, 12 * 0.3048, 0.9, 72 * 0.3048
    step = (L + 3.0) / rc                                         # angular spacing
    order = [0]
    for i in range(1, n):
        order.append(((i + 1) // 2) * (1 if i % 2 else -1))       # 0, +1, -1, +2, -2 ... around the south
    prof = [(hw * math.cos(t), wall + (h - wall) * math.sin(t)) for t in np.linspace(0, math.pi, 17)]
    prof = [(hw, 0.0)] + prof + [(-hw, 0.0)]
    for k, o in enumerate(order[:n]):
        a = math.radians(270) + o * step
        cx, cy = rc * math.cos(a), rc * math.sin(a)
        g = ground_z(T, z, cx, cy) * ex
        bm = bmesh.new()
        ends = []
        for yy in (-L / 2, L / 2):
            ends.append([bm.verts.new((px_, yy, pz)) for px_, pz in prof])
        for i in range(len(prof) - 1):
            bm.faces.new((ends[0][i], ends[0][i + 1], ends[1][i + 1], ends[1][i]))
        bm.faces.new(ends[0][::-1])
        bm.faces.new(ends[1])
        o_ = mesh_obj("Tunnel_%d" % k, bm, poly)
        o_.location = (cx, cy, g + 0.02)
        o_.rotation_euler = (0, 0, a)                             # long axis along the ring tangent
        for row in (-2.0, -0.7, 0.7, 2.0):                        # crop rows inside
            rx = cx + row * math.cos(a)
            ry = cy + row * math.sin(a)
            box("TunnelRow", (0.7, L - 2.0, 0.5), (rx, ry, g + 0.25), crop, (0, 0, a))


def add_spoke(T, z, cfg, ex):
    """Floating work spoke: island edge across the inner ring and orchard berm to the deep ring."""
    steel = material("Spoke", (0.55, 0.56, 0.58), rough=0.4, metal=0.8)
    float_m = material("Floats", (0.85, 0.85, 0.82), rough=0.5)
    a = math.radians(215)
    r0, r1 = cfg.hub_radius - 1.0, cfg.moats[1].r_in + 3.0
    wl = max(w for w in T.water_levels if w is not None)
    h = (wl + 1.4) * ex
    mid = 0.5 * (r0 + r1)
    deck = box("SpokeDeck", (r1 - r0, 1.3, 0.12), (mid * math.cos(a), mid * math.sin(a), h), steel, (0, 0, a))
    for side in (-0.65, 0.65):
        box("SpokeRail", (r1 - r0, 0.05, 0.05), (mid * math.cos(a) - side * math.sin(a),
                                                 mid * math.sin(a) + side * math.cos(a), h + 1.0), steel, (0, 0, a))
    for rr in (0.5 * (cfg.moats[0].r_in + cfg.moats[0].r_out), r1 - 1.0):
        m = 0 if rr < 30 else 1
        box("SpokeFloat", (2.0, 2.6, 0.7), (rr * math.cos(a), rr * math.sin(a), T.water_levels[m] * ex + 0.2),
            float_m, (0, 0, a))
        box("SpokeLeg", (0.12, 0.12, h - T.water_levels[m] * ex), (rr * math.cos(a), rr * math.sin(a),
                                                                    0.5 * (h + T.water_levels[m] * ex)), steel)
    del deck


def add_solar(T, z, cfg, ex):
    pv = material("PV", (0.02, 0.03, 0.07), rough=0.15, metal=0.3)
    frame = material("PVFrame", (0.6, 0.6, 0.6), rough=0.4, metal=0.8)
    tilt = math.radians(35)
    n = 0
    for row, y in enumerate((cfg.r_max + 9.0, cfg.r_max + 14.0, cfg.r_max + 19.0)):
        for i in range(13):
            x = (i - 6) * 1.1
            g = ground_z(T, z, x, y) * ex
            box("PV_%d" % n, (1.05, 1.95, 0.04), (x, y, g + 1.2), pv, (-tilt, 0, 0))
            box("PVPost_%d" % n, (0.06, 0.06, 1.2), (x, y + 0.5, g + 0.6), frame)
            n += 1


def add_eox(T, z, cfg, ex):
    body = material("eOx", (0.85, 0.55, 0.05), rough=0.5)
    tyre = material("Tyre", (0.03, 0.03, 0.03), rough=0.9)
    r = cfg.r_max + 3.0
    for k, t in enumerate((math.radians(300), math.radians(120))):
        x, y = r * math.cos(t), r * math.sin(t)
        g = ground_z(T, z, x, y) * ex
        box("eOx_%d" % k, (2.2, 1.1, 0.7), (x, y, g + 0.75), body, (0, 0, t + math.pi / 2))
        for dx in (-0.75, 0.75):
            for dy in (-0.6, 0.6):
                lx = dx * math.cos(t + math.pi / 2) - dy * math.sin(t + math.pi / 2)
                ly = dx * math.sin(t + math.pi / 2) + dy * math.cos(t + math.pi / 2)
                box("eOxWheel", (0.46, 0.22, 0.46), (x + lx, y + ly, g + 0.23), tyre, (0, 0, t + math.pi / 2))


def lights_world():
    sun = link(bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")))
    sun.data.energy = 4.0
    sun.data.angle = math.radians(1.5)
    sun.data.color = (1.0, 0.92, 0.80)
    sun.rotation_euler = (math.radians(62), 0, math.radians(-50))     # low autumn afternoon sun
    w = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    te.ensure_nodes(w)
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs["Strength"].default_value = 1.0
    sky = nt.nodes.new("ShaderNodeTexSky")
    ok = False
    for kind in ("NISHITA", "MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "HOSEK_WILKIE"):
        try:
            sky.sky_type = kind
            ok = True
            break
        except TypeError:
            continue
    if ok:
        for attr, val in (("sun_elevation", math.radians(22)), ("sun_rotation", math.radians(220)),
                          ("altitude", 300.0), ("air_density", 1.2), ("dust_density", 2.0)):
            if hasattr(sky, attr):
                setattr(sky, attr, val)
        if hasattr(sky, "sun_disc"):
            sky.sun_disc = False
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.35
    else:
        bg.inputs["Color"].default_value = (0.45, 0.58, 0.82, 1)


def camera(name, loc, target, lens=35, ortho=None):
    cam = link(bpy.data.objects.new(name, bpy.data.cameras.new(name)))
    cam.data.lens = lens
    cam.data.clip_end = 2000
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    cam.location = loc
    t = link(bpy.data.objects.new(name + "_target", None))
    t.location = target
    c = cam.constraints.new("TRACK_TO")
    c.target = t
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    return cam


def render(cam, path, w, h, samples):
    sc = bpy.context.scene
    sc.camera = cam
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    try:
        sc.eevee.taa_render_samples = samples
    except AttributeError:
        pass
    for attr, val in (("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
        if hasattr(sc.eevee, attr):
            setattr(sc.eevee, attr, val)
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[render] " + path)


def main():
    a = args_after_dashes()
    ov = ["grid.resolution=%d" % a.res, "grid.extent_m=110.0"]
    if a.site == "flat":
        ov.append('site={"type": "flat"}')
    cfg = load_config(PARAMS, ov)
    clear()
    T, z, _ = build_terrain(cfg, a.exaggeration)
    ex = a.exaggeration
    add_water(T, cfg, ex)
    add_buildings(T, z, cfg, ex)
    add_paths(T, z, cfg, ex)
    add_hoops_and_crops(T, z, cfg, ex)
    add_trees(T, z, cfg, ex)
    add_spoke(T, z, cfg, ex)
    add_tunnels(T, z, cfg, ex, a.tunnels)
    add_solar(T, z, cfg, ex)
    add_eox(T, z, cfg, ex)
    lights_world()
    os.makedirs(a.out, exist_ok=True)
    views = a.views.split(",")
    if "aerial" in views:
        render(camera("Aerial", (55, -125, 78), (0, 6, -4), lens=30),
               os.path.join(a.out, "%s-aerial.png" % a.prefix), 1600, 900, a.samples)
    if "plan" in views:
        render(camera("Plan", (0, 0, 400), (0, 0.001, 0), ortho=200),
               os.path.join(a.out, "%s-plan.png" % a.prefix), 1200, 1200, a.samples)
    if "tunnels" in views:
        render(camera("Tunnels", (34, -94, 16), (-4, -66, 1), lens=32),
               os.path.join(a.out, "%s-tunnels.png" % a.prefix), 1600, 900, a.samples)
    if "island" in views:
        render(camera("Island", (-34, -52, 18), (-2, 2, 2), lens=30),
               os.path.join(a.out, "%s-island.png" % a.prefix), 1600, 900, a.samples)


main()
