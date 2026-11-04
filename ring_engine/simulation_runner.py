"""Atlantean Berm & Ring Engine - main simulation loop.

Headless (plain Python + NumPy):
    python3 simulation_runner.py [--res 256] [--set rig.lifts=4] [--out output]

Inside Blender 4.x / 5.x (builds the scene, bakes the sim, animates it):
    blender --python simulation_runner.py
    blender -b --python simulation_runner.py -- --render-still out.png --still-frame 200
    blender -b --python simulation_runner.py -- --render-anim /tmp/frames/ --save-blend rings.blend
"""
import argparse
import csv
import importlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

import config as _config  # noqa: E402
import kinematics as _kin  # noqa: E402
import terrain_engine as _te  # noqa: E402

for _mod in (_config, _te, _kin):   # pick up edits when re-run inside one Blender session
    importlib.reload(_mod)

from config import load_config  # noqa: E402
from kinematics import build_trajectory  # noqa: E402
from terrain_engine import Terrain, write_png  # noqa: E402


# --------------------------------------------------------------------------
# Simulation core
# --------------------------------------------------------------------------
class Simulation:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        t0 = time.time()
        self.terrain = Terrain(cfg)
        self.traj = build_trajectory(cfg, self.terrain.berm_heights)
        self.log("[init] grid %dx%d (dx=%.2f m), %d trajectory samples, %d lifts, setup %.1fs"
                 % (cfg.resolution, cfg.resolution, self.terrain.dx, len(self.traj), cfg.lifts,
                    time.time() - t0))
        for w in cfg.warnings:
            self.log("[warn] " + w)

        self.bucket = 0.0          # loose m3 currently in the bucket / on the conveyor
        self.v_cut_bank = 0.0      # in-situ m3 excavated
        self.v_recut_loose = 0.0   # loose m3 re-scraped (slumped spoil)
        self.v_deposited = 0.0     # loose m3 discharged onto berms
        self.t_elapsed = 0.0       # s, production-limited
        self.t_kinematic = 0.0     # s, pure motion
        self.step_index = 0
        self.discharging = False
        self.telemetry = []

    # ---------------------------------------------------------------- state
    @property
    def v_fill(self):
        """Loose spoil in place on the ground (m3)."""
        return self.v_deposited - self.v_recut_loose

    def state(self, frame=None):
        i = min(self.step_index, len(self.traj) - 1)
        tr, T, cfg = self.traj, self.terrain, self.cfg
        th, r, rd = float(tr.theta[i]), float(tr.r[i]), float(tr.r_dump[i])
        c, s = math.cos(th), math.sin(th)
        L = cfg.r_max + 5.0
        cut = self.v_cut_bank
        return {
            "frame": frame, "step": i, "t_s": self.t_elapsed, "t_kin_s": self.t_kinematic,
            "theta_rad": th, "theta_deg": math.degrees(th) % 360.0, "revolutions": th / (2 * math.pi),
            "r_m": r, "r_dump_m": rd, "lift": int(tr.lift[i]), "moat": int(tr.moat[i]),
            "active": bool(tr.active[i]),
            "z_head": T.sample_z(r * c, r * s), "z_dump": T.sample_z(rd * c, rd * s),
            "z_end": T.sample_z(L * c, L * s),
            "V_cut_bank_m3": cut, "V_loose_generated_m3": cut * cfg.swell_factor,
            "V_fill_m3": self.v_fill, "V_bucket_m3": self.bucket,
            "fill_cut_ratio": self.v_fill / cut if cut > 0 else 0.0,
            "balance_error_m3": self.v_fill + self.bucket - cfg.swell_factor * cut,
            "discharging": self.discharging,
        }

    # ----------------------------------------------------------------- loop
    def run(self, n_frames=None, on_frame=None, progress_every=0.1):
        cfg, T, tr = self.cfg, self.terrain, self.traj
        S = len(tr)
        F = max(2, n_frames or cfg.frames)
        frame_steps = np.round(np.linspace(0, S - 1, F - 1)).astype(int)
        next_frame = 0
        sf, fp, cr = cfg.swell_factor, cfg.footprint_radius, cfg.chute_radius
        cap, K = cfg.bucket_capacity, cfg.lifts
        rate = (cfg.production_rate_m3_hr or 0.0) / 3600.0
        theta, rad, rdump = tr.theta, tr.r, tr.r_dump
        active, berm, lift, dt_kin = tr.active, tr.berm, tr.lift, tr.dt_kin
        prev_lift = 1
        report_at = max(1, int(S * progress_every)) if progress_every else S + 1
        t_wall = time.time()

        for i in range(S):
            self.step_index = i
            th = theta[i]
            c, s = math.cos(th), math.sin(th)
            lf = lift[i] / K
            if lift[i] != prev_lift:             # settle the whole site between lifts
                T.relax(iters=10)
                prev_lift = lift[i]

            bank_rm = 0.0
            if active[i]:
                r = rad[i]
                bank_rm, loose_rm = T.cut_at(r * c, r * s, fp, lf, cap - self.bucket)
                self.bucket += loose_rm + sf * bank_rm
                self.v_cut_bank += bank_rm
                self.v_recut_loose += loose_rm

            self.discharging = False
            if self.bucket > 1e-9:
                rd = rdump[i]
                dep = T.deposit_at(rd * c, rd * s, cr, int(berm[i]), lf, self.bucket)
                if self.bucket - dep > 0.5 * cap:   # local crown full: spread the chute wider
                    dep += T.deposit_at(rd * c, rd * s, 2.5 * cr, int(berm[i]), 1.0,
                                        self.bucket - dep)
                if dep > 0.0:
                    self.bucket -= dep
                    self.v_deposited += dep
                    self.discharging = True
            if cfg.relax_every and i % cfg.relax_every == 0:
                rd = rdump[i]
                T.relax_near(rd * c, rd * s, cfg.relax_window, iters=3)

            self.t_kinematic += dt_kin[i]
            self.t_elapsed += max(dt_kin[i], bank_rm / rate if rate > 0 else 0.0)

            while next_frame < len(frame_steps) and frame_steps[next_frame] == i:
                st = self.state(next_frame)
                self.telemetry.append(st)
                if on_frame:
                    on_frame(next_frame, self, st)
                next_frame += 1

            if (i + 1) % report_at == 0:
                st = self.state()
                self.log("[%5.1f%%] lift %d/%d  theta=%7.1f deg  r=%6.1f m  cut=%9.0f m3  "
                         "fill=%9.0f m3  bucket=%5.1f m3  F/C=%.3f  t=%6.1f h  (%.1fs)"
                         % (100.0 * (i + 1) / S, st["lift"], K, st["theta_deg"], st["r_m"],
                            st["V_cut_bank_m3"], st["V_fill_m3"], st["V_bucket_m3"],
                            st["fill_cut_ratio"], st["t_s"] / 3600.0, time.time() - t_wall))

        # Final dressing: empty the bucket, settle all slopes.
        placed = T.cleanup_deposit(self.bucket)
        self.v_deposited += placed
        self.bucket -= placed
        T.relax(iters=30)
        self.discharging = False
        st = self.state(F - 1)
        self.telemetry.append(st)
        if on_frame:
            on_frame(F - 1, self, st)
        self.wall_time = time.time() - t_wall
        return self.report()

    # --------------------------------------------------------------- report
    def report(self):
        cfg, T = self.cfg, self.terrain
        vol = T.volumes()
        cut = self.v_cut_bank
        return {
            "inputs": {
                "swell_factor": cfg.swell_factor, "angle_of_repose_deg": cfg.repose_deg,
                "canal_side_slope_deg": cfg.canal_slope_deg, "grid_resolution": cfg.resolution,
                "cell_size_m": T.dx, "lifts": cfg.lifts, "path_mode": cfg.path_mode,
            },
            "design": T.design_report,
            "design_totals": {
                "V_cut_bank_m3": T.design_cut_total,
                "V_fill_loose_m3": T.design_fill_total,
                "design_parity_ratio": T.design_fill_total / max(T.design_cut_total, 1e-9),
            },
            "achieved": {
                "V_cut_bank_m3": cut,
                "V_loose_generated_m3": cut * cfg.swell_factor,
                "V_fill_in_place_m3": self.v_fill,
                "V_bucket_residual_m3": self.bucket,
                "fill_cut_ratio": self.v_fill / cut if cut else 0.0,
                "target_ratio_Sf": cfg.swell_factor,
                "mass_balance_error_m3": self.v_fill + self.bucket - cfg.swell_factor * cut,
                "grid_check_bank_cut_m3": vol["bank_cut_grid_m3"],
                "grid_check_loose_m3": vol["loose_on_ground_m3"],
                "loose_on_berms_m3": vol["loose_on_berms_m3"],
                "loose_spilled_outside_berms_m3": vol["loose_spilled_m3"],
                "moat_completion_pct": vol["moat_completion_pct"],
                "moat_profile_rmse_m": vol["moat_rmse_m"],
                "berm_profile_rmse_m": vol["berm_rmse_m"],
            },
            "cycle_time": {
                "kinematic_path_time_h": self.t_kinematic / 3600.0,
                "production_limited_time_h": self.t_elapsed / 3600.0,
                "production_rate_m3_hr": cfg.production_rate_m3_hr,
                "v_theta_rad_s": cfg.v_theta, "v_r_m_s": cfg.v_r, "v_tool_max_m_s": cfg.v_tool_max,
                "total_revolutions": float(self.traj.theta[-1] / (2 * math.pi)),
                "trajectory_samples": len(self.traj),
            },
            "warnings": cfg.warnings,
        }


