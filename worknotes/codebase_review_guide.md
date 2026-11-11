# Codebase review: the review guide for the SDS

**Status:** the review of 2026-11-10 is executed in full: all ten clusters, every item, as the SDS
chose. Nothing is committed (Q570): the whole change is in the working tree for one review.
`git diff HEAD --stat` lists it; `git diff HEAD -- <path>` shows one file.

**Verdict.** Every number EDA and Feature Checks produce is unchanged, except where a change was
approved; the suite is green and faster; two ML audits found no defect. What to read first, by
what a mistake would cost: A (Training's frames), C (the statistics rule), B (the ledger's
pairing), D (the replay).

## Before you review
1. **Rerun EDA, then Feature Checks, once per use case.** The ledger's sidecar is at schema 3
   and the stage jsons at schema 2, so the stored folders under `data/` are refused with "rerun".
   `02_eda` step 1, then `03_feature_checks` step 1.
2. **The two stage guides are rewritten for this code**:
   `m2_2_understanding/review_guide.md` (EDA) and `feature_checks_review_guide.md`. Each pairs
   every code step with a section of `notebooks/00_eda_fc_helper.ipynb`. This guide is the
   per-cluster view of the same diff; read whichever order suits you.

## How it was checked
- **A before-and-after manifest of every artifact** (every table, json, ledger, audit-log entry
  and report page of Target Factory, EDA and Feature Checks, on the saved-model-input path and
  the in-memory path, binary and regression): identical after every wave, except the changes
  named per cluster below.
- **Old against new on real sizes:** every statistic of both stages recomputed from the stored
  100k cells of both use cases; Feature Checks' per-period table compared exactly.
- **Reviews:** one code review per cluster (Opus), fixes applied in one round.
- **Two ML audits** (Fable, at the highest effort): no defect in what this work changed. Their
  should-fixes are applied (listed per cluster); the one must-fix is not in this diff: it is a
  gap in what Training's gate will have to check, and it is under "For M2.3" below.
- **Compatibility check:** old artifacts are refused loudly by the new code and new ones by the
  old code; both example configs and both environment files load.
- **Tests:** the full suite, 646 passed in 13 min 10 s (621 in 17 min 33 s before). The fixes
  from the last review, the compatibility check and the second audit came after it; the tests
  of the modules they touch were rerun (see "Final checks").

## The clusters
Paths are under `src/core_modelling/` unless they start with `tests/`, `synthetic/` or `docs/`.

### A. Training's frames
- **Read:** `dataset/frames.py` → `STAGE_PARTS`, `build_frames`, `_check_request`,
  `_modelling_frames`, `_modelling_rows`.
- **Right when:** Training's rows stop at the window and the validation frame is not collected
  for it; the select of the keys, the features, `target` and `split` sits after the eligibility
  and null-target filters and before the sampling; Evaluation gets all three frames.
- **Beyond the plan:** Training's frames need the resolved config and refuse a held or excluded
  feature (ML audit 1); a repeated feature name is refused; Training's null-target log stops at
  the window.
- **Read this test:** `tests/test_frames.py` →
  `test_downsampling_leaves_test_and_validation_whole` (a mutation run confirmed it fails when
  the sampling moves before the split).

### B. Stage plumbing and the artifact seam
- **Read:** `artifacts.py` → `SETTINGS_PATHS_BY_STAGE`, `stage_identity`, `check_upstream`,
  `read_upstream`, `new_run_token`, `STAGE_SCHEMA_VERSION`; `config/replay.py` →
  `check_resolved`, `dump_resolved`; `ledger.py` → `_sidecar`, `save_ledger`, `read_ledger`,
  `read_candidates`; then how the two stages use them: `eda/run.py` → `_stage_meta`, `_write`;
  `feature_checks/run.py` → `_read_eda`, `_stage_meta`, `_write`.
