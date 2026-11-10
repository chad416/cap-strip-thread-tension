"""Expected thread breaks from simulated tension histories.

Sound cord does not break at these tensions: the weakest-link (Weibull) probability for a
cord of mean strength 230 N and modulus m = 30 at 25 N over 1000 km is below 1e-20
(`sound_cord_breaks`).  Breaks need defects.  The model (DOSSIER 8.5):

* weak spots (knots, splices, damaged filaments) occur at `ws_density` per km of cord;
* their strength has the lower tail  F_ws(s) = (s / S_ref)^k  (s <= S_ref);
* a weak spot breaks when the largest tension it meets on its way through the machine
  exceeds its strength.

A material element that leaves the bobbin when the cumulative line travel is sigma is in
path segment j while  s(t) - sigma  lies in [X_j, X_j+1).  The largest tension it meets is a
range-maximum over the recorded tension of that segment (sparse table, O(n log n)).  The
expected number of breaks is  ws_density * d_sigma * sum_elements F_ws(max_tension).

Attribution (Euler allocation): at the place and time of an element's maximum the tension
is a sum of parts,  T2 = T_b + (G-1) T_b + D,  and for F ~ T^k Euler's theorem splits F
into  F * part / T  (shares add to 1).  The bobbin part is split into its steady value and
the transient excess; the drag part likewise.
"""

from __future__ import annotations

import math

import numpy as np

from .params import BASE, Params

CAUSES = ("unwind steady", "unwind transient", "guides", "template steady", "template transient")


def F_ws(T, p: Params = BASE, k: float | None = None):
    k = p.v("ws_tail_k") if k is None else k
    return np.minimum((np.maximum(T, 0.0) / p.v("ws_Sref")) ** k, 1.0)


def sound_cord_breaks(T: float, length_m: float, p: Params = BASE) -> float:
    """Expected weakest-link breaks of sound cord at constant tension T over length_m."""
    m = p.v("weibull_m")
    s0 = p.v("strength_mean") / math.gamma(1 + 1 / m)
    return 1 - math.exp(-(length_m / p.v("weibull_L0")) * (T / s0) ** m)


class _RangeMax:
    """Sparse-table range maximum with argmax along axis 0 of a (n_t, n_c) array."""

    def __init__(self, a: np.ndarray):
        self.levels = [a]
        self.idx = [np.broadcast_to(np.arange(a.shape[0])[:, None], a.shape).astype(np.int32)]
        j = 1
        while (1 << j) <= a.shape[0]:
            prev, pidx = self.levels[-1], self.idx[-1]
            h = 1 << (j - 1)
            left, right = prev[:-h], prev[h:]
            take = right > left
            self.levels.append(np.where(take, right, left))
            self.idx.append(np.where(take, pidx[h:], pidx[:-h]))
            j += 1

    def query(self, i0: np.ndarray, i1: np.ndarray):
        """Max over rows [i0, i1] inclusive, for each pair (vectors), all columns."""
        ln = np.maximum(i1 - i0 + 1, 1)
        j = np.floor(np.log2(ln)).astype(int)
        out = np.empty((len(i0), self.levels[0].shape[1]), self.levels[0].dtype)
        arg = np.empty(out.shape, np.int32)
        for lev in np.unique(j):
            sel = np.nonzero(j == lev)[0]
            a, b = i0[sel], i1[sel] - (1 << lev) + 1
            va, vb = self.levels[lev][a], self.levels[lev][b]
            take = vb > va
            out[sel] = np.where(take, vb, va)
            arg[sel] = np.where(take, self.idx[lev][b], self.idx[lev][a])
        return out, arg


