"""Training's automated feature selection: three rules in a fixed order, on the train split only
(`docs/components/training.md` → Selection, D-140 (e), `CLAUDE.md` §4.4).

Selection runs in two parts. `screen_features`, the model-free part, reads `train_statistics`
and runs the cluster rule and the floor; Training calls it before it takes a run number, so a
screen that leaves no feature refuses without one. `prune_features` runs importance pruning
after it: LightGBM fold models beside five seeded noise columns, whatever families are searched,
sized to the frame so every column is offered to about ten trees; no noise column leaves it.
Each rule is switched by `training.selection`, and a feature one rule drops is not judged by the
later ones. Each rule returns one row per feature it judged (`RULE_COLUMNS`); the rows stacked
are Training's `selection` table, and the per-run ledger reads them: the one record of a drop
(D-125). A person's `keep` is measured by every rule and dropped by none (`protected`).
"""

import math

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.model.calibration import uncalibrated
from core_modelling.model.encoder import select_encoder
from core_modelling.model.families import FAMILIES
from core_modelling.model.family_inputs import check_order
from core_modelling.training.fold_models import FOLD_COLUMN, fit_fold_models, out_of_fold_loss
from core_modelling.training.train_statistics import train_statistics

# `cleared_by`: on a floor row that passed, the statistic that cleared the threshold
RULE_COLUMNS = ["feature", "rule", "value", "threshold", "outcome", "represented_by", "cleared_by"]
NOISE_COLUMNS = [f"__noise_{i}" for i in range(5)]  # the pruning's yardstick, never a feature
# The pruning's LightGBM: the search's smallest trees (4 leaves, so three splits a tree) at
# LightGBM's default rate and leaf size. Each tree is offered `COLUMNS_PER_TREE` columns, one
# per split, so every offered column can get a split, and there are enough trees that each
# column is offered to about `OFFERS_PER_COLUMN` of them, whatever the frame's width.
PRUNING_MODEL = {"learning_rate": 0.1, "num_leaves": 4, "min_child_samples": 20}
COLUMNS_PER_TREE = 3
OFFERS_PER_COLUMN = 10
# With every column offered, 300 trees gave the full count's outcomes in every simulated case at
# a third of the time at 400 columns; the full count (1,350 there) overfits at ~1,000 events.
COMPARISON_TREES = 300


def screen_features(
    train: pd.DataFrame, X: pd.DataFrame, encoder: dict, stage2: pd.DataFrame, cfg: UseCaseConfig
) -> tuple[list[str], pd.DataFrame, pd.DataFrame]:
    """`(the features left in the encoder's order, the screen's rows stacked, the train
    statistics)`: the cluster rule and the floor, the rules that fit no model.

    Receives Training's collected train frame `train`, its encoded frame `X` (the encoder's
    features in order) and the Stage 2 ledger rows. The rules switched on by
    `cfg.training.selection` run in order on what the previous one left; `cfg.features.kept`
    is protected by each. A rule that leaves no feature fails loud, naming itself. The frame's
    order is checked before the rules and after each one.
    """
    check_order(X, encoder)
    statistics = train_statistics(train, X, encoder, cfg)
    rules, kept = cfg.training.selection, list(cfg.features.kept)
    features, tables = list(X.columns), []
    if rules.cluster:
        tables.append(apply_cluster_rule(statistics, stage2, features, kept))
        features = _remaining(X, encoder, features, tables[-1])
    if rules.floor_z is not None:
        tables.append(apply_floor(statistics, features, kept, rules.floor_z))
        features = _remaining(X, encoder, features, tables[-1])
    return features, stack_rows(tables), statistics


def prune_features(
    train: pd.DataFrame,
    X: pd.DataFrame,
    encoder: dict,
    features: list[str],
    cfg: UseCaseConfig,
    threads: int,
) -> tuple[list[str], pd.DataFrame]:
    """`(the final features in the encoder's order, the pruning's rows)`: importance pruning on
    the `features` the screen left when `training.selection.prune` is on, else those features
    and no row. `train` and `X` are `screen_features`' frames."""
    if not cfg.training.selection.prune:
        return features, stack_rows([])
    y, folds = train["target"].to_numpy(), train[[FOLD_COLUMN]]
    kept = list(cfg.features.kept)
    rows = prune_by_importance(
        X[features], y, folds, select_encoder(encoder, features), kept, cfg, threads
    )
    return _remaining(X, encoder, features, rows), rows


