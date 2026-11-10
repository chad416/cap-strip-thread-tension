"""Physics, models and study building blocks."""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pytest

from captension import bobbin, breaks, sensor, sim, winder
from captension.control import BrakeCfg, WinderCfg
from captension.params import BASE, die_drag, guide_factor, registry

ROOT = Path(__file__).resolve().parents[1]
p = BASE


def test_every_parameter_is_tagged():
    for name, q in registry():
        assert q.tag in {"read", "abstract", "std", "derived", "assumed"}, name
        if q.tag in ("read", "abstract", "std"):
            assert q.source, name


def test_bobbin_geometry():
    L = bobbin.capacity(p)
    assert 14e3 < L < 16e3
    assert bobbin.radius(0.0, p) == pytest.approx(p.v("r_full"))
    assert bobbin.radius(L, p) == pytest.approx(p.v("r_core"), abs=1e-9)
    # inertia of a hollow cylinder: m (R^2 + r^2)/2 for the package
    m = L * p.v("cord_lin_density")
    Jpack = m * (p.v("r_full") ** 2 + p.v("r_core") ** 2) / 2
    assert bobbin.inertia(p.v("r_full"), p) - p.v("J_core") == pytest.approx(Jpack, rel=0.02)


def test_capstan_law_and_drag():
    assert guide_factor(0.3, p) == pytest.approx(math.exp(0.3 * p.v("wrap")))
    d1, d01 = float(die_drag(1.0, p)), float(die_drag(0.1, p))
    assert d1 / d01 == pytest.approx(10 ** p.v("rheo_n"), rel=1e-9)  # power law in speed
    assert float(die_drag(0.0, p)) == 0.0


def test_span_rate_reduces_to_koc_equation_for_one_segment():
    """L dT/dt = EA (v2 - v1) + T1 v1 - T v2 (Koc et al. 2002 / Vedrines & Knittel eq. 2)."""
    EA, L, T = 600.0, 3.0, 10.0
    v1, v2 = 1.0, 1.002
    rate, _ = sim.span_rate(np.array(T), v1, v2, 1.0, 0.0, 0.0, EA, L, 0.0, 0.0)
    koc = (EA * (v2 - v1) + 0.0 * v1 - T * v2) / L  # upstream (bobbin) strain zero
    assert float(rate) == pytest.approx(koc, rel=0.05)


def test_steady_states_follow_their_control_laws():
    m = sim.draw_machines(p, 3, seed=2)
    r = np.array([0.105, 0.06])
    A = sim.steady_state(p, sim.ALTS["A"], m, r)
    ratio = A["Tb"][1] / A["Tb"][0]  # constant torque: T ~ 1/r (bearing drag included)
    assert np.allclose(ratio, 0.105 / 0.06, rtol=1e-9)
    D = sim.steady_state(p, sim.ALTS["D"], m, r)
    assert np.allclose(D["T1"][0], p.v("T_set") - m["s_off"])  # the sensor's offset is the error
    B = sim.steady_state(p, sim.ALTS["B"], m, r)
    assert np.all(np.abs(B["phi"]) < p.v("B_travel"))


def test_dynamic_steady_matches_quasistatic():
    m = sim.draw_machines(p, 2, seed=3)
    for key in ("A", "C", "D"):
        res = sim.simulate(p, sim.ALTS[key], m, [0.08], sim.scenario("steady", p), eccentric=False)
        sel = res.t > 6
        assert np.allclose(res.T1[sel].mean(0), res.ss["T1"], rtol=0.01), key


def test_category0_estop_leaves_slack_and_category1_does_not():
    m = sim.draw_machines(p, 1, seed=4)
    sc = sim.scenario("estop", p)
    c1 = sim.simulate(p, sim.ALTS["D"], m, [0.104], sc, eccentric=False)
    c0 = sim.simulate(p, sim.all_alts()["D_cat0"], m, [0.104], sc, eccentric=False)
    assert c1.slack.max() == 0.0
    assert c0.slack.max() > 1.0


def test_closed_loop_holds_tolerance_through_start():
    m = sim.draw_machines(p, 2, seed=5)
    sc = sim.scenario("start", p)
    res = sim.simulate(p, sim.ALTS["D"], m, [0.104, 0.046], sc, eccentric=False)
    sel = res.t >= sc.window[0]
    assert np.abs(res.T1[sel] / p.v("T_set") - 1).max() < 0.15


