"""The panel: the sources joined with one target column per use case, and its preparation for
one use case (D-129, D-131; the Stage 1 addendum, section B).

`load_panel` takes a list of configs sharing one data definition (the same feature sources,
keys, model input and period) and reads every source of an entity through `read_keyed_source`
(keys renamed, periods at their last day), left-joins the other feature sources to the
governing spine on the keys, then each config's targets (`load_targets`, built over the whole
target source, never a window of it) as `target_<use_case>`, and keeps the periods from the
earliest observation window's first to the spine's last. That panel, the sources plus the
target columns and nothing else, is what the model input saves: one table serves several use
cases, and a changed eligibility never forces a rebuild. `prepare_panel` is the read side, run
from the reader's own config on the saved or the in-memory panel, its columns planned by
`read_side_columns` (the saved table's candidate list follows the same plan without Spark): the
other use cases' target columns are dropped, and every upstream target's source column that is
in the panel as a label (its target source is a feature source): another use case's, being
forward-looking, the own one, its values being `target`'s; a source column named like one the
dataset adds (`target`, `split`, `eligible`) is renamed `source_<name>`, and the own target
column becomes `target`, each drop and rename printed and logged. Then the eligibility steps
and the candidates (`eligibility.py`), the contract check and the split. `build_panel` is both
for one config, the in-memory path.
"""

from dataclasses import dataclass

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.config.identities import HASH_VERSION, data_definition_hash, target_spec_hash
from core_modelling.dataset.contract import check_contract
from core_modelling.dataset.eligibility import apply_eligibility, modelling_tags, resolve_candidates
from core_modelling.dataset.split import assign_split
from core_modelling.environment import EnvironmentConfig
from core_modelling.periods import Period, label_by_period, period_spec
from core_modelling.sources import (
    HELPER_COLUMNS,
    KEYS,
    check_periods_covered,
    read_keyed_source,
    rename_reserved,
)
from core_modelling.target_factory import load_targets, target_lineage

PANEL_META_KEYS = ("data_definition_hash", "target_spec_hash", "hash_version", "lineage",
                   "candidates", "tags")  # what `prepare_panel` puts in the meta  # fmt: skip
# The config fields every config of one model input must share (the panel is built from them).
SHARED_FIELDS = {
    "sources.features": lambda cfg, entity: cfg.entities[entity].sources.features,
    "keys": lambda cfg, entity: cfg.data.keys.model_dump(),
    "model_input": lambda cfg, entity: cfg.data.model_input,
    "time.period": lambda cfg, entity: cfg.time.period,
}


@dataclass(frozen=True)
class JoinedSource:
    """One source in the join: its read log, the marker column its rows carry (None for the
    spine), its role (`spine`, `joined`, `targets`) and, for a target, its use case."""

    log: dict
    marker: str | None
    role: str
    use_case: str | None = None


def target_column(use_case: str) -> str:
    """The panel's target column of a use case, `target_<use_case>` lower-cased (Q405): Spark
    compares column names ignoring case."""
    return f"target_{use_case.lower()}"


def load_panel(
    cfgs: list[UseCaseConfig], entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[dict], dict]:
    """The governing spine with the other feature sources and every config's targets
    left-joined on the keys, from the earliest window's first period to the spine's last; the
    join log, one entry per source; the meta: the definition the panel was built from and, per
    use case, its target's column, spec hash, lineage, source, windows and null share."""
    _check_shared_definition(cfgs, entity)
    spec = period_spec(cfgs[0])
    panel, joined = _join_sources(cfgs, entity, env, spark)
    panel, joined, targets = _join_targets(panel, joined, cfgs, entity, env, spark)
    first = min(cfg.time.observation_window.first for cfg in cfgs)
    last = joined[0].log["periods"][-1]
    panel = panel.where(F.col("period").between(first, last))
    entries, null_shares = _join_log(panel, joined, cfgs, spec)
    for use_case, share in null_shares.items():
        targets[use_case]["null_in_window_share"] = share
    cfg = cfgs[0]
    meta = {
        "hash_version": HASH_VERSION,
        "sources": {"features": cfg.entities[entity].sources.features},
        "keys": cfg.data.keys.model_dump(),
        "period": cfg.time.period,
        "periods": {"first": spec.label(first), "last": spec.label(last)},
        "targets": targets,
    }
    transient = [source.marker for source in joined if source.marker]
    transient += [f"_null_{t['column']}" for t in targets.values()]
    return panel.drop(*transient), entries, meta


