"""The statistics engine on cells against exact oracles (D-082, D-135, T28, T32).

Cells are built in the test from synthetic rows the way the counts pass builds them, then every
statistic is checked against an oracle on the rows: the table concordance against
`roc_auc_score` (equal with values as bins, within 0.005 at 100 quantile bins), the regression
concordance against Somers' D from `kendalltau` and the tie counts on the binned rows (equal),
the Spearman matrix against pandas' pairwise Spearman, the intervals against scipy. The
level-encoding and best-order tests use the canonical sizes (100,000 rows a period, 2% base
rate) where they can: a 300-level random code over a six-period window reads below 0.55 in
sample and below 0.52 cross-fitted, an inverted U gains at least 0.05 from the best order, a
null control gains nothing that marks it. Two run the auditor's simulations small and over
several seeds, since one seed would test luck: a null numeric at 500 events is rarely marked
`non_monotone`, and a null 50-level code at 190 events a period reads high in sample and not
cross-fitted. No Spark.
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
    two_way_table,
)
from core_modelling.statistics.concordance import (
    SE_FLOOR,
    best_order_concordance,
    cochran_q,
    concordance_exact,
    concordance_from_table,
    concordance_se,
    cross_fitted_table,
    direction_from_table,
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
    null target's `sum_y` is NaN, as Spark's sum of nulls is null."""
    rows = rows.assign(feature="f", lagged=False)
    grouped = rows.groupby(KEYS, dropna=False)["y"]
    return pd.concat([grouped.size().rename("n"), grouped.sum(min_count=1).rename("sum_y")], axis=1)


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


def _categorical_cells(codes: np.ndarray, y: np.ndarray, periods: np.ndarray) -> pd.DataFrame:
    """One categorical's cells, `bin_order` its frequency rank, a binary target."""
    labels = codes.astype(str)
    rank = {level: i for i, level in enumerate(pd.Series(labels).value_counts().index)}
    rows = pd.DataFrame({"period": periods, "bin": labels, "is_null": False, "y": y,
                         "target_bin": y.astype(int).astype(str)})  # fmt: skip
    return _count(rows.assign(bin_order=rows["bin"].map(rank))).reset_index()


def _code_window(
    seed: int, levels: int, rows: int, effect: np.ndarray | None = None
) -> tuple[pd.DataFrame, list[str], float]:
    """Six periods of `rows` rows of a `levels`-level code at 2% (times `effect[code]`): the
    cells, the periods and the binary `k_rows`."""
    rng = np.random.default_rng(seed)
    names = [f"2025-0{m}" for m in range(3, 9)]
    periods = np.repeat(names, rows)
    codes = rng.integers(0, levels, periods.size)
    rate = 0.02 if effect is None else 0.02 * effect[codes]
    y = (rng.random(periods.size) < rate).astype(float)
    k_rows = TASK_SPECS["binary"]["shrinkage_rows"](50, y.mean())
    return _categorical_cells(codes, y, periods), names, k_rows


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
    Kendall null SE at 1,000 units, halved (0.010559); both floored at `SE_FLOOR`."""
    assert concordance_se(0.8, 50, 100) == pytest.approx(0.041247, abs=1e-6)
    assert concordance_se(1.0, 50, 100) == SE_FLOOR
    assert concordance_se(0.7, 1_000_000, 1_000_000) == SE_FLOOR
    assert kendall_null_se(1_000) == pytest.approx(0.010559, abs=1e-6)
    assert kendall_null_se(10_000_000) == SE_FLOOR
    assert TASK_SPECS["regression"]["concordance_se"](0.6, 400, 600) == kendall_null_se(1_000)
    with pytest.raises(ValueError, match="needs events and non-events, got 0 and 10"):
        concordance_se(0.6, 0, 10)


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
    on the window the code reads below 0.55, cross-fitted by period below 0.52."""
    cells, periods, k_rows = _code_window(seed=0, levels=300, rows=100_000)
    assert _in_sample(cells, periods, k_rows) < 0.55
    assert concordance_from_table(cross_fitted_table(cells, periods, k_rows), sign=1) < 0.52


def test_cross_fitting_removes_a_null_codes_in_sample_gain() -> None:
    """The auditor's case over 20 seeds: a null 50-level code at about 190 events a period reads
    above 0.53 in sample every time and, cross-fitted by period and read in the encoding's
    direction, never (0.52 at most, 0.495 on average)."""
    in_sample, cross_fitted = [], []
    for seed in range(20):
        cells, periods, k_rows = _code_window(seed, levels=50, rows=9_500)
        in_sample.append(_in_sample(cells, periods, k_rows))
        table = cross_fitted_table(cells, periods, k_rows)
        cross_fitted.append(concordance_from_table(table, sign=1))
    assert min(in_sample) > 0.53 > max(cross_fitted)
    assert np.mean(cross_fitted) < 0.505


