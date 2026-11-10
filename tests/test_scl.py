"""The SCL text that goes into TIA Portal, run with float32 Real, against the Python twins."""

from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pytest

from captension import scl, sim
from captension.control import BrakeCfg, ThreadBrakeVec, WinderCfg, WinderVec
from captension.params import BASE

ROOT = Path(__file__).resolve().parents[1]
FBS = scl.load(sorted(glob.glob(str(ROOT / "plc" / "FB_*.scl"))))


def test_all_blocks_translate():
    assert set(FBS) == {"FB_ThreadBrake", "FB_WinderTension", "FB_LineSupervisor", "FB_DataCollect"}


def _scl_brake(cfg: BrakeCfg):
    fb = FBS["FB_ThreadBrake"]()
    for k, v in cfg.scl_inputs().items():
        setattr(fb, k, np.float32(v) if isinstance(v, float) else v)
    return fb


def test_thread_brake_matches_reference_open_trace():
    """Random input trace through every mode: SCL (float32) == ThreadBrakeVec (float64)."""
    rng = np.random.default_rng(5)
    cfg = BrakeCfg()
    ref = ThreadBrakeVec(cfg, (1,))
    fb = _scl_brake(cfg)
    mode = 2
    r_true = 0.105
    for k in range(3000):
        if k % 250 == 0:
            mode = int(rng.integers(0, 5))
        if k == 1200:
            r_true = 0.06  # bobbin changed without NewBobbin: far outside the 15 % gate
        v = float(np.clip(1.0 + 0.3 * np.sin(k / 200), 0, 2)) if mode != 3 else 0.0
        w = v / r_true * (1 + rng.normal(0, 0.003))
        Tm = 15 + rng.normal(0, 0.5)
        ok = bool(rng.random() > 0.05)
        a = 0.1 * np.cos(k / 200)
        new = k == 2600
        ref(mode, v, a, np.array([w]), np.array([Tm]), ok, NewBobbin=new)
        fb.BrakeMode, fb.LineSpeed, fb.LineAccel, fb.Omega = mode, np.float32(v), np.float32(a), np.float32(w)
        fb.Tmeas, fb.TmeasOk, fb.NewBobbin = np.float32(Tm), ok, new
        fb()
        assert abs(float(fb.CurrentCmd) - ref.CurrentCmd[0]) < 2e-3, k
        assert abs(float(fb.Radius) - ref.Radius[0]) < 1e-5, k
        assert abs(float(fb.Tvirtual) - ref.Tvirtual[0]) < 0.05 * max(1.0, abs(ref.Tvirtual[0])), k
        assert bool(fb.Closed) == bool(ref.Closed[0])


class _SclBrakeArray:
    """Adapter: one SCL FB_ThreadBrake instance per cord, with the ThreadBrakeVec interface."""

    def __init__(self, cfg, shape):
        self.shape = shape
        self.n = int(np.prod(shape))
        self.fbs = [_scl_brake(cfg) for _ in range(self.n)]
        self.sInit = np.zeros(shape, bool)
        self.sR = np.full(shape, cfg.Rfull)
        self.sI = np.zeros(shape)
        self.sMest = np.zeros(shape)
        self.sOmegaPrev = np.zeros(shape)
        self.Tvirtual = np.zeros(shape)
        self._seeded = False

    def __call__(self, mode, v, a, w, Tm, ok, NewBobbin=False):
        if not self._seeded:
            for i, fb in enumerate(self.fbs):
                fb.sInit = bool(self.sInit.flat[i])
                fb.sR = np.float32(self.sR.flat[i])
                fb.sI = np.float32(self.sI.flat[i])
                fb.sMest = np.float32(self.sMest.flat[i])
                fb.sOmegaPrev = np.float32(self.sOmegaPrev.flat[i])
            self._seeded = True
        I = np.zeros(self.n)
        tv = np.zeros(self.n)
        Tm = np.broadcast_to(Tm, self.shape)
        for i, fb in enumerate(self.fbs):
            fb.BrakeMode, fb.LineSpeed, fb.LineAccel = int(mode), np.float32(v), np.float32(a)
            fb.Omega, fb.Tmeas, fb.TmeasOk = np.float32(w.flat[i]), np.float32(Tm.flat[i]), bool(ok)
            fb()
            I[i] = float(fb.CurrentCmd)
            tv[i] = float(fb.Tvirtual)
        self.Tvirtual = tv.reshape(self.shape)
        return I.reshape(self.shape)