def exposure(res, p: Params = BASE, d_sigma: float = 0.02, k: float | None = None, window: tuple | None = None):
    """Expected weak-spot breaks per cord for the material in a simulation, with attribution.

    Returns a dict with
      n_el      number of material elements (each d_sigma long)
      Fmax      (n_el, cords) probability that a weak spot in that element breaks
      shares    (n_el, cords, 5) Euler shares over CAUSES
      seg       (n_el, cords) segment of the maximum (0 creel span, 1 guides->template, 2 template->capstan)
      length    metres of cord represented
    Only elements that leave the bobbin inside `window` (default: the scenario window) count.
    """
    t, v = res.t, res.v.astype(float)
    dt = np.diff(t, prepend=t[0])
    s = np.cumsum(v * dt)
    s -= s[0]
    nc = int(np.prod(res.Tb.shape[1:]))
    Tb = res.Tb.reshape(len(t), nc).astype(float)
    D = res.D.reshape(len(t), nc).astype(float)
    G = np.broadcast_to(res.G, res.Tb.shape[1:]).reshape(nc)
    segs = [Tb, Tb * G, Tb * G + D]
    X = np.cumsum([0.0, p.v("L0"), p.v("L1"), p.v("L2")])
    w0, w1 = window if window is not None else res.scen.window
    sw0 = np.interp(w0, t, s)
    sw1 = np.interp(min(w1, t[-1]), t, s)
    # elements: those in the path at the window start, then those leaving the bobbin in it
    sig = np.arange(sw0 - X[-1], sw1, d_sigma)
    if len(sig) == 0:
        return None
    best = np.full((len(sig), nc), -1.0)
    bseg = np.zeros((len(sig), nc), np.int8)
    barg = np.zeros((len(sig), nc), np.int32)
    i_w0 = int(np.searchsorted(t, w0))
    for j, Tseg in enumerate(segs):
        rm = _RangeMax(Tseg)
        enter = sig + X[j]
        leave = sig + X[j + 1]
        i0 = np.searchsorted(s, enter, side="left")
        i1 = np.searchsorted(s, leave, side="left") - 1
        i0 = np.clip(np.maximum(i0, i_w0), 0, len(t) - 1)
        i1 = np.clip(i1, 0, len(t) - 1)
        ok = i1 >= i0
        mx, am = rm.query(i0, np.maximum(i1, i0))
        mx[~ok] = -1.0
        upd = mx > best
        best = np.where(upd, mx, best)
        bseg = np.where(upd, j, bseg)
        barg = np.where(upd, am, barg)
    valid = best >= 0
    best = np.maximum(best, 0.0)
    F = np.where(valid, F_ws(best, p, k), 0.0)
    # Euler shares at the argmax
    cols = np.broadcast_to(np.arange(nc), barg.shape)
    tb = Tb[barg, cols]
    d = D[barg, cols]
    ss = res.ss
    tb_ss = np.broadcast_to(ss["Tb"], res.Tb.shape[1:]).reshape(nc)[None, :]
    d_ss = np.broadcast_to(ss["D"], res.Tb.shape[1:]).reshape(nc)[None, :]
    g = G[None, :]
    parts = np.zeros(best.shape + (5,))
    parts[..., 0] = np.minimum(tb, tb_ss)
    parts[..., 1] = np.maximum(tb - tb_ss, 0.0)
    parts[..., 2] = np.where(bseg >= 1, (g - 1) * tb, 0.0)
    parts[..., 3] = np.where(bseg == 2, np.minimum(d, d_ss), 0.0)
    parts[..., 4] = np.where(bseg == 2, np.maximum(d - d_ss, 0.0), 0.0)
    tot = parts.sum(-1, keepdims=True)
    shares = np.where(tot > 0, parts / np.where(tot > 0, tot, 1.0), 0.0)
    return {"n_el": len(sig), "Fmax": F, "Tmax": best, "shares": shares, "seg": bseg,
            "length": len(sig) * d_sigma, "d_sigma": d_sigma}


def expected(ex: dict, p: Params = BASE) -> dict[str, np.ndarray]:
    """Expected breaks per cord (summed over elements) and per cause."""
    lam = p.v("ws_density") / 1000.0  # per metre
    tot = lam * ex["d_sigma"] * ex["Fmax"].sum(0)
    by = lam * ex["d_sigma"] * (ex["Fmax"][..., None] * ex["shares"]).sum(0)
    return {"total": tot, "by_cause": by}
