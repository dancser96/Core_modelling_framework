---
name: bank-parity-check
description: Check that code will run inside the bank's environment (Python 3.11, PySpark 3.4.3, Java 11, numpy 2.3.5, pinned packages, raw HDFS, one-way code flow). Use this whenever adding or changing imports or dependencies, writing IO, path, Spark-session or file-transport code, using a library API you are not certain exists in the pinned version, or preparing a release zip.
---

# Bank parity check

The code is developed outside and copied into the bank as a zip. Anything that only works on the
laptop becomes a bug found weeks later that nobody can debug from outside. Pinned versions and
known traps: `docs/context/environment.md` and `docs/context/lessons.md`.

## Checklist

- [ ] **Dependencies.** Every import is in `requirements.txt` (bank-parity pins) or the standard
      library. New package → stop and ask the user whether it exists internally.
- [ ] **API exists in the pinned version.** Verify signatures against the pinned versions
      (e.g. `pip show`, `help()` in the venv), not memory.
- [ ] **numpy 2 / PySpark 3.4.** Entry points import the compat shim before pyspark/flaml (T1).
      Avoid pandas-on-Spark (`pyspark.pandas`) entirely.
- [ ] **Paths.** No cwd-relative paths; roots come from config via the environment adapter (T5).
      `hdfs://` URIs stay strings, never `pathlib` (T2). HDFS reads outside Spark go through the
      adapter's transport (T3).
- [ ] **Local I/O** helpers coerce `Path(x)` at the boundary (T4).
- [ ] **Spark → pandas.** Prune columns/rows (and sample) in Spark before `toPandas()`.
- [ ] **Write modes.** No overwrite inside loops; batch-scoped outputs written once (T6, T7).
- [ ] **Identifiers.** No bank names, internal paths, table names or people's names. Physical names
      belong only in `conf/local/` (gitignored).
- [ ] **Java 11 / Python 3.11 features only.** No syntax or stdlib features beyond Python 3.11.
- [ ] **Tests run on local Spark** with the pinned versions (not stubs).

## Output

List each item as ok / issue (file:line + fix). Anything uncertain gets flagged as "verify inside
the bank" with a one-line check the user can run internally.
