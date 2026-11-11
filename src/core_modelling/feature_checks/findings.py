"""The finding table as plain data (docs/components/feature_checks.md "The finding table").

Every finding a step can raise, by its full name `<step>.<finding>` (the name the audit log's
`flag` entries, the `keep` entries' `findings` and the ledger's `flags` and `notes` carry), in the
steps' run order: its kind, a flag ("should not enter a model as it is": it holds the feature out
of training until a person keeps or excludes it, D-134) or a note ("look at this": it never
affects training), its one-line text and its `measure`, the name of the statistic its `value`
holds (the held features' `flag_values` key). The text names no threshold, since a threshold is
a config leaf the run states in the findings' `threshold` column; it is a `flag` entry's reason.
A step's findings are rows of `FINDING_COLUMNS`: `finding` the full name, `value` the feature's
statistic, `threshold` the parameter it was compared with, `detail` what the row adds to the
text ('' when nothing), such as a rare value's bin or a pair's partners. The row builders a step
assembles its findings with (`finding_rows`, `finding_frame`, `unavailable_rows`:
`UNAVAILABLE_COLUMNS`, the findings that cannot exist with their reasons) and `stack_parts` live
here too.
"""

import pandas as pd

FINDING_COLUMNS = ["feature", "step", "finding", "kind", "value", "threshold", "text", "detail"]
UNAVAILABLE_COLUMNS = ["feature", "finding", "reason"]
STEP_ORDER = ["quality", "leakage", "time_alignment", "stability", "redundancy"]
REDUNDANT = "Near-duplicates; the cluster table shows which carries the signal."

FINDINGS: dict[str, dict[str, str]] = {
    "quality.all_null": {
        "kind": "flag", "measure": "missing_share_window", "text": "Every value is null.",
    },
    "quality.constant": {
        "kind": "flag", "measure": "dominant_share_window",
        "text": "One value only, null counted as a value.",
    },
    "quality.high_missing": {
        "kind": "flag", "measure": "missing_share_window", "text": "Almost every value is null.",
    },
    "quality.near_constant": {
        "kind": "flag", "measure": "dominant_share_window",
        "text": "One value covers almost every row, null counted as a value.",
    },
    "quality.high_cardinality": {
        "kind": "flag", "measure": "levels",
        "text": "Codes or free text? Held until a person confirms the levels are meaningful.",
    },
    "quality.nulls_may_be_zeros": {
        "kind": "note", "measure": "missing_share_window",
        "text": "Many nulls and never a zero: if a null means 0 here, fill it upstream; the "
        "framework never imputes.",
    },
    "quality.nulls_informative": {
        "kind": "note", "measure": "null_concordance_window",
        "text": "Whether the value is filled carries information; keep the nulls as their own "
        "group; a family that imputes must impute outside the value range, never the median.",
    },
    "leakage.too_strong": {
        "kind": "flag", "measure": "concordance_window_or_best_order",
        "text": "A single feature this strong is usually the target under another name or a "
        "consequence of it.",
    },
    "leakage.missingness_leak": {
        "kind": "flag", "measure": "null_concordance_window",
        "text": "Whether the value is filled predicts the target this strongly: ask how and when "
        "the field gets filled.",
    },
    "leakage.rare_value_leak": {
        "kind": "flag", "measure": "rare_effect",
        "text": "Beside one dominant value, the other values' target rate (an amount: mean) is "
        "far above the dominant value's: a code set after the outcome?",
    },
    "time_alignment.lagged_signal_drop": {
        "kind": "flag", "measure": "signal_kept",
        "text": "The feature loses most of its signal when lagged one period: its value may be "
        "stamped after the period.",
    },
    "time_alignment.client_constant": {
        "kind": "flag", "measure": "constant_share",
        "text": "Constant within the client across the window and predictive: a static "
        "attribute, or one date's value stamped onto every period.",
    },
    "stability.concordance_unstable": {
        "kind": "flag", "measure": "heterogeneity_p",
        "text": "The feature's power differs across the window's periods.",
    },
    "stability.psi_window_large": {
        "kind": "flag", "measure": "psi_window",
        "text": "The distribution moved strongly while the model's data was collected: find the "
        "cause before a keep.",
    },
    "stability.psi_latest_large": {
        "kind": "flag", "measure": "psi_latest",
        "text": "Production will score a strongly different distribution: find the cause before "
        "a keep.",
    },
    "stability.psi_window": {
        "kind": "note", "measure": "psi_window",
        "text": "The distribution moved while the model's data was collected.",
    },
    "stability.psi_latest": {
        "kind": "note", "measure": "psi_latest",
        "text": "Production will score a different distribution: expect Monitoring to see it.",
    },
    "stability.new_levels": {
        "kind": "note", "measure": "new_level_share",
        "text": "Levels unseen in the window cover a share of the latest period's rows.",
    },
    "redundancy.correlated_pair": {"kind": "note", "measure": "association", "text": REDUNDANT},
    "redundancy.associated_pair": {"kind": "note", "measure": "association", "text": REDUNDANT},
}  # fmt: skip


def step_findings(step: str) -> list[str]:
    """The full names of the findings `step` can raise, in table order."""
    if step not in STEP_ORDER:
        raise ValueError(f"unknown Feature Checks step {step!r}; the steps are {STEP_ORDER}")
    return [name for name in FINDINGS if name.split(".")[0] == step]


def finding_rows(
    name: str,
    ledger: pd.DataFrame,
    fires: pd.Series,
    value: pd.Series,
    threshold: float,
    detail: pd.Series | str = "",
) -> pd.DataFrame:
    """Finding `name`'s rows for the ledger rows `fires` marks: each feature's `value` and
    `detail` against `threshold`."""
    rows = pd.DataFrame({
        "feature": ledger.loc[fires, "feature"], "value": value[fires].astype(float),
        "detail": detail[fires] if isinstance(detail, pd.Series) else detail,
    })  # fmt: skip
    return finding_frame(name, rows, threshold)


def finding_frame(name: str, rows: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """`rows` (`feature`, `value`, `detail`) as finding `name`'s `FINDING_COLUMNS` rows."""
    out = rows.assign(
        step=name.split(".")[0], finding=name, kind=FINDINGS[name]["kind"],
        threshold=float(threshold), text=FINDINGS[name]["text"],
    )  # fmt: skip
    return out[FINDING_COLUMNS].reset_index(drop=True)


def unavailable_rows(name: str, features: pd.Series, reason: pd.Series | str) -> pd.DataFrame:
    """`unavailable` rows of finding `name` for `features`, with one reason or one each."""
    reasons = reason if isinstance(reason, str) else reason.to_numpy()
    return pd.DataFrame({"feature": features.to_numpy(), "finding": name, "reason": reasons})


def stack_parts(parts: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    """The parts stacked in order; an empty frame of `columns` (numbers as floats) when none
    holds a row."""
    parts = [part for part in parts if not part.empty]
    if parts:
        return pd.concat(parts, ignore_index=True)[columns]
    empty = pd.DataFrame(columns=columns)
    return empty.astype({column: float for column in ("value", "threshold") if column in columns})