def _check_shared_definition(cfgs: list[UseCaseConfig], entity: str) -> None:
    """The use cases are distinct ignoring case and every config lists `entity` and declares the
    same feature sources, keys, model input and period, else the two use cases and the field are
    named."""
    if not cfgs:
        raise ValueError("load_panel needs at least one config")
    lowered = [cfg.use_case.lower() for cfg in cfgs]
    repeated = sorted({cfg.use_case for cfg in cfgs if lowered.count(cfg.use_case.lower()) > 1})
    if repeated:
        raise ValueError(
            "the use cases must be distinct ignoring case (Spark column names are "
            "case-insensitive, so target_X and target_x would collide); repeated: "
            f"{repeated}"
        )
    for cfg in cfgs:
        if entity not in cfg.entities:
            raise ValueError(
                f"unknown entity {entity!r}: the config {cfg.use_case!r} has {sorted(cfg.entities)}"
            )
    first = cfgs[0]
    for cfg in cfgs[1:]:
        for field, value in SHARED_FIELDS.items():
            if value(cfg, entity) != value(first, entity):
                raise ValueError(
                    f"the configs {first.use_case!r} and {cfg.use_case!r} differ in {field} "
                    f"({value(first, entity)} vs {value(cfg, entity)}); one model input needs "
                    "one data definition"
                )


def _join_sources(
    cfgs: list[UseCaseConfig], entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[JoinedSource]]:
    """The spine, checked to cover the earliest window's first period to the latest validation
    period, with the other feature sources left-joined and marked; the joined sources, the
    spine first."""
    cfg = cfgs[0]
    names = cfg.entities[entity].sources.features
    panel, spine_log = read_keyed_source(cfg, entity, names[0], env, spark)
    # A gap would drop a period of rows quietly; a validation period must exist to be scored.
    first = min(c.time.observation_window.first for c in cfgs)
    last = max(c.time.validation_period for c in cfgs)
    spec = period_spec(cfg)
    check_periods_covered(spine_log, first, last, "spine", "time.validation_period", spec)
    joined = [JoinedSource(spine_log, None, "spine")]
    for name in names[1:]:
        source, log = read_keyed_source(cfg, entity, name, env, spark)
        _check_no_shared_column(panel, source, name)
        marker = f"_from_{name}"
        panel = panel.join(source.withColumn(marker, F.lit(True)), KEYS, "left")
        joined.append(JoinedSource(log, marker, "joined"))
    return panel, joined


def _join_targets(
    panel: DataFrame,
    joined: list[JoinedSource],
    cfgs: list[UseCaseConfig],
    entity: str,
    env: EnvironmentConfig,
    spark: SparkSession,
) -> tuple[DataFrame, list[JoinedSource], dict]:
    """Each config's targets left-joined as `target_<use_case>`, `null_in_window` as the
    transient `_null_<column>`, marked; the joined list extended; per use case the target's
    meta (`_target_meta`)."""
    targets = {}
    for cfg in cfgs:
        column = target_column(cfg.use_case)
        if column in (name.lower() for name in panel.columns):
            raise ValueError(
                f"the target column {column!r} of use case {cfg.use_case!r} is a column of the "
                "sources; rename it upstream"
            )
        built, log = load_targets(cfg, entity, env, spark)
        marker = f"_from_{column}"
        built = built.select(
            *KEYS, F.col("target").alias(column), F.col("null_in_window").alias(f"_null_{column}")
        )
        panel = panel.join(built.withColumn(marker, F.lit(True)), KEYS, "left")
        joined.append(JoinedSource(log, marker, "targets", cfg.use_case))
        targets[cfg.use_case] = _target_meta(cfg, entity, column, log)
    return panel, joined, targets


