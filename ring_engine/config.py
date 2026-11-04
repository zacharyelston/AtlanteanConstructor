"""Parameter loading and validation for the Atlantean Berm & Ring Engine.

Reads ``params.json`` (or another file), applies dotted command-line overrides
such as ``rig.lifts=4``, and returns a validated :class:`Config`.
"""
import copy
import json
import math
import os
from dataclasses import dataclass, field
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PARAMS_PATH = os.path.join(HERE, "params.json")

SPEC_MIN_RESOLUTION = 512
MAX_CANAL_SLOPE_DEG = 33.0


@dataclass
class Moat:
    r_in: float
    r_out: float
    depth: float

    @property
    def width(self):
        return self.r_out - self.r_in


@dataclass
class Berm:
    r_in: float
    r_out: float
    height: Optional[float] = None      # None -> solved for mass balance
    source_moat: Optional[int] = None   # which moat feeds this berm

    @property
    def width(self):
        return self.r_out - self.r_in


@dataclass
class Config:
    raw: dict
    resolution: int
    extent: float
    hub_radius: float
    swell_factor: float
    repose_deg: float
    canal_slope_deg: float
    moats: List[Moat]
    berms: List[Berm]
    auto_size_berms: bool
    mast_height: float
    footprint_radius: float
    chute_radius: float
    bucket_capacity: float
    lifts: int
    path_mode: str
    revolutions_per_moat: Optional[float]
    pass_overlap: float
    path_step: float
    v_theta: float
    v_r: float
    v_tool_max: float
    production_rate_m3_hr: Optional[float]
    frames: int
    fps: int
    relax_every: int
    relax_window: float
    display_exaggeration: float = 3.0
    warnings: List[str] = field(default_factory=list)

    @property
    def tan_repose(self):
        return math.tan(math.radians(self.repose_deg))

    @property
    def tan_canal(self):
        return math.tan(math.radians(self.canal_slope_deg))

    @property
    def r_min(self):
        return min(m.r_in for m in self.moats)

    @property
    def r_max(self):
        return max([m.r_out for m in self.moats] + [b.r_out for b in self.berms])

    def moat_to_berm(self):
        """Map moat index -> list of berm indices that receive its spoil."""
        mapping = {i: [] for i in range(len(self.moats))}
        for k, b in enumerate(self.berms):
            mapping[b.source_moat].append(k)
        return mapping


