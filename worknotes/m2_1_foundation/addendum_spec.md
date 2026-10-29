# Stage 1 addendum: the spec every builder follows
_Written 2026-10-28 from the SDS's answers (Q400 reworked and accepted, Q401 as proposed, Q403
approved, Q405 `target_<use_case>`, Q406 one shape). Three changes built in one pass:
**B** one model input for several use cases, **A** the unit of analysis as a parameter, **C**
`revert` in the audit log, plus the id cast found by the hash check. This file is the record of
what was built; the design reasoning is in `review_answers.md`._

Rules for every piece: `CLAUDE.md` §1 (functions first, ≤ ~50 lines, type hints and a docstring
on every function, fail loud, no new dependency, no bank names, no cwd-relative paths), §4
(the invariants), `docs/glossary.md` for names. 0.x: renamed config fields get no migration
(D-007 (c)); a config with an old name fails naming the unknown key.

## A. The unit of analysis: `period`
The framework meant "month" in two senses: a calendar month (stays "month") and the unit of
analysis, one row per unit per period (becomes **period**). The synthetic data stays monthly, so
the synthetic package, its tests, its notebook and `test_harness.md` keep "month"; so does
`monitoring.retrain_policy.max_age_months` (a model's age is calendar time).

**Config** (`config/schema.py`):
- `data.keys: {unit_id: <col>, period: <col>}` (was `month`).
- `time.period: Literal["month", "week", "day"] = "month"`.
- `time.observation_window: {first: date, last: date}` (was `train_months`).
- `time.target_window: int ≥ 1` (was `target_window_months`): w periods, t+1 … t+w.
- `time.validation_period: date` (was `validation_month`).
- A period is held as its last day. The typo rule at load, in a `model_validator` on `Time`
  (it needs `time.period`): a month is written as its first or its last day (else refused as
  before), a week as any of its days, a day as itself; the three dates are moved to the
  period's end. `_check_validation_after_window`: `index(v) − index(last) ≥ w` by period.
  `Month`, `_month_end` and `_months_between` go.
- `replay.LOGGABLE_SETTINGS`: `"time.validation_period": "evaluation"`.
- `identities.data_definition_hash`: the `time` part includes `period`, `observation_window`,
  `target_window`. The golden digests in `tests/test_identities.py` are re-pinned.

**One plain dict** in a new module `src/core_modelling/periods.py` (no import of `config`):

```python
@dataclass(frozen=True)
class Period:
    """One unit of analysis: a date's period index and its period's start and end, in Python
    and in Spark, how a period is written and which dates a config may write it as."""

    index: Callable[[date], int]  # consecutive periods → consecutive integers
    from_index: Callable[[int], date]  # the inverse, as the period's end
    start: Callable[[date], date]  # the period's first day
    end: Callable[[date], date]  # the period's last day
    spark_index: Callable[[Column], Column]
    spark_end: Callable[[Column], Column]
    label: Callable[[date], str]  # 2025-06 · 2025-W23 · 2025-06-15
    accept: Callable[[date], bool]  # the typo rule at config load


PERIODS: dict[str, Period] = {"month": ..., "week": ..., "day": ...}
```

- month: index `y × 12 + m − 1`, end the last day, start day 1, Spark index
  `year × 12 + month − 1`, Spark end `F.last_day`, label `%Y-%m`, accept day in (1, last).
- week: ISO week, Monday to Sunday; index `(d − 1970-01-05).days // 7` (a Monday), end the
  Sunday, start the Monday, Spark index `floor(datediff(d, '1970-01-05') / 7)`, Spark end
  `date_add(d, 6 − ((dayofweek(d) + 5) % 7))` (Spark's `dayofweek` is 1 on Sunday), label
  `%G-W%V`, accept any day.
- day: index `(d − 1970-01-01).days`, end and start the day itself, Spark index
  `datediff(d, '1970-01-01')`, Spark end the column, label `%Y-%m-%d`, accept any day.
- `period_spec(cfg) -> Period` = `PERIODS[cfg.time.period]`. Never `add_months` or adding days
  to step periods (T19): always the index.

**Where the arithmetic moves** (every `F.col("month")`, `"month"` key, `month_number`,
`last_day` goes through the spec):
- `sources.py`: `read_keyed_source` renames the keys to `unit_id`, `period`, moves `period` to
  `spec.spark_end`, and **casts `unit_id` to string** (so the split's hash draw survives an
  upstream change of the id column's type). The log: `{"source", "periods": [...], "period_tag"}`
  with the tag `"period start"`, `"period end"` or `"other days"` (end checked first, so a day
  period is always "period end"). `period_index` / `period_from_index` are the spec's;
  `missing_periods(periods, first, last, spec) -> list[str]` (labels),
  `check_periods_covered(log, first, last, role, until, spec)`; the message names
  `time.observation_window.first` and `until`.
- `target_factory.py`: `_month_index()` becomes `spec.spark_index(F.col("period"))` in the
  forward window; `load_targets` computes `matured = spec.from_index(spec.index(v) + w)` and
  checks the target source `first … matured` ("time.validation_period + target_window");
  `_check_upstream_tail` by index. **`null_in_window` is null where the window is incomplete**
  (was false), so an average over it is the share among complete windows.
- `tasks.py`: the summary's row key is `period`, labelled by the spec; `all` row unchanged.
- `dataset/*`: `KEYS = ["unit_id", "period"]`; `partitionBy("period")`; the frames select on
  `period`; every per-period dict is keyed by the spec's label; the printouts say "period".
- `split.py`: `negative_downsampling` draws on `(unit_id, period)`; the pinned draw test
  (unit id `'12345'`, salt `split`, seed 42 → 0.322993) is unchanged.
- Tests: the hand-made panels stay monthly, plus in `test_target_factory.py` one weekly and one
  daily forward-window test (a missing period is a gap, never skipped) and in
  `test_sources.py` the end-of-period move for a week (to its Sunday) and a day, the index
  round trip for all three, `missing_periods` across a year end for weeks, and the id cast (an
  integer id reads back as a string).
- Docs: "period" wherever the unit is meant (observation period, validation period, inference
  period, gap periods, "one row per unit per period"); `docs/glossary.md` owns the term.

## B. One model input for several use cases
The table is the sources joined plus one target column per use case, nothing else; everything
config-driven after the join is derived on read from the reader's config (deterministic SQL
and a hash draw, recomputed exactly). A single config is the one-element list: one shape.

**`dataset/panel.py`**
- `KEYS = ["unit_id", "period"]`, `HELPER_COLUMNS = ["target", "split", "eligible"]`.
- `target_column(use_case: str) -> str` = `f"target_{use_case}"` (Q405).
- `load_panel(cfgs: list[UseCaseConfig], entity, env, spark) -> tuple[DataFrame, list[dict], dict]`:
  1. `_check_shared_definition(cfgs, entity)`: the use cases are distinct and every config
     declares the same `entities.<entity>.sources.features`, `data.keys`, `data.model_input`
     and `time.period`; else `ValueError` naming the two use cases and the field.
  2. The spine from `cfgs[0]`, checked to cover `min(observation_window.first)` …
     `max(validation_period)` (`"spine"`, `"time.validation_period"`); the feature sources
     joined as today.
  3. Per config: `load_targets(cfg, …)`; its column `target_column(cfg.use_case)` must not be
     a column of the sources (`ValueError`); left-join `target` as that column and
     `null_in_window` as a transient `_null_<column>`, with a marker `_from_<column>`, role
     `"targets"`.
  4. Rows from `min(first)` to the spine's last period.
  5. `_join_log(panel, joined, cfgs)`: one rollup per period as today (spine rows, matched rows
     per joined source, plus `avg(_null_<column>)` per target); per config, a window period
     with no known value in its target column fails loud naming the use case. Returns the
     entries and the null shares.
  6. The markers and `_null_*` columns dropped. Returns the panel (keys, every feature
     column, the target columns), the join log and the meta:
     `{"hash_version", "sources": {"features": [...]}, "keys": {...}, "period": "month",
     "periods": {"first": label, "last": label}, "targets": {use_case: {"column",
     "target_spec_hash", "lineage", "source", "observation_window": {first, last},
     "target_window", "validation_period", "null_in_window_share"}}}` (dates as labels).
- `prepare_panel(panel, cfg, entity, targets: dict) -> tuple[DataFrame, list[dict], dict]`,
  the read side: drop the other use cases' target columns (`targets[u]["column"]`, u ≠ own)
  and rename the own one to `target`; then as `build_panel` does today: `apply_eligibility`,
  `resolve_candidates(panel.columns, cfg, lineage)` with the lineage from `targets`,
  `_check_named_features`, `modelling_tags`, `check_contract(panel, cfg,
  targets[own]["null_in_window_share"])`, `assign_split`, the select
  `[*KEYS, *candidates, *tags, "eligible", "target", "split"]`; the meta as today
  (`PANEL_META_KEYS`: `data_definition_hash`, `target_spec_hash`, `hash_version`, `lineage`,
  `candidates`, `tags`). A `cfg.use_case` not in `targets` fails naming the saved use cases.
  Another use case's target is forward-looking and is never a candidate, by construction.
- `build_panel(cfg, entity, env, spark)` = `load_panel([cfg], …)` then `prepare_panel`; the
  in-memory path and the tests keep using it; its return shape is unchanged.

**`dataset/contract.py`**: `check_contract(panel, cfg, null_in_window_share: float | None)`;
`_null_callout(share, cfg)` takes the share (no column scan): `None` → unknown (upstream
target), above 0 → the callout text as today.

**`dataset/model_input.py`** (sidecar schema 3; the comment names the bump reason):
- `save_model_input(cfgs: UseCaseConfig | list[UseCaseConfig], entity, env, spark) -> str`:
  one config is the one-element list; `load_panel`, written partitioned by `period`; the
  sidecar: `schema_version`, `framework_version`, `built_at`, `entity`, `model_input`,
  `use_cases` (in order), the meta of `load_panel`, `columns`, `log` (the join log).
- `read_model_input_metadata(cfg, entity, env) -> dict`: in order, each refused naming
  `save_model_input`: no table or sidecar; another `schema_version` (with the version note as
  today); another `hash_version`; other `sources.features`, `keys` or `period`; `cfg.use_case`
  not in `targets`; another `target_spec_hash` for it; `periods` not covering
  `observation_window.first … validation_period`. A changed eligibility, window, split or
  candidate list is **not** refused: that is the point.
- `read_model_input(cfg, entity, env, spark)`: read, cast `period` to date, select the saved
  columns, `prepare_panel(panel, cfg, entity, metadata["targets"])`; returns the prepared panel,
  the join log plus the preparation's log, and the preparation's meta.
- `saved_candidates(cfg, entity, env)`: `resolve_candidates` over the sidecar's columns minus
  the target columns, with the lineage from the sidecar: no Spark.

**`run.py` and `__main__.py`**: `run(config_paths: str | Path | list[str | Path], env_path,
stages, entity)` loads every config; a stage function takes the list
(`Stage = Callable[[list[UseCaseConfig], str, EnvironmentConfig, SparkSession], dict]`);
`_run_target_factory_stage` prints every config's summary (`{"summary": {use_case: frame}}`)
and saves once when the configs name a model input (`"model_input": path`); the entity must be
in every config. CLI: `run a.yml b.yml --stages target_factory` (`config` takes `nargs="+"`).
`run_target_factory(cfg, …)` stays per config.

**`target_factory.py`**: `load_targets` unchanged in shape (`unit_id`, `period`, `target`,
`null_in_window`); `run_target_factory` per config.

## C. `revert` in the audit log
- `replay.Op` gains `"revert"`; `Entry` gains `to_seq: int | None = None` (`ge=0`; 0 = the
  config as written). The operand check: `revert` needs `to_seq` and takes no features, path,
  from or to; every other op takes no `to_seq`. `to_seq` must be below the entry's own `seq`.
- `replay(cfg, entries)`: a `revert` entry restarts the raw dict from the config with entries
  1 … `to_seq` replayed (the slice; recursion handles a revert inside it) and continues after
  it. `_origins` restarts the same way. The entries after the reverted point stay in the log as
  the trail; `resolve_config(upto=n)` still reproduces every earlier state.
- `write_resolved`: one header line per revert, `# entry 14 reverted to the state after #8`.
- `record_decision(…, revert_to: int | None = None)`: the fifth operation, exactly one of the
  five; CLI `decide --revert-to N`. `show_decisions` shows `to #8` in `what`.
- `log_schema_version` is not bumped: a new op, old entries stay readable.
- Tests (`tests/test_audit_log.py`): path A (three entries), `revert` to 1, path B (one entry):
  the resolved config is the config plus entries 1 and 5; `upto=3` reproduces A; a revert to 0
  gives the config as written; `to_seq` not below `seq` is refused; the header line; the
  `show_decisions` row; the CLI flag.

## D. Acceptance for the whole addendum
`pytest` (full suite) green, `ruff check .` and `ruff format --check .` clean, the Target
Factory notebook's cells run on the dev data and save a model input at sidecar schema 3, and
`run conf/base/cc_acquisition.yml <second config> --stages target_factory` saves one table with
two target columns.
