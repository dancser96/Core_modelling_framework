"""Permutation importance per redundancy cluster (evaluation.md → "The explanation tables").

It runs on its own seeded sample of the test part, `PERMUTATION_ROWS` rows of the features and
the target drawn by the hash the explanation sample is drawn by (`explain.py` collects both in
one pass), since every cluster is scored again `PERMUTATIONS` times on the driver and the
explanation sample's 5,000 rows hold too few events at a rare rate. Whether it can run is
decided before it runs (`permutation_unavailable`, D-035), so nothing fails mid-permutation.
The rank check sets its order beside the explanation sample's contribution shares. Nothing is
fitted and nothing is chosen on these numbers (`CLAUDE.md` §4.4).
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import DEVIANCE_METRICS, LOG_LINK_OBJECTIVES
from core_modelling.model.bundle import Bundle
from core_modelling.model.scoring import score_frame
from core_modelling.tasks import TASK_SPECS

PERMUTATION_ROWS = 50_000  # the permutation sample: this many seeded test rows, or every row
PERMUTATIONS = 5  # seeded permutations per cluster: the loss change is their mean
DISAGREEMENTS = 3  # the clusters whose two ranks differ most, marked for the rank check
PERMUTATION_COLUMNS = ["cluster", "members", "loss_change", "loss_change_sd",
                       "contribution_share", "importance_rank", "contribution_rank", "rank_gap",
                       "disagrees", "rank_correlation"]  # fmt: skip
ONE_TARGET_VALUE = "one target value in the permutation sample"


def permutation_unavailable(sample: pd.DataFrame, cfg: UseCaseConfig, objective: str) -> str | None:
    """Why permutation importance cannot be computed on the permutation sample (its `target`),
    decided before it runs (D-035); None when it can. The reason is bare: the view adds "Not
    available: ".

    - fewer events (the task's `events_noun`: positive rows, or rows with a non-zero target)
      than `strata.min_events`, the count named: a handful of rows would drive every change.
      A regression target without zeros makes every row an event, so the minimum is then
      vacuous;
    - a target of one value gives no loss to compare;
    - a deviance metric under the run's `objective` without a log link: a permuted row's
      prediction can be zero or negative, where the deviance is undefined.
    """
    target = sample["target"]
    events, floor = int((target != 0).sum()), cfg.strata.min_events
    if events < floor:
        noun = TASK_SPECS[cfg.task]["events_noun"]
        return (f"{events} {noun} in the permutation sample of {len(sample):,} rows, fewer "
                f"than strata.min_events ({floor})")  # fmt: skip
    if target.nunique() < 2:
        return ONE_TARGET_VALUE
    metric = cfg.decision.metric
    if metric in DEVIANCE_METRICS and objective not in LOG_LINK_OBJECTIVES:
        return (f"the {metric} needs positive predictions, which the run's {objective!r} "
                "objective does not guarantee on permuted rows")  # fmt: skip
    return None


def permutation_importance(
    bundle: Bundle,
    sample: pd.DataFrame,
    clusters: pd.DataFrame,
    shares: pd.Series,
    metric: Callable[[np.ndarray, np.ndarray], float],
    seed: int,
) -> pd.DataFrame:
    """Per redundancy cluster, the loss change when its members are permuted together, the mean
    over `PERMUTATIONS` seeded permutations of the sample's rows, and the rank check against
    the contribution shares. Run it only when `permutation_unavailable` gives no reason.

    `sample` is the permutation sample (the bundle's features and `target`), `clusters` holds
    `feature, cluster` (the Stage 2 ledger's; a null cluster is the feature alone), `shares`
    each feature's contribution share (the feature table's, on the explanation sample) and
    `metric(y, score)` a loss (lower is better). Returns one row per cluster, largest mean loss
    change first, in `PERMUTATION_COLUMNS`: `loss_change` the mean and `loss_change_sd` the
    standard deviation (ddof 1) over the permutations, the ranks and `disagrees` (the
    `DISAGREEMENTS` largest non-zero gaps) on the mean, and `rank_correlation` (Spearman's
    between the two, the same on every row; null when undefined).
    """
    groups = _cluster_members(bundle.features, clusters)
    y = sample["target"].to_numpy()
    frame = sample[bundle.features]
    base = metric(y, score_frame(bundle, frame)["score"].to_numpy())
    rng = np.random.default_rng(seed)
    rows = []
    for cluster, members in groups:
        changes = [_permuted_loss(bundle, frame, members, rng.permutation(len(frame)), y, metric)
                   - base for _ in range(PERMUTATIONS)]  # fmt: skip
        rows.append({"cluster": cluster, "members": members,
                     "loss_change": float(np.mean(changes)),
                     "loss_change_sd": float(np.std(changes, ddof=1)),
                     "contribution_share": float(shares[members].sum())})  # fmt: skip
    table = pd.DataFrame(rows).astype({"cluster": "Int64"})
    return _rank_check(table)[PERMUTATION_COLUMNS]


def _permuted_loss(
    bundle: Bundle,
    frame: pd.DataFrame,
    members: list[str],
    order: np.ndarray,
    y: np.ndarray,
    metric: Callable[[np.ndarray, np.ndarray], float],
) -> float:
    """The loss with `members`' values reordered by `order`, one order for every member, so
    their rows move together and the other features stay in place."""
    permuted = frame.copy()
    for name in members:
        permuted[name] = frame[name].to_numpy()[order]
    return metric(y, score_frame(bundle, permuted)["score"].to_numpy())


def _cluster_members(
    features: list[str], clusters: pd.DataFrame
) -> list[tuple[int | None, list[str]]]:
    """The model's features grouped by their cluster, in the features' order: `(cluster,
    members)`, a feature with a null cluster alone under None; a feature without a row fails."""
    known = clusters.set_index("feature")["cluster"]
    missing = [name for name in features if name not in known.index]
    if missing:
        raise ValueError(f"the clusters table has no row for the model's features {missing}")
    groups: dict[int | str, list[str]] = {}
    for name in features:
        key = name if pd.isna(known[name]) else int(known[name])  # alone: keyed by its name
        groups.setdefault(key, []).append(name)
    return [(None if isinstance(key, str) else key, members) for key, members in groups.items()]


def _rank_check(table: pd.DataFrame) -> pd.DataFrame:
    """The permutation table with both ranks, their gap, the largest gaps marked and Spearman's
    rank correlation between the loss change and the contribution share."""
    table["importance_rank"] = table["loss_change"].rank(ascending=False, method="min")
    table["contribution_rank"] = table["contribution_share"].rank(ascending=False, method="min")
    table = table.astype({"importance_rank": "int64", "contribution_rank": "int64"})
    table["rank_gap"] = table["importance_rank"] - table["contribution_rank"]
    gap = table["rank_gap"].abs()
    largest = gap[gap > 0].sort_values(ascending=False, kind="stable").index[:DISAGREEMENTS]
    table["disagrees"] = table.index.isin(largest)
    correlation = table["loss_change"].corr(table["contribution_share"], method="spearman")
    table["rank_correlation"] = None if pd.isna(correlation) else float(correlation)
    return table.sort_values("loss_change", ascending=False, kind="stable").reset_index(drop=True)
