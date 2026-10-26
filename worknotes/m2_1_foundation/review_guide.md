# Stage 1 (M2.1 Foundation): review guide
_For the SDS (every major step) and the LDS (major steps 2 and 3 in full, D-072 (i)) · written as
each major step ends (D-003 (b)) · the plan is `plan.md`, the design `questions.md` and D-129–D-133_

Each major step has one section: what to read in which order, what "right" looks like, and the
reviewers' findings that were taken or justified. Read the docs first, then the tests (they say
what the code promises), then the code.

## Major step 1: config spine and environment adapter
_Status: being built (10-26)._

### Read in this order
1. `docs/components/config.md`: the layout, the load, the identities, the audit log, the level
   mapping. What "right" looks like: every field of `conf/base/cc_acquisition.yml` is explained
   there; nothing in the doc describes code that doesn't exist without saying "planned".
2. `docs/components/environment.md`: the environment file and the public session function.
3. `conf/base/cc_acquisition.yml` and `conf/base/TEMPLATE.yml`: readable as a DS's first
   contact with the framework; every option has a when-to-use.
4. `tests/test_config_schema.py`: one test per rule; a failing config's message says how to fix
   it.
5. `src/core_modelling/config/schema.py`: flat models, one validator per rule, no cleverness.
6. `src/core_modelling/config/identities.py` and `tests/test_identities.py`: what changes which
   hash matches D-088 and D-129.
7. `src/core_modelling/config/audit_log.py` and `tests/test_audit_log.py`: the worked example of
   `config.md` is the test.
8. `src/core_modelling/environment.py` and `tests/test_environment.py`.
9. `src/core_modelling/__main__.py`: `decide` only parses arguments and calls `record_decision`.

### What "right" looks like
- `load_config` on the example gives the resolved level defaults; an unknown key fails naming it.
- The validation month changes the config hash and not the data-definition hash.
- Replaying the worked example's entries gives the states of its table.
- A second `get_spark_session` with other settings fails loud naming the difference.
- Nothing reads `conf/local` except `load_environment`; no physical name in `conf/base`.

### Reviewers' findings
Three reviewers ran on the merged state of 1.2–1.5 (code-reviewer, silent-failure-hunter,
compat-guardian, all strong, high); the fix pass that followed is one agent's, verified on the
main thread.

**Taken (the fix pass):**
- An `hdfs://` data root reached `pathlib` in the audit log and read back an empty log (all three
  reviewers): the log refuses a URI root until the M2.4 transport.
- A logged `set automation_level` relabelled the config without moving the level defaults (code
  review, silent-failure audit): the loader records which paths the level filled, and the move
  re-fills exactly those from the new level.
- `SparkSession.getActiveSession()` is thread-local, so a call from another thread would have
  reused and mutated the session quietly: the adapter now detects the process-wide session.
- The write-clash retry re-numbered an entry whose checks were made against an older log: a clash
  now fails, and the person re-runs the decision.
- A config file carrying `features.excluded` or `housekeeping` loaded quietly, bypassing the
  audit log: `load_config` refuses them; a saved resolved config is read through
  `read_resolved_config`.
- Operands that don't belong to an operation, a `set` that couldn't write `null`, a partial entry
  file left by a failed dump, a naive local timestamp: all fixed.
- Compatibility: `hash_version` on every entry, the entry version checked before validation, a
  golden-hash test that makes a silent change of the hash recipe impossible, a dummy-migration
  test, `schema_version` on the environment file with the migration loop shared, the environment
  values in the resolved config's housekeeping.
- Shapes: `selection.auc_floor` → `univariate_floor` (the statistic comes from the per-task
  spec); typed lists replace three validators; the feature store and a wrong locator are refused
  at load; `extra` can't override the framework's fixed Spark keys; a missing or unknown level
  fails in one place; an empty log folder is logged as a warning.
- Removed: `candidate_names`, which always returned `None` (the resolved candidate list arrives
  with the model input in major step 3; until then `record_decision` says it checked the
  patterns only).

**Justified, not taken:**
- `environment.py` keeps its own strict base instead of importing the config package's
  `StrictModel`: the adapter must not depend on the config package.
- `record_decision` takes paths while `resolve_config` and `show_decisions` take loaded models:
  the first is the notebook and CLI call, as `config.md` designed it; the others serve code that
  already holds the config.
- `rate_band` stays a binary field: regression's contract check has no band; the per-task spec
  decides which checks apply (D-050).
- `target.rule` stays a plain string: the rule names live in the per-task spec, which validates
  them when the target is built (major step 2), not at config load.
- `schema.py` is 424 lines: one model per YAML block, one concept.

**Deferred, with a row:** the audit log's folder is keyed by the short data-definition hash, so a
change of the hash recipe would orphan a log silently; the golden-hash test prevents the silent
part, and a `definition.json` beside the log for relocation is an open question in `config.md`.

### The SDS's review (10-26)
Six remarks, answered in `review_answers.md` with Q388–Q390. Taken: the template shows every
default under a header key, enforced by a test; `training.calibration` defaults. Found while
answering and fixed: a level move overwrote a person's `set` on a level-filled setting.

## Major step 2: Target Factory and the holdings table
_(written when the step ends)_

## Major step 3: dataset, `run`, the notebook
_(written when the step ends)_
