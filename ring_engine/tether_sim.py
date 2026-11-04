"""Tethered eOx earthmoving sim: an eOx on a leash towing a box scraper in circles.

The vehicle drives tangentially around a fixed pivot. A winch at the pivot sets the
radius, so there is no steering: each lap the scraper takes whatever depth the pull
budget allows. When the pan is full (or its load uses up most of the pull), the
winch walks the vehicle out on a spiral to the paired berm, it spreads the load,
and spirals back to the ring it was cutting.

Every step is limited by physics from the eOx models:

    pull available  = min(tyre grip [Brixius, eox.tyres], motor force [rated, or peak while cool])
    pull needed     = rolling (vehicle + pan) + grade (along the direction of travel)
                      + cutting work / distance   (specific energy k, kJ per m3)
    speed           = min(tool speed, shaft power / pull)

plus boulder refusals, motor heating, a shallow water table (wet ground under the
tyres) and battery recharges when not on tether power.

    python3 tether_sim.py --soil ne_glacial_till                 # sloped New England site
    python3 tether_sim.py --soil florida_sand --site flat        # flat Florida lot
"""
import argparse
import csv
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

import tyres as ty  # noqa: E402
from config import load_config  # noqa: E402
from terrain_engine import Terrain, write_png  # noqa: E402

G = 9.81
DEFAULT_PARAMS = os.path.join(HERE, "tether_params.json")
DEFAULT_VEHICLE = os.path.join(HERE, "vehicles", "eox_home_tethered.json")


def load_vehicle(path=None, overrides=None):
    with open(path or DEFAULT_VEHICLE) as fh:
        v = json.load(fh)
    for item in overrides or []:
        key, val = item.split("=", 1)
        node = v
        parts = key.split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = json.loads(val)
    return v


