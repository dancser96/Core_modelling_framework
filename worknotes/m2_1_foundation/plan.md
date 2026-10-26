# Stage 1 (M2.1 Foundation): build plan
_Written 2026-10-26 for the SDS · built from `questions.md` (Q349–Q373, all answered) · D-022 (the
Phase 2 plan: skeleton first, two rounds), D-072 (a) (major steps end in the SDS's review, minor
steps in the review skills and subagents) · amended at each major step's review; deleted with the
folder when the stage is done_

**Verdict.** Three major steps over six working days (10-26 – 11-02): the config spine and the
environment adapter; Target Factory with the holdings table; the dataset with `run`, the thin
notebook and the LDS's review guide. Stage 1 is done when `cc_acquisition.yml` gives the window
frame and the train, test and validation frames on the `dev` dataset, with the join, eligibility,
split and collect logs, through a notebook and the CLI alike, and every Stage 1 test passes in
under two minutes on the `unit` preset.

## 1. Ground rules

- **Review rhythm.** Each minor step ends with `pytest`, `ruff check .`, and the reviewers:
  `code-reviewer` and `simplicity-review` always; `silent-failure-hunter` where the step loads,
  validates or writes; `compat-guardian` where it touches a schema, an artifact format or the
  Public API; `ml-correctness-auditor` (xhigh) for Target Factory and the dataset. Each major step
  ends in the SDS's review with a review guide (D-003 (b)); the LDS reviews the ML-critical code
  of major steps 2 and 3 in full from `review_guide.md`.
- **Size.** A minor step is one logical change of about 300–400 changed lines of code at most;
  functions ≤ ~50 lines; one module one concept (`CLAUDE.md` §1).
- **Delegation** (D-072 (b), the `delegation` skill). Each minor step is a complete brief to one
  agent with disjoint files; the main thread integrates, runs the suite, runs the reviewers and
  writes the record (decisions, UPDATES, sync, log, review guides). Code on the §4 path (Target
  Factory, dataset) and anything that feeds a decision runs on the strong model at high effort;
  mechanical pieces on sonnet. Steps with disjoint files run in parallel.
- **Memory.** One Spark job at a time on the laptop; dataset regeneration and the slow suite run
  in the background.
- **Docs in the same change** (`CLAUDE.md` §8): each minor step updates its owner doc's Interface
  and the records; `doc-sync` closes each major step.
- **Numbering.** Decisions from D-129; re-read the last D-row before numbering (another chat may
  add rows).

## 2. Holistic review (`holistic-review`, before the build)

Holistic review — Stage 1: config spine, environment adapter, Target Factory thin, dataset thin.
- **Goals:** advances Structure (one config, one environment file), Decisions (the audit log),
  Targets and leakage (lineage, time separation), Splits (client split, OOT month), Environment
  (the adapter) and Knowledge (the glossary). Works against none.
- **Knock-on effects:**
  - EDA and Feature Checks (M2.2): read the **window frame** (`build_frames(stage="eda")`), every
    client, labels included (D-030); Feature Checks also reads the gap and latest months from the
    model input. Needed: nothing now; their sections exist in the schema with defaults.
  - Training (M2.3): reads train / test from `build_frames(stage="training")`, the sampling record
    (true and sampled rate) and the resolved config from the audit log's replay. Needed: the
    `training` section's fields exist from Stage 1.
  - Evaluation: the validation frame carries `split`, so "validation on test clients only" is a
    filter. Needed: nothing now.
  - Lifecycle (M2.4): `register` packs the audit log's slice from `04_feature/<…>/decisions/`;
    `roots.registered` and `roots.production` exist in the environment file as `null`.
  - Inference: reads the **sources**, not the model input, and applies the model's eligibility to
    the inference month; the same `apply_eligibility` and key renaming serve it. The master layer's
    `unit_id` matches the renamed key.
  - Monitoring (M4): labels for scored months need `build_targets` on a later month range; the
    function takes the source frame, so nothing blocks it.
  - Reporting: every report's choices block reads the resolved config and the logs that
    `Frames.log` and `Frames.meta` carry.
  - Run modes: `run --stages target_factory` and `decide` land now; `register`, `promote`,
    `deploy` later.
  - Synthetic data: the holdings table is additive (0.5.1); both datasets are regenerated once.
