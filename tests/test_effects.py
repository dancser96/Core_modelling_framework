"""Tests of the effects table on constructed EDA groups, no Spark: a sample row joins the EDA
group its value falls in (singletons, a by-level numeric, a value below the first group or
between two groups, a null with and without EDA's null group), a feature without a lift gets
one row saying why, and a group table that does not fit EDA's edges fails loud."""

import numpy as np
import pandas as pd
import pytest

from core_modelling.evaluation.effects import (
    EFFECT_COLUMNS,
    NO_BASE,
    NOT_KEY,
    _bucket_groups,
    effect_table,
)
from core_modelling.statistics.distributions import bin_labels, quantile_edges, range_label

EDGES = np.array([1.0, 2.0, 3.0])  # buckets: < 1, [1, 2), [2, 3), ≥ 3


def _groups(feature: str, groups: list[str]) -> pd.DataFrame:
    """An EDA group table for `feature` with a lift over a base of 0.1."""
    estimate = np.linspace(0.05, 0.2, len(groups))
    return pd.DataFrame({"feature": feature, "group": groups, "rows": 100, "support": 30.0,
                         "estimate": estimate, "low": estimate * 0.8, "high": estimate * 1.2,
                         "lift": estimate / 0.1, "insufficient": False})  # fmt: skip


def _effects(values: list, groups: list[str], edges: np.ndarray | None, by_level: bool = False
             ) -> pd.DataFrame:  # fmt: skip
    """The effects table of one feature `f` with `values` against EDA's `groups`, listed in
    `levels` when `by_level` (as EDA lists a numeric with few values) or with no `edges`."""
    sample = pd.DataFrame({"f": values, "f__contribution": np.arange(len(values), dtype=float)})
    table = _groups("f", groups)
    empty = table.iloc[:0]
    bins, levels = (empty, table) if by_level or edges is None else (table, empty)
    edge_rows = pd.DataFrame({"feature": "f", "position": range(0 if edges is None else len(edges)),
                              "edge": [] if edges is None else edges})  # fmt: skip
    return effect_table(sample, bins, levels, edge_rows, ["f"])


def test_singleton_groups_hold_their_value_only() -> None:
    """A mass point at 0 is its own group `= 0`; a value just above it joins `(0, 2)`."""
    edges = np.array([0.0, np.nextafter(0.0, 1.0), 2.0])
    assert bin_labels(edges)[1:] == ["= 0", "(0, 2)", "≥ 2"]
    groups = _bucket_groups(pd.Series([0.0, 1e-9, 2.5], name="f"), ["= 0", "(0, 2)", "≥ 2"], edges)
    assert groups.tolist() == ["= 0", "(0, 2)", "≥ 2"]


def test_a_numeric_listed_by_level_joins_by_bucket() -> None:
    """A numeric EDA lists by value (`0.333333`, in `levels`) is matched on its edges, not as
    text, so 1/3 and 2/3 keep their groups."""
    values = [1 / 3, 2 / 3, 1 / 3]
    edges = quantile_edges(np.array(values), 10)
    labels = [label.removeprefix("= ") for label in bin_labels(edges) if label.startswith("= ")]
    assert labels == ["0.333333", "0.666667"]
    table = _effects(values, labels, edges, by_level=True)
    assert table["kind"].unique().tolist() == ["numeric"]
    assert table["sample_rows"].tolist() == [2, 1]
    assert table[["left_out_null", "left_out_level"]].to_numpy().sum() == 0


def test_values_below_and_between_groups_join_the_group_below() -> None:
    """A value in a bucket below the first group joins the first; one in a bucket between two
    groups (empty at EDA's snapshot) joins the group below it."""
    below = _bucket_groups(pd.Series([0.5], name="f"), ["[1, 2)", "≥ 2"], EDGES)
    assert below.tolist() == ["[1, 2)"]
    between = _bucket_groups(pd.Series([1.5, 2.5], name="f"), ["< 1", "[2, 3)"], EDGES)
    assert between.tolist() == ["< 1", "[2, 3)"]


def test_a_null_joins_eda_null_group_or_is_counted_out() -> None:
    """A null joins EDA's `null` group when there is one, else it is left out and counted."""
    numeric = [range_label(EDGES, 0, 1), range_label(EDGES, 2, 3)]
    with_null = _effects([0.5, np.nan, 2.5], [*numeric, "null"], EDGES)
    assert list(with_null.columns) == EFFECT_COLUMNS
    assert with_null["unavailable"].eq("").all()
    assert with_null["sample_rows"].tolist() == [1, 1, 1]
    assert with_null["left_out_null"].iloc[0] == 0
    without = _effects([0.5, np.nan, 2.5], numeric, EDGES)
    assert without["sample_rows"].tolist() == [1, 1]
    assert without["left_out_null"].iloc[0] == 1
    levels = _effects(["x", "q", None], ["x", "y"], None)
    assert levels["kind"].iloc[0] == "categorical"
    assert levels[["left_out_null", "left_out_level"]].iloc[0].tolist() == [1, 1]


def test_groups_that_do_not_fit_the_edges_fail_loud() -> None:
    """A label opening at no bucket, and groups out of bucket order, are refused."""
    values = pd.Series([0.5], name="f")
    with pytest.raises(ValueError, match="open at no bucket"):
        _bucket_groups(values, ["< 1", "[1.5, 3)"], EDGES)
    with pytest.raises(ValueError, match="not in bucket order"):
        _bucket_groups(values, ["[2, 3)", "[1, 2)"], EDGES)


def test_a_feature_without_a_lift_has_one_row_saying_why() -> None:
    """A feature EDA has no groups for reads `NOT_KEY`, one whose groups have no positive lift
    (EDA's base is 0) `NO_BASE`, each as one row with nothing else filled."""
    sample = pd.DataFrame({"f": ["x", "y"], "f__contribution": [0.1, -0.1],
                           "g": [1.0, 2.0], "g__contribution": [0.2, 0.3]})  # fmt: skip
    flat = _groups("f", ["x", "y"]).assign(lift=0.0)
    no_edges = pd.DataFrame({"feature": [], "position": [], "edge": []})
    table = effect_table(sample, flat.iloc[:0], flat, no_edges, ["f", "g"])
    assert table["feature"].tolist() == ["f", "g"]
    assert table["unavailable"].tolist() == [NO_BASE, NOT_KEY]
    assert table["group"].isna().all()
