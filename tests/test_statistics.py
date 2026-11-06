"""The statistics engine on cells against exact oracles (D-082, D-135, T28, T32).

Cells are built in the test from synthetic rows the way the counts pass builds them, then every
statistic is checked against an oracle on the rows: the table concordance against
`roc_auc_score` (equal with values as bins, within 0.005 at 100 quantile bins), the regression
concordance against Somers' D from `kendalltau` and the tie counts on the binned rows (equal),
the Spearman matrix against pandas' pairwise Spearman, the intervals against scipy. The
level-encoding and best-order tests use the canonical sizes (100,000 rows a period, 2% base
rate) where they can: a 300-level random code over a six-period window reads below 0.55 in
sample and below 0.52 cross-fitted, an inverted U gains at least 0.05 from the best order, a
null control gains nothing that marks it. Four run the audits' simulations small and over
several seeds, since one seed would test luck: a null numeric at 500 events is rarely marked
`non_monotone`, and a null 50-level code at 190 events a period reads high in sample and not
cross-fitted; on a panel (the same clients in every period, a target that persists over a
three-month window) a null code reads high cross-fitted by period and not by client fold, and a
null numeric is not marked on the window's effective clients. A fifth checks the regression
concordance's SE against a null numeric's spread on a zero-inflated amount (300 seeds). No
Spark.
"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from scipy.stats import contingency
from sklearn.metrics import roc_auc_score

from core_modelling.statistics import association as association_module
from core_modelling.statistics.association import (
    association_table,
    cluster_features,
    correlation_ratio,
    cramers_v,
    explained_by_others,
    spearman_matrix,
)
from core_modelling.statistics.cells import (
    ZERO_LABELS,
    group_shares,
    level_share_difference,
    null_table,
    pool_periods,
    shares,
    support_by_bin,
    target_shares,
    two_way_table,
)
from core_modelling.statistics.concordance import (
    SE_FLOOR,
    best_order_concordance,
    cochran_q,
    concordance_exact,
    concordance_from_table,
    concordance_se,
    cross_fitted_concordance,
    direction_from_table,
    effective_count,
    encode_levels,
    is_non_monotone,
    kendall_null_se,
    ranking_value,
)
from core_modelling.statistics.distributions import bin_labels, merge_bins, quantile_edges
from core_modelling.statistics.intervals import t_interval, wilson_interval
from core_modelling.tasks import TASK_SPECS

PERIOD = "2025-08"
KEYS = ["feature", "period", "lagged", "bin", "bin_order", "is_null", "target_bin"]


def _count(rows: pd.DataFrame) -> pd.DataFrame:
    """Rows (`period, bin, bin_order, is_null, target_bin, y`) summed into counts-table cells; a
    null target's `sum_y` and `sum_y2` are NaN, as Spark's sum of nulls is null."""
    rows = rows.assign(feature="f", lagged=False, y2=rows["y"] ** 2)
    grouped = rows.groupby(KEYS + ["fold"] if "fold" in rows else KEYS, dropna=False)
    sums = grouped[["y", "y2"]].sum(min_count=1).set_axis(["sum_y", "sum_y2"], axis=1)
    return pd.concat([grouped.size().rename("n"), sums], axis=1)


def _numeric_cells(
    x: np.ndarray, y: np.ndarray, edges: np.ndarray, target_edges: np.ndarray | None = None,
    periods: np.ndarray | str = PERIOD,
) -> pd.DataFrame:  # fmt: skip
    """One numeric's cells: NaN `x` the null bin, NaN `y` unlabelled; a binary target unless
    `target_edges` bin it."""
    null = np.isnan(x)
    index = np.digitize(np.where(null, 0.0, x), edges)
    labels = np.array(bin_labels(edges))
    if target_edges is None:
        target_bin = np.where(np.isnan(y), None, np.nan_to_num(y).astype(int).astype(str))
    else:
        target_labels = np.array(bin_labels(target_edges))
        target_bin = np.where(np.isnan(y), None, target_labels[np.digitize(y, target_edges)])
    rows = pd.DataFrame({"period": periods, "bin": np.where(null, "null", labels[index]),
                         "bin_order": np.where(null, edges.size + 1, index), "is_null": null,
                         "target_bin": target_bin, "y": y})  # fmt: skip
    return _count(rows).reset_index()


def _null_numeric_marks(seed: int, events: int) -> tuple[bool, bool]:
    """A null numeric at 2% with `events` expected events: marked by the SE-scaled margin, and
    by the fixed 0.03 alone."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=events * 50)
    y = (rng.random(x.size) < 0.02).astype(float)
    pooled = pool_periods(_numeric_cells(x, y, quantile_edges(x, 100)), [PERIOD])
    plain = concordance_from_table(two_way_table(pooled))
    best = best_order_concordance(pooled, TASK_SPECS["binary"]["shrinkage_rows"](50, y.mean()))
    support = shares(pooled)
    se = concordance_se(plain, support["events"], support["non_events"])
    return is_non_monotone(plain, best, se), best >= plain + 0.03


def _categorical_cells(
    codes: np.ndarray, y: np.ndarray, periods: np.ndarray, folds: np.ndarray
) -> pd.DataFrame:
    """One categorical's cells with each row's client fold, `bin_order` its frequency rank, a
    binary target."""
    labels = codes.astype(str)
    rank = {level: i for i, level in enumerate(pd.Series(labels).value_counts().index)}
    rows = pd.DataFrame({"period": periods, "fold": folds, "bin": labels, "is_null": False,
                         "y": y, "target_bin": y.astype(int).astype(str)})  # fmt: skip
    return _count(rows.assign(bin_order=rows["bin"].map(rank))).reset_index()


