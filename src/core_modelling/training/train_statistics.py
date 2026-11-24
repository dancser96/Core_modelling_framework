"""The train-split statistics the selection rules read: each encoder feature's concordance with
the target on the train rows only (`CLAUDE.md` §4.4, D-030).

Each feature's cells are built in pandas from its encoded column, what the model sees, with the
counts table's columns (`dataset/counts.py`, `CELL_COLUMNS`) on edges of the train rows' own, and
read by the one statistics engine
EDA and Feature Checks read (`statistics/scope.py`, D-137): a numeric bucketed on
`quantile_edges` of its own train values, an ordered categorical by its code, an unordered one by
its code with the row's `cv_fold` as the fold, so its level encoding is cross-fitted on other
clients. The SE is on effective train clients, as EDA's window rules read it. Beside the
value's concordance, each feature's null indicator gets its own (`null_concordance`, on every
train row) with its SE, which the floor also reads: the families take nulls natively, so a
feature whose being filled predicts the target is used by the model. The frame is used as
collected: label-dependent sampling leaves a rank statistic unbiased. EDA's all-client ranking
is never read (D-030), nor is its `non_monotone` mark: both have seen test labels, so whether a
feature is judged on its best order is decided again here, on the train rows.
"""

import hashlib

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.counts import CELL_COLUMNS
from core_modelling.statistics.concordance import (
    SE_FLOOR,
    best_order_concordance,
    is_non_monotone,
)
from core_modelling.statistics.distributions import bin_labels, bin_orders, quantile_edges
from core_modelling.statistics.scope import encoding_prior_rows, feature_se, scope_statistics
from core_modelling.tasks import TASK_SPECS
from core_modelling.training.fold_models import FOLD_COLUMN

STATISTIC_COLUMNS = ["feature", "concordance", "sign", "se", "concordance_best_order",
                     "non_monotone", "value", "unavailable", "null_concordance",
                     "null_se", "null_pattern"]  # fmt: skip
CELL_KEYS = ["period", "bin_order", "is_null", "target_bin"]  # a cell, beside the feature and fold


def train_statistics(
    train: pd.DataFrame, X: pd.DataFrame, encoder: dict, cfg: UseCaseConfig
) -> pd.DataFrame:
    """One row per encoder feature (`STATISTIC_COLUMNS`), in the encoder's order.

    Receives `train`, Training's collected train frame (one row per client and period, with
    `unit_id`, `period`, `target` and `cv_fold`) and `X`, the same rows as `encode_frame`
    returned them. `concordance` has the direction taken out and `sign` is the raw sign of D
    (±1, 0 when unavailable); `se` is on effective train clients; `concordance_best_order`
    exists for numerics; `non_monotone` is EDA's rule (`is_non_monotone`) on these three train
    numbers; `value`, what the rules read, is the best-order concordance when `non_monotone`,
    else the plain one; `unavailable` is the engine's reason, '' when the concordance exists.
    `null_concordance` is the null indicator's, direction taken out, NaN outside the engine's
    `NULL_SHARE_RANGE` (a feature with no nulls has none), `null_se` its SE on every train
    row in effective clients (`_null_se`) and `null_pattern` a digest of the rows it is null on.
    """
    _check_inputs(train, X, encoder)
    rows = pd.DataFrame(
        {
            "period": train["period"].astype(str).to_numpy(),
            "target_bin": _target_bins(train["target"], cfg),
            "y": train["target"].to_numpy(dtype=float),
            "fold": train[FOLD_COLUMN].to_numpy(),
        }
    )
    periods = sorted(rows["period"].unique())
    clients = _train_clients(train)
    every_row_shares = rows["target_bin"].value_counts(normalize=True).to_numpy()
    exact = cfg.eda.bins is None
    cells = {
        entry["name"]: _feature_cells(entry, X[entry["name"]].to_numpy(), rows, cfg.eda.bins)
        for entry in encoder["features"]
    }
    first = cells[encoder["features"][0]["name"]]  # every feature counts every row
    prior_rows = encoding_prior_rows(first, cfg.task, cfg.strata.min_events, periods)
    records = []
    for entry in encoder["features"]:
        engine_kind = "categorical" if entry["kind"] == "unordered" else "numeric"
        scope = scope_statistics(
            cells[entry["name"]], engine_kind, read=periods, task=cfg.task,
            window_periods=periods, prior_rows=prior_rows, exact=exact, clients=clients,
        )  # fmt: skip
        is_null = _null_mask(entry, X[entry["name"]].to_numpy())
        null_se = _null_se(
            scope["null_concordance"], float(is_null.mean()), clients, every_row_shares, cfg.task
        )
        records.append({**_record(entry, scope, prior_rows), "null_se": null_se,
                        "null_pattern": _null_pattern(is_null)})  # fmt: skip
    return pd.DataFrame(records, columns=STATISTIC_COLUMNS)


