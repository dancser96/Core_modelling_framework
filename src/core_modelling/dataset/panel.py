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
from the reader's own config on the saved or the in-memory panel: the other use cases' target
columns are dropped, with the source column an upstream target of theirs is read from (both
are forward-looking), and the own one becomes `target`; then the eligibility steps and the
candidates (`eligibility.py`), the contract check and the split. `build_panel` is both for one
config, the in-memory path.
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
from core_modelling.sources import KEYS, check_periods_covered, read_keyed_source
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
    """The panel's target column of a use case, `target_<use_case>` (Q405)."""
    return f"target_{use_case}"


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
    """The use cases are distinct and every config lists `entity` and declares the same feature
    sources, keys, model input and period, else the two use cases and the field are named."""
    if not cfgs:
        raise ValueError("load_panel needs at least one config")
    names = [cfg.use_case for cfg in cfgs]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"the use cases must be distinct; repeated: {repeated}")
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
        if column in panel.columns:
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
        raise ValueError(
            f"feature source {name!r} shares the columns {shared} with an earlier source; rename "
            "them upstream"
        )


def _check_named_features(panel: DataFrame, cfg: UseCaseConfig) -> None:
    """A name in the audit log's replayed lists that is not a column fails loud (a typo in an
    entry would otherwise exclude nothing)."""
    for field in ("excluded", "kept_despite_flags"):
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
    rows = by_period.values()
    if marker is None:
        entry["rows"] = label_by_period(rows, "rows", spec)
        print(f"spine {log['source']} ({log['period_tag']} periods): {all_rows.rows:,} rows "
              f"from {spec.label(min(by_period))} to {spec.label(max(by_period))}")  # fmt: skip
        return entry
    entry.update(matched_share=all_rows[marker] / all_rows.rows)
    entry.update(matched=label_by_period(rows, marker, spec))
    print(f"join {log['source']} ({role}, {log['period_tag']} periods): "
          f"{entry['matched_share']:.1%} of the spine's rows matched")  # fmt: skip
    if use_case is not None:
        nulls = label_by_period(rows, f"_nulls_{use_case}", spec)
        entry.update(use_case=use_case, column=target_column(use_case), null_in_window=nulls)
    return entry


def foreign_target_columns(targets: dict, use_case: str) -> list[str]:
    """The other use cases' target columns and, for an upstream target of theirs, the source
    column it was read from: both are forward-looking, so the reader never sees them as a
    candidate. The own lineage is reserved by `resolve_candidates`."""
    columns = []
    for other, target in targets.items():
        if other != use_case:
            columns.append(target["column"])
            if target["upstream"]:
                columns.append(target["lineage"][0])
    return columns


def prepare_panel(
    panel: DataFrame, cfg: UseCaseConfig, entity: str, targets: dict
) -> tuple[DataFrame, list[dict], dict]:
    """The panel of `load_panel` (or the saved model input) prepared for `cfg`: the other use
    cases' target columns dropped and the own one as `target`, eligibility applied, the
    candidates resolved, the contract checked, the split assigned; the keys, the candidates, the
    tags, `eligible`, `target` and `split`, with the log and the meta (`PANEL_META_KEYS`)."""
    if cfg.use_case not in targets:
        raise ValueError(
            f"the panel has no target for use case {cfg.use_case!r}; its use cases: "
            f"{sorted(targets)}"
        )
    own = targets[cfg.use_case]
    foreign = foreign_target_columns(targets, cfg.use_case)
    panel = panel.drop(*foreign).withColumnRenamed(own["column"], "target")
    _check_named_features(panel, cfg)
    panel, eligibility_log = apply_eligibility(panel, cfg.data.eligibility, period_spec(cfg))
    candidates = resolve_candidates(panel.columns, cfg, own["lineage"])
    tags = modelling_tags(cfg)
    contract_log = check_contract(panel, cfg, own["null_in_window_share"])
    panel = assign_split(panel, cfg)
    columns = [*KEYS, *candidates, *tags, "eligible", "target", "split"]
    meta = {
        "data_definition_hash": data_definition_hash(cfg, entity),
        "target_spec_hash": target_spec_hash(cfg, entity),
        "hash_version": HASH_VERSION,
        "lineage": own["lineage"],
        "candidates": candidates,
        "tags": tags,
    }
    return panel.select(columns), [*eligibility_log, *contract_log], meta


def build_panel(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[dict], dict]:
    """The panel built in memory for one config: `load_panel` of the one config, then
    `prepare_panel`; the prepared panel with the join log followed by the preparation's log,
    and the preparation's meta."""
    panel, log, meta = load_panel([cfg], entity, env, spark)
    panel, prepared_log, prepared_meta = prepare_panel(panel, cfg, entity, meta["targets"])
    return panel, [*log, *prepared_log], prepared_meta
