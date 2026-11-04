"""Build an EOx vehicle description from modules: N drive-axle modules on the 48 V bus.

Part data are EOx's shared modules (zacharyelston/EOx @30f9dd8):

* 3 HP unit  (design/units.toml): 2,240 W rated at 3,600 rpm (5.94 N*m), peak torque x4,
  motor 0.80, controller 0.97, 18 + 2.5 kg, 100 A battery-side limit per controller.
* drive-axle module (design/axle.toml): golf-cart rear end 45 kg, 2 x 8 kg wheels on
  18x8.50-8 tyres, 12 kg subframe; stock 12.4:1, 15:1 gear set, or 24.8:1 with a chain stage.
* bus (design/units.toml, out/pro-report.md): the pack and main contactor carry 3 units at
  rated power at once (197 A of 200 A); a 4th unit needs a bigger pack or bus.

A tethered trencher needs no steering (the leash sets the radius), so every axle is a
driven module and all of the machine's weight is on driven wheels. For two or more
axles on a circle, a fixed chassis scrubs; an articulated frame (EOx Pro, issue EOx#5)
locked to the circle's curvature avoids it.
"""
import copy
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

UNIT = {"rated_w": 2240.0, "base_rpm": 3600.0, "peak_factor": 4.0, "motor_eff": 0.80,
        "controller_eff": 0.97, "mass_kg": 20.5, "battery_limit_a": 100.0}
MODULE = {"rear_end_kg": 45.0, "wheels_kg": 16.0, "subframe_kg": 12.0, "axle_eff": 0.93,
          "tyre": {"diameter_mm": 457, "width_mm": 216, "rim_mm": 203, "pressure_kpa": 83}}
BUS = {"max_units_rated": 3, "pack_continuous_a": 200.0, "nominal_v": 51.2}


def wheel_forces(ratio, tyre_d_mm):
    """(rated, peak) tractive force per module at the tyre, N."""
    t_rated = UNIT["rated_w"] / (UNIT["base_rpm"] * 2 * math.pi / 60.0)
    r = tyre_d_mm / 2000.0
    rated = t_rated * ratio * MODULE["axle_eff"] / r
    return rated, rated * UNIT["peak_factor"]


def build(spec):
    """spec: modules, ratio, ballast_kg, chassis_kg, tool{...}, name, ... -> vehicle dict."""
    n = int(spec["modules"])
    ratio = float(spec.get("ratio", 24.8))
    tyre = dict(MODULE["tyre"], **spec.get("tyre", {}))
    rated, peak = wheel_forces(ratio, tyre["diameter_mm"])
    # Forced-air cooling raises the continuous (thermal) rating; peak torque is unchanged.
    rated *= float(spec.get("continuous_factor", 1.0))
    module_kg = MODULE["rear_end_kg"] + MODULE["wheels_kg"] + MODULE["subframe_kg"] + UNIT["mass_kg"]
    mass = spec.get("chassis_kg", 85.0) + n * module_kg
    v_base = UNIT["base_rpm"] / ratio * 2 * math.pi / 60.0 * tyre["diameter_mm"] / 2000.0
    warnings = []
    units_total = n + spec.get("aux_units", 0)
    if units_total > BUS["max_units_rated"]:
        warnings.append("%d units exceed the EOx bus rating (%d at rated power); needs a bigger "
                        "pack/bus or a tether supply sized for it" % (units_total, BUS["max_units_rated"]))
    current_a = units_total * UNIT["rated_w"] / (UNIT["motor_eff"] * UNIT["controller_eff"] * 44.0)
    veh = {
        "name": spec.get("name", "EOx trencher %dWD" % (2 * n)),
        "derived_from": "eox_vehicle.build(%s)" % json.dumps({k: v for k, v in spec.items() if k != "tool"}),
        "mass_kg": mass,
        "ballast_kg": spec.get("ballast_kg", 0.0),
        "drive_axle_static_fraction": 1.0,
        "tyre": {**tyre, "driven": 2 * n, "total": 2 * n},
        "drive": {"peak_force_n": peak, "rated_force_n": rated, "rated_shaft_power_w": UNIT["rated_w"],
                  "units": n, "motor_eff": UNIT["motor_eff"], "controller_eff": UNIT["controller_eff"],
                  "driveline_eff": MODULE["axle_eff"], "v_max_m_s": min(2.2, v_base),
                  "thermal_time_constant_s": 600},
        "battery": {"usable_wh": spec.get("battery_wh", 4096), "charger_w": 1400, "handling_min": 10},
        "hotel_w": spec.get("hotel_w", 80),
        "tether": {"line_loss": spec.get("line_loss", 0.08),
                   "winch_radial_speed_m_s": spec.get("winch_radial_speed_m_s", 0.5)},
        "tool": spec["tool"],
        "bus": {"units": units_total, "rated_current_a": current_a, "warnings": warnings},
    }
    return veh


def train(car, n):
    """n identical cars coupled nose-to-tail on one leash, each towing its own pan along the same
    ring: pull, mass, pans and hotel load scale by n; the cut width does not."""
    t = copy.deepcopy(car)
    t["name"] = "EOx train %d x %s" % (n, car["name"].replace("EOx trencher ", ""))
    t["mass_kg"] = car["mass_kg"] * n
    t["ballast_kg"] = car.get("ballast_kg", 0.0) * n
    t["drive"]["units"] = car["drive"]["units"] * n
    t["tyre"]["driven"] = car["tyre"]["driven"] * n
    t["tyre"]["total"] = car["tyre"]["total"] * n
    t["hotel_w"] = car.get("hotel_w", 0.0) * n
    t["tool"]["capacity_loose_m3"] = car["tool"]["capacity_loose_m3"] * n
    t["tool"]["mass_kg"] = car["tool"]["mass_kg"] * n
    t["tool"]["type"] = "%d x %s" % (n, car["tool"]["type"])
    t["train_cars"] = n
    t["bus"] = dict(car.get("bus", {}), note="each car carries its own bus; the leash feeds all cars")
    return t


def load_fleet(path=None):
    with open(path or os.path.join(HERE, "vehicles", "trencher_variants.json")) as fh:
        data = json.load(fh)
    base_tool = data["tools"]
    fleet = {}
    for key, spec in data["variants"].items():
        if key.startswith("_"):
            continue
        if "file" in spec:
            with open(os.path.join(HERE, "vehicles", spec["file"])) as fh:
                fleet[key] = json.load(fh)
            continue
        spec = copy.deepcopy(spec)
        cars = int(spec.pop("train_cars", 1))
        spec["tool"] = copy.deepcopy(base_tool[spec.pop("tool")])
        car = build(spec)
        fleet[key] = train(car, cars) if cars > 1 else car
    return fleet


if __name__ == "__main__":
    for key, v in load_fleet().items():
        d = v["drive"]
        u = d.get("units", 1)
        print("%-14s %-34s %4.0f kg  rated %5.0f N  peak %5.0f N  v_max %.1f m/s  %s"
              % (key, v["name"], v["mass_kg"] + v.get("ballast_kg", 0), d["rated_force_n"] * u,
                 d["peak_force_n"] * u, d["v_max_m_s"], "; ".join(v.get("bus", {}).get("warnings", []))))
