"""The train rows as every fit after selection sees them (training.md → "The encoder and the
families", "Selection").

`fit_train_encoder` fits the encoder of the feature set in force on the train frame and refuses
a constraint on an unordered categorical. `encode_and_screen` applies the encoder once, before
any library sees a value, and runs selection's model-free screen on the encoded frame (the
cluster rule and the floor): Training calls both before it reserves a run number, so their
refusals take none. `finish_selection` prunes what the screen left and returns it as
`TrainData`, with selection's log entry and warnings. Everything here reads the train split
only (`CLAUDE.md` §4.4).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.folds import fold_columns
from core_modelling.model.encoder import encode_frame, fit_encoder, select_encoder
from core_modelling.model.family_inputs import monotone_directions
from core_modelling.training.selection import prune_features, screen_features, stack_rows


@dataclass
class Screened:
    """The train frame after the screen, before the run number: the encoded frame of every
    feature in force (the encoder's order), the encoder's shares on it, the train statistics,
    the cluster rule's and the floor's rows, and the features they left."""

    X: pd.DataFrame
    shares: pd.DataFrame
    statistics: pd.DataFrame
    rows: pd.DataFrame
    features: list[str]


@dataclass
class TrainData:
    """The train rows after selection: the encoded frame of the final features (the encoder's
    order), the target, the fold columns, the final features' encoder and constraints. For the
    per-run ledger: the encoder of every feature that entered selection with its shares on the
    train frame, the selection table and the train statistics."""

    X: pd.DataFrame
    y: np.ndarray
    folds: pd.DataFrame
    encoder: dict
    monotone: dict[str, str]
    entered_encoder: dict
    shares: pd.DataFrame
    selection: pd.DataFrame
    statistics: pd.DataFrame


def fit_train_encoder(
    train: pd.DataFrame, features: list[str], ledger: pd.DataFrame, resolved: UseCaseConfig
) -> dict:
    """The encoder of the feature set in force, fitted on the train frame: each feature's kind
    is the ledger's, a categorical named in `features.order` is ordered. A constraint on an
    unordered categorical is refused here, before any fit (the libraries fail in three ways),
    and so is a train level that `features.order` does not list."""
    kinds = ledger.set_index("feature")["kind"].loc[features].to_dict()
    order = {name: levels for name, levels in resolved.features.order.items() if name in features}
    categoricals = resolved.training.categoricals
    encoder = fit_encoder(
        train, features, kinds, order, categoricals.min_level_client_count, categoricals.unordered
    )
    declared = {n: d for n, d in resolved.training.monotone.items() if n in features}
    monotone_directions("training.monotone", encoder, declared)
    return encoder


def encode_and_screen(
    train: pd.DataFrame, encoder: dict, ledger: pd.DataFrame, resolved: UseCaseConfig
) -> tuple[Screened, dict, list[str]]:
    """`(the screened frame, the encoder's log entry, its warnings)`, before the run number.

    Receives Training's collected train frame (one row per client and period, with `target`
    and the fold columns), the encoder fitted on it, the Stage 2 ledger rows and the resolved
    config. The frame is encoded once and screened by the rules that fit no model
    (`screen_features`), which refuse when they leave no feature; a warning never changes what
    the run does.
    """
    X, shares = encode_frame(train, encoder)
    entry, notes = _encoder_notes(X, encoder, shares)
    features, rows, statistics = screen_features(train, X, encoder, ledger, resolved)
    return Screened(X, shares, statistics, rows, features), entry, notes


def finish_selection(
    train: pd.DataFrame,
    encoder: dict,
    screened: Screened,
    resolved: UseCaseConfig,
    threads: int,
) -> tuple[TrainData, dict, list[str]]:
    """`(the train data after selection, selection's log entry, the warnings)`: importance
    pruning on what the screen left (`prune_features`), then the frame of the final features.
    `train` and `encoder` are the ones `encode_and_screen` received. The warnings name the
    pruning that was undone or compared nothing with noise, and a constrained final feature
    with nulls while `catboost` is searched."""
    X = screened.X
    final, pruned = prune_features(train, X, encoder, screened.features, resolved, threads)
    selection = stack_rows([table for table in (screened.rows, pruned) if len(table)])
    dropped = selection.loc[selection["outcome"] == "dropped", "rule"].value_counts().to_dict()
    entry = {"step": "selection", "entered": len(X.columns), "final": len(final),
             "dropped": dropped}  # fmt: skip
    print(f"selection: {len(final)} of {len(X.columns)} features left ({dropped or 'no drop'})")
    notes = [*_pruning_notes(pruned), *_catboost_notes(final, screened.shares, resolved)]
    data = TrainData(
        X=X[final],
        y=train["target"].to_numpy(),
        folds=train[fold_columns(resolved.training.fold_repeats)],
        encoder=select_encoder(encoder, final),
        monotone={n: d for n, d in resolved.training.monotone.items() if n in final},
        entered_encoder=encoder,
        shares=screened.shares,
        selection=selection,
        statistics=screened.statistics,
    )
    return data, entry, notes


def _pruning_notes(pruned: pd.DataFrame) -> list[str]:
    """The pruning's warnings from its rows: candidates `undone` because the loss rose without
    them, and a best noise share (every row's `threshold`) of 0, when no noise column got a
    split and no feature was compared with noise."""
    notes = []
    undone = pruned.loc[pruned["outcome"] == "undone", "feature"].tolist()
    if undone:
        notes.append(f"pruning was undone: without {undone} the out-of-fold loss rose")
    if len(pruned) and (pruned["threshold"] == 0).all():
        notes.append(
            "pruning dropped nothing: no noise column got a split in the pruning model, so no "
            "feature could be compared with noise"
        )
    return notes


def _catboost_notes(final: list[str], shares: pd.DataFrame, resolved: UseCaseConfig) -> list[str]:
    """The warning for final features under a constraint with nulls in train while `catboost`
    is searched: CatBoost counts a null as the smallest value, inside the constraint. `shares`
    is `encode_frame`'s on train."""
    null_share = shares.set_index("feature")["null_share"]
    monotone = resolved.training.monotone
    constrained = [name for name in final if name in monotone and null_share[name] > 0]
    if not (constrained and "catboost" in resolved.training.estimator_list):
        return []
    return [
        f"the constrained features {constrained} have nulls and catboost is searched: "
        "CatBoost counts a null as the smallest value, inside the constraint; its fold loss "
        "carries the cost"
    ]


def _encoder_notes(X: pd.DataFrame, encoder: dict, shares: pd.DataFrame) -> tuple[dict, list[str]]:
    """The encoder's log entry (per ordered feature, the declared levels no train row holds:
    each keeps its position and is allowed) and its warnings: an ordered feature without a train
    null, for which a null or an unseen level at scoring is a value the model never saw. `X` and
    `shares` are `encode_frame`'s on train."""
    null_share = shares.set_index("feature")["null_share"]
    unseen, notes = {}, []
    for entry in encoder["features"]:
        name = entry["name"]
        if entry["kind"] != "ordered":
            continue
        seen = set(X[name].dropna().astype(int))
        missing = [level for position, level in enumerate(entry["levels"]) if position not in seen]
        if missing:
            unseen[name] = missing
        if null_share[name] == 0:
            notes.append(
                f"the ordered feature {name!r} has no null in train: a null or an unseen level "
                "at scoring is a value the model never saw, scored as an extreme"
            )
    entry = {"step": "encoder", "features": len(encoder["features"]),
             "levels_without_train_rows": unseen}  # fmt: skip
    return entry, notes
