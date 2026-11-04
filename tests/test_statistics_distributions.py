"""The edges rule, the labels, the merge rule and the two-distribution measures (T25, D-135).

Three constructed columns at 100 bins check `quantile_edges`: 90% zeros with a lognormal tail,
Poisson counts (every value a singleton), a continuous normal. Each must give at least half the
bins asked (or one per distinct value), every mass point its own bin and no other bin above
`2 / bins`; the plain `np.quantile` edges on the zero-inflated column collapse, which is why the
rule exists. `merge_bins` keeps a 90% mass point alone and splits the rest into the other nine
groups, and a 20% spike inside a normal column gets its own group; `psi`, `new_level_share` and
`standardised_difference` are checked on hand-computed values and their edge cases, including
the inputs they refuse. No Spark.
"""

import numpy as np
import pandas as pd
import pytest

from core_modelling.statistics.distributions import (
    PSI_FLOOR,
    bin_labels,
    merge_bins,
    new_level_share,
    psi,
    quantile_edges,
    standardised_difference,
)

BINS = 100
ROWS = 100_000


@pytest.fixture(scope="module")
def zero_inflated() -> np.ndarray:
    """90% zeros and a lognormal tail."""
    rng = np.random.default_rng(0)
    return np.concatenate([np.zeros(ROWS * 9 // 10), rng.lognormal(0.0, 1.0, ROWS // 10)])


def _bin_shares(values: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Every bin's share of `values` and whether it is a singleton (`[v, nextafter(v))`)."""
    counts = np.bincount(np.digitize(values, edges), minlength=edges.size + 1)
    singleton = np.zeros(edges.size + 1, dtype=bool)
    singleton[1:-1] = edges[1:] == np.nextafter(edges[:-1], np.inf)
    return counts / values.size, singleton


def _check_edges_rule(values: np.ndarray, edges: np.ndarray) -> int:
    """Strictly increasing finite edges, every mass point a singleton holding exactly its rows,
    no other bin above `2 / BINS`; returns the number of occupied bins."""
    assert np.isfinite(edges).all() and (np.diff(edges) > 0).all()
    shares, singleton = _bin_shares(values, edges)
    assert (shares[~singleton] <= 2 / BINS + 1e-3).all()
    distinct, counts = np.unique(values, return_counts=True)
    is_mass = counts >= values.size / BINS
    for value, count in zip(distinct[is_mass], counts[is_mass], strict=True):
        index = np.digitize(value, edges)
        assert singleton[index] and shares[index] == count / values.size
    return int((shares > 0).sum())


def test_zero_inflated_column_keeps_zero_alone_and_bins_the_tail(zero_inflated: np.ndarray) -> None:
    """Zero is a singleton holding only zeros, the tail fills the other bins, and plain quantile
    edges would have collapsed onto zero."""
    edges = quantile_edges(zero_inflated, BINS)
    assert _check_edges_rule(zero_inflated, edges) >= BINS / 2
    zero_bin = np.digitize(0.0, edges)
    assert (zero_inflated[np.digitize(zero_inflated, edges) == zero_bin] == 0).all()
    plain = np.unique(np.quantile(zero_inflated, np.arange(1, BINS) / BINS))
    assert plain.size <= 15
    labels = bin_labels(edges)
    assert len(labels) == edges.size + 1
    assert labels[0] == "< 0" and labels[1] == "= 0" and labels[2].startswith("(0, ")
    assert labels[-1].startswith("≥ ")


def test_discrete_column_gives_one_singleton_per_value() -> None:
    """Poisson counts have a dozen distinct values: each is its own bin, and nothing else."""
    values = np.random.default_rng(1).poisson(3.0, ROWS).astype(float)
    edges = quantile_edges(values, BINS)
    distinct = np.unique(values)
    assert _check_edges_rule(values, edges) == distinct.size
    assert edges.size == 2 * distinct.size
    assert bin_labels(edges)[1::2] == [f"= {v:g}" for v in distinct]


def test_continuous_column_gets_equal_share_bins() -> None:
    """A normal column has no mass point: `BINS` bins of about `1 / BINS` each."""
    values = np.random.default_rng(2).normal(size=ROWS)
    edges = quantile_edges(values, BINS)
    assert edges.size == BINS - 1
    assert _check_edges_rule(values, edges) == BINS
    shares, _ = _bin_shares(values, edges)
    assert shares.max() <= 1 / BINS + 1e-3


def test_quantile_edges_edge_cases() -> None:
    """Empty values give no edge, infinities take no edge and land in the outer bins, NaN and a
    bin count below one are refused."""
    assert quantile_edges(np.array([]), BINS).size == 0
    with_inf = np.array([-np.inf, 1.0, 2.0, 3.0, np.inf])
    edges = quantile_edges(with_inf, BINS)
    assert np.isfinite(edges).all()
    assert np.digitize(-np.inf, edges) == 0 and np.digitize(np.inf, edges) == edges.size
    with pytest.raises(ValueError, match="NaN"):
        quantile_edges(np.array([1.0, np.nan]), BINS)
    with pytest.raises(ValueError, match="bins"):
        quantile_edges(np.array([1.0]), 0)


def test_bin_labels_read_singletons_and_the_bins_around_them() -> None:
    """Hand edges give `<`, `=`, `(v, e)`, `[e, e)` and `≥`; a singleton closing the range reads
    `> v`; -0.0 reads `= 0`; integer codes that six digits would merge fall back to their exact
    text."""
    edges = np.array([0.0, np.nextafter(0.0, np.inf), 1.5, 10.0])
    assert bin_labels(edges) == ["< 0", "= 0", "(0, 1.5)", "[1.5, 10)", "≥ 10"]
    assert bin_labels(quantile_edges(np.array([2.0, 2.0, 5.0]), BINS))[-1] == "> 5"
    assert bin_labels(quantile_edges(np.array([-0.0, -0.0, 1.0]), BINS))[1] == "= 0"
    codes = quantile_edges(np.repeat([1000001.0, 1000002.0], 5), BINS)
    labels = bin_labels(codes)
    assert len(set(labels)) == len(labels) == codes.size + 1
    assert labels[1] == "= 1000001.0"
    assert bin_labels(np.array([])) == ["all"]


def _cells(n: np.ndarray, labels: list[str] | None = None) -> pd.DataFrame:
    """One feature's pooled cells from counts per bin, with `sum_y` a tenth of `n`."""
    labels = labels or [f"b{i}" for i in range(n.size)]
    return pd.DataFrame(
        {"bin": labels, "bin_order": np.arange(n.size), "n": n, "sum_y": n / 10, "feature": "x"}
    )


def _counted_cells(values: np.ndarray) -> pd.DataFrame:
    """The occupied, labelled cells of `values` binned on their `quantile_edges` at `BINS`."""
    edges = quantile_edges(values, BINS)
    counts = np.bincount(np.digitize(values, edges), minlength=edges.size + 1)
    occupied = counts > 0
    return _cells(counts[occupied], list(np.array(bin_labels(edges))[occupied]))


def test_merge_bins_keeps_the_mass_point_and_splits_the_rest(zero_inflated: np.ndarray) -> None:
    """The zero bin is one group of ten; the tail's bins share the other nine about equally,
    and `sum_y` is summed along."""
    cells = _counted_cells(zero_inflated)
    merged = merge_bins(cells, 10)
    columns = ["group", "bin_order_first", "bin_order_last", "label", "n", "sum_y"]
    assert list(merged.columns) == columns
    assert list(merged["group"]) == list(range(10))
    zero = merged.iloc[0]
    assert zero["label"] == "= 0" and zero["n"] == ROWS * 9 // 10
    assert zero["bin_order_first"] == zero["bin_order_last"]
    tail = merged.iloc[1:]
    assert np.allclose(tail["n"], ROWS // 10 / 9, atol=2 * cells["n"].iloc[1:].max())
    assert merged["n"].sum() == ROWS and merged["sum_y"].sum() == pytest.approx(ROWS / 10)
    assert " – " in tail["label"].iloc[0]


def test_merge_bins_gives_an_interior_mass_point_its_own_group() -> None:
    """A 20% spike at 0.37 inside a normal column is a group of its own at ten groups: it splits
    the run of bins around it, which adds an eleventh group."""
    rng = np.random.default_rng(3)
    values = np.concatenate([rng.normal(size=ROWS * 4 // 5), np.full(ROWS // 5, 0.37)])
    merged = merge_bins(_counted_cells(values), 10)
    spike = merged.loc[merged["label"] == "= 0.37"]
    assert len(spike) == 1 and spike["n"].iloc[0] == ROWS // 5
    assert spike["bin_order_first"].iloc[0] == spike["bin_order_last"].iloc[0]
    assert len(merged) == 11 and merged["n"].sum() == ROWS


def test_merge_bins_equal_bins_and_few_bins() -> None:
    """A hundred equal bins give ten equal groups of ten; four bins give four groups, one per bin,
    with the single labels; a repeated `bin_order` and a stray numeric `period` are refused."""
    equal = merge_bins(_cells(np.ones(100)), 10)
    assert list(equal["n"]) == [10] * 10
    assert list(equal["bin_order_first"]) == list(range(0, 100, 10))
    assert equal["label"].iloc[0] == "b0 – b9"
    few = merge_bins(_cells(np.array([5.0, 1.0, 1.0, 50.0])), 10)
    assert list(few["label"]) == ["b0", "b1", "b2", "b3"] and list(few["n"]) == [5, 1, 1, 50]
    twice = pd.concat([_cells(np.ones(3)), _cells(np.ones(3))])
    with pytest.raises(ValueError, match="one row per bin_order"):
        merge_bins(twice, 10)
    with pytest.raises(ValueError, match="period"):
        merge_bins(_cells(np.ones(3)).assign(period=202401), 10)


def test_psi_on_known_shares() -> None:
    """Identical shares give 0, a shift gives the hand-computed value, a zero share is floored,
    and misaligned bins and counts passed as shares are refused."""
    assert psi(np.array([0.2, 0.3, 0.5]), np.array([0.2, 0.3, 0.5])) == 0.0
    shift = 0.1 * np.log(1.2) - 0.1 * np.log(0.8)
    assert psi(np.array([0.5, 0.5]), np.array([0.6, 0.4])) == pytest.approx(shift)
    floored = (0.5 - 1.0) * np.log(0.5) + (0.5 - PSI_FLOOR) * np.log(0.5 / PSI_FLOOR)
    assert psi(np.array([1.0, 0.0]), np.array([0.5, 0.5])) == pytest.approx(floored)
    with pytest.raises(ValueError, match="shape"):
        psi(np.array([1.0, 0.0]), np.array([1.0]))
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        psi(np.array([4.0, 0.0]), np.array([0.5, 0.5]))


def test_new_level_share_counts_unseen_bins_over_all_rows() -> None:
    """A `__new__` bin's rows over the period's rows, null rows in the denominator; a period
    without cells is refused."""
    cells = pd.DataFrame(
        {
            "period": ["p1"] * 4 + ["p0"],
            "bin": ["a", "b", "null", "__new__", "a"],
            "n": [50, 30, 10, 10, 70],
        }
    )
    assert new_level_share(cells, ["a", "b", "null"], "p1") == pytest.approx(0.1)
    assert new_level_share(cells, ["a"], "p0") == 0.0
    with pytest.raises(ValueError, match="p2"):
        new_level_share(cells, ["a"], "p2")


def test_new_level_share_reads_current_cells_only() -> None:
    """The same period's lagged cells are left out, and a period whose cells sum to `n == 0` is
    refused instead of giving NaN."""
    cells = pd.DataFrame(
        {
            "period": ["p1"] * 4,
            "lagged": [False, False, True, True],
            "bin": ["a", "__new__", "a", "__new__"],
            "n": [90, 10, 50, 50],
        }
    )
    assert new_level_share(cells, ["a"], "p1") == pytest.approx(0.1)
    empty = pd.DataFrame({"period": ["p1"], "bin": ["a"], "n": [0]})
    with pytest.raises(ValueError, match="'p1' has no rows"):
        new_level_share(empty, ["a"], "p1")


def test_standardised_difference_known_value_and_constant_sides() -> None:
    """Cohen's d on a textbook pair, NaN dropped; equal constants give 0 (even when their means
    differ by rounding), different constants ±inf; too few values are refused."""
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan])
    b = np.array([3.0, 4.0, 5.0, 6.0, 7.0])
    assert standardised_difference(a, b) == pytest.approx(-2 / np.sqrt(2.5))
    assert standardised_difference(np.array([2.0, 2.0, 2.0]), np.array([2.0, 2.0])) == 0.0
    assert standardised_difference(np.full(3, 0.1), np.full(4, 0.1)) == 0.0
    assert standardised_difference(np.array([2.0, 2.0]), np.array([3.0, 3.0])) == -np.inf
    assert standardised_difference(np.array([3.0, 3.0]), np.array([2.0, 2.0])) == np.inf
    with pytest.raises(ValueError, match="at least two"):
        standardised_difference(np.array([1.0]), b)