def _code_window(
    seed: int, levels: int, rows: int, effect: np.ndarray | None = None
) -> tuple[pd.DataFrame, list[str], float]:
    """Six periods of `rows` rows of a `levels`-level code at 2% (times `effect[code]`), every
    row a new client: the cells, the periods and the binary `k_rows`."""
    rng = np.random.default_rng(seed)
    names = [f"2025-0{m}" for m in range(3, 9)]
    periods = np.repeat(names, rows)
    codes = rng.integers(0, levels, periods.size)
    rate = 0.02 if effect is None else 0.02 * effect[codes]
    y = (rng.random(periods.size) < rate).astype(float)
    k_rows = TASK_SPECS["binary"]["shrinkage_rows"](50, y.mean())
    folds = rng.integers(0, 5, periods.size)
    return _categorical_cells(codes, y, periods, folds), names, k_rows


def _kish_sizes(y: np.ndarray) -> dict[str, float]:
    """`counts.window_clients` on a clients × periods 0/1 target: per class and in all, the rows
    and Kish's effective clients `(Σ m)² / Σ m²` over each client's rows `m`."""
    sizes = {}
    for prefix, per_client in (("event_", (y == 1).sum(1)), ("non_event_", (y == 0).sum(1)),
                               ("", np.full(len(y), y.shape[1])),):  # fmt: skip
        sizes[f"{prefix}rows"] = float(per_client.sum())
        sizes[f"{prefix}effective"] = per_client.sum() ** 2 / (per_client**2).sum()
    return sizes


def _panel_targets(rng: np.random.Generator, clients: int) -> np.ndarray:
    """Six periods' targets of the same `clients`, at about 2%: an event in the three periods
    after each, at a client-specific rate, so a client's label persists (clients × periods)."""
    rate = 0.02 / 3 * rng.gamma(0.5, 2.0, clients)
    events = rng.random((clients, 10)) < rate[:, None]
    return np.stack([events[:, t + 1 : t + 4].any(axis=1) for t in range(6)], 1).astype(float)


def _in_sample(cells: pd.DataFrame, periods: list[str], k_rows: float) -> float:
    """The concordance of the pooled periods in the order of the encoding fitted on them."""
    pooled = pool_periods(cells, periods)
    encoding = encode_levels(pooled, k_rows)
    return concordance_from_table(two_way_table(pooled, sorted(encoding, key=encoding.get)))


def _pairs(rows: list[tuple[str, str, float, str]]) -> pd.DataFrame:
    """A long association table from `(a, b, statistic, method)` rows."""
    return pd.DataFrame(rows, columns=["a", "b", "statistic", "method"])


def _somers_from_kendall(x: np.ndarray, y: np.ndarray) -> float:
    """The oracle: Somers' D of x with respect to y from `kendalltau`'s τ-b and the tie counts,
    on the concordance scale."""

    def untied(values: np.ndarray) -> float:
        """Pairs of rows with different values."""
        counts = np.unique(values, return_counts=True)[1].astype(float)
        return (counts.sum() ** 2 - (counts**2).sum()) / 2

    tau_b = stats.kendalltau(x, y).statistic
    return (1 + abs(tau_b * np.sqrt(untied(x) / untied(y)))) / 2


def _binary(x: np.ndarray, rng: np.random.Generator, slope: float = 1.0) -> np.ndarray:
    """A 0/1 target with a logistic dependence on `x`."""
    return (rng.random(x.size) < 1 / (1 + np.exp(-(slope * np.nan_to_num(x) - 2)))).astype(float)


def test_table_concordance_equals_the_auc_with_values_as_bins() -> None:
    """A discrete column with nulls: its values are its bins, so the table gives the AUC of the
    non-null rows exactly (N6), and the null bin gives the null indicator's AUC."""
    rng = np.random.default_rng(0)
    x = rng.integers(0, 40, 2_000).astype(float)
    x[rng.random(x.size) < 0.1] = np.nan
    y = _binary(x / 10, rng)
    pooled = pool_periods(_numeric_cells(x, y, quantile_edges(x[~np.isnan(x)], 100)), [PERIOD])
    filled = ~np.isnan(x)
    auc = roc_auc_score(y[filled], x[filled])
    assert concordance_from_table(two_way_table(pooled)) == pytest.approx(max(auc, 1 - auc), 1e-12)
    null_auc = roc_auc_score(y, ~filled)
    assert concordance_from_table(null_table(pooled)) == pytest.approx(
        max(null_auc, 1 - null_auc), 1e-12
    )


def test_table_concordance_at_100_quantile_bins_is_within_0_005_of_the_raw_auc() -> None:
    """A continuous column cut into 100 quantile bins loses at most 0.005 of its AUC."""
    rng = np.random.default_rng(1)
    x = rng.normal(size=2_000)
    y = _binary(x, rng)
    table = two_way_table(pool_periods(_numeric_cells(x, y, quantile_edges(x, 100)), [PERIOD]))
    assert concordance_from_table(table) == pytest.approx(roc_auc_score(y, x), abs=0.005)


def test_direction_and_the_window_sign() -> None:
    """A falling feature has direction −1; read in the opposite direction it reads below 0.5;
    a weak one has no direction at a wide SE."""
    rng = np.random.default_rng(2)
    x = rng.normal(size=2_000)
    y = _binary(-x, rng)
    table = two_way_table(pool_periods(_numeric_cells(x, y, quantile_edges(x, 100)), [PERIOD]))
    value = concordance_from_table(table)
    assert direction_from_table(table, se=0.01) == -1
    assert direction_from_table(table, se=0.5) == 0
    assert concordance_from_table(table, sign=-1) == pytest.approx(value)
    assert concordance_from_table(table, sign=1) == pytest.approx(1 - value)


def test_regression_concordance_is_somers_d_from_kendalltau_on_the_binned_rows() -> None:
    """The regression table (100 feature bins × 20 target bins, 0 its own) equals Somers' D
    from τ-b and the tie counts on the binned rows, exactly (T32)."""
    rng = np.random.default_rng(3)
    x = rng.normal(size=2_000)
    y = np.exp(rng.normal(size=x.size) + 0.5 * x) * (rng.random(x.size) < 0.6)
    edges = quantile_edges(x, 100)
    target_edges = TASK_SPECS["regression"]["target_bins"](y, False)
    pooled = pool_periods(_numeric_cells(x, y, edges, target_edges), [PERIOD])
    table = two_way_table(pooled)
    assert table.shape[1] == 20
    oracle = _somers_from_kendall(np.digitize(x, edges), np.digitize(y, target_edges))
    assert concordance_from_table(table) == pytest.approx(oracle, abs=1e-12)


