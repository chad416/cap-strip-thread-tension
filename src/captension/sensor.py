"""Direct continuous tension measurement: 3-roller sensor design and measurement-chain budget.

Geometry: two fixed outer rollers at spacing s, the measuring roller in the middle deflects
the cord by h.  Each side turns the cord by alpha = atan(2h/s), the wrap on the measuring roller
is theta = 2 alpha and the force on it is
    F = 2 T sin(theta/2)                                  (static equilibrium of the roller)
so the sensor gain is F/T = 2 sin(alpha).  The vendor calibrates the head with its own
geometry; the formula is used here to size the range and to show how a geometry error enters.
"""

from __future__ import annotations

import math

from .params import BASE, Params


def gain(h: float, s: float) -> float:
    a = math.atan(2 * h / s)
    return 2 * math.sin(a)


def chain_budget(p: Params = BASE, T: float | None = None) -> list[tuple[str, float, str]]:
    """1-sigma contributions (N) at the operating tension T, and their basis."""
    T = p.v("T_set") if T is None else T
    FS = p.v("sens_range")
    u = 1 / math.sqrt(3)  # uniform -> 1 sigma
    rows = [
        ("Sensor accuracy out of the box (+-1 % FS)", p.v("sens_acc_fs") * FS * u, "read [S1]; replaced by the calibration below"),
        ("After two-point calibration with a reference weight (+-0.3 % FS)", p.v("sens_cal_fs") * FS * u, "assumed procedure"),
        ("Temperature drift 0.1 % FS/K over +-5 K", p.v("sens_drift") * p.v("sens_dT") * FS * u, "read rate [S1], assumed swing"),
        ("Noise 0.2 % FS RMS, averaged by the 30 Hz filter", p.v("sens_noise") * FS, "assumed"),
        ("Analog input card, 16 bit incl. sign, +-0.1 % FS", 0.001 * FS * u, "assumed typical S7-1500 AI"),
        ("Geometry: cord path offset 1 mm on h = 10 mm", T * abs(gain(0.011, 0.1) / gain(0.010, 0.1) - 1) * u,
         "derived from F = 2 T sin(theta/2); removed by calibrating in place"),
    ]
    return rows


def calibrated_sigma(p: Params = BASE) -> float:
    rows = chain_budget(p)
    keep = [r[1] for r in rows if not r[0].startswith(("Sensor accuracy out", "Geometry"))]
    return math.sqrt(sum(x * x for x in keep))


def resolution(p: Params = BASE) -> float:
    """N per count of a 27648-count S7 analog input over the sensor range."""
    return p.v("sens_range") / 27648.0
