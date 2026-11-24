"""Tests of the effect features' rule and the effects table on constructed EDA groups, no
Spark: a sample row joins the EDA
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
    effect_features,
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
    `levels` when `by_level` (as EDA lists a numeric with few values) or with no `edges`; `f`
    is numeric when it has `edges`."""
    sample = pd.DataFrame({"f": values, "f__contribution": np.arange(len(values), dtype=float)})
    table = _groups("f", groups)
    empty = table.iloc[:0]
    bins, levels = (empty, table) if by_level or edges is None else (table, empty)
    edge_rows = pd.DataFrame({"feature": "f", "position": range(0 if edges is None else len(edges)),
                              "edge": [] if edges is None else edges})  # fmt: skip
    kinds = pd.Series({"f": "categorical" if edges is None else "numeric"})
    return effect_table(sample, bins, levels, edge_rows, kinds, ["f"])


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


def test_a_feature_in_both_of_edas_group_tables_is_refused() -> None:
    """A feature EDA lists in both its bins and its levels has two group tables, so the stage2
    copy is not of one EDA run: refused, naming the feature."""
    sample = pd.DataFrame({"f": ["x"], "f__contribution": [0.1]})
    groups = _groups("f", ["x"])
    no_edges = pd.DataFrame({"feature": [], "position": [], "edge": []})
    with pytest.raises(ValueError, match="f has rows in both EDA's bins and levels"):
        effect_table(sample, groups, groups, no_edges, pd.Series({"f": "categorical"}), ["f"])


def test_a_numeric_without_edges_fails_loud() -> None:
    """The kind comes from the ledger, not from the edges: a numeric the `stage2/` copy holds
    no edges for is refused, never read as a categorical whose every row is a left-out level."""
    sample = pd.DataFrame({"f": [0.5, 2.5], "f__contribution": [0.1, -0.1]})
    no_edges = pd.DataFrame({"feature": [], "position": [], "edge": []})
    with pytest.raises(ValueError, match="the numeric f has no EDA edges"):
        effect_table(sample, _groups("f", ["< 1", "≥ 1"]), _groups("f", [])[:0], no_edges,
                     pd.Series({"f": "numeric"}), ["f"])  # fmt: skip


def test_a_feature_without_a_lift_has_one_row_saying_why() -> None:
    """A feature EDA has no groups for reads `NOT_KEY`, one whose groups have no positive lift
    (EDA's base is 0) `NO_BASE`, each as one row with nothing else filled."""
    sample = pd.DataFrame({"f": ["x", "y"], "f__contribution": [0.1, -0.1],
                           "g": [1.0, 2.0], "g__contribution": [0.2, 0.3]})  # fmt: skip
    flat = _groups("f", ["x", "y"]).assign(lift=0.0)
    no_edges = pd.DataFrame({"feature": [], "position": [], "edge": []})
    kinds = pd.Series({"f": "categorical", "g": "numeric"})
    table = effect_table(sample, flat.iloc[:0], flat, no_edges, kinds, ["f", "g"])
    assert table["feature"].tolist() == ["f", "g"]
    assert table["unavailable"].tolist() == [NO_BASE, NOT_KEY]
    assert table["group"].isna().all()


def _eda_ledger(keys: list[str]) -> pd.DataFrame:
    """A `stage2/` ledger in which `keys` are EDA's key features and one more feature is not."""
    flags = [*["top_n"] * len(keys), None]
    return pd.DataFrame({"feature": [*keys, "other"], "key_feature": flags})


def _run_ledger(shares: list[float]) -> pd.DataFrame:
    """A per-run ledger of features `f00`, `f01`, … with these out-of-fold shares, all used."""
    names = [f"f{i:02d}" for i in range(len(shares))]
    used = pd.array([True] * len(shares), dtype="boolean")
    return pd.DataFrame({"feature": names, "in_model": used, "contribution_share": shares})


def test_the_effect_features_are_twenty_at_most_with_every_used_key_feature() -> None:
    """The ten largest plus every key feature the model uses; a key feature the model does not
    use stays out; key features beyond twenty keep the twenty largest of them."""
    ledger = _run_ledger(list(np.linspace(1, 0.01, 30)))
    ledger.loc[ledger["feature"] == "f29", "in_model"] = False
    keys = ["f25", "f12", "f29", "absent"]
    chosen = effect_features(ledger, _eda_ledger(keys))
    assert chosen == [*[f"f{i:02d}" for i in range(10)], "f12", "f25"]
    many = [f"f{i:02d}" for i in range(5, 29)]
    chosen = effect_features(ledger, _eda_ledger(many))
    assert len(chosen) == 20 and chosen == many[:20]
