"""Feature Checks' five steps over EDA's artifacts, in their fixed order (feature_checks.md
"The finding table").

Each step is one function of what every step reads (`CheckInputs`, which `inputs.check_inputs`
gathers from EDA's artifacts) and its own parameters and returns a `StepResult`: its findings
(`FINDING_COLUMNS`; a flag or a note as `FINDINGS` says, the rows built with `findings.py`'s row
builders), its ledger columns for every read candidate, the findings that cannot exist with their
reasons, decided before computing (D-035), and, for redundancy, the clusters table. A step
judges and changes nothing: a flag holds a feature out of training until a person keeps or
excludes it, a note never does (D-134).

No check skips a feature for low support (Q540): each computes on the support there is, and a
finding with an SE states in its detail its support in effective clients and its SE, and "not
significant at this support" when its value is not more than 2 SE past its threshold (`_evidence`;
4 for a best-order value, EDA's margin for the same in-sample gain), the SE taken at the threshold:
an SE at an estimate near 0 or 1 is tiny on any support. A noisy flag then holds the feature and a
person keeps it. "Window" is the window periods' cells pooled, the ledger's `*_window` columns.
`STEPS` maps each step's name to its function in the run order.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core_modelling.config.schema import Leakage, Quality, Redundancy, Stability, TimeAlignment
from core_modelling.dataset.counts import POOLED_LEVEL_CAP
from core_modelling.feature_checks.findings import (
    FINDING_COLUMNS,
    UNAVAILABLE_COLUMNS,
    finding_frame,
    finding_rows,
    stack_parts,
    unavailable_rows,
)
from core_modelling.feature_checks.inputs import CheckInputs
from core_modelling.feature_checks.measures import effective_se, lagged_concordance, period_psi
from core_modelling.statistics.association import cluster_features, explained_by_others
from core_modelling.statistics.cells import (
    null_table,
    pool_periods,
    shares,
    support_by_bin,
    target_shares,
)
from core_modelling.statistics.concordance import NON_MONOTONE_SE_MULTIPLE, cochran_q
from core_modelling.statistics.distributions import new_level_share
from core_modelling.statistics.scope import NULL_SHARE_RANGE, feature_se, null_concordance
from core_modelling.tasks import TASK_SPECS

CLUSTER_COLUMNS = ["cluster", "feature", "kind", "concordance", "association_with_best",
                   "explained_by_others", "unavailable"]  # fmt: skip
NO_NULL_ROWS = "not available: no labelled null or no labelled non-null window row"
NO_LATEST = "not available: no period after the validation period"
FEW_PERIODS = "not available: fewer than two window periods with a concordance"
NOT_SIGNIFICANT = "not significant at this support"
FLIPPED = "read one period earlier it orders clients the other way"


@dataclass(frozen=True, eq=False)
class StepResult:
    """One step's output: `findings` (`FINDING_COLUMNS`), `columns` (`feature` and the step's
    ledger columns, one row per read candidate), `unavailable` (`feature, finding, reason`) and
    its own `tables` (redundancy's `clusters`)."""

    findings: pd.DataFrame
    columns: pd.DataFrame
    unavailable: pd.DataFrame
    tables: dict[str, pd.DataFrame]


def _window_signs(ranking: pd.DataFrame) -> dict[str, int]:
    """Per feature, the raw sign of the window's D (+1, −1, 0 without a window concordance): the
    direction a lagged concordance is read in. The ledger's `direction` is the snapshot's and
    null below 2 SE, so it cannot give it."""
    return dict(zip(ranking["feature"], ranking["raw_sign_window"].astype(int), strict=True))


def _evidence(support: float, se: float, past: float, noun: str, multiple: float = 2) -> str:
    """A finding's support in effective `noun` and its SE (the caller's, at the threshold), with
    `NOT_SIGNIFICANT` unless the value is more than `multiple` SE past its threshold (`past`:
    the distance on the side it fires)."""
    text = f"support {support:,.0f} effective {noun}, SE {se:.3f}"
    return text if past > multiple * se else f"{text}; {NOT_SIGNIFICANT}"


def _joined(*parts: pd.Series) -> pd.Series:
    """Per row, the parts' non-empty texts joined by '; '."""
    frame = pd.concat(parts, axis=1).fillna("")
    return frame.apply(lambda row: "; ".join(text for text in row if text), axis=1)


def check_quality(inputs: CheckInputs, params: Quality) -> StepResult:
    """The `quality` findings. All-null, constant, high-missing and near-constant are exclusive
    in that order: a feature gets the first that applies, so an all-null column is neither
    constant nor high-missing. Null counts as a value, so one value plus nulls is not constant
    (N4). Near-constant's detail is the minority's effect where it exists (`_minority_effect`,
    the rare-value rule's): a 99%-zero flag can carry real lift at low prevalence (Q440).
    High-cardinality and the two null notes apply independently; `nulls_informative` needs a
    labelled null and non-null window row (`_null_rows_exist`)."""
    ledger = inputs.ledger
    missing, dominant = ledger["missing_share_window"], ledger["dominant_share_window"]
    near = dominant >= params.dominant_share_max
    exclusive = [
        ("quality.all_null", missing == 1, missing, 1.0, ""),
        ("quality.constant", dominant == 1, dominant, 1.0, ""),
        ("quality.high_missing", missing >= params.missing_share_max, missing,
         params.missing_share_max, ""),
        ("quality.near_constant", near, dominant, params.dominant_share_max,
         _minority_details(inputs, near)),
    ]  # fmt: skip
    taken = pd.Series(False, index=ledger.index)
    parts = []
    for name, fires, value, threshold, detail in exclusive:
        parts.append(finding_rows(name, ledger, fires & ~taken, value, threshold, detail))
        taken |= fires
    levels = ledger["levels"]
    wide = (ledger["kind"] == "categorical") & (levels > params.max_levels)
    parts.append(finding_rows("quality.high_cardinality", ledger, wide, levels, params.max_levels))
    parts.append(_nulls_may_be_zeros(ledger, params))
    nulls, exists = ledger["null_concordance_window"], _null_rows_exist(inputs)
    informative = (nulls >= params.nulls_informative_min) & (nulls < inputs.null_concordance_max)
    parts.append(_nulls_informative(inputs, exists & informative, params.nulls_informative_min))
    name = "quality.nulls_informative"
    absent = unavailable_rows(name, ledger.loc[nulls.notna() & ~exists, "feature"], NO_NULL_ROWS)
    return _result(ledger, parts, [absent])


def _nulls_may_be_zeros(ledger: pd.DataFrame, params: Quality) -> pd.DataFrame:
    """The `nulls_may_be_zeros` note: a numeric with many nulls and almost never a zero among its
    values (N15); the detail gives the zero share."""
    rule = params.nulls_may_be_zeros
    missing, zeros = ledger["missing_share_window"], ledger["zero_share_window"]
    fires = (ledger["kind"] == "numeric") & (missing >= rule.missing_min) & zeros.notna()
    fires &= zeros <= rule.zero_share_max
    detail = zeros.map(lambda share: f"zero share among the values {share:.2%}")
    return finding_rows(
        "quality.nulls_may_be_zeros", ledger, fires, missing, rule.missing_min, detail
    )


def _nulls_informative(inputs: CheckInputs, fires: pd.Series, threshold: float) -> pd.DataFrame:
    """The `nulls_informative` notes: each detail names its null set (`_null_sets`) and its
    evidence (`_null_evidence`); the rows ordered by set, largest first, the features alone
    last, each in ledger order."""
    ledger, nulls = inputs.ledger, inputs.ledger["null_concordance_window"]
    sets = _null_sets(inputs, ledger.loc[fires, "feature"])
    named = ledger["feature"].map({f: _null_set_text(*place) for f, place in sets.items()})
    detail = _joined(named, _null_evidence(inputs, fires, nulls, threshold))
    rows = finding_rows("quality.nulls_informative", ledger, fires, nulls, threshold, detail)
    number = rows["feature"].map({f: n for f, (n, _) in sets.items()})
    return rows.iloc[np.argsort(number.fillna(np.inf).to_numpy(), kind="stable")]


def _null_set_text(number: int, size: int) -> str:
    """A `nulls_informative` detail's null set, e.g. "null set 1: the same null counts per period
    and target as 36 other features" (equal counts, in practice one null set of rows)."""
    others = f"{size - 1} other feature" + ("s" if size > 2 else "")
    return f"null set {number}: the same null counts per period and target as {others}"


def _null_sets(inputs: CheckInputs, features: pd.Series) -> dict[str, tuple[int, int]]:
    """Per feature of `features` sharing its null set with another, the set's number and size.

    Features with the same null counts in every period and target bin of EDA's current cells
    (the window's labelled and unlabelled rows, the gap and latest periods' too) share one null
    set: in practice the same null rows, so the same null concordance; the unlabelled and later
    counts tell apart two sets that coincide on the labelled counts. Sets are numbered 1… by
    size, largest first, ties in `features`' order; a feature alone is left out.
    """
    cells = inputs.cells
    nulls = cells.loc[
        cells["feature"].isin(features) & ~cells["lagged"] & cells["is_null"] & (cells["n"] > 0)
    ]
    target = nulls["target_bin"].astype(object).where(nulls["target_bin"].notna(), "unlabelled")
    nulls = nulls.assign(target=target.astype(str))
    keys = {
        name: tuple(sorted(zip(rows["period"], rows["target"], rows["n"], strict=True)))
        for name, rows in nulls.groupby("feature")
    }
    groups: dict[tuple, list[str]] = {}
    for name in features:
        groups.setdefault(keys[name], []).append(name)
    shared = sorted((members for members in groups.values() if len(members) > 1), key=len,
                    reverse=True)  # fmt: skip
    return {name: (n, len(members)) for n, members in enumerate(shared, 1) for name in members}


def _null_evidence(
    inputs: CheckInputs, fires: pd.Series, values: pd.Series, threshold: float
) -> pd.Series:
    """Per read candidate `fires` marks, the null indicator concordance's `_evidence` against
    `threshold` ('' elsewhere): its SE at the threshold as EDA computes a window's
    (`effective_se`) on every labelled window row, null or not."""
    noun = TASK_SPECS[inputs.task]["support_name"]
    evidence = pd.Series("", index=inputs.ledger.index)
    pools = _window_pools(inputs, inputs.ledger.loc[fires, "feature"])
    for i in inputs.ledger.index[fires]:
        pooled = pools[inputs.ledger.at[i, "feature"]]
        table = null_table(pooled)
        events = float(support_by_bin(pooled).sum())
        # the indicator is no encoded level, so no cross-fit inflation: kind "numeric"
        se, support = effective_se(
            threshold, events, table.sum() - events, table.sum(axis=0) / table.sum(),
            kind="numeric", task=inputs.task, clients=inputs.clients,
        )  # fmt: skip
        evidence[i] = _evidence(support, se, values[i] - threshold, noun)
    return evidence


def _minority_details(inputs: CheckInputs, marked: pd.Series) -> pd.Series:
    """Per read candidate, the minority effect's detail for the ones `marked` ('' elsewhere and
    where the effect does not exist)."""
    features = inputs.ledger.loc[marked, "feature"]
    effects = {
        name: _minority_effect(pooled, inputs)[0]
        for name, pooled in _window_pools(inputs, features).items()
    }
    details = {name: effect["detail"] for name, effect in effects.items() if effect}
    return inputs.ledger["feature"].map(details).fillna("")


def _null_rows_exist(inputs: CheckInputs) -> pd.Series:
    """Per read candidate, whether its window holds a labelled null row and a labelled non-null
    row: without both a null concordance cannot exist (N15)."""
    cells = inputs.cells
    window = cells["period"].isin(inputs.periods["window"])
    labelled = cells.loc[~cells["lagged"] & window & cells["target_bin"].notna()]
    counts = labelled.groupby(["feature", "is_null"])["n"].sum().unstack(fill_value=0)
    counts = counts.reindex(index=inputs.ledger["feature"], columns=[False, True], fill_value=0)
    return pd.Series((counts > 0).all(axis=1).to_numpy(), index=inputs.ledger.index)


def check_leakage(inputs: CheckInputs, params: Leakage) -> StepResult:
    """The `leakage` flags: a window concordance this strong (`_too_strong`; EDA's reason where
    it has none), a null indicator this strong (where a labelled null and non-null row exist;
    below EDA's null-share range read here, `_nulls_below_range`), and a minority beside a
    dominant value whose rate (mean) is far above the dominant value's (`_minority_effect`)."""
    ledger = inputs.ledger
    exists = _null_rows_exist(inputs)
    below, below_values = _nulls_below_range(inputs, exists)
    nulls = ledger["null_concordance_window"].fillna(below_values)
    leak = exists & (nulls >= params.null_concordance_max)
    read_below = ledger["missing_share_window"].map(
        lambda s: f"read below EDA's null-share range (missing share {s:.2%})"
    )
    evidence = _null_evidence(inputs, leak, nulls, params.null_concordance_max)
    rare, rare_unavailable = _rare_value_leaks(inputs, params.rare_effect_max)
    parts = [
        _too_strong(inputs, params.concordance_max),
        finding_rows("leakage.missingness_leak", ledger, leak, nulls, params.null_concordance_max,
                     _joined(read_below.where(below, ""), evidence)),
        rare,
    ]  # fmt: skip
    absent = ledger.loc[(nulls.notna() | below) & ~exists, "feature"]
    unavailable = [
        _eda_unavailable("leakage.too_strong", inputs, ledger["concordance_window"].isna()),
        unavailable_rows("leakage.missingness_leak", absent, NO_NULL_ROWS),
        rare_unavailable,
    ]
    return _result(ledger, parts, unavailable)


def _too_strong(inputs: CheckInputs, threshold: float) -> pd.DataFrame:
    """The `too_strong` rows: the higher of the window's concordance and its best order (EDA's
    `concordance_best_order_window`, NaN skipped: a U-shaped leak is strong only in best order)
    at or above `threshold`, the detail naming the best order when it is the higher, and the
    `_evidence` of the window SE in effective clients at the threshold (`effective_se`), a
    best-order value needing `NON_MONOTONE_SE_MULTIPLE` SE: it is fitted in sample."""
    ledger = inputs.ledger
    plain = ledger["concordance_window"]
    best = ledger["feature"].map(
        inputs.ranking.set_index("feature")["concordance_best_order_window"]
    )
    value = pd.concat([plain, best], axis=1).max(axis=1)
    fires = value >= threshold
    order = plain.map(lambda v: f"best order; in bin order {v:.3f}").where(best > plain, "")
    noun = TASK_SPECS[inputs.task]["support_name"]
    evidence = pd.Series("", index=ledger.index)
    pools = _window_pools(inputs, ledger.loc[fires, "feature"])
    for i in ledger.index[fires]:
        pooled = pools[ledger.at[i, "feature"]]
        counts = shares(pooled)
        se, support = effective_se(
            threshold, counts["events"], counts["non_events"], target_shares(pooled),
            kind=ledger.at[i, "kind"], task=inputs.task, clients=inputs.clients,
        )  # fmt: skip
        multiple = NON_MONOTONE_SE_MULTIPLE if best[i] > plain[i] else 2
        evidence[i] = _evidence(support, se, value[i] - threshold, noun, multiple)
    detail = _joined(order, evidence)
    return finding_rows("leakage.too_strong", ledger, fires, value, threshold, detail)


def _nulls_below_range(inputs: CheckInputs, exists: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Per read candidate, whether its window's missing share is above 0 but below EDA's
    `NULL_SHARE_RANGE`, where EDA reads no null concordance, and that concordance computed as EDA
    computes it where a labelled null and non-null row `exists` and the labelled rows hold two
    target values (`null_concordance`, NaN elsewhere). A field blanked when a client converts
    has a null share near the prevalence, often below the range."""
    ledger = inputs.ledger
    missing = ledger["missing_share_window"]
    below = (missing > 0) & (missing < NULL_SHARE_RANGE[0])
    below &= ledger["null_concordance_window"].isna()
    values = pd.Series(np.nan, index=ledger.index)
    pools = _window_pools(inputs, ledger.loc[below & exists, "feature"])
    for i in ledger.index[below & exists]:
        values[i] = null_concordance(pools[ledger.at[i, "feature"]])
    return below, values


def _eda_unavailable(name: str, inputs: CheckInputs, marked: pd.Series) -> pd.DataFrame:
    """`unavailable` rows of finding `name` for the read candidates `marked`, which have no
    window concordance, with EDA's reason (the ranking table's `unavailable`)."""
    absent = inputs.ledger.loc[marked, "feature"]
    reasons = absent.map(inputs.ranking.set_index("feature")["unavailable"])
    return unavailable_rows(name, absent, reasons)


def _rare_value_leaks(inputs: CheckInputs, threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`rare_value_leak` over every read candidate: the finding's rows (a minority effect at or
    above `threshold`, its detail with the effect's `_evidence`) and the dominated features
    whose effect is not available."""
    noun = TASK_SPECS[inputs.task]["support_name"]
    found, reasons = [], []
    for name, pooled in _window_pools(inputs, inputs.ledger["feature"]).items():
        effect, reason = _minority_effect(pooled, inputs)
        reasons += [(name, reason)] if reason else []
        if not effect or effect["value"] < threshold:
            continue
        evidence = _evidence(effect["support"], effect["se"], effect["value"] - threshold, noun)
        found.append({"feature": name, "value": effect["value"],
                      "detail": f"{effect['detail']}; {evidence}"})  # fmt: skip
    rows = pd.DataFrame(found, columns=["feature", "value", "detail"])
    reasons = pd.DataFrame(reasons, columns=["feature", "reason"])
    name = "leakage.rare_value_leak"
    return (
        finding_frame(name, rows, threshold),
        unavailable_rows(name, reasons["feature"], reasons["reason"]),
    )


def _window_pools(inputs: CheckInputs, features: pd.Series) -> dict[str, pd.DataFrame]:
    """Each of `features`' current cells pooled over the window periods, in `features`' order."""
    cells = inputs.cells
    current = cells.loc[~cells["lagged"] & cells["feature"].isin(features)]
    by_feature = dict(tuple(current.groupby("feature")))
    return {name: pool_periods(by_feature[name], inputs.periods["window"]) for name in features}


def _minority_effect(pooled: pd.DataFrame, inputs: CheckInputs) -> tuple[dict | None, str]:
    """One feature's minority effect on its pooled window cells (`value`, `se`, `support`,
    `detail`) or None, and '' or why it cannot exist, decided before computing (D-035).

    Over the filled (non-null) rows only, the nulls being the null concordance's business: when
    one value holds at least `dominant_share_min` of them and another exists, every other value
    pooled is the minority. Its effect is the task's `rare_effect` of the minority's labelled
    rows against the dominant value's (Cohen's h on the rates, d on the means; signed, so a
    minority below the dominant value reads negative), its SE on both sides' rows in effective
    clients and its support the minority's events in effective clients (`_effective_side`): a
    client labelled in several periods of the pooled window counts about once (A28). Computed
    on any support (Q540); `rare_effect_unavailable` names what cannot exist. None and '' when
    no value dominates.
    """
    dominant = _dominant_value(pooled, inputs.dominant_share_min)
    if dominant is None:
        return None, ""
    label, minority_share = dominant
    spec = TASK_SPECS[inputs.task]
    filled = pooled.loc[pooled["target_bin"].notna() & ~pooled["is_null"]]
    in_dominant = filled["bin"] == label
    minority, common = filled.loc[~in_dominant], filled.loc[in_dominant]
    reason = spec["rare_effect_unavailable"](minority, common)
    if reason:
        return None, f"not available: {reason}"
    (support, minority_rows), (_, common_rows) = (
        _effective_side(side, inputs) for side in (minority, common)
    )
    value, se = spec["rare_effect"](minority, common, (minority_rows, common_rows))
    noun, show = spec["estimate_noun"], spec["estimate_format"].format
    detail = (
        f"the {minority_share:.1%} of filled rows outside the dominant value {label}: {noun} "
        f"{show(_estimate(minority))} against {show(_estimate(common))}, "
        f"{spec['rare_effect_name']} {value:.2f}"
    )
    return {"value": value, "se": se, "support": support, "detail": detail}, ""


def _effective_side(side: pd.DataFrame, inputs: CheckInputs) -> tuple[float, float]:
    """One side's labelled cells in effective clients (`client_support`): its events (the
    support: positive events, or units with a non-zero target) and all its rows."""
    events = float(support_by_bin(side).sum())
    effective = TASK_SPECS[inputs.task]["client_support"](
        events, side["n"].sum() - events, inputs.clients
    )
    return float(effective[0]), float(sum(effective))


def _dominant_value(pooled: pd.DataFrame, share_min: float) -> tuple[str, float] | None:
    """The filled bin holding at least `share_min` of the filled rows, labelled or not, with the
    share of filled rows outside it; None when no bin does or no other filled row exists."""
    rows = pooled.loc[~pooled["is_null"]].groupby("bin")["n"].sum()
    rows = rows[rows > 0]
    if rows.empty or not share_min <= rows.max() / rows.sum() < 1:
        return None
    return rows.idxmax(), float(1 - rows.max() / rows.sum())


def _estimate(labelled: pd.DataFrame) -> float:
    """The rate (mean) of labelled cells; NaN without rows."""
    rows = labelled["n"].sum()
    return float(labelled["sum_y"].sum() / rows) if rows else np.nan


def check_time_alignment(inputs: CheckInputs, params: TimeAlignment) -> StepResult:
    """The `time_alignment` flags, on the features with window signal only (`concordance_min`;
    without signal there is nothing to lose or to stamp): the signal a one-period lag keeps,
    `signal_kept = (lagged − 0.5) / (concordance_window − 0.5)`, the lagged value read in the
    window's direction over the window after its first period (whose lag EDA's rows do not
    hold), so a flip reads below 0.5 and `signal_kept` may go negative, on whatever support the
    lagged rows hold (`_drop_details` states it); and the share of clients whose value never
    changes in the window.

    Known limit: the numerator is read on the rows with a lagged value over the window's later
    periods, the denominator is `concordance_window` over every window period (the spec's rule),
    so a population that changes over the window shifts `signal_kept` slightly.
    """
    ledger = inputs.ledger
    lagged = _lagged_values(inputs)
    window = ledger["concordance_window"]
    # `concordance_min` may be 0.5, and a window at exactly 0.5 has no signal to keep
    gated = (window >= params.concordance_min) & (window > 0.5)
    kept = ((lagged["value"] - 0.5) / (window - 0.5)).where(gated)
    drop = kept < params.signal_kept_min
    constant = ledger["feature"].map(inputs.client_constant.set_index("feature")["constant_share"])
    stamped = gated & (constant >= params.constant_clients_min)
    parts = [
        finding_rows("time_alignment.lagged_signal_drop", ledger, drop, kept,
                     params.signal_kept_min,
                     _drop_details(inputs, lagged, drop, kept, params.signal_kept_min)),
        finding_rows("time_alignment.client_constant", ledger, stamped, constant,
                     params.constant_clients_min),
    ]  # fmt: skip
    unlagged, unknown = gated & (lagged["reason"] != ""), gated & constant.isna()
    unavailable = [
        unavailable_rows("time_alignment.lagged_signal_drop", ledger.loc[unlagged, "feature"],
                     lagged.loc[unlagged, "reason"]),
        unavailable_rows("time_alignment.client_constant", ledger.loc[unknown, "feature"],
                     "not available: no client with two non-null values in the window"),
    ]  # fmt: skip
    columns = {
        "lagged_concordance": lagged["value"],
        "signal_kept": kept,
        "constant_share": constant,
    }
    return _result(ledger, parts, unavailable, columns)


def _drop_details(
    inputs: CheckInputs, lagged: pd.DataFrame, drop: pd.Series, kept: pd.Series, threshold: float
) -> pd.Series:
    """Per read candidate `drop` marks, the `lagged_signal_drop` detail ('' elsewhere): the share
    with no lagged value, `FLIPPED` when the lagged value is more than 2 SE below 0.5 (the SE at
    0.5), and the `_evidence` of `signal_kept` below `threshold`, its SE the lagged SE at the
    value the threshold implies, `0.5 + threshold · (concordance_window − 0.5)`, over
    `concordance_window − 0.5` (the window's own noise left out)."""
    noun = TASK_SPECS[inputs.task]["support_name"]
    window = inputs.ledger["concordance_window"]
    no_lag = lagged["missing_share"].map(
        lambda s: f"no lagged value on {s:.1%} of the window's rows after its first period"
    )
    flipped, evidence = pd.Series("", index=lagged.index), pd.Series("", index=lagged.index)
    for i in lagged.index[drop]:
        null_se, _ = _lagged_se(inputs, lagged, i, 0.5)
        flipped[i] = FLIPPED if lagged.at[i, "value"] < 0.5 - 2 * null_se else ""
        se, support = _lagged_se(inputs, lagged, i, 0.5 + threshold * (window[i] - 0.5))
        evidence[i] = _evidence(support, se / (window[i] - 0.5), threshold - kept[i], noun)
    return _joined(no_lag.where(drop, ""), flipped, evidence)


def _lagged_se(
    inputs: CheckInputs, lagged: pd.DataFrame, i: int, value: float
) -> tuple[float, float]:
    """Row `i`'s lagged concordance SE at `value` and its support, in effective clients
    (`effective_se` on the lagged counts)."""
    return effective_se(
        value, lagged.at[i, "events"], lagged.at[i, "non_events"],
        lagged.at[i, "target_bin_shares"], kind=inputs.ledger.at[i, "kind"], task=inputs.task,
        clients=inputs.clients,
    )  # fmt: skip


def _lagged_values(inputs: CheckInputs) -> pd.DataFrame:
    """Per read candidate, `measures.lagged_concordance` (`value`, `missing_share`, `reason`,
    `events`, `non_events`, `target_bin_shares`)."""
    by_feature = dict(tuple(inputs.cells.groupby("feature")))
    signs = _window_signs(inputs.ranking)
    ledger = inputs.ledger
    settings = {"task": inputs.task, "window": inputs.periods["window"],
                "prior_rows": inputs.prior_rows, "exact": inputs.exact}  # fmt: skip
    records = [
        lagged_concordance(by_feature[name], kind, sign=signs[name], **settings)
        for name, kind in zip(ledger["feature"], ledger["kind"], strict=True)
    ]
    columns = ["value", "missing_share", "reason", "events", "non_events", "target_bin_shares"]
    return pd.DataFrame(records, index=ledger.index, columns=columns)


def check_stability(inputs: CheckInputs, params: Stability) -> StepResult:
    """The `stability` findings: a concordance whose power differs across the window's periods
    (Cochran's Q with an effect-size condition relative to the signal, the range at least
    `concordance_range_min` × |`concordance_window` − 0.5| and never below
    `concordance_range_floor`, a flag); PSI on named periods, from
    the window's first to its last period and from the window's last to the latest period
    (whatever `eda.snapshot` says), each a flag from `psi_max` and else a note from
    `psi_note_min`, so a feature raises one of the two; and a categorical's latest share of
    levels unseen in every window period (a note)."""
    ledger, window, latest = inputs.ledger, inputs.periods["window"], inputs.periods["latest"]
    q = _heterogeneity(inputs)
    signal = (ledger["concordance_window"] - 0.5).abs()
    unstable = q["heterogeneity_p"] <= params.heterogeneity_p_max
    needed = (params.concordance_range_min * signal).clip(lower=params.concordance_range_floor)
    unstable &= q["concordance_range"] >= needed
    noun = TASK_SPECS[inputs.task]["support_name"]
    tested = (
        q["concordance_range"].map(lambda r: f"range {r:.3f}") + " over " + q["tested"]
        + q["least_support"].map(lambda n: f"; support {n:,.0f} {noun} in the thinnest period")
    )  # fmt: skip
    drift, drift_unavailable = _drift(inputs)
    first_last = f"{window[0]} → {window[-1]}"
    last_latest = f"{window[-1]} → {latest[0]}" if latest else ""
    psi_window, psi_latest = drift["psi_window"], drift["psi_latest"]
    new = drift["new_level_share"]
    window_large, latest_large = psi_window >= params.psi_max, psi_latest >= params.psi_max
    window_noted = (psi_window >= params.psi_note_min) & ~window_large
    latest_noted = (psi_latest >= params.psi_note_min) & ~latest_large
    parts = [
        finding_rows("stability.concordance_unstable", ledger, unstable, q["heterogeneity_p"],
                     params.heterogeneity_p_max, tested),
        finding_rows("stability.psi_window_large", ledger, window_large, psi_window, params.psi_max,
                     first_last),
        finding_rows("stability.psi_latest_large", ledger, latest_large, psi_latest, params.psi_max,
                     last_latest),
        finding_rows("stability.psi_window", ledger, window_noted, psi_window, params.psi_note_min,
                     first_last),
        finding_rows("stability.psi_latest", ledger, latest_noted, psi_latest, params.psi_note_min,
                     last_latest),
        finding_rows("stability.new_levels", ledger, new >= params.new_level_share_max, new,
                     params.new_level_share_max,
                     f"{latest[0]} against the window" if latest else ""),
    ]  # fmt: skip
    name, untested = "stability.concordance_unstable", q["heterogeneity_p"].isna()
    absent = ledger["concordance_window"].isna()
    unavailable = [
        _eda_unavailable(name, inputs, untested & absent),
        unavailable_rows(name, ledger.loc[untested & ~absent, "feature"], FEW_PERIODS),
        *drift_unavailable,
    ]
    columns = dict(pd.concat([q, drift], axis=1)[STEP_COLUMNS["stability"]].items())
    return _result(ledger, parts, unavailable, columns)


def _heterogeneity(inputs: CheckInputs) -> pd.DataFrame:
    """Per read candidate over every window period with a concordance in EDA's
    `concordance_per_period` (below `strata.min_events` support included: its `insufficient` is
    a display mark, Q540): Cochran's Q p-value (weights `_period_ses`), the concordances' range,
    the periods tested and the thinnest one's support; NaN and '' with fewer than two such
    periods. The periods share clients, so their concordances are positively correlated and Q,
    which assumes them independent, is conservative: fewer flags than the nominal level."""
    table = inputs.concordance_per_period
    available = table.loc[(table["unavailable"] == "") & table["concordance"].notna()]
    by_feature = dict(tuple(available.groupby("feature")))
    ledger = inputs.ledger
    records = []
    for name, kind, window in zip(ledger["feature"], ledger["kind"], ledger["concordance_window"],
                                  strict=True):  # fmt: skip
        rows = by_feature.get(name)
        if rows is None or len(rows) < 2:
            records.append({"heterogeneity_p": np.nan, "concordance_range": np.nan, "tested": "",
                            "least_support": np.nan})  # fmt: skip
            continue
        values = rows["concordance"].to_numpy(dtype=float)
        records.append({
            "heterogeneity_p": cochran_q(values, _period_ses(rows, window, kind, inputs.task)),
            "concordance_range": float(values.max() - values.min()),
            "tested": ", ".join(rows["period"]),
            "least_support": float(rows["support"].min()),
        })  # fmt: skip
    return pd.DataFrame(records, index=ledger.index)


def _period_ses(rows: pd.DataFrame, window: float, kind: str, task: str) -> np.ndarray:
    """Each period's SE for Cochran's Q: Hanley–McNeil at the window's concordance on the
    period's own rows (one per client, so no client scaling), a categorical's times
    `CROSS_FIT_SE_INFLATION`; at its own value a thin period near 0 or 1 would get the SE floor
    and dominate Q. A task whose SE does not depend on the value (`period_se_at_window_value`
    false: Kendall's null SE) keeps EDA's `se`."""
    if not TASK_SPECS[task]["period_se_at_window_value"]:
        return rows["se"].to_numpy(dtype=float)
    # `feature_se` without `clients`: no client scaling; Hanley–McNeil reads no target shares,
    # which the per-period table does not hold
    ses = [
        feature_se(window, support, total - support, None, kind, task)
        for support, total in zip(rows["support"], rows["rows"], strict=True)
    ]
    return np.array(ses)


def _drift(inputs: CheckInputs) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """Per read candidate: `psi_window`, `psi_latest` and a categorical's `new_level_share`, NaN
    where not available, and the reasons, decided before computing (D-035): for each PSI's flag
    and note alike a one-period window or no latest period; for `new_levels` also a categorical
    over the level ceiling (seen and unseen levels cannot be told apart there)."""
    ledger, window, latest = inputs.ledger, inputs.periods["window"], inputs.periods["latest"]
    by_feature = dict(tuple(inputs.cells.loc[~inputs.cells["lagged"]].groupby("feature")))
    features, categorical = ledger["feature"], ledger["kind"] == "categorical"
    countable = categorical & ~features.isin(inputs.over_ceiling)
    columns = ["psi_window", "psi_latest", "new_level_share"]
    values = pd.DataFrame(np.nan, index=ledger.index, columns=columns)
    for i, name, kind in zip(ledger.index, features, ledger["kind"], strict=True):
        cells = by_feature[name]
        if len(window) > 1:
            values.at[i, "psi_window"] = period_psi(cells, kind, window[0], window[-1])
        if latest:
            values.at[i, "psi_latest"] = period_psi(cells, kind, window[-1], latest[0])
        if latest and countable[i]:
            values.at[i, "new_level_share"] = _new_level_share(cells, window, latest[0])
    unavailable = []
    if len(window) < 2:
        one = "not available: a one-period window"
        names = ["stability.psi_window_large", "stability.psi_window"]
        unavailable += [unavailable_rows(name, features, one) for name in names]
    if not latest:
        names = ["stability.psi_latest_large", "stability.psi_latest"]
        unavailable += [unavailable_rows(name, features, NO_LATEST) for name in names]
        unavailable.append(
            unavailable_rows("stability.new_levels", features[categorical], NO_LATEST)
        )
    else:
        over = f"not available: more than {POOLED_LEVEL_CAP:,} window levels"
        over_ceiling = features[categorical & ~countable]
        unavailable.append(unavailable_rows("stability.new_levels", over_ceiling, over))
    return values, unavailable


def _new_level_share(cells: pd.DataFrame, window: list[str], latest: str) -> float:
    """The latest period's share of rows in bins holding no row in any window period: `__new__`
    always, null only when no window period had a null (N5)."""
    in_window = cells.loc[cells["period"].isin(window) & (cells["n"] > 0), "bin"]
    return new_level_share(cells, list(in_window.unique()), latest)


def check_redundancy(inputs: CheckInputs, params: Redundancy) -> StepResult:
    """The `redundancy` notes on EDA's snapshot association table: a numeric pair with |Spearman|
    at or above `correlation_max`, a pair with a categorical member (Cramér's V or η) at or above
    `association_max`, one row per member; and the clusters (`cluster_features` cut at
    `correlation_max`), each member with its association with the best member and
    `explained_by_others`."""
    ledger = inputs.ledger
    read = ledger["feature"]
    table = inputs.correlation.loc[
        inputs.correlation["a"].isin(read) & inputs.correlation["b"].isin(read)
    ]
    strength, spearman = table["statistic"].abs(), table["method"] == "spearman"
    correlated = table.loc[spearman & (strength >= params.correlation_max)]
    associated = table.loc[~spearman & (strength >= params.association_max)]
    parts = [
        _pair_findings("redundancy.correlated_pair", correlated, read, params.correlation_max),
        _pair_findings("redundancy.associated_pair", associated, read, params.association_max),
    ]
    clusters = _cluster_table(table, ledger, params.correlation_max)
    partners = _partners(pd.concat([correlated, associated]), read)
    by_member = clusters.set_index("feature")
    columns = {
        "cluster": pd.array(read.map(by_member["cluster"]), dtype="Int64"),
        "explained_by_others": read.map(by_member["explained_by_others"]).astype(float),
        "partners": partners,
    }
    return _result(ledger, parts, [], columns, {"clusters": clusters})


def _pair_findings(
    name: str, pairs: pd.DataFrame, order: pd.Series, threshold: float
) -> pd.DataFrame:
    """One finding row per feature of `pairs`, in `order`: its largest |statistic| and its
    partners with their statistic, strongest first."""
    by_feature = dict(tuple(_pair_sides(pairs).groupby("feature")))
    rows = []
    for feature in [f for f in order if f in by_feature]:
        sides = by_feature[feature]
        partners = zip(sides["partner"], sides["statistic"], strict=True)
        detail = ", ".join(f"{partner} {statistic:.3f}" for partner, statistic in partners)
        rows.append({"feature": feature, "value": sides["strength"].iloc[0], "detail": detail})
    frame = pd.DataFrame(rows, columns=["feature", "value", "detail"])
    return finding_frame(name, frame, threshold)


def _partners(pairs: pd.DataFrame, order: pd.Series) -> list[list[str]]:
    """Per feature of `order`, the features it pairs with above either threshold, strongest
    first."""
    by_feature = _pair_sides(pairs).groupby("feature")["partner"].agg(list).to_dict()
    return [by_feature.get(feature, []) for feature in order]


def _pair_sides(pairs: pd.DataFrame) -> pd.DataFrame:
    """Each pair once from each side (`feature, partner, statistic, strength` = |statistic|),
    strongest first, ties by partner."""
    sides = pd.concat([
        pairs[["a", "b", "statistic"]].set_axis(["feature", "partner", "statistic"], axis=1),
        pairs[["b", "a", "statistic"]].set_axis(["feature", "partner", "statistic"], axis=1),
    ])  # fmt: skip
    sides = sides.assign(strength=sides["statistic"].abs())
    return sides.sort_values(["strength", "partner"], ascending=[False, True], kind="stable")


def _cluster_table(table: pd.DataFrame, ledger: pd.DataFrame, cut: float) -> pd.DataFrame:
    """The clusters (`CLUSTER_COLUMNS`): per cluster the members by the ledger's snapshot
    concordance, descending (the association is measured on the snapshot), each with its
    |statistic| with the best member (1 for the best itself; NaN when not compared) and its
    `explained_by_others` with the reason where that is NaN."""
    clusters = cluster_features(table, cut)
    by_feature = ledger.set_index("feature")
    strength = {}
    for a, b, statistic in table[["a", "b", "statistic"]].itertuples(index=False):
        strength[a, b] = strength[b, a] = abs(statistic)
    concordance = by_feature["concordance"]
    records = []
    for number in sorted(set(clusters.values())):
        members = [feature for feature, cluster in clusters.items() if cluster == number]
        # the strongest first, a member without a concordance last, ties by name
        members.sort(key=lambda f: (np.isnan(concordance[f]), -np.nan_to_num(concordance[f]), f))
        explained = explained_by_others(table, members)
        reasons = _explained_reasons(table, members, by_feature["kind"], explained)
        best = members[0]
        records += [
            {"cluster": number, "feature": f, "kind": by_feature.at[f, "kind"],
             "concordance": by_feature.at[f, "concordance"],
             "association_with_best": 1.0 if f == best else strength.get((f, best), np.nan),
             "explained_by_others": explained[f], "unavailable": reasons[f]}
            for f in members
        ]  # fmt: skip
    frame = pd.DataFrame(records, columns=CLUSTER_COLUMNS)
    return frame.astype({"cluster": "Int64", "concordance": float, "association_with_best": float,
                         "explained_by_others": float})  # fmt: skip


def _explained_reasons(
    table: pd.DataFrame, members: list[str], kinds: pd.Series, explained: dict[str, float]
) -> dict[str, str]:
    """Why each member's `explained_by_others` is NaN, from the pairs' methods and NaNs, never
    from an error: a categorical member, a numeric with no other numeric member, a Spearman
    pair among the numeric members not compared, or correlations no matrix can hold together
    (R² outside [0, 1]); '' where it has a value."""
    numerics = [m for m in members if kinds[m] == "numeric"]
    inside = table["a"].isin(numerics) & table["b"].isin(numerics) & (table["method"] == "spearman")
    compared = int(table.loc[inside, "statistic"].notna().sum())
    every_pair = compared == len(numerics) * (len(numerics) - 1) // 2
    reasons = {}
    for member in members:
        if not np.isnan(explained[member]):
            reasons[member] = ""
        elif kinds[member] != "numeric":
            reasons[member] = "not available: a categorical member"
        elif len(numerics) < 2:
            reasons[member] = "not available: no other numeric member"
        elif not every_pair:
            reasons[member] = "not available: a pair in the cluster was not compared"
        else:
            reasons[member] = "not available: inconsistent correlations (R² outside [0, 1])"
    return reasons


def _result(
    ledger: pd.DataFrame,
    findings: list[pd.DataFrame],
    unavailable: list[pd.DataFrame],
    columns: dict | None = None,
    tables: dict[str, pd.DataFrame] | None = None,
) -> StepResult:
    """A step's `StepResult`: the parts stacked, its `columns` beside `feature` for every read
    candidate."""
    frame = ledger[["feature"]].copy()
    for column, values in (columns or {}).items():
        frame[column] = values
    return StepResult(
        findings=stack_parts(findings, FINDING_COLUMNS),
        columns=frame,
        unavailable=stack_parts(unavailable, UNAVAILABLE_COLUMNS),
        tables=tables or {},
    )


STEPS: dict[str, Callable[..., StepResult]] = {
    "quality": check_quality,
    "leakage": check_leakage,
    "time_alignment": check_time_alignment,
    "stability": check_stability,
    "redundancy": check_redundancy,
}  # the run order, which is STEP_ORDER
STEP_COLUMNS: dict[str, list[str]] = {
    "quality": [],
    "leakage": [],
    "time_alignment": ["lagged_concordance", "signal_kept", "constant_share"],
    "stability": ["concordance_range", "heterogeneity_p", "psi_window", "psi_latest",
                  "new_level_share"],
    "redundancy": ["cluster", "explained_by_others", "partners"],
}  # every Feature Checks ledger column but `flags` and `notes`  # fmt: skip