@pytest.mark.parametrize("scen", ["start", "estop"])
def test_thread_brake_scl_closed_loop_matches_python(monkeypatch, scen):
    """The SCL block closing the loop on the cord model gives the same tensions as the twin."""
    p = BASE
    m = sim.draw_machines(p, 1, seed=7)
    sc = sim.scenario(scen, p)
    ref = sim.simulate(p, sim.ALTS["D"], m, [0.075], sc, eccentric=False)
    monkeypatch.setattr(sim, "ThreadBrakeVec", _SclBrakeArray)
    got = sim.simulate(p, sim.ALTS["D"], m, [0.075], sc, eccentric=False)
    d = np.abs(got.T1 - ref.T1)
    # float32 vs float64 over ~13 s of closed loop: the stick/slip instants of the bobbin at
    # standstill can shift by a step, so the peak difference is looser than the RMS one
    assert np.sqrt((d ** 2).mean()) < 0.05, np.sqrt((d ** 2).mean())
    assert d.max() < 0.5, d.max()
    assert abs(got.T1.max() - ref.T1.max()) < 0.02 * ref.T1.max()
    sel = got.t >= sc.window[0]
    assert np.abs(got.T1[sel] / p.v("T_set") - 1).max() < 0.40


def test_winder_matches_reference():
    rng = np.random.default_rng(9)
    cfg = WinderCfg()
    ref = WinderVec(cfg, (1,))
    fb = FBS["FB_WinderTension"]()
    for k, v in cfg.__dict__.items():
        setattr(fb, k, np.float32(v))
    mode = 2
    w = 7.0
    for k in range(2500):
        if k % 300 == 0:
            mode = int(rng.integers(0, 5))
        v = float(np.clip(1 + 0.2 * np.sin(k / 150), 0, 2))
        w = max(0.0, w + rng.normal(0, 0.05))
        T = 40 + rng.normal(0, 2)
        a = 0.05 * np.cos(k / 150)
        ref(mode, v, a, np.array([w]), np.array([T]), True)
        fb.WinderMode, fb.LineSpeed, fb.LineAccel = mode, np.float32(v), np.float32(a)
        fb.OmegaW, fb.StripT, fb.StripTOk = np.float32(w), np.float32(T), True
        fb()
        assert abs(float(fb.TorqueCmd) - ref.TorqueCmd[0]) < 2e-3 * max(1.0, abs(ref.TorqueCmd[0])), k
        assert abs(float(fb.Tref) - ref.Tref[0]) < 1e-3


def _sup(**kw):
    fb = FBS["FB_LineSupervisor"]()
    fb.EStopOk = True
    for i in range(8):
        fb.Tension[i] = np.float32(15.0)
        fb.TensionOk[i] = True
        fb.Radius[i] = np.float32(0.08)
    for k, v in kw.items():
        setattr(fb, k, v)
    return fb


def _run(fb, n, **kw):
    for _ in range(n):
        for k, v in kw.items():
            setattr(fb, k, v)
        for i in range(8):
            fb.Omega[i] = np.float32(float(fb.SpeedRef) / 0.08)
        fb()


def test_supervisor_start_run_stop():
    fb = _sup()
    _run(fb, 1, StartReq=True)
    assert fb.LineMode == 2 and fb.BrakeMode == 2
    _run(fb, 320, StartReq=False)
    assert fb.LineMode == 3 and abs(float(fb.SpeedRef) - 1.0) < 1e-5
    assert abs(float(fb.AccelRef)) < 1e-6
    _run(fb, 1, StopReq=True)
    assert fb.LineMode == 4
    _run(fb, 320, StopReq=False)
    assert fb.LineMode == 0 and fb.BrakeMode == 3 and float(fb.SpeedRef) == 0.0


def test_supervisor_estop_and_ack():
    fb = _sup()
    _run(fb, 320, StartReq=True)
    _run(fb, 1, StartReq=False, EStopOk=False)
    assert fb.LineMode == 5 and fb.BrakeMode == 4 and fb.WinderMode == 4
    _run(fb, 60)
    assert float(fb.SpeedRef) == 0.0
    _run(fb, 5, EStopOk=True)
    assert fb.LineMode == 5  # needs Ack
    _run(fb, 1, Ack=True)
    assert fb.LineMode == 0