def test_exact_path_equals_the_table_with_values_as_bins() -> None:
    """`eda.bins: null` for regression: τ-b on the expanded cells gives the table's value and
    the raw rows' Somers' D."""
    rng = np.random.default_rng(4)
    x = rng.integers(0, 40, 3_000).astype(float)
    y = np.where(rng.random(x.size) < 0.4, 0.0, rng.poisson(1 + x / 8).astype(float))
    target_edges = TASK_SPECS["regression"]["target_bins"](y, True)
    cells = _numeric_cells(x, y, quantile_edges(x, np.unique(x).size), target_edges)
    pooled = pool_periods(cells, [PERIOD])
    exact = concordance_exact(pooled)
    assert exact == pytest.approx(concordance_from_table(two_way_table(pooled)), abs=1e-12)
    assert exact == pytest.approx(_somers_from_kendall(x, y), abs=1e-12)
    assert concordance_exact(pooled, sign=-1) == pytest.approx(1 - exact, abs=1e-12)


def test_standard_errors_follow_hanley_mcneil_and_kendall_with_the_floor() -> None:
    """Hanley–McNeil at A = 0.8 with 50 events and 100 non-events (hand value 0.041247); the
    Kendall null SE at 1,000 units without target ties, halved (0.010559, the tie factor 1 to
    1/n); both floored at `SE_FLOOR`; the binary hook leaves the target shares unread."""
    no_ties = np.full(1_000, 1e-3)
    assert concordance_se(0.8, 50, 100) == pytest.approx(0.041247, abs=1e-6)
    assert concordance_se(1.0, 50, 100) == SE_FLOOR
    assert concordance_se(0.7, 1_000_000, 1_000_000) == SE_FLOOR
    assert kendall_null_se(1_000, no_ties) == pytest.approx(0.010559, rel=2e-3)
    assert kendall_null_se(10_000_000, [0.5, 0.5]) == SE_FLOOR
    binary, regression = TASK_SPECS["binary"], TASK_SPECS["regression"]
    assert binary["concordance_se"](0.8, 50, 100, no_ties) == concordance_se(0.8, 50, 100)
    assert regression["concordance_se"](0.6, 400, 600, no_ties) == kendall_null_se(1_000, no_ties)
    with pytest.raises(ValueError, match="needs events and non-events, got 0 and 10"):
        concordance_se(0.6, 0, 10)


def test_kendall_se_scales_for_the_ties_on_the_target() -> None:
    """τ's null SE times `sqrt(1 − Σp³) / (1 − Σp²)`: a hand table's target shares (0.4, 0.3,
    0.3) at 100 units give 0.048263; two equal target bins give the Mann–Whitney null SE
    `sqrt((n + 1) / (12 n₁ n₂))` to 1/n; the floor comes after the factor (τ's SE alone is 0.0024
    at 20,000 units); shares that are negative, fill one bin or don't sum to 1 are refused."""
    table = np.array([[30.0, 10.0, 0.0], [10.0, 20.0, 30.0]])
    assert kendall_null_se(100, table.sum(axis=0) / 100) == pytest.approx(0.048263, abs=1e-6)
    mann_whitney = np.sqrt(1_001 / (12 * 500 * 500))
    assert kendall_null_se(1_000, [0.5, 0.5]) == pytest.approx(mann_whitney, rel=2e-3)
    assert kendall_null_se(20_000, [0.9, 0.1]) == pytest.approx(0.006805, abs=1e-6)
    for bad in ([0.5, 0.6], [1.0, 0.0], [1.2, -0.2], []):
        with pytest.raises(ValueError, match="the target shares must be"):
            kendall_null_se(1_000, bad)


def test_kendall_se_matches_a_null_numerics_spread_on_a_zero_inflated_target() -> None:
    """A null numeric (100 quantile bins) against a 70%-zero lognormal amount, 2,000 units, 300
    seeds: the concordance's spread is within 10% of the tie-scaled SE and about 1.6× the SE
    that leaves the target's ties out (a null feature then got a direction 21% of the time)."""
    regression, n = TASK_SPECS["regression"], 2_000
    signed, ses = [], []
    for seed in range(300):
        rng = np.random.default_rng(seed)
        x = rng.normal(size=n)
        y = np.where(rng.random(n) < 0.7, 0.0, rng.lognormal(size=n))
        feature_bin = np.digitize(x, quantile_edges(x, 100))
        target_bin = np.digitize(y, regression["target_bins"](y, False))
        table = np.zeros((feature_bin.max() + 1, target_bin.max() + 1))
        np.add.at(table, (feature_bin, target_bin), 1)
        signed.append(concordance_from_table(table, sign=1))
        events = int((y != 0).sum())
        value = max(signed[-1], 1 - signed[-1])
        ses.append(regression["concordance_se"](value, events, n - events, table.sum(axis=0) / n))
    spread = np.std(signed, ddof=1)
    assert spread / np.mean(ses) == pytest.approx(1, abs=0.1)
    assert spread / kendall_null_se(n, np.full(n, 1 / n)) > 1.4


def test_encoding_shrinks_levels_towards_the_base() -> None:
    """`(sum_y + k · base) / (n + k)` over labelled rows; the null level is left out (N7) and a
    level without labels scores the base."""
    cells = pd.DataFrame({
        "bin": ["a", "a", "b", "c", "null"], "bin_order": [0, 0, 1, 2, 3],
        "is_null": [False, False, False, False, True], "target_bin": ["1", "0", "0", None, "1"],
        "n": [10, 90, 100, 7, 50], "sum_y": [10.0, 0.0, 0.0, np.nan, 50.0],
    })  # fmt: skip
    encoding = encode_levels(cells, k_rows=100)
    assert set(encoding) == {"a", "b", "c"}
    assert encoding["a"] == pytest.approx((10 + 100 * 0.05) / (100 + 100))
    assert encoding["c"] == pytest.approx(0.05)


