"""Hidden client traits that drive behaviour but never appear in the mart.

Every client has five traits (wealth, activity, digital, credit appetite, cross-border). Each has a
long-run mean, the subsegment's mean plus shifts for nationality group and employment, and a
profile-specific spread and correlation. Month to month the traits follow a stationary AR(1), so
they persist but drift, and their distribution never changes. Later build steps feed them into
product adoption, usage and amounts; the oracle file records them for checking.
"""

import numpy as np
import pandas as pd

from synthetic.presets import LATENTS


def latent_means(spec: dict, clients: pd.DataFrame) -> np.ndarray:
    """Each client's long-run mean: subsegment mean plus nationality-group and employment shifts."""
    shape = (len(clients), len(LATENTS))  # explicit, so zero clients still gives a 2-D array
    subs = spec["subsegments"]
    base = np.array([subs[s]["latent_mean"] for s in clients["subsegment"]]).reshape(shape)
    nat_shift = spec["latent_shift_nationality"]
    nat = np.array([nat_shift[g] for g in clients["nationality_group"]]).reshape(shape)
    emp_shift = spec["latent_shift_employment"]
    emp = np.array([emp_shift[e] for e in clients["employment_status"]]).reshape(shape)
    return base + nat + emp


def latent_covariances(spec: dict) -> dict[str, np.ndarray]:
    """Covariance per profile, D R D."""
    out = {}
    for name, p in spec["profiles"].items():
        scale = np.diag(p["latent_scale"])
        out[name] = scale @ np.array(p["latent_corr"]) @ scale
    return out


def draw_latents(
    spec: dict, clients: pd.DataFrame, means: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Draw from each client's stationary distribution N(mean, Σ_profile)."""
    return means + _correlated_noise(spec, clients, rng)


def step_latents(
    spec: dict, clients: pd.DataFrame, z: np.ndarray, means: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """One month of AR(1); the stationary distribution stays exactly N(mean, Σ_profile)."""
    rho = spec["latent_rho"]
    return means + rho * (z - means) + np.sqrt(1 - rho**2) * _correlated_noise(spec, clients, rng)


def _correlated_noise(spec: dict, clients: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Standard normal noise per client, correlated with its profile's covariance."""
    names = list(spec["profiles"])
    # Cholesky fails loud if a profile's correlation matrix is not positive definite.
    chol = np.stack([np.linalg.cholesky(c) for c in latent_covariances(spec).values()])
    codes = clients["profile"].map({name: i for i, name in enumerate(names)}).to_numpy()
    eps = rng.standard_normal((len(clients), len(LATENTS)))
    return np.einsum("nij,nj->ni", chol[codes], eps)
