"""Tyre grip and rolling resistance on soil (Brixius 1987 / ASAE D497).

Ported from zacharyelston/EOx ``src/eox/tyres.py`` (MIT) so the tethered-eOx sim
uses the same traction physics as the eOx calcs. Keep the two in step.

    Bn  = (CI b d / W) * (1 + 5 delta/h) / (1 + 3 b/d)
    GTR = 0.88 (1 - e^(-0.1 Bn)) (1 - e^(-7.5 s)) + 0.04     gross traction ratio
    MRR = 1/Bn + 0.04 + 0.5 s / sqrt(Bn)                     motion resistance ratio

Brixius is fitted to moderately compacted, non-sandy agricultural soils. On
loose sand it is optimistic about grip, so treat sand results as a best case.
"""
import math
from dataclasses import dataclass

G = 9.81


@dataclass
class Tyre:
    diameter: float      # mm
    width: float         # mm, section width
    rim: float           # mm, rim diameter
    pressure_kpa: float

    @property
    def section_height(self):
        return (self.diameter - self.rim) / 2


@dataclass
class Ground:
    cone_index_kpa: float
    design_slip: float = 0.12
    carcass_kpa: float = 15.0


def stiffness(t, ground):
    """Vertical stiffness, N/m."""
    return (t.pressure_kpa + ground.carcass_kpa) * 1000 * math.pi * math.sqrt(
        t.diameter / 1000 * t.width / 1000)


def deflection(t, load_n, ground):
    """Static deflection under load, mm."""
    return max(load_n, 0.0) / stiffness(t, ground) * 1000


def mobility(t, load_n, ground):
    W = max(load_n, 1.0)
    d, b = t.diameter / 1000, t.width / 1000
    delta_h = deflection(t, W, ground) / t.section_height
    return ground.cone_index_kpa * 1000 * b * d / W * (1 + 5 * delta_h) / (1 + 3 * b / d)


def grip(t, load_n, ground, slip=None):
    """Gross traction ratio at the design slip: the most the tyre pulls per unit load."""
    s = ground.design_slip if slip is None else slip
    Bn = mobility(t, load_n, ground)
    return 0.88 * (1 - math.exp(-0.1 * Bn)) * (1 - math.exp(-7.5 * s)) + 0.04


def rolling(t, load_n, ground):
    """Motion resistance ratio, free rolling."""
    return 1 / mobility(t, load_n, ground) + 0.04
