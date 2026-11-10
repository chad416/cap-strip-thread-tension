"""Unwind -> guides -> rubberising template -> pull-off capstan, for 8 cords at once.

Model (DOSSIER section 8, where the equations are derived and sourced):

* Bobbin:  J(r) dw/dt + dJ/dt w = T_b r - M_brake - M_bear,   v_b = w (r + e sin(theta)).
* Cord path with three segments of free length L0 (bobbin -> guides, plus the dancer loop in
  alternative B), L1 (guides -> template) and L2 (template -> capstan).  Along the path the
  tension is  T_b,  T1 = G T_b  after the guides (capstan law, G = exp(mu * wrap)),  and
  T2 = T1 + D  after the template (drag D).  The unstretched cord length in the path is
      U = L0'/(1+eps_b) + L1/(1+eps_1) + L2/(1+eps_2),   eps = T/EA,
  and conservation of cord gives
      dU/dt = v_b - v_c/(1+eps_2),
  so  dT_b/dt = [v_b - v_c/(1+eps_2) - (dL0'/dt)/(1+eps_b) - dU/dD dD/dt] / (dU/dT_b)
  (cord leaves a relaxed package: wound-in strain zero).
  For one segment this is the web-span equation of Koc et al. (2002), written as eq. (2) in
  Vedrines & Knittel (2005), to first order in eps.  The cord carries Kelvin-Voigt damping
  (loss factor tan_delta).  If the tension would go negative the cord is slack and the slack
  length is integrated instead (overrun at an emergency stop); taking the slack up again is
  the snatch.
* Brakes A-E as in DOSSIER section 10.1 (stiction for the friction brakes, first-order lag,
  residual drag and hysteresis for the magnetic-particle brake, a servo torque loop for E).
* The PLC part of C, D and E is `control.ThreadBrakeVec`, the Python twin of FB_ThreadBrake,
  called every 10 ms with a quantised encoder and the 3-roller sensor model.

Arrays have shape (n_radius, n_machine, 8); everything is paired across alternatives: the
same machine draws and the same scenarios.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import bobbin
from .control import BrakeCfg, ThreadBrakeVec
from .params import BASE, Params, die_drag, guide_factor


# ---------------------------------------------------------------------------- alternatives

@dataclass(frozen=True)
class Alt:
    key: str
    kind: str  # A..E
    label: str
    sensor_after_guides: bool = True
    damping: bool = True
    estop_cat: int = 1


ALTS = {
    "A": Alt("A", "A", "Constant-torque friction brake"),
    "B": Alt("B", "B", "Dancer-compensated band brake (mechanical loop)"),
    "C": Alt("C", "C", "Magnetic-particle brake, diameter-compensated open loop"),
    "D": Alt("D", "D", "Magnetic-particle brake + tension sensor after the guides, PI"),
    "E": Alt("E", "E", "Servo unwind + tension sensor after the guides, PI"),
}
VARIANTS = {
    "D_pre": Alt("D_pre", "D", "D with the sensor at the creel, before the guides", sensor_after_guides=False),
    "D_nodamp": Alt("D_nodamp", "D", "D without the speed-damping term (Kd = 0)", damping=False),
    "C_cat0": Alt("C_cat0", "C", "C, emergency stop category 0 (brake loses power)", estop_cat=0),
    "D_cat0": Alt("D_cat0", "D", "D, emergency stop category 0 (brake loses power)", estop_cat=0),
    "E_cat0": Alt("E_cat0", "E", "E, emergency stop category 0 (STO + holding brake)", estop_cat=0),
}


def all_alts() -> dict[str, Alt]:
    return {**ALTS, **VARIANTS}


# ---------------------------------------------------------------------------- machine draws

def draw_machines(p: Params, n_mc: int, seed: int = 1) -> dict[str, np.ndarray]:
    """Random properties of n_mc machines x 8 positions (shared by all alternatives)."""
    rng = np.random.default_rng(seed)
    sh = (n_mc, 8)
    n = lambda: rng.standard_normal(sh)  # noqa: E731
    u = lambda: rng.uniform(-1.0, 1.0, sh)  # noqa: E731
    m = {
        "mu_g": np.clip(p.v("mu_guide") + p.v("mu_guide_sd") * n(), 0.05, 0.8),
        "EA": p.v("EA") * (1 + p.v("EA_cv") * n()),
        "die_f": np.exp(p.v("die_cv") * n() - 0.5 * p.v("die_cv") ** 2),
        "M_bear": p.v("M_bear") * np.clip(1 + p.v("M_bear_cv") * n(), 0.2, 3.0),
        "A_f": np.exp(p.v("A_mu_cv") * n() - 0.5 * p.v("A_mu_cv") ** 2),
        "B_mu": p.v("B_band_mu_cv") * n(),
        "B_pre": p.v("B_preload_cv") * n(),
        "K_err": p.v("MPB_gain_cv") * n(),
        "hyst": p.v("MPB_hyst") * p.v("MPB_Mmax") * u() * 0.5,
        "drag": p.v("MPB_drag") * p.v("MPB_Mmax") * (1 + 0.3 * n()),
        "E_err": p.v("E_gain_cv") * n(),
        "s_off": (p.v("sens_cal_fs") * u() + p.v("sens_drift") * p.v("sens_dT") * u()) * p.v("sens_range"),
        "ecc": p.v("ecc") * rng.uniform(0.5, 1.5, sh),
        "ecc_ph": rng.uniform(0, 2 * math.pi, sh),
        "enc_ph": rng.uniform(0, 1, sh),
        "noise_seed": rng.integers(0, 2 ** 31, size=1),
    }
    m["G"] = np.exp(m["mu_g"] * p.v("wrap"))
    return m


# ---------------------------------------------------------------------------- design constants

def brake_cfg(p: Params, alt: Alt) -> BrakeCfg:
    G = guide_factor(p.v("mu_guide"), p)
    cfg = BrakeCfg(
        Tset=p.v("T_set"), Gnom=G, Rcore=p.v("r_core"), Rfull=p.v("r_full"), Jcore=p.v("J_core"),
        Jcoef=bobbin.Jcoef(p), Kr=bobbin.Kr(p), Mbear=p.v("M_bear"), Kbrake=p.v("MPB_Mmax"), Imax=1.0,
        Mdrag=p.v("MPB_drag") * p.v("MPB_Mmax"), EStopDecel=p.v("v_line") / p.v("t_estop"),
        BrakeTau=p.v("MPB_tau"), CycleTime=p.v("Ts"),
    )
    if alt.kind == "E":
        cfg.Bidirectional = True
        cfg.Mdrag = 0.0
        cfg.BrakeTau = p.v("E_tau")
    if alt.kind == "D" and not alt.sensor_after_guides:
        cfg.Tset = p.v("T_set") / G   # controls the bobbin-side tension
        cfg.Gnom = 1.0
    if not alt.damping:
        cfg.Kd = 0.0   # same PI as D: the difference is the damping alone
    return cfg


def B_design(p: Params) -> dict[str, float]:
    """Dancer-compensated band brake, nominal design (DOSSIER 10.1, alternative B).

    Arm: 2*T*l_a = K_s*(phi0 + phi) at equilibrium; band: M = C_b*(phi_c - phi).
    Loop gain beta = 2 l_a C_b / (K_s r); C_b is chosen for beta = B_beta at the full bobbin and
    phi0 so the nominal mid-bobbin tension equals the set value.
    """
    la, Ks = p.v("B_arm"), p.v("B_Ks")
    Cb = p.v("B_beta") * Ks * p.v("r_full") / (2 * la)
    phic = 0.15
    rmid = 0.5 * (p.v("r_full") + p.v("r_core"))
    Tb = p.v("T_set") / guide_factor(p.v("mu_guide"), p)
    Mb = p.v("M_bear")
    # T = Ks (phi0 + phic + Mb/Cb) / (2 la + Ks r / Cb)  ->  phi0
    phi0 = Tb * (2 * la + Ks * rmid / Cb) / Ks - phic - Mb / Cb
    theta_b = 4.0
    return {"Cb": Cb, "phic": phic, "phi0": phi0, "la": la, "Ks": Ks, "theta_b": theta_b, "mu_b": 0.25}


def A_setting(p: Params) -> float:
    """Torque of the constant-torque brake: length-weighted mean tension = set value.

    Mean over the bobbin of M/r weighted by dL ~ r dr gives M * 2/(r_full + r_core).
    """
    Tb = p.v("T_set") / guide_factor(p.v("mu_guide"), p)
    return Tb * 0.5 * (p.v("r_full") + p.v("r_core")) - p.v("M_bear")


# ---------------------------------------------------------------------------- steady state

def steady_state(p: Params, alt: Alt, m: dict, r: np.ndarray, v: float | None = None) -> dict[str, np.ndarray]:
    """Static tensions of every cord at bobbin radius r (no dynamics, no ripple)."""
    v = p.v("v_line") if v is None else v
    r = np.asarray(r, float)[..., None, None] * np.ones_like(m["G"])
    G, EA, Mb = m["G"], m["EA"], m["M_bear"]
    D = m["die_f"] * die_drag(v, p)
    out: dict[str, np.ndarray] = {}
    k = alt.kind
    if k == "A":
        M = A_setting(p) * m["A_f"]
        Tb = (M + Mb) / r
    elif k == "B":
        b = B_design(p)
        f0 = math.exp(b["mu_b"] * b["theta_b"]) - 1
        Cb = b["Cb"] * (np.exp(b["mu_b"] * (1 + m["B_mu"]) * b["theta_b"]) - 1) / f0
        phi0 = (b["phi0"] + b["phic"]) * (1 + m["B_pre"]) - b["phic"]
        Tb = b["Ks"] * (phi0 + b["phic"] + Mb / Cb) / (2 * b["la"] + b["Ks"] * r / Cb)
        phi = 2 * Tb * b["la"] / b["Ks"] - phi0
        out["phi"] = phi
        M = Cb * (b["phic"] - phi)
    else:
        cfg = brake_cfg(p, alt)
        Kn = cfg.Kbrake
        Tb = np.full_like(r, p.v("T_set") / guide_factor(p.v("mu_guide"), p))
        sI = np.zeros_like(r)
        for _ in range(4):  # fixed point: r_hat = v/omega carries the cord strain at the capstan
            T2 = G * Tb + D
            rhat = r * (1 + T2 / EA)
            if k == "C":
                Mcmd = rhat * cfg.Tset / cfg.Gnom - cfg.Mbear
                I = np.clip((Mcmd - cfg.Mdrag) / Kn, 0, 1)
                M = Kn * (1 + m["K_err"]) * I + m["drag"] + m["hyst"]
                Tb = (M + Mb) / r
            else:
                FS = p.v("sens_range")
                Ttrue = cfg.Tset - m["s_off"]  # what the sensor location really carries
                Tb = Ttrue / (G if alt.sensor_after_guides else 1.0)
                M = Tb * r - Mb
                if k == "D":
                    I = (M - m["drag"] - m["hyst"]) / (Kn * (1 + m["K_err"]))
                    Icmd_M = Kn * I + cfg.Mdrag
                else:
                    I = M / (Kn * (1 + m["E_err"]))
                    Icmd_M = Kn * I
                sI = (Icmd_M - rhat * cfg.Tset / cfg.Gnom + cfg.Mbear) * cfg.Gnom / rhat
                _ = FS
        out["sI"] = sI * np.ones_like(r)
        out["rhat"] = rhat * np.ones_like(r)
    Tb = Tb * np.ones_like(r)
    M = M * np.ones_like(r)
    out["Tb"] = Tb
    out["T1"] = G * Tb
    out["T2"] = G * Tb + D
    out["M"] = M
    out["D"] = D * np.ones_like(Tb)
    return out


# ---------------------------------------------------------------------------- scenarios

PHASES = {"run": 0, "up": 1, "down": 2, "hold": 3, "estop": 4, "estop_hold": 5}


@dataclass
class Scenario:
    name: str
    t: np.ndarray
    v: np.ndarray
    a: np.ndarray
    phase: np.ndarray
    knot_t: float | None = None
    window: tuple[float, float] = (0.0, 1e9)


def scenario(name: str, p: Params = BASE, dt: float = 1e-3) -> Scenario:
    vn, tr, te = p.v("v_line"), p.v("t_ramp"), p.v("t_estop")
    segs = {
        "steady": [(12.0, "run")],
        "start": [(1.5, "run"), (tr, "down"), (1.5, "hold"), (tr, "up"), (4.0, "run")],
        "stop": [(2.0, "run"), (tr, "down"), (2.5, "hold")],
        "estop": [(2.0, "run"), (te, "estop"), (2.5, "estop_hold"), (tr, "up"), (5.0, "run")],
        "knot": [(7.0, "run")],
    }[name]
    T = sum(d for d, _ in segs)
    t = np.arange(0.0, T, dt)
    v = np.zeros_like(t)
    ph = np.zeros(t.shape, int)
    t0 = 0.0
    for d, kind in segs:
        sel = (t >= t0) & (t < t0 + d)
        x = (t[sel] - t0) / d
        v[sel] = {"run": vn, "up": vn * x, "down": vn * (1 - x), "hold": 0.0, "estop": vn * (1 - x),
                  "estop_hold": 0.0}[kind]
        ph[sel] = PHASES[kind]
        t0 += d
    a = np.gradient(v, dt)
    win = {"steady": (2.0, T), "start": (1.5 + tr + 1.0, T), "stop": (1.5, T), "estop": (1.5, T),
           "knot": (2.0, T)}[name]
    return Scenario(name, t, v, a, ph, knot_t=3.0 if name == "knot" else None, window=win)


# ---------------------------------------------------------------------------- dynamic simulation

def span_rate(Te, vb, vc, G, D, Ddot, EA, L0, L1, L2, dL0=0.0):
    """dT_b/dt of the three-segment cord path (module docstring) and dU/dT_b.

    U = L0/(1+eps_b) + L1/(1+eps_1) + L2/(1+eps_2) with eps = T/EA, T1 = G T_b, T2 = T1 + D;
    dU/dt = vb - vc/(1+eps_2): cord comes off a relaxed package (wound-in strain taken as zero,
    as T_0 = 0 in Koc et al.) and leaves at the capstan with the strain of the last segment.
    """
    eb = Te / EA
    e1 = G * Te / EA
    e2 = (G * Te + D) / EA
    dUdT = -(L0 / (1 + eb) ** 2 + L1 * G / (1 + e1) ** 2 + L2 * G / (1 + e2) ** 2) / EA
    dUdD = -L2 / (EA * (1 + e2) ** 2)
    flux = vb - vc / (1 + e2) - dL0 / (1 + eb) - dUdD * Ddot
    return flux / dUdT, dUdT


@dataclass
class SimResult:
    alt: Alt
    scen: Scenario
    radii: np.ndarray
    t: np.ndarray
    v: np.ndarray
    phase: np.ndarray
    Tb: np.ndarray
    T1: np.ndarray
    T2: np.ndarray
    D: np.ndarray
    w: np.ndarray
    slack: np.ndarray
    M: np.ndarray
    Tvirt: np.ndarray
    Tmeas: np.ndarray
    ss: dict = field(default_factory=dict)
    G: np.ndarray | None = None


def simulate(p: Params, alt: Alt, m: dict, radii, scen: Scenario, dt: float = 1e-3,
             rec_dt: float = 0.01, eccentric: bool = True, tuning: dict | None = None,
             rhat0: float | None = None) -> SimResult:
    """Simulate scenario `scen` for alternative `alt` at the bobbin radii `radii`.

    rhat0: start the diameter estimate of the PLC at this radius instead of the true one
    (a bobbin changed without the NewBobbin button).
    """
    radii = np.asarray(radii, float)
    nr = len(radii)
    S = (nr,) + m["G"].shape
    bc = lambda x: np.broadcast_to(x, S).copy()  # noqa: E731
    G, EA, Mbear = bc(m["G"]), bc(m["EA"]), bc(m["M_bear"])
    die_f = bc(m["die_f"])
    ecc = bc(m["ecc"]) if eccentric else np.zeros(S)
    ecc_ph = bc(m["ecc_ph"])
    L0, L1, L2 = p.v("L0"), p.v("L1"), p.v("L2")
    tau_d = p.v("tan_delta") / (2 * math.pi * 2.0)
    Kr = bobbin.Kr(p)
    kind = alt.kind
    rng = np.random.default_rng(int(m["noise_seed"][0]) + sum(map(ord, scen.name)))

    # ---- initial steady state at the first speed of the scenario
    v0 = scen.v[0]
    ss = steady_state(p, alt, m, radii, v=max(v0, 1e-3))
    r = np.broadcast_to(radii[:, None, None], S).copy()
    Te = ss["Tb"].copy()
    w = np.full(S, v0) / r / (1 + ss["T2"] / EA) if v0 > 0 else np.zeros(S)
    theta = bc(m["ecc_ph"]) * 0
    slack = np.zeros(S)
    stuck = np.zeros(S, bool) if v0 > 0 else np.ones(S, bool)
    J = bobbin.inertia(r, p)
    # brake-specific state
    phi = np.zeros(S)
    dphi = np.zeros(S)
    if kind == "A":
        Mset = A_setting(p) * bc(m["A_f"])
    if kind == "B":
        b = B_design(p)
        f0 = math.exp(b["mu_b"] * b["theta_b"]) - 1
        Cb = b["Cb"] * (np.exp(b["mu_b"] * (1 + bc(m["B_mu"])) * b["theta_b"]) - 1) / f0
        phi0 = (b["phi0"] + b["phic"]) * (1 + bc(m["B_pre"])) - b["phic"]
        phi = ss["phi"].copy()
        la, Ks, Ia, ca, trav = b["la"], b["Ks"], p.v("B_Ia"), p.v("B_ca"), p.v("B_travel")
    ctrl = None
    if kind in "CDE":
        cfg = brake_cfg(p, alt)
        for kk, vv in (tuning or {}).items():
            setattr(cfg, kk, vv)
        ctrl = ThreadBrakeVec(cfg, S)
        ctrl.sInit[:] = True
        ctrl.sR = ss["rhat"].copy() if rhat0 is None else np.full(S, rhat0)
        ctrl.sI = ss["sI"].copy()
        Kn = cfg.Kbrake
        if kind == "E":
            Kgain = Kn * (1 + bc(m["E_err"]))
            drag = np.zeros(S)
            hyst = np.zeros(S)
            tau_b = p.v("E_tau")
        else:
            Kgain = Kn * (1 + bc(m["K_err"]))
            drag, hyst = bc(m["drag"]), bc(m["hyst"])
            tau_b = p.v("MPB_tau")
        M_act = ss["M"].copy()
        I_cmd = ((M_act - drag - hyst) / Kgain) if kind != "E" else M_act / Kgain
        ctrl.sMest = Kn * I_cmd + cfg.Mdrag
        ctrl.sOmegaPrev = w.copy()
        s_off = bc(m["s_off"])
        enc_N = p.v("enc_counts")
        enc_cnt = np.floor(theta * enc_N / (2 * math.pi) + bc(m["enc_ph"]))
        Tsens = G * Te if alt.sensor_after_guides else Te.copy()
        hold_t = np.zeros(S)
    a_s = math.exp(-dt / (1 / (2 * math.pi * p.v("sens_bw"))))
    nplc = int(round(p.v("Ts") / dt))
    nrec = int(round(rec_dt / dt))
    n = len(scen.t)
    nout = (n + nrec - 1) // nrec
    rec = {k: np.zeros((nout,) + S, np.float32) for k in ("Tb", "T1", "T2", "D", "w", "slack", "M", "Tvirt", "Tmeas")}
    # die restart overshoot (common to all cords: the line speed is common)
    rest_t, x_since, armed = 0.0, 0.0, False
    D_prev = die_f * die_drag(v0, p)
    Lp_prev = None
    Tdot = np.zeros(S)
    M_brake = ss["M"].copy()
    I_power = True
    t_power_off = -1.0
    for k in range(n):
        tk = scen.t[k]
        v = scen.v[k]
        ph = scen.phase[k]
        # ---------------- template drag
        if v < 1e-4:
            rest_t += dt
            if rest_t > 1.0:
                armed, x_since = True, 0.0
        else:
            rest_t = 0.0
            if armed:
                x_since += v * dt
        osf = 1.0 + (p.v("die_overshoot") - 1.0) * math.exp(-x_since / p.v("die_os_len")) if armed else 1.0
        D = die_f * die_drag(v, p) * osf
        if scen.knot_t is not None and scen.knot_t <= tk < scen.knot_t + 0.02:
            D = D.copy()
            D[..., 0] += 5.0
        gknot = 0.0
        if scen.knot_t is not None and scen.knot_t - 0.5 <= tk < scen.knot_t - 0.47:
            gknot = 2.0  # knot passing the comb, 1 m upstream of the template
        Ddot = (D - D_prev) / dt
        D_prev = D
        # ---------------- PLC cycle
        if ctrl is not None and k % nplc == 0:
            power = not (alt.estop_cat == 0 and ph in (PHASES["estop"], PHASES["estop_hold"]))
            if not power and I_power:
                t_power_off = tk
            I_power = power
            enc_new = np.floor(theta * enc_N / (2 * math.pi) + bc(m["enc_ph"]))
            w_meas = (enc_new - enc_cnt) * 2 * math.pi / enc_N / p.v("Ts")
            enc_cnt = enc_new
            if kind == "C":
                Tm, ok = np.zeros(S), False
            else:
                noise = p.v("sens_noise") * p.v("sens_range") * rng.standard_normal(S)
                Tm, ok = np.clip(Tsens + s_off + noise, 0, p.v("sens_range")), True
            if ph in (PHASES["run"], PHASES["up"], PHASES["down"]):
                bmode = 1 if kind == "C" else 2
            elif ph == PHASES["hold"]:
                bmode = 3
            else:
                bmode = 4
            I_cmd = ctrl(bmode, v, scen.a[k], w_meas, Tm, ok)
            if not power:
                I_cmd = np.zeros(S)
        # ---------------- brake torque available (kinetic Mk, static Ms)
        if kind == "A":
            Mk = Mset
            Ms = Mset * p.v("mu_s_over_k")
        elif kind == "B":
            Mk = Cb * np.maximum(b["phic"] - phi, 0.0)
            Ms = Mk * p.v("mu_s_over_k")
        elif kind in "CD":
            target = Kgain * I_cmd + drag + hyst
            M_act += (target - M_act) * (1 - math.exp(-dt / tau_b))
            Mk = Ms = M_act
        else:  # E: servo; holding brake after STO in category 0
            target = Kgain * I_cmd
            M_act += (target - M_act) * (1 - math.exp(-dt / tau_b))
            Mk = M_act
            if not I_power and tk - t_power_off >= p.v("E_hold_delay"):
                Mk = np.full(S, p.v("E_hold_M"))
            Ms = np.maximum(Mk, 0.0)
        M_brake = Mk
        # ---------------- bobbin (symplectic: speed first)
        Tb_out = np.maximum(Te + tau_d * Tdot, 0.0)
        drive = Tb_out * r
        if kind == "E":
            free = stuck & (drive - Mk > Mbear)
        else:
            free = stuck & (drive > Ms + Mbear)
        stuck = stuck & ~free
        dJ = 4 * bobbin.Jcoef(p) * r ** 3 * (-Kr * w * r / (2 * r))
        wdot = (drive - Mk - Mbear - dJ * w) / J
        w_new = np.where(stuck, 0.0, w + wdot * dt)
        newly = w_new <= 0.0
        stuck = stuck | newly
        w = np.maximum(w_new, 0.0)
        theta = theta + w * dt
        vb = w * (r + ecc * np.sin(theta + ecc_ph))
        r = np.sqrt(np.maximum(r * r - Kr * vb * dt, p.v("r_core") ** 2))
        J = bobbin.inertia(r, p)
        # ---------------- dancer (B)
        dL0 = 0.0
        L0p = L0
        if kind == "B":
            ddphi = (2 * Tb_out * la - Ks * (phi0 + phi) - ca * dphi) / Ia
            dphi = dphi + ddphi * dt
            phi_new = phi + dphi * dt
            hit = (phi_new > trav) | (phi_new < -trav)
            phi_new = np.clip(phi_new, -trav, trav)
            dphi = np.where(hit, 0.0, dphi)
            dL0 = -2 * la * (phi_new - phi) / dt
            phi = phi_new
            L0p = L0 - 2 * la * phi
        # ---------------- span tension / slack
        Gk = G + gknot / np.maximum(Te, 1.0) if gknot else G
        rate, dUdT = span_rate(Te, vb, v, Gk, D, Ddot, EA, L0p, L1, L2, dL0)
        taut = slack <= 0.0
        Tdot = np.where(taut, rate, 0.0)
        Te_new = Te + Tdot * dt
        went_slack = taut & (Te_new < 0)
        slack = np.where(went_slack, -Te_new * (-dUdT), slack)
        Te = np.where(taut, np.maximum(Te_new, 0.0), Te)
        sl = ~taut
        sdot = vb - v / (1 + D / EA) - dL0
        s_new = slack + sdot * dt
        back = sl & (s_new < 0)
        Te = np.where(back, -s_new / (-dUdT), Te)
        slack = np.where(sl, np.maximum(s_new, 0.0), slack)
        Tdot = np.where(sl, 0.0, Tdot)
        Tb_out = np.maximum(Te + tau_d * Tdot, 0.0)
        # ---------------- sensor (3-roller after the guides, or at the creel)
        if ctrl is not None and kind != "C":
            Tloc = Gk * Tb_out if alt.sensor_after_guides else Tb_out
            Tsens = a_s * Tsens + (1 - a_s) * Tloc
        if k % nrec == 0:
            j = k // nrec
            rec["Tb"][j] = Tb_out
            rec["T1"][j] = Gk * Tb_out
            rec["T2"][j] = Gk * Tb_out + D
            rec["D"][j] = D
            rec["w"][j] = w
            rec["slack"][j] = slack
            rec["M"][j] = M_brake
            if ctrl is not None:
                rec["Tvirt"][j] = ctrl.Tvirtual
                rec["Tmeas"][j] = Tsens
    idx = np.arange(0, n, nrec)
    return SimResult(alt, scen, radii, scen.t[idx], scen.v[idx], scen.phase[idx], rec["Tb"], rec["T1"], rec["T2"],
                     rec["D"], rec["w"], rec["slack"], rec["M"], rec["Tvirt"], rec["Tmeas"], ss=ss, G=G)
