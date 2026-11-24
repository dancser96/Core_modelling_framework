"""Evaluation's metric tables, slices, baselines and drift reference (evaluation/tables.py,
slices.py, baselines.py, drift_reference.py) on score cells built from constructed rows with
`cells_oracle.cells_from_rows`, replicates stacked with Poisson client weights; two Spark tests
for the baselines' columns."""

import inspect
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from cells_oracle import cells_from_rows
from conftest import REGRESSION
from pyspark.sql import SparkSession
from scipy.special import expit
from sklearn.metrics import log_loss

from core_modelling.artifacts import STAGE_SCHEMA_VERSIONS
from core_modelling.config import UseCaseConfig
from core_modelling.evaluation.baselines import (
    NULL_SCORE,
    RAW_FEATURE,
    add_baselines,
    baseline_columns,
    baseline_loss,
    choose_single_feature,
    compare_baselines,
    describe_baseline_columns,
)
from core_modelling.evaluation.drift_reference import _feature_shares, build_drift_reference
from core_modelling.evaluation.tables import MEAN, metric_rows, metric_tables
from core_modelling.run_artifacts import STAGE2_COLUMNS, read_stage2_copy
from core_modelling.statistics.distributions import psi
from core_modelling.statistics.metrics import binary_metrics, binned_concordance
from core_modelling.statistics.score_cells import POOLED, bin_quantiles
from core_modelling.tasks import TASK_SPECS
from core_modelling.training.gate import Stage2, save_stage2

BINARY_GRID = TASK_SPECS["binary"]["score_grid"]
REGRESSION_GRID = TASK_SPECS["regression"]["score_grid"]
REPLICATES = 20
TEST_PERIODS = ["2024-01", "2024-02", "2024-03"]
VALIDATION = "2024-06"
BASE = 0.1
PREVIOUS = [{"previous_model": "old_score"}]  # a previous model's score column as a baseline


def _rows(clients: int = 3_000) -> pd.DataFrame:
    """Test clients in three periods and every client at the validation period, with a
    `segment` of three levels (`tiny` rare) and a score whose level moves by period."""
    rng = np.random.default_rng(3)
    client = np.arange(clients)
    split = np.where(client % 3 == 0, "train", "test")
    segment = rng.choice(["large", "small", "tiny"], clients, p=[0.7, 0.29, 0.01])
    frames = []
    for i, period in enumerate([*TEST_PERIODS, VALIDATION]):
        part = "validation" if period == VALIDATION else "test"
        keep = np.ones(clients, bool) if part == "validation" else split == "test"
        margin = rng.normal(-2.2 + 0.4 * i, 1.0, clients)
        frames.append(pd.DataFrame({
            "client": client, "part": part, "period": period, "split": split, "segment": segment,
            "score": expit(margin), "target": (rng.random(clients) < expit(margin)).astype(float),
        }).loc[keep])  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def _strata_grid(task: str) -> np.ndarray:
    """The strata's cut points: every `strata_step`-th of the task's `bin_quantiles`."""
    spec = TASK_SPECS[task]
    return bin_quantiles(spec["score_grid"])[spec["strata_step"] - 1 :: spec["strata_step"]]


def _cells(
    rows: pd.DataFrame, by: list[str], grid: np.ndarray, loss: str | None, zero_bin: bool = False
) -> pd.DataFrame:
    """Every replicate's cells: replicate 0 at weight 1, then `REPLICATES` with one Poisson(1)
    weight per client, the score cut at the cut points `grid` over every row; the target its
    own bin, or with `zero_bin` the zero bin and one bin for every non-zero target."""
    edges = np.quantile(rows["score"], grid)
    target_bin = (rows["target"] != 0) if zero_bin else rows["target"]
    binned = rows.assign(score_bin=np.searchsorted(edges, rows["score"], side="right"),
                         target_bin=target_bin.astype(int))  # fmt: skip
    rng = np.random.default_rng(5)
    weights = [np.ones(rows["client"].max() + 1, int)]
    weights += [rng.poisson(1.0, rows["client"].max() + 1) for _ in range(REPLICATES)]
    frames = [
        cells_from_rows(binned.assign(weight=w[binned["client"]]), by, loss).assign(replicate=r)
        for r, w in enumerate(weights)
    ]
    return pd.concat(frames, ignore_index=True)