def _target_meta(cfg: UseCaseConfig, entity: str, column: str, target_log: dict) -> dict:
    """One use case's target as the meta records it: what `prepare_panel` and the model input's
    checks need; dates as the period's labels, but the target source's last period as an ISO
    date, which a reader turns back into a date to check its own validation period against."""
    spec, window = period_spec(cfg), cfg.time.observation_window
    return {
        "column": column,
        "target_spec_hash": target_spec_hash(cfg, entity),
        "lineage": target_lineage(cfg),
        "source": target_log["source"],
        "target_last": target_log["periods"][-1].isoformat(),
        "upstream": cfg.data.target.rule is None,
        "observation_window": {"first": spec.label(window.first), "last": spec.label(window.last)},
        "target_window": cfg.time.target_window,
        "validation_period": spec.label(cfg.time.validation_period),
    }


def _check_no_shared_column(panel: DataFrame, source: DataFrame, name: str) -> None:
    """A non-key column in two feature sources fails loud: the join would carry two of it."""
    shared = sorted(set(panel.columns) & set(source.columns) - set(KEYS))
    if shared:
        renamed = any(column.startswith("source_") for column in shared)
        note = " (a `source_<name>` column is a source's `<name>` read under another name)"
        raise ValueError(
            f"feature source {name!r} shares the columns {shared} with an earlier source"
            f"{note if renamed else ''}; rename them upstream"
        )


def _check_named_features(panel: DataFrame, cfg: UseCaseConfig) -> None:
    """A name in the audit log's replayed lists that is a key, a column the dataset adds or not
    a column fails loud (it would otherwise exclude nothing)."""
    for field in ("excluded", "kept_despite_flags"):
        framework = [n for n in getattr(cfg.features, field) if n in (*KEYS, *HELPER_COLUMNS)]
        if framework:
            raise ValueError(
                f"features.{field} names {framework}, the framework's own columns; a source "
                f"column of that name is read as `source_<name>`: name it so"
            )
        unknown = [n for n in getattr(cfg.features, field) if n not in panel.columns]
        if unknown:
            raise ValueError(f"features.{field} names columns the sources don't have: {unknown}")


def _join_log(
    panel: DataFrame, joined: list[JoinedSource], cfgs: list[UseCaseConfig], spec: Period
) -> tuple[list[dict], dict]:
    """One entry per source from one rollup of the panel: the spine's rows per period, per
    joined source the rows it matched per period and their share, per target also the share of
    rows whose window held a null. A feature source matching no spine row, or a window period
    with no known value in a config's target column, fails loud (keys or periods disagree). The
    null share over each config's observation window comes back by use case, for the
    contract's callout."""
    by_period, all_rows = _rollup(panel, joined, cfgs)
    _check_sources_matched(joined, all_rows)
    for cfg in cfgs:
        _check_window_labelled(by_period, cfg, spec)
    entries = [_join_entry(source, by_period, all_rows, spec) for source in joined]
    return entries, {cfg.use_case: all_rows[f"_share_{cfg.use_case}"] for cfg in cfgs}


def _rollup(
    panel: DataFrame, joined: list[JoinedSource], cfgs: list[UseCaseConfig]
) -> tuple[dict, object]:
    """The panel's rows, the rows each marker matched, per target the known values and the
    null share, per period (the rows keyed by the period) and over every period (the last
    row), from one rollup."""
    markers = [source.marker for source in joined if source.marker]
    use_cases = [cfg.use_case for cfg in cfgs]
    counts = [F.count(marker).alias(marker) for marker in markers]
    known = [F.count(target_column(u)).alias(f"_known_{u}") for u in use_cases]
    nulls = [F.avg(_null_flag(u)).alias(f"_nulls_{u}") for u in use_cases]
    shares = [_window_null_share(cfg) for cfg in cfgs]
    rows = panel.rollup("period").agg(
        F.grouping("period").alias("_all"), F.count(F.lit(1)).alias("rows"),
        *counts, *known, *nulls, *shares,
    )  # fmt: skip
    collected = rows.orderBy("_all", "period").collect()
    return {row.period: row for row in collected if not row._all}, collected[-1]


