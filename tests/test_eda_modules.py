"""EDA's table modules on cells built in the test from the unit preset (D-135): the ranking's
columns and order, the key features' correlation skip, the levels count, a numeric's deep-dive
groups against the merged cells (the row-to-group mapping agrees with the `Bucketizer`), the
greyed groups, the target per period's pooled row, `pivot_target` with a backticked name, the
correlation overview's left-out key feature, and one regression run with no binary assumption.

The hand-made cases (ties, the skip, the levels, the statistics that cannot exist and a flipped
period, the level labels, a rare level) run on small frames, so each is
visible in the test; the rest reads the skeleton config's real frames, built once.
"""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from sklearn.metrics import roc_auc_score

from core_modelling.artifacts import StageResult
from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import KeyFeatures
from core_modelling.dataset import Frames, build_frames
from core_modelling.dataset.counts import (
    bin_edges,
    count_cells,
    window_clients,
    window_levels,
)
from core_modelling.eda.deep_dives import (
    DEEP_DIVE_GROUPS,
    MIN_BIN_SUPPORT,
    bin_table,
    level_table,
    per_period_concordance,
    quartiles_by_target,
    strata_pivots,
)
from core_modelling.eda.explore import pivot_target
from core_modelling.eda.population import (
    cap_levels,
    funnel_per_period,
    known_rows,
    reference_groups,
    strata_tables,
    target_per_period,
)
from core_modelling.eda.ranking import (
    count_levels,
    encoding_prior_rows,
    feature_statistics,
    rank_features,
    scope_statistics,
    select_key_features,
)
from core_modelling.eda.report import _concordance_row, _correlation_view
from core_modelling.environment import EnvironmentConfig
from core_modelling.ledger import COLUMNS_BY_STAGE
from core_modelling.periods import PERIODS
from core_modelling.statistics.cells import pool_periods
from core_modelling.statistics.distributions import bin_labels, merge_bins, quantile_edges
from core_modelling.statistics.intervals import wilson_interval
from core_modelling.tasks import TASK_SPECS

ENTITY = "entity_a"
MONTH = PERIODS["month"]
FEATURES = ["age", "segment", "income"]  # a numeric, a categorical, a numeric with nulls


def _window(cfg: UseCaseConfig) -> list[date]:
    """The window periods as dates."""
    first, last = cfg.time.observation_window.first, cfg.time.observation_window.last
    return [MONTH.from_index(i) for i in range(MONTH.index(first), MONTH.index(last) + 1)]


def _cells(frames: Frames, cfg: UseCaseConfig, target_edges: np.ndarray | None) -> pd.DataFrame:
    """The counts table (pass 1) of `FEATURES` over every compared period."""
    kinds = {name: frames.meta["kinds"][name] for name in FEATURES}
    edges = bin_edges(frames.snapshot, kinds, cfg.eda.bins)
    categoricals = [name for name, kind in kinds.items() if kind == "categorical"]
    levels, over = window_levels(frames.rows, categoricals, _window(cfg))
    rows = frames.rows.select("unit_id", "period", *FEATURES, "target")
    return count_cells(rows, edges, levels, over, target_edges, _window(cfg), MONTH)


@pytest.fixture(scope="module")
def cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config without a model input."""
    return variant(data={"model_input": None})


@pytest.fixture(scope="module")
def frames(spark: SparkSession, unit_env: EnvironmentConfig, cfg: UseCaseConfig) -> Frames:
    """EDA's frames on the unit preset, built once."""
    return build_frames(cfg, ENTITY, unit_env, spark, "eda")


@pytest.fixture(scope="module")
def cells(frames: Frames, cfg: UseCaseConfig) -> pd.DataFrame:
    """The binary counts table of the three features."""
    return _cells(frames, cfg, None)


@pytest.fixture(scope="module")
def ranking(frames: Frames, cfg: UseCaseConfig, cells: pd.DataFrame) -> pd.DataFrame:
    """The ranked statistics of the three features."""
    return rank_features(_statistics(frames, cfg, cells, exact=False))