- **Shape / compatibility risks:** the config schema and the environment file are new formats
  (`schema_version: 1`); `build_frames`, `save_model_input`, `run_target_factory`,
  `record_decision`, `show_decisions`, `resolve_config`, `run` and `get_spark_session` join the
  Public API (D-024). 0.x promises nothing (D-007 (c)); compat-guardian runs on steps 1.2, 1.4, 1.5,
  3.4 and 3.5. The target column is `target`, the keys `unit_id` and `month`: task-agnostic.
- **Invariants touched:** §4.1 (time separation, Target Factory), §4.2 (`v ≥ tk + w` at load),
  §4.8 (contract checks before sampling), §4.9 (eligibility identical across frames and the
  inference month), §4.11 (client split), §4.12 (sampling after the split, train-only), §4.10
  (hashes). The ML auditor runs on 2.2, 3.1–3.4.
- **Contradictions:** `config.md` req. 2 ("`conf/base` → `conf/local` merge") is replaced by the
  environment file (Q358); `target_factory.md` req. 5's "refused with a reason" becomes guidance
  (Q367); `dataset.md` req. 5's "fail loud" on the budget becomes a callout (Q371); OD-25 closes
  (Q360). All fixed in minor step 1.1.
- **Gaps:** where the environment file is found inside the bank (a path argument or an environment
  variable, settled in 1.4); the `define` step's null semantics (a null condition counts as false
  in a filter: documented in the template, from the fact check); the trap test mapping (M2.2).
- **Simpler alternative:** none taken; the dataset package is the one place where a single module
  would have exceeded 300 lines.
- **Verdict:** proceed.