def hud_text(st, cfg):
    return ("ATLANTEAN BERM & RING ENGINE\n"
            "theta %6.1f deg  (rev %6.1f)   r %6.1f m   chute %6.1f m   lift %d/%d\n"
            "cut (bank) %10s m3    fill (loose) %10s m3    bucket %5.1f m3\n"
            "fill/cut %.3f  (target Sf %.2f)    elapsed %7.1f h"
            % (st["theta_deg"], st["revolutions"], st["r_m"], st["r_dump_m"], st["lift"], cfg.lifts,
               "{:,.0f}".format(st["V_cut_bank_m3"]), "{:,.0f}".format(st["V_fill_m3"]),
               st["V_bucket_m3"], st["fill_cut_ratio"], cfg.swell_factor, st["t_s"] / 3600.0))


def print_report(rep, log=print):
    d, a, c = rep["design_totals"], rep["achieved"], rep["cycle_time"]
    log("")
    log("=" * 72)
    log(" EARTHWORK SUMMARY")
    log("=" * 72)
    for m in rep["design"]["moats"]:
        log("  moat %d  r %5.1f-%5.1f m  depth %.2f m   V_bank %10s m3 (exact %s)"
            % (m["index"], m["r_in"], m["r_out"], m["depth"], "{:,.0f}".format(m["V_bank_grid_m3"]),
               "{:,.0f}".format(m["V_bank_exact_m3"])))
    for b in rep["design"]["berms"]:
        log("  berm %d  r %5.1f-%5.1f m  crown %.2f m   V_loose %9s m3 <- moat %d"
            % (b["index"], b["r_in"], b["r_out"], b["crown_height_m"],
               "{:,.0f}".format(b["V_design_grid_m3"]), b["source_moat"]))
    log("-" * 72)
    log("  design   cut %12s m3 bank   fill %12s m3 loose   ratio %.4f"
        % ("{:,.0f}".format(d["V_cut_bank_m3"]), "{:,.0f}".format(d["V_fill_loose_m3"]),
           d["design_parity_ratio"]))
    log("  achieved cut %12s m3 bank   fill %12s m3 loose   ratio %.4f (Sf %.2f)"
        % ("{:,.0f}".format(a["V_cut_bank_m3"]), "{:,.0f}".format(a["V_fill_in_place_m3"]),
           a["fill_cut_ratio"], a["target_ratio_Sf"]))
    log("  mass-balance error %.3e m3   bucket residual %.2f m3   spill outside berms %s m3"
        % (a["mass_balance_error_m3"], a["V_bucket_residual_m3"],
           "{:,.0f}".format(a["loose_spilled_outside_berms_m3"])))
    log("  moat completion %.1f%%   profile RMSE moat %.3f m / berm %.3f m"
        % (a["moat_completion_pct"], a["moat_profile_rmse_m"], a["berm_profile_rmse_m"]))
    log("  cycle time: %.1f h kinematic, %.1f h production-limited (%s m3/h), %.0f revolutions"
        % (c["kinematic_path_time_h"], c["production_limited_time_h"], c["production_rate_m3_hr"],
           c["total_revolutions"]))
    log("=" * 72)


