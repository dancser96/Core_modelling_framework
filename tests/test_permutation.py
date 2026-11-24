"""Permutation importance on its own sample: whether it runs is decided before it runs (the event
minimum with the count, one target value, a deviance under an objective without a log link), a
cluster is permuted as one, an ignored feature has no importance, and every scoring reads the
permutation sample, never the explanation sample the shares come from (no Spark).
"""

from collections.abc import Callable
from functools import partial
from pathlib import Path

import pandas as pd
import pytest
from test_explain import FEATURES, _bundle, _sample

from core_modelling.config import UseCaseConfig
from core_modelling.evaluation import permutation
from core_modelling.evaluation.explain import compute_contributions, contribution_shares
from core_modelling.evaluation.permutation import (
    ONE_TARGET_VALUE,
    PERMUTATION_COLUMNS,
    PERMUTATIONS,
    _cluster_members,
    permutation_importance,
    permutation_unavailable,
)
from core_modelling.model import score_frame
from core_modelling.model.bundle import Bundle
from core_modelling.statistics.losses import metric_loss


def test_below_the_event_minimum_it_is_not_available_with_the_count(
    cc_config: UseCaseConfig,
) -> None:
    """Fewer events than `strata.min_events` in the permutation sample: not available, the count
    and the floor named in the task's words (binary: positive rows); at the floor it runs; one
    target value has its own reason."""
    floor = cc_config.strata.min_events
    few = pd.DataFrame({"target": [1] * (floor - 1) + [0] * 500})
    expected = (f"{floor - 1} positive rows in the permutation sample of {floor + 499:,} rows, "
                f"fewer than strata.min_events ({floor})")  # fmt: skip
    assert permutation_unavailable(few, cc_config, "binary") == expected
    enough = pd.DataFrame({"target": [1] * floor + [0] * 500})
    assert permutation_unavailable(enough, cc_config, "binary") is None
    positives = pd.DataFrame({"target": [1] * (floor + 5)})
    assert permutation_unavailable(positives, cc_config, "binary") == ONE_TARGET_VALUE


def test_a_feature_without_a_clusters_row_is_refused() -> None:
    """Members are grouped by the clusters table, a null cluster alone; a model feature the
    table has no row for fails, naming it, rather than being left unpermuted."""
    clusters = pd.DataFrame({"feature": ["income", "age"],
                             "cluster": pd.array([4, 4], dtype="Int64")})  # fmt: skip
    assert _cluster_members(["income", "age"], clusters) == [(4, ["income", "age"])]
    with pytest.raises(ValueError, match=r"no row for the model's features \['flat'\]"):
        _cluster_members(["income", "flat", "age"], clusters)


def test_a_deviance_without_a_log_link_is_not_available(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A deviance metric needs positive predictions: under the run's log-link objective it runs,
    under one without a log link (a run trained under another config) it is declared up front."""
    cfg = variant(task="regression", decision={"metric": "tweedie_deviance"},
                  training={"objective": "tweedie"})  # fmt: skip
    sample = pd.DataFrame({"target": [0.0, 2.5] * cfg.strata.min_events})
    assert permutation_unavailable(sample, cfg, "tweedie") is None
    reason = permutation_unavailable(sample, cfg, "regression")
    assert reason is not None and "positive predictions" in reason and "'regression'" in reason


def test_a_cluster_is_permuted_as_one_on_its_own_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`income` and `age` share a cluster: one permutation moves their rows together and leaves
    the other features in place; each cluster is permuted `PERMUTATIONS` times, every scoring on
    the 400 rows of the permutation sample, while the shares come from a 100-row explanation
    sample; `flat`, which the model ignores, changes no loss."""
    bundle = _bundle(tmp_path)
    sample = _sample(bundle, rows=400)
    shares = contribution_shares(compute_contributions(bundle, _sample(bundle, 100)), FEATURES)
    clusters = pd.DataFrame(
        {"feature": FEATURES, "cluster": pd.array([4, None, None, None, 4], dtype="Int64")}
    )
    scored = []

    def spy(bundle: Bundle, frame: pd.DataFrame) -> pd.DataFrame:
        """The real `score_frame`, keeping each frame it scores."""
        scored.append(frame)
        return score_frame(bundle, frame)

    monkeypatch.setattr(permutation, "score_frame", spy)
    loss = partial(metric_loss, "log_loss")
    table = permutation_importance(bundle, sample, clusters, shares, loss, seed=5)
    original, permuted = scored[0], scored[1]  # the base, then the first cluster: income and age
    pairs = original.dropna(subset=["income"]).set_index("income")["age"]
    known = permuted["income"].notna()
    assert (permuted.loc[known, "age"] == permuted.loc[known, "income"].map(pairs)).all()
    assert not permuted["income"].equals(original["income"])
    assert permuted[["flat", "channel", "rating"]].equals(original[["flat", "channel", "rating"]])
    assert {len(frame) for frame in scored} == {400}
    by_members = table.set_index(table["members"].map(", ".join))
    assert by_members.loc["income, age", "cluster"] == 4
    assert by_members.loc["income, age", "contribution_share"] == pytest.approx(
        shares["income"] + shares["age"]
    )
    assert by_members.loc["flat", "loss_change"] == 0.0
    assert by_members.loc["flat", "loss_change_sd"] == 0.0
    assert list(table.columns) == PERMUTATION_COLUMNS
    assert len(scored) == 1 + PERMUTATIONS * len(table)
