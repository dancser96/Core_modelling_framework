"""The value profile: every supported candidate's values in one table, in rank order (Extended,
after the correlation overview; docs/components/eda.md).

`value_profile` gives a numeric's range over its finite non-null values on the snapshot's
eligible rows (`min`, `p1`, `median`, `p99`, `max`, one vectorised `quantile` call over every
numeric, V59) and its ±infinity share over those rows, and a categorical's `TOP_LEVELS` largest
levels on the snapshot period's cells with their shares of the rows; `kind`, `rank` and
`missing_share` come from the ranking. A sentinel (−1, 999, 9 999 999) shows as a mass point at
`min` or `max`. It describes values, not a feature's path, so it is no ledger column (V59). Pure
pandas.
"""

import numpy as np
import pandas as pd

from core_modelling.statistics.cells import pool_periods

QUANTILES = {"min": 0.0, "p1": 0.01, "median": 0.5, "p99": 0.99, "max": 1.0}
TOP_LEVELS = 3  # a categorical's largest levels shown
PROFILE_COLUMNS = ["feature", "kind", "rank", "rows", "missing_share", *QUANTILES, "inf_share",
                   "top_levels"]  # fmt: skip


def value_profile(
    snapshot: pd.DataFrame,
    kinds: dict[str, str],
    ranking: pd.DataFrame,
    cells: pd.DataFrame,
    snapshot_period: str,
) -> pd.DataFrame:
    """One row per feature of `kinds` in rank order (`PROFILE_COLUMNS`; `rows` the snapshot's
    eligible rows): a numeric's range and `inf_share`, a categorical's `top_levels` text (a
    numeric's ''; a categorical's range NaN)."""
    unranked = sorted(set(kinds) - set(ranking["feature"]))
    if unranked:
        raise ValueError(f"value_profile: the ranking has no row for {unranked}")
    eligible = snapshot.loc[snapshot["eligible"] == 1]
    numerics = [name for name, kind in kinds.items() if kind == "numeric"]
    values = eligible[numerics].astype(float)
    finite = values.replace([np.inf, -np.inf], np.nan)
    ranges = finite.quantile(list(QUANTILES.values())).T.set_axis(list(QUANTILES), axis=1)
    ranges["inf_share"] = np.isinf(values).mean()
    levels = {
        name: _top_levels(cells.loc[cells["feature"] == name], snapshot_period)
        for name, kind in kinds.items()
        if kind == "categorical"
    }
    columns = ["feature", "kind", "rank", "missing_share"]
    profile = ranking.loc[ranking["feature"].isin(list(kinds)), columns].sort_values("rank")
    profile = profile.assign(rows=len(eligible)).join(ranges, on="feature")
    profile["top_levels"] = profile["feature"].map(levels).fillna("")
    return profile[PROFILE_COLUMNS].reset_index(drop=True)


def _top_levels(cells: pd.DataFrame, period: str) -> str:
    """One categorical's `TOP_LEVELS` largest non-null levels in `period`'s current cells, each
    with its share of every row (null included), as `A: 40.1% · '': 12.0%`; ties by label."""
    pooled = pool_periods(cells, [period])
    counts = pooled.loc[~pooled["is_null"]].groupby("bin")["n"].sum()
    top = counts.sort_index().sort_values(ascending=False, kind="stable").head(TOP_LEVELS)
    total = pooled["n"].sum()
    return " · ".join(f"{level}: {n / total:.1%}" for level, n in top.items())
