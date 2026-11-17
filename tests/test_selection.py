"""Training's train-split statistics and its three selection rules on a constructed panel (no
Spark): clients over several periods with their `cv_fold`, a strong numeric and a noisy copy of
it in one Stage 2 cluster, a U-shaped numeric, pure noise, a rarely-set noise flag, a
high-cardinality noise level column and an ordered categorical."""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from core_modelling.config import UseCaseConfig
from core_modelling.model.encoder import encode_frame, fit_encoder, select_encoder
from core_modelling.training import selection
from core_modelling.training.selection import (
    NOISE_COLUMNS,
    apply_cluster_rule,
    apply_floor,
    prune_by_importance,
    select_features,
)
from core_modelling.training.train_statistics import train_statistics

CLIENTS, PERIODS, SEED = 1200, 4, 3
NUMERICS = ["strong", "strong_copy", "u_shape", "noise", "sparse_noise"]
KINDS = {**dict.fromkeys(NUMERICS, "numeric"), "level_noise": "categorical", "tier": "categorical"}
FEATURES = list(KINDS)
TIERS = ["low", "mid", "high"]
START = {"n_estimators": 50, "num_leaves": 4, "learning_rate": 0.1}
STAGE2 = pd.DataFrame(
    {
        "feature": FEATURES,
        "kind": list(KINDS.values()),
        "non_monotone": [False, False, True, False, False, False, False],
        "cluster": pd.array([1, 1, None, None, None, None, None], dtype="Int64"),
    }
)


def _panel() -> pd.DataFrame:
    """One row per client and period, the client's fold its id modulo 5: the target rises with
    `strong` and with `u_shape`'s distance from 0; every other column is noise but `tier`."""
    rng = np.random.default_rng(SEED)
    unit = np.repeat(np.arange(CLIENTS), PERIODS)
    n = unit.size
    strong, u_shape = rng.normal(size=n), rng.normal(size=n)
    logit = -1.0 + 1.5 * strong + 1.2 * (u_shape**2 - 1)
    levels = np.array([f"L{i}" for i in range(300)])[rng.integers(0, 300, CLIENTS)]
    return pd.DataFrame(
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


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The panel, its encoded frame and the encoder (levels kept from two clients)."""
    train = _panel()
    encoder = fit_encoder(train, FEATURES, KINDS, {"tier": TIERS}, 2, "native")
    return train, encode_frame(train, encoder)[0], encoder


@pytest.fixture(scope="module")
def make_cfg(variant: Callable[..., UseCaseConfig]) -> Callable[..., UseCaseConfig]:
    """The card config with the selection switches and the kept features given."""

    def make(kept: list[str] | None = None, **rules: object) -> UseCaseConfig:
        """The variant, validated."""
        return variant(training={"selection": rules}, features={"kept": kept or []})

    return make


@pytest.fixture(scope="module")
def stats(data: tuple, make_cfg: Callable[..., UseCaseConfig]) -> pd.DataFrame:
    """The train statistics of the panel, indexed by feature."""
    return train_statistics(*data, make_cfg()).set_index("feature")


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


def test_the_floor_reads_the_best_order_for_a_non_monotone_feature(
    data: tuple, stats: pd.DataFrame, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """A U-shaped signal passes the floor on its best-order concordance (A10); its plain one
    would drop it. Whether a feature is non-monotone is decided on the train rows by EDA's
    rule, never from Stage 2's mark, which has seen test labels (§4.4): the statistics take no
    Stage 2 input, mark the U shape themselves and judge plain noise on its plain concordance."""
    marked = apply_floor(stats.reset_index(), ["u_shape"], [], 2.0).iloc[0]
    assert stats.loc["u_shape", "non_monotone"]
    assert marked["value"] == stats.loc["u_shape", "concordance_best_order"]
    assert marked["outcome"] == "passed"
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
    final, table, _ = select_features(*data, STAGE2, cfg, START, 1)
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
    """Each rule shows a kept feature's value and marks it `protected` where it would drop it
    (A8); the cluster's representative is still chosen with it in the comparison."""
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
        ["sparse_noise"], START, make_cfg(), 1,
    ).set_index("feature")  # fmt: skip
    assert pruned.loc["sparse_noise", "outcome"] == "protected"


def test_pruning_drops_what_the_best_noise_column_beats(
    data: tuple, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """A rarely-set flag does no better than the best noise column and is dropped; the rows name
    the frame's features only, each against the one best noise share."""
    train, X, encoder = data
    names = ["strong", "u_shape", "sparse_noise"]
    rows = prune_by_importance(
        X[names], train["target"].to_numpy(), train[["cv_fold"]], select_encoder(encoder, names),
        [], START, make_cfg(), 1,
    )  # fmt: skip
    assert rows["feature"].tolist() == names
    assert rows["outcome"].tolist() == ["passed", "passed", "dropped"]
    assert rows["threshold"].nunique() == 1
    assert rows["value"].iloc[2] <= rows["threshold"].iloc[0] < rows["value"].iloc[0]


def test_pruning_is_undone_when_the_loss_rises(
    data: tuple, make_cfg: Callable[..., UseCaseConfig], monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the fit without the candidates scores a higher fold loss than the fit with them,
    both without the noise columns, nothing is pruned: the candidates are `undone` and stay in
    the final list."""
    losses = iter([0.0, 0.10, 0.20])  # the fit with noise, then with and without the candidates
    monkeypatch.setattr(selection, "mean_fold_loss", lambda *args: next(losses))
    cfg = make_cfg(cluster=False, floor_z=None, prune=True)
    final, table, _ = select_features(*data, STAGE2, cfg, START, 1)
    undone = table.loc[table["outcome"] == "undone", "feature"].tolist()
    assert "sparse_noise" in undone
    assert set(table["outcome"]) == {"passed", "undone"}
    assert final == FEATURES
    assert next(losses, None) is None  # all three fits ran


def test_bad_inputs_and_an_emptied_list_fail_loud(
    data: tuple, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """A train row without a client fold is refused, and a rule that drops every feature names
    itself before pruning could fit on the noise columns alone."""
    train, X, encoder = data
    unfolded = train.assign(cv_fold=train["cv_fold"].astype("Int64").mask(train.index == 0))
    with pytest.raises(ValueError, match="cv_fold"):
        train_statistics(unfolded, X, encoder, make_cfg())
    with pytest.raises(ValueError, match="the floor rule left no feature"):
        select_features(*data, STAGE2, make_cfg(floor_z=50.0), START, 1)


def test_select_features_returns_the_encoders_order_without_noise(
    data: tuple, make_cfg: Callable[..., UseCaseConfig]
) -> None:
    """Every rule on: the final features keep the encoder's order, a kept feature stays, and no
    noise column appears in any returned table."""
    cfg = make_cfg(kept=["noise"], cluster=True, floor_z=2.0, prune=True)
    final, table, statistics = select_features(*data, STAGE2, cfg, START, 1)
    assert final == [name for name in FEATURES if name in final]
    assert "noise" in final and "strong_copy" not in final
    returned = {*final, *table["feature"], *statistics["feature"]}
    assert not returned & set(NOISE_COLUMNS)
    assert set(table["rule"]) == {"cluster", "floor", "prune"}
