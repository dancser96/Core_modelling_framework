# Environment adapter
**Status:** legacy-only · **Legacy:** `src/_compat.py`, `src/io.py` (`_read`), `src/inference.py` (`_put_file`, `_read_text`, `_fetch_dir`, `_is_hdfs`)
**Related:** [`docs/context/environment.md`](../context/environment.md) · [lifecycle](lifecycle.md) (tier paths) ·
[reporting](reporting.md) (theme) · [test harness](test_harness.md) (synthetic sources) · D-011 · OD-06

## Purpose
The single seam between framework logic and wherever it runs (laptop vs bank). Framework code never
checks where it is running; it calls this module, and `conf/local/` decides.

## Phase 2 requirements
1. Create or get the Spark session from config, including the Arrow setting and app name.
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
   path in `conf/local/`. On a laptop it maps to the synthetic dataset in `data/01_raw/`.
6. The report theme location (a theme file in `conf/local/`, used after internalisation).

## Design constraints
- Plain functions in one module until it genuinely outgrows ~300 lines.
- `hdfs dfs` subprocess calls in one place, failing loud.
- Local-I/O helpers accept `str | Path` and coerce at the boundary (T4).

## Lessons from the crunch
T1–T5 (`docs/context/lessons.md`).

## Interface
*(fill when built)*

## Open questions
- The bank-side folder layout for the registered/production tiers per entity × domain, and whether
  permissions differ per entity (OD-06).