def test_a_300_level_random_code_over_a_canonical_window() -> None:
    """Six periods of 100,000 rows at 2% (12,000 events): ordered by its shrunk encoding fitted
    on the window the code reads below 0.55, cross-fitted by client fold below 0.52."""
    cells, periods, k_rows = _code_window(seed=0, levels=300, rows=100_000)
    assert _in_sample(cells, periods, k_rows) < 0.55
    assert cross_fitted_concordance(cells, periods, k_rows) < 0.52


def test_cross_fitting_removes_a_null_codes_in_sample_gain() -> None:
    """The auditor's case over 20 seeds: a null 50-level code at about 190 events a period reads
    above 0.53 in sample every time and, cross-fitted by client fold and read in the encoding's
    direction, never (about 0.50 on average)."""
    in_sample, cross_fitted = [], []
    for seed in range(20):
        cells, periods, k_rows = _code_window(seed, levels=50, rows=9_500)
        in_sample.append(_in_sample(cells, periods, k_rows))
        cross_fitted.append(cross_fitted_concordance(cells, periods, k_rows))
    assert min(in_sample) > 0.53 > max(cross_fitted)
    assert abs(np.mean(cross_fitted) - 0.5) < 0.005


def test_cross_fitting_skips_a_fold_without_the_read_period() -> None:
    """Fold 2's clients are all outside the read period: the fold is skipped, as one without
    labelled rows is, so the value equals the one with an unlabelled read-period cell added to
    fold 2 (a level it already has, so no encoding moves)."""
    rng = np.random.default_rng(3)
    names = ["2025-07", "2025-08"]
    periods = np.repeat(names, 600)
    folds = np.tile([0, 1, 2], 400)
    folds = np.where((periods == names[1]) & (folds == 2), rng.integers(0, 2, folds.size), folds)
    codes = rng.integers(0, 4, periods.size)
    y = (rng.random(periods.size) < 0.1 + 0.1 * codes).astype(float)
    cells = _categorical_cells(codes, y, periods, folds)
    k_rows = TASK_SPECS["binary"]["shrinkage_rows"](50, y.mean())
    value = cross_fitted_concordance(cells, names, k_rows, read=[names[1]])
    unlabelled = cells.iloc[[0]].assign(period=names[1], fold=2, target_bin=None, sum_y=np.nan)
    padded = pd.concat([cells, unlabelled], ignore_index=True)
    assert value == cross_fitted_concordance(padded, names, k_rows, read=[names[1]])
    assert 0.6 < value < 1


def test_cross_fitting_by_client_holds_on_a_panel() -> None:
    """The SDS's case over 10 seeds: 10,000 clients in every period, each keeping one of 50
    levels, unrelated to a target that persists (about 200 events a period). In sample it reads
    about 0.60 and cross-fitted by period (folds that are periods) still about 0.57, since the
    other periods hold the same clients and labels; by client fold 0.50 on average (40 seeds:
    0.502, SD 0.019, about 1.4× its SE on the ~500 event clients: single values of 0.53–0.55
    are noise)."""
    names = [f"2025-0{m}" for m in range(3, 9)]
    in_sample, by_period, by_client = [], [], []
    for seed in range(10):
        rng = np.random.default_rng(seed)
        y = _panel_targets(rng, 10_000)
        codes = np.tile(rng.integers(0, 50, 10_000), 6)
        periods = np.repeat(names, 10_000)
        outcome = y.T.reshape(-1)
        k_rows = TASK_SPECS["binary"]["shrinkage_rows"](50, outcome.mean())
        folds = np.tile(rng.integers(0, 5, 10_000), 6)
        cells = _categorical_cells(codes, outcome, periods, folds)
        in_sample.append(_in_sample(cells, names, k_rows))
        by_client.append(cross_fitted_concordance(cells, names, k_rows))
        one_label = np.full(periods.size, "window")  # the period moved into the fold
        as_periods = _categorical_cells(codes, outcome, one_label, np.repeat(np.arange(6), 10_000))
        by_period.append(cross_fitted_concordance(as_periods, ["window"], k_rows))
    assert min(in_sample) > 0.57 and np.mean(by_period) > 0.55
    assert abs(np.mean(by_client) - 0.5) < 0.01
    assert np.mean(by_period) - np.mean(by_client) > 0.05


def test_cross_fitting_keeps_a_predictive_codes_signal() -> None:
    """A 20-level code whose rate varies by level loses under 0.01 to cross-fitting at about 400
    events a period; one period's rows read alone; the lagged cells read against the encoding
    fitted on the current ones; cells outside the periods need no fold; a period's cells without
    one, a single fold and an empty `read` are refused."""
    effect = np.exp(np.random.default_rng(99).normal(0, 0.6, 20))
    cells, periods, k_rows = _code_window(seed=0, levels=20, rows=20_000, effect=effect)
    cross_fitted = cross_fitted_concordance(cells, periods, k_rows)
    assert 0 <= _in_sample(cells, periods, k_rows) - cross_fitted < 0.01 and cross_fitted > 0.6
    assert cross_fitted_concordance(cells, periods, k_rows, read=[periods[-1]]) > 0.6
    both = pd.concat([cells, cells.assign(lagged=True)])
    lagged = cross_fitted_concordance(both, periods, k_rows, lagged=True)
    assert lagged == pytest.approx(cross_fitted)
    later = cells.loc[cells["period"] == periods[-1]].assign(period="2025-09", fold=np.nan)
    with_later = pd.concat([cells, later])
    assert cross_fitted_concordance(with_later, periods, k_rows) == pytest.approx(cross_fitted)
    with pytest.raises(ValueError, match="needs a client fold"):
        cross_fitted_concordance(with_later, periods, k_rows, read=["2025-09"])
    with pytest.raises(ValueError, match="needs two client folds"):
        cross_fitted_concordance(cells.assign(fold=0), periods, k_rows)
    with pytest.raises(ValueError, match="names no period"):
        cross_fitted_concordance(cells, periods, k_rows, read=[])