def _statistics(
    frames: Frames, cfg: UseCaseConfig, cells: pd.DataFrame, exact: bool
) -> pd.DataFrame:
    """`feature_statistics` of `FEATURES` on the frames' snapshot and window."""
    window = [MONTH.label(p) for p in _window(cfg)]
    kinds = {name: frames.meta["kinds"][name] for name in FEATURES}
    prior_rows = encoding_prior_rows(cells, cfg.task, cfg.strata.min_events, window)
    clients = window_clients(frames.rows, _window(cfg))
    levels = count_levels(frames.snapshot, kinds)
    snapshot = frames.meta["snapshot_period"]
    return feature_statistics(
        cells, kinds, cfg.task, snapshot, window, clients, prior_rows, levels, exact
    )


def test_the_ranking_holds_the_ledger_columns_ranked_by_value(
    frames: Frames, ranking: pd.DataFrame
) -> None:
    """Every EDA ledger column but the key-feature pair, ranked 1… by the ranking value
    descending; each feature's statistics exist on the unit preset; a numeric's snapshot
    concordance is its AUC on the snapshot's rows, direction taken out; a categorical has no
    best order."""
    ledger = [c for c in COLUMNS_BY_STAGE["eda"] if c not in ("key_feature", "represented_by")]
    assert set(ledger) <= set(ranking.columns)
    assert ranking["rank"].tolist() == [1, 2, 3]
    assert ranking["ranking_value"].is_monotonic_decreasing
    assert (ranking["unavailable"] == "").all() and ranking["concordance"].between(0.5, 1).all()
    by_feature = ranking.set_index("feature")
    assert np.isnan(by_feature.loc["segment", "concordance_best_order"])
    assert by_feature.loc["income", "missing_share"] > 0 and by_feature.loc["age", "levels"] > 10
    known = known_rows(frames.snapshot)
    auc = roc_auc_score(known["target"], known["age"])
    assert by_feature.loc["age", "concordance"] == pytest.approx(max(auc, 1 - auc), abs=0.005)


def test_rank_ties_by_name_and_no_value_last() -> None:
    """Equal ranking values order by name; a feature without a concordance ranks last."""
    stats = pd.DataFrame(
        {
            "feature": ["b", "a", "c", "d"],
            "kind": ["numeric", "numeric", "categorical", "numeric"],
            "concordance": [0.6, 0.6, 0.7, np.nan],
            "concordance_best_order": [0.6, 0.6, np.nan, np.nan],
            "concordance_se": [0.01, 0.01, 0.01, np.nan],
        }
    )
    ranked = rank_features(stats)
    assert ranked["feature"].tolist() == ["c", "a", "b", "d"]
    assert ranked["rank"].tolist() == [1, 2, 3, 4]


def test_key_features_skip_by_association_and_list_the_included_first() -> None:
    """`e` is listed first and never skipped, so `a` (0.95 with it) is represented by `e`; `c`
    (|−0.95| with `b`) by `b`; `d`'s pairs are not compared (NaN), which never skips; the walk
    stops at `top_n` = 2 and a feature without a value is never chosen."""
    ranking = pd.DataFrame(
        {
            "feature": list("abcdef"),
            "ranking_value": [0.8, 0.7, 0.65, 0.6, 0.55, np.nan],
            "rank": [1, 2, 3, 4, 5, 6],
        }
    )
    pairs = [("a", "e", 0.95), ("b", "e", 0.2), ("a", "b", 0.1), ("c", "e", np.nan),
             ("c", "b", -0.95), ("d", "e", np.nan), ("d", "b", np.nan)]  # fmt: skip
    association = pd.DataFrame(pairs, columns=["a", "b", "statistic"])
    rule = KeyFeatures(top_n=2, include=["e"], max_correlation=0.9)
    chosen = select_key_features(ranking, association, rule).set_index("feature")
    assert chosen["key_feature"].to_dict() == {
        "a": "", "b": "top_n", "c": "", "d": "top_n", "e": "listed", "f": ""
    }  # fmt: skip
    assert chosen["represented_by"].to_dict() == {
        "a": "e", "b": "", "c": "b", "d": "", "e": "", "f": ""
    }  # fmt: skip


