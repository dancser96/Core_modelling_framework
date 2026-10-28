# Environment adapter
**Status:** building (M2.1, from 2026-10-26; the compat shim is built) · **Legacy:** `src/_compat.py`, `src/io.py` (`_read`), `src/inference.py` (`_put_file`, `_read_text`, `_fetch_dir`, `_is_hdfs`)
**Related:** [`docs/context/environment.md`](../context/environment.md) · [config](config.md) (what the environment file is kept out of) ·
[dataset](dataset.md) (the collect budget, the model input) · [lifecycle](lifecycle.md) (tier paths) ·
[reporting](reporting.md) (theme) · [test harness](test_harness.md) (synthetic sources) · D-011, D-021, D-024, D-079,
D-088, D-100, D-130, D-131, D-133 · OD-06, OD-26

## Purpose
The single seam between framework logic and wherever it runs (laptop vs bank). Framework code never
checks where it is running; it calls this module, and the **environment file** decides.

## The environment file (D-130)
`conf/local/environment.yml` (gitignored) holds the environment facts only, under its own schema:
Spark settings, roots (data; registered and production from M2.4), the physical sources per entity
by logical name, the collect budget and the theme. An unknown key fails loud, so a modelling
field can't hide there. The use-case config never holds a physical name, and there is **no merge**
of the environment file over the config: it is loaded beside the config, by a path argument or
the `CORE_MODELLING_ENVIRONMENT` variable, never from the working directory (T5). The hashes
exclude it (D-088); the resolved config's housekeeping block records the values a run used. The
laptop's file points at the synthetic `dev` dataset; the bank fills its own. The example, with
placeholders, is `conf/base/environment.example.yml`:

```yaml
schema_version: 1                        # the environment file's own version; migrated at load (CLAUDE.md §2)
spark:
  master: "local[*]"
  driver_memory: 2g
  shuffle_partitions: 8
  time_zone: UTC
  extra: {}                              # any other spark.* setting; the named and fixed keys are refused here
roots:
  data: /ABSOLUTE/PATH/data              # the layers of data/README.md hang off it
  registered: null                       # set when M2.4 builds register / promote / deploy
  production: null
sources:                                 # logical name → physical, per entity
  entity_a:
    retail_mart:          {format: parquet, path: /ABSOLUTE/PATH/data/01_raw/synthetic_dev/mart}
    retail_holdings:      {format: parquet, path: /ABSOLUTE/PATH/data/01_raw/synthetic_dev/holdings}
    cc_acquisition_input: {format: parquet, path: /ABSOLUTE/PATH/data/05_model_input/cc_acquisition/entity_a}
collect_budget_gb: 1.5                   # the collect printout's budget (D-133)
theme: null
```

Inside the bank a source is `{format: table, table: <name>}` or a parquet path; a relative path
is refused (T5). Credentials references, if any, also live here and never in the repo.

## Phase 2 requirements
1. Create or get the Spark session from the environment file's `spark` settings, with Arrow on
   (its silent fallback off), the UI off and the app name set, through the **public**
   `get_spark_session(env)` (D-024). `getOrCreate()` silently reuses an existing session: it
   ignores static settings (master, memory) and overwrites runtime SQL settings, and `spark.conf`
   then shows the requested static value while the JVM keeps the old one. So when a session
   already exists, the function compares the requested settings with
   `spark.sparkContext.getConf()` and the runtime conf and fails loud listing every difference,
   detecting the session process-wide (`getActiveSession` is thread-local),
   never keeping the old session quietly (D-100 (c); e.g. a notebook's setup cell rerun with
   other settings).
2. Apply the numpy/PySpark compat shim once, before any pyspark/flaml import (T1).
3. Transport functions that work for local paths and `hdfs://` URIs alike (`read_text`,
   `write_text`, `put_file`, `fetch_dir_to_local`): M2.4, with the registered and production
   roots.
