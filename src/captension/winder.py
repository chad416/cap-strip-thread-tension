"""Strip span capstan -> winder and the effect of the recipe tension.

* Span: the same conservation law as in sim.py with one segment; the strip leaves the
  (non-slipping) capstan with the strain of the cords upstream of it, sum(T2)/EA_strip.
* Spool: J_w(R) dw/dt = M_w - T R - M_fric;  J_w(R) = J_core + Jcoef (R^4 - R_core^4).
* Drive: torque loop with lag W_tau; the PLC part is control.WinderVec (= FB_WinderTension).
* Product effects (DOSSIER 8.6): strip strain eps = T/(8 EA) (green compound carries almost no
  load), pressure under the outermost wrap p = T/(w R) (exact for a membrane), a no-relaxation
  upper bound of the interlayer pressure at the core, and the capstan no-slip limit
  T_w >= T_in exp(-mu_c theta_c) (Euler-Eytelwein on the pull-off capstan).
"""

from __future__ import annotations

import math

import numpy as np

from .control import WinderCfg, WinderVec
from .params import BASE, Params

MU_CAPSTAN = 0.6   # green compound on a steel capstan, assumed (DOSSIER 8.2)
WRAP_CAPSTAN = math.pi


def winder_cfg(p: Params) -> WinderCfg:
    Jcoef = math.pi / 2 * p.v("W_strip_mass") / (p.v("W_strip_w") * p.v("W_layer")) * 0.3 * 0.8
    return WinderCfg(Trecipe=p.v("W_T"), Taper=p.v("W_taper"), Rcore=p.v("W_rcore"), Rmax=p.v("W_rfull"),
                     Jcore=p.v("W_Jcore"), Jcoef=Jcoef, Mfric=p.v("W_fric"),
                     EStopDecel=p.v("v_line") / p.v("t_estop"), CycleTime=p.v("Ts"))


def simulate_winder(p: Params, scen, radii, n_mc: int = 16, seed: int = 3, estop_cat: int = 1,
                    T_in: float = 145.0, dt: float = 1e-3, rec_dt: float = 0.01) -> dict:
    rng = np.random.default_rng(seed)
    cfg = winder_cfg(p)
    radii = np.asarray(radii, float)
    S = (len(radii), n_mc)
    R = np.broadcast_to(radii[:, None], S).copy()
    J_err = 1 + 0.10 * rng.standard_normal(S)
    fric = p.v("W_fric") * np.clip(1 + 0.3 * rng.standard_normal(S), 0.3, 2)
    lc_off = p.v("W_lc_acc") * p.v("W_lc_fs") * rng.uniform(-1, 1, S)
    EAs = 8 * p.v("EA")
    L = p.v("W_span")
    eps_in = T_in / EAs
    ctrl = WinderVec(cfg, S)
    ctrl.sInit[:] = True
    ctrl.sR = R.copy()
    Tref0 = cfg.Trecipe * (1 - cfg.Taper * (1 - cfg.Rcore / R))
    T = Tref0.copy()
    v0 = scen.v[0]
    w = v0 / R * (1 + T / EAs) / (1 + eps_in)
    Jw = (cfg.Jcore + cfg.Jcoef * (R ** 4 - cfg.Rcore ** 4)) * J_err
    M = T * R + fric
    ctrl.sI = (fric - cfg.Mfric) / R
    Mcmd = M.copy()
    nplc = int(round(p.v("Ts") / dt))
    nrec = int(round(rec_dt / dt))
    n = len(scen.t)
    out = {"T": [], "slack": [], "t": [], "v": [], "Tref": []}
    slack = np.zeros(S)
    power_off = False
    for k in range(n):
        v = scen.v[k]
        ph = scen.phase[k]
        if k % nplc == 0:
            mode = {0: 2, 1: 2, 2: 2, 3: 3, 4: 4, 5: 4}[int(ph)]
            power_off = estop_cat == 0 and ph in (4, 5)
            meas = T + lc_off + 0.002 * p.v("W_lc_fs") * rng.standard_normal(S)
            wm = w + 0.002 * rng.standard_normal(S)
            Mcmd = ctrl(mode, v, scen.a[k], wm, meas, True)
            if power_off:
                Mcmd = np.zeros(S)
        M += (Mcmd - M) * (1 - math.exp(-dt / p.v("W_tau")))
        resist = np.where(w > 0, fric, 0.0)
        wdot = (M - T * R - resist) / Jw
        w = np.maximum(w + wdot * dt, 0.0)
        vw = w * R
        eps = T / EAs
        taut = slack <= 0
        dUdT = -L / (EAs * (1 + eps) ** 2)
        flux = v / (1 + eps_in) - vw / (1 + eps)  # strip leaves the capstan with the upstream strain
        Tn = T + np.where(taut, flux / dUdT, 0.0) * dt
        went = taut & (Tn < 0)
        slack = np.where(went, -Tn * (-dUdT), slack)
        T = np.where(taut, np.maximum(Tn, 0.0), T)
        sl = ~taut
        sn = slack + (v - vw) * dt
        back = sl & (sn < 0)
        T = np.where(back, -sn / (-dUdT), T)
        slack = np.where(sl, np.maximum(sn, 0.0), slack)
        if k % nrec == 0:
            out["T"].append(T.copy())
            out["slack"].append(slack.copy())
            out["t"].append(scen.t[k])
            out["v"].append(v)
            out["Tref"].append(ctrl.Tref.copy())
    return {kk: np.array(vv) for kk, vv in out.items()}


def capstan_min_tension(T_in: float) -> float:
    """Smallest winder tension that keeps the pull-off capstan from slipping (capstan law)."""
    return T_in * math.exp(-MU_CAPSTAN * WRAP_CAPSTAN)


def recipe_effects(p: Params, T_w: np.ndarray) -> dict[str, np.ndarray]:
    T_w = np.asarray(T_w, float)
    EAs = 8 * p.v("EA")
    w = p.v("W_strip_w")
    Rc, Rf, t = p.v("W_rcore"), p.v("W_rfull"), p.v("W_layer")
    tap = p.v("W_taper")
    # tension along the spool with taper, outer-wrap pressure at the full spool
    Tfull = T_w * (1 - tap * (1 - Rc / Rf))
    p_wrap = Tfull / (w * Rf)
    # no-relaxation upper bound at the core: integral of T(R)/(w R) dR / t over the spool
    Rg = np.linspace(Rc, Rf, 400)
    TR = T_w[:, None] * (1 - tap * (1 - Rc / Rg[None, :]))
    p_bound = np.trapezoid(TR / (w * Rg[None, :]), Rg, axis=1) / t
    return {"strain": T_w / EAs, "p_wrap": p_wrap, "p_bound": p_bound}