def _null_se(
    null: float,
    share: float,
    clients: dict[str, float],
    target_bin_shares: np.ndarray,
    task: str,
) -> float:
    """The SE of a null indicator's concordance `null` (NaN for none), `share` its null share on
    the train rows: the task's SE on every train row (events and non-events in effective
    clients, `_train_clients`; the target bins' shares over every row for Kendall's) times
    `sqrt(3·p·(1 − p))`, the tie correction `1 − Σt³/N³` of a two-valued indicator, floored at
    `SE_FLOOR`."""
    if np.isnan(null):
        return np.nan
    events, non_events = clients["event_rows"], clients["non_event_rows"]
    se = feature_se(null, events, non_events, target_bin_shares, "numeric", task, clients)
    return max(se * np.sqrt(3 * share * (1 - share)), SE_FLOOR)


def _null_mask(entry: dict, codes: np.ndarray) -> np.ndarray:
    """Each row's null flag from one encoded column: a NaN for a numeric or an ordered
    categorical, code 0 (the null bin) for an unordered one."""
    if entry["kind"] == "unordered":
        return codes.astype(np.int64) == 0
    return np.isnan(codes.astype(float))


def _null_pattern(is_null: np.ndarray) -> str:
    """A digest of a null mask: two features with the same digest are null on the same rows."""
    return hashlib.sha256(np.packbits(is_null).tobytes()).hexdigest()[:16]


def _train_clients(train: pd.DataFrame) -> dict[str, float]:
    """The pandas twin of `counts.window_clients` on the train rows, every one labelled: the
    rows and Kish's effective clients `(Σ m)² / Σ m²` per class (`event_*`: a non-zero target,
    `non_event_*`) and in all, and `event_clients`, the distinct clients with an event."""
    event = (train["target"] != 0).to_numpy()
    per_client = (
        pd.DataFrame({"unit_id": train["unit_id"].to_numpy(), "event": event, "non_event": ~event})
        .assign(all=1)
        .groupby("unit_id")[["event", "non_event", "all"]]
        .sum()
    )
    sizes = {}
    for name, prefix in (("event", "event_"), ("non_event", "non_event_"), ("all", "")):
        total, squares = per_client[name].sum(), (per_client[name] ** 2).sum()
        sizes[f"{prefix}rows"] = float(total)
        sizes[f"{prefix}effective"] = float(total**2 / squares) if squares else 0.0
    sizes["event_clients"] = float((per_client["event"] > 0).sum())
    return sizes


def _check_inputs(train: pd.DataFrame, X: pd.DataFrame, encoder: dict) -> None:
    """Fail loud unless `train` and `X` hold the same rows, every target and client fold is
    known (an unordered feature's cells would lose a row without a fold) and the encoder has a
    feature."""
    if len(train) != len(X) or not train.index.equals(X.index):
        raise ValueError(
            f"train_statistics: the train frame ({len(train):,} rows) and its encoded frame "
            f"({len(X):,} rows) must hold the same rows in the same order"
        )
    if train["target"].isna().any():
        raise ValueError("train_statistics: the train frame holds null targets, which it drops")
    if train[FOLD_COLUMN].isna().any():
        raise ValueError(f"train_statistics: the train frame holds rows without a {FOLD_COLUMN}")
    if not encoder["features"]:
        raise ValueError("train_statistics: the encoder holds no feature")