- **Right when:** no stage imports another stage's run module; each run writes one token into
  its json and into the ledger's sidecar, and a reader refuses a ledger from another run;
  changing `decision` or `evaluation.slices` makes EDA stale; a config that was only loaded is
  refused by `resolve_features`, `render_decisions`, `check_upstream` and `stage_identity`.
- **Beyond the plan (second audit):** `save_ledger` renames the sidecar before the table, so a
  crash between the two is refused by the tokens.
- **Changed against the plan:** `stage_identity` records the settings of the config the run
  read. The plan kept Feature Checks recording the config after its own entries; the review
  showed that could let Training accept stale artifacts in a narrow race. The stage json's
  schema version is 2 (the compatibility check).
- **Expected artifact changes:** `_ledger.json` (`runs`; `stage`, `stages` and
  `settings_digest` gone); the stage jsons (`run_token`, a longer `settings`, another digest,
  `schema_version` 2).

### C. One statistics engine
- **Read:** `statistics/scope.py` whole; `statistics/concordance.py` → `fold_encodings`,
  `cross_fitted_concordance`; `statistics/cells.py` → `group_of_bins`, `population_cells`;
  `statistics/capture.py`; `statistics/distributions.py` → `cohens_h`, `cohens_d`,
  `variance_from_sums`; `eda/deep_dives.py` → `group_table`; then the callers that got shorter:
  `eda/ranking.py`, `eda/slices.py`, `feature_checks/measures.py`.
- **Right when:** `feature_se` is the only place the SE rule is written (four copies before);
  the guards give Feature Checks' lagged reasons with `lagged=True`, character for character;
  `tasks.py` holds no formula of its own.
- **The one approved change (Q565):** the slices order a categorical by the encoding the
  concordance reads. It moves nothing in your current runs (every key feature is numeric); with
  every categorical forced to a key feature it reorders 2 of 20. Simulated on a null code, it
  leaks nothing.
- **Not done:** fitting a categorical's fold encodings once per feature and handing them to
  every per-period read; it needed a parameter with no caller.

### D. Audit-log replay
- **Read:** `config/replay.py` → `replay`, `effective_entries`, `decisions_in_force`,
  `open_flags`; `config/audit_log.py` → `load_entries`, `_is_period_label`; `ledger.py` →
  `render_decisions`; the two validators: `config/schema.py` → `Decision._check_n_matches_type`,
  `environment.py` → `_check_theme_null`.
- **Right when:** `states[n]` is the state after entry n and a revert takes it; the three
  feature lists are written last, from the effective entries alone.
- **Beyond the plan (from the review and the second audit):** a config with a replayed list
  filled is refused by the replay, and `resolve_config` refuses a config that is already
  resolved (replaying onto its replayed values gave another input than the file's after a
  revert); `check_resolved` recomputes the resolved-input hash, so a saved resolved config
  edited by hand is refused; `render_decisions` refuses entries that do not end at the config's
  `replayed_to`.
