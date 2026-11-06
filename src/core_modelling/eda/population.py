"""EDA's population and target tables: the headline, the funnel, the target per period and by
stratum, and the reference groups (docs/components/eda.md requirement 2, "The views").

The window views read the frames' log (the funnel), the D-088 population counts and the cells
(the target per period); the snapshot views read the collected snapshot. Every label statistic
uses the snapshot's eligible rows with a known target (`known_rows`, §4.4); the reference groups
are label-free and use every snapshot row. `cap_levels` and `summarise_groups` are the two
pieces every group table shares (here and in `deep_dives.py`): a column's values as capped,
ordered level labels, null a level (N16), and one row of the per-task group summary per group
with `insufficient` below its support rule (`TASK_SPECS[task]["summarise_group"]`, D-050).
`is_numeric` and `reference_sides` are public because `run.py` and `explore.py` judge a column
and cut a tag's sides the same way.

`reference_groups` returns one long table, per modelling tag, with three sections, each side
being the rows the tag excludes (`tag = 0`) against the modelling population (`eligible = 1`):
- `size` (one row): `rows_<side>` and `share_<side>`, the side's share of the snapshot's rows;
- `composition` (one row per stratum variable and level, the levels capped over the whole
  snapshot): `rows_<side>` at the level and `share_<side>`, the level's share of the side;
- `feature` (one row per key feature, by |`smd`| descending): `rows_<side>`, `share_<side>` the
  side's non-null share, `median_`/`p10_`/`p90_<side>` (numerics), `smd` (Cohen's d on non-null
  values; a categorical's largest level-share difference, null a level) and `differs` (|`smd`|
  ≥ `SMD_DIFFERS`, a description, not a test); `unavailable` names why `smd` is missing.
"""

import numpy as np
import pandas as pd

from core_modelling.config.schema import Strata
from core_modelling.dataset.counts import BLANK_LEVEL, NULL_BIN, OTHER, RESERVED_BINS
from core_modelling.statistics.cells import level_share_difference
from core_modelling.statistics.distributions import standardised_difference
from core_modelling.tasks import TASK_SPECS

STRATA_KEYS = ["variable", "level", "feature", "feature_group"]
SMD_DIFFERS = 0.25  # |SMD| from which a reference group "differs" (a description, not a test)
SIDES = ("excluded", "eligible")
REFERENCE_COLUMNS = [
    "tag", "section", "variable", "level",
    *[f"{stat}_{side}" for stat in ("rows", "share", "median", "p10", "p90") for side in SIDES],
    "smd", "differs", "unavailable",
]  # fmt: skip


def known_rows(snapshot: pd.DataFrame) -> pd.DataFrame:
    """The snapshot's eligible rows with a known target: what every label statistic reads."""
    return snapshot.loc[(snapshot["eligible"] == 1) & snapshot["target"].notna()]


def is_numeric(values: pd.Series, kind: str | None) -> bool:
    """A candidate is numeric by its kind; any other column has none and, not being a feature, is
    not bound by N13 (kinds never read the dtype): its dtype decides, a boolean not numeric."""
    if kind is not None:
        return kind == "numeric"
    return pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values)


def cap_levels(values: pd.Series, max_levels: int) -> pd.Series:
    """Each value as a level label (an ordered categorical on the same index): the `max_levels`
    levels with the most rows (ties by label) as their text (`_level_text`), a real level named
    like a reserved bin or blank quoted (`'null'`, `''`, `' '`), the rest `__other__`, null (a
    NaN too) `null`; ordered by rows, then `__other__`, then `null` last."""
    text = values.dropna().map(_level_text).astype(str)  # str: an empty map keeps a float dtype
    quoted = text.isin(RESERVED_BINS) | text.str.match(BLANK_LEVEL)
    text = text.where(~quoted, "'" + text + "'")
    counts = text.value_counts().sort_index().sort_values(ascending=False, kind="stable")
    kept = list(counts.index[:max_levels])
    order = kept + ([OTHER] if len(counts) > max_levels else [])
    order += [NULL_BIN] if values.isna().any() else []
    labels = text.where(text.isin(kept), OTHER).reindex(values.index).fillna(NULL_BIN)
    return pd.Series(pd.Categorical(labels, categories=order, ordered=True), index=values.index)