def _target_bins(target: pd.Series, cfg: UseCaseConfig) -> np.ndarray:
    """Each row's target bin as the counts table writes it: a 0/1 target's `"0"` or `"1"`, a
    regression target's bucket label on `TASK_SPECS[task]["target_bins"]`' edges."""
    known = target.to_numpy(dtype=float)
    edges = TASK_SPECS[cfg.task]["target_bins"](known, cfg.eda.bins is None)
    if edges is None:  # binary: the two values are the bins
        odd = sorted(set(np.unique(known)) - {0.0, 1.0})
        if odd:
            raise ValueError(f"train_statistics: a binary target holds the values {odd[:5]}")
        return known.astype(int).astype(str)
    return np.asarray(bin_labels(edges), dtype=object)[np.digitize(known, edges)]


def _bin_orders(entry: dict, codes: np.ndarray, bins: int | None) -> tuple[np.ndarray, np.ndarray]:
    """Each row's `bin_order` and null flag from one encoded column: a numeric's bucket on
    `quantile_edges` of its non-null values (every distinct value a bin when `bins` is None) as
    `distributions.bin_orders` gives it, an ordered categorical's code, an unordered one's code
    (0, the null bin). A numeric's or ordered categorical's null bin is last, as in the counts
    table (`bin_orders` gives it -1). Unlike `counts.bin_edges`, a numeric gets no `= 0`
    singleton bin: nothing here reads `zero_share`."""
    is_null = _null_mask(entry, codes)
    if entry["kind"] == "unordered":
        return codes.astype(np.int64), is_null
    values = codes.astype(float)
    if entry["kind"] == "ordered":
        order = np.where(is_null, len(entry["levels"]), np.nan_to_num(values))
        return order.astype(np.int64), is_null
    known = values[~is_null]
    edges = quantile_edges(known, max(np.unique(known).size, 1) if bins is None else bins)
    return np.where(is_null, edges.size + 1, bin_orders(pd.Series(values), edges)), is_null


def _feature_cells(
    entry: dict, codes: np.ndarray, rows: pd.DataFrame, bins: int | None
) -> pd.DataFrame:
    """One feature's cells with the counts table's columns (`CELL_COLUMNS`), one row per period,
    fold, bin and target bin: `rows` holds each train row's `period`, `target_bin`, target `y`
    and `fold`; the fold is kept for an unordered categorical only, null otherwise."""
    order, is_null = _bin_orders(entry, codes, bins)
    frame = rows.assign(bin_order=order, is_null=is_null, y2=rows["y"] ** 2)
    keys = [*CELL_KEYS, "fold"] if entry["kind"] == "unordered" else CELL_KEYS
    cells = frame.groupby(keys, as_index=False).agg(
        n=("y", "size"), sum_y=("y", "sum"), sum_y2=("y2", "sum")
    )
    if "fold" not in cells:
        cells["fold"] = pd.NA
    cells["fold"] = cells["fold"].astype("Int64")
    cells["bin"] = cells["bin_order"].astype(str)
    cells = cells.assign(feature=entry["name"], lagged=False)
    return cells[CELL_COLUMNS]


def _record(entry: dict, scope: dict, prior_rows: float) -> dict:
    """One feature's row from its train scope (`scope_statistics`). A numeric is judged on its
    best-order concordance when the train rows show it as non-monotone (`is_non_monotone` on
    its plain concordance, its best-order one and its SE, the rule EDA marks features with);
    Stage 2's own mark is not read, since it has seen test labels (`CLAUDE.md` §4.4). A
    concordance without an SE fails loud."""
    available = not scope["reason"]
    if available and np.isnan(scope["se"]):
        raise ValueError(
            f"train_statistics: {entry['name']!r} (kind {entry['kind']}) has a concordance but "
            "no SE for the rules to read"
        )
    best, non_monotone = np.nan, False
    if available and entry["kind"] == "numeric":
        best = best_order_concordance(scope["pooled"], prior_rows)
        non_monotone = not np.isnan(best) and is_non_monotone(
            scope["concordance"], best, scope["se"]
        )
    sign = (1 if scope["signed"] >= 0.5 else -1) if available else 0
    return {
        "feature": entry["name"], "concordance": scope["concordance"], "sign": sign,
        "se": scope["se"], "concordance_best_order": best, "non_monotone": non_monotone,
        "value": best if non_monotone else scope["concordance"],
        "unavailable": scope["reason"], "null_concordance": scope["null_concordance"],
    }  # fmt: skip