# --------------------------------------------------------------------------
# Headless outputs
# --------------------------------------------------------------------------
def write_cross_section(terrain, path_csv, path_svg):
    rc, za, zd = terrain.radial_profile()
    with open(path_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["r_m", "z_achieved_mean_m", "z_design_m"])
        for row in zip(rc, za, zd):
            w.writerow(["%.3f" % v for v in row])
    W, H, pad = 1000, 320, 40
    zmin = min(za.min(), zd.min()) - 0.5
    zmax = max(za.max(), zd.max()) + 0.5
    sx = (W - 2 * pad) / rc[-1]
    sy = (H - 2 * pad) / (zmax - zmin)

    def pts(z):
        return " ".join("%.1f,%.1f" % (pad + r * sx, H - pad - (v - zmin) * sy) for r, v in zip(rc, z))
    y0 = H - pad - (0 - zmin) * sy
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="sans-serif" '
        'font-size="12">' % (W, H),
        '<rect width="100%" height="100%" fill="#faf8f3"/>',
        '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#999" stroke-dasharray="2,3"/>'
        % (pad, y0, W - pad, y0),
        '<polyline fill="none" stroke="#c2741f" stroke-width="2" points="%s"/>' % pts(za),
        '<polyline fill="none" stroke="#1f4e8c" stroke-width="1.5" stroke-dasharray="6,4" '
        'points="%s"/>' % pts(zd),
        '<text x="%d" y="20">Azimuthal-mean cross-section (vertical exaggeration %.1fx): '
        'solid = achieved, dashed = design</text>' % (pad, sy / sx),
        '<text x="%d" y="%d">r = 0</text>' % (pad, H - 10),
        '<text x="%d" y="%d" text-anchor="end">r = %.0f m</text>' % (W - pad, H - 10, rc[-1]),
        '<text x="%d" y="%.1f" text-anchor="end">z=0</text>' % (pad - 4, y0 + 4),
        "</svg>",
    ]
    with open(path_svg, "w") as fh:
        fh.write("\n".join(svg))


