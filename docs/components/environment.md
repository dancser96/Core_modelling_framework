# Environment adapter
**Status:** built (partial: compat shim + local Spark session) · **Legacy:** `src/_compat.py`, `src/io.py` (`_read`), `src/inference.py` (`_put_file`, `_read_text`, `_fetch_dir`, `_is_hdfs`)
**Related:** [`docs/context/environment.md`](../context/environment.md) · [lifecycle](lifecycle.md) (tier paths) ·
[reporting](reporting.md) (theme) · [test harness](test_harness.md) (synthetic sources) · D-011, D-021 · OD-06, OD-26

## Purpose
The single seam between framework logic and wherever it runs (laptop vs bank). Framework code never
checks where it is running; it calls this module, and `conf/local/` decides.

## Phase 2 requirements
1. Create or get the Spark session from config, including the Arrow setting and app name.
   `getOrCreate()` silently reuses an existing session: it ignores static settings (master,
   memory) and overwrites runtime SQL settings. Calling the session function again with different
   arguments (e.g. re-running a notebook's setup cell) therefore fails loud or restarts the
   session, never keeps the old one quietly (D-100).
2. Apply the numpy/PySpark compat shim once, before any pyspark/flaml import (T1).
3. Transport functions that work for local paths and `hdfs://` URIs alike:
   - `read_text`
   - `write_text`
   - `put_file`
   - `fetch_dir_to_local`
4. Path construction from config, for data, models (local, registered, production), outputs and
   reports, per entity where the layout needs it (OD-06). HDFS paths are built by string joining,
   never with `pathlib` (T2).
5. Source resolution: a logical source name in the use-case config maps to a physical Hive table or
   path in `conf/local/`. On a laptop it maps to the synthetic dataset in `data/01_raw/`. In the
   first release a source can also be the feature store, alone or next to other sources (D-021);
   how is designed after the work stream that learns it (OD-26).
6. The report theme location: a theme file in `conf/local/` (the mechanism in Phase 2; the corporate
   look it applies comes after internalisation).

## Design constraints
- Plain functions in one module until it genuinely outgrows ~300 lines.
- `hdfs dfs` subprocess calls in one place, failing loud.
- Local-I/O helpers accept `str | Path` and coerce at the boundary (T4).

## Lessons from the crunch
T1–T5 (`docs/context/lessons.md`).

## Interface
Built so far (M1 steps 0 and 7, D-011), all private until M2 lists them in the Public API:
- `core_modelling/_compat.py`: the `np.NaN` alias, applied on package import (T1). Verified
  2026-10-14: without it, `import pyspark.pandas` fails on the pinned numpy 2.3.5 + PySpark 3.4.3.
- `environment._get_spark_session() -> SparkSession`: local defaults (`local[*]`, 2 GB driver,
  8 shuffle partitions, UTC, Arrow on with its silent fallback off, UI off). Settings from
  `conf/local/` come in M2; until then these defaults must not be used inside the bank.
- `environment._load_sources(path) -> dict` and `_read_source(spark, source) -> DataFrame`: a
  logical source → parquet path (absolute or a URI) or table, from a YAML mapping
  (`conf/base/sources.example.yml`; the real one in `conf/local/`). Minimal, for the synthetic
  dataset (M1 step 7); M2 redesigns them with the config spine.
- `tests/conftest.py`: the `spark` fixture, one real session per test run (T15).

## Open questions
- M2: the session function takes arguments (defaults from `conf/local/`), because notebooks
  define their Spark session through it, more elaborately than the crunch's bare
  `SparkSession.builder.getOrCreate()`. Which arguments the bank needs (memory, executors, queue,
  extra conf…) is listed by the builder when M2 designs it. `conf/local/` also sets the bank's
  time zone (local default: UTC).
- The bank-side folder layout for the registered/production tiers per entity × domain, and whether
  permissions differ per entity (OD-06).
