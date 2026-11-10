"""All model parameters in one place, each with its source tag.

Tags (same convention as docs/sources/REFERENCES.md):
- read:     the value was read in the cited source;
- abstract: only an abstract, listing or search snippet was available;
- std:      a standard textbook result, section named, page not re-checked;
- derived:  computed in this repo from tagged values (the formula is named);
- assumed:  a modelling choice of this repo, carried in the TBD register with a sensitivity range.

`registry()` returns the rows of the sourced-vs-assumed table in DOSSIER section 8.2, so the
table and the code cannot drift apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace


@dataclass(frozen=True)
class P:
    value: float
    unit: str
    tag: str
    source: str
    note: str = ""
    lo: float | None = None  # sensitivity range (assumed values)
    hi: float | None = None


def _p(value, unit, tag, source, note="", lo=None, hi=None):
    return field(default=P(value, unit, tag, source, note, lo, hi))


@dataclass(frozen=True)
class Params:
    # ---------------------------------------------------------------- cord (nylon 6.6, 1400 dtex x1x2, dipped)
    cord_break_min: P = _p(206.0, "N", "read", "[M1] cord-fabric table, 1400 dtex x1x2 PA66", "minimum breaking strength")
    cord_elong_break: P = _p(0.22, "-", "read", "[M1]", "22 +- 2 %")
    cord_elong_20N: P = _p(0.035, "-", "read", "[M1]", "elongation at 20 N, 3.5 +- 1.5 %")
    cord_elong_39N: P = _p(0.065, "-", "read", "[M1]", "elongation at 39 N, 6.5 +- 1.5 %")
    cord_dia: P = _p(0.63e-3, "m", "read", "[M1]", "thickness 0.63 +- 0.03 mm, used as cord diameter")
    EA: P = _p(600.0, "N", "derived", "[M1] 20 N/3.5 % = 571 N secant, (39-20)/(6.5-3.5 %) = 633 N tangent",
               "load-elongation slope used in 0-40 N")
    EA_cv: P = _p(0.03, "-", "assumed", "", "cord-to-cord, from the +-1.5 % elongation tolerance band", 0.01, 0.06)
    cord_lin_density: P = _p(0.30e-3, "kg/m", "assumed", "2 x 1400 dtex = 0.28 g/m greige + ~7 % dip pick-up")
    fibre_density: P = _p(1140.0, "kg/m3", "std", "[T1] PA66 fibre density 1.14 g/cm3")
    tan_delta: P = _p(0.07, "-", "assumed", "", "cord loss factor near 2 Hz (Kelvin-Voigt damping)", 0.03, 0.12)
    strength_mean: P = _p(230.0, "N", "assumed", "", "mean > 206 N minimum; with CV 4 % the minimum is mean - 2.9 sigma")
    weibull_m: P = _p(30.0, "-", "derived", "m ~ 1.2/CV for CV 4 % (assumed CV)", "sound-cord strength", 15.0, 40.0)
    weibull_L0: P = _p(0.25, "m", "std", "[T2] ASTM D885 tensile test gauge length 250 mm (order)")
    # weak spots (defects) -- the breaks that actually happen at 5-10 % of nominal strength
    ws_density: P = _p(1.0, "1/km", "assumed", "", "weak spots per km of cord; scales all break counts linearly (TBD-6)", 0.1, 10.0)
    ws_tail_k: P = _p(2.0, "-", "assumed", "", "F_ws(s) = (s/S_ref)^k lower tail of weak-spot strength", 1.0, 4.0)
    ws_Sref: P = _p(206.0, "N", "derived", "= cord_break_min", "tail reference strength")

    # ---------------------------------------------------------------- bobbin
    r_core: P = _p(0.040, "m", "assumed", "", "bobbin core radius")
    r_full: P = _p(0.110, "m", "assumed", "", "full bobbin radius")
    bobbin_w: P = _p(0.20, "m", "assumed", "", "traverse width")
    pack_fill: P = _p(0.60, "-", "assumed", "", "volume fill of the package", 0.5, 0.7)
    J_core: P = _p(1.3e-3, "kg m2", "assumed", "", "core tube + spindle + brake rotor")
    M_bear: P = _p(0.02, "N m", "assumed", "", "bearing and seal drag of the spindle", 0.005, 0.05)
    M_bear_cv: P = _p(0.30, "-", "assumed", "", "bearing drag spread between positions")
    ecc: P = _p(0.2e-3, "m", "assumed", "", "package eccentricity (run-out) amplitude", 0.05e-3, 0.5e-3)

    # ---------------------------------------------------------------- line and path
    v_line: P = _p(1.0, "m/s", "assumed", "", "line speed 60 m/min (TBD-2)", 0.5, 2.0)
    t_ramp: P = _p(3.0, "s", "assumed", "", "start/stop ramp 0 <-> full speed", 1.0, 6.0)
    t_estop: P = _p(0.5, "s", "assumed", "", "line quick-stop time in an emergency stop", 0.2, 1.5)
    L0: P = _p(2.0, "m", "assumed", "", "bobbin -> first guide (creel span)")
    L1: P = _p(1.0, "m", "assumed", "", "last guide -> template")
    L2: P = _p(2.0, "m", "assumed", "", "template -> pull-off capstan")
    wrap: P = _p(1.6, "rad", "assumed", "", "total wrap on fixed guides, eyelets and comb (sum of angles)", 0.8, 3.0)
    mu_guide: P = _p(0.30, "-", "abstract", "[F1] PP on ceramic 0.32-0.42; [F2] nylon on nylon 0.40-0.47; value assumed in that band",
                     "", 0.20, 0.45)
    mu_guide_sd: P = _p(0.04, "-", "assumed", "", "position-to-position spread (wear, finish, contamination)", 0.01, 0.08)
    T_set: P = _p(15.0, "N", "assumed", "", "recipe tension per cord at the template entrance (TBD-1)", 8.0, 25.0)
    tol: P = _p(0.10, "-", "assumed", "", "tension tolerance +-10 % of set (TBD-1)")

    # ---------------------------------------------------------------- rubberising template (crosshead die)
    rheo_k: P = _p(0.9881e6, "Pa s^n", "read", "[R1] Ha et al. 2007, compound w6043, Table 1 (units assumed SI)")
    rheo_n: P = _p(0.2226, "-", "read", "[R1]")
    rheo_b: P = _p(0.0089, "1/K", "read", "[R1]", "temperature coefficient, reference 363 K")
    die_T: P = _p(363.0, "K", "assumed", "", "compound temperature in the template = reference temperature")
    die_land: P = _p(5.0e-3, "m", "assumed", "", "wetted land length per cord", 2e-3, 10e-3)
    die_gap: P = _p(0.30e-3, "m", "assumed", "", "radial gap cord to template bore", 0.15e-3, 0.5e-3)
    slip: P = _p(0.05, "-", "assumed", "[R2] wall slip of filled rubber; fraction of no-slip shear stress transmitted",
                 "", 0.02, 0.15)
    die_cv: P = _p(0.15, "-", "assumed", "", "cord-to-cord drag spread (bore wear, eccentricity)", 0.05, 0.30)
    die_overshoot: P = _p(1.5, "-", "assumed", "", "drag overshoot at restart (rested compound, stress overshoot)", 1.0, 2.5)
    die_os_len: P = _p(0.3, "m", "assumed", "", "cord travel over which the restart overshoot decays")

    # ---------------------------------------------------------------- brakes
    # A: constant-torque friction brake
    A_mu_cv: P = _p(0.12, "-", "assumed", "", "torque spread between positions (lining, spring setting, temperature)", 0.05, 0.25)
    mu_s_over_k: P = _p(1.3, "-", "assumed", "[B1] static > kinetic friction of brake linings", "", 1.1, 1.5)
    # B: dancer-compensated band brake
    B_beta: P = _p(4.0, "-", "assumed", "", "mechanical loop gain of the compensator at full bobbin (chosen from 2/4/10, study section 10)", 2.0, 10.0)
    B_arm: P = _p(0.15, "m", "assumed", "", "dancer arm length")
    B_Ks: P = _p(2.0, "N m/rad", "assumed", "", "dancer spring rate")
    B_Ia: P = _p(0.01, "kg m2", "assumed", "", "dancer arm + roller inertia")
    B_ca: P = _p(0.02, "N m s/rad", "assumed", "", "dancer damping (pivot friction; chosen from 0.02/0.05/0.15, study section 10)")
    B_preload_cv: P = _p(0.03, "-", "assumed", "", "spring preload setting spread between positions", 0.01, 0.06)
    B_band_mu_cv: P = _p(0.12, "-", "assumed", "", "band friction spread", 0.05, 0.25)
    B_travel: P = _p(0.40, "rad", "assumed", "", "dancer travel either side of centre")
    # C/D: magnetic-particle brake
    MPB_Mmax: P = _p(3.95, "N m", "read", "[B2] magnetic-particle brake B35 class, 0.07-3.95 N m")
    MPB_tau: P = _p(0.025, "s", "abstract", "[B2] data-sheet response 'unforced 25' (units ms inferred)", "", 0.014, 0.06)
    MPB_drag: P = _p(0.01, "-", "assumed", "[B3] hysteresis brake drag ~0.5 % of rating (abstract)", "residual drag, fraction of rating",
                     0.003, 0.03)
    MPB_hyst: P = _p(0.01, "-", "assumed", "[B2] 'brakes exhibit hysteresis' (no figure)", "torque hysteresis, fraction of rating",
                     0.0, 0.03)
    MPB_gain_cv: P = _p(0.06, "-", "assumed", "", "torque-per-ampere spread unit-to-unit and with temperature", 0.02, 0.12)
    enc_counts: P = _p(8192.0, "1/rev", "assumed", "", "spindle encoder 2048 ppr x4")
    # E: servo unwind
    E_tau: P = _p(0.002, "s", "assumed", "", "torque loop of a servo drive")
    E_gain_cv: P = _p(0.02, "-", "assumed", "", "torque accuracy of a servo drive")
    E_hold_M: P = _p(3.0, "N m", "assumed", "", "motor holding brake applied at STO (category 0)")
    E_hold_delay: P = _p(0.05, "s", "assumed", "", "holding-brake engage delay")

    # ---------------------------------------------------------------- tension sensor (3-roller)
    sens_range: P = _p(49.0, "N", "read", "[S1] 3-roller sensor, ranges 1-50 kg; 5 kg range", "")
    sens_acc_fs: P = _p(0.01, "-", "read", "[S1] accuracy +-1 % FS", "out of the box")
    sens_cal_fs: P = _p(0.003, "-", "assumed", "", "after in-situ two-point calibration with a reference weight")
    sens_drift: P = _p(0.001, "1/K", "read", "[S1] < +-0.1 % FS per degC")
    sens_dT: P = _p(5.0, "K", "assumed", "", "temperature swing at the creel after calibration")
    sens_bw: P = _p(30.0, "Hz", "read", "[S1] damping 30 Hz")
    sens_noise: P = _p(0.002, "-", "assumed", "", "noise RMS, fraction of FS")
    sens_spacing: P = _p(0.100, "m", "read", "[S1] outer roller spacing 100 mm up to 10 kg")
    sens_defl: P = _p(0.5e-3, "m", "read", "[S1] measuring-roller deflection max 0.5 mm")

    # ---------------------------------------------------------------- operation and economics
    shift_h: P = _p(8.0, "h", "assumed", "", "shift length")
    stops_per_shift: P = _p(6.0, "1/shift", "assumed", "", "normal stops incl. bobbin changes (TBD-3)", 2.0, 15.0)
    estops_per_shift: P = _p(0.5, "1/shift", "assumed", "", "emergency stops (TBD-3)", 0.1, 3.0)
    snag_len: P = _p(0.10, "m", "assumed", "", "overrun slack above which a loop can catch a guide or a neighbour", 0.05, 0.3)
    snag_p: P = _p(0.3, "-", "assumed", "", "probability that such a loop snags and breaks the cord at restart", 0.1, 0.8)
    hours_per_year: P = _p(5000.0, "h", "assumed", "", "production hours per year")
    cost_break: P = _p(25.0, "EUR", "assumed", "", "re-threading stop (3 min) + scrap strip per break", 10.0, 100.0)
    cost_A: P = _p(150.0, "EUR", "assumed", "", "friction brake + weight/spring per position")
    cost_B: P = _p(600.0, "EUR", "assumed", "", "dancer compensator with band brake per position")
    cost_C: P = _p(1150.0, "EUR", "derived", "[B4] MPB15 list price USD 600 (read); 4 N m size + amplifier 250 + encoder 120 + I/O 80 (assumed)")
    cost_D: P = _p(3030.0, "EUR", "assumed", "", "C + 3-roller sensor 1800 (quote only, assumed) + I/O 80", 2000.0, 4500.0)
    cost_E: P = _p(4400.0, "EUR", "assumed", "", "servo motor/gearbox/drive 2500 + sensor 1800 + I/O 100")
    eng_A: P = _p(0.0, "EUR", "assumed", "", "one-off engineering for 8 positions")
    eng_B: P = _p(1000.0, "EUR", "assumed", "")
    eng_C: P = _p(6000.0, "EUR", "assumed", "")
    eng_D: P = _p(8000.0, "EUR", "assumed", "")
    eng_E: P = _p(12000.0, "EUR", "assumed", "")

    # ---------------------------------------------------------------- PLC
    Ts: P = _p(0.010, "s", "assumed", "", "OB30 period (justified in DOSSIER section 7.1)")

    # ---------------------------------------------------------------- winder
    W_T: P = _p(40.0, "N", "assumed", "", "recipe strip tension at the winder (TBD-1)", 20.0, 80.0)
    W_taper: P = _p(0.20, "-", "assumed", "", "hyperbolic taper over the spool")
    W_rcore: P = _p(0.10, "m", "assumed", "", "spool core radius")
    W_rfull: P = _p(0.166, "m", "derived", "1000 m of 12 x 1.1 mm strip+liner on a 0.3 m traverse, fill 0.8")
    W_Jcore: P = _p(0.10, "kg m2", "assumed", "", "spool core + shaft")
    W_strip_mass: P = _p(0.016, "kg/m", "derived", "8 cords x 0.30 g/m + 12 x 1.0 mm x 1150 kg/m3 compound")
    W_strip_w: P = _p(0.012, "m", "assumed", "", "strip width")
    W_layer: P = _p(1.1e-3, "m", "assumed", "", "strip + liner thickness per layer")
    W_span: P = _p(3.0, "m", "assumed", "", "capstan -> winder span")
    W_tau: P = _p(0.005, "s", "assumed", "", "winder drive torque loop")
    W_fric: P = _p(0.5, "N m", "assumed", "", "winder friction torque")
    W_lc_fs: P = _p(200.0, "N", "assumed", "", "strip load-cell range")
    W_lc_acc: P = _p(0.005, "-", "assumed", "", "load-cell chain accuracy, fraction of FS")

    def v(self, name: str) -> float:
        return getattr(self, name).value

    def with_values(self, **kw: float) -> "Params":
        """Copy with some values replaced (tags kept), for sensitivity runs."""
        return replace(self, **{k: replace(getattr(self, k), value=float(x)) for k, x in kw.items()})


BASE = Params()


def registry(p: Params = BASE) -> list[tuple[str, P]]:
    return [(f.name, getattr(p, f.name)) for f in fields(p)]


def registry_markdown(p: Params = BASE) -> str:
    rows = ["| Parameter | Value | Unit | Status | Source / note | Sensitivity range |", "|---|---|---|---|---|---|"]
    for name, q in registry(p):
        rng = f"{q.lo:g} - {q.hi:g}" if q.lo is not None else ""
        src = "; ".join(s for s in (q.source, q.note) if s)
        rows.append(f"| `{name}` | {q.value:g} | {q.unit} | **{q.tag}** | {src} | {rng} |")
    return "\n".join(rows)


# ------------------------------------------------------------------ derived quantities

def cord_area(p: Params = BASE) -> float:
    """Solid cross-section of the cord, m2 (linear density / fibre density)."""
    return p.v("cord_lin_density") / p.v("fibre_density")


def guide_factor(mu: float, p: Params = BASE) -> float:
    """Capstan (Euler-Eytelwein) gain over all fixed guides: T_out/T_in = exp(mu * wrap) [T3]."""
    return math.exp(mu * p.v("wrap"))


def die_drag(v, p: Params = BASE):
    """Template drag on one cord, N, at cord speed v (m/s).

    Power-law shear stress at the cord surface, tau = slip * k * exp(-b (T - T0)) * (v/h)^n,
    over the wetted land: F = tau * pi * d * L_land.  Wire-coating analogue [R3]; slip factor
    and geometry are assumed (DOSSIER 8.2).
    """
    import numpy as np

    k = p.v("rheo_k") * math.exp(-p.v("rheo_b") * (p.v("die_T") - 363.0))
    gam = np.maximum(np.asarray(v, dtype=float), 0.0) / p.v("die_gap")
    tau = p.v("slip") * k * gam ** p.v("rheo_n")
    return tau * math.pi * p.v("cord_dia") * p.v("die_land")


def T_bobbin_nominal(p: Params = BASE) -> float:
    """Bobbin-side tension that gives T_set at the template entrance with nominal guides."""
    return p.v("T_set") / guide_factor(p.v("mu_guide"), p)
