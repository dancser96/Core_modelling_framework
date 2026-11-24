"""Training's train-split statistics and its three selection rules on constructed frames (no
Spark): a panel of clients over several periods with their `cv_fold`, a strong numeric and a
noisy copy of it in one Stage 2 cluster, a U-shaped numeric, pure noise, a rarely-set noise
flag, a high-cardinality noise level column and an ordered categorical; a wide frame of a few
strong and many weak features; a feature whose values are noise and whose nulls predict the
target; and a frame of seven real features beside a rarely-set flag. The floor and the pruning
are checked on a zero-heavy amount too, under regression's default objective and under Tweedie."""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from conftest import REGRESSION
from scipy.stats import norm
from sklearn.metrics import roc_auc_score

from core_modelling.config import UseCaseConfig
from core_modelling.model.calibration import uncalibrated
from core_modelling.model.encoder import encode_frame, fit_encoder, select_encoder
from core_modelling.model.families import FAMILIES
from core_modelling.statistics.concordance import concordance_se
from core_modelling.training import selection
from core_modelling.training.fold_models import fit_fold_models, out_of_fold_loss
from core_modelling.training.selection import (
    NOISE_COLUMNS,
    apply_cluster_rule,
    apply_floor,
    prune_by_importance,
    prune_features,
    screen_features,
)
from core_modelling.training.train_data import encode_and_screen, finish_selection
from core_modelling.training.train_statistics import train_statistics

CLIENTS, PERIODS, SEED = 1200, 4, 3
NUMERICS = ["strong", "strong_copy", "u_shape", "noise", "sparse_noise"]
KINDS = {**dict.fromkeys(NUMERICS, "numeric"), "level_noise": "categorical", "tier": "categorical"}
FEATURES = list(KINDS)
TIERS = ["low", "mid", "high"]
SMALL_FITS = {  # one small configuration per family, in FLAML's own parameter names
    "lgbm": {"n_estimators": 20, "num_leaves": 8, "learning_rate": 0.1},
    "xgboost": {"n_estimators": 20, "max_leaves": 8, "learning_rate": 0.1},
    "xgb_limitdepth": {"n_estimators": 20, "max_depth": 4, "learning_rate": 0.1},
    "catboost": {"n_estimators": 20, "learning_rate": 0.1},
}
TASKS = {  # each case's config sections and objective (None: the task's default)
    "binary": ({}, None),
    "regression": (REGRESSION, None),
    "tweedie": ({**REGRESSION, "decision": {"metric": "tweedie_deviance"}}, "tweedie"),
}
PANEL_OF = {"binary": "binary", "regression": "regression", "tweedie": "regression"}
STAGE2 = pd.DataFrame(
    {
        "feature": FEATURES,
        "kind": list(KINDS.values()),
        "non_monotone": [False, False, True, False, False, False, False],
        "cluster": pd.array([1, 1, None, None, None, None, None], dtype="Int64"),
    }
)


def _panel(task: str = "binary") -> pd.DataFrame:
    """One row per client and period, the client's fold its id modulo 5: the target rises with
    `strong` and with `u_shape`'s distance from 0; every other column is noise but `tier`. The
    regression target is the binary one times a lognormal amount whose level rises with
    `strong`: zero on about two rows in three."""
    rng = np.random.default_rng(SEED)
    unit = np.repeat(np.arange(CLIENTS), PERIODS)
    n = unit.size
    strong, u_shape = rng.normal(size=n), rng.normal(size=n)
    logit = -1.0 + 1.5 * strong + 1.2 * (u_shape**2 - 1)
    levels = np.array([f"L{i}" for i in range(300)])[rng.integers(0, 300, CLIENTS)]
    frame = pd.DataFrame(
        {
            "unit_id": unit,
            "period": np.tile(
                pd.date_range("2024-01-01", periods=PERIODS, freq="MS").date, CLIENTS
            ),
            "strong": strong,
            "strong_copy": strong + rng.normal(scale=0.5, size=n),
            "u_shape": u_shape,
            "noise": rng.normal(size=n),
            "sparse_noise": (rng.random(n) < 0.02).astype(float),
            "level_noise": levels[unit],  # one level per client, about four clients per level
            "tier": np.array(TIERS)[np.digitize(strong, [-0.5, 0.5])],
            "target": (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int),
            "split": "train",
            "cv_fold": unit % 5,
        }
    )
    if task == "regression":  # drawn last, so the binary panel's draws stay as they are
        amount = np.exp(1.0 + 0.3 * strong + rng.normal(scale=0.3, size=n))
        frame["target"] = frame["target"] * amount
    return frame