def test_best_order_lifts_an_inverted_u_and_not_a_null_control() -> None:
    """At 100,000 rows and 2% (2,000 events), an inverted U gains at least 0.05 from the best
    order and is ranked by it; a null control stays below 0.55, unmarked."""
    rng = np.random.default_rng(0)
    x = rng.normal(size=100_000)
    edges = quantile_edges(x, 100)
    for rate, inverted_u in ((0.02 * (0.2 + 2.4 * np.exp(-(x**2))), True), (0.02, False)):
        y = (rng.random(x.size) < rate).astype(float)
        pooled = pool_periods(_numeric_cells(x, y, edges), [PERIOD])
        plain = concordance_from_table(two_way_table(pooled))
        best = best_order_concordance(pooled, TASK_SPECS["binary"]["shrinkage_rows"](50, y.mean()))
        support = shares(pooled)
        se = concordance_se(plain, support["events"], support["non_events"])
        assert is_non_monotone(plain, best, se) is inverted_u
        if inverted_u:
            assert best >= plain + 0.05 and ranking_value(plain, best, se) == best
        else:
            assert best < 0.55 and ranking_value(plain, best, se) == plain


def test_a_null_numeric_at_500_events_is_rarely_marked() -> None:
    """The auditor's case over 50 seeds: the SE-scaled margin leaves at least 98% of null
    numerics at 500 events unmarked, where the fixed 0.03 alone marks many of them."""
    marks = [_null_numeric_marks(seed, events=500) for seed in range(50)]
    assert sum(scaled for scaled, _ in marks) <= 1
    assert sum(fixed for _, fixed in marks) >= 10


def test_a_panel_null_numeric_is_rarely_marked_on_distinct_clients() -> None:
    """Over 20 seeds, 5,000 clients in every period with a persistent value unrelated to a
    persistent target (about 100 events a period): the window's SE on its rows marks some of
    them `non_monotone`, the SE on its effective clients (`client_support`) at most one."""
    names = [f"2025-0{m}" for m in range(3, 9)]
    on_rows = on_clients = 0
    for seed in range(20):
        rng = np.random.default_rng(seed)
        y = _panel_targets(rng, 5_000)
        x = rng.normal(size=5_000)[:, None] + 0.1 * rng.normal(size=(5_000, 6))
        cells = _numeric_cells(x.T.reshape(-1), y.T.reshape(-1), quantile_edges(x[:, -1], 100),
                               periods=np.repeat(names, 5_000))  # fmt: skip
        pooled = pool_periods(cells, names)
        plain = concordance_from_table(two_way_table(pooled))
        best = best_order_concordance(pooled, TASK_SPECS["binary"]["shrinkage_rows"](50, y.mean()))
        support = shares(pooled)
        rows_se = concordance_se(plain, support["events"], support["non_events"])
        events = TASK_SPECS["binary"]["client_support"](
            support["events"], support["non_events"], _kish_sizes(y)
        )
        on_rows += is_non_monotone(plain, best, rows_se)
        on_clients += is_non_monotone(plain, best, concordance_se(plain, *events))
    assert on_clients <= 1 < on_rows


def test_client_support_per_task() -> None:
    """Binary scales each class by its own ratio; regression scales the units by the window's
    one ratio and takes a target without zeros; a feature's few rows keep one row's worth; a
    class without rows is refused."""
    clients = {"event_rows": 300.0, "event_effective": 100.0, "non_event_rows": 6_000.0,
               "non_event_effective": 3_000.0, "rows": 6_300.0, "effective": 2_100.0}  # fmt: skip
    assert TASK_SPECS["binary"]["client_support"](30, 600, clients) == (10.0, 300.0)
    assert TASK_SPECS["binary"]["client_support"](2, 600, clients)[0] == 1.0
    assert TASK_SPECS["regression"]["client_support"](30, 0, clients) == (10.0, 0.0)
    assert TASK_SPECS["regression"]["concordance_se"](0.6, 10.0, 0.0, [0.5, 0.5]) > 0
    # the audit's case: a strictly positive amount on two rows of a 1,002-row window keeps two
    # units, split by the classes' shares, so Kendall's SE exists
    few = TASK_SPECS["regression"]["client_support"](2, 0, {"rows": 1_002.0, "effective": 200.0})
    assert few == (2.0, 0.0)
    assert np.isfinite(TASK_SPECS["regression"]["concordance_se"](0.7, *few, [0.5, 0.5]))
    assert TASK_SPECS["regression"]["client_support"](3, 3, clients) == (1.0, 1.0)
    with pytest.raises(ValueError, match="no labelled rows of this class"):
        effective_count(5, 0, 0)


def test_best_order_on_a_regression_target() -> None:
    """A zero-inflated amount: an inverted U in both the non-zero share and the size is marked
    and gains at least 0.1; a null amount is not marked (Kendall's null SE in units)."""
    rng = np.random.default_rng(0)
    x = rng.normal(size=20_000)
    bump = np.exp(-(x**2))
    regression = TASK_SPECS["regression"]
    for scale, share, inverted_u in ((0.5 + 4 * bump, 0.2 + 0.6 * bump, True), (2.0, 0.5, False)):
        y = rng.exponential(scale, x.size) * (rng.random(x.size) < share)
        target_edges = regression["target_bins"](y, False)
        pooled = pool_periods(_numeric_cells(x, y, quantile_edges(x, 100), target_edges), [PERIOD])
        plain = concordance_from_table(two_way_table(pooled))
        best = best_order_concordance(pooled, regression["shrinkage_rows"](50, y.mean()))
        se = regression["concordance_se"](plain, 0, x.size, target_shares(pooled))
        assert is_non_monotone(plain, best, se) is inverted_u
        assert best >= plain + 0.1 if inverted_u else best < 0.53