def write_telemetry(rows, path):
    if not rows:
        return
    keys = [k for k in rows[0].keys()]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run_headless(cfg, args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    sim = Simulation(cfg)
    hook = None
    if args.png_every:
        fdir = os.path.join(out, "frames")
        os.makedirs(fdir, exist_ok=True)

        def hook(f, s, st):
            if f % args.png_every == 0:
                write_png(os.path.join(fdir, "frame_%04d.png" % f), s.terrain.hillshade_rgb())
    rep = sim.run(on_frame=hook)
    print_report(rep)
    with open(os.path.join(out, "report.json"), "w") as fh:
        json.dump(rep, fh, indent=2)
    write_telemetry(sim.telemetry, os.path.join(out, "telemetry.csv"))
    write_png(os.path.join(out, "final_topdown.png"), sim.terrain.hillshade_rgb())
    write_png(os.path.join(out, "design_topdown.png"),
              sim.terrain.hillshade_rgb(sim.terrain.design))
    write_cross_section(sim.terrain, os.path.join(out, "cross_section.csv"),
                        os.path.join(out, "cross_section.svg"))
    print("[done] outputs in %s (sim %.1fs)" % (out, sim.wall_time))
    return rep


# --------------------------------------------------------------------------
# Blender scene
# --------------------------------------------------------------------------
_BLENDER_STATE = {}


def _clear_scene():
    import bpy
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras,
                 bpy.data.lights):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def _terrain_material():
    import bpy
    mat = bpy.data.materials.new("Terrain_CutFill")
    _te.ensure_nodes(mat)
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = _te.COLOR_ATTR
    attr.location = (-400, 200)
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    return mat


