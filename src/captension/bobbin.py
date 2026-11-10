"""Bobbin geometry and inertia.

    r^2 = r_full^2 - A_cord * L / (pi * w * fill)                    (package volume balance)
    J(r) = J_core + (pi/2) * rho_fibre * fill * w * (r^4 - r_core^4)   (hollow cylinder)
    v = omega * r

Standard winding geometry [W1 ch. 2, std]; the forms are those the brief asks for.
"""

from __future__ import annotations

import math

import numpy as np

from .params import BASE, Params, cord_area


def Kr(p: Params = BASE) -> float:
    """Decrease of r^2 per metre of cord taken off, m."""
    return cord_area(p) / (math.pi * p.v("bobbin_w") * p.v("pack_fill"))


def capacity(p: Params = BASE) -> float:
    """Cord length on a full bobbin, m."""
    return (p.v("r_full") ** 2 - p.v("r_core") ** 2) / Kr(p)


def radius(L, p: Params = BASE):
    """Package radius after L metres have been unwound."""
    r2 = p.v("r_full") ** 2 - Kr(p) * np.asarray(L, float)
    return np.sqrt(np.maximum(r2, p.v("r_core") ** 2))


def Jcoef(p: Params = BASE) -> float:
    return math.pi / 2 * p.v("fibre_density") * p.v("pack_fill") * p.v("bobbin_w")


def inertia(r, p: Params = BASE):
    r = np.asarray(r, float)
    return p.v("J_core") + Jcoef(p) * (r ** 4 - p.v("r_core") ** 4)


def mass(p: Params = BASE) -> float:
    return capacity(p) * p.v("cord_lin_density")


def length_weights(radii: np.ndarray, p: Params = BASE) -> np.ndarray:
    """Weights for averaging a quantity over the bobbin by cord length (dL ~ r dr).

    `radii` are the centres of equal-width radius bins between r_core and r_full.
    """
    radii = np.asarray(radii, float)
    w = radii / radii.sum()
    return w
