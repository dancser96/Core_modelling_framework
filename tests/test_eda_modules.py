"""EDA's table modules on cells built in the test from the unit preset (D-135): the ranking's
columns and order, the key features' correlation skip, the levels count, a numeric's deep-dive
groups against the merged cells (the row-to-group mapping agrees with the `Bucketizer`), the
greyed groups, the target per period's pooled row, `pivot_target` with a backticked name, the
correlation overview's left-out key feature, and one regression run with no binary assumption.

The hand-made cases (ties, the skip, the levels, the statistics that cannot exist and a flipped
period, the level labels, a rare level) run on small frames, so each is
visible in the test; the rest reads the skeleton config's real frames (`conftest.py`'s, built
once for the session).
"""

from collections.abc import Callable
from datetime import date
from html import unescape

import numpy as np
import pandas as pd
import pytest
from conftest import REGRESSION
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
    concordance_per_period,
    group_table,
    numeric_groups,
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
    sources_per_period,
    strata_tables,
    target_per_period,
)
from core_modelling.eda.profile import PROFILE_COLUMNS, QUANTILES, value_profile
from core_modelling.eda.ranking import (
    count_levels,
    feature_statistics,
    rank_features,
    select_key_features,
)
from core_modelling.eda.report import (
    _concordance_row,
    _correlation_view,
    _per_period_view,
    _profile_views,
    _slices_views,
)
from core_modelling.eda.slices import (
    CURVE_COLUMNS,
    NO_BASE,
    SIGNED,
    SLICE_COLUMNS,
    SLICE_GRID,
    ordered_categorical_bins,
    ordered_numeric_bins,
    skipped_slices,
    slice_shares,
    slice_tables,
)
from core_modelling.environment import EnvironmentConfig
from core_modelling.ledger import COLUMNS_BY_STAGE
from core_modelling.periods import PERIODS
from core_modelling.reporting.formats import plain_number
from core_modelling.reporting.theme import THEME
from core_modelling.statistics.capture import capture_curve, capture_table
from core_modelling.statistics.cells import pool_periods
from core_modelling.statistics.distributions import bin_labels, merge_bins, quantile_edges
from core_modelling.statistics.intervals import wilson_interval
from core_modelling.statistics.scope import encoding_prior_rows, scope_statistics
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
def cells(eda_frames: Frames, in_memory: UseCaseConfig) -> pd.DataFrame:
    """The binary counts table of the three features."""
    return _cells(eda_frames, in_memory, None)