def _setup_camera_light_hud(cfg, pivot):
    import bpy
    R = cfg.r_max
    cam_data = bpy.data.cameras.new("Survey_Camera")
    cam_data.lens = 30.0
    cam_data.clip_end = 5000.0
    cam = bpy.data.objects.new("Survey_Camera", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (0.35 * R, -1.45 * R, 0.95 * R)
    track = cam.constraints.new("TRACK_TO")
    track.target = pivot
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.context.scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 4.5
    sun_data.angle = math.radians(3)
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(64), 0.0, math.radians(-40))  # raking light
    bpy.context.scene.collection.objects.link(sun)

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    _te.ensure_nodes(world)
    bg = world.node_tree.nodes.get("Background") if world.node_tree else None
    if bg:
        bg.inputs["Color"].default_value = (0.30, 0.38, 0.50, 1.0)
        bg.inputs["Strength"].default_value = 0.7

    txt_data = bpy.data.curves.new("HUD", "FONT")
    txt_data.size = 0.2
    txt_data.align_y = "TOP"
    txt_data.body = "HUD"
    hud = bpy.data.objects.new("Telemetry_HUD", txt_data)
    bpy.context.scene.collection.objects.link(hud)
    hud.parent = cam
    hud.location = (-5.75, 3.2, -10.0)
    hud_mat = bpy.data.materials.new("HUD_Text")
    _te.ensure_nodes(hud_mat)
    b = hud_mat.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (0, 0, 0, 1)
        for key in ("Emission Color", "Emission"):
            if key in b.inputs:
                b.inputs[key].default_value = (1, 1, 1, 1)
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = 1.0
    txt_data.materials.append(hud_mat)
    return cam, hud


def _on_frame_change(scene, depsgraph=None):
    st = _BLENDER_STATE
    if not st:
        return
    idx = min(max(scene.frame_current - scene.frame_start, 0), len(st["z"]) - 1)
    T = st["terrain"]
    z = st["z"][idx].astype(np.float64)
    _te.update_blender_mesh(st["terrain_obj"], st["co"], z, T.colors(z))
    tel = st["telemetry"][idx]
    ex = st["cfg"].display_exaggeration
    _kin.pose_rig(st["rig"], tel["theta_rad"], tel["r_m"], tel["z_head"] * ex, tel["r_dump_m"],
                  tel["z_dump"] * ex, tel["z_end"] * ex, tel["discharging"])
    st["hud"].data.body = hud_text(tel, st["cfg"])