def test_cross_fitting_keeps_a_predictive_codes_signal() -> None:
    """A 20-level code whose rate varies by level loses under 0.01 to cross-fitting at about 400
    events a period; the snapshot's value reads one period's rows; one period falls back to the
    in-sample order."""
    effect = np.exp(np.random.default_rng(99).normal(0, 0.6, 20))
    cells, periods, k_rows = _code_window(seed=0, levels=20, rows=20_000, effect=effect)
    cross_fitted = concordance_from_table(cross_fitted_table(cells, periods, k_rows), sign=1)
    assert 0 <= _in_sample(cells, periods, k_rows) - cross_fitted < 0.01 and cross_fitted > 0.6
    snapshot = cross_fitted_table(cells, periods, k_rows, read=[periods[-1]])
    assert snapshot.sum() == pool_periods(cells, [periods[-1]])["n"].sum()
    one = cross_fitted_table(cells, periods[:1], k_rows)
    assert concordance_from_table(one) == pytest.approx(_in_sample(cells, periods[:1], k_rows))
    with pytest.raises(ValueError, match="must name some of `periods`"):
        cross_fitted_table(cells, periods[:2], k_rows, read=[periods[3]])


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
        se = regression["concordance_se"](plain, 0, x.size)
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
    """Two periods summed per bin and target bin; the shares count unlabelled and null rows,
    the events only labelled non-null rows (N4, N6)."""
    x = np.array([0.0, 0.0, 0.0, 1.0, 2.0, np.nan, 0.0, 3.0])
    y = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 1.0, np.nan, 0.0])
    periods = np.array(["p1"] * 4 + ["p2"] * 4)
    cells = _numeric_cells(x, y, quantile_edges(x[~np.isnan(x)], 100), periods=periods)
    pooled = pool_periods(cells, ["p1", "p2"])
    assert pooled["n"].sum() == 8 and not pooled.duplicated(["bin", "target_bin"]).any()
    assert pooled.loc[pooled["target_bin"].isna(), "sum_y"].isna().all()  # unlabelled: no sum
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


def test_regression_shares_and_one_target_bin() -> None:
    """Regression events are the labelled non-null rows outside the zero target bin; a 0 written
    as `= 0.0` (six digits reading two edges alike) is still the zero bin; a table with one
    target bin has no concordance, which the caller sees first as no events."""
    x = np.array([0.0, 1.0, 2.0, 3.0, np.nan, 5.0])
    y = np.array([0.0, 4.0, 0.0, 7.5, 2.0, np.nan])
    target_edges = TASK_SPECS["regression"]["target_bins"](y[~np.isnan(y)], False)
    pooled = pool_periods(_numeric_cells(x, y, quantile_edges(x[~np.isnan(x)], 100),
                                         target_edges), [PERIOD])  # fmt: skip
    assert (shares(pooled)["events"], shares(pooled)["non_events"]) == (2, 2)
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
    groups = merge_bins(per_bin, 10)
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
    frame.loc[rng.random(3_000) < 0.8, "f"] = np.nan
    matrix = spearman_matrix(frame)
    expected = frame.corr(method="spearman")
    compared = list("abcde")
    np.testing.assert_allclose(matrix.loc[compared, compared], expected.loc[compared, compared])
    assert matrix.loc["a", "f"] != matrix.loc["a", "f"]  # NaN: about 600 shared rows


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
    cap's rows, the same for the same seed."""
    rng = np.random.default_rng(8)
    numeric = rng.normal(size=(3_000, 2))
    frame = pd.DataFrame(
        {"n1": numeric[:, 0], "n2": numeric[:, 1], "c1": rng.choice(["a", "b"], 3_000)}
    ).assign(c2=rng.choice(["x", "y"], 3_000))
    frame.loc[:99, "n2"] = np.nan
    kinds = {"n1": "numeric", "n2": "numeric", "c1": "categorical", "c2": "categorical"}
    table = association_table(frame, kinds, seed=1)
    assert sorted(table["method"]) == ["cramers_v", "eta", "eta", "eta", "eta", "spearman"]
    assert table.set_index(["a", "b"]).loc[("n1", "n2"), "rows"] == 2_900
    monkeypatch.setattr(association_module, "PAIRWISE_ROWS", 2_000)
    capped = association_table(frame, kinds, seed=1)
    assert capped.loc[capped["method"] == "cramers_v", "rows"].item() == 2_000
    pd.testing.assert_frame_equal(capped, association_table(frame, kinds, seed=1))


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
    bins (0 its own regression bin) and the headline."""
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
    headline = regression["base_rate_views"](pd.Series([0.0, 0.0, 3.0, 5.0]))
    assert headline["zero_share"] == 0.5 and headline["nonzero_units"] == 2
    with pytest.raises(ValueError, match="known targets"):
        binary["summarise_group"](pd.Series([1.0, np.nan]), 0.2)