def _null_flag(use_case: str) -> Column:
    """The use case's transient `null_in_window` as 0/1 (null where the window is incomplete or
    the target is upstream), so its average is the share among complete windows."""
    return F.col(f"_null_{target_column(use_case)}").cast("double")


def _window_null_share(cfg: UseCaseConfig) -> Column:
    """The share of the config's observation-window rows whose target window held a null, among
    the rows with a complete window; null for an upstream target, which never fills it."""
    window = cfg.time.observation_window
    in_window = F.col("period").between(window.first, window.last)
    return F.avg(F.when(in_window, _null_flag(cfg.use_case))).alias(f"_share_{cfg.use_case}")


def _check_sources_matched(joined: list[JoinedSource], all_rows: object) -> None:
    """Every joined feature source matched some spine row, else the keys disagree: named with
    both id types (the targets have their own per-window check)."""
    spine = joined[0].log
    for source in joined:
        if source.role == "joined" and all_rows[source.marker] == 0:
            raise ValueError(
                f"feature source {source.log['source']!r} matched no spine row: do the keys "
                f"agree? its id is {source.log['id_type']}, the spine's {spine['id_type']} (both "
                "cast to string at read)"
            )


def _check_window_labelled(by_period: dict, cfg: UseCaseConfig, spec: Period) -> None:
    """Every period of the config's observation window has a known value in its target column
    (the target source matched some spine row there)."""
    window = cfg.time.observation_window
    in_window = [p for p in by_period if window.first <= p <= window.last]
    unlabelled = [spec.label(p) for p in in_window if not by_period[p][f"_known_{cfg.use_case}"]]
    if unlabelled:
        raise ValueError(
            f"no known target of use case {cfg.use_case!r} in the window's periods {unlabelled}: "
            "the target source matched no spine row there (do the keys and the periods agree?)"
        )


def _join_entry(source: JoinedSource, by_period: dict, all_rows: object, spec: Period) -> dict:
    """One source's join entry, printed: the spine's rows per period; a joined source's matched
    rows per period and share; a target's use case, column and null share per period too."""
    log, marker, role, use_case = source.log, source.marker, source.role, source.use_case
    entry = {"step": "join", "source": log["source"], "role": role, "period_tag": log["period_tag"]}
    if log["renamed"]:
        entry["renamed"] = log["renamed"]
    rows = by_period.values()
    if marker is None:
        entry["rows"] = label_by_period(rows, "rows", spec)
        print(f"spine {log['source']} ({log['period_tag']} periods): {all_rows.rows:,} rows "
              f"from {spec.label(min(by_period))} to {spec.label(max(by_period))}")  # fmt: skip
        return entry
    entry.update(matched_share=all_rows[marker] / all_rows.rows)
    entry.update(matched=label_by_period(rows, marker, spec))
    what = role if use_case is None else f"{role} of {use_case}"  # one line per use case's target
    print(f"join {log['source']} ({what}, {log['period_tag']} periods): "
          f"{entry['matched_share']:.1%} of the spine's rows matched")  # fmt: skip
    if use_case is not None:
        nulls = label_by_period(rows, f"_nulls_{use_case}", spec)
        entry.update(use_case=use_case, column=target_column(use_case), null_in_window=nulls)
    return entry


DROP_REASONS = {
    "target": "another use case's target",
    "label": "another use case's label (its upstream target column)",
    "own label": "this use case's label: its values are `target`'s",
}


def _columns_to_drop(targets: dict, use_case: str, features: list[str]) -> dict[str, str]:
    """The columns the use case's read drops, with why: the other use cases' target columns and
    every upstream target's source column that is in the panel as a label (its target source
    is one of the `features` sources); both are forward-looking, so never a candidate nor
    nameable in eligibility."""
    dropped = {}
    for name, target in targets.items():
        if name != use_case:
            dropped[target["column"]] = DROP_REASONS["target"]
        if target["upstream"] and target["source"] in features:
            reason = DROP_REASONS["own label" if name == use_case else "label"]
            dropped.setdefault(target["lineage"][0], reason)
    return dropped