def test_ranking_value_on_both_sides_of_the_margin() -> None:
    """Best-order from plain + max(0.03, 4 SE) on (V2); a missing SE is refused."""
    assert ranking_value(0.60, 0.62, se=0.005) == 0.60
    assert ranking_value(0.60, 0.64, se=0.005) == 0.64
    assert ranking_value(0.60, 0.55, se=0.005) == 0.60
    assert ranking_value(0.60, 0.64, se=0.02) == 0.60
    assert ranking_value(0.60, 0.69, se=0.02) == 0.69
    with pytest.raises(ValueError, match="se must be a non-negative number"):
        is_non_monotone(0.60, 0.69, float("nan"))


def test_cochran_q_against_the_chi_square() -> None:
    """Q around the weighted mean with k − 1 degrees of freedom; one value is refused."""
    values, ses = np.array([0.60, 0.70, 0.65]), np.array([0.02, 0.03, 0.025])
    weights = 1 / ses**2
    pooled = (weights * values).sum() / weights.sum()
    q = (weights * (values - pooled) ** 2).sum()
    assert cochran_q(values, ses) == pytest.approx(stats.chi2.sf(q, 2))
    with pytest.raises(ValueError, match="at least two"):
        cochran_q(np.array([0.6]), np.array([0.02]))
    with pytest.raises(ValueError, match="positive"):
        cochran_q(values, np.array([0.02, 0.0, 0.03]))


def test_intervals_against_scipy() -> None:
    """Wilson against `binomtest`, scalar and vectorised; t against `stats.t.interval`."""
    cases = [(0, 10), (3, 10), (50, 1_000), (999, 1_000), (1, 1)]
    for k, n in cases:
        expected = stats.binomtest(k, n).proportion_ci(method="wilson")
        assert wilson_interval(k, n) == pytest.approx((expected.low, expected.high), abs=1e-12)
    low, high = wilson_interval(np.array([3, 50]), np.array([10, 1_000]))
    assert low.shape == (2,) and high[1] > low[1]
    expected = stats.t.interval(0.95, 19, loc=2.0, scale=1.5 / np.sqrt(20))
    assert t_interval(2.0, 1.5, 20) == pytest.approx(expected)
    with pytest.raises(ValueError):
        wilson_interval(5, 3)


def test_pool_periods_and_shares() -> None:
    """Two periods summed per bin and target bin, `sum_y2` too; the shares count unlabelled and
    null rows, the events only labelled non-null rows (N4, N6)."""
    x = np.array([0.0, 0.0, 0.0, 1.0, 2.0, np.nan, 0.0, 3.0])
    y = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 1.0, np.nan, 0.0])
    periods = np.array(["p1"] * 4 + ["p2"] * 4)
    cells = _numeric_cells(x, y, quantile_edges(x[~np.isnan(x)], 100), periods=periods)
    pooled = pool_periods(cells, ["p1", "p2"])
    assert pooled["n"].sum() == 8 and not pooled.duplicated(["bin", "target_bin"]).any()
    assert pooled.loc[pooled["target_bin"].isna(), ["sum_y", "sum_y2"]].isna().all(axis=None)
    labelled = pooled.dropna(subset=["target_bin"])  # binary: y² = y
    assert labelled["sum_y2"].tolist() == labelled["sum_y"].tolist()
    summary = shares(pooled)
    assert summary == {"rows": 8, "missing_share": 1 / 8, "zero_share": 4 / 7,
                       "dominant_share": 4 / 8, "dominant_value": "= 0", "bins": 4,
                       "events": 2, "non_events": 4}  # fmt: skip
    with pytest.raises(ValueError, match="no current cells"):
        pool_periods(cells, ["p3"])
    with pytest.raises(ValueError, match="pool the periods first"):
        two_way_table(pd.concat([pooled, pooled]))
    with pytest.raises(ValueError, match="not in `order`"):
        two_way_table(pooled, order=["= 0"])


def test_support_by_bin_counts_each_bins_labelled_rows_outside_the_zero_target_bin() -> None:
    """Per bin, the labelled rows with a non-zero target: the null bin's too, a bin without one
    (zero or unlabelled) 0; over the non-null bins they sum to `shares`' events."""
    x = np.array([0.0, 0.0, 1.0, 1.0, np.nan, np.nan, 2.0, 3.0])
    y = np.array([0.0, 4.0, 0.0, 7.5, 2.0, np.nan, 0.0, np.nan])
    target_edges = TASK_SPECS["regression"]["target_bins"](y[~np.isnan(y)], False)
    cells = _numeric_cells(x, y, quantile_edges(x[~np.isnan(x)], 100), target_edges)
    pooled = pool_periods(cells, [PERIOD])
    support = support_by_bin(pooled)
    assert sorted(support.index) == sorted(pooled["bin"].unique()) and support["null"] == 1
    assert sorted(support.tolist()) == [0, 0, 1, 1, 1]
    assert support.drop("null").sum() == shares(pooled)["events"]


def test_regression_shares_and_one_target_bin() -> None:
    """Regression events are the labelled non-null rows outside the zero target bin, and the
    target shares are those rows'; a 0 written as `= 0.0` (six digits reading two edges alike)
    is still the zero bin; a table with one target bin has no concordance, which the caller sees
    first as no events."""
    x = np.array([0.0, 1.0, 2.0, 3.0, np.nan, 5.0])
    y = np.array([0.0, 4.0, 0.0, 7.5, 2.0, np.nan])
    target_edges = TASK_SPECS["regression"]["target_bins"](y[~np.isnan(y)], False)
    pooled = pool_periods(_numeric_cells(x, y, quantile_edges(x[~np.isnan(x)], 100),
                                         target_edges), [PERIOD])  # fmt: skip
    assert (shares(pooled)["events"], shares(pooled)["non_events"]) == (2, 2)
    assert sorted(target_shares(pooled)) == [0.25, 0.25, 0.5]
    large = np.concatenate([np.zeros(1_000), 1e6 + np.arange(1_000) / 1_000])
    edges = quantile_edges(large, 100)
    assert bin_labels(edges)[1] == "= 0.0" and set(ZERO_LABELS) == {"= 0", "= 0.0"}
    cells = _numeric_cells(large, np.zeros(large.size), edges)
    summary = shares(pool_periods(cells, [PERIOD]))
    assert summary["zero_share"] == 0.5 and summary["events"] == 0
    with pytest.raises(ValueError, match="needs labelled rows in at least two target bins"):
        concordance_from_table(two_way_table(pool_periods(cells, [PERIOD])))