def _encoded(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The panel, its encoded frame and the encoder (levels kept from two clients)."""
    encoder = fit_encoder(train, FEATURES, KINDS, {"tier": TIERS}, 2, "native")
    return train, encode_frame(train, encoder)[0], encoder


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The binary panel, its encoded frame and the encoder."""
    return _encoded(_panel())


@pytest.fixture(scope="module")
def panels(data: tuple) -> dict[str, tuple[pd.DataFrame, pd.DataFrame, dict]]:
    """`data` and its regression twin, by panel (`PANEL_OF`)."""
    return {"binary": data, "regression": _encoded(_panel("regression"))}


@pytest.fixture(scope="module")
def make_cfg(variant: Callable[..., UseCaseConfig]) -> Callable[..., UseCaseConfig]:
    """The card config, or its regression case (`TASKS`), with the selection switches and the
    kept features given."""

    def make(kept: list[str] | None = None, task: str = "binary", **rules: object) -> UseCaseConfig:
        """The variant, validated."""
        sections, objective = TASKS[task]
        training = {"selection": rules} | ({"objective": objective} if objective else {})
        return variant(**sections, training=training, features={"kept": kept or []})

    return make


@pytest.fixture(scope="module")
def stats(data: tuple, make_cfg: Callable[..., UseCaseConfig]) -> pd.DataFrame:
    """The train statistics of the panel, indexed by feature."""
    return train_statistics(*data, make_cfg()).set_index("feature")


@pytest.fixture(scope="module")
def stats_by_task(
    stats: pd.DataFrame, panels: dict, make_cfg: Callable[..., UseCaseConfig]
) -> dict[str, pd.DataFrame]:
    """`stats` and the regression panel's train statistics, by task, indexed by feature."""
    regression = train_statistics(*panels["regression"], make_cfg(task="regression"))
    return {"binary": stats, "regression": regression.set_index("feature")}


def test_a_strong_numerics_concordance_agrees_with_the_auc(
    data: tuple, stats: pd.DataFrame
) -> None:
    """At 100 quantile bins the train concordance is the raw rows' AUC within the binning's
    tolerance, read in its direction, with an SE on effective clients."""
    train = data[0]
    row = stats.loc["strong"]
    assert row["concordance"] == pytest.approx(
        roc_auc_score(train["target"], train["strong"]), abs=0.003
    )
    assert (row["sign"], row["unavailable"], row["value"]) == (1, "", row["concordance"])
    assert 0.005 < row["se"] < 0.05
    assert stats.loc["tier", "concordance"] > 0.6  # the ordered categorical read by its code


def test_an_unordered_categorical_is_cross_fitted(data: tuple, stats: pd.DataFrame) -> None:
    """A pure-noise level column with a few clients per level looks strong when its encoding is
    read on the rows it was fitted on, and does not pass the floor cross-fitted."""
    train = data[0]
    in_sample = train.groupby("level_noise")["target"].transform("mean")
    floor = apply_floor(stats.reset_index(), ["level_noise"], [], 2.0).iloc[0]
    assert roc_auc_score(train["target"], in_sample) > floor["threshold"]
    assert floor["outcome"] == "dropped"
    assert stats.loc["level_noise", "concordance"] < 0.55


@pytest.mark.parametrize("task", ["binary", "regression"])
def test_the_floor_reads_the_best_order_for_a_non_monotone_feature(
    task: str, stats_by_task: dict[str, pd.DataFrame]
) -> None:
    """A U-shaped signal passes the floor on its best-order concordance, which the row names;
    its plain one would drop it. Whether a feature is non-monotone is decided on the train rows
    by EDA's rule, never from Stage 2's mark, which has seen test labels (§4.4): the statistics
    take no Stage 2 input, mark the U shape themselves and judge plain noise on its plain
    concordance. The same holds for an amount, read by its concordance."""
    stats = stats_by_task[task]
    marked = apply_floor(stats.reset_index(), ["u_shape"], [], 2.0).iloc[0]
    assert stats.loc["u_shape", "non_monotone"]
    assert marked["value"] == stats.loc["u_shape", "concordance_best_order"]
    assert (marked["outcome"], marked["cleared_by"]) == ("passed", "concordance_best_order")
    plain = stats.reset_index().assign(value=stats["concordance"].to_numpy())
    assert apply_floor(plain, ["u_shape"], [], 2.0).iloc[0]["outcome"] == "dropped"
    assert not stats.loc["noise", "non_monotone"]
    assert stats.loc["noise", "value"] == stats.loc["noise", "concordance"]


def test_a_cluster_drop_is_not_judged_by_the_floor(
    data: tuple, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """The cluster rule runs first and the floor judges only what it left; pruning switched off
    writes no rows."""
    cfg = make_cfg(cluster=True, floor_z=2.0, prune=False)
    final, table, _ = screen_features(*data, STAGE2, cfg)
    assert prune_features(*data, final, cfg, 1)[0] == final
    copy = table.loc[table["feature"] == "strong_copy"]
    assert copy[["rule", "outcome", "represented_by"]].values.tolist() == [
        ["cluster", "dropped", "strong"]
    ]
    assert copy["threshold"].iloc[0] == table.loc[table["feature"] == "strong", "value"].iloc[0]
    assert set(table["rule"]) == {"cluster", "floor"}
    assert final == ["strong", "u_shape", "tier"]


def test_a_kept_feature_is_measured_and_never_dropped(
    data: tuple, stats: pd.DataFrame, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """Each rule shows a kept feature's value and marks it `protected` where it would drop it;
    the cluster's representative is still chosen with it in the comparison."""
    statistics = stats.reset_index()
    cluster = apply_cluster_rule(statistics, STAGE2, FEATURES, ["strong_copy"]).set_index("feature")
    assert cluster.loc["strong_copy", "outcome"] == "protected"
    assert pd.isna(cluster.loc["strong_copy", "represented_by"])
    assert cluster.loc["strong", "outcome"] == "passed"
    floor = apply_floor(statistics, ["noise"], ["noise"], 2.0).iloc[0]
    assert (floor["outcome"], floor["value"]) == ("protected", stats.loc["noise", "value"])
    train, X, encoder = data
    names = ["strong", "sparse_noise"]
    pruned = prune_by_importance(
        X[names], train["target"].to_numpy(), train[["cv_fold"]], select_encoder(encoder, names),
        ["sparse_noise"], make_cfg(), 1,
    ).set_index("feature")  # fmt: skip
    assert pruned.loc["sparse_noise", "outcome"] == "protected"


@pytest.mark.parametrize("task", list(TASKS))
def test_pruning_drops_what_the_best_noise_column_beats(
    task: str, panels: dict, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """A rarely-set flag does no better than the best noise column and is dropped; the rows name
    the frame's features only, each against the one best noise share."""
    train, X, encoder = panels[PANEL_OF[task]]
    names = ["strong", "u_shape", "sparse_noise"]
    rows = prune_by_importance(
        X[names], train["target"].to_numpy(), train[["cv_fold"]], select_encoder(encoder, names),
        [], make_cfg(task=task), 1,
    )  # fmt: skip
    assert rows["feature"].tolist() == names
    assert rows["outcome"].tolist() == ["passed", "passed", "dropped"]
    assert rows["threshold"].nunique() == 1
    assert rows["value"].iloc[2] <= rows["threshold"].iloc[0] < rows["value"].iloc[0]


RARE_NAMES = [*(f"w{i}" for i in range(7)), "rare"]


def _rare_frame(task: str, effect: float) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """1,500 clients over four periods: seven real numerics (one strong, six weak) and `rare`, a
    flag set on 0.5% of the rows that moves the log-odds by `effect` (0: pure noise); the binary
    target, or for regression that target times a lognormal amount. Returns the frame with its
    target and `cv_fold`, the encoded frame and its encoder."""
    rng = np.random.default_rng(SEED)
    unit = np.repeat(np.arange(1500), 4)
    real = rng.normal(size=(unit.size, 7))
    rare = (rng.random(unit.size) < 0.005).astype(float)
    logit = -1.5 + real @ np.array([1.2] + [0.3] * 6) + effect * rare
    target = (rng.random(unit.size) < 1 / (1 + np.exp(-logit))).astype(int)
    if PANEL_OF[task] == "regression":
        target = target * np.exp(1.0 + 0.3 * real[:, 0])
    X = pd.DataFrame(real, columns=RARE_NAMES[:7]).assign(rare=rare)
    encoder = {"schema_version": 1, "unordered": "native", "min_level_client_count": 2,
               "features": [{"name": name, "kind": "numeric"} for name in RARE_NAMES]}  # fmt: skip
    return X.assign(target=target, cv_fold=unit % 5), X, encoder


def _recorded_pruning(
    task: str, effect: float, make_cfg: Callable[..., UseCaseConfig], patch: pytest.MonkeyPatch
) -> tuple[list[str], pd.DataFrame, list[float]]:
    """`prune_features` on `_rare_frame(task, effect)` with every rule but pruning off, and the
    fold losses it computed, in order, recorded around the real `out_of_fold_loss`."""
    losses: list[float] = []

    def recording_loss(*arguments: object) -> float:
        """The real fold loss, recorded."""
        losses.append(out_of_fold_loss(*arguments))
        return losses[-1]

    patch.setattr(selection, "out_of_fold_loss", recording_loss)
    cfg = make_cfg(task=task, cluster=False, floor_z=None, prune=True)
    final, table = prune_features(*_rare_frame(task, effect), RARE_NAMES, cfg, 1)
    return final, table, losses


@pytest.mark.parametrize("task", list(TASKS))
def test_pruning_is_undone_when_the_loss_rises(
    task: str, make_cfg: Callable[..., UseCaseConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flag on 0.5% of the rows that triples the odds has a contribution share no higher than
    the best noise column's, so it is a candidate; the fit without it scores a higher fold loss
    than the fit with it, both without the noise columns, so nothing is pruned: the candidate is
    `undone` and stays in the final list."""
    final, table, losses = _recorded_pruning(task, 3.0, make_cfg, monkeypatch)
    rare = table.set_index("feature").loc["rare"]
    assert rare["value"] <= rare["threshold"]
    assert table.loc[table["outcome"] == "undone", "feature"].tolist() == ["rare"]
    assert set(table["outcome"]) == {"passed", "undone"}
    assert final == RARE_NAMES
    assert len(losses) == 3 and losses[2] > losses[1]  # with noise, with and without the flag


@pytest.mark.parametrize("task", list(TASKS))
def test_a_pure_noise_candidate_is_dropped_not_undone(
    task: str, make_cfg: Callable[..., UseCaseConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same flag without any effect is a candidate too, and leaving it out must not raise
    the fold loss: the drop stands. The undo check compares the fits with and without the
    candidates, so it must compare like with like; a rise that a noise column's removal causes
    would undo every drop."""
    final, table, losses = _recorded_pruning(task, 0.0, make_cfg, monkeypatch)
    rare = table.set_index("feature").loc["rare"]
    assert rare["value"] <= rare["threshold"]
    assert len(losses) == 3
    assert rare["outcome"] == "dropped", f"fold losses with noise, with and without: {losses}"
    assert final == RARE_NAMES[:7]


def test_bad_inputs_and_an_emptied_list_fail_loud(
    data: tuple, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """A train row without a client fold is refused, and a rule of the screen that drops every
    feature names itself: the screen fits no model, so Training refuses there, before it takes
    a run number (the end-to-end check is `test_training.py`'s)."""
    train, X, encoder = data
    unfolded = train.assign(cv_fold=train["cv_fold"].astype("Int64").mask(train.index == 0))
    with pytest.raises(ValueError, match="cv_fold"):
        train_statistics(unfolded, X, encoder, make_cfg())
    with pytest.raises(ValueError, match="the floor rule left no feature"):
        screen_features(*data, STAGE2, make_cfg(floor_z=50.0))


def test_select_features_returns_the_encoders_order_without_noise(
    data: tuple, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """Every rule on: the final features keep the encoder's order, a kept feature stays, and no
    noise column appears in any returned table."""
    cfg = make_cfg(kept=["noise"], cluster=True, floor_z=2.0, prune=True)
    screened, _, _ = encode_and_screen(data[0], data[2], STAGE2, cfg)
    selected, _, _ = finish_selection(data[0], data[2], screened, cfg, 1)
    final, table, statistics = list(selected.X.columns), selected.selection, selected.statistics
    assert final == [name for name in FEATURES if name in final]
    assert "noise" in final and "strong_copy" not in final
    returned = {*final, *table["feature"], *statistics["feature"]}
    assert not returned & set(NOISE_COLUMNS)
    assert set(table["rule"]) == {"cluster", "floor", "prune"}


def test_a_nan_statistic_never_clears_the_floor() -> None:
    """A concordance or an SE that came out NaN without a reason is no evidence: the feature is
    dropped, never passed by a comparison with NaN."""
    statistics = pd.DataFrame(
        {"feature": ["nan_value", "nan_se"], "value": [np.nan, 0.9], "se": [0.01, np.nan],
         "unavailable": ["", ""], "non_monotone": [False, False],
         "null_concordance": [np.nan, np.nan], "null_se": [np.nan, np.nan],
         "null_pattern": ["a", "b"]}
    )  # fmt: skip
    rows = apply_floor(statistics, ["nan_value", "nan_se"], [], 2.0)
    assert rows["outcome"].tolist() == ["dropped", "dropped"]
    assert rows["cleared_by"].isna().all()


def test_the_undo_check_caps_the_yardsticks_tree_count() -> None:
    """The undo check's fits offer every column to every tree at the yardstick's tree count up
    to `COMPARISON_TREES`: unchanged on a narrow frame, capped on a wide one."""
    narrow, wide = selection._pruning_configuration(20), selection._pruning_configuration(400)
    assert narrow["n_estimators"] < selection.COMPARISON_TREES < wide["n_estimators"]
    for yardstick, trees in ((narrow, narrow["n_estimators"]), (wide, selection.COMPARISON_TREES)):
        comparison = selection._comparison_configuration(yardstick)
        assert comparison == {**yardstick, "colsample_bytree": 1.0, "n_estimators": trees}


def _wide_frame(rows: int = 30000, weak: int = 47) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """One row per client, a 15% event rate, three strong features (single-feature AUC 0.65)
    and `weak` weak ones (0.53), each drawn given the target as N(mu · y, 1) and so each
    carrying signal of its own; the client folds by row."""
    rng = np.random.default_rng(0)
    aucs = [0.65] * 3 + [0.53] * weak
    names = [f"strong_{i}" for i in range(3)] + [f"weak_{i}" for i in range(weak)]
    y = (rng.random(rows) < 0.15).astype(int)
    shift = np.outer(y, np.sqrt(2) * norm.ppf(aucs))
    X = pd.DataFrame(rng.standard_normal((rows, len(aucs))) + shift, columns=names)
    return X, y, pd.DataFrame({"cv_fold": np.arange(rows) % 5})


def test_pruning_on_a_wide_frame_compares_with_noise_and_keeps_every_real_feature(
    make_cfg: Callable[..., UseCaseConfig],
) -> None:
    """With more columns than the search's start model can split, its noise columns got no
    split and every unsplit real feature was dropped. The pruning model sized to the frame
    offers each column to about ten trees: the noise columns get splits, so the features are
    compared with noise, and none of the fifty real features is pruned."""
    X, y, folds = _wide_frame()
    names = list(X.columns)
    encoder = {"schema_version": 1, "unordered": "native", "min_level_client_count": 2,
               "features": [{"name": name, "kind": "numeric"} for name in names]}  # fmt: skip
    rows = prune_by_importance(X, y, folds, encoder, [], make_cfg(), 1)
    assert (rows["threshold"] > 0).all()
    assert rows["outcome"].eq("passed").all()


def test_a_best_noise_share_of_zero_prunes_nothing_and_warns(
    data: tuple, make_cfg: Callable[..., UseCaseConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no noise column got a split, nothing was compared with noise: a feature without a
    split either is not pruned, every `prune` row passes at a threshold of 0, and the run's
    warnings say so."""

    def without_noise_splits(*arguments: object) -> tuple[np.ndarray, np.ndarray]:
        """The fold models, with no contribution from the noise columns nor `sparse_noise`."""
        margins, parts = fit_fold_models(*arguments)
        columns = list(arguments[0].columns)
        unsplit = [columns.index(n) for n in [*NOISE_COLUMNS, "sparse_noise"] if n in columns]
        parts[:, unsplit] = 0.0
        return margins, parts

    monkeypatch.setattr(selection, "fit_fold_models", without_noise_splits)
    cfg = make_cfg(cluster=False, floor_z=None, prune=True)
    screened, _, _ = encode_and_screen(data[0], data[2], STAGE2, cfg)
    selected, _, notes = finish_selection(data[0], data[2], screened, cfg, 1)
    pruned = selected.selection
    assert list(selected.X.columns) == FEATURES
    assert pruned["outcome"].eq("passed").all() and pruned["threshold"].eq(0).all()
    assert any("no noise column got a split" in note for note in notes)


def _null_panel() -> pd.DataFrame:
    """1,500 clients over three periods: a strong numeric, and `nully`, filled for 40% of the
    clients with pure-noise values; a filled client's log-odds are 1 higher."""
    rng = np.random.default_rng(0)
    clients, periods = 1500, 3
    unit = np.repeat(np.arange(clients), periods)
    filled = (rng.random(clients) < 0.4)[unit]
    strong = rng.normal(size=unit.size)
    logit = -2.0 + strong + 1.0 * filled
    dates = pd.date_range("2024-01-01", periods=periods, freq="MS").date
    return pd.DataFrame(
        {
            "unit_id": unit,
            "period": np.tile(dates, clients),
            "strong": strong,
            "nully": np.where(filled, rng.normal(size=unit.size), np.nan),
            "target": (rng.random(unit.size) < 1 / (1 + np.exp(-logit))).astype(int),
            "cv_fold": unit % 5,
        }
    )


@pytest.mark.parametrize("family", FAMILIES)
def test_a_feature_whose_nulls_predict_the_target_passes_the_floor(
    family: str, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """The floor read the value's concordance on the known rows only and dropped a feature
    whose being filled predicts the target. It now passes on its null indicator's concordance,
    against a threshold on that statistic's own SE, and the row says so; a feature without
    nulls has no null concordance. Every family takes nulls natively and gains from it: the
    fold models' loss on grouped folds is lower with the feature than without."""
    train = _null_panel()
    names = ["strong", "nully"]
    encoder = fit_encoder(train, names, dict.fromkeys(names, "numeric"), {}, 2, "native")
    X = encode_frame(train, encoder)[0]
    statistics = train_statistics(train, X, encoder, make_cfg())
    assert np.isnan(statistics.set_index("feature").loc["strong", "null_concordance"])
    floor = apply_floor(statistics, names, [], 2.0).set_index("feature").loc["nully"]
    value = statistics.set_index("feature").loc["nully"]
    assert value["value"] < 0.5 + 2.0 * value["se"]  # the value alone would be dropped
    assert (floor["outcome"], floor["cleared_by"]) == ("passed", "null_concordance")
    assert floor["value"] == value["null_concordance"] >= floor["threshold"]
    y, folds = train["target"].to_numpy(), train[["cv_fold"]]
    losses = []
    for columns in (["strong"], names):
        chosen = select_encoder(encoder, columns)
        fixed = FAMILIES[family].fixed_params("binary", "log_loss", chosen, {}, SEED, 1, None)
        margins, _ = fit_fold_models(
            X[columns], y, folds, family, {**fixed, **SMALL_FITS[family]}, "binary"
        )
        fold = folds["cv_fold"].to_numpy()
        losses.append(
            out_of_fold_loss("log_loss", y, margins, fold, uncalibrated("log_loss"), "binary")
        )
    assert losses[1] < losses[0] - 0.005


def _floor_rows(
    train: pd.DataFrame, names: list[str], cfg: UseCaseConfig, kept: list[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The train statistics of the numerics `names` and the floor's rows at z = 2, both by
    feature."""
    encoder = fit_encoder(train, names, dict.fromkeys(names, "numeric"), {}, 2, "native")
    statistics = train_statistics(train, encode_frame(train, encoder)[0], encoder, cfg)
    rows = apply_floor(statistics, names, kept or [], 2.0)
    return statistics.set_index("feature"), rows.set_index("feature")


def test_a_shared_null_pattern_clears_one_feature_not_all(
    make_cfg: Callable[..., UseCaseConfig],
) -> None:
    """Three noise features null on the same rows, whose being filled predicts the target, share
    one null indicator: the one with the highest value passes on it, the other two are dropped
    naming it, and a kept one is protected. Each alone would have passed."""
    train = _null_panel()
    train = train.assign(nully_b=train["nully"] * 0.5 + np.random.default_rng(1).normal(
        size=len(train)), nully_c=-train["nully"])  # fmt: skip
    train[["nully_b", "nully_c"]] = train[["nully_b", "nully_c"]].where(train["nully"].notna())
    names = ["nully", "nully_b", "nully_c"]
    statistics, rows = _floor_rows(train, names, make_cfg())
    assert statistics["null_pattern"].nunique() == 1
    carrier = max(names, key=lambda name: statistics.loc[name, "value"])
    assert rows.loc[carrier, "cleared_by"] == "null_concordance"
    others = [name for name in names if name != carrier]
    assert (rows.loc[others, "outcome"] == "dropped").all()
    assert (rows.loc[others, "represented_by"] == carrier).all()
    _, kept_rows = _floor_rows(train, names, make_cfg(), kept=others[:1])
    assert kept_rows.loc[others[0], "outcome"] == "protected"
    assert kept_rows.loc[others[1], "represented_by"] == carrier


def test_a_pattern_whose_group_passes_on_a_value_clears_nobody_else(
    make_cfg: Callable[..., UseCaseConfig],
) -> None:
    """When a member of the null pattern passes on its value, the pattern is in the model
    through it: a noise member null on the same rows is dropped, naming that member."""
    train = _null_panel()
    train["signal"] = train["strong"].where(train["nully"].notna())
    _, rows = _floor_rows(train, ["signal", "nully"], make_cfg())
    assert (rows.loc["signal", "outcome"], rows.loc["signal", "cleared_by"]) == (
        "passed", "concordance"
    )  # fmt: skip
    assert (rows.loc["nully", "outcome"], rows.loc["nully", "represented_by"]) == (
        "dropped", "signal"
    )  # fmt: skip


def _rare_null_frame(effect: float, seed: int) -> pd.DataFrame:
    """3,000 clients in one period, about 15% events: `rare` is noise, null on 1% of the rows,
    whose log-odds are `effect` higher."""
    rng = np.random.default_rng(seed)
    rows = 3000
    null = rng.random(rows) < 0.01
    logit = -1.7 + effect * null
    return pd.DataFrame(
        {
            "unit_id": np.arange(rows),
            "period": pd.Timestamp("2024-01-01").date(),
            "rare": np.where(null, np.nan, rng.normal(size=rows)),
            "target": (rng.random(rows) < 1 / (1 + np.exp(-logit))).astype(int),
            "cv_fold": np.arange(rows) % 5,
        }
    )


def test_a_rare_null_pattern_with_a_real_signal_passes_on_the_tie_corrected_se(
    make_cfg: Callable[..., UseCaseConfig],
) -> None:
    """A null indicator is two-valued, so its concordance's SE carries the tie correction
    `sqrt(3·p·(1 − p))`; without it, at 1% nulls, the SE was about six times too large (here
    it is floored at `SE_FLOOR`) and a real null signal was dropped. A noise feature with
    random nulls stays dropped."""
    train = _rare_null_frame(2.0, 0)
    statistics, rows = _floor_rows(train, ["rare"], make_cfg())
    row, events = statistics.loc["rare"], int(train["target"].sum())
    former = 0.5 + 2.0 * concordance_se(row["null_concordance"], events, len(train) - events)
    assert row["null_concordance"] < former  # the uncorrected SE would have dropped it
    assert (rows.loc["rare", "outcome"], rows.loc["rare", "cleared_by"]) == (
        "passed", "null_concordance"
    )  # fmt: skip
    noise = _null_panel().assign(nully=lambda f: f["nully"].sample(frac=1, random_state=0).values)
    _, rows = _floor_rows(noise, ["nully"], make_cfg())
    assert rows.loc["nully", "outcome"] == "dropped"


def test_catboosts_null_note_names_final_features_only(
    data: tuple, variant: Callable[..., UseCaseConfig]
) -> None:
    """The note on constrained features with nulls under CatBoost names the features the model
    is trained on: a constrained feature the floor dropped is left out of it."""
    train = data[0].assign(
        strong=data[0]["strong"].mask(data[0].index % 10 == 0),
        noise=data[0]["noise"].mask(data[0].index % 10 == 1),
    )
    names = ["strong", "noise"]
    encoder = fit_encoder(train, names, dict.fromkeys(names, "numeric"), {}, 2, "native")
    cfg = variant(
        training={
            "estimator_list": ["lgbm", "catboost"],
            "monotone": {"strong": "increasing", "noise": "increasing"},
            "selection": {"cluster": False, "floor_z": 2.0, "prune": False},
        }
    )
    screened, _, screen_notes = encode_and_screen(train, encoder, STAGE2, cfg)
    _, _, notes = finish_selection(train, encoder, screened, cfg, 1)
    assert screened.features == ["strong"]
    catboost = [note for note in [*screen_notes, *notes] if "catboost is searched" in note]
    assert len(catboost) == 1 and "['strong']" in catboost[0]
