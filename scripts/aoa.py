"""Analysis of alternatives (Wasson ch. 32) for the unwind-brake concept.

Weighted scoring with linear utility functions, a +-10 % weight sensitivity check, a sweep of
the cost weight, and a re-ranking under changed assumed parameters.  Inputs come from
results/summary.json (scripts/run_study.py); the judgement scores are entered here with
their reasons (Wasson p.694: check the arithmetic; P32.5: an undocumented trade study is
opinion).

    python scripts/aoa.py   ->  results/aoa.md
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from captension import metrics, sim  # noqa: E402
from captension.params import BASE  # noqa: E402

RES = ROOT / "results"
ALTS = ["A", "B", "C", "D", "E"]


def utility(x: float, worst: float, best: float) -> float:
    """Linear utility, 0 at `worst`, 1 at `best`, clipped (Wasson Fig. 32.9, linear profile)."""
    return float(min(max((x - worst) / (best - worst), 0.0), 1.0))


def rank(scores: dict, weights: dict) -> list[tuple[str, float]]:
    tot = sum(weights.values())
    out = [(a, sum(weights[k] * s[k] for k in weights) / tot * 100) for a, s in scores.items()]
    return sorted(out, key=lambda t: -t[1])


def sensitivity(scores, weights) -> list[str]:
    base = rank(scores, weights)[0][0]
    notes = []
    for k, f in itertools.product(weights, (0.9, 1.1)):
        w = dict(weights)
        w[k] *= f
        win = rank(scores, w)[0][0]
        if win != base:
            notes.append(f"weight '{k}' x{f}: winner changes {base} -> {win}")
    return notes or [f"no single +-10 % weight change moves the winner away from {base}"]


JUDGE = {
    # maintainability and robustness (0..1) with the reason
    "A": (0.8, "simplest hardware, but each position needs re-setting by hand as the bobbin empties"),
    "B": (0.6, "no electronics; spring preload and band wear need periodic setting; hunts near the core"),
    "C": (0.6, "brake calibration drifts unseen; no direct break detection; needs a bobbin-change interlock"),
    "D": (0.7, "8 sensors to calibrate yearly, but they show every cord, detect breaks and log the data"),
    "E": (0.5, "8 servo axes with STO and holding brakes; most parts, most skills needed"),
}


def build(S: dict, steady_scale: dict | None = None, cost_scale: dict | None = None):
    raw, sc = {}, {}
    st = S["steady"]
    tr = S["transients"]
    br = S["breaks"]
    cost = S["cost"]
    for a in ALTS:
        p99 = st[a]["metrics"]["p99_dev"] * (steady_scale or {}).get(a, 1.0)
        pre = st[a]["metrics"]["prestrain_p99"] * (steady_scale or {}).get(a, 1.0)
        pk = max(tr[s][a]["peak_max"] for s in ("start", "stop", "estop"))
        lo = min(tr[s][a]["min_min"] for s in ("start", "stop", "estop"))
        b = br[a]["total"] / br["D"]["total"]
        capex = cost[a]["capex"] * (cost_scale or {}).get(a, 1.0)
        raw[a] = {"steady": f"{100 * p99:.1f} %", "transient": f"{pk:.2f} / {lo:.2f}",
                  "pre-strain": f"{100 * pre:.2f} %", "breaks": f"{b:.2f} x D", "cost": f"{capex / 1000:.1f} kEUR",
                  "maintainability": f"{JUDGE[a][0]:.1f}"}
        sc[a] = {
            "steady": utility(p99, 0.50, 0.02),
            "transient": min(utility(pk, 2.0, 1.1), utility(lo, 0.0, 0.9)),
            "pre-strain": utility(pre, 0.02, 0.003),
            "breaks": utility(b, 1.3, 1.0),
            "cost": utility(capex, 40000.0, 0.0),
            "maintainability": JUDGE[a][0],
        }
    return sc, raw


WEIGHTS = {"steady": 25, "transient": 15, "pre-strain": 15, "breaks": 10, "cost": 20, "maintainability": 15}


def table(sc, raw, weights) -> str:
    keys = list(weights)
    rows = ["| alternative | " + " | ".join(f"{k} ({weights[k]})" for k in keys) + " | FOM |",
            "|" + "---|" * (len(keys) + 2)]
    for a, fom in rank(sc, weights):
        rows.append(f"| {a} | " + " | ".join(f"{sc[a][k]:.2f} ({raw[a][k]})" for k in keys) + f" | **{fom:.1f}** |")
    return "\n".join(rows)


def assumption_runs(S: dict) -> list[tuple[str, str, str]]:
    """Re-rank with steady metrics scaled by the quasi-static change under other assumptions."""
    p = BASE
    m = sim.draw_machines(p, 200, seed=11)
    rg = np.linspace(p.v("r_core") + 0.0009, p.v("r_full"), 30)

    def qs(pp):
        o = {}
        for a in ALTS:
            ss = sim.steady_state(pp, sim.ALTS[a], m_of(pp), rg)
            o[a] = metrics.steady_metrics(ss["T1"][None], pp.v("T_set"), pp.v("tol"), rg)["p99_dev"]
        return o

    def m_of(pp):
        mm = dict(m)
        z = (m["mu_g"] - p.v("mu_guide")) / p.v("mu_guide_sd")
        mm["mu_g"] = pp.v("mu_guide") + pp.v("mu_guide_sd") * z
        mm["G"] = np.exp(mm["mu_g"] * pp.v("wrap"))
        mm["K_err"] = m["K_err"] * pp.v("MPB_gain_cv") / p.v("MPB_gain_cv")
        mm["A_f"] = np.exp(np.log(m["A_f"]) * pp.v("A_mu_cv") / p.v("A_mu_cv"))
        mm["s_off"] = m["s_off"] * pp.v("sens_cal_fs") / p.v("sens_cal_fs")
        return mm

    base = qs(p)
    cases = [
        ("guide mu spread 0.01 (polished, identical guides)", p.with_values(mu_guide_sd=0.01)),
        ("guide mu spread 0.08 (worn guides)", p.with_values(mu_guide_sd=0.08)),
        ("guide wrap halved", p.with_values(wrap=0.8)),
        ("brake gain spread 2 % (calibrated brakes)", p.with_values(MPB_gain_cv=0.02)),
        ("brake gain spread 12 %", p.with_values(MPB_gain_cv=0.12)),
        ("friction-brake spread 5 %", p.with_values(A_mu_cv=0.05)),
        ("compensator gain beta 10", p.with_values(B_beta=10.0)),
        ("sensor calibration 3x worse", p.with_values(sens_cal_fs=0.009)),
    ]
    out = []
    win0 = rank(build(S)[0], WEIGHTS)[0][0]
    for name, pp in cases:
        new = qs(pp)
        scale = {a: new[a] / base[a] for a in ALTS}
        sc, _ = build(S, steady_scale=scale)
        r = rank(sc, WEIGHTS)
        out.append((name, " > ".join(f"{a} {f:.0f}" for a, f in r), "same winner" if r[0][0] == win0 else f"winner {r[0][0]}"))
    for name, cs in (("sensor and servo costs x1.5", {"D": 1.5, "E": 1.5}), ("sensor and servo costs x0.5", {"D": 0.5, "E": 0.5}),
                     ("mechanical options cost x2", {"A": 2.0, "B": 2.0})):
        sc, _ = build(S, cost_scale=cs)
        r = rank(sc, WEIGHTS)
        out.append((name, " > ".join(f"{a} {f:.0f}" for a, f in r), "same winner" if r[0][0] == win0 else f"winner {r[0][0]}"))
    return out


def main() -> None:
    S = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
    sc, raw = build(S)
    L = ["# Analysis of alternatives: unwind-brake concept", "",
         "Generated by `scripts/aoa.py` from `results/summary.json`. Method: Wasson ch. 32, 12 steps "
         "(p.689-690): 100-point weights, linear utilities (Fig. 32.9), +-10 % weight sensitivity (section 32.7). "
         "Everything is simulation.", "",
         "## Factors, weights and utility ranges", "",
         "| factor | weight | utility 0 at | utility 1 at | source of the raw value |", "|---|---|---|---|---|",
         "| steady: p99 of abs(T1/T_set - 1) over the bobbin | 25 | 50 % | 2 % | study section 3 |",
         "| transient: worst peak / lowest T1/T_set in start, stop, e-stop (cat. 1) | 15 | peak 2.0 or 0.0 | peak 1.1 and 0.9 | study section 4 |",
         "| pre-strain: p99 cord-to-cord strain spread at embedding | 15 | 2 % | 0.3 % | study section 3 |",
         "| breaks: expected breaks relative to D | 10 | 1.3 | 1.0 | study section 5 |",
         "| cost: 8 positions + engineering | 20 | 40 kEUR | 0 | study section 13 |",
         "| maintainability (judgement, below) | 15 | 0 | 1 | this file |", "",
         "## Scores (utility, raw value in brackets)", "", table(sc, raw, WEIGHTS), "",
         "Judgement scores:", ""]
    for a in ALTS:
        L.append(f"- **{a}** {JUDGE[a][0]:.1f}: {JUDGE[a][1]}.")
    L += ["", "## Sensitivity to the weights", ""]
    L += [f"- {n}" for n in sensitivity(sc, WEIGHTS)]
    L += ["", "Cost weight swept from 5 to 60 (others scaled to keep 100):", "",
          "| cost weight | ranking |", "|---|---|"]
    for wc in (5, 10, 20, 30, 40, 50, 60):
        f = (100 - wc) / (100 - WEIGHTS["cost"])
        w = {k: (v * f if k != "cost" else wc) for k, v in WEIGHTS.items()}
        L.append(f"| {wc} | " + " > ".join(f"{a} {x:.0f}" for a, x in rank(sc, w)) + " |")
    L += ["", "## Sensitivity to assumed parameters", "",
          "Steady scores are rescaled by the change of the quasi-static p99 deviation under the changed "
          "assumption (200 machines); transient, break and judgement scores are kept.", "",
          "| assumption changed | ranking (FOM) | effect |", "|---|---|---|"]
    for name, r, eff in assumption_runs(S):
        L.append(f"| {name} | {r} | {eff} |")
    L.append("")
    (RES / "aoa.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
