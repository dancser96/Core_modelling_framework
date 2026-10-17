"""Relevance rankings: how strongly each mart column tracks the true window probability of a
standard target (test_harness.md, "Ground truth and oracle"; truth.json `oracle.relevance`).

For every binary standard target, every mart column but the keys gets a score: its rank
correlation with the true window probability (`oracle.window_probability`, w = 3) over the target's
eligible rows of one month, the median over the observation months, as an absolute value. The
numeric columns are ranked once per month over the sampled rows and correlated with the
probability's ranks over each target's eligible rows by matrix products (a column is ranked among
its non-null rows, and correlated over those). A categorical column gets a held-out correlation
ratio instead, since the plain η grows with the number of levels: level means of the probability's
ranks fitted on one half of the clients, scored against the other half (median over months; it
can fall a little below 0 when the levels carry nothing). Columns with no score in any month
(constant or null among the eligible rows) are left out. Rankings run on a fixed 20% client sample
(client ids divisible by 5, as `output.read_output(client_sample=5)` reads them) and the halves
are seeded by the dataset's seed, so the in-memory and the written truth agree.
"""

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from synthetic.oracle import BINARY_TARGETS, KEYS, window_probability

WINDOW = 3
SAMPLE_EVERY = 5  # client ids divisible by this: a fixed 20% sample


def relevance_rankings(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> dict:
    """Every binary standard target's ranking on the 20% client sample, as truth.json stores it:
    target → [{column, score}], most relevant first."""
    ids = np.unique(mart["client_id"])
    sample = ids[ids % SAMPLE_EVERY == 0]
    rankings = _rankings(mart, oracle, truth, BINARY_TARGETS, sample)
    return {target: ranking.to_dict("records") for target, ranking in rankings.items()}


def relevance_ranking(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, target: str, sample: np.ndarray
) -> pd.DataFrame:
    """One target's ranking over the clients in `sample` (ids): columns `column` and `score`,
    most relevant first."""
    return _rankings(mart, oracle, truth, [target], sample)[target]


def _rankings(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, targets: list[str], sample: np.ndarray
) -> dict[str, pd.DataFrame]:
    """The rankings of `targets` on the sampled clients' rows; ranks are taken once per month."""
    sample = np.sort(sample)  # the halves are looked up by position
    # Only a whole panel needs filtering: copying an already-sampled one doubles its memory.
    mart, oracle = (_rows_of(df, sample) for df in (mart, oracle))
    chances = {t: window_probability(mart, oracle, truth, t, WINDOW).to_numpy() for t in targets}
    columns = [c for c in mart.columns if c not in KEYS]
    numeric = [c for c in columns if pd.api.types.is_numeric_dtype(mart[c])]
    categorical = [c for c in columns if c not in numeric]
    codes = np.column_stack([pd.factorize(mart[c], use_na_sentinel=False)[0] for c in categorical])
    halves = np.random.default_rng(truth["seed"]).random(len(sample)) < 0.5  # seeded, per client
    first_half = halves[np.searchsorted(sample, mart["client_id"].to_numpy())]
    month = pd.factorize(mart["snapshot_month"])[0]
    scores = {t: [] for t in targets}
    for m in range(month.max() + 1):
        rows = month == m
        # The month's rows first: selecting columns first would copy every sampled row.
        values = mart[rows][numeric].to_numpy(dtype=float, na_value=np.nan)
        ranks = rankdata(values, axis=0, nan_policy="omit")
        for target in targets:
            use = ~np.isnan(chances[target][rows])
            if use.sum() < 3:
                continue
            p = rankdata(chances[target][rows][use])
            rho = _rank_correlations(ranks[use], p)
            eta = _held_out_eta(codes[rows][use], p, first_half[rows][use])
            scores[target].append(np.concatenate([rho, eta]))
    return {t: _ranking([*numeric, *categorical], len(numeric), scores[t]) for t in targets}


def _rank_correlations(ranks: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Pearson correlation of each column of `ranks` (NaN = no value) with `p`, over the rows
    where the column has a value; NaN where either side is constant there."""
    has = ~np.isnan(ranks)
    x = np.where(has, ranks, 0.0)
    n = has.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_x, mean_p = x.sum(axis=0) / n, (has.T @ p) / n
        cov = (x.T @ p) / n - mean_x * mean_p
        var_x = (x**2).sum(axis=0) / n - mean_x**2
        var_p = (has.T @ p**2) / n - mean_p**2
        rho = cov / np.sqrt(var_x * var_p)
    return np.where((var_x > 1e-9) & (var_p > 1e-9), rho, np.nan)


def _held_out_eta(codes: np.ndarray, p: np.ndarray, first_half: np.ndarray) -> np.ndarray:
    """Per categorical column (`codes`, one column each): the correlation of `p` in the second
    half of the clients with its level means fitted on the first half (a level the first half
    lacks gets that half's mean); NaN where the fitted means are constant."""
    fit, score = first_half, ~first_half
    out = np.full(codes.shape[1], np.nan)
    if fit.sum() < 2 or score.sum() < 2:
        return out
    for j in range(codes.shape[1]):
        levels = codes[:, j].max() + 1
        count = np.bincount(codes[fit, j], minlength=levels)
        total = np.bincount(codes[fit, j], weights=p[fit], minlength=levels)
        means = np.where(count > 0, total / np.maximum(count, 1), p[fit].mean())
        fitted = means[codes[score, j]]
        if fitted.max() > fitted.min():  # exact: a std of equal values can round above 0
            out[j] = np.corrcoef(fitted, p[score])[0, 1]
    return out


def _ranking(columns: list[str], n_numeric: int, months: list[np.ndarray]) -> pd.DataFrame:
    """Scores (median over months; absolute for rank correlations) sorted, most relevant first;
    columns without a score in any month are left out."""
    if not months:
        return pd.DataFrame({"column": [], "score": []})
    by_month = np.vstack(months)
    scored = ~np.isnan(by_month).all(axis=0)
    median = np.full(len(columns), np.nan)
    median[scored] = np.nanmedian(by_month[:, scored], axis=0)
    score = np.where(np.arange(len(columns)) < n_numeric, np.abs(median), median)
    ranking = pd.DataFrame({"column": columns, "score": score})[scored]
    return ranking.sort_values("score", ascending=False, kind="stable", ignore_index=True)


def _rows_of(df: pd.DataFrame, sample: np.ndarray) -> pd.DataFrame:
    """The rows of the clients in `sample`; `df` itself if it holds no other client."""
    keep = df["client_id"].isin(sample).to_numpy()
    return df if keep.all() else df[keep]