def test_levels_count_distinct_non_null_eligible_values() -> None:
    """A NaN is null, -0.0 is 0.0, an ineligible row's value doesn't count, '' is a level."""
    snapshot = pd.DataFrame(
        {
            "eligible": [1, 1, 1, 1, 1, 0],
            "x": [1.0, np.nan, 1.0, -0.0, 0.0, 7.0],
            "y": ["a", None, "", "a", np.nan, "z"],
        }
    )
    assert count_levels(snapshot, {"x": "numeric", "y": "categorical"}) == {"x": 2, "y": 2}


def _hand_cells(feature: str, rows: list[tuple]) -> pd.DataFrame:
    """One feature's current cells from `(period, bin, target, n, fold)` rows, `bin` None the
    null bin, a binary target."""
    frame = pd.DataFrame(rows, columns=["period", "bin", "target", "n", "fold"])
    return frame.assign(
        feature=feature, lagged=False, is_null=frame["bin"].isna(),
        bin_order=frame["bin"].map({"a": 0, "b": 1}).fillna(2).astype(int),
        target_bin=frame["target"].astype(str), sum_y=frame["target"] * frame["n"],
        sum_y2=frame["target"] * frame["n"],
    ).assign(bin=frame["bin"].fillna("null"))  # fmt: skip


def test_unavailable_statistics_are_decided_up_front_and_a_flip_reads_below_half() -> None:
    """Hand-made cells over two periods: no events among the non-null rows, a single target value
    among them, a categorical whose labelled values sit in one client fold: `unavailable` names
    why, the concordance and its SE are NaN, nothing raises. A falling feature's per-period value
    read with sign −1 is 1 − the signed one; read with +1 it is below 0.5, as a flipped period
    reads, with the same SE (Hanley–McNeil at max(A, 1 − A))."""
    periods = ["2025-07", "2025-08"]
    nulls = [(p, None, t, 20, 1) for p in periods for t in (0, 1)]  # the null rows hold both
    no_events = [(p, b, 0, 30, 0) for p in periods for b in "ab"]
    one_value = [(p, b, 1, 30, 0) for p in periods for b in "ab"]
    one_fold = [(p, b, t, 30, 0) for p in periods for b in "ab" for t in (0, 1)]
    flips = [(p, b, t, 40 if (b == "a") == (t == 1) else 10, f)
             for p in periods for b in "ab" for t in (0, 1) for f in (0, 1)]  # fmt: skip
    kinds = {"no_events": "numeric", "one_value": "numeric", "one_fold": "categorical",
             "flips": "numeric"}  # fmt: skip
    rows = {"no_events": no_events, "one_value": one_value, "one_fold": one_fold, "flips": flips}
    cells = pd.concat([_hand_cells(name, part + nulls) for name, part in rows.items()])
    clients = {"event_rows": 100.0, "event_effective": 100.0, "non_event_rows": 100.0,
               "non_event_effective": 100.0, "rows": 200.0, "effective": 200.0}  # fmt: skip
    levels = dict.fromkeys(kinds, 2)
    stats = feature_statistics(
        cells, kinds, "binary", periods[1], periods, clients, 10.0, levels, False
    ).set_index("feature")
    reasons = {"no_events": "no events among the non-null rows",
               "one_value": "a single target value among the non-null rows",
               "one_fold": "labelled values in fewer than two client folds"}  # fmt: skip
    for name, reason in reasons.items():
        assert stats.loc[name, "unavailable"] == (
            f"not available: {reason} in the snapshot; {reason} in the window"
        )
        assert np.isnan(stats.loc[name, ["concordance", "concordance_se"]].astype(float)).all()
    assert stats.loc["flips", "unavailable"] == "" and stats.loc["flips", "direction"] == "-"
    args = ("numeric", "binary", periods, 10.0, 1)
    down = per_period_concordance(cells, "flips", *args, -1, False)
    up = per_period_concordance(cells, "flips", *args, 1, False)
    current = cells.loc[cells["feature"] == "flips"]
    signed = scope_statistics(current, "numeric", [periods[0]], "binary", periods, 10.0, False,
                              None)["signed"]  # fmt: skip
    assert down["concordance"].iloc[0] == pytest.approx(1 - signed) and signed < 0.5
    assert (down["concordance"] > 0.5).all() and (up["concordance"] < 0.5).all()
    assert down["se"].tolist() == up["se"].tolist()
    # The sign a period is read in is the raw sign of the window's D (here −), 0 without one.
    assert stats.loc["flips", "raw_sign_window"] == -1
    assert (stats.loc[list(reasons), "raw_sign_window"] == 0).all()
    gone = per_period_concordance(cells, "no_events", *args, 0, False)
    assert gone["concordance"].isna().all() and gone["unavailable"].str.startswith("not").all()