def run_blender(cfg, args):
    import bpy
    scene = bpy.context.scene
    _clear_scene()

    sim = Simulation(cfg)
    F = cfg.frames
    z_frames = [None] * F
    tel_frames = [None] * F

    def hook(f, s, st):
        z_frames[f] = s.terrain.z.astype(np.float16)
        tel_frames[f] = st
    rep = sim.run(n_frames=F, on_frame=hook)
    print_report(rep)
    for f in range(F):          # guard against duplicated frame indices on tiny runs
        if z_frames[f] is None:
            z_frames[f], tel_frames[f] = z_frames[f - 1], tel_frames[f - 1]

    terrain_obj, co = _te.build_blender_mesh(sim.terrain, "Terrain_Heightmap")
    terrain_obj.data.materials.append(_terrain_material())
    terrain_obj.scale = (1.0, 1.0, cfg.display_exaggeration)   # display only; volumes use true z
    rig = _kin.build_rig(cfg)
    cam, hud = _setup_camera_light_hud(cfg, rig["pivot"])

    scene.frame_start = 1
    scene.frame_end = F
    scene.render.fps = cfg.fps
    scene["earthwork_report"] = json.dumps(rep["achieved"])
    _BLENDER_STATE.clear()
    _BLENDER_STATE.update(cfg=cfg, terrain=sim.terrain, terrain_obj=terrain_obj, co=co,
                          z=z_frames, telemetry=tel_frames, rig=rig, hud=hud, report=rep)
    handlers = bpy.app.handlers.frame_change_pre
    for h in list(handlers):
        if getattr(h, "__name__", "") == "_on_frame_change":
            handlers.remove(h)
    handlers.append(_on_frame_change)

    engine = (args.engine or "EEVEE").upper()
    choices = {"EEVEE": ["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"], "CYCLES": ["CYCLES"],
               "WORKBENCH": ["BLENDER_WORKBENCH"]}.get(engine, [engine])
    for name in choices:
        try:
            scene.render.engine = name
            break
        except TypeError:
            continue
    if scene.render.engine == "BLENDER_WORKBENCH":
        scene.display.shading.color_type = "VERTEX"
    try:
        scene.eevee.taa_render_samples = 16
    except AttributeError:
        pass
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    scene.frame_set(F if args.still_frame is None else int(args.still_frame))

    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save_blend))
    if args.render_still:
        scene.render.filepath = os.path.abspath(args.render_still)
        bpy.ops.render.render(write_still=True)
        print("[render] still written to %s" % scene.render.filepath)
    if args.render_anim:
        scene.render.filepath = os.path.join(os.path.abspath(args.render_anim), "frame_")
        bpy.ops.render.render(animation=True)
        print("[render] animation frames in %s" % args.render_anim)
    return rep


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(description="Atlantean Berm & Ring Engine")
    p.add_argument("--params", default=None, help="path to params.json")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="override a parameter, e.g. --set rig.lifts=4 --set soil.swell_factor=1.3")
    p.add_argument("--res", type=int, help="shortcut for grid.resolution")
    p.add_argument("--frames", type=int, help="shortcut for animation.frames")
    p.add_argument("--lifts", type=int, help="shortcut for rig.lifts")
    p.add_argument("--path", choices=["spiral", "stepped"], help="shortcut for rig.path_mode")
    p.add_argument("--out", default=os.path.join(HERE, "output"), help="headless output folder")
    p.add_argument("--png-every", type=int, default=0, help="headless: top-down PNG every N frames")
    p.add_argument("--engine", default="EEVEE", help="Blender: EEVEE | CYCLES | WORKBENCH")
    p.add_argument("--render-still", help="Blender: render one frame to this PNG path")
    p.add_argument("--still-frame", type=int, help="Blender: frame to show/render (default last)")
    p.add_argument("--render-anim", help="Blender: render all frames into this folder")
    p.add_argument("--save-blend", help="Blender: save the scene to this .blend path")
    return p.parse_args(argv)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    try:
        import bpy  # noqa: F401
        in_blender = True
        if "--" not in sys.argv:
            argv = []
    except ImportError:
        in_blender = False
    args = parse_args(argv)
    overrides = list(args.set)
    if args.res:
        overrides.append("grid.resolution=%d" % args.res)
    if args.frames:
        overrides.append("animation.frames=%d" % args.frames)
    if args.lifts:
        overrides.append("rig.lifts=%d" % args.lifts)
    if args.path:
        overrides.append('rig.path_mode="%s"' % args.path)
    cfg = load_config(args.params, overrides)
    return run_blender(cfg, args) if in_blender else run_headless(cfg, args)


if __name__ == "__main__":
    main()