def test_float32_radius_prediction_over_a_full_bobbin():
    """The per-metre prediction step of FB_ThreadBrake keeps float32 within 0.1 % (F13)."""
    f = np.float32
    Kr = f(bobbin.Kr(p))
    r, L, rc2 = f(p.v("r_full")), f(0.0), f(p.v("r_core") ** 2)
    n = int(bobbin.capacity(p) / 0.01 * 0.6)  # 60 % of a bobbin keeps the test short
    for _ in range(n):
        L = f(L + f(0.01))
        if L >= f(1.0):
            r2 = f(f(r * r) - f(Kr * L))
            L = f(0.0)
            r = f(np.sqrt(r2)) if r2 > rc2 else f(p.v("r_core"))
    true = float(bobbin.radius(n * 0.01, p))
    assert abs(float(r) / true - 1) < 1e-3


def test_range_max_matches_brute_force():
    rng = np.random.default_rng(1)
    a = rng.random((300, 5))
    rm = breaks._RangeMax(a)
    i0 = rng.integers(0, 300, 50)
    i1 = np.minimum(i0 + rng.integers(0, 120, 50), 299)
    mx, am = rm.query(i0, i1)
    for k in range(50):
        assert np.allclose(mx[k], a[i0[k]:i1[k] + 1].max(0))
        assert np.allclose(a[am[k], np.arange(5)], mx[k])


def test_breaks_constant_tension_equals_closed_form():
    m = sim.draw_machines(p, 1, seed=6)
    res = sim.simulate(p, sim.ALTS["D"], m, [0.075], sim.scenario("steady", p), eccentric=False)
    ex = breaks.exposure(res, p)
    e = breaks.expected(ex, p)
    T2 = res.T2[res.t > 3].mean(0).reshape(-1)
    closed = p.v("ws_density") / 1000 * ex["length"] * breaks.F_ws(T2, p)
    assert np.allclose(e["total"], closed, rtol=0.03)
    assert np.allclose(ex["shares"].sum(-1), 1.0)
    assert breaks.sound_cord_breaks(25.0, 1e6, p) < 1e-20


def test_sensor_and_winder_relations():
    assert sensor.gain(0.01, 0.1) == pytest.approx(2 * math.sin(math.atan(0.2)))
    assert winder.capstan_min_tension(100.0) == pytest.approx(100 * math.exp(-0.6 * math.pi))
    eff = winder.recipe_effects(p, np.array([40.0]))
    assert eff["strain"][0] == pytest.approx(40 / (8 * p.v("EA")))


def _scl_default(path: Path, name: str) -> float:
    m = re.search(rf"^\s*{name}\s*:\s*Real\s*:=\s*([-+0-9.Ee]+)", path.read_text(encoding="utf-8"), re.M)
    assert m, name
    return float(m.group(1))


def test_scl_defaults_match_design():
    """FB parameter defaults (used in OB30) equal the design values the study simulates."""
    cfg = sim.brake_cfg(p, sim.ALTS["D"])
    fb = ROOT / "plc" / "FB_ThreadBrake.scl"
    for name in ("Tset", "Gnom", "Rcore", "Rfull", "Jcore", "Jcoef", "Kr", "Mbear", "Kbrake", "Mdrag", "Kp", "Ti",
                 "Kd", "EStopDecel", "BrakeTau"):
        assert _scl_default(fb, name) == pytest.approx(getattr(cfg, name), rel=2e-3), name
    defaults = BrakeCfg()
    for name in ("Kp", "Ti", "Kd", "RadiusTf", "OmegaMin", "VMin", "CycleTime", "ReseedTime"):
        assert _scl_default(fb, name) == pytest.approx(getattr(defaults, name)), name
    wcfg = winder.winder_cfg(p)
    fw = ROOT / "plc" / "FB_WinderTension.scl"
    for name in ("Trecipe", "Taper", "Rcore", "Rmax", "Jcore", "Mfric", "EStopDecel"):
        assert _scl_default(fw, name) == pytest.approx(getattr(wcfg, name), rel=2e-3), name
    assert _scl_default(fw, "Jcoef") == pytest.approx(wcfg.Jcoef, rel=0.01)
    for name in ("Kp", "Kd", "Ti"):
        assert _scl_default(fw, name) == pytest.approx(getattr(WinderCfg(), name)), name