def _level_text(value: object) -> str:
    """A value's text as Spark's cast to string gives it, so a snapshot table names a level as
    the counts table's cells do: a boolean lower case, an integral float without `.0` (pandas
    holds an integer column with nulls as floats)."""
    if isinstance(value, bool | np.bool_):
        return str(value).lower()
    if isinstance(value, float | np.floating) and float(value).is_integer():
        return str(int(value))
    return str(value)


def summarise_groups(
    target: pd.Series, groups: pd.DataFrame, task: str, base: float, min_support: int
) -> pd.DataFrame:
    """One row per observed combination of `groups`' columns (ordered categoricals on the
    target's index, in their order): the keys, then the task's `summary_columns` from its group
    summary against `base` (`lift` NaN when no lift exists), `insufficient` meaning support below
    `min_support`."""
    if target.empty:
        raise ValueError("summarise_groups: no row with a known target to summarise")
    spec = TASK_SPECS[task]
    records = []
    keys = [groups[column] for column in groups.columns]
    for key, part in target.groupby(keys, observed=True, sort=True):
        summary = spec["summarise_group"](part, base)
        records.append({**dict(zip(groups.columns, key, strict=True)), **summary})
    table = pd.DataFrame.from_records(records)
    table["insufficient"] = table["support"] < min_support
    columns = [*groups.columns, *spec["summary_columns"]]
    if set(table.columns) != set(columns):
        missing, extra = sorted(set(columns) - set(table)), sorted(set(table) - set(columns))
        raise ValueError(
            f"summarise_groups: the {task} summary misses {missing} and adds {extra} against its "
            "summary_columns"
        )
    return table[columns]


def headline_numbers(snapshot: pd.DataFrame, per_period: pd.DataFrame, task: str) -> dict:
    """The summary's headline: the snapshot's eligible rows, clients and eligible share, the
    target's headline on its known rows (`base_rate_views`, prefixed `snapshot_`), and the
    window's rows, positive rows, positive events and rows per event from `target_per_period`'s
    `all` row."""
    eligible = snapshot.loc[snapshot["eligible"] == 1]
    views = TASK_SPECS[task]["base_rate_views"](known_rows(snapshot)["target"])
    window = per_period.set_index("period").loc["all"]
    events = window["support"]
    return {
        "eligible_rows": len(eligible),
        "clients": eligible["unit_id"].nunique(),
        "eligible_share": len(eligible) / len(snapshot),
        **{f"snapshot_{name}": value for name, value in views.items()},
        "window_rows": window["rows"],
        "window_positive_rows": window["positive_rows"],
        "window_positive_events": events,
        "rows_per_event": window["positive_rows"] / events if events else np.nan,
    }


def funnel_per_period(log: list[dict], window_periods: list[str]) -> pd.DataFrame:
    """Per window period plus an `all` row, from the frames' log: `spine` (the rows the first
    eligibility filter met; the eligible rows when there is no filter), `after_<name>` per
    analysis filter, `tagged_<name>` per modelling filter (the rows it tags 1) and `eligible`
    (the contract's eligible rows). A period missing from a step's counts had no row there."""
    steps = [entry for entry in log if entry["step"] == "eligibility"]
    contract = [entry for entry in log if entry.get("check") == "eligible_rows"]
    if len(contract) != 1:
        raise ValueError("funnel_per_period: the log needs one contract `eligible_rows` entry")
    eligible = contract[0]["per_period"]
    columns = {"spine": steps[0]["rows"] if steps else eligible}
    for entry in steps:
        prefix, counts = (
            ("after", "rows_out") if entry["kind"] == "analysis" else ("tagged", "tagged_1")
        )
        columns[f"{prefix}_{entry['name']}"] = entry[counts]
    columns["eligible"] = eligible
    table = pd.DataFrame(
        {name: [counts.get(p, 0) for p in window_periods] for name, counts in columns.items()},
        index=pd.Index(window_periods, name="period"),
    )
    table.loc["all"] = table.sum()
    return table.reset_index()


