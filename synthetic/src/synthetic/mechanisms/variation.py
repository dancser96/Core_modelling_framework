"""How amounts vary around their level: between clients, month to month, and in their split.

Every amount is a median multiple of a hidden base times a random part (test_harness.md maths §4):
the log of the random part is a trait's deviation from the client's mean, a persistent client
effect and monthly AR(1) noise, plus (balances) the log of a persistent power-law multiplier or
(flows) the current/savings balance's random part × the balance elasticity. A median offset `c`
(an exponentially modified normal's median, `scipy.stats.exponnorm`) makes the random part's median
exactly 1 for a client at its own trait means, so the median amount lands on the spec's multiple.
This module holds those parts, the levels they multiply, the overdispersed counts and the
subcategory splits (Dirichlet shares; parts rounded to the cent that add up to the total exactly).
`measure_offsets` and `log_variation` are shared by every amount mechanism and by the regression
oracle. Functions that take arrays work on any shape, as the regression oracle's
(clients, paths) arrays need: a per-client input then comes as an `(n, 1)` column, so it
broadcasts over the paths.
"""

import numpy as np
from scipy.stats import exponnorm

from synthetic.spec.presets import LATENTS
from synthetic.spec.products import PROFILE_ORDER


def draw_effects(rng: np.random.Generator, n: int, sds: np.ndarray) -> np.ndarray:
    """Persistent client effects, (n, measures), each N(0, sd²)."""
    return rng.standard_normal((n, len(sds))) * sds


def start_noise(rng: np.random.Generator, n: int, sds: np.ndarray) -> np.ndarray:
    """AR(1) noise at its stationary distribution N(0, sd²), (n, measures)."""
    return rng.standard_normal((n, len(sds))) * sds