def stack_rows(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """The rules' rows stacked in order (`RULE_COLUMNS`), an empty table when no rule ran."""
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=RULE_COLUMNS)


def apply_cluster_rule(
    statistics: pd.DataFrame, stage2: pd.DataFrame, features: list[str], kept: list[str]
) -> pd.DataFrame:
    """One row per feature of `features` (`RULE_COLUMNS`, rule `cluster`): within each Stage 2
    redundancy cluster among `features`, the member with the highest train `value` (a tie to the
    first in `features`' order, an unavailable value lowest) is the representative and passes,
    `threshold` its own value; every other member is dropped (`protected` when kept) with
    `threshold` the representative's value and, when dropped, `represented_by` its name. A kept
    member competes like any other. A feature alone in its cluster passes with a null threshold.
    """
    value = _by_feature(statistics, ["value"], features, "the train statistics")["value"]
    cluster = _by_feature(stage2, ["cluster"], features, "the Stage 2 rows")["cluster"]
    members: dict[int, list[str]] = {}
    for name in features:
        if pd.notna(cluster[name]):
            members.setdefault(int(cluster[name]), []).append(name)
    representative = {}
    for group in members.values():
        if len(group) > 1:
            best = max(group, key=lambda name: -np.inf if np.isnan(value[name]) else value[name])
            representative.update({name: best for name in group})
    rows = []
    for name in features:
        best = representative.get(name)
        if best is None:
            rows.append(_row(name, "cluster", value[name], np.nan, "passed"))
        elif best == name:
            rows.append(_row(name, "cluster", value[name], value[name], "passed"))
        elif name in kept:
            rows.append(_row(name, "cluster", value[name], value[best], "protected"))
        else:
            rows.append(_row(name, "cluster", value[name], value[best], "dropped", best))
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


def apply_floor(
    statistics: pd.DataFrame, features: list[str], kept: list[str], floor_z: float
) -> pd.DataFrame:
    """One row per feature of `features` (`RULE_COLUMNS`, rule `floor`).

    A feature passes on its train `value` when it is at least `0.5 + floor_z · se`, named in
    `cleared_by` (`concordance` or `concordance_best_order`). The features null on the same
    rows (`null_pattern`) share one null indicator, so one pattern clears at most one of them:
    when its `null_concordance` reaches `0.5 + floor_z · null_se` and no member passes on its
    value, the member with the highest value passes on it (`cleared_by` `null_concordance`,
    the row holding the null indicator's numbers). Every other member that fails on its value
    is dropped with `represented_by` naming the member that carries the pattern: the
    null-clearing one, or the value-passing one with the highest value. A failing feature is
    dropped, `protected` instead when kept, with the value's numbers: a null value when its
    concordance is unavailable on train. A null statistic never clears, nor does a null
    threshold; a tie goes to the first in `features`' order.
    """
    columns = ["value", "se", "unavailable", "non_monotone", "null_concordance", "null_se",
               "null_pattern"]  # fmt: skip
    table = _by_feature(statistics, columns, features, "the train statistics")
    value = {n: np.nan if table.at[n, "unavailable"] else float(table.at[n, "value"])
             for n in features}  # fmt: skip
    value_threshold = 0.5 + floor_z * table["se"]
    passes = {name: bool(value[name] >= value_threshold[name]) for name in features}
    carriers = _null_carriers(table, features, value, passes, floor_z)
    rows = []
    for name in features:
        row = table.loc[name]
        if passes[name]:
            named = "concordance_best_order" if row["non_monotone"] else "concordance"
            rows.append(_row(name, "floor", value[name], value_threshold[name], "passed",
                             cleared_by=named))  # fmt: skip
        elif carriers.get(name) == name:
            threshold = 0.5 + floor_z * row["null_se"]
            rows.append(_row(name, "floor", row["null_concordance"], threshold, "passed",
                             cleared_by="null_concordance"))  # fmt: skip
        elif name in kept:
            rows.append(_row(name, "floor", value[name], value_threshold[name], "protected"))
        else:
            rows.append(_row(name, "floor", value[name], value_threshold[name], "dropped",
                             carriers.get(name)))  # fmt: skip
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


