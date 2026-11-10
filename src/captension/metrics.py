"""Metrics on simulation results (definitions used in results/study.md)."""

from __future__ import annotations

import numpy as np


def wpercentile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    """Weighted percentile (q in 0..100) of flattened samples."""
    xa = np.asarray(x, float)
    w = np.broadcast_to(w, xa.shape).ravel() if np.ndim(w) else np.full(xa.size, float(w))
    x = xa.ravel()
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    cw /= cw[-1]
    return float(np.interp(q / 100.0, cw, x[o]))


def radius_weights(radii: np.ndarray) -> np.ndarray:
    """Cord-length weight of each radius (dL ~ r dr, equal-width radius bins)."""
    r = np.asarray(radii, float)
    return r / r.sum()


def steady_metrics(T1: np.ndarray, Tset: float, tol: float, radii: np.ndarray, T2=None, EA=None) -> dict:
    """T1: (n_t, n_r, n_mc, 8) at the template entrance."""
    wr = radius_weights(radii)
    n_t, n_r, n_mc, _ = T1.shape
    rel = T1 / Tset
    w_c = np.broadcast_to(wr[None, :, None, None], rel.shape) / (n_t * n_mc * 8)
    spread = (rel.max(-1) - rel.min(-1))
    w_s = np.broadcast_to(wr[None, :, None], spread.shape) / (n_t * n_mc)
    inside = np.abs(rel - 1) <= tol
    all8 = inside.all(-1)
    out = {
        "bias": float((rel - 1).reshape(n_t, n_r, -1).mean(axis=(0, 2)) @ wr),
        "sd": float(np.sqrt(((rel - 1) ** 2 * w_c).sum() - ((rel - 1) * w_c).sum() ** 2)),
        "p99_dev": wpercentile(np.abs(rel - 1), w_c, 99),
        "spread_p50": wpercentile(spread, w_s, 50),
        "spread_p99": wpercentile(spread, w_s, 99),
        "within": float((inside * w_c).sum()),
        "all8": float((all8 * w_s).sum()),
    }
    if T2 is not None and EA is not None:
        de = (T2 / EA).max(-1) - (T2 / EA).min(-1)
        out["prestrain_p99"] = wpercentile(de, w_s, 99)
    return out


def transient_metrics(res, Tset: float, tol: float) -> dict:
    sel = (res.t >= res.scen.window[0]) & (res.t <= res.scen.window[1])
    T1 = res.T1[sel] / Tset
    pk = T1.max(axis=(0, 3))  # per radius, machine
    mn = T1.min(axis=(0, 3))
    sl = res.slack[sel].max(axis=(0, 3))
    inside = (np.abs(T1 - 1) <= tol).all(-1)
    return {
        "peak_p50": float(np.median(pk)), "peak_max": float(pk.max()), "peak_by_r": pk.max(axis=1),
        "min_p50": float(np.median(mn)), "min_min": float(mn.min()), "min_by_r": mn.min(axis=1),
        "slack_max": float(sl.max()), "slack_by_r": sl.max(axis=1), "slack_all": res.slack[sel].max(axis=0),
        "all8_frac": float(inside.mean()),
        "T2_peak": float(res.T2[sel].max()),
    }