- **Not done:** `_origins` keeps its own walk (it carries the resolved file's header order);
  `levels.py` and `replay.set_at` still walk a dotted path each (sharing needs an import cycle).

### E. Reporting blocks
- **Read:** `reporting/blocks.py` → `headline`, `choices_block`, `identity_values`, `appendix`,
  `not_available`; `reporting/formats.py` → `format_of`; `reporting/html.py` → `table_html`;
  `eda/population.py` → `headline_formats`.
- **Right when:** a headline number without a format is refused; rendering leaves the Styler the
  notebook displays untouched.
- **Expected artifact changes:** the four `report.html` pages (the headline's numbers; the
  timings caption).

### F. Feature Checks module
- **Read:** `feature_checks/measures.py` → `per_period_table`, `_psi_reference`, `_psi_against`,
  `_period_rows` (the only function rewritten); `feature_checks/inputs.py` and the row builders
  at the end of `findings.py` are moved code.
- **Right when:** the table equals the old one exactly; `steps.py` holds the five checks.
- **Deviations:** the row builders are public names now (`finding_rows`, `finding_frame`,
  `unavailable_rows`), since no module imports a private name; `steps.py` is 807 lines, not
  about 750 (`StepResult` stays there).

### G. Spark time and the dataset build
- **Read:** `eda/run.py` → `_count_tables` (G1); `dataset/counts.py` → `estimate_cells`;
  `dataset/panel.py` → `join_definition`, `read_side_columns`, `_check_lineage_names` (G3 and
  Q574); `dataset/model_input.py` → `_check_join_definition`, `saved_candidates`;
  `dataset/eligibility.py` → `apply_eligibility`, `resolve_candidates`.
- **Right when:** the cell estimate runs with `eda.bins: null` only; one definition feeds the
  model input's sidecar and both checks.
- **G2, measured and dropped:** persisting the joined panel on the in-memory path cut 19 of 75
  Spark jobs and made the frames build 12–35% slower on `dev`; the code keeps the current path.
- **G4:** the example environment file and `environment.md` say what a cluster sets for
  `shuffle_partitions` (reasoned, not measured at the bank).
- **Beyond the plan:** lineage and eligibility step names are matched ignoring case, as Spark
  matches names; a lineage entry that names no source column is refused (Q574).

### H. Test suite
- **Read:** `tests/conftest.py` (the session fixtures `eda_frames`, `eda_card`,
  `eda_regression`, the shared variants and `build_entry`); `tests/test_run.py` →
  `test_run_two_configs_runs_every_stage`.
- **What stopped being tested:** EDA and Feature Checks on the full card config through the CLI
  (the trap test still runs them through `run`, at `dev` size); that `run_eda` itself calls
  `_check_frame_names` (the check is tested directly).
- **Collected tests:** 657 (646 in the default suite); three pipeline tests merged into one.

### I. Synthetic package
- **Read:** `synthetic/src/synthetic/mechanisms/traps.py` → `trap_window`, `lookahead_months`,
  `finalize_lookahead`; `generate.py` → `run_months`; `mechanisms/cards.py` → `step_card_month`
  (shared with `truth/regression.py`); `checks/table.py` → `trap_parameters`;
  `tests/test_synthetic_families.py`; `tests/test_traps.py` → `_may_leak_by_design`.
- **Right when:** the generated data is byte-identical (see "Final checks").
- **Changed against the plan:** the refusal for a too-short look-ahead buffer is not built: once
  the depth is derived from every trap row's window it could never fire. A new look-ahead kind
  must name its window `w` (the docstring says so).
- **Open, found in passing:** the generator's own checks on `dev` fail four statistical rows
  (holdings 437 of 440, amount levels 44 of 45), the same before and after; not looked into.

### J. Docs, packaging, notebooks
- `pyproject.toml` declares scipy, plotly and jinja2. `notebooks/02_eda.ipynb` has no outputs,
  and `tests/test_code_rules.py` keeps every notebook but `00_synthetic_data` so (the hostname
  and home path stay in git history, Q571).
- Stale lines fixed across `CLAUDE.md`, `docs/` and the READMEs; the six references to the
  deleted `docs/reference/` are gone; D-117 agrees with D-133.

## Final checks
- **Artifacts against the committed state:** 10 of 97 differ, all intended: the two ledger
  sidecars, the four stage jsons and the four report pages. All 58 tables, the saved model
  input, every audit-log entry and both resolved configs are identical.
- **Tests on the final tree:** the full suite once (646 passed, 13 min 10 s); then, after the
  last review and audit fixes, every framework test file again (the Spark files in three
  batches, the trap test among them; all passing) and the fast tests (325 passed). The
  synthetic package's own Spark tests ran in the full suite; its code has not changed since.
- **Synthetic data:** `data/01_raw/synthetic_dev` and `synthetic_canonical` are byte-identical
  to fresh generations by the final code (74 files each); at canonical size 1,374 of 1,374
  check rows pass in 10 families (one row more: the checks' target table against the oracle's).
  The two stored check tables that changed are refreshed; `00_synthetic_data` shows 1,373 in
  its committed outputs until it is rerun.
- **Lint:** `ruff check` and `ruff format --check` clean on `src`, `tests` and `synthetic`.

## For M2.3 (found by the second ML audit; not in this diff)
- **Training's gate must check that the Feature Checks run is still in force.** Today a held
  feature would reach `resolve_features` with every check green whenever the resolved config
  does not carry the run's flags: after a `revert` to before them, with `resolve_config(upto=…)`,
  or with a resolved config saved before the run. Measured: after `revert_to=0`, 170 features
  pass, all 48 held ones among them. No code trains yet. The proposal is in
  `docs/components/training.md` → Open questions (Q576).
- **The environment's physical sources are in no hash and no digest**, so pointing the sources
  at other data under the same root (dev, then canonical) leaves the stored EDA and Feature
  Checks passing as current (Q577).
- **Evaluation's frames** accept a config that was only loaded and any candidate, held ones
  included: when Evaluation is built, check its feature list against the model bundle's.
- **Lineage across use cases:** another use case's extra `data.target.lineage` entries stay
  candidates of this one on a shared model input (only its target column and upstream label are
  dropped), as before this work.

## Questions
Answered, and built:
- **Q563–Q569, Q571, Q572:** the defaults. Training gets no validation frame; `statistics/scope.py`
  imports `TASK_SPECS`; one prior for the level encoding; the ledger's run token now;
  `shuffle_partitions` keeps its default with guidance; `inputs.py` and the row builders moved;
  the trap test's guard narrowed (nothing fired); no history rewrite; `docs/reference/` stays
  deleted.
- **Q570:** one review by the SDS at the end; no commits by Claude.
- **Q573:** cluster H kept whole.
- **Q574:** a `data.target.lineage` entry that names no source column is refused.

Open (each with its default):
- **Q575.** The new ledger and stage formats and the committed ones both stamp
  `framework_version` 0.3.0. Move `__version__`? Default: keep 0.3.0 (nothing has left the
  laptop; D-137 puts 0.3.0 at Stage 2's close). Alternative: 0.3.1 now.
- **Q576.** Build the check that the Feature Checks run is still in force with Training's gate,
  as M2.3's first step? Default: yes.
- **Q577.** Add a digest of the entity's physical sources to each stage's identity, checked
  with the settings? Default: yes, with Q576. Alternative: accept it in writing (inside the
  bank one environment file serves one entity).
- **Q578.** Worknotes that have done their job (nothing is deleted unasked): (a)
  `synthetic_trap_coverage_plan.md`, built and committed as 0.6.0; (b) the two empty stubs
  `m2_2_understanding/questions.md` and `feature_checks_questions.md`; (c)
  `m2_2_understanding/eda_gaps_spec.md`, built, after its §0.2 (Q525–Q530 verbatim) moves into
  `answers.md` and D-138 points there; (d) `m2_2_understanding/plan.md` cut to §9, the V
  register the code, the tests and the decision log cite. Default: all four.

## Considered and not done
- Splitting `feature_checks/steps.py` per step or `eda/report.py`; role subfolders for `eda/`.
- `tasks.py` as a package: its split belongs to M2.3's design, when Training's entries are the
  second real use.
- A "report as a list of views" abstraction; generic trap builders in `synthetic/`; sharing
  statistics between the synthetic checks and the framework.
- A partial plotly.js bundle; a numpy `two_way_table`; a lighter per-period concordance path.
- Direct tests for `group_of_bins`, `fold_encodings` and `population_cells`, and a test pinning
  the lagged guards' texts (the C review's optional items): they are covered through their
  callers and by the audits' comparisons, not by tests of their own.
