"""The drift reference: Monitoring's yardstick for one run, written with `evaluation/` (D-054;
its format is owned by `docs/components/monitoring.md` → "The drift reference").

`build_drift_reference` takes the final features' (the bundle's) distributions over the
observation window from the run's own copy of EDA's counts (`stage2/`, opened through
`read_stage2_copy` only), so an EDA rerun never changes it: a numeric in EDA's stored bins plus
the null bin, a categorical in EDA's levels (the 50 largest, the rest `__other__`) plus `null`,
each bin's share of its period's rows. The window is the test part's periods. The score's
distribution comes from the test part's score cells at replicate 0, in `SCORE_GROUPS` quantile
groups of the pooled test scores (`merge_bins`, a mass point its own group) with each group's
extremes: Monitoring puts a production score in the last group whose `score_min` is at or below
it, the first group taking every lower score. Both sides count the true population (EDA counted
every eligible row, and test is never sampled). Every share is a valid `psi` input: each
period's shares, empty bins at 0, sum to 1 over a bin list fixed per feature. The writer stamps
`DRIFT_REFERENCE_SCHEMA_VERSION` beside the tables. Pure pandas.
"""

import numpy as np
import pandas as pd

from core_modelling.dataset.counts import NULL_BIN, OTHER, RESERVED_BINS
from core_modelling.statistics.distributions import bin_labels, merge_bins
from core_modelling.statistics.score_cells import POOLED
from core_modelling.training.gate import read_stage2_copy

DRIFT_REFERENCE_SCHEMA_VERSION = 1
SCORE_GROUPS = 10  # the score's quantile groups, as Feature Checks' PSI groups a numeric
FEATURE_COLUMNS = ["feature", "kind", "period", "bin_order", "bin", "rows", "share"]
SCORE_COLUMNS = ["period", "group", "score_min", "score_max", "rows", "share"]


def build_drift_reference(
    run_folder: str, cells: pd.DataFrame, features: list[str]
) -> dict[str, pd.DataFrame]:
    """The drift reference of the run at `run_folder` from its `stage2/` copy, the model's
    score cells (`score_cells(…, by=[])` over every replicate; only the test part's replicate 0
    is read) and `features`, the bundle's (`load_bundle(…).features`).

    Returns `features` (`FEATURE_COLUMNS`: one row per feature, window period or `pooled` (all
    the window's periods added up) and bin of `_bins`), `edges` (EDA's numeric edges, `feature,
    position, edge`, which Monitoring bins production values on as EDA did) and `scores`
    (`SCORE_COLUMNS`: one row per test period or `pooled` and score group).
    """
    test = cells.loc[(cells["part"] == "test") & (cells["replicate"] == 0)]
    if test.empty:
        raise ValueError("build_drift_reference: the score cells hold no test row at replicate 0")
    periods = sorted(test["period"].unique())
    stage2 = read_stage2_copy(run_folder)
    return {
        "features": _feature_shares(stage2, features, periods),
        "edges": stage2["edges"].reset_index(drop=True),
        "scores": _score_shares(test, periods),
    }


def _bins(kind: str, edges: np.ndarray, current: pd.DataFrame) -> pd.DataFrame:
    """One feature's fixed bins in EDA's order, `bin_order, bin`, whether or not a period holds
    rows in them: a numeric's `len(edges) + 1` bins (`bin_labels`) and the null bin last; a
    categorical's kept levels as its window cells (`current`) order them, then `__other__` and
    `null` at EDA's orders (the kept count, and two past it)."""
    if kind == "numeric":
        labels = [*bin_labels(edges), NULL_BIN]
        return pd.DataFrame({"bin_order": range(len(labels)), "bin": labels})
    levels = current.loc[~current["bin"].isin(RESERVED_BINS), ["bin_order", "bin"]]
    kept = levels.drop_duplicates().sort_values("bin_order")
    count = len(kept)
    pooled = pd.DataFrame({"bin_order": [count, count + 2], "bin": [OTHER, NULL_BIN]})
    return pd.concat([kept, pooled], ignore_index=True)


def _feature_shares(
    stage2: dict[str, pd.DataFrame], features: list[str], periods: list[str]
) -> pd.DataFrame:
    """`FEATURE_COLUMNS` for each of `features` in its order: each window period's rows per bin
    (the copy's current cells, folds and target bins added up) and its share of the period's
    rows, then the window pooled. A feature without cells in the copy or in a window period,
    or a level outside its bins, fails loud."""
    cells = stage2["cells"]
    current = cells.loc[~cells["lagged"].astype(bool) & cells["period"].isin(periods)]
    missing = sorted(set(features) - set(current["feature"]))
    if missing:
        raise ValueError(
            f"the run's EDA copy has no cells of the final features {missing} in the window"
        )
    kinds = stage2["ledger"].set_index("feature")["kind"]
    frames = []
    for feature in features:
        own = current.loc[current["feature"] == feature]
        absent = sorted(set(periods) - set(own["period"]))
        if absent:
            raise ValueError(f"the run's EDA copy has no cells of {feature!r} in {absent}")
        edges = stage2["edges"].loc[stage2["edges"]["feature"] == feature].sort_values("position")
        bins = _bins(kinds[feature], edges["edge"].to_numpy(dtype=float), own)
        counts = own.groupby(["period", "bin_order"])["n"].sum().unstack("period")
        stray = sorted(set(counts.index) - set(bins["bin_order"]))
        if stray:
            raise ValueError(f"{feature!r} has cells in bins {stray} outside its EDA bins")
        counts = counts.reindex(bins["bin_order"], fill_value=0).fillna(0)
        counts[POOLED] = counts[periods].sum(axis=1)
        long = counts.melt(ignore_index=False, var_name="period", value_name="rows").reset_index()
        long["share"] = long["rows"] / long.groupby("period")["rows"].transform("sum")
        frames.append(long.merge(bins, on="bin_order").assign(feature=feature, kind=kinds[feature]))
    return pd.concat(frames, ignore_index=True)[FEATURE_COLUMNS]


def _score_shares(test: pd.DataFrame, periods: list[str]) -> pd.DataFrame:
    """`SCORE_COLUMNS` from the test part's replicate-0 cells: the score bins pooled over the
    periods and merged into `SCORE_GROUPS` groups of about equal rows (`merge_bins`), each with
    the lowest and highest score in it, then each period's rows per group and its share."""
    per_bin = test.groupby("score_bin").agg(
        n=("rows", "sum"), score_min=("score_min", "min"), score_max=("score_max", "max")
    )
    merged = merge_bins(per_bin[["n"]].rename_axis("bin_order").reset_index(), SCORE_GROUPS, None)
    starts = merged["bin_order_first"].to_numpy()
    group = starts.searchsorted(per_bin.index.to_numpy(), side="right") - 1
    extremes = per_bin.groupby(group).agg(score_min=("score_min", "min"),
                                          score_max=("score_max", "max"))  # fmt: skip
    at = starts.searchsorted(test["score_bin"].to_numpy(), side="right") - 1
    counts = test.assign(group=at).groupby(["group", "period"])["rows"].sum().unstack("period")
    counts = counts.reindex(index=range(len(merged)), columns=periods, fill_value=0).fillna(0)
    counts[POOLED] = counts[periods].sum(axis=1)
    long = counts.melt(ignore_index=False, var_name="period", value_name="rows").reset_index()
    long["share"] = long["rows"] / long.groupby("period")["rows"].transform("sum")
    return long.join(extremes, on="group")[SCORE_COLUMNS]