class TetherSim:
    def __init__(self, cfg, vehicle, seed=1, log=print, ds_cut=0.4, ds_travel=1.0):
        self.cfg, self.veh, self.log = cfg, vehicle, log
        t0 = time.time()
        self.T = T = Terrain(cfg)
        soil = cfg.soil
        ops = cfg.raw.get("operations", {})
        self.ops = ops
        self.power = ops.get("power", "tether")
        self.ds_cut, self.ds_travel = ds_cut, ds_travel

        # Soil
        self.sf = cfg.swell_factor
        self.rho_loose = soil["bank_density_kg_m3"] / self.sf
        self.k_bank = soil["cutting_kpa"] * 1000.0                      # J per bank m3
        self.k_loose = self.k_bank * soil.get("loose_cut_factor", 0.3)
        self.ground_dry = ty.Ground(soil["cone_index_kpa"])
        self.ground_wet = ty.Ground(soil.get("cone_index_wet_kpa", soil["cone_index_kpa"]))
        self.wt_depth = soil.get("water_table_depth_m")
        self.rock_rate = soil.get("rock_refusals_per_bank_m3", 0.0)
        self.rock_delay = soil.get("rock_delay_min", 0.0) * 60.0
        self.rock_vol = soil.get("rock_volume_m3", 0.0)

        # Vehicle and tool
        v, d, tool = vehicle, vehicle["drive"], vehicle["tool"]
        t = v["tyre"]
        self.tyre = ty.Tyre(t["diameter_mm"], t["width_mm"], t["rim_mm"], t["pressure_kpa"])
        self.n_driven, self.n_tyres = t["driven"], t["total"]
        self.m_v = v["mass_kg"] + v.get("ballast_kg", 0.0)
        self.drive_frac = v["drive_axle_static_fraction"]
        self.F_peak = d["peak_force_n"] * d.get("units", 1)
        self.F_rated = d["rated_force_n"] * d.get("units", 1)
        self.P_wheel = d["rated_shaft_power_w"] * d.get("units", 1) * d["driveline_eff"]
        self.eta = d["motor_eff"] * d["controller_eff"] * d["driveline_eff"]
        self.v_max = d["v_max_m_s"]
        self.tau = d["thermal_time_constant_s"]
        self.width = tool["width_m"]
        self.cap = tool["capacity_loose_m3"]
        self.m_tool = tool["mass_kg"]
        self.tongue = tool["tongue_weight_fraction"]
        self.crr_tool = tool["rolling_resistance"]
        self.v_cut = tool["cut_speed_m_s"]
        self.spread_len = tool["spread_length_m"]
        self.hotel = v.get("hotel_w", 0.0)
        self.batt_wh = v["battery"]["usable_wh"]
        self.charger_w = v["battery"]["charger_w"]
        self.handling = v["battery"].get("handling_min", 10) * 60.0
        self.line_loss = v["tether"]["line_loss"]
        self.v_winch = v["tether"]["winch_radial_speed_m_s"]
        self.haul_pull = ops.get("haul_when_pull_used", 0.75)
        self.max_ramp = ops.get("max_ramp_grade", 0.12)
        self.half_wb = 0.5 * vehicle.get("wheelbase_m", 1.6)

        # Schedule
        lift_depth = cfg.raw["rig"].get("lift_depth_m", 0.3)
        self.lifts = max(1, int(math.ceil(T.max_depth / lift_depth)))
        self.pitch = self.width * (1.0 - cfg.pass_overlap)
        self.moat_to_berm = cfg.moat_to_berm()
        self.curves = {}
        for m in range(len(cfg.moats)):
            k = self.moat_to_berm[m][0]
            self.curves[m] = (T.cumulative_radial("moat", m), T.cumulative_radial("berm", k), k)
        self.rng = np.random.default_rng(seed)
        self.sectors = {}
        self.by_moat = {}
        self.loads_since_grade = {}
        self.grade_every = ops.get("grade_berm_every_loads", 40)
        self.n_sectors = 48

        # State
        self.theta, self.r = 0.0, float(cfg.moats[0].r_in)
        self.pan = 0.0
        self.heat = 0.0
        self.e_since_charge = 0.0
        self.c = dict(cut_bank=0.0, recut_loose=0.0, deposited=0.0, rock_bank=0.0, rocks=0,
                      t_move=0.0, t_rock=0.0, t_stall=0.0, t_charge=0.0, t_heat=0.0, heat_pauses=0,
                      e_batt_j=0.0,
                      charges=0, loads=0, laps=0, grading_laps=0, stalls=0, stalls_cut=0, stalls_travel=0, steps_cut=0, lim_grip=0,
                      lim_motor=0, lim_heat=0, steps_wet=0, steps_steep=0, max_cross_deg=0.0,
                      infeasible_rings=0, stuck_rings=0, dist_m=0.0)
        self.telemetry = []
        self.frames = []
        self._next_frame = 0.0
        self.aborted = None
        self.log("[init] %s on %s: grid %d (dx %.2f m), design cut %s m3, fill %s m3, %d lifts, "
                 "relief %.2f m (%.1f ft)  %.1fs"
                 % (vehicle["name"], soil.get("label", soil.get("preset", "soil")), cfg.resolution,
                    T.dx, "{:,.0f}".format(T.design_cut_total), "{:,.0f}".format(T.design_fill_total),
                    self.lifts, T.design_report["rules"]["existing_relief_m"],
                    T.design_report["rules"]["existing_relief_m"] / 0.3048, time.time() - t0))
        for w in cfg.warnings:
            self.log("[warn] " + w)

    # ------------------------------------------------------------ physics
    @property
    def t_total(self):
        c = self.c
        return c["t_move"] + c["t_rock"] + c["t_stall"] + c["t_charge"] + c["t_heat"]

    def _forces(self, x, y, hx, hy):
        T = self.T
        h = self.half_wb                                  # pitch of a rigid chassis over its wheelbase
        zf = T.sample_z(x + h * hx, y + h * hy)
        zb = T.sample_z(x - h * hx, y - h * hy)
        grade = (zf - zb) / (2.0 * h)
        sin_g = grade / math.sqrt(1.0 + grade * grade)
        wet = False
        if self.wt_depth is not None:
            wet = 0.5 * (zf + zb) < T._bilinear(T.z0, x, y) - self.wt_depth
        ground = self.ground_wet if wet else self.ground_dry
        m_pan = self.m_tool + self.pan * self.rho_loose
        W_v, W_pan = self.m_v * G, m_pan * G
        W_drive = W_v * self.drive_frac + self.tongue * W_pan
        mu = ty.grip(self.tyre, W_drive / self.n_driven, ground)
        W_on_tyres = W_v + self.tongue * W_pan
        crr = ty.rolling(self.tyre, W_on_tyres / self.n_tyres, ground)
        F_rr = crr * W_on_tyres + self.crr_tool * (1.0 - self.tongue) * W_pan
        F_grade = (W_v + W_pan) * sin_g
        return mu * W_drive, F_rr, F_grade, wet

    def _advance(self, x, y, hx, hy, ds, cutting=None):
        """Move ``ds`` along (hx, hy); optionally cut. Returns (bank, loose) removed."""
        T, c = self.T, self.c
        F_trac, F_rr, F_grade, wet = self._forces(x, y, hx, hy)
        if wet:
            c["steps_wet"] += 1
        F_motor = self.F_peak            # bursts above rated are paid for in cooling pauses
        F_lim = min(F_trac, F_motor)
        F_base = F_rr + F_grade
        bank = loose = 0.0
        if cutting is not None:
            lf, room = cutting
            c["steps_cut"] += 1
            # Throughput-optimal pull under torque^2 heating: cut rate ~ (F - F_base) * duty with
            # duty ~ (F_rated / F)^2, which peaks at F = 2 F_base (never below rated, never above grip).
            F_target = min(F_lim, max(self.F_rated, 2.0 * F_base))
            avail = F_target - F_base
            if avail > 0.0:
                bank, loose = T.cut_at(x, y, 0.5 * self.width, lf, room, max_work=avail * ds,
                                       k_bank=self.k_bank, k_loose=self.k_loose)
                limited = T.last_cut_limited and room > 1e-9
            else:
                limited = True
            if limited:
                if F_target < F_lim - 1e-6:
                    c["lim_heat"] += 1                    # held below grip to manage motor heat
                elif F_trac <= F_motor:
                    c["lim_grip"] += 1
                else:
                    c["lim_motor"] += 1
            self._last_limited = limited
        F = F_base + (self.k_bank * bank + self.k_loose * loose) / ds
        v_cap = self.v_cut if cutting is not None else self.v_max
        self._stalled = False
        if F > F_lim + 1e-6:                              # wheels slip: back off and creep
            c["stalls"] += 1
            c["stalls_cut" if cutting is not None else "stalls_travel"] += 1
            ph = "stall_" + getattr(self, "_phase", "cut")
            c[ph] = c.get(ph, 0) + 1
            c["t_stall"] += 4.0
            F, v = F_lim, 0.15
            self._stalled = True
        else:
            v = min(v_cap, self.P_wheel / max(F, 1.0))
        dt = ds / v
        a = 1.0 - math.exp(-dt / self.tau)               # motor heating: ~ torque^2, 10-min average
        self.heat += a * ((max(F, 0.0) / self.F_rated) ** 2 - self.heat)
        if self.heat >= 1.0:                              # over the thermal limit: stop and cool to 50 %
            pause = self.tau * math.log(self.heat / 0.5)
            c["t_heat"] += pause
            c["heat_pauses"] += 1
            self.heat = 0.5
            c["e_batt_j"] += self.hotel * pause
        e = max(F, 0.0) * ds / self.eta + self.hotel * dt
        c["e_batt_j"] += e
        c["t_move"] += dt
        c["dist_m"] += ds
        if self.power == "battery":
            self.e_since_charge += e
            if self.e_since_charge >= self.batt_wh * 3600.0:
                c["charges"] += 1
                c["t_charge"] += (self.batt_wh / self.charger_w * 3600.0 + self.handling
                                  + 2.0 * self.r / self.v_max)
                self.e_since_charge = 0.0
        return bank, loose

    # ----------------------------------------------------------- motions
    def _pos(self):
        return self.r * math.cos(self.theta), self.r * math.sin(self.theta)

    def _spiral_to(self, r_target):
        """Winch the vehicle radially while it keeps driving around (a spiral ramp)."""
        v_t = 1.5
        sin_nom = self.v_winch / math.hypot(self.v_winch, v_t)
        T = self.T
        self._phase = "spiral_loaded" if self.pan > 1e-6 else "spiral_empty"
        while abs(r_target - self.r) > 1e-6:
            sgn = 1.0 if r_target > self.r else -1.0
            x, y = self._pos()
            th = self.theta
            # Slow the winch on trench walls so the ramp along the path stays <= max_ramp_grade.
            ux, uy = math.cos(th), math.sin(th)
            # steepest radial slope over the next metre (look ahead onto trench walls)
            s_r = 0.0
            for off in (0.0, 0.5, 1.0):
                px, py = x + sgn * off * ux, y + sgn * off * uy
                s_r = max(s_r, abs(T.sample_z(px + 0.5 * ux, py + 0.5 * uy)
                                   - T.sample_z(px - 0.5 * ux, py - 0.5 * uy)))
            s_t = abs(T.sample_z(x - 0.5 * uy, y + 0.5 * ux) - T.sample_z(x + 0.5 * uy, y - 0.5 * ux))
            F_trac, F_rr, _, _ = self._forces(x, y, -uy, ux)
            W = (self.m_v + self.m_tool + self.pan * self.rho_loose) * G
            ramp = max(0.02, min(self.max_ramp, (0.85 * min(F_trac, self.F_peak) - F_rr) / W))
            sin_a = sin_nom if s_r < 1e-6 else max(0.02, min(sin_nom, max(ramp - s_t, 0.01) / s_r))
            cos_a = math.sqrt(1.0 - sin_a * sin_a)
            ds = min(self.ds_travel if s_r < 0.05 else 0.5 * self.ds_travel, abs(r_target - self.r) / sin_a)
            hx = cos_a * -math.sin(th) + sgn * sin_a * math.cos(th)
            hy = cos_a * math.cos(th) + sgn * sin_a * math.sin(th)
            self._advance(x, y, hx, hy, ds)
            self.r += sgn * ds * sin_a
            self.theta += ds * cos_a / max(self.r, 0.5)

    def _haul(self, m, r_c, lf):
        """Carry the pan out to the paired berm, spread it, and return to radius r_c."""
        (mr, mc), (br, bc), k = self.curves[m]
        frac = float(np.interp(r_c, mr, mc))
        r_d = float(np.interp(frac, bc, br))
        self._spiral_to(r_d)
        T, c = self.T, self.c
        spread = 0.0
        ds = self.ds_cut
        self._phase = "spread"
        layer = self.veh["tool"].get("spread_layer_m", 0.05)
        limit = 2.0 * math.pi * r_d                       # one full lap of spreading at most
        # Dump where the berm is low: drive on (loaded) to a sector near the least-built one.
        sec = self.sectors.setdefault(k, np.zeros(self.n_sectors))
        tol = 2.0 * self.cap
        seek = 0.0
        while seek < 0.5 * limit:
            si = int((self.theta % (2 * math.pi)) / (2 * math.pi) * self.n_sectors) % self.n_sectors
            if sec[si] <= sec.min() + tol:
                break
            x, y = self._pos()
            self._advance(x, y, -math.sin(self.theta), math.cos(self.theta), self.ds_travel)
            self.theta += self.ds_travel / self.r
            seek += self.ds_travel
        while self.pan > 1e-9:
            x, y = self._pos()
            want = min(self.pan, layer * self.width * ds * 1.5)
            placed = T.deposit_layer(x, y, 0.5 * self.width, k, layer, want)
            if spread > limit and placed < want:          # berm full along this whole ring
                placed += T.deposit_overfill(x, y, self.width, k, self.pan)
            self.pan -= placed
            c["deposited"] += placed
            sec[int((self.theta % (2 * math.pi)) / (2 * math.pi) * self.n_sectors) % self.n_sectors] += placed
            self._advance(x, y, -math.sin(self.theta), math.cos(self.theta), ds)
            self.theta += ds / self.r
            spread += ds
        self.pan = max(self.pan, 0.0)
        T.relax_near(*self._pos(), half_width=self.cfg.relax_window, iters=3)
        c["loads"] += 1
        self.loads_since_grade[k] = self.loads_since_grade.get(k, 0) + 1
        if self.loads_since_grade[k] >= self.grade_every:
            self.loads_since_grade[k] = 0
            self._grade_berm(k)
        self._spiral_to(r_c)
        self._phase = "cut"

    def _grade_berm(self, k):
        """Dress berm k: empty laps across it with the blade levelling loose spoil."""
        T = self.T
        lo, hi = T.zone_extent("berm", k)
        self._phase = "grade"
        for r in np.arange(lo + 0.5 * self.width, hi, self.width):
            self._spiral_to(float(r))
            travelled, circ = 0.0, 2.0 * math.pi * r
            while travelled < circ:
                x, y = self._pos()
                sl, mask = T._window(x, y, 0.5 * self.width)
                if sl is not None:
                    mm = mask & (T.berm_id[sl] == k)
                    if mm.any():
                        T.level(sl, mm)
                self._advance(x, y, -math.sin(self.theta), math.cos(self.theta), self.ds_travel)
                self.theta += self.ds_travel / self.r
                travelled += self.ds_travel
            self.c["grading_laps"] += 1

    def _lap(self, m, r_c, lf):
        """One full circle at r_c cutting moat m. Returns (bank cut this lap, any step pull-limited)."""
        T, c = self.T, self.c
        ds = self.ds_cut
        lap_cut, limited = 0.0, False
        travelled = 0.0
        circ = 2.0 * math.pi * r_c
        while travelled < circ:
            th = self.theta
            x, y = r_c * math.cos(th), r_c * math.sin(th)
            hx, hy = -math.sin(th), math.cos(th)
            # cross-slope across the track (radial), a rollover indicator
            zo = T.sample_z(x * (1 + 0.5 / r_c), y * (1 + 0.5 / r_c))
            zi = T.sample_z(x * (1 - 0.5 / r_c), y * (1 - 0.5 / r_c))
            cross = math.degrees(math.atan(abs(zo - zi)))
            if cross > c["max_cross_deg"]:
                c["max_cross_deg"] = cross
            if cross > 15.0:
                c["steps_steep"] += 1
            room = self.cap - self.pan
            self._last_limited = False
            bank, loose = self._advance(x, y, hx, hy, ds, cutting=(lf, room))
            limited |= self._last_limited
            if bank > 0.0 and self.rock_rate > 0.0:
                n = self.rng.poisson(self.rock_rate * bank)
                if n:
                    rv = min(n * self.rock_vol, bank)
                    c["rocks"] += int(n)
                    c["rock_bank"] += rv
                    c["t_rock"] += n * self.rock_delay
                    bank_to_pan = bank - rv
                else:
                    bank_to_pan = bank
            else:
                bank_to_pan = bank
            self.pan += loose + self.sf * bank_to_pan
            c["cut_bank"] += bank
            c["recut_loose"] += loose
            lap_cut += bank + loose
            self.theta += ds / r_c
            travelled += ds
            full = self.pan >= 0.97 * self.cap
            heavy = self.pan > 0.1 * self.cap and (self._stalled or self._pull_used() > self.haul_pull)
            if full or heavy:
                self._haul(m, r_c, lf)
                self.r = r_c
            self._snapshot()
        c["laps"] += 1
        return lap_cut, limited

    def _pull_used(self):
        x, y = self._pos()
        F_trac, F_rr, F_grade, _ = self._forces(x, y, -math.sin(self.theta), math.cos(self.theta))
        return (F_rr + max(F_grade, 0.0)) / max(min(F_trac, self.F_peak), 1.0)

    # ------------------------------------------------------------- output
    def _snapshot(self, force=False):
        frac = self.c["cut_bank"] / max(self.T.design_cut_total, 1e-9)
        if force or frac >= self._next_frame:
            self.frames.append((frac, self.t_total, self.T.z.astype(np.float32)))
            self._next_frame += 0.1
            self.telemetry.append(self.state())

    def state(self):
        c = self.c
        fill = c["deposited"] - c["recut_loose"]
        return {"t_h": self.t_total / 3600.0, "cut_bank_m3": c["cut_bank"], "fill_m3": fill,
                "pan_m3": self.pan, "rocks": c["rocks"], "loads": c["loads"], "laps": c["laps"],
                "energy_kwh": c["e_batt_j"] / 3.6e6, "theta_rev": self.theta / (2 * math.pi),
                "r_m": self.r, "complete_pct": 100.0 * c["cut_bank"] / max(self.T.design_cut_total, 1e-9)}

    # --------------------------------------------------------------- run
    def run(self, progress_every_h=None):
        cfg, T, c = self.cfg, self.T, self.c
        wall = time.time()
        max_laps = self.ops.get("max_laps_per_ring", 800)
        max_s = self.ops.get("max_sim_hours", 60000) * 3600.0
        self._snapshot(force=True)
        last_log = time.time()
        n_moats = len(cfg.moats)
        for lift in range(1, self.lifts + 1):
            lf = lift / self.lifts
            order = range(n_moats) if lift % 2 else range(n_moats - 1, -1, -1)
            for m in order:
                t_start = self.t_total
                lo, hi = T.zone_extent("moat", m)
                rings = np.arange(lo + 0.35 * self.width, hi - 0.35 * self.width + 1e-9, self.pitch)
                if rings.size == 0:
                    rings = np.array([0.5 * (lo + hi)])
                if lift % 2 == 0:
                    rings = rings[::-1]
                for r_c in rings:
                    self._spiral_to(float(r_c))
                    for lap in range(max_laps):
                        cut, limited = self._lap(m, float(r_c), lf)
                        if cut < 1e-4:
                            if limited:
                                c["infeasible_rings"] += 1
                            break
                    else:
                        c["stuck_rings"] += 1
                    if time.time() - last_log > 15:
                        last_log = time.time()
                        st = self.state()
                        self.log("  lift %d/%d moat %d r=%5.1f  %5.1f%%  cut %8.0f m3  t %7.0f h  "
                                 "rocks %5d  loads %6d  (%.0fs)"
                                 % (lift, self.lifts, m, r_c, st["complete_pct"], st["cut_bank_m3"],
                                    st["t_h"], c["rocks"], c["loads"], time.time() - wall))
                    if self.t_total > max_s:
                        self.aborted = "hit max_sim_hours (%d h)" % (max_s / 3600)
                        break
                self.by_moat[m] = self.by_moat.get(m, 0.0) + self.t_total - t_start
                if self.aborted:
                    break
            T.relax(iters=10)
            if self.aborted:
                break
        if self.pan > 0:                                   # last partial load
            m = len(cfg.moats) - 1
            self._haul(m, self.r, 1.0)
        T.relax(iters=30)
        self._snapshot(force=True)
        self.wall = time.time() - wall
        return self.report()

    def report(self):
        T, c, cfg = self.T, self.c, self.cfg
        vol = T.volumes()
        fill = c["deposited"] - c["recut_loose"]
        cut = c["cut_bank"]
        hours = self.t_total / 3600.0
        e_kwh = c["e_batt_j"] / 3.6e6
        grid_kwh = e_kwh / (1.0 - self.line_loss) if self.power == "tether" else e_kwh / 0.9
        lim = c["lim_grip"] + c["lim_motor"] + c["lim_heat"]
        hpd = self.ops.get("hours_per_day", 10)
        return {
            "scenario": {"soil": cfg.soil.get("preset"), "soil_label": cfg.soil.get("label"),
                         "site": cfg.site, "vehicle": self.veh["name"], "power": self.power,
                         "ballast_kg": self.veh.get("ballast_kg", 0), "units": self.veh["drive"].get("units", 1)},
            "design": {"existing_relief_m": T.design_report["rules"]["existing_relief_m"],
                       "water_levels_m": T.water_levels,
                       "max_cut_m": T.max_depth, "max_fill_m": T.max_height,
                       "V_cut_bank_m3": T.design_cut_total, "V_fill_loose_m3": T.design_fill_total,
                       "moats": T.design_report["moats"], "berms": T.design_report["berms"],
                       "lifts": self.lifts},
            "achieved": {"V_cut_bank_m3": cut, "V_fill_m3": fill, "V_rock_bank_m3": c["rock_bank"],
                         "pan_residual_m3": self.pan,
                         "mass_balance_error_m3": fill + self.pan + self.sf * c["rock_bank"] - self.sf * cut,
                         "moat_completion_pct": vol["moat_completion_pct"],
                         "moat_rmse_m": vol["moat_rmse_m"], "berm_rmse_m": vol["berm_rmse_m"],
                         "aborted": self.aborted},
            "time": {"total_h": hours, "moving_h": c["t_move"] / 3600.0,
                     "by_moat_h": [self.by_moat.get(m, 0.0) / 3600.0 for m in range(len(cfg.moats))],
                     "rock_delay_h": c["t_rock"] / 3600.0, "stall_h": c["t_stall"] / 3600.0,
                     "charging_h": c["t_charge"] / 3600.0, "motor_cooling_h": c["t_heat"] / 3600.0,
                     "motor_cooling_pauses": c["heat_pauses"], "working_days": hours / hpd,
                     "hours_per_day": hpd, "m3_per_hour": cut / max(hours, 1e-9)},
            "energy": {"battery_side_kwh": e_kwh, "grid_kwh": grid_kwh,
                       "kwh_per_bank_m3": e_kwh / max(cut, 1e-9), "charges": c["charges"]},
            "machine": {"laps": c["laps"], "loads": c["loads"], "grading_laps": c["grading_laps"],
                        "avg_load_bank_m3": cut / max(c["loads"], 1),
                        "distance_km": c["dist_m"] / 1000.0, "stalls": c["stalls"],
                        "stalls_cutting": c["stalls_cut"], "stalls_travelling": c["stalls_travel"],
                        "rock_refusals": c["rocks"],
                        "cut_steps_limited_pct": 100.0 * lim / max(c["steps_cut"], 1),
                        "limit_grip_pct": 100.0 * c["lim_grip"] / max(lim, 1),
                        "limit_motor_pct": 100.0 * c["lim_motor"] / max(lim, 1),
                        "limit_heat_pct": 100.0 * c["lim_heat"] / max(lim, 1),
                        "wet_ground_steps_pct": 100.0 * c["steps_wet"] / max(c["steps_cut"], 1),
                        "max_cross_slope_deg": c["max_cross_deg"],
                        "steep_cross_slope_steps_pct": 100.0 * c["steps_steep"] / max(c["steps_cut"], 1),
                        "infeasible_rings": c["infeasible_rings"], "stuck_rings": c["stuck_rings"]},
            "wall_time_s": getattr(self, "wall", None),
        }


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------
def section_svg(T, path, azimuth, title):
    sec = T.section_line(azimuth)
    s, z0, zd, z = sec["s"], sec["z0"], sec["design"], sec["z"]
    W, H, pad = 1000, 340, 50
    zmin = min(z0.min(), zd.min(), z.min()) - 0.3
    zmax = max(z0.max(), zd.max(), z.max()) + 0.3
    sx = (W - 2 * pad) / (s[-1] - s[0])
    sy = (H - 2 * pad) / (zmax - zmin)

    def pts(arr):
        return " ".join("%.1f,%.1f" % (pad + (a - s[0]) * sx, H - pad - (b - zmin) * sy) for a, b in zip(s, arr))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="sans-serif" font-size="12">' % (W, H),
           '<rect width="100%" height="100%" fill="#faf8f3"/>',
           '<polyline fill="none" stroke="#8a8a8a" stroke-width="1.5" stroke-dasharray="3,3" points="%s"/>' % pts(z0),
           '<polyline fill="none" stroke="#1f4e8c" stroke-width="1.5" stroke-dasharray="7,4" points="%s"/>' % pts(zd),
           '<polyline fill="none" stroke="#c2741f" stroke-width="2.2" points="%s"/>' % pts(z)]
    for wl in T.water_levels:
        if wl is not None:
            y = H - pad - (wl - zmin) * sy
            out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="#4fa3e0" stroke-width="0.8"/>' % (pad, W - pad, y, y))
    out += ['<text x="%d" y="20">%s</text>' % (pad, title),
            '<text x="%d" y="38" fill="#555">grey dotted = existing ground, blue dashed = design, orange = achieved, '
            'light blue = moat water levels; vertical exaggeration %.0fx</text>' % (pad, sy / sx),
            '<text x="%d" y="%d">low side</text>' % (pad, H - 12),
            '<text x="%d" y="%d" text-anchor="end">high side</text>' % (W - pad, H - 12),
            "</svg>"]
    with open(path, "w") as fh:
        fh.write("\n".join(out))