def target_per_period(
    population: pd.DataFrame,
    cells: pd.DataFrame,
    task: str,
    min_events: int,
    clients: dict[str, float],
) -> pd.DataFrame:
    """Per labelled window period plus the pooled `all` row: `rows` (a known target),
    `positive_rows`, `support` (units with a non-zero target; for `all` the distinct ones,
    `clients["event_clients"]` of `counts.window_clients`), the estimate with its interval from
    `period_estimate` (binary: the rate and Wilson; regression: `sum_y / rows` of one feature's
    labelled cells, which cover every eligible row, with its t-interval from `sum_y2`, and the
    non-zero share) and `insufficient` (support below `min_events`). The pooled row's clients
    recur in every period, so its counts are scaled to effective clients (Kish's, as every window
    SE): the estimate stays, the interval widens."""
    labelled = population.loc[population["known_target"].notna()].set_index("period")
    empty = list(labelled.index[labelled["known_target"] == 0])
    if empty:
        raise ValueError(f"target_per_period: no known target in the window periods {empty}")
    current = cells.loc[~cells["lagged"] & cells["target_bin"].notna()]
    if current.empty:
        raise ValueError("target_per_period: the cells hold no labelled current rows")
    one = current.loc[current["feature"] == current["feature"].iloc[0]]
    sums = one.groupby("period")[["n", "sum_y", "sum_y2"]].sum().reindex(labelled.index)
    if not np.array_equal(sums["n"].to_numpy(float), labelled["known_target"].to_numpy(float)):
        raise ValueError(
            "target_per_period: the cells' labelled rows per period differ from the population "
            "counts' known targets; both must come from the same frames"
        )
    names = {"known_target": "rows", "positive_rows": "positive_rows", "positive_events": "support"}
    counts = labelled[list(names)].astype(float).rename(columns=names)
    table = counts.join(sums[["sum_y", "sum_y2"]])
    table.loc["all"] = table.sum()
    table.loc["all", "support"] = clients["event_clients"]
    scale = np.where(table.index == "all", clients["effective"] / clients["rows"], 1.0)
    summed = ("rows", "positive_rows", "sum_y", "sum_y2")
    arrays = [table[c].to_numpy(dtype=float) * scale for c in summed]
    estimate = TASK_SPECS[task]["period_estimate"](*arrays)
    table = table.drop(columns=["sum_y", "sum_y2"]).assign(**estimate)
    table.insert(table.columns.get_loc("high") + 1, "insufficient", table["support"] < min_events)
    return table.rename_axis("period").reset_index()


def strata_tables(snapshot: pd.DataFrame, strata: Strata, task: str) -> pd.DataFrame:
    """The target by stratum on the snapshot's eligible rows with a known target: per variable,
    one row per level (`cap_levels` at `strata.max_levels` over the eligible rows), the summary
    columns against the snapshot's base and `insufficient` below `strata.min_events`; `feature`
    and `feature_group` null (the strata pivots fill them)."""
    eligible = snapshot.loc[snapshot["eligible"] == 1]
    known = known_rows(snapshot)
    base = known["target"].mean()
    parts = []
    for variable in strata.variables:
        level = cap_levels(eligible[variable], strata.max_levels).loc[known.index].rename("level")
        table = summarise_groups(known["target"], level.to_frame(), task, base, strata.min_events)
        parts.append(table.assign(variable=variable, feature=None, feature_group=None))
    return strata_frame(parts, task)


def strata_frame(parts: list[pd.DataFrame], task: str) -> pd.DataFrame:
    """The strata parts as one long table, `STRATA_KEYS` first; without a part, empty with the
    task's summary columns."""
    if not parts:
        return pd.DataFrame(columns=[*STRATA_KEYS, *TASK_SPECS[task]["summary_columns"]])
    table = pd.concat(parts, ignore_index=True)
    for key in ("level", "feature_group"):  # categoricals of different levels: plain text
        table[key] = table[key].astype(object)
    return table[[*STRATA_KEYS, *[c for c in table.columns if c not in STRATA_KEYS]]]