def test_cap_levels_name_levels_as_spark_casts_them() -> None:
    """A boolean lower case, an integer column with nulls (floats in pandas) without `.0`, a
    real float as it is; the empty and a blank string quoted (`''`, `' '`, N3) like `'null'`."""
    assert cap_levels(pd.Series([True, False, None, True]), 10).tolist() == [
        "true", "false", "null", "true"
    ]  # fmt: skip
    assert cap_levels(pd.Series([True, False]), 10).tolist() == ["true", "false"]
    assert cap_levels(pd.Series([3, None, 4]), 10).tolist() == ["3", "null", "4"]
    assert cap_levels(pd.Series([1.5, 2.0]), 10).tolist() == ["1.5", "2"]
    text = cap_levels(pd.Series(["", " ", "a", "null", None]), 10)
    assert text.tolist() == ["''", "' '", "a", "'null'", "null"]
    assert cap_levels(pd.Series([np.nan, np.nan]), 10).tolist() == ["null", "null"]


def test_bin_table_groups_match_the_merged_cells(
    frames: Frames, cfg: UseCaseConfig, cells: pd.DataFrame
) -> None:
    """For a numeric with nulls, each group's known-target rows and events equal the snapshot
    cells' labelled `n` and `sum_y` over the group's bins (`merge_bins` on every row, a group
    read as its outer range), so the rows' mapping agrees with the Bucketizer's buckets; the null
    group last; greyed below `MIN_BIN_SUPPORT`; the lift against the base."""
    snapshot_period = frames.meta["snapshot_period"]
    edges = bin_edges(frames.snapshot, {"income": "numeric"}, cfg.eda.bins)["income"]
    base = known_rows(frames.snapshot)["target"].mean()
    table = bin_table(
        cells, frames.snapshot, "income", edges, snapshot_period, cfg.task, base, DEEP_DIVE_GROUPS
    )
    current = cells.loc[(cells["feature"] == "income") & ~cells["lagged"]]
    pooled = pool_periods(current, [snapshot_period])
    values = pooled.loc[~pooled["is_null"]]
    groups = merge_bins(values.groupby("bin_order", as_index=False)["n"].sum(), 10, edges)
    labelled = pooled.loc[pooled["target_bin"].notna()]
    expected = []
    for group in groups.itertuples():
        inside = labelled["bin_order"].between(group.bin_order_first, group.bin_order_last)
        part = labelled.loc[inside & ~labelled["is_null"]]
        expected.append((group.label, part["n"].sum(), part["sum_y"].sum()))
    nulls = labelled.loc[labelled["is_null"]]
    expected.append(("null", nulls["n"].sum(), nulls["sum_y"].sum()))
    actual = list(table[["group", "rows", "support"]].itertuples(index=False, name=None))
    assert actual == expected
    assert table["group"].iloc[0].startswith("<") and table["group"].iloc[-2].startswith(("≥", ">"))
    assert (table["insufficient"] == (table["support"] < MIN_BIN_SUPPORT)).all()
    assert table["lift"].to_numpy() == pytest.approx(table["estimate"].to_numpy() / base)