def _null_carriers(
    table: pd.DataFrame,
    features: list[str],
    value: dict[str, float],
    passes: dict[str, bool],
    floor_z: float,
) -> dict[str, str]:
    """Each member of a null pattern whose null concordance clears the floor, mapped to the one
    member that carries the pattern: the value-passing member with the highest value, else the
    member with the highest value (an unavailable value lowest, a tie to the first). `table`
    is the floor's statistics by feature; the members of a pattern share its null numbers."""
    groups: dict[str, list[str]] = {}
    for name in features:
        groups.setdefault(table.at[name, "null_pattern"], []).append(name)
    carriers = {}
    for group in groups.values():
        first = table.loc[group[0]]
        if not first["null_concordance"] >= 0.5 + floor_z * first["null_se"]:  # NaN: False
            continue
        passers = [name for name in group if passes[name]]
        carrier = max(passers or group, key=lambda n: -np.inf if np.isnan(value[n]) else value[n])
        carriers.update(dict.fromkeys(group, carrier))
    return carriers


def prune_by_importance(
    X: pd.DataFrame,
    y: np.ndarray,
    folds: pd.DataFrame,
    encoder: dict,
    kept: list[str],
    cfg: UseCaseConfig,
    threads: int,
) -> pd.DataFrame:
    """One row per column of `X` (`RULE_COLUMNS`, rule `prune`; `value` its out-of-fold
    contribution share, `threshold` the best noise column's).

    `X` is the encoded train frame left by the earlier rules, `encoder` its encoder, `folds`
    the frame's `cv_fold` on the same rows. Five seeded noise columns are appended and
    LightGBM's fold models fitted, sized to that frame (`_pruning_configuration`), under the
    run's constraints; the candidates are the features whose share is not above the best noise
    column's (a kept one is `protected`). A best noise share of 0 compares nothing with noise:
    every feature then passes. The fold models are then fitted twice without the noise, with
    and without the candidates: the drops stand unless the decision's metric as a loss, the mean
    over the folds, rose without them, when the candidates are `undone`. The comparison judges
    the candidates as a set: one needed feature keeps them all, and weak ones go together. Both
    fits run at the yardstick's tree count, at most `COMPARISON_TREES`, and offer every column
    to every tree, so they differ only by the candidates: with the yardstick's three columns a
    tree, the two frames would draw different columns per tree and that chance alone moves the
    loss. No candidate, no further fit.
    """
    noisy, noisy_encoder = _with_noise(X, encoder, cfg.training.seed)
    configuration = _pruning_configuration(noisy.shape[1])
    _, contributions = _fold_fit(noisy, y, folds, noisy_encoder, configuration, cfg, threads)
    share = _contribution_shares(contributions, list(noisy.columns))
    best_noise = float(share[NOISE_COLUMNS].max())
    beaten = [name for name in X.columns if best_noise > 0 and share[name] <= best_noise]
    candidates = [name for name in beaten if name not in kept]
    outcome = "dropped"
    if candidates:
        rest = [name for name in X.columns if name not in candidates]
        if not rest:
            raise ValueError(
                "pruning: no feature does better than the best noise column, so every feature "
                "would be dropped; check the target and the candidates"
            )
        rest_encoder = select_encoder(encoder, rest)
        comparison = _comparison_configuration(configuration)
        loss, _ = _fold_fit(X, y, folds, encoder, comparison, cfg, threads)
        refit_loss, _ = _fold_fit(X[rest], y, folds, rest_encoder, comparison, cfg, threads)
        outcome = "undone" if refit_loss > loss else "dropped"
        print(f"  pruning's comparison: out-of-fold loss {loss:.6f} with the {len(candidates)} "
              f"candidates, {refit_loss:.6f} without: {outcome}")  # fmt: skip
    rows = []
    for name in X.columns:
        verdict = (
            "passed" if name not in beaten else (outcome if name in candidates else "protected")
        )
        rows.append(_row(name, "prune", float(share[name]), best_noise, verdict))
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


def _pruning_configuration(columns: int) -> dict:
    """LightGBM's configuration for the pruning's fold models on a frame of `columns` columns:
    `PRUNING_MODEL` with ⌈`OFFERS_PER_COLUMN` · columns / `COLUMNS_PER_TREE`⌉ trees and a column
    share per tree of `COLUMNS_PER_TREE` / columns, below 1 since the five noise columns and a
    feature make six or more. LightGBM 4.6 rounds the share times a frame's columns to the
    nearest count, at least one, so each tree of that frame gets three."""
    return {
        **PRUNING_MODEL,
        "n_estimators": math.ceil(OFFERS_PER_COLUMN * columns / COLUMNS_PER_TREE),
        "colsample_bytree": COLUMNS_PER_TREE / columns,
    }