def test_group_shares_place_an_outlying_bin_in_the_outer_group() -> None:
    """Groups cut on one period starting at bin 3: another period's bin 1 lands in group 0."""
    groups = pd.DataFrame({"bin_order_first": [3, 6], "bin_order_last": [5, 9]})
    cells = pd.DataFrame({"bin_order": [1, 3, 7, 10], "is_null": [False, False, False, True],
                          "n": [10, 20, 30, 40]})  # fmt: skip
    np.testing.assert_allclose(group_shares(cells, groups), [0.3, 0.3, 0.4])


def test_group_shares_align_two_periods_bin_for_bin() -> None:
    """Groups cut on one period apply to another: the same groups, the null bin last, a bin
    the first period lacks joining the outer group."""
    rng = np.random.default_rng(5)
    x = np.concatenate([rng.normal(size=5_000), rng.normal(0.3, 1.2, 5_000)])
    x[rng.random(x.size) < 0.05] = np.nan
    periods = np.repeat(["p1", "p2"], 5_000)
    edges = quantile_edges(x[:5_000][~np.isnan(x[:5_000])], 100)
    cells = _numeric_cells(x, np.zeros(x.size), edges, periods=periods)
    first, second = pool_periods(cells, ["p1"]), pool_periods(cells, ["p2"])
    per_bin = first.loc[~first["is_null"]].groupby(["bin_order", "bin"], as_index=False)["n"].sum()
    groups = merge_bins(per_bin, 10, edges)
    a, b = group_shares(first, groups), group_shares(second, groups)
    assert a.shape == b.shape == (len(groups) + 1,)
    assert a.sum() == pytest.approx(1) and b.sum() == pytest.approx(1)
    assert a[-1] == pytest.approx(first.loc[first["is_null"], "n"].sum() / first["n"].sum())
    assert level_share_difference(first, first) == 0
    assert 0 < level_share_difference(first, second) < 1


def test_spearman_matrix_is_pandas_pairwise_spearman_across_null_patterns() -> None:
    """Three null masks: equal to `DataFrame.corr(method="spearman")`; a pair under
    `MIN_SHARED_ROWS` shared rows is not compared."""
    rng = np.random.default_rng(6)
    base = rng.normal(size=(3_000, 1))
    frame = pd.DataFrame(base + rng.normal(size=(3_000, 6)), columns=list("abcdef"))
    frame.loc[rng.random(3_000) < 0.1, ["c", "d"]] = np.nan
    frame.loc[rng.random(3_000) < 0.3, "e"] = np.nan
    frame.loc[rng.random(3_000) < 0.9, "f"] = np.nan
    matrix = spearman_matrix(frame)
    expected = frame.corr(method="spearman")
    compared = list("abcde")
    np.testing.assert_allclose(matrix.loc[compared, compared], expected.loc[compared, compared])
    assert matrix.loc["a", "f"] != matrix.loc["a", "f"]  # NaN: about 300 shared rows


def test_correlation_ratio_is_spearman_for_two_levels_and_cramers_v_guards() -> None:
    """η on ranks equals |Spearman| with a 0/1 grouping; Cramér's V matches scipy, takes null
    as a level and is not compared with one level (T29)."""
    rng = np.random.default_rng(7)
    x = pd.Series(rng.normal(size=3_000))
    group = pd.Series((x + rng.normal(size=x.size) > 0.5).astype(int))
    assert correlation_ratio(x, group.astype(str)) == pytest.approx(
        abs(stats.spearmanr(x, group).statistic)
    )
    a = pd.Series(rng.choice(["u", "v", None], 3_000))
    b = pd.Series(np.where(a.isna(), "w", rng.choice(["w", "z"], 3_000)))
    table = pd.crosstab(a.fillna("null"), b).to_numpy()
    plain = contingency.association(table, method="cramer", correction=False)
    assert cramers_v(a, b) == pytest.approx(plain)
    assert np.isnan(cramers_v(a, pd.Series(["w"] * 3_000)))
    identity = pd.Series(["u"] * 50 + ["v"] * 50)
    assert cramers_v(identity, identity.copy()) == 1.0  # Yates' correction would read below 1


def test_association_table_methods_rows_and_seeded_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """One row per pair with its method and rows; above the cap a seeded sample of exactly the
    cap's rows (`pairwise_sample`), the same on every call."""
    rng = np.random.default_rng(8)
    numeric = rng.normal(size=(3_000, 2))
    frame = pd.DataFrame(
        {"n1": numeric[:, 0], "n2": numeric[:, 1], "c1": rng.choice(["a", "b"], 3_000)}
    ).assign(c2=rng.choice(["x", "y"], 3_000))
    frame.loc[:99, "n2"] = np.nan
    kinds = {"n1": "numeric", "n2": "numeric", "c1": "categorical", "c2": "categorical"}
    table = association_table(frame, kinds)
    assert sorted(table["method"]) == ["cramers_v", "eta", "eta", "eta", "eta", "spearman"]
    assert table.set_index(["a", "b"]).loc[("n1", "n2"), "rows"] == 2_900
    monkeypatch.setattr(association_module, "PAIRWISE_ROWS", 2_000)
    capped = association_table(frame, kinds)
    assert capped.loc[capped["method"] == "cramers_v", "rows"].item() == 2_000
    pd.testing.assert_frame_equal(capped, association_table(frame, kinds))


