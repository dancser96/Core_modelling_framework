"""The train rows as every fit after selection sees them (training.md → "The encoder and the
families", "Selection").

`fit_train_encoder` fits the encoder of the feature set in force on the train frame and refuses
a constraint on an unordered categorical; Training calls it before it reserves a run number.
`encode_and_select` applies the encoder once, before any library sees a value, runs the
automated selection on the encoded frame and returns what is left as `TrainData`, with the
log entries and the warnings of both steps. Everything here reads the train split only
(`CLAUDE.md` §4.4).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.folds import fold_columns
from core_modelling.model.encoder import encode_frame, fit_encoder, select_encoder
from core_modelling.model.family_inputs import monotone_directions
from core_modelling.training.search_space import family_space, start_configuration
from core_modelling.training.selection import select_features


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


def encode_and_select(
    train: pd.DataFrame, encoder: dict, ledger: pd.DataFrame, resolved: UseCaseConfig, threads: int
) -> tuple[TrainData, list[dict], list[str]]:
    """`(the train data after selection, the log entries, the warnings)`.

    Receives Training's collected train frame (one row per client and period, with `target`
    and the fold columns), the encoder fitted on it, the Stage 2 ledger rows and the resolved
    config. The frame is encoded once; selection's three rules run on it in order, pruning with
    LightGBM at its start configuration. The entries are the encoder's and selection's; a
    warning never changes what the run does.
    """
    X, shares = encode_frame(train, encoder)
    entry, notes = _encoder_notes(X, encoder, shares, resolved)
    space = family_space("lgbm", resolved.training.search_space.get("lgbm", {}))
    final, selection, statistics = select_features(
        train, X, encoder, ledger, resolved, start_configuration(space), threads
    )
    dropped = selection.loc[selection["outcome"] == "dropped", "rule"].value_counts().to_dict()
    selected = {"step": "selection", "entered": len(X.columns), "final": len(final),
                "dropped": dropped}  # fmt: skip
    undone = selection.loc[selection["outcome"] == "undone", "feature"].tolist()
    if undone:
        notes.append(f"pruning was undone: without {undone} the out-of-fold loss rose")
    print(f"selection: {len(final)} of {len(X.columns)} features left ({dropped or 'no drop'})")
    data = TrainData(
        X=X[final],
        y=train["target"].to_numpy(),
        folds=train[fold_columns(resolved.training.fold_repeats)],
        encoder=select_encoder(encoder, final),
        monotone={n: d for n, d in resolved.training.monotone.items() if n in final},
        entered_encoder=encoder,
        shares=shares,
        selection=selection,
        statistics=statistics,
    )
    return data, [entry, selected], notes


def _encoder_notes(
    X: pd.DataFrame, encoder: dict, shares: pd.DataFrame, resolved: UseCaseConfig
) -> tuple[dict, list[str]]:
    """The encoder's log entry (per ordered feature, the declared levels no train row holds:
    each keeps its position and is allowed) and its warnings: an ordered feature without a train
    null, for which a null or an unseen level at scoring is a value the model never saw; and a
    constrained feature with nulls while `catboost` is searched, which counts a null as the
    smallest value, inside the constraint. `X` and `shares` are `encode_frame`'s on train."""
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
    constrained = [n for n in resolved.training.monotone if null_share.get(n, 0) > 0]
    if constrained and "catboost" in resolved.training.estimator_list:
        notes.append(
            f"the constrained features {constrained} have nulls and catboost is searched: "
            "CatBoost counts a null as the smallest value, inside the constraint; its fold loss "
            "carries the cost"
        )
    entry = {"step": "encoder", "features": len(encoder["features"]),
             "levels_without_train_rows": unseen}  # fmt: skip
    return entry, notes
