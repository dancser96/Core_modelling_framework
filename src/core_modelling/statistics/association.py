"""How strongly features go together on the snapshot, and the redundancy clusters cut from it
(D-135).

`association_table` measures every pair of candidates on a seeded cap of `PAIRWISE_ROWS`
snapshot rows (the one place the framework caps rows, stated in the report): Spearman for two
numerics, Cramér's V (plain, not bias-corrected) for two categoricals, the correlation ratio η on
the numeric's ranks for a mixed pair; null is a level for the last two (N8). A pair that cannot
be measured is "not compared" (NaN). Feature Checks cuts the clusters from that long table
(`cluster_features`, average linkage, Q472) and scores each numeric member by
`explained_by_others`, from the table's Spearman pairs alone, with no rows (V4).
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import contingency

PAIRWISE_ROWS = 50_000  # the seeded cap of snapshot rows; a ρ's noise there is ~0.004 (EDS)
PAIRWISE_SEED = 0  # the cap's sample: the same rows on every run
MIN_SHARED_ROWS = 500  # fewer shared filled rows: "not compared" (ρ's noise ~0.01 near 0.9)
TABLE_COLUMNS = ["a", "b", "statistic", "method", "rows"]
R2_TOLERANCE = 1e-9  # rounding room around [0, 1] for `explained_by_others`' R²


def spearman_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """The pairwise-complete Spearman correlation of every pair of numeric columns, each pair
    ranked on the rows where both are filled; NaN for fewer than `MIN_SHARED_ROWS` such rows or
    a constant side.

    The columns are grouped by null mask, so one ranking serves every pair inside a group and
    one per group pair across groups: ranking each column once over its own rows is not this
    statistic when two masks differ, and pandas' pairwise Spearman is too slow (T28).
    """
    values = frame.to_numpy(dtype=float, na_value=np.nan)
    present = ~np.isnan(values)
    groups = _null_mask_groups(present)
    matrix = np.full((values.shape[1], values.shape[1]), np.nan)
    for i, first in enumerate(groups):
        for second in groups[i:]:
            rows = present[:, first[0]] & present[:, second[0]]
            if rows.sum() < MIN_SHARED_ROWS:
                continue
            ranks = _ranks(values, rows, first)
            block = _pearson(ranks, ranks if second is first else _ranks(values, rows, second))
            matrix[np.ix_(first, second)] = block
            matrix[np.ix_(second, first)] = block.T
    return pd.DataFrame(matrix, index=frame.columns, columns=frame.columns)


def pairwise_sample(frame: pd.DataFrame) -> pd.DataFrame:
    """The rows the pairwise association reads: a seeded sample of `PAIRWISE_ROWS` rows above the
    cap, else the frame as it is (so a capped frame passes unchanged)."""
    if len(frame) > PAIRWISE_ROWS:
        return frame.sample(n=PAIRWISE_ROWS, random_state=PAIRWISE_SEED)
    return frame


def association_table(frame: pd.DataFrame, kinds: dict[str, str]) -> pd.DataFrame:
    """The long association table: one row per pair of the `kinds` features (name → numeric or
    categorical), measured on `pairwise_sample`'s rows of `frame` (a no-op on a frame it capped
    already).

    Columns `a, b, statistic, method (spearman | cramers_v | eta), rows` (the rows the pair
    used); a mixed pair has its numeric as `a`. Refused for a feature not in `frame` or of
    another kind.
    """
    unknown = sorted(set(kinds) - set(frame.columns))
    odd = sorted(f for f, kind in kinds.items() if kind not in ("numeric", "categorical"))
    if unknown or odd:
        raise ValueError(
            f"association_table: features not in the frame {unknown}, or neither numeric nor "
            f"categorical {odd}"
        )
    frame = pairwise_sample(frame)
    numerics = [f for f, kind in kinds.items() if kind == "numeric"]
    codes = {f: _codes(frame[f]) for f, kind in kinds.items() if kind == "categorical"}
    numeric = frame[numerics].astype(float)
    ranks = {f: numeric[f].rank(na_option="keep").to_numpy() for f in numerics}
    names = list(codes)
    records = _spearman_records(numeric)
    records += [
        (a, b, _cramers_v(codes[a], codes[b]), "cramers_v", len(frame))
        for i, a in enumerate(names)
        for b in names[i + 1 :]
    ]
    records += [
        (a, b, _eta(ranks[a], codes[b]), "eta", int((~np.isnan(ranks[a])).sum()))
        for a in numerics
        for b in names
    ]
    return pd.DataFrame(records, columns=TABLE_COLUMNS)


def cluster_features(table: pd.DataFrame, max_assoc: float) -> dict[str, int]:
    """The redundancy clusters of the long `table`: average linkage on `1 − |statistic|`, cut at
    `1 − max_assoc`; feature → cluster number for clusters of two or more, numbered 1, 2, … by
    their first member, singletons left out.

    A "not compared" pair sits at distance 1, so it links only when the rest of a cluster
    outweighs it (ten or more near-identical members at the default 0.9).
    """
    features = list(pd.unique(pd.concat([table["a"], table["b"]])))
    if len(features) < 2:
        return {}
    where = {f: i for i, f in enumerate(features)}
    a, b = table["a"].map(where).to_numpy(), table["b"].map(where).to_numpy()
    distance = np.ones((len(features), len(features)))
    distance[a, b] = distance[b, a] = (1 - table["statistic"].abs()).fillna(1.0).clip(0, 1)
    np.fill_diagonal(distance, 0.0)
    labels = fcluster(linkage(squareform(distance), "average"), 1 - max_assoc, "distance")
    sizes = pd.Series(labels).value_counts()
    kept = [label for label in pd.unique(labels) if sizes[label] > 1]
    number = {label: i + 1 for i, label in enumerate(kept)}
    return {f: number[label] for f, label in zip(features, labels, strict=True) if label in number}


def explained_by_others(table: pd.DataFrame, members: list[str]) -> dict[str, float]:
    """Per member, the R² of it on the other numeric members from their Spearman submatrix,
    solved by least squares so an exact identity reads 1 (V4).

    NaN where not available, decided from the table before solving: a member without a Spearman
    pair inside `members` (a categorical, or the one numeric of a mixed-kind cluster), and every
    member when a Spearman pair among them is not compared (NaN, or absent). The caller names the
    reason from the pairs' methods.
    """
    if len(members) < 2:
        raise ValueError("explained_by_others: needs at least two members")
    missing = sorted(set(members) - set(table["a"]) - set(table["b"]))
    if missing:
        raise ValueError(f"explained_by_others: members {missing} are not in the table")
    inside = table["a"].isin(members) & table["b"].isin(members)
    pairs = table.loc[inside & (table["method"] == "spearman")]
    numerics = [m for m in members if m in set(pairs["a"]) | set(pairs["b"])]
    result = dict.fromkeys(members, float("nan"))
    where = {m: i for i, m in enumerate(numerics)}
    corr = np.full((len(numerics), len(numerics)), np.nan)
    np.fill_diagonal(corr, 1.0)
    a, b = (pairs[side].map(where).to_numpy(dtype=int) for side in ("a", "b"))
    corr[a, b] = corr[b, a] = pairs["statistic"].to_numpy(dtype=float)
    if np.isnan(corr).any():  # a pair not compared: no member's R² is available
        return result
    for i, member in enumerate(numerics):
        result[member] = _r_squared(corr, i)
    return result


def _null_mask_groups(present: np.ndarray) -> list[np.ndarray]:
    """The column indices grouped by identical null mask, in first-seen order."""
    groups: dict[bytes, list[int]] = {}
    for column in range(present.shape[1]):
        groups.setdefault(np.packbits(present[:, column]).tobytes(), []).append(column)
    return [np.array(columns) for columns in groups.values()]


def _ranks(values: np.ndarray, rows: np.ndarray, columns: np.ndarray) -> np.ndarray:
    """The ranks (ties averaged) of `columns` over `rows`, where every one of them is filled."""
    return stats.rankdata(values[np.ix_(rows, columns)], axis=0)


def _pearson(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The Pearson correlation of every column of `a` with every column of `b`; NaN where a
    column is constant."""
    a, b = a - a.mean(axis=0), b - b.mean(axis=0)
    scale = np.outer(np.sqrt((a**2).sum(axis=0)), np.sqrt((b**2).sum(axis=0)))
    result = np.full(scale.shape, np.nan)
    np.divide(a.T @ b, scale, out=result, where=scale > 0)
    return np.clip(result, -1.0, 1.0)