def read_side_columns(
    columns: list[str], targets: dict, use_case: str, features: list[str]
) -> tuple[dict[str, str], dict[str, str]]:
    """The panel's columns the use case's read drops, with why (`_columns_to_drop`), and the
    renames, in order: a remaining `target`, `split` or `eligible` as `source_<name>`, then the
    own target column as `target`; `features` are the entity's feature sources."""
    planned = _columns_to_drop(targets, use_case, features)
    dropped = {column: reason for column, reason in planned.items() if column in columns}
    remaining = [column for column in columns if column not in dropped]
    renames = rename_reserved(remaining, HELPER_COLUMNS, "the panel")
    renames[targets[use_case]["column"]] = "target"
    return dropped, renames


def prepare_panel(
    panel: DataFrame, cfg: UseCaseConfig, entity: str, targets: dict
) -> tuple[DataFrame, list[dict], dict]:
    """The panel of `load_panel` (or the saved model input) prepared for `cfg`: its columns
    dropped and renamed by `read_side_columns`, eligibility applied, the candidates resolved,
    the contract checked, the split assigned; the keys, the candidates, the tags, `eligible`,
    `target` and `split`, with the log and the meta (`PANEL_META_KEYS`; the lineage under its
    read names)."""
    if cfg.use_case not in targets:
        raise ValueError(
            f"the panel has no target for use case {cfg.use_case!r}; its use cases: "
            f"{sorted(targets)}"
        )
    own = targets[cfg.use_case]
    features = cfg.entities[entity].sources.features
    dropped, renames = read_side_columns(panel.columns, targets, cfg.use_case, features)
    panel = panel.drop(*dropped)
    for old, new in renames.items():  # in order: `source_target` before `target_<use_case>`
        panel = panel.withColumnRenamed(old, new)
    renamed = {old: new for old, new in renames.items() if old != own["column"]}
    read_log = _read_side_log(dropped, renamed)
    _check_named_features(panel, cfg)
    panel, eligibility_log = apply_eligibility(panel, cfg.data.eligibility, period_spec(cfg))
    lineage = [renames.get(column, column) for column in own["lineage"]]
    candidates = resolve_candidates(panel.columns, cfg, lineage)
    tags = modelling_tags(cfg)
    contract_log = check_contract(panel, cfg, own["null_in_window_share"])
    panel = assign_split(panel, cfg)
    columns = [*KEYS, *candidates, *tags, "eligible", "target", "split"]
    meta = {
        "data_definition_hash": data_definition_hash(cfg, entity),
        "target_spec_hash": target_spec_hash(cfg, entity),
        "hash_version": HASH_VERSION,
        "lineage": lineage,
        "candidates": candidates,
        "tags": tags,
    }
    return panel.select(columns), [*read_log, *eligibility_log, *contract_log], meta


def _read_side_log(dropped: dict[str, str], renamed: dict[str, str]) -> list[dict]:
    """The columns dropped, with why, and the source columns read under another name, printed:
    a `drop` then a `rename` entry, each only when there is one."""
    for column, reason in dropped.items():
        print(f"column {column!r} dropped: {reason}")
    for old, new in renamed.items():
        hint = (
            "; if it is a label, list it in data.target.lineage" if old.lower() == "target" else ""
        )
        print(f"column {old!r} of the sources read as {new!r} (the dataset adds its own "
              f"{old.lower()!r}){hint}")  # fmt: skip
    log = [{"step": "drop", "dropped": dropped}] if dropped else []
    return log + ([{"step": "rename", "renamed": renamed}] if renamed else [])


def build_panel(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[dict], dict]:
    """The panel built in memory for one config: `load_panel` of the one config, then
    `prepare_panel`; the prepared panel with the join log followed by the preparation's log,
    and the preparation's meta."""
    panel, log, meta = load_panel([cfg], entity, env, spark)
    panel, prepared_log, prepared_meta = prepare_panel(panel, cfg, entity, meta["targets"])
    return panel, [*log, *prepared_log], prepared_meta