def test_supervisor_break_detection_triggers_stop():
    fb = _sup()
    _run(fb, 320, StartReq=True)
    fb.Tension[4] = np.float32(1.0)
    trig = False
    for _ in range(10):
        _run(fb, 1, StartReq=False)
        trig = trig or bool(fb.Trigger)
    assert trig and fb.BreakThread == 5 and fb.LineMode == 4
    _run(fb, 400)
    assert fb.LineMode == 6
    _run(fb, 1, Ack=True)
    assert fb.LineMode == 0 and fb.BreakThread == 0


def test_supervisor_slack_inhibits_false_break_after_estop():
    fb = _sup()
    _run(fb, 320, StartReq=True)
    _run(fb, 1, StartReq=False, EStopOk=False)
    # bobbin 3 keeps turning after the capstan stopped: overrun slack
    for _ in range(60):
        fb.Omega[2] = np.float32(5.0)
        fb.Tension[2] = np.float32(0.0)
        fb()
    assert float(fb.SlackLen[2]) > 0.05 and fb.SlackFlag
    _run(fb, 1, EStopOk=True, Ack=True)
    fb.Ack = False
    fb.StartReq = True
    for _ in range(30):
        fb.Tension[2] = np.float32(0.0)
        fb.Omega[2] = np.float32(0.0)
        fb()
    assert fb.BreakThread == 0  # slack cord is not reported as broken


def _daq():
    fb = FBS["FB_DataCollect"]()
    return fb


def _feed(fb, n, T=15.0, mode=3, peak=None, thread=3):
    for k in range(n):
        for i in range(8):
            fb.Tension[i] = np.float32(T)
            fb.Current[i] = np.float32(0.3)
            fb.Radius[i] = np.float32(0.07)
        if peak is not None and k == n - 20:
            fb.Tension[thread - 1] = np.float32(peak)
        fb.LineMode = mode
        fb()


@pytest.mark.parametrize("mode,peak,slack,diep,cause", [
    (2, 25.0, False, 150.0, 1),
    (3, 25.0, True, 150.0, 2),
    (3, 25.0, False, 150.0, 3),
    (3, None, False, 190.0, 4),
    (3, None, False, 150.0, 5),
])
def test_datacollect_capture_and_classification(mode, peak, slack, diep, cause):
    fb = _daq()
    fb.DieTemp = np.float32(90.0)
    fb.DiePressure = np.float32(diep)
    _feed(fb, 450, mode=mode, peak=peak)
    fb.Trigger, fb.TriggerThread, fb.SlackFlag = True, 3, slack
    _feed(fb, 1, mode=mode)
    fb.Trigger = False
    _feed(fb, 98, mode=mode)
    assert not fb.Frozen
    _feed(fb, 1, mode=mode)
    assert fb.Frozen and fb.EventCount == 1 and fb.LastCause == cause
    assert fb.CauseCount[cause] == 1 and fb.ThreadCount[2] == 1
    assert abs(float(fb.EvRadius[0]) - 0.07) < 1e-6
    wi = int(fb.WriteIndex)
    _feed(fb, 5, mode=mode)
    assert int(fb.WriteIndex) == wi  # frozen: nothing overwritten
    fb.Release = True
    _feed(fb, 1, mode=mode)
    assert not fb.Frozen


def test_thread_brake_sensor_fault_fallback_is_bumpless():
    """SPS-323: a sensor fault drops the PI (open loop + learned correction) without a torque step."""
    fb = _scl_brake(BrakeCfg())
    rng = np.random.default_rng(3)
    for k in range(600):  # closed loop at steady speed, sensor reads 0.5 N high (learned correction)
        fb.BrakeMode, fb.LineSpeed, fb.LineAccel, fb.Omega = 2, np.float32(1.0), np.float32(0.0), np.float32(1.0 / 0.08)
        fb.Tmeas, fb.TmeasOk = np.float32(15.5 + rng.normal(0, 0.05)), True
        fb()
    before = float(fb.TorqueCmd)
    fb.TmeasOk = False
    fb()
    after = float(fb.TorqueCmd)
    assert not fb.Closed
    assert abs(after - before) < 0.05 * before
    fb.TmeasOk = True
    fb()
    assert fb.Closed and abs(float(fb.TorqueCmd) - after) < 0.05 * before