## 3. Facts checked on the pinned versions (2026-10-26, fact-check agent, local runs)
- `F.xxhash64(*cols)` takes no seed (fixed 42); a literal salt column changes the hash; the result
  is a signed long, so the residue is `F.pmod(hash, 1000)`, in 0–999. Deterministic across
  processes on this machine; across machines unverified (Spark's own XXH64, expected to match).
- `spark.driver.maxResultSize` applies to the Arrow `toPandas` path; the error is a
  `SparkException` naming the serialized size and the limit. The callout names the setting.
- `partitionOverwriteMode=dynamic` replaces only the partitions in the written frame.
- `getOrCreate` on an existing session returns it, overwrites runtime SQL settings and ignores
  static ones; `spark.conf` shows the requested static value while the JVM keeps the old one, so
  the check compares against `spark.sparkContext.getConf()`.
- `DataFrame.filter("<sql>")` resolves a boolean column by name; a missing column raises an
  `AnalysisException` at call time, before any action. A null boolean in a filter drops the row.
- With Arrow, `toPandas` returns date columns as `datetime.date` objects and integer columns with
  nulls as float64.

## 4. Package layout after Stage 1

- `src/core_modelling/`
  - `__init__.py`: version 0.2.0 at the end of the stage (0.1.0 now)
  - `__main__.py`: the CLI, `run` and `decide`
  - `_compat.py` (exists)
  - `environment.py`: the environment file's schema, `get_spark_session`, source reading, paths
  - `config/`
    - `__init__.py`: `load_config`, `UseCaseConfig`
    - `schema.py`: the Pydantic models, one per section
    - `levels.py`: `LEVEL_DEFAULTS`
    - `migrations.py`: `MIGRATIONS`, `migrate`
    - `identities.py`: the hashes
    - `audit_log.py`: entries, `record_decision`, `show_decisions`, `resolve_config`, replay
  - `tasks.py`: `TASK_SPECS`, the per-task spec (target rules, the target summary and contract
    checks in Stage 1)
  - `sources.py`: `read_keyed_source`, a logical source with its keys renamed and its months at
    their last day; Target Factory, the dataset and later Inference read through it (a top-level
    module, so `target_factory` and `dataset` both import it without a cycle)
  - `target_factory.py`: `build_targets`, `load_targets`, `target_lineage`, `run_target_factory`
  - `dataset/`
    - `__init__.py`: `build_frames`, `save_model_input`, `Frames`
    - `panel.py`: sources joined, eligibility, the target attached, candidates resolved
    - `split.py`: the client split and the two sampling options
    - `contract.py`: the contract checks
    - `frames.py`: `Frames`, the collect with its printout, the model input saved and read
  - `run.py`: `run`, `STAGES`
- `conf/base/`: `cc_acquisition.yml`, `TEMPLATE.yml`, `environment.example.yml`
  (`sources.example.yml` goes)
- `conf/local/environment.yml` (gitignored; `sources.yml` goes)
- `notebooks/01_target_factory.ipynb`
- `tests/`: `test_config_schema.py`, `test_identities.py`, `test_audit_log.py`,
  `test_environment.py` (rewritten), `test_target_factory.py`, `test_dataset.py`, `test_run.py`;
  `conftest.py` extended (an environment and a config fixture on the `unit` preset)

## 5. Major step 1: config spine and environment adapter (10-26 – 10-27)

Ends in the SDS's review of: the schema and the template, the hashes, the environment file, the
audit log. Review guide: `review_guide.md` → Major step 1.

### 1.1 Decisions into the docs (parallel with 1.2 and 1.4)
Main thread: D-129–D-13x in `docs/decisions.md` (the config layout; the environment file; the
model input; the collect printout; OD-25's mapping), OD-25 deleted from the roadmap,
`docs/UPDATES.md` statuses, sync and log. Agent A (strong, high; docs only): `config.md` (the
shape → the agreed YAML; req. 2 load = config + environment file; `define` / `filter` steps;
`decision` and `strata` blocks; the model input; req. 8 time rules with Q361; the level mapping
table from Q360 as settled; Interface planned), `dataset.md` (the two frame shapes; join rules;
model input; the collect printout; contract checks per task; Interface planned),
`environment.md` (the environment file, the public session function, source resolution per
entity, local paths), `target_factory.md` (req. 5 reworded; the model input; Interface planned),
`architecture.md` (§3, §10, §11, Public API "planned" list), `glossary.md` (model input, governing
spine, define / filter step, collect budget, environment file), `data/README.md` (05_model_input),
`conf/base/README.md`, and the Phase 3 sweep (Q353) in these files. Agent B (sonnet, medium; docs
only, disjoint): the Phase 3 sweep over `eda.md`, `feature_checks.md`, `feature_ledger.md`,
`training.md`, `evaluation.md`, `reporting.md`, `lifecycle.md`, `inference.md`, `monitoring.md`,
`run_modes.md`, `test_harness.md`, with the roadmap's wishlist as the only destination. Reviews:
the main thread reads every doc diff against §8.

### 1.2 Schema, levels, migrations, template (parallel with 1.1 and 1.4)
Agent (strong, high). Files: `config/__init__.py`, `config/schema.py`, `config/levels.py`,
`config/migrations.py`, `conf/base/cc_acquisition.yml`, `conf/base/TEMPLATE.yml`,
`tests/test_config_schema.py`.
- `load_config(path: str | Path) -> UseCaseConfig`: YAML → `migrate` → `apply_level_defaults` →
  `UseCaseConfig.model_validate` (`extra="forbid"` on every model, so a leftover key fails loud
  naming the key).
- `schema.py`: `UseCaseConfig` with one model per section (`Decision`, `Entity`, `Sources`,
  `Data`, `Keys`, `EligibilityStep`, `Target`, `Split`, `RateBand`, `Time`, `Features`,
  `Candidates`, `Strata`, `Eda`, `FeatureChecks`, `CheckStep`, `Training`, `Selection`,
  `Categoricals`, `Calibration`, `Sampling`, `Evaluation`, `Slices`, `Lifecycle`, `Inference`,
  `Monitoring`), fields and comments as in `questions.md` → Q354. Validators, one per rule:
  `use_case` splits into `product` and `activity` (D-128); `train_months.first ≤ last`;
  `validation_month ≥ last + target_window_months`; `target_window_months ≥ 1`; `decision.type`
  `top_n` needs `n`; an eligibility entry has exactly one of `define` / `filter`, and a `filter`
  has a `reason`; `target` has `rule` + `column` or `column` alone; `sampling.method` with its
  parameters; `metric` in FLAML's names when set (T9); `test_share` in (0, 1).
- `levels.py`: `LEVEL_DEFAULTS: dict[str, dict[str, dict]]`, path → {autonomous, assisted}
  (`eda.key_features.top_n`: 10 / 20; `training.max_iter`: 50 / 200; the rest as the docs name
  them); `apply_level_defaults(raw: dict) -> dict` fills nulls only.
- `migrations.py`: `CURRENT_SCHEMA_VERSION = 1`, `MIGRATIONS: dict[int, Callable[[dict], dict]]`
  (empty), `migrate(raw: dict) -> dict` (applies in order with a `DeprecationWarning`; a version
  above the current one fails loud).
- `TEMPLATE.yml`: every option with a one-line when-to-use; `cc_acquisition.yml`: the walking
  skeleton's values (months 2025-03 … 2025-08, `w` 3, validation 2025-11).
- Tests: the example and the template load; level defaults resolved and explicit values win;
  unknown key; each time rule; the name split; `top_n` without `n`; eligibility entry rules;
  sampling validation; a future `schema_version`.
- Reviews: code-reviewer, simplicity, silent-failure-hunter, compat-guardian.

### 1.3 Identities (after 1.2)
Agent (strong, high). Files: `config/identities.py`, `tests/test_identities.py`.
- `HASH_VERSION = 1`; `canonical_json(data: dict) -> str` (sorted keys, dates as ISO strings,
  from `model_dump(mode="json")`); `_sha256(text) -> str`; `short(digest: str) -> str` (12 chars).
- `config_hash(cfg) -> str`: every section after level resolution.
- `data_definition_hash(cfg, entity: str) -> str`: the entity name, its sources, `data.keys`,
  `data.eligibility`, `data.target`, `time.train_months`, `time.target_window_months`,
  `features.candidates`.
- `target_spec_hash(cfg, entity) -> str`: `data.target`, `data.keys`, `time.target_window_months`,
  the target source's name.
- `resolved_input_hash(resolved: UseCaseConfig) -> str`: the resolved config without the
  housekeeping block.
- Tests: the validation month changes the config hash and not the data-definition hash; a
  candidate pattern changes it; the entity is in it; a `training` field changes neither the
  data-definition nor the target-spec hash; the same config hashes the same twice.
- Reviews: code-reviewer, simplicity, compat-guardian.

### 1.4 Environment adapter (parallel with 1.1 and 1.2)
Agent (strong, high). Files: `environment.py`, `conf/base/environment.example.yml`,
`conf/local/environment.yml` (the laptop's; gitignored), `tests/test_environment.py`,
`tests/conftest.py` (the `spark` fixture and an `env` fixture), delete `conf/base/sources.example.yml`
and `conf/local/sources.yml`.
- `EnvironmentConfig` (Pydantic, `extra="forbid"`): `spark: SparkSettings` (master,
  driver_memory, shuffle_partitions, time_zone, extra), `roots: Roots` (data, registered,
  production), `sources: dict[str, dict[str, Source]]` (entity → logical name → `{format, path |
  table}`), `collect_budget_gb: float`, `theme: str | None`.
- `load_environment(path: str | None = None) -> EnvironmentConfig`: the argument, else the
  environment variable `CORE_MODELLING_ENVIRONMENT`, else fail loud saying both; a relative
  parquet path is refused (T5).
- `get_spark_session(env: EnvironmentConfig) -> SparkSession` (public): the settings dict from
  `spark`, Arrow on with the silent fallback off, UI off; when `SparkSession.getActiveSession()`
  exists, compare the requested settings with `sparkContext.getConf()` and the runtime conf, and
  fail loud listing every difference (D-100 (c)).
- `read_source(spark, env, entity: str, name: str) -> DataFrame`: parquet by path or a table; a
  `feature_store` format fails loud with "not implemented until OD-26".
- `data_path(env, layer: str, *parts: str) -> str`: string joins, never `pathlib` (T2);
  `audit_log_dir(env, cfg, entity, data_definition_hash) -> str`
  (`04_feature/<use_case>/<entity>/<hash>/decisions`).
- Tests: the example file loads once its placeholders are filled; an unknown key fails; neither a
  path nor the variable fails; a relative path is refused; the unit mart reads through an
  environment; a second `get_spark_session` with other settings raises and names the difference.
- Reviews: code-reviewer, simplicity, silent-failure-hunter, compat-guardian,
  `bank-parity-check` (IO).

### 1.5 Decision audit log and `decide` (after 1.2 and 1.3)
Agent (strong, high). Files: `config/audit_log.py`, `__main__.py` (`decide` only; `run` comes in
3.5), `tests/test_audit_log.py`.
- `Entry` (Pydantic): `seq`, `time`, `by: {kind, id}`, `stage`, `op`, `features` or `path` /
  `from_` / `to`, `reason`, `evidence`, `data_definition_hash`, `log_schema_version`; run markers
  add `run_id`, `replayed_to`, `resolved_input_hash`.
- `LOGGABLE_SETTINGS: dict[str, str]` (path → stage): `training.max_iter`,
  `training.time_budget_s`, `training.sampling`, `training.calibration.method`,
  `feature_checks.steps`, `eda.key_features`, `time.validation_month` (stage `evaluation`; the
  refusal once a Feature Checks run compared it, D-088, is added in M2.2), `automation_level`
  (stage `eda`: a level move reruns from EDA, D-132).
- `APPLY_BY_OP: dict[str, Callable]`: `exclude`, `include`, `keep_despite_flag`, `set` change the
  input (`features.excluded`, `features.kept_despite_flags`, the listed path); `flag`, `dropped`,
  `sign_off`, `register`, `promote`, `run` are `_leave_unchanged`.
- `record_decision(config_path, entity, *, exclude=None, include=None, keep_despite_flag=None,
  set=None, reason, evidence=(), by=None, stage=None, env_path=None) -> Entry`: refuses a missing
  reason, a setting not listed, a value the schema rejects, a feature outside the candidates (the
  model input's resolved list when it exists, else the patterns), a data-definition hash that
  differs from the log's; writes `<seq>.json` create-if-absent and retries on a clash.
- `read_entries(log_dir) -> list[Entry]`; `resolve_config(cfg, entity, env, upto=None,
  save_to=None) -> UseCaseConfig` (replay through `APPLY_BY_OP`, validate, a stale entry fails loud
  citing its `seq`); `show_decisions(cfg, entity, env) -> pd.DataFrame`.
- `__main__.py`: `python -m core_modelling decide <config> --entity … --exclude … --reason …`.
- Tests: the worked example of `config.md` replayed (states after #3, #5, #6, #7, #10, #12 and
  the hash changes); a stale entry; each refusal; the `LOGGABLE_SETTINGS` test (every path exists
  in the schema, none is in the data definition or the decision); a clash on write.
- Reviews: code-reviewer, simplicity, silent-failure-hunter, compat-guardian.

### 1.6 Integration and the SDS's review
Main thread: the merged suite and `ruff`; the reviewers' findings fixed or justified; `doc-sync`;
`review_guide.md` → Major step 1 (what to read in which order, what "right" looks like);
`UPDATES.md`, sync, log. The SDS reviews; amendments go into this plan.

## 6. Major step 2: Target Factory and the holdings table (10-28)

Ends in the SDS's review of Target Factory against the oracle. The LDS reads it in full.

### 2.1 The holdings table (parallel with 2.2)
Agent (sonnet, high; the main thread reads the whole diff). Files: `synthetic/src/synthetic/output.py`,
`synthetic/src/synthetic/__init__.py` (0.5.1), `tests/test_synthetic_output.py`,
`docs/components/test_harness.md` (the written tables), `synthetic/REVIEW.md`,
`conf/base/environment.example.yml` and `conf/local/environment.yml` (`retail_holdings`).
- `TABLES` gains `holdings`; `_write_months` writes `<out>/holdings/snapshot_month=…/part-0.parquet`
  with `HOLDINGS_COLUMNS = [client_id, casa_flag, cc_flag, td_flag, wealth_digital_flag,
  wealth_trad_flag, ebanking_flag]` from the mart frame; `read_output(out_dir, "holdings")`.
- Test: the holdings table equals the mart's columns on the same keys, every month.
- Background: regenerate `dev` and `canonical` (0.5.1), `--checks`.
- Reviews: code-reviewer, simplicity.

### 2.1b Holdings on last-day months (Q389; parallel with 2.2)
Agent (sonnet, high; the main thread reads the whole diff). Files: `synthetic/src/synthetic/output.py`,
`synthetic/src/synthetic/__init__.py` (0.5.2), `tests/test_synthetic_output.py`,
`docs/components/test_harness.md` (the written tables), `synthetic/REVIEW.md` (the version line).
- The holdings table's month is its month's last day (`snapshot_month=YYYY-MM-<last>/`), the mart
  and the oracle keep the first, so the skeleton's two sources carry the two tags and every run
  exercises the month move (D-129).
- Test: the holdings equal the mart's flags on the same clients, with each month at its last day.
- Background: regenerate `dev` and `canonical` (0.5.2), `--checks`.

### 2.2 The per-task spec, the keyed source and Target Factory
Agent (strong, high; §4 code). Files: `tasks.py`, `sources.py`, `target_factory.py`,
`tests/test_sources.py`, `tests/test_target_factory.py`.
- `sources.py`: `read_keyed_source(spark, env, cfg, entity, name) -> tuple[DataFrame, dict]`:
  `read_source`; the `data.keys` columns renamed to `unit_id`, `month` (a missing one fails naming
  the source's columns); `month` moved to its month's last day (`F.last_day`; a column that is
  not a date or timestamp fails loud naming its type); duplicate `(unit_id, month)` after the move
  fail loud naming the source and up to five keys; the log: the source, its distinct months and
  how they were tagged (first day, last day or other days).
- `tasks.py`: `TASK_SPECS = {"binary": {"target_rules": {"flag_in_window": _flag_in_window},
  "summarise_targets": _binary_summary}, "regression": {"target_rules": {"forward_sum":
  _forward_sum}, "summarise_targets": _regression_summary}}`; `contract_checks` joins in 3.3.
- `target_factory.py`:
  - `build_targets(source: DataFrame, cfg: UseCaseConfig) -> DataFrame`: on a keyed source; a
    contiguous month index `year × 12 + month`, never `add_months` (T19); the rule from
    `TASK_SPECS[cfg.task]` (an unknown rule fails naming the task's rules); the forward window
    `(1, w)` (T8); null unless all `w` later months are present for the unit (panel edge,
    leavers); `leavers: negative` fails loud as not implemented (M4, D-091). Columns: `unit_id`,
    `month`, `target`.
  - `load_targets(cfg, entity, env, spark) -> tuple[DataFrame, dict]`: the target source (the
    spine when `targets` is omitted) read keyed; the rule built, or the upstream `column` taken
    as `target`; with the source's log. `load_panel` (3.1) joins its result.
  - `_flag_in_window(df, column, w) -> Column` (the max of the flag over the window), `_forward_sum`.
  - `target_lineage(cfg) -> list[str]`: `[column]` plus the config's `lineage`.
  - `run_target_factory(cfg, entity, env, spark) -> pd.DataFrame` (public): `load_targets`, then
    the task's summary per month plus an `all` row, printed and returned: rows, the null share,
    the mean target; binary adds positive rows and positive events (distinct units with a
    positive target in the slice: in one month equal to the positive rows, over the window fewer,
    D-082); writes nothing (the model input is major step 3).
- Tests, on the `unit` preset through Spark: the target equals the oracle's
  `realised_target(mart, "cc_acquire", 3)` on the rows with `cc_flag = 0`, nulls included;
  `forward_sum` equals `realised_target(mart, "spend_cc_next_3_months", 3)` for card holders; a
  hand-made three-client frame checks the panel edge, a leaver and that month `t`'s own value never
  enters the target (§4.1); `leavers: negative` is refused; the lineage list; the per-month table's
  counts.
- Reviews: code-reviewer, simplicity, ml-correctness-auditor (xhigh).

### 2.3 Integration and the SDS's review
Main thread: suite, reviewers, `doc-sync` (`target_factory.md` Interface, `test_harness.md`,
`UPDATES.md`), `review_guide.md` → Major step 2, sync, log.

## 7. Major step 3: dataset, `run`, the notebook, the review guide (10-29 – 10-30; 11-02 buffer)

Ends in the SDS's review and the LDS's review of the dataset code in full.

### 3.1 The panel (after major step 2)
Agent (strong, high; §4 code). Files: `dataset/__init__.py`, `dataset/panel.py`,
`tests/test_dataset.py` (its panel tests).
- `load_panel(cfg, entity, env, spark) -> tuple[DataFrame, list[dict]]`: every source read with
  `read_keyed_source` (2.2: keys renamed, months at their last day, duplicate keys refused), the
  spine first; the other feature sources left-joined on the keys; a non-key column in two feature
  sources fails loud; `load_targets` (2.2) left-joined as `target`; months restricted to `train_months.first` … the spine's last month; the
  join log: per source, distinct units per month and the share of spine rows matched.
- `apply_eligibility(df, steps) -> tuple[DataFrame, list[dict]]`: `define` → `withColumn`;
  `filter` → `filter` with rows in → out per month; the define columns dropped at the end.
- `resolve_candidates(columns: list[str], cfg, lineage: list[str]) -> list[str]`: `fnmatch`
  include then exclude, minus the keys, `target`, the lineage and the define names.
- Reviews: code-reviewer, simplicity, silent-failure-hunter, ml-correctness-auditor (xhigh, with
  3.2–3.4 together).

### 3.2 The split and sampling (parallel with 3.1)
Agent (strong, high; §4 code). Files: `dataset/split.py`, `tests/test_dataset.py` (its split
tests; the agent owns a separate `tests/test_split.py` instead, to keep the files disjoint).
- `assign_split(df, cfg) -> DataFrame`: `pmod(xxhash64(unit_id, lit(seed)), 1000) < 1000 ×
  test_share` → `split` = `test` else `train`.
- `sample_train(df, cfg) -> tuple[DataFrame, dict]`: `negative_downsampling` keeps every positive
  and the negatives with `pmod(xxhash64(unit_id, month, lit(seed)), 1_000_000) < keep_fraction ×
  1e6`; `client_sample` keeps the clients with `pmod(xxhash64(unit_id, lit(seed)), 1000) < share ×
  1000`; the record: method, parameters, the true rate (unsampled train) and the sampled rate.
- Tests: no client in both splits; stable across months and reruns; sampling leaves test and
  validation untouched; the record's rates; `null` sampling is the identity.

### 3.3 Contract checks (parallel with 3.1)
Agent (sonnet, high; the spec rows are given). Files: `dataset/contract.py`, `tasks.py` (the
`contract_checks` entries), `tests/test_contract.py`.
- `check_contract(window: DataFrame, cfg) -> list[dict]`: runs `TASK_SPECS[task]["contract_checks"]`
  on the eligible window before any sampling (§4.8): binary = unique `(unit_id, month)`, a
  non-constant target, the pooled rate ≤ `rate_band.max` (reported per month); regression =
  unique keys, a non-constant and finite target. A failure raises with the numbers.

### 3.4 Frames, the collect printout, the model input (after 3.1–3.3)
Agent (strong, high; §4 code). Files: `dataset/frames.py`, `tests/test_frames.py`.
- `@dataclass Frames`: `window`, `train`, `test`, `validation` (pandas, or None when the stage
  didn't ask for them), `log: list[dict]`, `meta: dict`.
- `estimate_collect(df, spark) -> dict`: the exact row count; bytes per row from a 10,000-row
  sample's `memory_usage(deep=True)`; the estimate × 2 for the conversion peak.
- `collect_frame(df, name: str, env) -> pd.DataFrame`: prints rows, columns, the estimate and the
  budget every time; above the budget the printout becomes the callout (declare sampling with the
  two options' when-to-use, or raise `collect_budget_gb` and the Spark settings,
  `spark.driver.maxResultSize` named) and the collect proceeds (Q371). The real size is measured
  after the collect and both go into `meta`.
- `check_candidates` reads the resolved candidate list from the model input's metadata when it
  exists (closing the typo gap of 1.5), and `load_panel` fails loud when a name in
  `features.excluded` or `kept_despite_flags` is not a column.
- `build_frames(cfg, entity, env, spark, stage: str) -> Frames` (public): the model input when
  `data.model_input` is set (its `metadata.json` hash checked against the config's, a mismatch
  fails loud naming `save_model_input`), else `load_panel` → `apply_eligibility` → `check_contract`
  → `assign_split`; `stage` `eda` / `feature_checks` collect the window; `training` / `evaluation`
  collect train (sampled), test and validation; null-target rows dropped from the modelling frames
  with the share logged.
- `save_model_input(cfg, entity, env, spark) -> str` (public): the eligible panel with the
  candidates, `target` and `split`, partitioned by `month` with dynamic partition overwrite, to the
  path `conf/local` maps for `data.model_input`, plus `metadata.json` (schema version, the
  data-definition and target-spec hashes, the lineage, the resolved candidates, the logs, the
  framework version, when).
- Tests: the frames from the model input equal the frames built in memory; a hash mismatch fails
  loud; eligibility identical across frames (the logs agree); contract checks run before sampling
  (the log's order); the printout appears and the callout above a tiny budget; `meta` carries the
  estimate and the real size; the regression task through the same path.
- Reviews: code-reviewer, simplicity, silent-failure-hunter, compat-guardian,
  ml-correctness-auditor (xhigh).

### 3.5 `run`, the CLI and the thin notebook (after 3.4)
Agent (strong, high). Files: `run.py`, `__main__.py` (`run` added), `notebooks/01_target_factory.ipynb`,
`tests/test_run.py`, `src/core_modelling/__init__.py` (0.2.0).
- `STAGES = {"target_factory": _run_target_factory_stage}`, where the stage function calls
  `run_target_factory` and then `save_model_input` when `data.model_input` is set (D-131: the model
  input is written from the notebook or `run --stages target_factory`); `run(config_path,
  env_path=None, stages=None, entity=None) -> dict` loops over the config's entities unless one
  is given.
- `python -m core_modelling run <config> [--env …] [--stages …] [--entity …]`.
- The notebook (thin, D-022 (e)): the guide cell; the setup cell (`load_environment`,
  `get_spark_session`, `load_config`); `run_target_factory` and its table; `build_frames(stage="eda")`
  with the join, eligibility and collect printouts; `save_model_input`.
- Tests: `run` on the unit config through the CLI entry; the notebook calls only the Public API
  (the small test D-024 asks for).

### 3.6 Integration, the review guides, the SDS's and the LDS's reviews
Main thread: the full suite under two minutes on `unit`; `ruff`; every reviewer; `doc-sync`
(`dataset.md` Interface, `architecture.md` Public API table filled, `UPDATES.md` statuses to
`built`, the roadmap's M2.1 row, `glossary.md`); `review_guide.md` → Major step 3 and the LDS's
reading order (dataset and Target Factory in full); sync and log; the handover note if the chat
is long. Then this folder is deleted once the SDS and the LDS have reviewed.

## 8. Deliberately left out of Stage 1
- The `hdfs dfs` transport and the registered / production roots (M2.4).
- Labels for scored months, incremental per-month builds, the count-rise, threshold-on-sum and
  leavers-as-negatives rules (M4, D-091).
- Per-source key renames and column aliases; the feature store source (OD-26).
- EDA and Feature Checks artifacts under `04_feature` (M2.2); the trap-kind acceptance mapping.
- Stage-written audit-log entries (`flag`, `dropped`, `run`, `sign_off`, `register`, `promote`):
  the operations exist, their writers come with their stages.
- The rerun rule after a `set` on `automation_level` (recorded, not acted on until the stages
  exist).
- Any real migration (`MIGRATIONS` is empty), the MLflow question (OD-08), the `unstable` trap kind.

## 9. Timeline

| Day | Work |
|---|---|
| 10-26 | 1.1, 1.2, 1.4 in parallel; 1.3 after 1.2 |
| 10-27 | 1.5; 1.6 (integration, reviews, review guide); the SDS reviews major step 1 |
| 10-28 | 2.1 and 2.2 in parallel; 2.3; the SDS reviews major step 2 |
| 10-29 | 3.1, 3.2, 3.3 in parallel; 3.4 |
| 10-30 | 3.5; 3.6; the SDS reviews major step 3; the LDS's review guide out |
| 11-02 | Buffer: the LDS's findings, fixes, `doc-sync`, the folder deleted |

Risks: 1.5 is the most design-heavy step (the worked example is the test, so drift shows up at
once); the first collect on `dev` through Spark shows whether the 1.5 GB budget prints as expected
on this laptop; the regeneration to 0.5.1 must finish before 2.2's tests use the holdings table
(the tests use the `unit` preset generated in the run, so only the notebook waits).