def test_cluster_features_on_a_hand_table() -> None:
    """Two linked pairs (one negative), one singleton; the not-compared pair a–f is never
    linked, though f is close to b (average linkage, Q472)."""
    table = pd.DataFrame(
        [("a", "b", 0.96), ("c", "d", -0.93), ("a", "e", 0.2), ("b", "f", 0.95),
         ("a", "f", np.nan), ("c", "e", 0.1)],
        columns=["a", "b", "statistic"],
    )  # fmt: skip
    assert cluster_features(table, max_assoc=0.9) == {"a": 1, "b": 1, "c": 2, "d": 2}


def test_explained_by_others_reads_one_on_an_identity_and_zero_on_noise() -> None:
    """From a correlation table: c = a + b is fully explained, independent columns are not."""
    rng = np.random.default_rng(9)
    a, b, noise = rng.normal(size=(3, 5_000))
    names = ["x", "y", "z"]
    pairs = [(0, 1), (0, 2), (1, 2)]
    for third, identity in ((a + b, True), (noise, False)):
        corr = np.corrcoef(np.vstack([a, b, third]))
        rows = [(names[i], names[j], corr[i, j], "spearman") for i, j in pairs]
        explained = explained_by_others(_pairs(rows), names)
        if identity:
            assert explained == pytest.approx(dict.fromkeys(names, 1.0))
        else:
            assert max(explained.values()) < 0.01


def test_explained_by_others_where_it_is_not_available() -> None:
    """The reviewer's probe, eleven members at 0.99 and one pair not compared: NaN for all
    (filled with 0 it read above 1 and was clipped). A mixed cluster: the numerics on each
    other, NaN for the categorical; a categorical cluster: NaN. A complete but impossible
    submatrix is refused."""
    names = [f"m{i}" for i in range(11)]
    rows = [(a, b, 0.99, "spearman") for i, a in enumerate(names) for b in names[i + 1 :]]
    rows[0] = ("m0", "m1", np.nan, "spearman")
    assert all(np.isnan(value) for value in explained_by_others(_pairs(rows), names).values())
    mixed = _pairs([("n1", "n2", 0.95, "spearman"), ("n1", "c", 0.9, "eta"),
                    ("n2", "c", 0.9, "eta")])  # fmt: skip
    explained = explained_by_others(mixed, ["n1", "n2", "c"])
    assert explained["n1"] == pytest.approx(0.9025) and explained["n2"] == pytest.approx(0.9025)
    assert np.isnan(explained["c"])
    categorical = explained_by_others(_pairs([("c1", "c2", 0.95, "cramers_v")]), ["c1", "c2"])
    assert all(np.isnan(value) for value in categorical.values())
    impossible = _pairs([("a", "b", 0.9, "spearman"), ("b", "c", 0.9, "spearman"),
                         ("a", "c", -0.9, "spearman")])  # fmt: skip
    inconsistent = explained_by_others(impossible, ["a", "b", "c"])
    assert all(np.isnan(value) for value in inconsistent.values())  # not positive semi-definite


def test_regression_group_summary_with_zeros() -> None:
    """Rows, support (non-zero units), the mean with its t-interval and the median, the lift,
    the non-zero share with its Wilson interval and the non-zero mean and median."""
    target = pd.Series([0.0, 0.0, 2.0, 4.0, 0.0, 6.0, 0.0, 8.0])
    summary = TASK_SPECS["regression"]["summarise_group"](target, 2.0)
    low, high = stats.t.interval(0.95, 7, loc=2.5, scale=target.std() / np.sqrt(8))
    share = stats.binomtest(4, 8).proportion_ci(method="wilson")
    assert summary == pytest.approx({
        "rows": 8, "support": 4, "estimate": 2.5, "low": low, "high": high, "median": 1.0,
        "nonzero_share": 0.5, "nonzero_low": share.low, "nonzero_high": share.high,
        "nonzero_mean": 5.0, "nonzero_median": 5.0, "lift": 1.25,
    })  # fmt: skip
    assert "lift" not in TASK_SPECS["regression"]["summarise_group"](target, 0.0)


def test_binary_group_summary_and_the_task_entries() -> None:
    """The binary summary; the lift test, the rare effect, the events warning, the target
    bins (0 its own regression bin), the estimate's noun (no `period_interval` any more) and the
    headline."""
    binary, regression = TASK_SPECS["binary"], TASK_SPECS["regression"]
    summary = binary["summarise_group"](pd.Series([1.0, 0.0, 0.0, 1.0, 0.0]), 0.2)
    assert summary["support"] == 2 and summary["estimate"] == 0.4 and summary["lift"] == 2.0
    assert not regression["lift_available"](0.0) and not regression["lift_available"](-1.0)
    assert regression["lift_available"](0.1) and binary["lift_available"](0.02)
    assert binary["rare_effect"](0.10, 0.02) == pytest.approx(5.0)
    assert binary["rare_effect"](0.10, 0.0) == np.inf and binary["rare_effect"](0.0, 0.0) == 1.0
    assert regression["rare_effect"](3.0, 2.0) == 1.5
    with pytest.raises(ValueError, match="rest's mean 0.0 is not positive"):
        regression["rare_effect"](3.0, 0.0)
    assert "499 positive events" in binary["events_warning"](499)
    assert regression["support_name"] in regression["events_warning"](499)
    assert regression["events_warning"](500) is None
    assert binary["target_bins"](np.array([0.0, 1.0]), False) is None
    edges = regression["target_bins"](np.arange(1.0, 101.0), False)
    assert "= 0" in bin_labels(edges) and len(bin_labels(edges)) == 22
    assert (binary["estimate_noun"], regression["estimate_noun"]) == ("rate", "mean")
    assert "period_interval" not in binary and "period_interval" not in regression
    headline = regression["base_rate_views"](pd.Series([0.0, 0.0, 3.0, 5.0]))
    assert headline["zero_share"] == 0.5 and headline["nonzero_units"] == 2
    with pytest.raises(ValueError, match="known targets"):
        binary["summarise_group"](pd.Series([1.0, np.nan]), 0.2)
