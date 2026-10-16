"""Spec values restated for the checks, independently of the generator.

The check families compare the data with what the spec says, so they never call the generator's
functions: a generator bug would then pass its own check (worknotes/handovers/synthetic_build.md
§4.1). Values that several families need are restated here once, from `truth["spec"]` alone: the
subsegment median incomes and each client's mean traits, both moved by `separation` around their
share-weighted centre (test_harness.md maths §1), and a trait's deviation from the client's mean.
"""

import numpy as np
import pandas as pd

from synthetic.presets import LATENTS


def expected_medians(spec: dict) -> dict[str, float]:
    """Subsegment median incomes, moved on the log scale like the trait means:
    centre + separation × (log median − centre)."""
    subs = spec["subsegments"]
    logs = np.log([s["median_income"] for s in subs.values()])
    return dict(zip(subs, np.exp(_separate(spec, logs)), strict=True))


def expected_latent_means(spec: dict, df: pd.DataFrame) -> np.ndarray:
    """Each row's trait means, (rows, traits): subsegment mean (separated) + nationality shift +
    employment shift."""
    subs = spec["subsegments"]
    means = _separate(spec, np.array([s["latent_mean"] for s in subs.values()]))
    separated = dict(zip(subs, means, strict=True))
    rows = zip(df["subsegment"], df["nationality_group"], df["employment_status"], strict=True)
    return np.array(
        [
            separated[s] + spec["latent_shift_nationality"][g] + spec["latent_shift_employment"][e]
            for s, g, e in rows
        ]
    ).reshape(len(df), len(LATENTS))


def trait_deviation(spec: dict, df: pd.DataFrame, trait: str) -> np.ndarray:
    """Δz = z − m for one trait: the row's `z_<trait>` less its restated mean."""
    means = expected_latent_means(spec, df)[:, LATENTS.index(trait)]
    return df[f"z_{trait}"].to_numpy(dtype=float) - means


def _separate(spec: dict, values: np.ndarray) -> np.ndarray:
    """Per-subsegment values (first axis) moved to centre + separation × (value − centre), the
    centre being their share-weighted mean."""
    shares = np.array([s["share"] for s in spec["subsegments"].values()])
    centre = shares @ values / shares.sum()
    return centre + spec["separation"] * (values - centre)