def step_noise(
    noise: np.ndarray, rho: float | np.ndarray, sds: float | np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """One month of stationary AR(1): the noise keeps its sd and persists with `rho`."""
    return rho * noise + np.sqrt(1 - rho**2) * sds * rng.standard_normal(noise.shape)


def draw_multipliers(rng: np.random.Generator, n: int, tails: np.ndarray) -> np.ndarray:
    """Persistent power-law multipliers, Pareto(x_m = 1, a = tail), (n, measures).

    numpy's `pareto` is the Lomax distribution, so 1 is added.
    """
    return 1 + rng.pareto(tails, (n, len(tails)))


def median_offset(sd: np.ndarray, rate: np.ndarray) -> np.ndarray:
    """Log median of N(0, sd²) + Exponential(rate): the offset `c` of maths §4."""
    return exponnorm.median(1 / (sd * rate), loc=0, scale=sd)


def draw_counts(rng: np.random.Generator, mean: np.ndarray, shape: float) -> np.ndarray:
    """Overdispersed counts: Poisson(mean × G), G ~ Gamma(shape, 1 / shape), one per element."""
    return rng.poisson(mean * rng.gamma(shape, 1 / shape, np.shape(mean)))


def draw_transaction_counts(
    rng: np.random.Generator, amount: np.ndarray, mean: np.ndarray, shape: float
) -> np.ndarray:
    """Transactions behind an amount: 1 + overdispersed counts where it is positive, else 0.

    Drawn for every element whatever the amount, so the stream never depends on an outcome.
    """
    return np.where(np.asarray(amount) > 0, 1 + draw_counts(rng, mean, shape), 0)


def draw_shares(
    rng: np.random.Generator, mean_shares: np.ndarray, concentration: float
) -> np.ndarray:
    """Monthly shares ~ Dirichlet(concentration × mean shares) along the last axis.

    A zero mean share stays exactly 0 (a Gamma with shape 0 is 0).
    """
    g = rng.gamma(concentration * mean_shares)
    return g / g.sum(axis=-1, keepdims=True)


def split_amount(total: np.ndarray, shares: np.ndarray) -> np.ndarray:
    """Parts of `total` (rounded to the cent first) along a new last axis, in whole cents.

    Largest-remainder rounding: the parts add up to the rounded total exactly, and a zero share
    gets exactly 0.
    """
    cents = np.round(np.asarray(total) * 100)
    raw = cents[..., None] * shares
    parts = np.floor(raw)
    left = cents - parts.sum(axis=-1)  # whole cents still to hand out, fewer than the parts
    rank = np.argsort(np.argsort(parts - raw, axis=-1, kind="stable"), axis=-1, kind="stable")
    return (parts + (rank < left[..., None])) / 100


def tilted_shares(spec: dict, table: str, profiles: np.ndarray, dz: np.ndarray) -> np.ndarray:
    """Mean shares of a subcategory table (last axis), not yet renormalised: the profile's base
    shares × exp(Σ loading × trait deviation) for the subcategories the spec tilts."""
    sub = spec["levels"]["subcategories"]
    base = np.array([sub[table]["shares"][p] for p in PROFILE_ORDER], dtype=float)[profiles]
    log_tilts = []
    for name in sub[table]["names"]:
        log_tilt = np.zeros(dz.shape[:-1])
        for trait, loading in sub["tilts"].get(name, {}).items():
            log_tilt = log_tilt + loading * dz[..., LATENTS.index(trait)]
        log_tilts.append(log_tilt)
    return base * np.exp(np.stack(log_tilts, axis=-1))


def measures_of_kind(spec: dict, kind: str) -> list[str]:
    """The measures of one kind ("stock" or "flow") in the spec's order: the columns of that
    kind's state arrays."""
    names = [name for name, cfg in spec["levels"]["measures"].items() if cfg["kind"] == kind]
    if not names:
        raise ValueError(f"no measure of kind {kind!r}")
    return names


def measure_level(spec: dict, measure: str, profiles: np.ndarray, base: np.ndarray) -> np.ndarray:
    """A measure's median before its random part: the profile's multiple × the hidden `base`
    (the wealth base for balances, the true income for flows). `profiles` are PROFILE_ORDER codes
    that broadcast with `base`."""
    multiples = np.asarray(spec["levels"]["measures"][measure]["multiples"], dtype=float)
    return multiples[profiles] * base


def measure_offsets(spec: dict) -> dict[str, np.ndarray]:
    """The median offset `c` of every measure per profile (order: PROFILE_ORDER), maths §4.

    Stocks: N(0, λ²σ² + e² + s²) + Exponential(tail). Flows add the current/savings random part
    × φ: φ² × its normal variance and an Exponential(tail / φ), less φ × its offset, since that
    part enters already centred.
    """
    levels = spec["levels"]
    measures, phi = levels["measures"], levels["balance_elasticity"]
    stock_sd, flow, out = levels["stock_noise"]["sd"], levels["flow_noise"], {}
    casa = measures["casa_bal"]
    casa_var = _trait_var(spec, casa) + casa["effect_sd"] ** 2 + stock_sd**2
    for name, cfg in measures.items():
        if cfg["kind"] == "stock":
            var = _trait_var(spec, cfg) + cfg["effect_sd"] ** 2 + stock_sd**2
            out[name] = median_offset(np.sqrt(var), np.full(len(var), cfg["tail"]))
        else:
            var = _trait_var(spec, cfg) + flow["effect_sd"] ** 2 + flow["sd"] ** 2
            var = var + phi**2 * casa_var
            rate = np.full(len(var), casa["tail"] / phi)
            out[name] = median_offset(np.sqrt(var), rate) - phi * out["casa_bal"]
    return out


def _trait_var(spec: dict, cfg: dict) -> np.ndarray:
    """Variance of a measure's trait term λ·Δz per profile (Δz has the profile's latent scale)."""
    trait = LATENTS.index(cfg["trait"])
    scale = np.array([spec["profiles"][p]["latent_scale"][trait] for p in PROFILE_ORDER])
    return (cfg["loading"] * scale) ** 2


def log_variation(
    spec: dict,
    offsets: dict[str, np.ndarray],
    state: dict[str, np.ndarray],
    dz: np.ndarray,
    profiles: np.ndarray,
) -> dict[str, np.ndarray]:
    """Log of every measure's random part per client, with median 0 at the client's trait means.

    `state` holds the effects, noise and multipliers (`<kind>_effect`, `<kind>_noise`,
    `stock_pareto`); `dz` is z − the client's trait means; `profiles` are PROFILE_ORDER codes. The
    current/savings part (`casa_bal`) is D of maths §4, which every flow carries × φ.
    """
    measures, phi = spec["levels"]["measures"], spec["levels"]["balance_elasticity"]
    out = {}
    for kind in ("stock", "flow"):  # stocks first: every flow carries D
        for j, name in enumerate(measures_of_kind(spec, kind)):  # column j of the state arrays
            cfg = measures[name]
            trait = cfg["loading"] * dz[..., LATENTS.index(cfg["trait"])]
            part = trait + state[f"{kind}_effect"][..., j] + state[f"{kind}_noise"][..., j]
            if kind == "stock":
                part = part + np.log(state["stock_pareto"][..., j])
            else:
                part = part + phi * out["casa_bal"]
            out[name] = part - offsets[name][profiles]
    return out
