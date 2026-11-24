"""The effect features and the effects table: the model's mean contribution per EDA group beside
EDA's lift by the same groups (docs/components/evaluation.md "The explanation tables"; drawn by
the model results report's view 10 and the effect features' partial dependence by view 16,
both in `views_explain.py`).

`effect_features` names the features the effect views draw, from the per-run ledger and EDA's
key features alone (`key_features`, from the `stage2/` ledger). `effect_table` receives
Evaluation's explanation sample (`contributions`' sampled rows: one row per sampled test row, the
raw feature values and `<feature>__contribution`), the run's `stage2/` copies of EDA's `bins`,
`levels` and `edges` (one row per feature and group, or per feature and edge) and each
feature's kind. It returns one row per effect feature and EDA group, in EDA's group order
(`EFFECT_COLUMNS`), and one row with only `unavailable` filled for a feature EDA gives no lift
(the view draws its scatter and says which reason). Each sample row joins the EDA group its
value falls in. A numeric (whether EDA lists it by group in `bins` or by value in `levels`) goes
by its bucket on EDA's edges, as the counts table cuts it; a numeric without edges fails loud.
A categorical goes by its level text, a level outside EDA's groups into `__other__` when EDA has
that group. A row no group covers is left out and counted. Nothing is fitted or chosen on these
numbers (`CLAUDE.md` §4.4).

The limit: EDA's `bins` stores each group's label, not its first bucket, so a group's first
bucket is read back from the lower bound its label opens with (`_lower_bound`). That depends on
how `statistics/distributions.py::range_label` writes labels, and a label matching no bucket
fails loud. The sturdier fix, EDA storing `bin_order_first` in `bins`, is an EDA schema change
left for the review.
"""

import numpy as np
import pandas as pd

from core_modelling.dataset.counts import OTHER, cap_levels
from core_modelling.reporting.charts import NULL_LABEL
from core_modelling.reporting.explain_charts import MEAN_COLUMNS, group_means
from core_modelling.run_artifacts import sample_contributions
from core_modelling.statistics.cells import group_of_bins
from core_modelling.statistics.distributions import bin_labels, bin_orders

EFFECTS = "effects"  # the table's name among Evaluation's tables
TOP_EFFECTS, MAX_EFFECTS = 10, 20  # the effect features (`effect_features`)
EFFECT_COLUMNS = ["feature", "kind", "group", "group_order", *MEAN_COLUMNS, "eda_rows", "estimate",
                  "lift", "lift_low", "lift_high", "support", "insufficient", "left_out_null",
                  "left_out_level", "unavailable"]  # fmt: skip
NOT_KEY = "not one of EDA's key features"
NO_BASE = "EDA's base is not positive, so no lift exists"


def key_features(eda_ledger: pd.DataFrame) -> list[str]:
    """EDA's key features (EDA's ranking and a person's `include`), in the ledger's order: the
    features of the `stage2/` ledger whose `key_feature` says why it is one."""
    return eda_ledger.loc[eda_ledger["key_feature"].fillna("").ne(""), "feature"].tolist()


def effect_features(run_ledger: pd.DataFrame, eda_ledger: pd.DataFrame) -> list[str]:
    """The features the effect views draw: every key feature the model uses (`key_features` of
    the `stage2/` ledger) and the model's `TOP_EFFECTS` largest by Training's out-of-fold
    contribution share, `MAX_EFFECTS` at most, the key features first when they do not all fit;
    returned largest share first."""
    used = run_ledger.loc[run_ledger["in_model"].fillna(False).astype(bool)]
    used = used.sort_values("contribution_share", ascending=False, kind="stable")[
        "feature"
    ].tolist()
    keys = [name for name in used if name in set(key_features(eda_ledger))]
    chosen = set(list(dict.fromkeys([*keys, *used[:TOP_EFFECTS]]))[:MAX_EFFECTS])
    return [name for name in used if name in chosen]


def _lower_bound(label: str) -> str:
    """The lower bound a bucket or group label opens with, its bracket kept (`[v` closed, `(v`
    open); empty for one opening at minus infinity (`< v`, `≤ v`, `all`). A by-level numeric's
    group reads its value (`value_labels`), which opens like `= v`."""
    if label == "all" or label[0] in "<≤":
        return ""
    if label[0] in "=≥":
        return "[" + label[2:]
    if label[0] == ">":
        return "(" + label[2:]
    if label[0] in "[(":
        return label.split(",")[0]
    return "[" + label


def _bucket_groups(values: pd.Series, labels: list[str], edges: np.ndarray) -> pd.Series:
    """Each value's EDA group label: its bucket on EDA's `edges` (`bin_orders`) joins the group
    whose first bucket is the last at or below it, the first buckets read from the groups'
    labels; a bucket below the first group joins it, as EDA's explorer does (`group_of_bins`);
    a missing value is `null`. `labels` are EDA's non-null group labels in bucket order."""
    starts = {_lower_bound(label): order for order, label in enumerate(bin_labels(edges))}
    unknown = [label for label in labels if _lower_bound(label) not in starts]
    if unknown:
        raise ValueError(
            f"{values.name}: EDA's groups {unknown} open at no bucket of its edges; the stage2 "
            "copy's bins and edges are not of one EDA run"
        )
    firsts = np.array([starts[_lower_bound(label)] for label in labels])
    if (np.diff(firsts) <= 0).any():
        raise ValueError(f"{values.name}: EDA's groups are not in bucket order: {labels}")
    orders = bin_orders(values, edges)
    place = group_of_bins(firsts, np.maximum(orders, 0), join_outer=True)
    named = np.where(orders < 0, NULL_LABEL, np.array(labels, dtype=object)[place])
    return pd.Series(named, index=values.index, name=values.name)