def _spearman_records(numeric: pd.DataFrame) -> list[tuple]:
    """The long-table rows of every numeric pair, with its shared filled rows."""
    matrix = spearman_matrix(numeric).to_numpy()
    present = numeric.notna().to_numpy(dtype=float)
    shared = present.T @ present
    names = list(numeric.columns)
    upper = zip(*np.triu_indices(len(names), k=1), strict=True)
    return [(names[i], names[j], matrix[i, j], "spearman", int(shared[i, j])) for i, j in upper]


def _codes(values: pd.Series) -> np.ndarray:
    """Integer level codes, null its own level."""
    return pd.factorize(values, use_na_sentinel=False)[0]


def _cramers_v(a: np.ndarray, b: np.ndarray) -> float:
    """Cramér's V (no bias correction) of two code arrays, NaN with fewer than two levels a
    side; every code occurs, so no marginal is empty (T29)."""
    levels_a, levels_b = a.max(initial=-1) + 1, b.max(initial=-1) + 1
    if levels_a < 2 or levels_b < 2:
        return float("nan")
    table = np.bincount(a * levels_b + b, minlength=levels_a * levels_b)
    observed = table.reshape(levels_a, levels_b)
    return float(contingency.association(observed, method="cramer", correction=False))


def _r_squared(corr: np.ndarray, i: int) -> float:
    """The R² of column `i` of a correlation matrix on the other columns, `r'R⁻¹r` by least
    squares; NaN outside [0, 1] (beyond `R2_TOLERANCE`).

    Pairwise-complete correlations need not form a positive semi-definite matrix, so R² can
    leave [0, 1]: it is then "not available: inconsistent correlations", never clipped and never
    an error.
    """
    others = np.arange(corr.shape[0]) != i
    target = corr[i, others]
    beta = np.linalg.lstsq(corr[np.ix_(others, others)], target, rcond=None)[0]
    r2 = float(target @ beta)
    if not -R2_TOLERANCE <= r2 <= 1 + R2_TOLERANCE:
        return float("nan")
    return min(max(r2, 0.0), 1.0)


def _eta(ranks: np.ndarray, codes: np.ndarray) -> float:
    """The correlation ratio η of `ranks` (NaN where unfilled) on the level `codes`,
    `√(between-level / total sum of squares)`; NaN under `MIN_SHARED_ROWS` filled rows, with one
    occupied level or no spread."""
    filled = ~np.isnan(ranks)
    if filled.sum() < MIN_SHARED_ROWS:
        return float("nan")
    values, levels = ranks[filled], codes[filled]
    counts = np.bincount(levels)
    sums = np.bincount(levels, weights=values)
    total = ((values - values.mean()) ** 2).sum()
    if (counts > 0).sum() < 2 or total == 0:
        return float("nan")
    occupied = counts > 0
    between = (sums[occupied] ** 2 / counts[occupied]).sum() - values.size * values.mean() ** 2
    return float(np.sqrt(np.clip(between / total, 0.0, 1.0)))