def write_outputs(sim, rep, out):
    os.makedirs(out, exist_ok=True)
    T = sim.T
    with open(os.path.join(out, "report.json"), "w") as fh:
        json.dump(rep, fh, indent=2, default=float)
    if sim.telemetry:
        with open(os.path.join(out, "telemetry.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(sim.telemetry[0].keys()))
            w.writeheader()
            w.writerows(sim.telemetry)
    write_png(os.path.join(out, "existing.png"), T.hillshade_rgb(T.z0))
    write_png(os.path.join(out, "design.png"), T.hillshade_rgb(T.design))
    write_png(os.path.join(out, "final.png"), T.hillshade_rgb())
    for frac, t, z in sim.frames[1:-1:2]:
        write_png(os.path.join(out, "progress_%03d.png" % round(frac * 100)), T.hillshade_rgb(z))
    az = (sim.cfg.site or {}).get("uphill_azimuth_deg", 0.0)
    section_svg(T, os.path.join(out, "section.svg"), az,
                "Section through the pivot along the slope (%s)" % rep["scenario"]["soil_label"])


def print_report(rep, log=print):
    d, a, t, e, m = rep["design"], rep["achieved"], rep["time"], rep["energy"], rep["machine"]
    log("-" * 76)
    log(" %s | %s | %s power" % (rep["scenario"]["soil_label"], rep["scenario"]["site"].get("type"),
                                rep["scenario"]["power"]))
    log("  design cut %s m3 bank (max %.2f m deep), fill %s m3 loose, relief %.2f m"
        % ("{:,.0f}".format(d["V_cut_bank_m3"]), d["max_cut_m"], "{:,.0f}".format(d["V_fill_loose_m3"]),
           d["existing_relief_m"]))
    log("  achieved %.1f%% of cut, %s m3, balance error %.1e m3%s"
        % (a["moat_completion_pct"], "{:,.0f}".format(a["V_cut_bank_m3"]), a["mass_balance_error_m3"],
           ("  ABORTED: " + a["aborted"]) if a["aborted"] else ""))
    log("  time %s h = %s working days at %d h/day  (moving %.0f, motor cooling %.0f, rocks %.0f, "
        "stalls %.0f, charging %.0f h)"
        % ("{:,.0f}".format(t["total_h"]), "{:,.0f}".format(t["working_days"]), t["hours_per_day"],
           t["moving_h"], t["motor_cooling_h"], t["rock_delay_h"], t["stall_h"], t["charging_h"]))
    log("  %.2f m3/h, %.2f kWh per bank m3, %s grid kWh, %d charges"
        % (t["m3_per_hour"], e["kwh_per_bank_m3"], "{:,.0f}".format(e["grid_kwh"]), e["charges"]))
    log("  %s loads (avg %.3f bank m3), %s laps, %.0f km driven, %d rock refusals, %d stalls"
        % ("{:,}".format(m["loads"]), m["avg_load_bank_m3"], "{:,}".format(m["laps"]), m["distance_km"],
           m["rock_refusals"], m["stalls"]))
    log("  cutting limited by: grip %.0f%%, motor %.0f%%, motor heat %.0f%%; wet ground %.0f%% of cut "
        "steps; max cross-slope %.0f deg" % (m["limit_grip_pct"], m["limit_motor_pct"], m["limit_heat_pct"],
                                      m["wet_ground_steps_pct"], m["max_cross_slope_deg"]))


def build_overrides(args):
    ov = list(args.set)
    if args.soil:
        ov.append('soil.preset="%s"' % args.soil)
    if args.site == "flat":
        ov.append('site={"type": "flat"}')
    if args.res:
        ov.append("grid.resolution=%d" % args.res)
    if args.power:
        ov.append('operations.power="%s"' % args.power)
    return ov


def main(argv=None):
    p = argparse.ArgumentParser(description="Tethered eOx earthmoving sim")
    p.add_argument("--params", default=DEFAULT_PARAMS)
    p.add_argument("--vehicle", default=DEFAULT_VEHICLE)
    p.add_argument("--soil", help="soil preset from soils.json")
    p.add_argument("--site", choices=["flat", "slope"], help="flat overrides the sloped site")
    p.add_argument("--power", choices=["tether", "battery"])
    p.add_argument("--res", type=int)
    p.add_argument("--set", action="append", default=[], help="params override a.b=json")
    p.add_argument("--vset", action="append", default=[], help="vehicle override a.b=json")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", default=os.path.join(HERE, "output", "tether"))
    args = p.parse_args(argv)
    cfg = load_config(args.params, build_overrides(args))
    sim = TetherSim(cfg, load_vehicle(args.vehicle, args.vset), seed=args.seed)
    rep = sim.run()
    print_report(rep)
    write_outputs(sim, rep, args.out)
    print("[done] %s (%.0fs)" % (args.out, sim.wall))
    return rep


if __name__ == "__main__":
    main()