def _coerce(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def apply_overrides(raw, overrides):
    """Apply ``section.key=value`` overrides (value parsed as JSON when possible)."""
    raw = copy.deepcopy(raw)
    for item in overrides or []:
        if "=" not in item:
            raise ValueError("Override must look like section.key=value, got %r" % item)
        path, value = item.split("=", 1)
        node = raw
        keys = path.strip().split(".")
        for key in keys[:-1]:
            if isinstance(node, list):
                node = node[int(key)]
            else:
                node = node.setdefault(key, {})
        last = keys[-1]
        if isinstance(node, list):
            node[int(last)] = _coerce(value)
        else:
            node[last] = _coerce(value)
    return raw


def load_config(path=None, overrides=None):
    path = path or DEFAULT_PARAMS_PATH
    with open(path, "r") as fh:
        raw = json.load(fh)
    raw = apply_overrides(raw, overrides)

    g, hub, soil = raw["grid"], raw["hub"], raw["soil"]
    rig, spd, anim = raw["rig"], raw["speeds"], raw["animation"]
    cfg = Config(
        raw=raw,
        resolution=int(g["resolution"]),
        extent=float(g["extent_m"]),
        hub_radius=float(hub["radius_m"]),
        swell_factor=float(soil["swell_factor"]),
        repose_deg=float(soil["angle_of_repose_deg"]),
        canal_slope_deg=float(soil["canal_side_slope_deg"]),
        moats=[Moat(float(m["r_in"]), float(m["r_out"]), float(m["depth"])) for m in raw["moats"]],
        berms=[Berm(float(b["r_in"]), float(b["r_out"]),
                    None if b.get("height") is None else float(b["height"]),
                    b.get("source_moat")) for b in raw["berms"]],
        auto_size_berms=bool(raw.get("balance", {}).get("auto_size_berms", True)),
        mast_height=float(rig["mast_height_m"]),
        footprint_radius=float(rig["footprint_radius_m"]),
        chute_radius=float(rig.get("chute_radius_m", rig["footprint_radius_m"])),
        bucket_capacity=float(rig["bucket_capacity_m3"]),
        lifts=int(rig["lifts"]),
        path_mode=str(rig.get("path_mode", "spiral")).lower(),
        revolutions_per_moat=rig.get("revolutions_per_moat"),
        pass_overlap=float(rig.get("pass_overlap", 0.25)),
        path_step=float(rig.get("path_step_m", 1.5)),
        v_theta=float(spd["v_theta_rad_s"]),
        v_r=float(spd["v_r_m_s"]),
        v_tool_max=float(spd.get("v_tool_max_m_s") or 1e9),
        production_rate_m3_hr=spd.get("production_rate_m3_hr"),
        frames=int(anim["frames"]),
        fps=int(anim.get("fps", 24)),
        relax_every=int(anim.get("relax_every_n_steps", 20)),
        relax_window=float(anim.get("relax_window_m", 14.0)),
        display_exaggeration=float(anim.get("display_exaggeration", 3.0)),
    )
    validate(cfg)
    return cfg


def validate(cfg):
    w = cfg.warnings
    if not cfg.moats:
        raise ValueError("At least one moat is required.")
    if not cfg.berms:
        raise ValueError("At least one berm is required to receive spoil.")
    if cfg.path_mode not in ("spiral", "stepped"):
        raise ValueError("rig.path_mode must be 'spiral' or 'stepped'.")
    if cfg.swell_factor < 1.0:
        w.append("Swell factor < 1.0 means soil compacts on extraction; check soil.swell_factor.")
    if cfg.resolution < SPEC_MIN_RESOLUTION:
        w.append("Grid resolution %d is below the spec minimum of %d (fine for quick previews)."
                 % (cfg.resolution, SPEC_MIN_RESOLUTION))
    if cfg.canal_slope_deg > MAX_CANAL_SLOPE_DEG:
        w.append("Canal side slope %.1f deg exceeds the %.0f deg spec limit."
                 % (cfg.canal_slope_deg, MAX_CANAL_SLOPE_DEG))
    if cfg.canal_slope_deg > cfg.repose_deg:
        w.append("Canal side slope (%.1f) is steeper than the angle of repose (%.1f); walls would slump."
                 % (cfg.canal_slope_deg, cfg.repose_deg))

    # Annuli must be ordered and non-overlapping (hub, moats, berms together).
    annuli = [("hub", 0.0, cfg.hub_radius)]
    annuli += [("moat %d" % i, m.r_in, m.r_out) for i, m in enumerate(cfg.moats)]
    annuli += [("berm %d" % i, b.r_in, b.r_out) for i, b in enumerate(cfg.berms)]
    for name, a, b in annuli:
        if b <= a:
            raise ValueError("%s has r_out <= r_in" % name)
    annuli.sort(key=lambda t: t[1])
    for (n1, _, b1), (n2, a2, _) in zip(annuli, annuli[1:]):
        if a2 < b1 - 1e-9:
            raise ValueError("%s overlaps %s (%.2f < %.2f)" % (n2, n1, a2, b1))
    if cfg.r_max >= cfg.extent:
        raise ValueError("Outermost ring (%.1f m) must lie inside the grid extent (%.1f m)."
                         % (cfg.r_max, cfg.extent))

    tb = cfg.tan_canal
    for i, m in enumerate(cfg.moats):
        if 2.0 * m.depth / tb > m.width:
            w.append("Moat %d is too narrow for depth %.2f m at %.0f deg slopes; it becomes V-shaped "
                     "and shallower than designed." % (i, m.depth, cfg.canal_slope_deg))

    # Pair every berm with a source moat (default: nearest moat on its inner side).
    for k, b in enumerate(cfg.berms):
        if b.source_moat is None:
            inner = [i for i, m in enumerate(cfg.moats) if m.r_out <= b.r_in]
            if inner:
                b.source_moat = max(inner, key=lambda i: cfg.moats[i].r_out)
            else:
                b.source_moat = min(range(len(cfg.moats)),
                                    key=lambda i: abs(cfg.moats[i].r_in - b.r_out))
        b.source_moat = int(b.source_moat)
        if not 0 <= b.source_moat < len(cfg.moats):
            raise ValueError("berm %d source_moat %d out of range" % (k, b.source_moat))
    fed = cfg.moat_to_berm()
    for i, targets in fed.items():
        if not targets:
            raise ValueError("Moat %d has no berm to receive its spoil; set berms[*].source_moat." % i)

    dx = 2.0 * cfg.extent / (cfg.resolution - 1)
    if cfg.footprint_radius < 1.5 * dx:
        w.append("Tool footprint (%.2f m) is under 1.5 grid cells (%.2f m); cuts may alias."
                 % (cfg.footprint_radius, dx))
    return cfg
