"""Training's automated feature selection: three rules in a fixed order, on the train split only
(`docs/components/training.md` → Selection, D-140 (e), `CLAUDE.md` §4.4).

`select_features` runs the cluster rule, the floor and importance pruning, each switched by
`training.selection`; a feature one rule drops is not judged by the later ones. Each rule returns
one row per feature it judged (`RULE_COLUMNS`); the rows stacked are Training's `selection`
table, and the per-run ledger reads them: the one record of a drop (D-125). A person's `keep` is
measured by every rule and dropped by none (`protected`). The cluster rule and the floor read
`train_statistics`; pruning fits LightGBM fold models beside five seeded noise columns, whatever
families are searched, and no noise column leaves it.
"""

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.model.calibration import apply_calibration, uncalibrated
from core_modelling.model.encoder import select_encoder
from core_modelling.model.families import FAMILIES
from core_modelling.model.family_inputs import check_order
from core_modelling.statistics.losses import mean_fold_loss
from core_modelling.training.fold_models import FOLD_COLUMN, fit_fold_models
from core_modelling.training.train_statistics import train_statistics

RULE_COLUMNS = ["feature", "rule", "value", "threshold", "outcome", "represented_by"]
NOISE_COLUMNS = [f"__noise_{i}" for i in range(5)]  # the pruning's yardstick, never a feature


def select_features(
    train: pd.DataFrame,
    X: pd.DataFrame,
    encoder: dict,
    stage2: pd.DataFrame,
    cfg: UseCaseConfig,
    start: dict,
    threads: int,
) -> tuple[list[str], pd.DataFrame, pd.DataFrame]:
    """`(final features in the encoder's order, the rules' rows stacked, the train statistics)`.

    Receives Training's collected train frame `train`, its encoded frame `X` (the encoder's
    features in order), the Stage 2 ledger rows and LightGBM's start configuration `start`
    for pruning. The rules switched on by `cfg.training.selection` run in order on what the
    previous one left; `cfg.features.kept` is protected by each. The frame's order is checked
    before the rules and after each one.
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
    if rules.prune:
        y, folds = train["target"].to_numpy(), train[[FOLD_COLUMN]]
        pruning_encoder = select_encoder(encoder, features)
        tables.append(
            prune_by_importance(X[features], y, folds, pruning_encoder, kept, start, cfg, threads)
        )
        features = _remaining(X, encoder, features, tables[-1])
    selection = (
        pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=RULE_COLUMNS)
    )
    return features, selection, statistics


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
    """One row per feature of `features` (`RULE_COLUMNS`, rule `floor`): dropped when its train
    `value` is below `0.5 + floor_z · se`, the threshold; a feature whose concordance is
    unavailable on train is dropped with a null value. `protected` instead when kept."""
    table = _by_feature(
        statistics, ["value", "se", "unavailable"], features, "the train statistics"
    )
    rows = []
    for name in features:
        value, se, reason = table.loc[name, ["value", "se", "unavailable"]]
        threshold = 0.5 + floor_z * se
        below = bool(reason) or value < threshold
        outcome = ("protected" if name in kept else "dropped") if below else "passed"
        rows.append(_row(name, "floor", np.nan if reason else value, threshold, outcome))
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


def prune_by_importance(
    X: pd.DataFrame,
    y: np.ndarray,
    folds: pd.DataFrame,
    encoder: dict,
    kept: list[str],
    start: dict,
    cfg: UseCaseConfig,
    threads: int,
) -> pd.DataFrame:
    """One row per column of `X` (`RULE_COLUMNS`, rule `prune`; `value` its out-of-fold
    contribution share, `threshold` the best noise column's).

    `X` is the encoded train frame left by the earlier rules, `encoder` its encoder, `folds`
    the frame's `cv_fold` on the same rows, `start` LightGBM's start configuration. Five seeded
    noise columns are appended and LightGBM's fold models fitted at `start` under the run's
    constraints; the candidates are the features whose share is not above the best noise
    column's (a kept one is `protected`). The fold models are then fitted twice without the
    noise, with and without the candidates: the drops stand unless the decision's metric as a
    loss, the mean over the folds, rose without them, when the candidates are `undone`. Both
    fits leave the noise out, so the comparison is of like with like. No candidate, no further
    fit.
    """
    noisy, noisy_encoder = _with_noise(X, encoder, cfg.training.seed)
    _, contributions = _fold_fit(noisy, y, folds, noisy_encoder, start, cfg, threads)
    share = _contribution_shares(contributions, list(noisy.columns))
    best_noise = float(share[NOISE_COLUMNS].max())
    beaten = [name for name in X.columns if share[name] <= best_noise]
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
        loss, _ = _fold_fit(X, y, folds, encoder, start, cfg, threads)
        refit_loss, _ = _fold_fit(X[rest], y, folds, rest_encoder, start, cfg, threads)
        outcome = "undone" if refit_loss > loss else "dropped"
    rows = []
    for name in X.columns:
        verdict = (
            "passed" if name not in beaten else (outcome if name in candidates else "protected")
        )
        rows.append(_row(name, "prune", float(share[name]), best_noise, verdict))
    return pd.DataFrame(rows, columns=RULE_COLUMNS)


def _with_noise(X: pd.DataFrame, encoder: dict, seed: int) -> tuple[pd.DataFrame, dict]:
    """`X` with the `NOISE_COLUMNS` appended (uniform random numbers drawn with `seed`) and the
    encoder extended by them as numeric entries, in the same order."""
    clash = sorted(set(NOISE_COLUMNS) & set(X.columns))
    if clash:
        raise ValueError(f"pruning: the features {clash} carry the noise columns' reserved names")
    draws = np.random.default_rng(seed).random((len(X), len(NOISE_COLUMNS)))
    noise = pd.DataFrame(draws, index=X.index, columns=NOISE_COLUMNS)
    entries = [{"name": name, "kind": "numeric"} for name in NOISE_COLUMNS]
    return pd.concat([X, noise], axis=1), {**encoder, "features": [*encoder["features"], *entries]}


def _fold_fit(
    X: pd.DataFrame,
    y: np.ndarray,
    folds: pd.DataFrame,
    encoder: dict,
    start: dict,
    cfg: UseCaseConfig,
    threads: int,
) -> tuple[float, np.ndarray]:
    """LightGBM's fold models on `X` at `start` merged over its fixed parameters, under the
    run's constraints on the features in the frame: `(the decision's metric as a loss out of
    fold, the mean over the folds; the out-of-fold contributions, base value last)`."""
    check_order(X, encoder)
    monotone = {name: d for name, d in cfg.training.monotone.items() if name in X.columns}
    fixed = FAMILIES["lgbm"].fixed_params(
        cfg.task, cfg.training.objective, encoder, monotone, cfg.training.seed, threads,
        cfg.training.tweedie_variance_power,
    )  # fmt: skip
    margins, contributions = fit_fold_models(X, y, folds, "lgbm", {**fixed, **start}, cfg.task)
    score_raw, _ = apply_calibration(margins, uncalibrated(cfg.training.objective), cfg.task)
    fold = folds[FOLD_COLUMN].to_numpy()
    return mean_fold_loss(cfg.decision.metric, y, score_raw, fold), contributions


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
) -> dict:
    """One rule's row for one feature."""
    return {
        "feature": feature, "rule": rule, "value": value, "threshold": threshold,
        "outcome": outcome, "represented_by": represented_by,
    }  # fmt: skip