def _comparison_configuration(configuration: dict) -> dict:
    """The undo check's configuration from the yardstick's (`_pruning_configuration`): every
    column offered to every tree, the tree count capped at `COMPARISON_TREES`."""
    trees = min(configuration["n_estimators"], COMPARISON_TREES)
    return {**configuration, "colsample_bytree": 1.0, "n_estimators": trees}


def _with_noise(X: pd.DataFrame, encoder: dict, seed: int) -> tuple[pd.DataFrame, dict]:
    """`X` with the `NOISE_COLUMNS` appended (uniform random numbers drawn with `seed`) and the
    encoder extended by them as numeric entries, in the same order. The gate has refused a
    feature named like one (`gate.check_noise_names`)."""
    draws = np.random.default_rng(seed).random((len(X), len(NOISE_COLUMNS)))
    noise = pd.DataFrame(draws, index=X.index, columns=NOISE_COLUMNS)
    entries = [{"name": name, "kind": "numeric"} for name in NOISE_COLUMNS]
    return pd.concat([X, noise], axis=1), {**encoder, "features": [*encoder["features"], *entries]}


def _fold_fit(
    X: pd.DataFrame,
    y: np.ndarray,
    folds: pd.DataFrame,
    encoder: dict,
    configuration: dict,
    cfg: UseCaseConfig,
    threads: int,
) -> tuple[float, np.ndarray]:
    """LightGBM's fold models on `X` at `configuration` merged over its fixed parameters, under
    the run's constraints on the features in the frame: `(the decision's metric as a loss out
    of fold, the mean over the folds; the out-of-fold contributions, base value last)`."""
    check_order(X, encoder)
    monotone = {name: d for name, d in cfg.training.monotone.items() if name in X.columns}
    fixed = FAMILIES["lgbm"].fixed_params(
        cfg.task, cfg.training.objective, encoder, monotone, cfg.training.seed, threads,
        cfg.training.tweedie_variance_power,
    )  # fmt: skip
    margins, contributions = fit_fold_models(
        X, y, folds, "lgbm", {**fixed, **configuration}, cfg.task, threads
    )
    loss = out_of_fold_loss(
        cfg.decision.metric, y, margins, folds[FOLD_COLUMN].to_numpy(),
        uncalibrated(cfg.training.objective), cfg.task,
    )  # fmt: skip
    return loss, contributions


def _contribution_shares(contributions: np.ndarray, columns: list[str]) -> pd.Series:
    """Each column's share of the mean absolute out-of-fold contribution over `columns`, the
    base value (the last column of `contributions`) left out."""
    mean_absolute = np.abs(contributions[:, :-1]).mean(axis=0)
    total = mean_absolute.sum()
    if total == 0:
        raise ValueError("pruning: the fold models made no split, so no feature has a share")
    return pd.Series(mean_absolute / total, index=columns)


def _remaining(
    X: pd.DataFrame, encoder: dict, features: list[str], rows: pd.DataFrame
) -> list[str]:
    """`features` without the ones `rows` (one rule's) dropped; fails loud when none is left,
    naming the rule. The frame they leave is checked against the encoder restricted to them
    (`check_order`): `training.md` requires it after each drop, though it passes by construction."""
    dropped = set(rows.loc[rows["outcome"] == "dropped", "feature"])
    left = [name for name in features if name not in dropped]
    if not left:
        rule = rows["rule"].iat[0]
        raise ValueError(
            f"selection: the {rule} rule left no feature to train on; keep a feature (a `keep` "
            f"entry in the audit log) or switch the rule off in training.selection"
        )
    check_order(X[left], select_encoder(encoder, left))
    return left


def _by_feature(
    table: pd.DataFrame, columns: list[str], features: list[str], what: str
) -> pd.DataFrame:
    """`table[columns]` indexed by feature; fails loud on a feature of `features` it lacks."""
    by_feature = table.set_index("feature")[columns]
    missing = [name for name in features if name not in by_feature.index]
    if missing:
        raise ValueError(f"selection: {what} hold no row for {missing}")
    return by_feature


def _row(
    feature: str,
    rule: str,
    value: float,
    threshold: float,
    outcome: str,
    represented_by: str | None = None,
    cleared_by: str | None = None,
) -> dict:
    """One rule's row for one feature."""
    return {
        "feature": feature, "rule": rule, "value": value, "threshold": threshold,
        "outcome": outcome, "represented_by": represented_by, "cleared_by": cleared_by,
    }  # fmt: skip