def test_a_rare_level_is_greyed_not_hidden() -> None:
    """A level table on a hand-made snapshot: the rare level below `MIN_BIN_SUPPORT` events is
    kept and marked insufficient, the common one is not; null is its own level, last."""
    targets = [1] * 30 + [0] * 70 + [1] * 3 + [0] * 7 + [1] * 25 + [0] * 25
    snapshot = pd.DataFrame(
        {
            "eligible": 1,
            "target": targets,
            "x": ["common"] * 100 + ["rare"] * 10 + [None] * 50,
        }
    )
    table = level_table(snapshot, "x", "categorical", None, "binary", 58 / 160)
    assert table["group"].tolist() == ["common", "rare", "null"]
    assert table["support"].tolist() == [30, 3, 25]
    assert table["insufficient"].tolist() == [False, True, False]


def test_target_per_period_pools_the_window(
    frames: Frames, cfg: UseCaseConfig, cells: pd.DataFrame
) -> None:
    """Each window period's rows and rate are the population counts'; the `all` row sums the
    periods, its rate is the pooled one, its support the distinct positive units and its
    interval on effective clients, wider than on the pooled rows."""
    collected = frames.rows.select("unit_id", "period", "target").toPandas()
    window_events = collected.loc[collected["target"] == 1, "unit_id"].nunique()
    population = frames.meta["population"]
    clients = window_clients(frames.rows, _window(cfg))
    table = target_per_period(population, cells, cfg.task, cfg.strata.min_events, clients)
    periods = table.set_index("period")
    labelled = population.loc[population["known_target"].notna()].set_index("period")
    assert list(periods.index) == [*labelled.index, "all"]
    assert periods.loc[labelled.index, "rows"].tolist() == labelled["known_target"].tolist()
    window = periods.loc["all"]
    assert window["rows"] == labelled["known_target"].sum()
    assert window["estimate"] == pytest.approx(labelled["positive_rows"].sum() / window["rows"])
    assert window["support"] == window_events < window["positive_rows"]
    assert (periods["low"] < periods["estimate"]).all()
    rows_low, _ = wilson_interval(window["positive_rows"], window["rows"])
    assert window["low"] < rows_low  # the pooled rows are near copies: fewer effective clients


def test_the_other_tables_build_on_the_unit_preset(
    frames: Frames, cfg: UseCaseConfig, cells: pd.DataFrame
) -> None:
    """Smoke and bookkeeping: the funnel narrows step by step and its `all` row sums the
    periods; every stratum table and pivot covers the known rows once, a feature never crossed
    with itself; the reference group's two
    sides are the tag's 0 rows and the eligible rows; the boxes are ordered; one per-period row
    per window period, a categorical's too."""
    window = [MONTH.label(p) for p in _window(cfg)]
    funnel = funnel_per_period(frames.log, window).set_index("period")
    steps = ["spine", "after_income_known_or_salaried", "tagged_non_holders", "eligible"]
    assert funnel.columns.tolist() == steps and (funnel.diff(axis=1).iloc[:, 1:] <= 0).all().all()
    assert (funnel.loc["all"] == funnel.loc[window].sum()).all()
    snapshot, known = frames.snapshot, known_rows(frames.snapshot)
    strata = strata_tables(snapshot, cfg.strata, cfg.task)
    assert (strata.groupby("variable")["rows"].sum() == len(known)).all()
    edges = bin_edges(snapshot, {"age": "numeric", "income": "numeric"}, cfg.eda.bins)
    pivots = strata_pivots(snapshot, ["age", "segment"], edges, cfg.strata, cfg.task)
    assert (pivots.groupby(["feature", "variable"])["rows"].sum() == len(known)).all()
    others = [variable for variable in cfg.strata.variables if variable != "segment"]
    assert "segment" in cfg.strata.variables  # a key feature that is a stratum: no diagonal
    assert pivots.loc[pivots["feature"] == "segment", "variable"].unique().tolist() == others
    kinds = {"age": "numeric", "segment": "categorical"}
    groups = reference_groups(snapshot, ["non_holders"], ["age", "segment"], kinds, cfg.strata)
    size = groups.loc[groups["section"] == "size"].iloc[0]
    assert size["rows_excluded"] == (snapshot["non_holders"] == 0).sum()
    assert size["rows_eligible"] == (snapshot["eligible"] == 1).sum()
    assert groups.loc[groups["section"] == "feature", "smd"].notna().all()
    boxes = quartiles_by_target(snapshot, "age", cfg.task)
    assert boxes["target_class"].tolist() == ["0", "1"]
    assert ((boxes["q1"] <= boxes["median"]) & (boxes["median"] <= boxes["q3"])).all()
    prior_rows = encoding_prior_rows(cells, cfg.task, cfg.strata.min_events, window)
    for feature, kind in kinds.items():
        args = (cfg.task, window, prior_rows, cfg.strata.min_events, 1, False)
        periods = per_period_concordance(cells, feature, kind, *args)
        assert periods["period"].tolist() == window and periods["se"].notna().all()


