"""Whole study: results/study.md, results/*.csv, results/summary.json, docs/img/*.png.

    python scripts/run_study.py            # full study, about 15 min on a laptop
    python scripts/run_study.py --quick    # small Monte Carlo, for a smoke test

Every number in README.md and DOSSIER.md that is not a parameter comes from this script.
All alternatives see the same machine draws and the same scenarios (paired comparisons).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from captension import bobbin, breaks, metrics, scl, sensor, sim, winder  # noqa: E402
from captension.params import BASE, die_drag, guide_factor, registry_markdown  # noqa: E402

RES = ROOT / "results"
IMG = ROOT / "docs" / "img"
COL = {"A": "#E69F00", "B": "#56B4E9", "C": "#009E73", "D": "#0072B2", "E": "#D55E00",
       "D_pre": "#CC79A7", "D_nodamp": "#7F7F7F", "C_cat0": "#66C2A5", "D_cat0": "#6BAED6", "E_cat0": "#FC8D62"}
MAIN = ["A", "B", "C", "D", "E"]
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 110})

p = BASE
TSET, TOL = p.v("T_set"), p.v("tol")
out: list[str] = []
summary: dict = {}


def md(s: str = "") -> None:
    out.append(s)


def table(head: list[str], rows: list[list]) -> None:
    md("| " + " | ".join(head) + " |")
    md("|" + "---|" * len(head))
    for r in rows:
        md("| " + " | ".join(str(x) for x in r) + " |")
    md()


def pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f} %"


# ============================================================================ stages

def stage_plausibility() -> None:
    md("## 1. Plant numbers and plausibility")
    md()
    G = guide_factor(p.v("mu_guide"), p)
    Leff = p.v("L0") + G * (p.v("L1") + p.v("L2"))
    rows = []
    for r in (p.v("r_full"), 0.075, 0.045):
        J = float(bobbin.inertia(r, p))
        fn = math.sqrt(p.v("EA") * r * r / (Leff * J)) / (2 * math.pi)
        frot = p.v("v_line") / (2 * math.pi * r)
        rows.append([f"{1000 * r:.0f} mm", f"{J * 1000:.2f}", f"{fn:.2f}", f"{frot:.2f}"])
    md(f"- Cord on a full bobbin: **{bobbin.capacity(p) / 1000:.1f} km**, {bobbin.mass(p):.2f} kg "
       f"(r {1000 * p.v('r_core'):.0f} -> {1000 * p.v('r_full'):.0f} mm, width {1000 * p.v('bobbin_w'):.0f} mm, fill {p.v('pack_fill')}); "
       f"{bobbin.capacity(p) / p.v('v_line') / 3600:.1f} h at {60 * p.v('v_line'):.0f} m/min.")
    md(f"- Guide gain G = exp(mu * wrap) = exp({p.v('mu_guide')} x {p.v('wrap')}) = **{G:.3f}**; "
       f"a position-to-position spread of mu of {p.v('mu_guide_sd')} gives a G spread of "
       f"{100 * p.v('mu_guide_sd') * p.v('wrap'):.1f} % (1 sigma).")
    md(f"- Template drag per cord at {p.v('v_line')} m/s: **{float(die_drag(p.v('v_line'), p)):.2f} N** "
       f"(power law n = {p.v('rheo_n')}: at 0.1 m/s it is still {float(die_drag(0.1, p)):.2f} N).")
    md(f"- Bobbin-side tension for {TSET:.0f} N at the template entrance: {TSET / G:.2f} N; brake torque "
       f"{TSET / G * p.v('r_full'):.2f} N m (full) to {TSET / G * p.v('r_core'):.2f} N m (core); turndown "
       f"{p.v('r_full') / p.v('r_core'):.2f}.")
    md(f"- Effective span length L0 + G (L1 + L2) = {Leff:.2f} m; span stiffness EA/L = {p.v('EA') / Leff:.0f} N/m.")
    md()
    md("Span resonance (bobbin inertia against the cord span) and bobbin rotation frequency:")
    md()
    table(["radius", "J (g m2)", "span resonance f_n (Hz)", "rotation at line speed (Hz)"], rows)
    md("The rotation frequency (the eccentricity excitation) stays 1.6-2.4 times above the span resonance over "
       "the whole bobbin, so eccentricity is not resonant here. The resonance itself is lightly damped (cord "
       "damping only) and a magnetic-particle brake adds no speed-dependent torque: ramps, stops and stick-slip "
       "excite it (sections 3, 4 and 10).")
    md()
    summary["capacity_km"] = bobbin.capacity(p) / 1000
    summary["G"] = G
    summary["D0"] = float(die_drag(p.v("v_line"), p))


def stage_quasistatic(n_mc: int) -> dict:
    md("## 2. Steady tension over a full bobbin (quasi-static)")
    md()
    md(f"{n_mc} machines x 8 positions, 40 radii from core to full; no dynamics (section 3 adds them). "
       "Tension at the template entrance T1, relative to the set value.")
    md()
    m = sim.draw_machines(p, n_mc, seed=11)
    rg = np.linspace(p.v("r_core") + 0.0009, p.v("r_full"), 40)
    res = {}
    rows = []
    for key in MAIN + ["D_pre"]:
        alt = sim.all_alts()[key]
        ss = sim.steady_state(p, alt, m, rg)
        T1 = ss["T1"][None]
        mt = metrics.steady_metrics(T1, TSET, TOL, rg, T2=ss["T2"][None], EA=m["EA"])
        res[key] = {"T1": ss["T1"], "T2": ss["T2"], "metrics": mt}
        rows.append([key, f"{100 * mt['bias']:+.1f} %", pct(mt["sd"]), pct(mt["p99_dev"]), pct(mt["spread_p99"]),
                     pct(mt["within"]), pct(mt["all8"]), f"{100 * mt['prestrain_p99']:.2f} %"])
    table(["alt.", "mean T1 vs set", "SD", "p99 deviation", "p99 spread of 8", "cord length within +-10 %",
           "time all 8 within", "p99 pre-strain spread at embedding"], rows)
    md("*Bias and spread are length-weighted over the bobbin. 'p99 spread of 8' is (max - min)/T_set across "
       "the 8 cords of one machine. The pre-strain spread is the difference of T2/EA between the cords "
       "where the rubber closes around them.*")
    md()
    # figure
    Lf = (p.v("r_full") ** 2 - rg ** 2) / (p.v("r_full") ** 2 - p.v("r_core") ** 2)
    fig, ax = plt.subplots(1, 1, figsize=(7.2, 3.8))
    for key in MAIN:
        r = res[key]["T1"] / TSET
        flat = r.reshape(len(rg), -1)
        ax.fill_between(100 * Lf, np.percentile(flat, 1, 1), np.percentile(flat, 99, 1), color=COL[key], alpha=0.15)
        ax.plot(100 * Lf, np.median(flat, 1), color=COL[key], lw=2, label=f"{key}: {sim.ALTS[key].label}")
    ax.axhspan(1 - TOL, 1 + TOL, color="k", alpha=0.06, lw=0)
    ax.set_xlabel("cord taken off the bobbin (%)")
    ax.set_ylabel("T1 / T_set at the template entrance")
    ax.set_ylim(0.4, 2.2)
    ax.legend(fontsize=7, loc="upper left", frameon=False)
    ax.set_title("Steady tension over one bobbin: median and 1-99 %% of 8 x %d cords (grey band: +-10 %%)" % n_mc,
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(IMG / "tension_over_bobbin.png")
    plt.close(fig)
    summary["quasistatic"] = {k: v["metrics"] for k, v in res.items()}
    return res


def run_set(alts: list[str], scen_name: str, radii, m, ecc: bool, **kw):
    out_ = {}
    for key in alts:
        t0 = time.time()
        out_[key] = sim.simulate(p, sim.all_alts()[key], m, radii, sim.scenario(scen_name, p), eccentric=ecc, **kw)
        print(f"  {scen_name:7s} {key:9s} {time.time() - t0:5.1f} s", flush=True)
    return out_


def break_summary(res, ks=(1.0, 2.0, 3.0, 4.0), baseline: bool = True):
    """Expected weak-spot breaks per cord (mean over cords, length-weighted radii) for several k."""
    ex = breaks.exposure(res, p)
    wr = metrics.radius_weights(res.radii)
    nr = len(res.radii)
    lam = p.v("ws_density") / 1000.0
    o = {"length": ex["length"]}
    T2ss = np.broadcast_to(res.ss["T2"], res.Tb.shape[1:]).reshape(-1)
    Tbss = np.broadcast_to(res.ss["Tb"], res.Tb.shape[1:]).reshape(-1)
    Dss = np.broadcast_to(res.ss["D"], res.Tb.shape[1:]).reshape(-1)
    G = np.broadcast_to(res.G, res.Tb.shape[1:]).reshape(-1)
    base_sh = np.stack([Tbss, 0 * Tbss, (G - 1) * Tbss, Dss, 0 * Dss], -1) / T2ss[:, None]
    for k in ks:
        F = breaks.F_ws(ex["Tmax"], p, k) * (ex["Tmax"] > 0)
        tot = lam * ex["d_sigma"] * F.sum(0)
        by = lam * ex["d_sigma"] * (F[..., None] * ex["shares"]).sum(0)
        if baseline:
            Fb = breaks.F_ws(T2ss, p, k)
            tot = tot - lam * ex["length"] * Fb
            by = by - lam * ex["length"] * Fb[:, None] * base_sh
        tot_r = tot.reshape(nr, -1).mean(1) @ wr
        by_r = by.reshape(nr, -1, 5).mean(1).T @ wr
        o[k] = {"total": float(tot_r), "by": by_r.tolist()}
    seg = np.bincount(ex["seg"].ravel(), weights=ex["Fmax"].ravel(), minlength=3)
    o["seg_share"] = (seg / max(seg.sum(), 1e-30)).tolist()
    return o


def stage_steady_dynamic(n_mc: int, quick: bool) -> dict:
    md("## 3. Steady running with package eccentricity (dynamic)")
    md()
    nb = 3 if quick else 6
    edges = np.linspace(p.v("r_core"), p.v("r_full"), nb + 1)
    radii = 0.5 * (edges[1:] + edges[:-1])
    md(f"{n_mc} machines x 8 cords at {nb} radii (centres of equal radius bins, length-weighted), "
       f"{p.v('v_line')} m/s, eccentricity {1000 * p.v('ecc'):.2f} mm x U(0.5, 1.5), 10 s after 2 s settling.")
    md()
    m = sim.draw_machines(p, n_mc, seed=21)
    alts = MAIN + ["D_pre", "D_nodamp"]
    R = run_set(alts, "steady", radii, m, True)
    rows = []
    stats = {}
    for key in alts:
        r = R[key]
        sel = r.t >= r.scen.window[0]
        mt = metrics.steady_metrics(r.T1[sel], TSET, TOL, radii, T2=r.T2[sel], EA=np.broadcast_to(m["EA"], r.T1.shape[1:]))
        rip = (r.T1[sel].max(0) - r.T1[sel].min(0)) / 2 / TSET  # (nr, mc, 8)
        bs = break_summary(r, baseline=False)
        per_km = {k: bs[k]["total"] / bs["length"] * 1e6 for k in (1.0, 2.0, 3.0, 4.0)}
        by_km = np.array(bs[2.0]["by"]) / bs["length"] * 1e6
        stats[key] = {"metrics": mt, "ripple_by_r": np.median(rip.reshape(len(radii), -1), 1).tolist(),
                      "ripple_p99": float(np.percentile(rip, 99)), "breaks_per_1000km": per_km,
                      "by_cause_1000km": by_km.tolist(), "seg_share": bs["seg_share"]}
        rows.append([key, f"{100 * mt['bias']:+.1f} %", pct(mt["p99_dev"]), pct(mt["spread_p99"]), pct(mt["within"]),
                     pct(mt["all8"]), pct(stats[key]["ripple_p99"]), f"{100 * mt['prestrain_p99']:.2f} %"])
    table(["alt.", "mean T1 vs set", "p99 deviation", "p99 spread of 8", "within +-10 %", "time all 8 within",
           "p99 ripple amplitude", "p99 pre-strain spread"], rows)
    md("D_nodamp is D with Kd = 0 and the same PI (Kp 0.3, Ti 0.8 s, section 10). "
       "Ripple amplitude is half the peak-to-peak of T1 over the 10 s window, per cord.")
    md()
    # resonance figure
    G = guide_factor(p.v("mu_guide"), p)
    Leff = p.v("L0") + G * (p.v("L1") + p.v("L2"))
    rr = np.linspace(p.v("r_core"), p.v("r_full"), 100)
    fn = np.sqrt(p.v("EA") * rr ** 2 / (Leff * bobbin.inertia(rr, p))) / (2 * np.pi)
    frot = p.v("v_line") / (2 * np.pi * rr)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.3))
    a1.plot(1000 * rr, fn, color="k", label="span resonance f_n")
    a1.plot(1000 * rr, frot, color="k", ls="--", label="bobbin rotation (eccentricity)")
    a1.set_xlabel("bobbin radius (mm)")
    a1.set_ylabel("Hz")
    a1.legend(frameon=False, fontsize=7)
    a1.set_title("Rotation frequency stays above the span resonance", fontsize=9)
    for key in alts:
        a2.plot(1000 * radii, 100 * np.array(stats[key]["ripple_by_r"]), "o-", color=COL[key], label=key, ms=3)
    a2.set_xlabel("bobbin radius (mm)")
    a2.set_ylabel("median ripple amplitude (% of T_set)")
    a2.set_yscale("log")
    a2.legend(frameon=False, fontsize=7, ncol=2)
    a2.set_title("Tension ripple from eccentricity", fontsize=9)
    fig.tight_layout()
    fig.savefig(IMG / "resonance.png")
    plt.close(fig)
    summary["steady"] = stats
    return {"R": R, "radii": radii, "stats": stats, "m": m}


def stage_transients(n_mc: int, quick: bool) -> dict:
    md("## 4. Start, stop and emergency stop")
    md()
    radii = np.array([0.104, 0.075, 0.046]) if not quick else np.array([0.104, 0.046])
    md(f"{n_mc} machines x 8 cords at radii {', '.join(f'{1000 * r:.0f}' for r in radii)} mm; ramps "
       f"{p.v('t_ramp')} s, emergency quick stop {p.v('t_estop')} s, restart after 2.5 s. No eccentricity here, "
       "so the numbers isolate the transient. Category 1 stop: the brakes keep power until standstill; "
       "category 0: the brake amplifiers lose power at once (EN 60204-1 stop categories).")
    md()
    m = sim.draw_machines(p, n_mc, seed=31)
    base = MAIN + ["D_pre", "D_nodamp"]
    out_ = {"radii": radii}
    for sc in ("start", "stop", "estop"):
        alts = base + (["C_cat0", "D_cat0", "E_cat0"] if sc == "estop" else [])
        R = run_set(alts, sc, radii, m, False)
        out_[sc] = {}
        rows = []
        for key in alts:
            r = R[key]
            tm = metrics.transient_metrics(r, TSET, TOL)
            bs = break_summary(r)
            out_[sc][key] = {"tm": tm, "breaks": bs}
            rows.append([key, f"{tm['peak_p50']:.2f}", f"{tm['peak_max']:.2f}", f"{tm['min_min']:.2f}",
                         f"{1000 * tm['slack_max']:.0f}", pct(tm["all8_frac"]), f"{tm['T2_peak']:.1f}"])
        md(f"### 4.{('start', 'stop', 'estop').index(sc) + 1} {sc}")
        md()
        table(["alt.", "peak T1/T_set (median machine)", "peak T1/T_set (worst)", "lowest T1/T_set", "max slack (mm)",
               "time all 8 within +-10 %", "highest T2 (N)"], rows)
        if sc == "estop":
            out_["estop_R"] = R
        if sc == "start":
            out_["start_R"] = R
    # figures: traces and e-stop slack
    fig, axs = plt.subplots(2, 2, figsize=(8.4, 5.2), sharex="col")
    for col, sc in enumerate(("start", "estop")):
        R = out_[sc + "_R"]
        for row, ri in enumerate((0, len(radii) - 1)):
            ax = axs[row, col]
            for key in MAIN:
                r = R[key]
                y = r.T1[:, ri, 0, :] / TSET
                ax.plot(r.t, y.max(1), color=COL[key], lw=1.0, label=key)
                ax.plot(r.t, y.min(1), color=COL[key], lw=1.0, ls=":")
            ax2 = ax.twinx()
            ax2.plot(R["A"].t, R["A"].v, color="0.6", lw=0.8)
            ax2.set_ylim(0, 4)
            ax2.set_yticks([])
            ax.set_title(f"{sc}, r = {1000 * radii[ri]:.0f} mm (solid max, dotted min of 8 cords; grey: speed)", fontsize=8)
            ax.set_ylabel("T1 / T_set")
            ax.set_ylim(0, 3.1)
            ax.axhspan(1 - TOL, 1 + TOL, color="k", alpha=0.06, lw=0)
            if row == 1:
                ax.set_xlabel("time (s)")
    axs[0, 0].legend(frameon=False, fontsize=7, ncol=5, loc="upper left")
    fig.tight_layout()
    fig.savefig(IMG / "transients.png")
    plt.close(fig)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.2))
    keys = MAIN + ["C_cat0", "D_cat0", "E_cat0"]
    x = np.arange(len(keys))
    for i, key in enumerate(keys):
        tm = out_["estop"][key]["tm"]
        a1.bar(i, 1000 * tm["slack_max"], color=COL[key])
        a2.bar(i, tm["peak_max"], color=COL[key])
    for a in (a1, a2):
        a.set_xticks(x)
        a.set_xticklabels(keys, rotation=45, fontsize=7)
    a1.set_yscale("symlog", linthresh=10)
    a1.set_ylabel("largest overrun slack (mm)")
    a1.set_title("Cord paid out after the capstan stopped", fontsize=9)
    a2.set_ylabel("peak T1 / T_set, incl. restart")
    a2.set_title("Peak tension: stop + restart (snatch)", fontsize=9)
    fig.tight_layout()
    fig.savefig(IMG / "estop.png")
    plt.close(fig)
    summary["transients"] = {sc: {k: {kk: (vv if not isinstance(vv, np.ndarray) else vv.tolist())
                                      for kk, vv in v["tm"].items() if kk != "slack_all"}
                                  for k, v in out_[sc].items()} for sc in ("start", "stop", "estop")}
    return out_


def stage_breaks(steady: dict, trans: dict, qs: dict) -> dict:
    md("## 5. Thread breaks: rate, location and cause")
    md()
    shifts = 1e6 / (p.v("v_line") * 3600 * p.v("shift_h"))
    n_stop = p.v("stops_per_shift") * shifts
    n_es = p.v("estops_per_shift") * shifts
    md(f"Weak spots: {p.v('ws_density')} per km with strength tail F(s) = (s/{p.v('ws_Sref'):.0f} N)^k, k = "
       f"{p.v('ws_tail_k'):.0f} (assumed; absolute counts scale linearly with the density, which the plant's "
       f"break log calibrates - FB_DataCollect). Per 1000 km of cord: {n_stop:.0f} normal stop/start cycles and "
       f"{n_es:.0f} emergency stops ({p.v('stops_per_shift'):.0f} and {p.v('estops_per_shift')} per "
       f"{p.v('shift_h'):.0f} h shift). Overrun slack above {1000 * p.v('snag_len'):.0f} mm snags with "
       f"probability {p.v('snag_p')} (assumed).")
    md()
    md(f"Sound cord: the weakest-link probability at 25 N over 1000 km is "
       f"{breaks.sound_cord_breaks(25.0, 1e6, p):.1e} (Weibull m = {p.v('weibull_m'):.0f}). **Every break needs a "
       "defect; what the machine decides is the tension the defect meets.**")
    md()
    res = {}
    rows = []
    for key in MAIN + ["D_pre", "C_cat0", "D_cat0", "E_cat0"]:
        base = key.split("_")[0] if key.endswith("cat0") else key
        st = steady["stats"][base]
        tot = {}
        for k in (1.0, 2.0, 3.0, 4.0):
            ev = trans["start"][base]["breaks"][k]["total"] + trans["stop"][base]["breaks"][k]["total"]
            es = trans["estop"][key]["breaks"][k]["total"]
            tot[k] = st["breaks_per_1000km"][k] + n_stop * ev + n_es * es
        # snag: per e-stop per cord
        sl = trans["estop"][key]["tm"]["slack_all"]  # (nr, mc, 8)
        wr = metrics.radius_weights(trans["radii"])
        psnag = float((sl > p.v("snag_len")).reshape(sl.shape[0], -1).mean(1) @ wr) * p.v("snag_p")
        snag = n_es * psnag
        by = np.array(st["by_cause_1000km"]) + n_stop * (np.array(trans["start"][base]["breaks"][2.0]["by"]) +
                                                         np.array(trans["stop"][base]["breaks"][2.0]["by"])) \
            + n_es * np.array(trans["estop"][key]["breaks"][2.0]["by"])
        total2 = tot[2.0] + snag
        res[key] = {"total": total2, "by": by.tolist(), "snag": snag, "k": {k: tot[k] + snag for k in tot},
                    "steady": st["breaks_per_1000km"][2.0], "events": tot[2.0] - st["breaks_per_1000km"][2.0],
                    "seg_share": st["seg_share"]}
        cause = by / max(by.sum(), 1e-12)
        rows.append([key, f"**{total2:.2f}**", f"{st['breaks_per_1000km'][2.0]:.2f}", f"{tot[2.0] - st['breaks_per_1000km'][2.0]:+.3f}",
                     f"{snag:.2f}"] + [pct(c, 0) for c in cause] +
                    [" / ".join(f"{100 * s:.0f}" for s in st["seg_share"])])
    table(["alt.", "breaks per 1000 km per cord", "steady running", "starts, stops, e-stops (net)", "overrun snags",
           "unwind steady", "unwind transient", "guides", "template steady", "template transient",
           "where (creel / guides-template / template-capstan, %)"], rows)
    md("Cause columns: Euler allocation of the weak-spot break probability to the parts of the tension at "
       "the place and moment each element saw its maximum (steady running and events together, without snags).")
    md()
    # sensitivity to the tail exponent
    rows = []
    for key in MAIN:
        rows.append([key] + [f"{res[key]['k'][k]:.3g}" for k in (1.0, 2.0, 3.0, 4.0)] +
                    [f"{res[key]['k'][3.0] / res['D']['k'][3.0]:.2f}"])
    md("Sensitivity to the weak-spot tail exponent k (breaks per 1000 km per cord; the ratio to D is what "
       "the comparison rests on):")
    md()
    table(["alt.", "k = 1", "k = 2", "k = 3", "k = 4", "ratio to D at k = 3"], rows)
    # levers (counterfactual, quasi-static, steady running, k = 2)
    md("**Levers (counterfactual, steady running, quasi-static over the bobbin, k = 2).** Change one thing, "
       "keep the alternative's control law, and count the steady breaks again:")
    md()
    m = sim.draw_machines(p, 300, seed=11)
    rg = np.linspace(p.v("r_core") + 0.0009, p.v("r_full"), 30)
    wr = metrics.radius_weights(rg)
    lam = p.v("ws_density")

    def steady_rate(pp, mm, key):
        ss = sim.steady_state(pp, sim.ALTS[key], mm, rg)
        F = breaks.F_ws(ss["T2"], pp, 2.0)
        return float(F.reshape(len(rg), -1).mean(1) @ wr) * lam * 1000

    levers = {
        "as designed": (p, m),
        "guides: no position spread": (p, {**m, "mu_g": np.full_like(m["mu_g"], p.v("mu_guide")),
                                           "G": np.full_like(m["G"], guide_factor(p.v("mu_guide"), p))}),
        "guides: wrap halved": (p.with_values(wrap=p.v("wrap") / 2), {**m, "G": np.exp(m["mu_g"] * p.v("wrap") / 2)}),
        "template drag halved": (p.with_values(slip=p.v("slip") / 2), m),
        "set tension -10 %": (p.with_values(T_set=0.9 * TSET), m),
    }
    rows = []
    lev = {}
    for name, (pp, mm) in levers.items():
        vals = [steady_rate(pp, mm, key) for key in MAIN]
        lev[name] = vals
        rows.append([name] + [f"{v:.2f}" for v in vals])
    base_vals = lev["as designed"]
    rows2 = [[r[0]] + [f"{100 * (lev[r[0]][i] / base_vals[i] - 1):+.0f} %" for i in range(len(MAIN))] for r in rows[1:]]
    table(["steady breaks per 1000 km"] + MAIN, rows)
    table(["change vs as designed"] + MAIN, rows2)
    md("With the tension held at the template entrance (D, E) the guides drop out: the loop makes up "
       "for any guide friction, so polishing guides changes the tension spread of A-C but not the breaks "
       "of D and E. The Euler share of the guides above says where the tension comes from, the levers say "
       "what changes the break count.")
    md()
    # figure
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    keys = MAIN + ["C_cat0", "D_cat0", "E_cat0"]
    bottom = np.zeros(len(keys))
    labels = list(breaks.CAUSES) + ["overrun snag"]
    colors = ["#0072B2", "#56B4E9", "#E69F00", "#009E73", "#99D8C9", "#D55E00"]
    for ci in range(6):
        vals = np.array([(res[k]["by"][ci] if ci < 5 else res[k]["snag"]) for k in keys])
        ax.bar(keys, vals, bottom=bottom, color=colors[ci], label=labels[ci])
        bottom += np.maximum(vals, 0)
    ax.set_ylabel("expected breaks per 1000 km per cord")
    ax.set_title(f"Breaks by cause (k = 2, {p.v('ws_density'):g} weak spot/km; absolute scale is assumed)", fontsize=9)
    ax.legend(frameon=False, fontsize=7, ncol=3)
    fig.tight_layout()
    fig.savefig(IMG / "breaks.png")
    plt.close(fig)
    summary["breaks"] = {k: {kk: vv for kk, vv in v.items()} for k, v in res.items()}
    summary["levers"] = lev
    return res


def stage_observer(steady: dict, trans: dict) -> None:
    md("## 6. Virtual (model-based) tension instead of a sensor")
    md()
    md("FB_ThreadBrake computes T_virtual = G_nom (M_est + J dw/dt + M_bear) / r_hat from the brake current, "
       "the encoder and the diameter estimate. Error against the true tension at the template entrance:")
    md()
    rows = []
    for key in ("C", "D"):
        r = steady["R"][key]
        sel = r.t >= r.scen.window[0]
        e = r.Tvirt[sel] / np.maximum(r.T1[sel], 0.5) - 1
        b = e.mean(0)
        rs = trans["start_R"][key]
        sel2 = (rs.t >= 4.5) & (rs.t <= 9.5) & (rs.v[:] > 0.1)
        e2 = rs.Tvirt[sel2] / np.maximum(rs.T1[sel2], 0.5) - 1
        rows.append([key, pct(float(np.abs(b).mean())), pct(float(np.percentile(np.abs(b), 99))),
                     pct(float(np.sqrt(((e - b) ** 2).mean()))), pct(float(np.percentile(np.abs(e2), 99)))])
    table(["alt.", "mean static error per cord", "p99 static error", "dynamic RMS (steady)", "p99 error during start ramp"], rows)
    md(f"The static error is the brake torque-per-ampere error ({pct(p.v('MPB_gain_cv'))} 1 sigma), the residual "
       f"drag and hysteresis, and the guide spread (G_nom is used for every position). None of these is "
       f"observable from current and speed alone in steady running, so the virtual tension cannot replace the "
       f"sensor for absolute accuracy (calibrated 3-roller sensor: {sensor.calibrated_sigma(p):.2f} N 1 sigma, "
       f"{100 * sensor.calibrated_sigma(p) / TSET:.1f} % of set). It does track the inertia term during ramps "
       f"and is useful as a plausibility check of the sensor and as the break detector of alternative C.")
    md()
    # figure
    rs = trans["start_R"]["D"]
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    for c, col in ((0, "#0072B2"), (3, "#D55E00")):
        ax.plot(rs.t, rs.T1[:, 0, 0, c], color=col, lw=1.2, label=f"true T1, cord {c + 1}")
        ax.plot(rs.t, rs.Tvirt[:, 0, 0, c], color=col, lw=1.0, ls="--", label=f"virtual, cord {c + 1}")
        ax.plot(rs.t, rs.Tmeas[:, 0, 0, c], color=col, lw=0.6, alpha=0.5, label=f"sensor (filtered), cord {c + 1}")
    ax.set_xlim(4.0, 11.0)
    ax.set_ylim(8, 22)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("N")
    ax.set_title("Start-up, alternative D, full bobbin: true, measured and virtual tension", fontsize=9)
    ax.legend(frameon=False, fontsize=6.5, ncol=3)
    fig.tight_layout()
    fig.savefig(IMG / "observer.png")
    plt.close(fig)


def stage_bobbin_change() -> None:
    md("## 7. Bobbin changed without pressing NewBobbin")
    md()
    m = sim.draw_machines(p, 8, seed=41)
    rows = []
    for key in ("C", "D"):
        r = sim.simulate(p, sim.ALTS[key], m, [0.104], sim.scenario("steady", p), eccentric=False, rhat0=0.045)
        rel = r.T1[:, 0] / TSET
        dev = np.abs(rel - rel[-1][None]).max(axis=(1, 2))
        out_t = r.t[dev > TOL]
        slack_t = r.t[(r.slack[:, 0] > 0).any(axis=(1, 2))]
        rows.append([key, f"{rel.min():.2f}", f"{(slack_t.max() - slack_t.min() if len(slack_t) else 0):.1f} s",
                     f"{(out_t.max() if len(out_t) else 0):.1f} s"])
    table(["alt.", "lowest T1/T_set", "time with slack cords", "back within +-10 % of its own steady value after"], rows)
    md(f"The diameter estimate starts at the old (near-empty) radius, 45 mm, on a 104 mm bobbin. v/omega disagrees "
       f"by more than 15 %, so it is rejected and, after ReseedTime = 1 s of consistent readings, used to re-seed "
       f"the estimate (FB_ThreadBrake, region Radius). Until then the brake torque is 45/104 of what it should "
       f"be; the speed-damping term, which uses v/r, is switched off after 0.1 s of a mismatch above 30 %. "
       f"Mitigation in the FMEA (section 9 of the dossier): a bobbin-present switch that pulses NewBobbin.")
    md()


def stage_knot() -> None:
    md("## 8. Knot or splice passing the comb and the template")
    md()
    m = sim.draw_machines(p, 8, seed=51)
    rows = []
    for key in MAIN:
        r = sim.simulate(p, sim.ALTS[key], m, [0.075], sim.scenario("knot", p), eccentric=False)
        sel = (r.t > 2.4) & (r.t < 3.3)
        rows.append([key, f"{r.T2[sel, 0, :, 0].max():.1f}", f"{r.T2[sel, 0, :, 1:].max():.1f}"])
    table(["alt.", "highest T2 on the knotted cord (N)", "highest T2 on the other cords (N)"], rows)
    md("Assumed knot forces: +2 N for 30 ms at the comb, +5 N for 20 ms in the template bore. The knot itself "
       "keeps 60-80 % of the cord strength (assumed), i.e. > 120 N, so a sound knot does not break; a knot is "
       "a weak spot of the kind section 5 counts.")
    md()


def stage_winder(quick: bool) -> None:
    md("## 9. Strip winder: transients and the recipe tension")
    md()
    radii = [p.v("W_rcore"), 0.133, p.v("W_rfull")]
    rows = []
    traces = {}
    for sc in ("start", "stop", "estop"):
        for cat in ((1, 0) if sc == "estop" else (1,)):
            o = winder.simulate_winder(p, sim.scenario(sc, p), radii, n_mc=4 if quick else 16, estop_cat=cat)
            rel = o["T"] / o["Tref"]
            sel = o["t"] >= 1.5
            traces[(sc, cat)] = o
            rows.append([f"{sc}{' cat 0' if cat == 0 else ''}", f"{rel[sel].max():.2f}", f"{rel[sel].min():.2f}",
                         f"{1000 * o['slack'].max():.0f}", f"{100 * rel[sel].max() * p.v('W_T') / (8 * p.v('EA')):.2f} %"])
    table(["scenario", "peak T/T_ref", "lowest T/T_ref", "slack (mm)", "peak strip strain"], rows)
    T_in = 8 * (TSET + summary["D0"])
    Tmin = winder.capstan_min_tension(T_in)
    Tw = np.array([15, 20, 25, 30, 40, 50, 60, 80.0])
    eff = winder.recipe_effects(p, Tw)
    rows = [[f"{t:.0f}", f"{100 * s:.2f} %", f"{pw / 1000:.1f}", f"{pb / 1e6:.2f}", "slips" if t < Tmin else "ok"]
            for t, s, pw, pb in zip(Tw, eff["strain"], eff["p_wrap"], eff["p_bound"])]
    md(f"Recipe tension window. The strip enters the capstan at about {T_in:.0f} N (8 x (T_set + drag)); "
       f"with green compound on steel mu = {winder.MU_CAPSTAN} over {winder.WRAP_CAPSTAN:.2f} rad the capstan "
       f"holds while T_w >= {Tmin:.1f} N.")
    md()
    table(["T_w (N)", "strip strain", "pressure under the last wrap (kPa)", "interlayer pressure bound at the core (MPa)", "capstan"], rows)
    md("The strain is what the strip loses in length when it relaxes on the building drum; the "
       "no-relaxation pressure bound is a gross over-estimate (it ignores the radial compliance of the green "
       "strip and the liner, Hakiel's model needs that modulus - TBD-9), but it scales linearly with the recipe "
       "tension, which is the point.")
    md()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.2))
    for (sc, cat), ls, lab in ((("start", 1), "-", "start"), (("estop", 1), "-", "e-stop cat 1"), (("estop", 0), ":", "e-stop cat 0")):
        o = traces[(sc, cat)]
        a1.plot(o["t"], o["T"][:, 0, 0], ls, lw=1, label=f"{lab}, core")
    a1.set_xlabel("time (s)")
    a1.set_ylabel("strip tension (N)")
    a1.legend(frameon=False, fontsize=7)
    a1.set_title("Winder strip tension (recipe 40 N, core)", fontsize=9)
    a2.plot(Tw, 100 * eff["strain"], "o-", color="#0072B2", label="strip strain (%)")
    a2.plot(Tw, eff["p_wrap"] / 1e4, "s-", color="#E69F00", label="last-wrap pressure (x10 kPa)")
    a2.axvline(Tmin, color="#D55E00", ls="--", lw=1)
    a2.text(Tmin + 1, 1.6, "capstan slips below", color="#D55E00", fontsize=7)
    a2.set_xlabel("recipe tension T_w (N)")
    a2.legend(frameon=False, fontsize=7)
    a2.set_title("What the recipe value changes", fontsize=9)
    fig.tight_layout()
    fig.savefig(IMG / "winder.png")
    plt.close(fig)
    summary["winder"] = {"T_in": T_in, "Tmin_capstan": Tmin, "rows": rows}


def stage_tuning(quick: bool) -> None:
    md("## 10. Tuning of the tension loop (alternative D)")
    md()
    if quick:
        md("(skipped in --quick)")
        md()
        return
    m = sim.draw_machines(p, 4, seed=61)
    sc = sim.scenario("start", p)
    rows = []
    for Kd in (0.0, 4.5, 9.0, 14.0):
        for Kp, Ti in ((0.3, 0.8), (0.6, 0.3), (1.0, 0.3)):
            r = sim.simulate(p, sim.ALTS["D"], m, [0.104, 0.075, 0.046], sc, tuning=dict(Kd=Kd, Kp=Kp, Ti=Ti))
            sel = r.t >= sc.window[0]
            e = np.abs(r.T1[sel] / TSET - 1)
            rows.append([f"{Kd:g}", f"{Kp:g}", f"{Ti:g}", pct(float(np.percentile(e, 99))), pct(float(e.max()))])
    table(["Kd", "Kp", "Ti (s)", "p99 |T1/T_set - 1| over the start", "worst"], rows)
    md("Kd is the speed-damping gain, scheduled as Kd r sqrt(J); Kd = 9 gives a damping ratio of about 0.5 "
       "at every radius. Without it no PI setting holds the cords inside +-10 % (100 % = the cord went slack). "
       "Chosen: Kd = 9, Kp = 0.3, Ti = 0.8 s (lowest p99 over the start).")
    md()
    md("**Compensator B** (mechanical loop gain beta at the full bobbin, arm damping c_a), 4 machines, "
       "radii 104/75/46 mm:")
    md()
    rows = []
    for beta in (2.0, 4.0, 10.0):
        for ca in (0.02, 0.05, 0.15):
            pp = p.with_values(B_beta=beta, B_ca=ca)
            mm = sim.draw_machines(pp, 4, seed=61)
            r1 = sim.simulate(pp, sim.ALTS["B"], mm, [0.104, 0.075, 0.046], sim.scenario("steady", pp))
            s1 = r1.t >= r1.scen.window[0]
            e1 = np.abs(r1.T1[s1] / TSET - 1)
            rip = (r1.T1[s1].max(0) - r1.T1[s1].min(0)) / 2 / TSET
            r2 = sim.simulate(pp, sim.ALTS["B"], mm, [0.104, 0.075, 0.046], sim.scenario("start", pp), eccentric=False)
            s2 = r2.t >= r2.scen.window[0]
            rows.append([f"{beta:g}", f"{ca:g}", pct(float(np.percentile(e1, 99))),
                         pct(float(np.median(rip[2]))), f"{r2.T1[s2].max() / TSET:.2f} / {r2.T1[s2].min() / TSET:.2f}"])
    table(["beta", "c_a (N m s/rad)", "steady p99 deviation", "median ripple near the core", "start peak / lowest"], rows)
    md("A high gain regulates the droop away but hunts near the core, where the bobbin is light; more arm "
       "damping slows the arm that closes the loop and makes it worse. Chosen: beta = 4, c_a = 0.02 "
       "(nearly the lowest steady p99, 27.7 % vs 26.4 % at c_a = 0.05, with a third of its ripple near the core).")
    md()


def stage_budget() -> None:
    md("## 11. PLC cycle budget (CPU 1513-1 PN)")
    md()
    fbs = scl.load(sorted(glob.glob(str(ROOT / "plc" / "FB_*.scl"))))
    ns = {"real": 256, "cmp": 256, "math": 20 * 256, "mov": 48, "int": 64}

    def cost(fb, setup, calls=1):
        inst = fbs[fb]()
        for k, v in setup.items():
            setattr(inst, k, v)
        inst()
        scl.reset_ops()
        for _ in range(calls):
            inst()
        ops = dict(scl.OPS)
        return ops, sum(ops[k] * ns[k] for k in ns) / 1000.0 / calls

    rows = []
    tot = 0.0
    items = [
        ("FB_ThreadBrake, closed loop, moving (x8)", "FB_ThreadBrake",
         dict(BrakeMode=2, LineSpeed=1.0, Omega=9.0, Tmeas=15.0, TmeasOk=True), 8),
        ("FB_WinderTension, run", "FB_WinderTension", dict(WinderMode=2, LineSpeed=1.0, OmegaW=7.0, StripT=38.0, StripTOk=True), 1),
        ("FB_LineSupervisor, run (loop over 8)", "FB_LineSupervisor", dict(EStopOk=True, StartReq=True), 1),
        ("FB_DataCollect, recording", "FB_DataCollect", {}, 1),
    ]
    for name, fb, setup, mult in items:
        ops, us = cost(fb, setup)
        rows.append([name, ops["real"] + ops["cmp"], ops["math"], ops["mov"], ops["int"], f"{us * mult:.1f}"])
        tot += us * mult
    # classification cycle: arm, post samples, freeze
    inst = fbs["FB_DataCollect"]()
    inst.PostSamples = 2
    inst.Tension[0] = 15.0
    for _ in range(3):
        inst()
    inst.Trigger = True
    inst.TriggerThread = 1
    inst()
    inst.Trigger = False
    scl.reset_ops()
    inst()
    assert inst.Frozen, "classification cycle not reached"
    ops = dict(scl.OPS)
    us_cls = sum(ops[k] * ns[k] for k in ns) / 1000.0
    rows.append(["FB_DataCollect, classification cycle (once per break)", ops["real"] + ops["cmp"],
                 ops["math"], ops["mov"], ops["int"], f"{us_cls:.1f}"])
    overhead = 12 * 2.0 + 4 * 24 * 0.048
    rows.append(["FB call overhead 12 x 2 us (assumed) + array parameters 96 moves", "", "", 96, "", f"{overhead:.1f}"])
    worst = tot + max(us_cls, 0) + overhead
    table(["block", "Real ops + compares", "SQRT/EXP", "moves", "int/loop", "us per OB30 call"], rows)
    md(f"Worst cycle (recording + classification + overhead): **{worst / 1000:.3f} ms**; with a 3x margin "
       f"([W] p.669) **{3 * worst / 1000:.2f} ms** of the 10 ms OB30 period, inside the 3 ms allocation "
       "(SPS-361). Times: 256 ns per floating-point operation, 64 ns per fixed-point operation and 48 ns "
       "per word move from the CPU 1513-1 PN data sheet [P1]; SQRT/EXP costed as 20 floating-point "
       "operations (assumed).")
    md()
    summary["budget_ms"] = worst / 1000
    summary["budget_margin_ms"] = 3 * worst / 1000
    # float32 radius prediction over a whole bobbin, prediction only (no v/omega correction)
    f = np.float32
    Kr = f(bobbin.Kr(p))
    n = int(bobbin.capacity(p) / 0.01)
    r1 = r2 = f(p.v("r_full"))
    L = f(0.0)
    rc2 = f(p.v("r_core") ** 2)
    dec = f(Kr * f(0.01))
    for _ in range(n):
        q = f(f(r1 * r1) - dec)
        r1 = f(np.sqrt(q)) if q > rc2 else f(p.v("r_core"))
        L = f(L + f(0.01))
        if L >= f(1.0):
            q = f(f(r2 * r2) - f(Kr * L))
            L = f(0.0)
            r2 = f(np.sqrt(q)) if q > rc2 else f(p.v("r_core"))
    true = float(bobbin.radius(n * 0.01, p))
    md(f"**float32 radius prediction over one bobbin** (prediction only, {n} cycles of 10 ms at 1 m/s): "
       f"updating r^2 every cycle ends at **{1000 * float(r1):.2f} mm**, updating once per metre at "
       f"**{1000 * float(r2):.3f} mm**; exact {1000 * true:.3f} mm. Per cycle the decrement of r^2 is only "
       f"{float(dec) / float(np.spacing(f(p.v('r_full') ** 2))):.0f} float32 ulps at the full bobbin, so rounding biases it. "
       "FB_ThreadBrake uses the per-metre update.")
    md()
    summary["float32_radius_mm"] = {"per_cycle": 1000 * float(r1), "per_metre": 1000 * float(r2), "exact": 1000 * true}


def stage_sensor(trans: dict) -> None:
    md("## 12. Measurement chain of the direct tension measurement")
    md()
    rows = [[n, f"{s:.3f}", f"{100 * s / TSET:.2f} %", b] for n, s, b in sensor.chain_budget(p)]
    table(["contribution", "1 sigma (N)", "of T_set", "basis"], rows)
    peak = max(trans["estop"]["D"]["tm"]["T2_peak"], trans["start"]["D"]["tm"]["T2_peak"])
    pk1 = max(trans["estop"]["D"]["tm"]["peak_max"], trans["start"]["D"]["tm"]["peak_max"]) * TSET
    md(f"- Calibrated chain: **{sensor.calibrated_sigma(p):.2f} N** (1 sigma) = {100 * sensor.calibrated_sigma(p) / TSET:.1f} % "
       f"of the set tension. Without in-situ calibration the +-1 % FS of a 49 N head alone is "
       f"+-{0.01 * p.v('sens_range'):.2f} N = +-{100 * 0.01 * p.v('sens_range') / TSET:.1f} % of set.")
    md(f"- Range: highest tension at the sensor in any category-1 scenario of D {pk1:.1f} N, inside the "
       f"{p.v('sens_range'):.0f} N range; resolution {1000 * sensor.resolution(p):.1f} mN per count.")
    md(f"- Bandwidth: 30 Hz head against a span resonance of 1-3 Hz and a 10 ms loop: adequate.")
    md(f"- Geometry: with 100 mm outer spacing and 10 mm deflection the head sees F = {sensor.gain(0.01, 0.1):.3f} T; "
       "the deflection adds two rotating rollers to the path (negligible friction), and the position after "
       "the last guide is the only place where each cord is still separate and already carries the guide "
       "friction (section 2, D vs D_pre).")
    md()
    _ = peak


def stage_cost(qs: dict, steady: dict, br: dict) -> None:
    md("## 13. Cost per position and over five years")
    md()
    hours = p.v("hours_per_year")
    km_per_cord_year = p.v("v_line") * 3600 * hours / 1000
    rows = []
    cst = {}
    for key in MAIN:
        capex = 8 * p.v(f"cost_{key}") + p.v(f"eng_{key}")
        b = br[key]["total"] * km_per_cord_year / 1000 * 8
        tco = capex + 5 * b * p.v("cost_break")
        cst[key] = {"capex": capex, "breaks_year": b, "tco5": tco}
        rows.append([key, f"{p.v(f'cost_{key}'):.0f}", f"{capex:.0f}", f"{b:.0f}", f"{5 * b * p.v('cost_break'):.0f}", f"{tco:.0f}"])
    table(["alt.", "per position (EUR)", "8 positions + engineering (EUR)", "breaks per year (8 cords)",
           "break cost, 5 years (EUR)", "total, 5 years (EUR)"], rows)
    md(f"{hours:.0f} h/year at {60 * p.v('v_line'):.0f} m/min = {km_per_cord_year:.0f} km per cord per year; "
       f"{p.v('cost_break'):.0f} EUR per break (assumed). Break counts use the assumed weak-spot density, so the "
       "break cost column is a scale, not a forecast.")
    md()
    # break-even weak-spot density between D and B (and C)
    for a, b in (("D", "B"), ("D", "C"), ("E", "D")):
        dcap = cst[a]["capex"] - cst[b]["capex"]
        dbr = (cst[b]["breaks_year"] - cst[a]["breaks_year"]) * 5 * p.v("cost_break")
        if dbr > 0:
            md(f"- {a} vs {b}: extra investment {dcap:.0f} EUR; pays back in 5 years if the weak-spot density is "
               f"at least **{p.v('ws_density') * dcap / dbr:.2g} per km** (break counts scale linearly with it).")
        else:
            md(f"- {a} vs {b}: extra investment {dcap:.0f} EUR and no fewer breaks: does not pay back on breaks.")
    md()
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for key in MAIN:
        y = steady["stats"][key]["metrics"]["p99_dev"]
        ax.scatter(cst[key]["capex"] / 1000, 100 * y, s=60, color=COL[key])
        ax.annotate(f"{key}", (cst[key]["capex"] / 1000, 100 * y), xytext=(6, 4), textcoords="offset points")
    ax.axhline(100 * TOL, color="k", lw=0.8, ls="--")
    ax.set_yscale("log")
    ax.set_xlabel("investment for 8 positions incl. engineering (kEUR)")
    ax.set_ylabel("p99 |T1 / T_set - 1| in steady running (%)")
    ax.set_title("What the money buys (dashed: +-10 % tolerance)", fontsize=9)
    fig.tight_layout()
    fig.savefig(IMG / "cost.png")
    plt.close(fig)
    summary["cost"] = cst


# ============================================================================ main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    quick = a.quick
    RES.mkdir(exist_ok=True)
    (RES / "cache").mkdir(exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    md("# Study results")
    md()
    md("Generated by `scripts/run_study.py`" + (" --quick (small Monte Carlo; not the published numbers)" if quick else "")
       + ". Everything here is **simulation**; no line data. Parameter status (read / abstract / std / derived / "
       "assumed) is in DOSSIER section 8.2 and in `captension.params`.")
    md()
    stage_plausibility()
    qs = stage_quasistatic(40 if quick else 500)
    st = stage_steady_dynamic(3 if quick else 32, quick)
    tr = stage_transients(3 if quick else 32, quick)
    br = stage_breaks(st, tr, qs)
    stage_observer(st, tr)
    stage_bobbin_change()
    stage_knot()
    stage_winder(quick)
    stage_tuning(quick)
    stage_budget()
    stage_sensor(tr)
    stage_cost(qs, st, br)
    md("## Parameter registry")
    md()
    md(registry_markdown(p))
    md()
    md(f"*Run time {time.time() - t0:.0f} s.*")
    (RES / ("study_quick.md" if quick else "study.md")).write_text("\n".join(out) + "\n", encoding="utf-8")

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        return o

    (RES / ("summary_quick.json" if quick else "summary.json")).write_text(json.dumps(clean(summary), indent=1), encoding="utf-8")
    with open(RES / "cache" / ("study_quick.pkl" if quick else "study.pkl"), "wb") as fh:
        pickle.dump(clean(summary), fh)
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