def _feature_edges(name: str, kind: str | None, edges: pd.DataFrame) -> np.ndarray | None:
    """A numeric's EDA edges in position order, None for a categorical; a numeric without edges
    in the `stage2/` copy fails loud, since its rows would otherwise read as unknown levels."""
    if kind == "categorical":
        return None
    if kind != "numeric":
        raise ValueError(f"{name} has the kind {kind!r}, neither numeric nor categorical")
    own = edges.loc[edges["feature"] == name].sort_values("position")["edge"]
    if own.empty:
        raise ValueError(f"the numeric {name} has no EDA edges in the run's stage2 copy")
    return own.to_numpy(dtype=float)


def _row_groups(values: pd.Series, groups: list[str], edges: np.ndarray | None) -> pd.Series:
    """Each sample row's EDA group label, null where none of `groups` covers it: a numeric (one
    with `edges`) by its bucket (`_bucket_groups`); a categorical (`edges` None) by its level
    text as EDA writes it, a level outside the groups `__other__` when EDA has that group; a
    missing value `null`."""
    if edges is not None:
        labels = _bucket_groups(values, [g for g in groups if g != NULL_LABEL], edges)
    else:
        labels = cap_levels(values, len(values)).astype(str)  # every level, as EDA's texts
        if OTHER in groups:
            labels = labels.where(labels.isin(groups) | labels.eq(NULL_LABEL), OTHER)
    return labels.where(labels.isin(groups)).rename(values.name)


def _with_lift_interval(groups: pd.DataFrame) -> pd.DataFrame | None:
    """EDA's group table with the lift's interval in lift units (the estimate's interval over
    EDA's base, read back as estimate / lift); None when no group has a positive lift (EDA's
    base is not positive, so no lift exists)."""
    known = groups["lift"] > 0
    if not known.any():
        return None
    base = float((groups["estimate"] / groups["lift"])[known].iloc[0])
    return groups.assign(lift_low=groups["low"] / base, lift_high=groups["high"] / base)


def _eda_groups(name: str, bins: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    """A feature's EDA group table, from `bins` or `levels` (empty in both when EDA has none:
    not one of its key features); a feature in both fails loud."""
    found = [table.loc[table["feature"] == name] for table in (bins, levels)]
    if all(len(table) for table in found):
        raise ValueError(f"{name} has rows in both EDA's bins and levels")
    return pd.concat(found, ignore_index=True)


def _feature_effects(
    sample: pd.DataFrame, name: str, groups: pd.DataFrame, edges: np.ndarray | None
) -> pd.DataFrame:
    """One feature's rows of the effects table (`EFFECT_COLUMNS`), from its EDA group table
    with the lift's interval and its edges (None for a categorical)."""
    contribution = sample_contributions(sample, [name])[name]
    labels = _row_groups(sample[name], groups["group"].tolist(), edges)
    kept = labels.notna()
    means = group_means(contribution[kept], labels[kept], groups["group"].tolist())
    null = sample[name].isna() & ~kept
    table = groups.rename(columns={"rows": "eda_rows"}).assign(
        kind="numeric" if edges is not None else "categorical",
        group_order=np.arange(len(groups)),
        left_out_null=int(null.sum()),
        left_out_level=int((~kept & ~null).sum()),
        unavailable="",
    )
    for column, source in MEAN_COLUMNS.items():
        table[column] = means[source].to_numpy()
    return table[EFFECT_COLUMNS]


def effect_table(
    contributions: pd.DataFrame,
    bins: pd.DataFrame,
    levels: pd.DataFrame,
    edges: pd.DataFrame,
    kinds: pd.Series,
    features: list[str],
) -> pd.DataFrame:
    """Per effect feature with a lift and EDA group, in `features` order and EDA's group order:
    the sample's rows and mean contribution with its 95% interval (`MEAN_COLUMNS`), EDA's rows,
    estimate, lift with its interval, support and `insufficient`, and the sample rows left out
    (`left_out_null`: a null EDA has no group for; `left_out_level`: a level outside EDA's
    groups without `__other__`), the same on each of the feature's rows, `unavailable` empty.
    A feature without EDA groups (`NOT_KEY`), or whose EDA base is not positive (`NO_BASE`),
    has one row holding only that reason in `unavailable`. `kinds` is each feature's kind by
    name (`numeric` or `categorical`, the `stage2/` ledger's), so a numeric never reads as a
    categorical for want of edges (`_feature_edges`)."""
    parts = []
    for name in features:
        groups = _eda_groups(name, bins, levels)
        lift = _with_lift_interval(groups)
        if lift is None:
            reason = NO_BASE if len(groups) else NOT_KEY
            parts.append(pd.DataFrame([{"feature": name, "unavailable": reason}],
                                      columns=EFFECT_COLUMNS))  # fmt: skip
            continue
        numeric = _feature_edges(name, kinds.get(name), edges)
        parts.append(_feature_effects(contributions, name, lift.reset_index(drop=True), numeric))
    if not parts:
        return pd.DataFrame(columns=EFFECT_COLUMNS)
    return pd.concat(parts, ignore_index=True)