def test_pivot_target_with_a_backticked_filter_and_columns(
    frames: Frames, cfg: UseCaseConfig
) -> None:
    """A bank-style column name in `where` (backticks), rows by a numeric cut into quantile
    bins against a stratum's levels: the bins in bin order, the levels by rows with null last,
    each cell's rate the rows' mean target; without `columns`, the lean long form; no rows
    refused."""
    snapshot = frames.snapshot.rename(columns={"segment": "client segment"})
    left_out = snapshot["client segment"].dropna().iloc[0]
    ledger = pd.DataFrame({"feature": ["age"], "kind": ["numeric"]})
    result = StageResult({}, ledger, [], {}, {}, {}, snapshot, cfg)
    styler = pivot_target(result, "age", "onboarding_channel", f"`client segment` != '{left_out}'")
    data = known_rows(snapshot)
    data = data.loc[data["client segment"] != left_out]
    edges = quantile_edges(data["age"].dropna().to_numpy(dtype=float), 10)
    labels = np.array(bin_labels(edges), dtype=object)[np.digitize(data["age"] + 0.0, edges)]
    channel = data["onboarding_channel"].fillna("null").astype(str)
    expected = data.groupby([labels, channel])["target"].mean().unstack()
    by_rows = data["onboarding_channel"].value_counts().sort_index()
    levels = list(by_rows.sort_values(ascending=False, kind="stable").index.astype(str))
    levels += ["null"] if data["onboarding_channel"].isna().any() else []
    bins = [label for label in bin_labels(edges) if label in set(labels)]
    shown = styler.data
    shown.index, shown.columns = shown.index.astype(str), shown.columns.astype(str)
    assert list(shown.index) == bins and list(shown.columns) == levels
    pd.testing.assert_frame_equal(
        shown.astype(float), expected.loc[bins, levels], check_names=False
    )
    assert "greyed below strata.min_events" in styler.caption
    long = pivot_target(result, "onboarding_channel").data
    assert long.columns.tolist() == ["rows", "support", "estimate", "lift"]
    with pytest.raises(ValueError, match="rows names no column"):
        pivot_target(result, [])


