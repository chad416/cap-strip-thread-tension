"""Python references of the PLC blocks, vectorised over cords.

`ThreadBrakeVec` is line-for-line the algorithm of plc/FB_ThreadBrake.scl, written with numpy
arrays so one call updates every cord of every Monte-Carlo machine.  tests/test_scl.py runs the
SCL text through the float32 translator (captension.scl) and checks it against this class, so
the simulation results in results/study.md are produced by the same algorithm that compiles
in TIA Portal.

`WinderVec` is the same for plc/FB_WinderTension.scl.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BrakeCfg:
    Tset: float = 15.0
    Gnom: float = 1.6161
    Rcore: float = 0.04
    Rfull: float = 0.11
    Jcore: float = 0.0013
    Jcoef: float = 214.9
    Kr: float = 6.98e-7
    Mbear: float = 0.02
    Kbrake: float = 3.95
    Imax: float = 1.0
    Mdrag: float = 0.0395
    Bidirectional: bool = False
    Kp: float = 0.3
    Ti: float = 0.8
    Kd: float = 9.0
    HoldFactor: float = 1.0
    EStopDecel: float = 2.0
    RadiusTf: float = 2.0
    ReseedTime: float = 1.0
    OmegaMin: float = 0.5
    VMin: float = 0.05
    BrakeTau: float = 0.025
    CycleTime: float = 0.01

    def scl_inputs(self) -> dict[str, float | bool]:
        return dict(self.__dict__)


class ThreadBrakeVec:
    """Vectorised FB_ThreadBrake (see the SCL header for the modes)."""

    def __init__(self, cfg: BrakeCfg, shape: tuple[int, ...]):
        self.c = cfg
        z = lambda: np.zeros(shape)  # noqa: E731
        self.sR = np.full(shape, cfg.Rfull)
        self.sI, self.sMest, self.sOmegaPrev, self.sAlphaF, self.sBadTime = z(), z(), z(), z(), z()
        self.sLacc = z()
        self.sRsum = z()
        self.sFarTime = z()
        self.sInit = np.zeros(shape, bool)
        # outputs
        self.CurrentCmd, self.TorqueCmd, self.Radius, self.Inertia = z(), z(), z(), z()
        self.Tvirtual, self.GuideFactor = z(), z()
        self.RadiusOk = np.zeros(shape, bool)
        self.TvirtualOk = np.zeros(shape, bool)
        self.Saturated = np.zeros(shape, bool)
        self.Closed = np.zeros(shape, bool)

    def __call__(self, BrakeMode, LineSpeed, LineAccel, Omega, Tmeas, TmeasOk, NewBobbin=False):
        c = self.c
        sh = self.sR.shape
        mode = np.broadcast_to(np.asarray(BrakeMode), sh)
        v = np.broadcast_to(np.asarray(LineSpeed, float), sh)
        a = np.broadcast_to(np.asarray(LineAccel, float), sh)
        w = np.asarray(Omega, float)
        Tm = np.asarray(Tmeas, float)
        ok = np.broadcast_to(np.asarray(TmeasOk, bool), sh)
        nb = np.broadcast_to(np.asarray(NewBobbin, bool), sh)
        Ts = c.CycleTime
        # ---- radius
        seed = (~self.sInit) | nb
        self.sR = np.where(seed, c.Rfull, self.sR)
        self.sBadTime = np.where(seed, 0.0, self.sBadTime)
        self.sLacc = np.where(seed, 0.0, self.sLacc)
        self.sRsum = np.where(seed, 0.0, self.sRsum)
        self.sFarTime = np.where(seed, 0.0, self.sFarTime)
        self.sInit = self.sInit | seed
        self.sLacc = self.sLacc + v * Ts
        step = self.sLacc >= 1.0
        r2 = self.sR * self.sR - c.Kr * self.sLacc
        self.sR = np.where(step, np.where(r2 > c.Rcore * c.Rcore, np.sqrt(np.maximum(r2, 0.0)), c.Rcore), self.sR)
        self.sLacc = np.where(step, 0.0, self.sLacc)
        moving = (w > c.OmegaMin) & (v > c.VMin)
        rm = np.where(moving, v / np.where(w > 0, w, 1.0), 0.0)
        plaus = moving & (rm > 0.97 * c.Rcore) & (rm < 1.05 * c.Rfull)
        close = plaus & (np.abs(rm - self.sR) < 0.15 * self.sR)
        far = plaus & ~close
        self.sR = np.where(close, self.sR + Ts / c.RadiusTf * (rm - self.sR), self.sR)
        bad = np.where(far, self.sBadTime + Ts, self.sBadTime)
        rsum = np.where(far, self.sRsum + rm * Ts, self.sRsum)
        reseed = far & (bad > c.ReseedTime - 0.5 * Ts)
        self.sR = np.where(reseed, rsum / np.where(bad > 0, bad, 1.0), self.sR)
        self.sBadTime = np.where(close | reseed, 0.0, bad)
        self.sRsum = np.where(close | reseed, 0.0, rsum)
        self.RadiusOk = close
        gross = plaus & (np.abs(rm - self.sR) > 0.3 * self.sR)
        self.sFarTime = np.where(gross, self.sFarTime + Ts, 0.0)
        R = self.sR
        self.Radius = R.copy()
        J = c.Jcore + c.Jcoef * (R ** 4 - c.Rcore ** 4)
        self.Inertia = J
        # ---- torque
        Tb = c.Tset / c.Gnom
        mv = (v > c.VMin) & (w > c.OmegaMin) & (self.sFarTime < 0.095)
        md = np.where(mv, c.Kd * R * np.sqrt(J) * (w - v / R), 0.0)
        ut = self.sI.copy()
        e = np.zeros(sh)
        closed = np.zeros(sh, bool)
        m12 = (mode == 1) | (mode == 2)
        M = np.zeros(sh)
        M = np.where(m12, R * Tb - J * a / R - c.Mbear + md, M)
        ut = np.where(mode == 1, 0.0, ut)
        cl = (mode == 2) & ok
        closed = cl
        e = np.where(cl, c.Tset - Tm, e)
        ut = np.where(cl, c.Kp * e + self.sI, ut)
        M = np.where(mode == 3, c.HoldFactor * R * Tb, M)
        es = mode == 4
        M = np.where(es & (w > c.OmegaMin), R * Tb + J * c.EStopDecel / R - c.Mbear + md, M)
        M = np.where(es & ~(w > c.OmegaMin), c.HoldFactor * R * Tb, M)
        off = ~(m12 | (mode == 3) | es)
        ut = np.where(off, 0.0, ut)
        M = M + R / c.Gnom * ut
        Mmax = c.Kbrake * c.Imax
        Mmin = -Mmax if c.Bidirectional else 0.0
        self.Saturated = (M > Mmax) | ((M < Mmin) & (mode != 0))
        M = np.clip(M, Mmin, Mmax)
        self.TorqueCmd = M
        self.Closed = closed
        integ = closed & ~(((M >= Mmax) & (e > 0)) | ((M <= Mmin) & (e < 0)))
        sI = np.where(integ, np.clip(self.sI + c.Kp * Ts / c.Ti * e, -c.Tset, c.Tset), self.sI)
        track = ~closed & ((mode == 0) | (mode == 1))
        sI = np.where(track, np.where(ok, -c.Kp * (c.Tset - Tm), 0.0), sI)
        self.sI = sI
        if c.Bidirectional:
            I = M / c.Kbrake
        else:
            I = np.clip((M - c.Mdrag) / c.Kbrake, 0.0, c.Imax)
        self.CurrentCmd = I
        # ---- observer
        ta = Ts / (c.BrakeTau + Ts)
        drag = 0.0 if c.Bidirectional else c.Mdrag
        self.sMest = self.sMest + ta * (c.Kbrake * I + drag - self.sMest)
        self.sAlphaF = self.sAlphaF + Ts / (0.05 + Ts) * ((w - self.sOmegaPrev) / Ts - self.sAlphaF)
        self.sOmegaPrev = w.copy() if isinstance(w, np.ndarray) else np.full(sh, w)
        den = self.sMest + J * self.sAlphaF + c.Mbear
        self.TvirtualOk = w > c.OmegaMin
        self.Tvirtual = c.Gnom * den / R
        gf = np.where(self.TvirtualOk & ok & (den > 0.01), Tm * R / np.where(den > 0.01, den, 1.0), 0.0)
        self.GuideFactor = gf
        return I


@dataclass
class WinderCfg:
    Trecipe: float = 40.0
    Taper: float = 0.20
    Rcore: float = 0.10
    Rmax: float = 0.166
    Jcore: float = 0.10
    Jcoef: float = 457.0
    Mfric: float = 0.5
    Kp: float = 0.5
    Kd: float = 40.0
    Ti: float = 0.8
    Mmax: float = 30.0
    EStopDecel: float = 2.0
    RadiusTf: float = 2.0
    OmegaMin: float = 0.3
    VMin: float = 0.05
    CycleTime: float = 0.01


class WinderVec:
    """Vectorised FB_WinderTension: taper, inertia/friction feedforward, load-cell PI trim."""

    def __init__(self, cfg: WinderCfg, shape: tuple[int, ...]):
        self.c = cfg
        self.sR = np.full(shape, cfg.Rcore)
        self.sI = np.zeros(shape)
        self.sInit = np.zeros(shape, bool)
        self.TorqueCmd = np.zeros(shape)
        self.Tref = np.zeros(shape)
        self.Radius = np.zeros(shape)
        self.Saturated = np.zeros(shape, bool)

    def __call__(self, Mode, LineSpeed, LineAccel, OmegaW, StripT, StripTOk, NewSpool=False):
        c = self.c
        sh = self.sR.shape
        mode = np.broadcast_to(np.asarray(Mode), sh)
        v = np.broadcast_to(np.asarray(LineSpeed, float), sh)
        a = np.broadcast_to(np.asarray(LineAccel, float), sh)
        w = np.asarray(OmegaW, float)
        Tm = np.asarray(StripT, float)
        ok = np.broadcast_to(np.asarray(StripTOk, bool), sh)
        nb = np.broadcast_to(np.asarray(NewSpool, bool), sh)
        Ts = c.CycleTime
        seed = (~self.sInit) | nb
        self.sR = np.where(seed, c.Rcore, self.sR)
        self.sInit = self.sInit | seed
        moving = (w > c.OmegaMin) & (v > c.VMin)
        rm = np.where(moving, v / np.where(w > 0, w, 1.0), self.sR)
        good = moving & (rm > 0.95 * c.Rcore) & (rm < 1.05 * c.Rmax)
        self.sR = np.where(good, self.sR + Ts / c.RadiusTf * (rm - self.sR), self.sR)
        R = self.sR
        self.Radius = R.copy()
        J = c.Jcore + c.Jcoef * (R ** 4 - c.Rcore ** 4)
        Tref = c.Trecipe * (1.0 - c.Taper * (1.0 - c.Rcore / R))
        self.Tref = Tref
        acc = np.where(mode == 4, -c.EStopDecel, a)
        run = (mode == 1) | (mode == 2) | (mode == 4)
        e = np.where(ok, Tref - Tm, 0.0)
        pi_on = (mode == 2) & ok
        ut = np.where(pi_on, c.Kp * e + self.sI, self.sI)
        md = np.where(v > c.VMin, c.Kd * R * np.sqrt(J) * (w - v / R), 0.0)
        M = np.where(run, Tref * R + J * acc / R + c.Mfric + R * ut - md, 0.0)
        M = np.where(mode == 3, Tref * R, M)
        self.Saturated = (M > c.Mmax) | (M < -c.Mmax)
        M = np.clip(M, -c.Mmax, c.Mmax)
        integ = pi_on & ~(((M >= c.Mmax) & (e > 0)) | ((M <= -c.Mmax) & (e < 0)))
        self.sI = np.where(integ, np.clip(self.sI + c.Kp * Ts / c.Ti * e, -c.Trecipe, c.Trecipe), self.sI)
        self.sI = np.where(mode == 0, 0.0, self.sI)
        self.TorqueCmd = M
        return M