4. Path construction from the environment file's roots, by string joining, never with `pathlib`
   (T2). The local layout under `roots.data` (the layers of `data/README.md`):
   - `04_feature/<use_case>/<entity>/<data_definition_hash>/`: the decision audit log under
     `decisions/` (Stage 1) and, from M2.2, the EDA and Feature Checks artifacts;
   - `05_model_input`: where the environment file's source entry for `data.model_input` points
     (D-131), e.g. `05_model_input/<use_case>/<entity>`;
   - `06_models/<use_case>/<entity>/<run_id>/`: local-tier runs (M2.3).

   The registered and production roots are `null` until M2.4; the bank-side layout per entity ×
   domain is OD-06.
5. Source resolution per entity: `entities.<e>.sources` in the use-case config names logical
   sources, and `sources.<entity>.<name>` in the environment file maps each to a parquet path or a
   table. The example maps three for `entity_a`: `retail_mart` (the governing spine),
   `retail_holdings` (the target source) and `cc_acquisition_input` (the model input, a parquet
   source whose path stays local until the transport of M2.4, like the audit log's). On a
   laptop they point at the synthetic dataset in `data/01_raw/` and `data/05_model_input/`. In
   the first release a source can also be the feature store, alone or next to other sources
   (D-021); a `feature_store` format is refused at load until OD-26 is settled, since the
   integration is designed after the work stream that learns it. One use case config shows the
   three source settings (the feature store, other sources, both); outside the bank only the
   other-sources setting runs, on synthetic data, and the two feature-store settings ship
   commented out. In Phase 2 the feature store integration is limited to Stage 1, where a use
   case's data comes in; no later stage knows about it (D-021).
6. The report theme: `theme` in the environment file (the mechanism in Phase 2; the corporate
   look it applies comes after internalisation).

## Design constraints
- Plain functions in one module until it genuinely outgrows ~300 lines.
- `hdfs dfs` subprocess calls in one place, failing loud (M2.4).
- Local-I/O helpers accept `str | Path` and coerce at the boundary (T4).
- The adapter never derives `spark.driver.maxResultSize` from the collect budget; the printout's
  callout names the setting (D-133).

## Lessons from the crunch
T1–T5 (`docs/context/lessons.md`).

## Interface
Built: `core_modelling/_compat.py`, the `np.NaN` alias applied on package import (T1; verified
2026-10-14: without it, `import pyspark.pandas` fails on the pinned numpy 2.3.5 + PySpark 3.4.3).

Built in Stage 1's major step 1 (2026-10-26; under the SDS's review), in
`core_modelling/environment.py` (176 lines). They replace the M1 private session and source
functions and their YAML source mapping.
- `EnvironmentConfig` (Pydantic, `extra="forbid"`): `spark: SparkSettings` (master,
  driver_memory, shuffle_partitions, time_zone, extra), `roots: Roots` (data, registered,
  production), `sources: dict[str, dict[str, Source]]` (entity → logical name → `{format, path |
  table}`), `collect_budget_gb: float`, `theme: str | None`.
- `load_environment(path: str | None = None) -> EnvironmentConfig` (public, D-024: the
  notebooks' setup cell calls it): the argument, else `CORE_MODELLING_ENVIRONMENT`, else fail
  loud naming both.
- `get_spark_session(env: EnvironmentConfig) -> SparkSession` (public, D-024): req. 1.
- `read_source(spark, env, entity: str, name: str) -> DataFrame`: parquet by path or a table.
- `data_path(env, layer: str, *parts: str) -> str`; `audit_log_dir(env, use_case, entity,
  data_definition_hash) -> str`.
- `tests/conftest.py`: the `spark` fixture, one real session per test run through
  `get_spark_session` (T15), and `unit_env`, an environment on the written `unit` preset.

## Open questions
- The bank-side folder layout for the registered/production tiers per entity × domain (OD-06).
  Whether storage permissions differ per entity is the platform's (D-079).