def test_the_correlation_overview_leaves_out_a_key_feature_without_a_compared_pair() -> None:
    """Key features a, b, c and d represented by a (e is neither): every pair of c is not
    compared, so the heatmap shows a, b and d only and the subtitle counts c as left out."""
    ranking = pd.DataFrame(
        {"feature": list("abcde"), "key_feature": ["top_n", "top_n", "listed", "", ""],
         "represented_by": ["", "", "", "a", ""]}
    )  # fmt: skip
    pairs = [("a", "b", 0.3), ("a", "c", np.nan), ("b", "c", np.nan), ("a", "d", 0.95),
             ("b", "d", 0.2), ("c", "d", np.nan), ("a", "e", 0.1)]  # fmt: skip
    correlation = pd.DataFrame(pairs, columns=["a", "b", "statistic"]).assign(method="spearman")
    heatmap = _correlation_view(correlation, ranking)[0]
    assert list(heatmap.data[0].x) == ["a", "b", "d"] == list(heatmap.data[0].y)
    assert "3 shown, 1 without a compared pair left out" in heatmap.layout.title.text


def test_a_regression_target_runs_through_the_same_tables(
    spark: SparkSession, unit_env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Card spend summed forward for holders: the statistics exist for every feature (Kendall's
    SE), the bin table's groups carry the mean, its t-interval and the median, and each period's
    mean its t-interval from the cells' sum of squares."""
    cfg = variant(
        task="regression",
        entities={ENTITY: {"sources": {"features": ["retail_mart"], "targets": None}}},
        data={
            "model_input": None,
            "target": {"rule": "forward_sum", "column": "spend_cc_vol"},
            "eligibility": {
                "modelling": [
                    {"name": "holders", "filter": "cc_flag = 1", "reason": "spend needs a card"}
                ]
            },
        },
    )
    frames = build_frames(cfg, ENTITY, unit_env, spark, "eda")
    known = known_rows(frames.snapshot)["target"]
    cells = _cells(frames, cfg, TASK_SPECS["regression"]["target_bins"](known, False))
    stats = _statistics(frames, cfg, cells, exact=False)
    assert (stats["unavailable"] == "").all() and stats["concordance"].between(0.5, 1).all()
    assert stats["concordance_se"].notna().all()
    edges = bin_edges(frames.snapshot, {"age": "numeric"}, cfg.eda.bins)["age"]
    table = bin_table(cells, frames.snapshot, "age", edges, frames.meta["snapshot_period"],
                      "regression", known.mean(), DEEP_DIVE_GROUPS)  # fmt: skip
    assert {"median", "nonzero_share"} <= set(table.columns)
    assert table["rows"].sum() == len(known)
    assert (table["low"] <= table["estimate"]).all() and (table["estimate"] <= table["high"]).all()
    clients = window_clients(frames.rows, _window(cfg))
    periods = target_per_period(frames.meta["population"], cells, "regression", 1, clients)
    assert periods["low"].isna().equals(periods["rows"] < 2)
    known_periods = periods.loc[periods["rows"] >= 2]
    assert (known_periods["low"] < known_periods["estimate"]).all()
    assert (known_periods["estimate"] < known_periods["high"]).all()


def test_a_concordance_row_without_any_period_reads_not_available() -> None:
    """When no window period has a concordance, the row says why instead of an empty chart, beside
    a numeric's boxes by target class when it has them."""
    periods = pd.DataFrame(
        {"feature": "x", "period": ["2025-07", "2025-08"], "rows": 50, "support": 0,
         "concordance": np.nan, "se": np.nan, "insufficient": True,
         "unavailable": "not available: no events among the non-null rows"}
    )  # fmt: skip
    quartiles = pd.DataFrame(
        {"feature": "x", "target_class": ["0", "1"], "rows": 10, "q1": 1.0, "median": 2.0,
         "q3": 3.0, "lower_whisker": 0.5, "upper_whisker": 4.0, "skew": 0.1}
    )  # fmt: skip
    alone = _concordance_row(
        "x", {"per_period": periods, "quartiles": quartiles.iloc[:0]}, "binary"
    )
    assert alone == [
        "<p>Not available: x&#x27;s concordance per period (no events among the non-null rows).</p>"
    ]
    boxes, text = _concordance_row("x", {"per_period": periods, "quartiles": quartiles}, "binary")
    assert len(boxes.data) == 2 and text == alone[0]
