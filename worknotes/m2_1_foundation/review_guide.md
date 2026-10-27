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
_Status: built and reviewed (10-26), for the SDS's review; the LDS reads it in full._

### Read in this order
1. `docs/components/target_factory.md` → Interface: what each function does and refuses. What
   "right" looks like: every refusal is named there, and nothing describes code that doesn't
   exist.
2. `src/core_modelling/tasks.py`: the two rules, the two column checks and the summary, one dict
   by task (D-050). The rule is the label: read `_flag_goes_up` against D-029 (c).
3. `src/core_modelling/target_factory.py`: `build_targets` (the forward window, the one place
   §4.1 lives), then the checks `load_targets` runs before building, then `run_target_factory`.
4. `src/core_modelling/sources.py`: one reader for every source (keys renamed, months at their
   last day, the refusals). Target Factory uses it now, the dataset and Inference later.
5. `tests/test_target_factory.py`: hand-made panels first (the window bounds, gaps, leavers, the
   null semantics with and without `null_as`, the column refusals), then the comparison with the
   oracle on the `unit` preset; then `tests/test_sources.py`.
6. `synthetic/src/synthetic/output.py::_holdings_frame`: the holdings tag the last day, the mart
   the first, so every run converts one of them (0.5.2).

### What "right" looks like
- The rule compares the observation month with the forward months, t+1 … t+w by calendar
  month: 1 when some forward flag exceeds the flag at t, else 0. A holder at t gets 0; who is in
  the population is eligibility's business (`before: model`), never the rule's.
- A missing forward row (a leaver, a gap) gives a null target. A null value follows SQL: it never
  counts as an event; the target is null only when nothing can be compared, and the summary's
  `null_value_share` shows how often a window held one.
- The built targets equal the oracle's on every non-holder row of the `unit` preset, nulls
  included.
- A source tagged on the first day and one tagged on the last key alike; a bad month, key, column
  type or value, a short source and an upstream target with values in its last w months all fail
  loud, naming the source.
- The summary never shows a label rate outside the observation window.

### Reviewers' findings
Four reviewers ran on the built step (code-reviewer, silent-failure-hunter, compat-guardian:
strong, high; ml-correctness-auditor: strong, xhigh), then one fix agent (strong, high) and a
focused re-audit of the fixes (ml-correctness-auditor, high).

**Reverted by the SDS's review (10-27), see below:**
- The ML audit's "null unless the flag at t is 0" precondition: a holder at t is an eligibility
  matter, and the rule compares t with the forward months (a holder gets 0).
- The ML audit's "any null value in the window gives a null target": too strict for a column
  that isn't filled; nulls follow SQL semantics and their share is shown.

**Taken (the fix pass):**
- The summary showed label rates for months after the window, the validation month included:
  label columns are now for the observation window only (ML audit; `CLAUDE.md` §4.4, D-030).
- A string flag (`'Y'`/`'N'`) gave an all-zero target, a flag of 2 counted as 0, a string amount
  summed partly: each task now checks its target column's type and values before building (code
  review, silent-failure audit).
- A TimestampType month written at midnight in another time zone shifted the whole source a
  month: a timestamp month must be at 00:00 in the session time zone (silent-failure audit, ML
  audit).
- A source with a missing month, or ending before `v + w`, gave null targets without a word:
  `load_targets` now checks the months it needs (silent-failure audit).
- An upstream target had no §4.1 protection: one with values in the source's last w months is
  refused, and the doc says §4.1 is owned for built targets (ML audit).
- Replay applied a `set` on any path, so a hand-edited entry could change `decision` or the seed:
  replay now refuses a path that isn't loggable (compat review).
- Smaller: null unit ids are refused and named before duplicates; empty and null-month sources
  get separate messages; `read_keyed_source` takes its arguments in the public order; a missing
  target column names the source; test comparisons survive nulls.

**Justified, not taken:**
- `_regression_summary` stays a named function rather than registering `_summarise` directly:
  the dict reads the same for both tasks.
- `forward_sum` keeps Spark's own sum type; the contract check (step 3) sees the target.

**Deferred, with a row:**
- `training.calibration` defaults to Platt for regression too: decided with Training (M2.3),
  `config.md` → Open questions.
- A use case's laptop audit log is orphaned when the data-definition hash changes: the
  `definition.json` question, before the December pre-release (roadmap backlog).
- For step 3 (plan 3.1): never filter the target source to the window before building; assert
  targets exist at `train_months.last`; log the target source's forward coverage of the spine.
- The oracle's loan-opening kind uses month-on-month steps; the count rule (M4) compares with
  t, so the oracle is aligned when that rule is built (D-029 (c)).

**Re-audit of the fixes** (ml-correctness-auditor, high): all five label findings fixed, each with
a test that fails without its fix; two test gaps closed on the main thread (an upstream tail one
month short, a time zone west of UTC) and the tail test checked by breaking the code.

**The single failed run.** During the build, one combined test run failed two tests (one of them
`test_forward_sum_matches_the_oracle`) while both step 2 agents ran Spark at once on the 8 GB
machine; its error text was lost. Three sequential reruns then passed, and so did every run
since. Load is the likely cause, unconfirmed.

### The SDS's review (10-27)
Three conceptual points, all taken (`review_answers.md`): the rule compares the observation month
with the forward months (`flag_goes_up`; a holder at t gets 0; the count and amount rules are
separate rules for M4); nulls follow SQL semantics with `null_value_share` shown and an optional
`data.target.null_as`; eligibility filters split into `before: eda` (dropped) and `before: model`
(tagged, so EDA keeps the current holders as a reference group). D-029 (c), D-129 and D-131
extended; the dataset step amended.

## Major step 3: dataset, `run`, the notebook
_(written when the step ends)_