def _model_cells(
    rows: pd.DataFrame, loss: str | None = "log_loss"
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """The cells `metric_tables` reads: `all` and `split`, and apart the `segment` stratum's."""
    cells = {"all": _cells(rows, [], bin_quantiles(BINARY_GRID), loss),
             "split": _cells(rows, ["split"], bin_quantiles(BINARY_GRID), loss)}  # fmt: skip
    return cells, {"segment": _cells(rows, ["segment"], _strata_grid("binary"), loss)}


def _population(rows: pd.DataFrame) -> dict[str, int]:
    """Each period's eligible rows over both splits: every client."""
    return dict.fromkeys([*TEST_PERIODS, VALIDATION], int(rows["client"].nunique()))


@pytest.fixture(scope="module")
def card(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The card config with one stratum, a 10% slice and a 1,000-client list, few replicates."""
    return variant(
        strata={"variables": ["segment"], "min_events": 50},
        evaluation={"slices": {"top_pct": [0.1], "top_n": [1_000]},
                    "intervals": {"replicates": REPLICATES}},
    )  # fmt: skip


@pytest.fixture(scope="module")
def built(card: UseCaseConfig) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """The rows and the model's tables, built once."""
    rows = _rows()
    cells, strata = _model_cells(rows)
    return rows, metric_tables(cells, strata, card, BASE, _population(rows), loss="log_loss")


def test_the_slices_are_cut_inside_each_period_and_add_up(
    built: tuple[pd.DataFrame, dict[str, pd.DataFrame]],
) -> None:
    """Each period's top 10% holds a tenth of that period's test rows although the score's level
    moves by period (a pooled cut would take the last period's rows), and the pooled slice is
    the periods added up; the fixed capture depths are there, not configured."""
    rows, tables = built
    slices = tables["slices"].loc[tables["slices"]["part"] == "test"]
    top = slices.loc[slices["slice"] == "top 10%"].set_index("period")
    counts = rows.loc[rows["part"] == "test"].groupby("period").size()
    for period in TEST_PERIODS:
        assert top.loc[period, "rows"] == pytest.approx(0.1 * counts[period])
    assert top.loc[POOLED, "rows"] == pytest.approx(top.loc[TEST_PERIODS, "rows"].sum())
    assert top.loc[POOLED, "target"] == pytest.approx(top.loc[TEST_PERIODS, "target"].sum())
    depths = slices.loc[~slices["configured"].astype(bool), "slice"].unique()
    assert list(depths) == ["top 1%", "top 2%", "top 5%", "top 20%", "top 30%", "top 50%"]


def test_each_slice_rate_has_its_bootstrap_interval_per_period_and_pooled(
    built: tuple[pd.DataFrame, dict[str, pd.DataFrame]],
) -> None:
    """Capture, rate and lift each sit inside their interval in every period and pooled, the
    pooled interval narrower than a period's; a slice not available has none."""
    _, tables = built
    slices = tables["slices"].loc[tables["slices"]["unavailable"] == ""]
    for rate in ("capture", "rate", "lift"):
        low, value, high = (slices[f"{rate}_low"], slices[rate], slices[f"{rate}_high"])
        assert ((low <= value) & (value <= high) & (low < high)).all(), rate
    top = slices.loc[(slices["part"] == "test") & (slices["slice"] == "top 10%")]
    width = (top["lift_high"] - top["lift_low"]).set_axis(top["period"])
    assert width[POOLED] < width[TEST_PERIODS].min()
    unavailable = tables["slices"].loc[tables["slices"]["unavailable"] != ""]
    assert unavailable[["capture_low", "lift_high"]].isna().all().all()


def test_a_top_n_above_a_periods_population_is_not_available(card: UseCaseConfig) -> None:
    """A list of 1,000 in a period of 500 eligible rows is not available there and in the sum,
    while the other periods keep theirs."""
    rows = _rows()
    population = {**_population(rows), TEST_PERIODS[0]: 500}
    cells = {"all": _cells(rows, [], bin_quantiles(BINARY_GRID), "log_loss")}
    slices = metric_tables(cells, {}, card, BASE, population, loss="log_loss")["slices"]
    listed = slices.loc[(slices["part"] == "test") & (slices["slice"] == "top 1,000")]
    listed = listed.set_index("period")
    for period in (TEST_PERIODS[0], POOLED):
        assert listed.loc[period, "unavailable"].startswith("not available")
        assert np.isnan(listed.loc[period, "rows"])
    assert listed.loc[TEST_PERIODS[1], "unavailable"] == ""


def test_the_pooled_period_and_mean_rows_are_all_there(
    built: tuple[pd.DataFrame, dict[str, pd.DataFrame]],
) -> None:
    """Test has a pooled row, one per period and the mean of the periods; validation its period
    beside them and the test clients' part too. The pooled value is the metric on all the
    part's rows (the log loss exactly), and the mean row is the mean of the period rows."""
    rows, tables = built
    metrics = tables["metrics"].loc[tables["metrics"]["stratum"].isna()]
    auc = metrics.loc[metrics["metric"] == "roc_auc"].set_index(["part", "period"])
    assert set(auc.loc["test"].index) == {POOLED, *TEST_PERIODS, MEAN}
    assert set(auc.loc["validation"].index) == {POOLED, VALIDATION}
    assert set(auc.loc["validation_test_clients"].index) == {POOLED, VALIDATION}
    test = rows.loc[rows["part"] == "test"]
    pooled = metrics.set_index(["part", "period", "metric"]).loc[("test", POOLED)]
    assert pooled.loc["log_loss", "value"] == pytest.approx(log_loss(test["target"], test["score"]))
    first = _model_cells(rows)[0]["all"]
    first = first.loc[(first["replicate"] == 0) & (first["part"] == "test")]
    assert pooled.loc["roc_auc", "value"] == binary_metrics(first, BASE)["roc_auc"]
    assert auc.loc[("test", MEAN), "value"] == pytest.approx(
        auc.loc[[("test", p) for p in TEST_PERIODS], "value"].mean()
    )
    low, high = auc.loc[("test", POOLED), ["low", "high"]]
    assert low < auc.loc[("test", POOLED), "value"] < high


def test_a_stratum_level_below_the_minimum_is_greyed_not_hidden(
    built: tuple[pd.DataFrame, dict[str, pd.DataFrame]],
) -> None:
    """The rare level has its metric rows and its composition row, marked insufficient."""
    _, tables = built
    levels = tables["metrics"].loc[tables["metrics"]["stratum"] == "segment"]
    tiny = levels.loc[(levels["level"] == "tiny") & (levels["part"] == "test")]
    assert not tiny.empty and tiny["insufficient"].all() and (tiny["events"] < 50).all()
    strata = tables["strata"].set_index(["part", "level"])
    assert strata.loc[("test", "tiny"), "insufficient"]
    assert not strata.loc[("test", "large"), "insufficient"]


def test_a_regression_levels_events_are_its_rows_with_a_non_zero_target(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A regression stratum's cells hold the zero bin and one bin for every non-zero target:
    a level's events are its rows with a non-zero target, and it has no concordance row."""
    cfg = variant(**REGRESSION, strata={"variables": ["segment"], "min_events": 50},
                  evaluation={"intervals": {"replicates": REPLICATES}})  # fmt: skip
    rows = _rows()
    amount = rows["target"] * np.random.default_rng(4).gamma(2.0, 50.0, len(rows))
    rows = rows.assign(target=amount, score=rows["score"] * 100)
    cells = {"all": _cells(rows, [], bin_quantiles(REGRESSION_GRID), None, zero_bin=True)}
    strata = {"segment": _cells(rows, ["segment"], _strata_grid("regression"), None,
                                zero_bin=True)}  # fmt: skip
    metrics = metric_tables(cells, strata, cfg, 30.0, _population(rows), loss=None)["metrics"]
    levels = metrics.loc[(metrics["stratum"] == "segment") & (metrics["part"] == "test")]
    test = rows.loc[rows["part"] == "test"]
    for level, own in test.groupby("segment"):
        assert (levels.loc[levels["level"] == level, "events"] == (own["target"] != 0).sum()).all()
    assert "concordance" not in set(levels["metric"])


def test_the_lists_composition_sums_to_the_list(
    built: tuple[pd.DataFrame, dict[str, pd.DataFrame]],
) -> None:
    """At the decision's slice (the first configured, top 10%) the levels' list rows add up to
    the list the slices table cut, and both shares sum to 1."""
    _, tables = built
    slices = tables["slices"].set_index(["part", "period", "slice"])
    for part in ("test", "validation"):
        strata = tables["strata"].loc[tables["strata"]["part"] == part]
        assert (strata["slice"] == "top 10%").all()
        listed = slices.loc[(part, POOLED, "top 10%"), "rows"]
        assert strata["list_rows"].sum() == pytest.approx(listed)
        assert strata["list_share"].sum() == pytest.approx(1)
        assert strata["population_share"].sum() == pytest.approx(1)


def test_a_stratum_named_all_with_levels_mean_and_pooled_reads_its_own_cells(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A stratum `all` whose levels are `pooled`, `mean` and `tiny`: each level's metrics are
    read on that level's cells alone, and the part's pooled metrics on every cell, never
    replaced by the stratum's."""
    cfg = variant(strata={"variables": ["all"], "min_events": 50},
                  evaluation={"intervals": {"replicates": REPLICATES}})  # fmt: skip
    names = {"large": "pooled", "small": "mean", "tiny": "tiny"}
    rows = _rows().assign(all=lambda frame: frame["segment"].map(names))
    every = _cells(rows, [], bin_quantiles(BINARY_GRID), "log_loss")
    cells = {"all": every, "split": _cells(rows, ["split"], bin_quantiles(BINARY_GRID), "log_loss")}
    stratum = _cells(rows, ["all"], _strata_grid("binary"), "log_loss")
    tables = metric_tables(cells, {"all": stratum}, cfg, BASE, _population(rows), loss="log_loss")
    metrics = tables["metrics"]
    test = rows.loc[rows["part"] == "test"]
    levels = metrics.loc[(metrics["stratum"] == "all") & (metrics["part"] == "test")]
    levels = levels.set_index(["level", "metric"])["value"]
    first = stratum.loc[(stratum["replicate"] == 0) & (stratum["part"] == "test")]
    for level, own in test.groupby("all"):
        assert levels[(level, "log_loss")] == pytest.approx(log_loss(own["target"], own["score"]))
        auc = binary_metrics(first.loc[first["all"] == level], BASE)["roc_auc"]
        assert levels[(level, "roc_auc")] == auc
    pooled = metrics.loc[metrics["stratum"].isna() & (metrics["period"] == POOLED)]
    pooled = pooled.set_index(["part", "metric"])["value"]
    whole = every.loc[(every["replicate"] == 0) & (every["part"] == "test")]
    assert pooled[("test", "roc_auc")] == binary_metrics(whole, BASE)["roc_auc"]


def test_a_baseline_value_left_undefined_reads_not_available(
    card: UseCaseConfig, built: tuple[pd.DataFrame, dict[str, pd.DataFrame]]
) -> None:
    """A compared value the part's rows leave undefined (NaN with no reason declared up front,
    here the single feature's validation AUC) is not available with its reason, never a blank
    cell; the defined cells beside it stay available."""
    _, tables = built
    feature = tables["metrics"].copy()
    undefined = (feature["part"] == "validation") & (feature["metric"] == "roc_auc")
    feature.loc[undefined, ["value", "low", "high"]] = np.nan
    metrics = {"model": tables["metrics"], "single_feature": feature}
    table = compare_baselines(metrics, card, BASE, {}, card.training.objective)
    table = table.set_index(["scorer", "part", "metric"])
    cell = table.loc[("single_feature", "validation", "roc_auc")]
    assert cell["unavailable"].startswith("not available") and np.isnan(cell["value"])
    assert table.loc[("single_feature", "test", "roc_auc"), "unavailable"] == ""


def test_the_single_feature_is_chosen_from_the_ledgers_alone() -> None:
    """No row argument exists; the unordered categorical with the highest concordance is
    passed over for the best numeric or ordered one, whose direction comes along."""
    assert list(inspect.signature(choose_single_feature).parameters) == [
        "run_ledger", "stage2_ledger", "order"
    ]  # fmt: skip
    run_ledger = pd.DataFrame({
        "feature": ["channel", "income", "tier", "age"],
        "train_concordance": [0.80, 0.62, 0.70, np.nan], "train_sign": [1, 1, -1, 0],
    })  # fmt: skip
    kinds = ["categorical", "numeric", "categorical", "numeric"]
    stage2 = pd.DataFrame({"feature": ["channel", "income", "tier", "age"], "kind": kinds})
    choice = choose_single_feature(run_ledger, stage2, {"tier": ["low", "mid", "high"]})
    assert choice == {"feature": "tier", "kind": "ordered", "sign": -1,
                      "levels": ["low", "mid", "high"], "train_concordance": 0.70}  # fmt: skip
    assert choose_single_feature(run_ledger, stage2, {})["feature"] == "income"
    assert choose_single_feature(run_ledger.iloc[[0, 3]], stage2, {}) is None


def test_a_run_feature_without_a_stage2_ledger_row_is_refused() -> None:
    """The single feature is chosen from the two ledgers: a feature of the run's ledger that the
    Stage 2 copy has no row for fails, naming it, rather than being passed over."""
    run_ledger = pd.DataFrame({"feature": ["income", "age"], "train_concordance": [0.6, 0.7],
                               "train_sign": [1, 1]})  # fmt: skip
    stage2 = pd.DataFrame({"feature": ["income"], "kind": ["numeric"]})
    with pytest.raises(ValueError, match=r"the Stage 2 ledger has no row for \['age'\]"):
        choose_single_feature(run_ledger, stage2, {})


def test_metric_tables_refuse_cells_and_a_population_they_cannot_read(
    card: UseCaseConfig, built: tuple[pd.DataFrame, dict[str, pd.DataFrame]]
) -> None:
    """A stratum that is no `strata.variables`, a period of the cells without its eligible
    population, a part without cells and a stratum with a null level are each refused, naming
    what is wrong, before any table is returned."""
    rows, _ = built
    cells, strata = _model_cells(rows)
    population = _population(rows)
    arguments = (card, BASE)
    with pytest.raises(ValueError, match=r"\['region'\] are not among the strata.variables"):
        metric_tables(cells, {"region": strata["segment"]}, *arguments, population,
                      loss="log_loss")  # fmt: skip
    short_population = {name: size for name, size in population.items() if name != VALIDATION}
    with pytest.raises(ValueError, match=r"no eligible population for the periods \['2024-06'\]"):
        metric_tables(cells, strata, *arguments, short_population, loss="log_loss")
    no_validation = {**cells, "all": cells["all"].loc[cells["all"]["part"] != "validation"]}
    with pytest.raises(ValueError, match=r"the parts \['validation'\] hold no score cells"):
        metric_tables(no_validation, strata, *arguments, population, loss="log_loss")
    unlabelled = {"segment": strata["segment"].assign(segment=None)}
    with pytest.raises(ValueError, match="the stratum 'segment' has a null level"):
        metric_tables(cells, unlabelled, *arguments, population, loss="log_loss")


def test_the_drift_reference_refuses_a_copy_that_misses_a_period_or_holds_a_stray_bin() -> None:
    """From a hand-made `stage2/` copy: a feature with no cells in one of the window's periods,
    and cells in a bin its EDA edges do not have, are refused, naming the feature."""
    cells = pd.DataFrame({"feature": ["income"], "lagged": [False], "period": ["2024-01"],
                          "bin": ["< 10"], "bin_order": [0], "n": [10]})  # fmt: skip
    stage2 = {"cells": cells,
              "edges": pd.DataFrame({"feature": ["income"], "position": [0], "edge": [10.0]}),
              "ledger": pd.DataFrame({"feature": ["income"], "kind": ["numeric"]})}  # fmt: skip
    with pytest.raises(ValueError, match=r"no cells of 'income' in \['2024-02'\]"):
        _feature_shares(stage2, ["income"], ["2024-01", "2024-02"])
    stray = {**stage2, "cells": cells.assign(bin_order=5)}
    with pytest.raises(ValueError, match=r"'income' has cells in bins \[5\] outside its EDA bins"):
        _feature_shares(stray, ["income"], ["2024-01"])


def test_compare_baselines_gives_not_available_for_a_raw_features_log_loss(
    card: UseCaseConfig, built: tuple[pd.DataFrame, dict[str, pd.DataFrame]]
) -> None:
    """The raw feature fills AUC and has no log loss or mean prediction, by its form; the base
    rate shows its rate; the observed rate stands beside them."""
    rows, tables = built
    feature = rows.assign(score=rows["score"] + np.random.default_rng(1).normal(0, 0.2, len(rows)))
    feature_cells = {"all": _cells(feature, [], bin_quantiles(BINARY_GRID), None)}
    metrics = {"model": tables["metrics"],
               "single_feature": metric_rows(feature_cells, card, BASE, loss=None)}  # fmt: skip
    table = compare_baselines(metrics, card, BASE, {}, card.training.objective)
    table = table.set_index(["scorer", "part", "metric"])
    assert table.loc[("single_feature", "test", "log_loss"), "unavailable"] == RAW_FEATURE
    assert np.isnan(table.loc[("single_feature", "test", "log_loss"), "value"])
    assert table.loc[("single_feature", "test", "roc_auc"), "unavailable"] == ""
    assert 0.5 < table.loc[("single_feature", "test", "roc_auc"), "value"]
    assert table.loc[("population_base_rate", "test", "mean_prediction"), "value"] == BASE
    assert table.loc[("population_base_rate", "test", "roc_auc"), "unavailable"].startswith(
        "not available"
    )
    observed = rows.loc[rows["part"] == "test", "target"].mean()
    assert table.loc[("observed", "test", "mean_prediction"), "value"] == pytest.approx(observed)


def test_a_previous_models_nulls_rank_lowest_and_switch_its_level_metrics_off(
    variant: Callable[..., UseCaseConfig], built: tuple[pd.DataFrame, dict[str, pd.DataFrame]]
) -> None:
    """A previous model with 20% nulls (scored at `NULL_SCORE`) fills AUC and reads "has nulls
    (20.0%)" on its log loss and mean prediction, decided from its facts before any cell."""
    rows, tables = built
    cfg = variant(decision={"baselines": PREVIOUS},
                  evaluation={"intervals": {"replicates": REPLICATES}})  # fmt: skip
    nulls = np.random.default_rng(2).random(len(rows)) < 0.2
    previous = rows.assign(score=rows["score"].where(~nulls, NULL_SCORE))
    facts = {"previous_model": {"null_share": 0.2, "min": 0.01, "max": 0.95}}
    objective = cfg.training.objective
    loss, _ = baseline_loss("previous_model", cfg, facts["previous_model"], objective)
    previous_cells = {"all": _cells(previous, [], bin_quantiles(BINARY_GRID), loss)}
    metrics = {"model": tables["metrics"],
               "previous_model": metric_rows(previous_cells, cfg, BASE, loss=loss)}  # fmt: skip
    table = compare_baselines(metrics, cfg, BASE, facts, objective)
    table = table.set_index(["scorer", "part", "metric"])
    for label in ("log_loss", "mean_prediction"):
        cell = table.loc[("previous_model", "test", label)]
        assert cell["unavailable"] == "not available: `old_score` has nulls (20.0%)"
        assert np.isnan(cell["value"])
    assert 0.5 < table.loc[("previous_model", "test", "roc_auc"), "value"]


def test_baseline_loss_is_decided_from_the_form_and_the_columns_facts(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A clean probability carries the model's loss; one outside [0, 1] is no prediction; a
    deviance refuses a non-positive prediction on the deviance alone; a rate fills its rate."""
    card = variant(decision={"baselines": ["population_base_rate", *PREVIOUS]})
    clean = {"null_share": 0.0, "min": 0.01, "max": 0.9}
    assert baseline_loss("previous_model", card, clean, "log_loss") == ("log_loss", {})
    loss, reasons = baseline_loss("previous_model", card, {**clean, "max": 3.0}, "log_loss")
    assert loss is None and set(reasons) == {"log_loss", "mean_prediction"}
    assert "runs from 0.01 to 3, outside [0, 1]" in reasons["log_loss"]
    rate_reasons = baseline_loss("population_base_rate", card, None, "log_loss")[1]
    assert set(rate_reasons) == {"log_loss", "roc_auc", "ap"}
    amount = variant(**REGRESSION, decision={"metric": "tweedie_deviance", "baselines": PREVIOUS},
                     training={"objective": "tweedie"})  # fmt: skip
    loss, reasons = baseline_loss("previous_model", amount, {**clean, "min": 0.0}, "tweedie")
    assert loss is None and list(reasons) == ["tweedie_deviance"]
    assert baseline_loss("previous_model", amount, clean, "tweedie") == ("tweedie_deviance", {})


def test_the_drift_reference_is_accepted_by_psi(
    tmp_path: Path, built: tuple[pd.DataFrame, dict[str, pd.DataFrame]]
) -> None:
    """From a saved `stage2/` copy and the test part's score counts: each feature's and the
    score's shares cover a fixed bin list per period and pooled, sum to 1, and go into `psi`
    against a window period."""
    rows, _ = built
    cells = pd.DataFrame({
        "feature": ["income"] * 4 + ["channel"] * 3, "lagged": False,
        "period": ["2024-01", "2024-01", "2024-02", "2024-02", "2024-01", "2024-02", "2024-02"],
        "bin": ["< 10", "≥ 10", "< 10", "null", "web", "branch", "null"],
        "bin_order": [0, 1, 0, 2, 0, 1, 4], "n": [30, 70, 50, 50, 10, 6, 4],
    })  # fmt: skip
    tables = {"cells": cells,
              "edges": pd.DataFrame({"feature": ["income"], "position": [0], "edge": [10.0]}),
              "bins": pd.DataFrame({"feature": ["income"]}),
              "levels": pd.DataFrame({"feature": ["channel"]}),
              "ledger": pd.DataFrame({"feature": ["income", "channel"],
                                      "kind": ["numeric", "categorical"]})}  # fmt: skip
    # the copy's frozen columns, the ones this test does not fill left null
    tables = {name: table.reindex(columns=list(STAGE2_COLUMNS[name]))
              for name, table in tables.items()}  # fmt: skip
    stage2 = Stage2(
        eda_meta={"schema_version": STAGE_SCHEMA_VERSIONS["eda"]},
        eda_tables={name: tables[name] for name in ("cells", "edges", "bins", "levels")},
        feature_checks_meta={},
        ledger=tables["ledger"],
        tokens={"eda": "a", "feature_checks": "b"},
    )
    save_stage2(str(tmp_path / "stage2"), stage2, ["income", "channel"])
    test = rows.loc[(rows["part"] == "test") & rows["period"].isin(["2024-01", "2024-02"])]
    score_cells = _cells(test, [], bin_quantiles(BINARY_GRID), "log_loss")
    first = score_cells.loc[(score_cells["replicate"] == 0) & (score_cells["part"] == "test")]
    counts = first.groupby(["period", "score_bin"], as_index=False).agg(
        rows=("rows", "sum"), score_min=("score_min", "min"), score_max=("score_max", "max")
    )
    copy = read_stage2_copy(str(tmp_path))
    reference = build_drift_reference(copy, counts, ["income", "channel"])
    features = reference["features"]
    assert set(features.loc[features["feature"] == "channel", "bin"]) == {
        "web", "branch", "__other__", "null"
    }  # fmt: skip
    income = features.loc[features["feature"] == "income"]
    for name, table, bins in (("income", income, "bin_order"),
                              ("score", reference["scores"], "group")):  # fmt: skip
        shares = table.pivot_table(index=bins, columns="period", values="share")
        assert np.allclose(shares.sum(), 1), name
        assert np.isfinite(psi(shares[POOLED].to_numpy(), shares["2024-01"].to_numpy()))
    assert reference["scores"]["group"].nunique() == 10
    with pytest.raises(ValueError, match=r"no cells of the final features \['tenure'\]"):
        build_drift_reference(copy, counts, ["income", "channel", "tenure"])


def test_add_baselines_puts_a_null_lowest_in_trains_direction(
    spark: SparkSession, card: UseCaseConfig
) -> None:
    """A falling feature scores by its negated value, a null and a NaN below every value; an
    ordered categorical by its declared position, a level held as a double (3.0) matching its
    text (`3`) as the encoder codes it; the carried columns are dropped."""
    rows = spark.createDataFrame(
        [(1, 5.0, "low", 3.0), (2, -3.0, "high", 1.0), (3, None, None, None),
         (4, float("nan"), "mid", 2.0)],
        "unit_id int, income double, tier string, grade double",
    )  # fmt: skip
    falling = {"feature": "income", "kind": "numeric", "sign": -1, "levels": None}
    choice = {"features": [], "single_feature": falling}
    scored = add_baselines(rows, card, choice).orderBy("unit_id").toPandas()
    assert "income" not in scored.columns
    assert scored["baseline_single_feature"].tolist() == [-5.0, 3.0, NULL_SCORE, NULL_SCORE]
    ordered = {"feature": "tier", "kind": "ordered", "sign": 1, "levels": ["low", "mid", "high"]}
    scored = add_baselines(rows, card, {"features": ["income"], "single_feature": ordered})
    values = scored.orderBy("unit_id").toPandas()["baseline_single_feature"].tolist()
    assert values == [0.0, 2.0, NULL_SCORE, 1.0]
    assert "income" in scored.columns and "tier" not in scored.columns
    grade = {"feature": "grade", "kind": "ordered", "sign": 1, "levels": ["1", "2", "3"]}
    scored = add_baselines(rows, card, {"features": [], "single_feature": grade}).orderBy("unit_id")
    assert scored.toPandas()["baseline_single_feature"].tolist() == [2.0, 0.0, NULL_SCORE, 1.0]


def test_a_column_baselines_facts_come_from_one_aggregate_and_its_nulls_score_lowest(
    spark: SparkSession, variant: Callable[..., UseCaseConfig]
) -> None:
    """A previous model's null and NaN count in its null share and score `NULL_SCORE`; its
    score column is named by `baseline_columns`, and rows already holding that name are
    refused."""
    cfg = variant(decision={"baselines": PREVIOUS})
    rows = spark.createDataFrame(
        [(1, 0.2), (2, None), (3, float("nan")), (4, 0.9)], "unit_id int, old_score double"
    )
    choice = {"features": [], "single_feature": None}
    facts = describe_baseline_columns(rows, cfg)
    assert facts == {"previous_model": {"null_share": 0.5, "min": 0.2, "max": 0.9}}
    assert baseline_columns(cfg, choice) == {"previous_model": "baseline_previous_model"}
    scored = add_baselines(rows, cfg, choice).orderBy("unit_id").toPandas()
    assert scored["baseline_previous_model"].tolist() == [0.2, NULL_SCORE, NULL_SCORE, 0.9]
    assert "old_score" not in scored.columns
    clashing = rows.withColumn("baseline_previous_model", rows["old_score"])
    with pytest.raises(ValueError, match="the names of the baseline score columns"):
        add_baselines(clashing, cfg, choice)


def test_binned_concordance_reads_rows_on_the_cells_buckets() -> None:
    """A hand-made frame of seven rows on two score edges and two target edges (a score at an
    edge opens the bucket above it, as `Bucketizer` cuts): the buckets are, by hand, scores
    0 1 1 2 2 0 1 and targets 0 1 1 2 2 0 2; of the 16 pairs in different target buckets, 14 are
    ordered with the score and 2 tie on it, so 15/16. On rows the pair (0.5, 2) and (0.6, 1)
    would count against it; on cells it shares a target bucket and does not count."""
    score = np.array([0.1, 0.5, 0.6, 0.9, 1.3, 0.2, 0.3])
    target = np.array([0.0, 2.0, 1.0, 3.0, 5.0, 0.0, 4.0])
    value = binned_concordance(score, target, np.array([0.3, 0.8]), np.array([0.5, 2.5]))
    assert value == pytest.approx(15 / 16)
    one_bucket = binned_concordance(score, np.zeros(7), np.array([0.3, 0.8]), np.array([0.5]))
    assert np.isnan(one_bucket)