def reference_groups(
    snapshot: pd.DataFrame,
    tags: list[str],
    key_features: list[str],
    kinds: dict[str, str],
    strata: Strata,
) -> pd.DataFrame:
    """Per modelling tag, label-free, the rows it excludes against the modelling population on
    every snapshot row: sizes, composition per stratum, and per key feature the distribution and
    the standardised difference; the long shape is the module docstring's."""
    records = []
    for tag in tags:
        sides = reference_sides(snapshot, tag)
        records.append({"tag": tag, "section": "size", **_sizes(sides, len(snapshot))})
        for variable in strata.variables:
            levels = cap_levels(snapshot[variable], strata.max_levels)
            records += [{"tag": tag, **r} for r in _composition(levels, sides, variable)]
        rows = [_feature_row(snapshot[f], sides, f, kinds[f]) for f in key_features]
        rows.sort(key=lambda r: -abs(r["smd"]) if pd.notna(r["smd"]) else np.inf)
        records += [{"tag": tag, "section": "feature", **r} for r in rows]
    return pd.DataFrame.from_records(records, columns=REFERENCE_COLUMNS)


def reference_sides(snapshot: pd.DataFrame, tag: str) -> dict[str, pd.Series]:
    """A modelling tag's two sides as row masks over the snapshot: the rows it excludes
    (`tag == 0`) and the modelling population (`eligible == 1`)."""
    return {"excluded": snapshot[tag] == 0, "eligible": snapshot["eligible"] == 1}


def _sizes(sides: dict[str, pd.Series], total: int) -> dict:
    """Each side's rows and share of the snapshot's rows."""
    rows = {side: int(mask.sum()) for side, mask in sides.items()}
    return {
        **{f"rows_{s}": n for s, n in rows.items()},
        **{f"share_{s}": n / total for s, n in rows.items()},
    }


def _composition(levels: pd.Series, sides: dict[str, pd.Series], variable: str) -> list[dict]:
    """One row per level: each side's rows at it and its share of the side (an empty side's 0 / 0:
    NaN)."""
    counts = {side: levels[mask].value_counts() for side, mask in sides.items()}
    rows = pd.DataFrame(counts).reindex(levels.cat.categories)
    table = rows.add_prefix("rows_").join((rows / rows.sum()).add_prefix("share_"))
    table = table.rename_axis("level").reset_index()
    return table.assign(section="composition", variable=variable).to_dict("records")


def _feature_row(values: pd.Series, sides: dict[str, pd.Series], feature: str, kind: str) -> dict:
    """One key feature's sides (rows, non-null share, median, p10, p90 for a numeric) and its
    standardised difference, decided "not available" up front."""
    record = {"section": "feature", "variable": feature}
    parts = {side: values[mask] for side, mask in sides.items()}
    for side, part in parts.items():
        record[f"rows_{side}"] = len(part)
        record[f"share_{side}"] = part.notna().mean() if len(part) else np.nan
        if kind == "numeric":
            filled = part.dropna().to_numpy(dtype=float)
            quantiles = np.quantile(filled, [0.5, 0.1, 0.9]) if filled.size else [np.nan] * 3
            names = [f"{q}_{side}" for q in ("median", "p10", "p90")]
            record.update(zip(names, quantiles, strict=True))
    smd, reason = _difference(parts["excluded"], parts["eligible"], kind)
    differs = bool(abs(smd) >= SMD_DIFFERS) if pd.notna(smd) else False
    return {**record, "smd": smd, "differs": differs, "unavailable": reason}


def _difference(excluded: pd.Series, eligible: pd.Series, kind: str) -> tuple[float, str]:
    """The excluded side's standardised difference from the eligible side and '' (a categorical:
    the largest level-share difference, null a level), or NaN and the "not available" reason."""
    if excluded.empty or eligible.empty:
        return np.nan, "not available: a side has no row"
    if kind == "categorical":
        codes = pd.factorize(pd.concat([excluded, eligible]), use_na_sentinel=False)[0]
        cells = pd.DataFrame({"bin_order": codes, "n": 1})
        return level_share_difference(cells[: len(excluded)], cells[len(excluded) :]), ""
    a, b = (side.dropna().to_numpy(dtype=float) for side in (excluded, eligible))
    if min(a.size, b.size) < 2:
        return np.nan, "not available: fewer than two non-null values on a side"
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        return np.nan, "not available: infinite values"
    return standardised_difference(a, b), ""