@pytest.fixture(scope="module")
def ranking(eda_frames: Frames, in_memory: UseCaseConfig, cells: pd.DataFrame) -> pd.DataFrame:
    """The ranked statistics of the three features."""
    return rank_features(_statistics(eda_frames, in_memory, cells, exact=False))


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
    eda_frames: Frames, ranking: pd.DataFrame
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
    known = known_rows(eda_frames.snapshot)
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
    """One feature's current cells from `(period, bin, target, n, fold)` rows, `bin` "a" to "e"
    in order or None the null bin (the last order), a binary target."""
    frame = pd.DataFrame(rows, columns=["period", "bin", "target", "n", "fold"])
    orders = {letter: order for order, letter in enumerate("abcde")}
    return frame.assign(
        feature=feature, lagged=False, is_null=frame["bin"].isna(),
        bin_order=frame["bin"].map(orders).fillna(len(orders)).astype(int),
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
    # The sign a period is read in is the raw sign of the window's D (here −), 0 without one;
    # the snapshot's raw sign (a one-feature list's direction) likewise.
    signs = ["raw_sign", "raw_sign_window"]
    assert (stats.loc["flips", signs] == -1).all()
    assert (stats.loc[list(reasons), signs] == 0).all().all()
    gone = per_period_concordance(cells, "no_events", *args, 0, False)
    assert gone["concordance"].isna().all() and gone["unavailable"].str.startswith("not").all()


PERIODS_TWO = ["2025-07", "2025-08"]
CLIENTS = {"event_rows": 100.0, "event_effective": 100.0, "non_event_rows": 100.0,
           "non_event_effective": 100.0, "rows": 200.0, "effective": 200.0}  # fmt: skip


def _u_shaped_rows(events_in_a: int) -> list[tuple]:
    """Two periods of bins "a" to "e" in two client folds, the outer bins mostly events and the
    inner ones mostly not (a U: the plain order cancels out); "a" holds `events_in_a` events."""
    rates = {"a": events_in_a, "b": 10, "c": 10, "d": 10, "e": 40}
    return [(p, b, t, rates[b] if t == 1 else 50 - rates[b], f)
            for p in PERIODS_TWO for b in "abcde" for t in (0, 1) for f in (0, 1)]  # fmt: skip


def test_a_u_shaped_numeric_reaches_its_window_value_only_in_best_order() -> None:
    """A U-shaped numeric reads about 0.5 on the window in its plain order and well above in
    best order, as on the snapshot; a categorical on the same cells has no best order."""
    cells = pd.concat([_hand_cells(name, _u_shaped_rows(40)) for name in ("u_numeric", "u_code")])
    kinds = {"u_numeric": "numeric", "u_code": "categorical"}
    stats = feature_statistics(
        cells, kinds, "binary", PERIODS_TWO[1], PERIODS_TWO, CLIENTS, 10.0, dict.fromkeys(kinds, 5),
        False,
    ).set_index("feature")  # fmt: skip
    numeric = stats.loc["u_numeric"]
    assert numeric["concordance_window"] == pytest.approx(0.5, abs=0.01)
    assert numeric["concordance_best_order_window"] > numeric["concordance_window"] + 0.2
    assert numeric["concordance_best_order_window"] == pytest.approx(
        numeric["concordance_best_order"], abs=0.01
    )
    assert stats.loc["u_code", "concordance_window"] > 0.7
    assert np.isnan(stats.loc["u_code", "concordance_best_order_window"])


def test_concordance_per_period_reads_every_ranked_feature_in_its_window_direction(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """Every ranked feature's `per_period_concordance` in rank order, each in its
    `raw_sign_window`; the view pivots it feature × period in that order, greyed where
    insufficient, its caption naming the direction and `strata.min_events`."""
    cells = pd.concat([_hand_cells("rising", _u_shaped_rows(10)),
                       _hand_cells("u_code", _u_shaped_rows(40))])  # fmt: skip
    ranking = pd.DataFrame({"feature": ["u_code", "rising"], "kind": ["categorical", "numeric"],
                            "raw_sign_window": [1, 1]})  # fmt: skip
    table = concordance_per_period(cells, ranking, "binary", PERIODS_TWO, 10.0, 200, False)
    assert table.columns.tolist() == ["feature", "period", "rows", "support", "concordance", "se",
                                      "insufficient", "unavailable"]  # fmt: skip
    assert table["feature"].tolist() == ["u_code", "u_code", "rising", "rising"]
    alone = per_period_concordance(cells, "rising", "numeric", "binary", PERIODS_TWO, 10.0, 200,
                                   1, False)  # fmt: skip
    pd.testing.assert_frame_equal(table.iloc[2:].reset_index(drop=True), alone)
    assert (table["concordance"] > 0.5).all()
    assert table["insufficient"].tolist() == [False, False, True, True]  # 220 and 160 events
    view = _per_period_view(table, PERIODS_TWO, variant(strata={"min_events": 200}))
    assert view.data.index.tolist() == ["u_code", "rising"]
    assert view.data.columns.tolist() == PERIODS_TWO
    assert "a flip reads below 0.5" in view.caption
    assert "min_events = 200 positive events" in view.caption
    assert THEME["insufficient"] in view.to_html()


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


def test_group_table_groups_match_the_merged_cells(
    eda_frames: Frames, in_memory: UseCaseConfig, cells: pd.DataFrame
) -> None:
    """For a numeric with nulls, each group's known-target rows and events equal the snapshot
    cells' labelled `n` and `sum_y` over the group's bins (`merge_bins` on every row, a group
    read as its outer range), so the rows' mapping agrees with the Bucketizer's buckets; the null
    group last; greyed below `MIN_BIN_SUPPORT`; the lift against the base."""
    snapshot_period = eda_frames.meta["snapshot_period"]
    edges = bin_edges(eda_frames.snapshot, {"income": "numeric"}, in_memory.eda.bins)["income"]
    base = known_rows(eda_frames.snapshot)["target"].mean()
    table = group_table(
        eda_frames.snapshot, "income", "numeric", edges, in_memory.task, base, DEEP_DIVE_GROUPS
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
    table = group_table(snapshot, "x", "categorical", None, "binary", 58 / 160, None)
    assert table["group"].tolist() == ["common", "rare", "null"]
    assert table["support"].tolist() == [30, 3, 25]
    assert table["insufficient"].tolist() == [False, True, False]


def test_target_per_period_pools_the_window(
    eda_frames: Frames, in_memory: UseCaseConfig, cells: pd.DataFrame
) -> None:
    """Each window period's rows and rate are the population counts'; the `all` row sums the
    periods, its rate is the pooled one, its support the distinct positive units and its
    interval on effective clients, wider than on the pooled rows."""
    collected = eda_frames.rows.select("unit_id", "period", "target").toPandas()
    window_events = collected.loc[collected["target"] == 1, "unit_id"].nunique()
    population = eda_frames.meta["population"]
    clients = window_clients(eda_frames.rows, _window(in_memory))
    table = target_per_period(
        population, cells, in_memory.task, in_memory.strata.min_events, clients
    )
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
    eda_frames: Frames, in_memory: UseCaseConfig, cells: pd.DataFrame
) -> None:
    """Smoke and bookkeeping: the funnel narrows step by step and its `all` row sums the
    periods; every stratum table and pivot covers the known rows once, a feature never crossed
    with itself; the reference group's two
    sides are the tag's 0 rows and the eligible rows; the boxes are ordered; one per-period row
    per window period, a categorical's too."""
    window = [MONTH.label(p) for p in _window(in_memory)]
    funnel = funnel_per_period(eda_frames.log, window).set_index("period")
    steps = ["spine", "after_income_known_or_salaried", "tagged_non_holders", "eligible"]
    assert funnel.columns.tolist() == steps and (funnel.diff(axis=1).iloc[:, 1:] <= 0).all().all()
    assert (funnel.loc["all"] == funnel.loc[window].sum()).all()
    snapshot, known = eda_frames.snapshot, known_rows(eda_frames.snapshot)
    strata = strata_tables(snapshot, in_memory.strata, in_memory.task)
    assert (strata.groupby("variable")["rows"].sum() == len(known)).all()
    edges = bin_edges(snapshot, {"age": "numeric", "income": "numeric"}, in_memory.eda.bins)
    pivots = strata_pivots(snapshot, ["age", "segment"], edges, in_memory.strata, in_memory.task)
    assert (pivots.groupby(["feature", "variable"])["rows"].sum() == len(known)).all()
    others = [variable for variable in in_memory.strata.variables if variable != "segment"]
    assert "segment" in in_memory.strata.variables  # a key feature that is a stratum: no diagonal
    assert pivots.loc[pivots["feature"] == "segment", "variable"].unique().tolist() == others
    kinds = {"age": "numeric", "segment": "categorical"}
    groups = reference_groups(
        snapshot, ["non_holders"], ["age", "segment"], kinds, in_memory.strata
    )
    size = groups.loc[groups["section"] == "size"].iloc[0]
    assert size["rows_excluded"] == (snapshot["non_holders"] == 0).sum()
    assert size["rows_eligible"] == (snapshot["eligible"] == 1).sum()
    assert groups.loc[groups["section"] == "feature", "smd"].notna().all()
    boxes = quartiles_by_target(snapshot, "age", in_memory.task)
    assert boxes["target_class"].tolist() == ["0", "1"]
    assert ((boxes["q1"] <= boxes["median"]) & (boxes["median"] <= boxes["q3"])).all()
    prior_rows = encoding_prior_rows(cells, in_memory.task, in_memory.strata.min_events, window)
    for feature, kind in kinds.items():
        args = (in_memory.task, window, prior_rows, in_memory.strata.min_events, 1, False)
        periods = per_period_concordance(cells, feature, kind, *args)
        assert periods["period"].tolist() == window and periods["se"].notna().all()


def test_pivot_target_with_a_backticked_filter_and_columns(
    eda_frames: Frames, in_memory: UseCaseConfig
) -> None:
    """A bank-style column name in `where` (backticks), rows by a numeric cut into quantile
    bins against a stratum's levels: the bins in bin order, the levels by rows with null last,
    each cell's rate the rows' mean target; without `columns`, the lean long form; no rows
    refused."""
    snapshot = eda_frames.snapshot.rename(columns={"segment": "client segment"})
    left_out = snapshot["client segment"].dropna().iloc[0]
    ledger = pd.DataFrame({"feature": ["age"], "kind": ["numeric"]})
    result = StageResult({}, ledger, [], {}, {}, {}, snapshot, in_memory)
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


def test_the_correlation_overview_shows_the_key_features_and_whom_they_represent() -> None:
    """Key features a, b and c, d represented by a (e is neither): every pair of c is not
    compared, so the heatmap shows a and b only and the subtitle counts c as left out; beneath
    it d with a and their association; a rule that skipped nothing says so."""
    ranking = pd.DataFrame(
        {"feature": list("abcde"), "key_feature": ["top_n", "top_n", "listed", "", ""],
         "represented_by": ["", "", "", "a", ""]}
    )  # fmt: skip
    pairs = [("a", "b", 0.3), ("a", "c", np.nan), ("b", "c", np.nan), ("a", "d", 0.95),
             ("b", "d", 0.2), ("c", "d", np.nan), ("a", "e", 0.1)]  # fmt: skip
    correlation = pd.DataFrame(pairs, columns=["a", "b", "statistic"]).assign(method="spearman")
    heatmap, represented = _correlation_view(correlation, ranking, 0.9, "binary")
    assert list(heatmap.data[0].x) == ["a", "b"] == list(heatmap.data[0].y)
    assert "2 shown, 1 without a compared pair left out" in heatmap.layout.title.text
    assert represented.data.to_dict("records") == [
        {"candidate": "d", "represented_by": "a", "association": 0.95, "method": "spearman"}
    ]
    alone = ranking.assign(represented_by="")
    assert "represent no candidate" in _correlation_view(correlation, alone, 0.9, "binary")[1]
    assert _correlation_view(correlation, alone.iloc[2:], 0.9, "binary")[0].startswith(
        "<p>Not available"
    )


def test_a_by_level_numeric_reads_values_and_a_mass_point_among_ranges_keeps_its_sign() -> None:
    """Every group one value: labelled `0`, `1`, `2` (null last), not `= 0`; merged into ranges,
    a mass point among them keeps `= 0`."""
    few = pd.Series([0, 1, 2, 1, np.nan, 0], dtype=float, name="few")
    edges = quantile_edges(few.dropna().to_numpy(), 10)
    assert list(numeric_groups(few, edges, None).cat.categories) == ["0", "1", "2", "null"]
    wide = pd.Series(np.r_[np.zeros(50), np.arange(1.0, 51.0)], name="wide")
    merged = numeric_groups(wide, quantile_edges(wide.to_numpy(), 10), 3).cat.categories
    assert merged[0] == "= 0" and merged[1].startswith("(0, ") and len(merged) == 3


def test_a_regression_target_runs_through_the_same_tables(
    spark: SparkSession, unit_env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Card spend summed forward for holders: the statistics exist for every feature (Kendall's
    SE), the bin table's groups carry the mean, its t-interval and the median, and each period's
    mean its t-interval from the cells' sum of squares."""
    cfg = variant(**REGRESSION)
    frames = build_frames(cfg, ENTITY, unit_env, spark, "eda")
    known = known_rows(frames.snapshot)["target"]
    cells = _cells(frames, cfg, TASK_SPECS["regression"]["target_bins"](known, False))
    stats = _statistics(frames, cfg, cells, exact=False)
    assert (stats["unavailable"] == "").all() and stats["concordance"].between(0.5, 1).all()
    assert stats["concordance_se"].notna().all()
    edges = bin_edges(frames.snapshot, {"age": "numeric"}, cfg.eda.bins)["age"]
    table = group_table(frames.snapshot, "age", "numeric", edges, "regression", known.mean(),
                        DEEP_DIVE_GROUPS)  # fmt: skip
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


def test_sources_per_period_shares_are_the_join_entries(eda_frames: Frames) -> None:
    """Over the compared periods, each joined feature source's share is its entry's matched rows
    over the spine's, `all` pooled, the target source left out; the spine alone leaves `rows`."""
    compared = next(entry for entry in eda_frames.log if entry["step"] == "compared_periods")
    periods = [*compared["window"], *compared["gap"], *compared["latest"]]
    spine, extract, targets = [entry for entry in eda_frames.log if entry["step"] == "join"]
    table = sources_per_period(eda_frames.log, periods).set_index("period")
    assert table.columns.tolist() == ["rows", extract["source"]] and targets["role"] == "targets"
    assert table.index.tolist() == [*periods, "all"]
    rows = pd.Series(spine["rows"])[periods]
    shares = pd.Series(extract["matched"])[periods] / rows
    np.testing.assert_allclose(table.loc[periods, extract["source"]], shares)
    assert table.loc["all", "rows"] == rows.sum()
    pooled = sum(extract["matched"][p] for p in periods) / rows.sum()
    assert table.loc["all", extract["source"]] == pytest.approx(pooled)
    alone = sources_per_period([spine, targets], periods)
    assert alone.columns.tolist() == ["period", "rows"]


def _slice_cells(feature: str, rows: list[tuple]) -> pd.DataFrame:
    """One feature's current cells from `(period, bin_order, target, n)` rows, a categorical's
    with its client `fold` fifth; bin order −1 the null bin and `v<order>` the others; each
    target value its own target bin."""
    columns = ["period", "bin_order", "target", "n", "fold"][: len(rows[0])]
    frame = pd.DataFrame(rows, columns=columns)
    is_null = frame["bin_order"] < 0
    return frame.assign(
        feature=feature, lagged=False, is_null=is_null,
        bin=np.where(is_null, "null", "v" + frame["bin_order"].astype(str)),
        target_bin=frame["target"].astype(str), sum_y=frame["target"] * frame["n"],
        sum_y2=frame["target"] ** 2 * frame["n"],
    ).drop(columns="target")  # fmt: skip


def _slice_ranking(features: list[str], kinds: list[str], raw_signs: list[int]) -> pd.DataFrame:
    """A ranking of key features in the given order with the columns `slice_tables` reads."""
    unavailable = ["" if sign else "not available: no events in the snapshot" for sign in raw_signs]
    return pd.DataFrame({"feature": features, "kind": kinds, "rank": range(1, len(features) + 1),
                         "key_feature": "top_n", "raw_sign": raw_signs,
                         "unavailable": unavailable})  # fmt: skip


def test_a_feature_with_every_positive_in_its_top_bins_captures_share_over_base() -> None:
    """Ten bins of 100 rows, the top two all positive, and a negative null bin (base 200 /
    1,100): the capture is min(1, share / base) at each share, linear inside the boundary bin,
    and 1 at 100%; read with sign −1 the order reverses, the null bin last both ways."""
    period = "2025-08"
    rows = [(period, b, int(b >= 8), 100) for b in range(10)] + [(period, -1, 0, 100)]
    cells, base = _slice_cells("x", rows), 200 / 1_100
    ordered = ordered_numeric_bins(cells, 1, period)
    assert ordered["bin"].tolist() == [f"v{b}" for b in range(9, -1, -1)] + ["null"]
    shares = {"top 5%": 0.05, "top 10%": 0.1, "half": 0.5, "all": 1.0}
    table = capture_table(ordered, shares, base, "binary", "")
    expected = np.minimum(1, np.array(list(shares.values())) / base)
    np.testing.assert_allclose(table["capture"], expected)
    np.testing.assert_allclose(table["lift"], table["estimate"] / base)
    assert table["estimate"].iloc[0] == 1.0 and (table["unavailable"] == "").all()
    reverse = ordered_numeric_bins(cells, -1, period)
    assert reverse["bin"].tolist() == [f"v{b}" for b in range(10)] + ["null"]
    halves = capture_table(reverse, {"half": 0.5, "all": 1.0}, base, "binary", "")
    assert halves["capture"].tolist() == [0.0, 1.0]


def test_an_independent_feature_captures_its_share_along_the_curve() -> None:
    """Twenty bins with the same 5% rate: the capture curve stays within noise (±0.03, about
    four standard errors at 5,000 positives) of the diagonal and ends at 1."""
    rng = np.random.default_rng(3)
    positives = rng.binomial(5_000, 0.05, 20)
    rows = [("p", b, 1, int(k)) for b, k in enumerate(positives)]
    rows += [("p", b, 0, 5_000 - int(k)) for b, k in enumerate(positives)]
    curve = capture_curve(ordered_numeric_bins(_slice_cells("x", rows), 1, "p"), SLICE_GRID)
    assert np.abs(curve["capture"] - curve["share"]).max() < 0.03
    assert curve["capture"].iloc[-1] == pytest.approx(1.0)


def _null_code_rows(rng: np.random.Generator, clients: int, periods: list[str]) -> list[tuple]:
    """`_slice_cells` rows, with folds, of a 50-level code without signal, constant per client,
    on a panel: a label is any event in the next three periods at the client's own hazard
    (lognormal frailty, a rate near 3%), so a client keeps its label across periods."""
    level, fold = rng.integers(0, 50, clients), rng.integers(0, 5, clients)
    frailty = rng.lognormal(0, 1, clients)
    events = rng.random((clients, len(periods) + 3)) < 0.01 * frailty[:, None] / frailty.mean()
    labels = [events[:, t + 1 : t + 4].any(axis=1) for t in range(len(periods))]
    frame = pd.DataFrame({"period": np.repeat(periods, clients),
                          "bin_order": np.tile(level, len(periods)),
                          "target": np.concatenate(labels).astype(int),
                          "fold": np.tile(fold, len(periods))})  # fmt: skip
    keys = ["period", "bin_order", "target"]
    counts = frame.groupby([*keys, "fold"]).size().rename("n").reset_index()
    return list(counts[[*keys, "n", "fold"]].itertuples(index=False, name=None))


def test_a_null_categorical_on_a_panel_captures_its_share() -> None:
    """A null client-constant code on a panel whose clients keep their labels across the
    overlapping target windows: ordered per client fold by the other folds' encoding, its list
    captures its share (the mean of 20 seeded panels of 2,000 clients, within 0.025, about 3
    standard errors; ordered by the other periods' raw rates it read about 0.08 and 0.15)."""
    rng = np.random.default_rng(7)
    periods = [f"2025-{month:02d}" for month in range(1, 7)]
    shares = {"top 5%": 0.05, "top 10%": 0.1}
    captured = []
    for _ in range(20):
        cells = _slice_cells("c", _null_code_rows(rng, 2_000, periods))
        prior_rows = encoding_prior_rows(cells, "binary", 50, periods)
        ordered = ordered_categorical_bins(cells, periods[-1], periods, prior_rows)
        captured.append(capture_table(ordered, shares, 0.03, "binary", "")["capture"])
    np.testing.assert_allclose(np.mean(captured, axis=0), [0.05, 0.1], atol=0.025)


def test_slice_tables_order_categoricals_by_client_fold_and_take_the_decision_once(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A categorical's levels are ordered per client fold by the other folds' encoding, not
    its own (a level unseen there at their base, the null bin last), so a one-period window
    has a list; each fold is cut at the share and the counts summed. `decision.n` comes first
    once (its listed twin left out), a count above the labelled rows is skipped and named, a
    feature without a snapshot concordance reads the ranking's reason; the curve ends with the
    diagonal."""
    p = "2025-08"
    level = [(p, 0, 1, 10, 0), (p, 0, 0, 90, 0), (p, 1, 1, 50, 0), (p, 1, 0, 50, 0),
             (p, 0, 1, 50, 1), (p, 0, 0, 50, 1), (p, 1, 1, 10, 1), (p, 1, 0, 90, 1),
             (p, 2, 1, 5, 1), (p, 2, 0, 5, 1), (p, -1, 0, 40, 1)]  # fmt: skip
    numeric = _slice_cells("x", [(p, 0, 0, 325), (p, 1, 1, 125)])
    cells = pd.concat([_slice_cells("c", level), numeric])
    prior_rows = encoding_prior_rows(cells, "binary", 50, [p])  # the run's, as `run_eda` hands it
    order = ordered_categorical_bins(cells.loc[cells["feature"] == "c"], p, [p], prior_rows)
    by_fold = order.groupby("fold")["bin"].agg(list).to_dict()
    assert by_fold == {0: ["v0", "v1"], 1: ["v1", "v2", "v0", "null"]}
    ranking = _slice_ranking(["x", "c", "z"], ["numeric", "categorical", "numeric"], [1, 1, 0])
    resolved = variant(decision={"type": "top_n", "n": 45},
                       evaluation={"slices": {"top_pct": [0.1], "top_n": [45, 5_000]}})  # fmt: skip
    meta = {"snapshot_period": p, "snapshot_base": 125 / 450,
            "slices": slice_shares(resolved, 450)}  # fmt: skip
    slices, curve = slice_tables(cells, ranking, meta, resolved, [p], prior_rows)
    assert slices.columns.tolist() == SLICE_COLUMNS and curve.columns.tolist() == CURVE_COLUMNS
    assert slices["slice"].iloc[:2].tolist() == ["decision n = 45", "top 10%"]
    assert slices["feature"].tolist() == ["x", "x", "c", "c", "z"]
    assert slices["unavailable"].tolist() == ["", "", "", "", ranking["unavailable"].iloc[2]]
    # c: fold 0 cut at 20 of 200 rows inside v0 (2 positives), fold 1 at 25 of 250 inside v1 (2.5)
    np.testing.assert_allclose(slices["capture"], [0.36, 0.36, 4.5 / 125, 4.5 / 125, np.nan])
    assert curve["feature"].unique().tolist() == ["x", "c", "random"]
    random = curve.loc[curve["feature"] == "random"]
    np.testing.assert_allclose(random["capture"], random["share"])
    probability = variant(evaluation={"slices": {"top_pct": [0.1], "top_n": [45, 5_000]}})
    assert slice_shares(probability, 450) == {"top 10%": 0.1, "n = 45": 0.1}
    assert slice_shares(resolved, 20) == {"top 10%": 0.1}
    assert skipped_slices(resolved, 20) == ["decision n = 45", "n = 5,000"]


def test_a_regression_capture_needs_a_target_never_negative(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """Decided up front: an amount that is never negative captures all of it at 100%; one that
    can be negative has no capture or curve (+3,000 and −2,000 would read 3.0 at 50%), its lift
    kept; one whose mean is not positive has neither capture nor lift. The estimate stays."""
    p = "2025-08"
    resolved = variant(task="regression",
                       evaluation={"slices": {"top_pct": [0.5, 1.0], "top_n": []}})  # fmt: skip
    nan = [np.nan, np.nan]
    cases = {"": ((0.0, 10.0), 5.0, [1.0, 1.0], [2.0, 1.0], [10.0, 5.0]),
             SIGNED: ((-20.0, 30.0), 5.0, nan, [6.0, 1.0], [30.0, 5.0]),
             NO_BASE: ((-30.0, 10.0), -10.0, nan, nan, [10.0, -10.0])}  # fmt: skip
    for reason, (targets, base, capture, lift, estimate) in cases.items():
        cells = _slice_cells("x", [(p, b, target, 100) for b, target in enumerate(targets)])
        meta = {"snapshot_period": p, "snapshot_base": base, "slices": slice_shares(resolved, 200)}
        slices, curve = slice_tables(cells, _slice_ranking(["x"], ["numeric"], [1]), meta,
                                     resolved, [p], 50.0)  # fmt: skip
        assert (slices["unavailable"] == reason).all() and curve.empty == bool(reason)
        read = slices[["capture", "lift", "estimate"]].to_numpy().T
        np.testing.assert_allclose(read, [capture, lift, estimate])
    with pytest.raises(ValueError, match="not positive"):
        capture_curve(ordered_numeric_bins(cells, 1, p), SLICE_GRID)


def _profile_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A snapshot (eleven eligible rows and one not), its ranking and the categorical's cells,
    labelled by `cap_levels` as the counts pass names levels."""
    snapshot = pd.DataFrame({
        "eligible": [1] * 11 + [0],
        "x": [1, 2, 3, np.nan, np.inf, -np.inf, 999, 999, 5, 4, 0, -1e9],
        "y": np.arange(12, dtype=float),
        "c": ["A", "A", "A", "A", "B", "B", "B", "", "", "C", None, "A"],
    })  # fmt: skip
    ranking = pd.DataFrame({"feature": ["y", "c", "x"],
                            "kind": ["numeric", "categorical", "numeric"], "rank": [3, 1, 2],
                            "missing_share": [0.0, 1 / 11, 1 / 11]})  # fmt: skip
    levels = cap_levels(snapshot.loc[snapshot["eligible"] == 1, "c"], 50).value_counts()
    cells = pd.DataFrame({"feature": "c", "period": "2025-08", "lagged": False,
                          "bin": levels.index.astype(str), "bin_order": range(len(levels)),
                          "is_null": levels.index == "null", "target_bin": None,
                          "n": levels.to_numpy(), "sum_y": np.nan, "sum_y2": np.nan})  # fmt: skip
    return snapshot, ranking, cells


def test_value_profile_ranges_are_pandas_on_the_finite_values() -> None:
    """On the eligible rows, the range equals pandas' quantiles of the finite non-null values (a
    sentinel 999 at `max`), `inf_share` counts both infinities, and the categorical's top three
    levels come from its cells with their shares of every row, blank quoted; rank order."""
    snapshot, ranking, cells = _profile_inputs()
    kinds = {"x": "numeric", "y": "numeric", "c": "categorical"}
    profile = value_profile(snapshot, kinds, ranking, cells, "2025-08").set_index("feature")
    assert profile.index.tolist() == ["c", "x", "y"] and (profile["rows"] == 11).all()
    finite = pd.Series([1, 2, 3, 999, 999, 5, 4, 0], dtype=float)
    expected = finite.quantile([0, 0.01, 0.5, 0.99, 1]).to_numpy()
    np.testing.assert_allclose(profile.loc["x", list(QUANTILES)].astype(float), expected)
    assert profile.loc["x", "max"] == 999 and profile.loc["x", "inf_share"] == 2 / 11
    assert profile.loc["c", "top_levels"] == "A: 36.4% · B: 27.3% · '': 18.2%"
    assert profile.loc["x", "top_levels"] == "" and np.isnan(profile.loc["c", "min"])


def test_value_profile_keeps_its_columns_without_a_kind() -> None:
    """Only numerics, or only a categorical: the same columns either way."""
    snapshot, ranking, cells = _profile_inputs()
    numerics = value_profile(snapshot, {"x": "numeric"}, ranking, cells, "2025-08")
    categorical = value_profile(snapshot, {"c": "categorical"}, ranking, cells, "2025-08")
    assert numerics.columns.tolist() == categorical.columns.tolist() == PROFILE_COLUMNS
    assert numerics["top_levels"].tolist() == [""] and categorical["min"].isna().all()


def test_the_value_profile_view_splits_the_kinds_and_prints_amounts_plainly() -> None:
    """Numerics then categoricals, each with its own columns and no `rows`; a kind without a
    candidate reads not available; an amount prints with separators, never as 6.931e+04."""
    snapshot, ranking, cells = _profile_inputs()
    kinds = {"x": "numeric", "y": "numeric", "c": "categorical"}
    numeric, categorical = _profile_views(value_profile(snapshot, kinds, ranking, cells, "2025-08"))
    assert numeric.data.columns.tolist() == ["feature", "rank", "missing_share", *QUANTILES,
                                             "inf_share"]  # fmt: skip
    assert categorical.data.columns.tolist() == ["feature", "rank", "missing_share", "top_levels"]
    only = _profile_views(value_profile(snapshot, {"x": "numeric"}, ranking, cells, "2025-08"))
    assert only[1] == "<p>Not available: no categorical candidate.</p>"
    assert [plain_number(x) for x in (69_310.4, -1_000.0, 0.331_49, 12.0)] == [
        "69,310", "-1,000", "0.3315", "12"]  # fmt: skip


def test_the_slices_view_states_the_decision_and_draws_the_diagonal_as_a_reference(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A top_n decision's paragraph gives its share of the labelled rows, the perfect and a
    random list and says the view is no baseline; the caption names the skipped count; the
    `random` line is dashed and muted; without a key feature the view says not available."""
    resolved = variant(decision={"type": "top_n", "n": 100},
                       evaluation={"slices": {"top_pct": [0.1], "top_n": [5_000]}})  # fmt: skip
    population = pd.DataFrame(
        {"period": ["2025-08"], "known_target": [1_000], "positive_events": [50]}
    )
    slices = pd.DataFrame(
        {"feature": "x", "slice": ["decision n = 100", "top 10%"], "share": 0.1, "rows": 100.0,
         "support": 30.0, "estimate": 0.3, "low": 0.2, "high": 0.4, "lift": 6.0, "capture": 0.6,
         "insufficient": [False, True], "unavailable": ""}
    )  # fmt: skip
    curve = pd.DataFrame({"feature": ["x", "x", "random", "random"], "share": [0.5, 1.0] * 2,
                          "capture": [0.9, 1.0, 0.5, 1.0]})  # fmt: skip
    tables = {"population": population, "slices": slices, "capture_curve": curve}
    meta = {"snapshot_period": "2025-08", "snapshot_base": 0.05}
    views = _slices_views(tables, meta, resolved)
    text, (table, chart) = views["decision_note"], views["slices"]
    assert (
        "n = 100, 10.0% of the snapshot's 1,000 labelled rows: a perfect list captures all 50 "
        "positives at 50.0% precision; a random list captures 10.0% of the positives at the "
        "base rate 5.00%." in unescape(text)
    )
    assert "not a baseline" in text
    assert table.data.columns.tolist() == ["feature", "slice", "capture", "estimate", "lift",
                                           "support"]  # fmt: skip
    assert "skipped, above the labelled rows: n = 5,000" in table.caption
    random = next(trace for trace in chart.data if trace.name == "random")
    assert random.line.dash == "dash" and random.line.color == THEME["muted"]
    assert chart.layout.yaxis.range == (0, 1.02)  # capture stops at 100%
    empty = {**tables, "slices": slices.iloc[:0], "capture_curve": curve.iloc[:0]}
    assert _slices_views(empty, meta, resolved)["slices"] == [
        "<p>Not available: no key feature.</p>"
    ]
