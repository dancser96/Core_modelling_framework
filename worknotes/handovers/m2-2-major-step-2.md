# Handover: m2-2-major-step-2
_Written: 2026-11-04 · branch: main · last commit: e89eefc (Stage 2.1 initial build; everything
below is uncommitted on top of it)_

## Goal
Build Stage 2's major step 2, EDA: m2.1 the reporting primitives, m2.2 the EDA modules, m2.3 the
EDA stage with its report and `run --stages eda`, m2.4 notebook 02. Then the full suite, the
review guide, and the SDS's review 2. The binding list of files, functions and tests per minor step is
`worknotes/m2_2_understanding/plan.md` §2 → "Major step 2". The SDS's intent for this step:
- lean on tokens ("target almost no Fable"; about 50% of major step 1's tokens and 70% of
  its time was the estimate given to the SDS);
- "properly architecting code rather than needing multiple rewrites";
- notebook guides are the main deliverable ("allocate resources to concisely but thoroughly
  explain steps");
- run lean tests: only the changed workflows, the full suite once at the step's end.

## State
- **Done:** major step 1 (foundations), reviewed by the SDS (review 1). Its fixes are applied and
  verified with targeted tests (`test_statistics.py` 33, `test_counts.py` 19, `test_code_rules.py`).
  The full suite last ran before the review-1 fixes (443 passed, 2026-11-03).
- **Not started:** m2.1–m2.4.
- **Uncommitted (19 files):**
  - working rules: `.claude/commands/brief.md`, `CLAUDE.md`, `worknotes/README.md`;
  - docs: `docs/components/{dataset,eda,feature_checks,reporting}.md`,
    `docs/context/lessons.md`, `docs/decisions.md`, `docs/roadmap.md`;
  - build config: `pyproject.toml`;
  - code: `src/core_modelling/dataset/counts.py`, `src/core_modelling/statistics/{association,concordance}.py`,
    `src/core_modelling/tasks.py`;
  - tests: `tests/test_counts.py`, `tests/test_statistics.py`;
  - worknotes: `worknotes/log.md`, `worknotes/m2_2_understanding/plan.md`.

  The SDS may commit them before resuming: check `git status`.

## Decisions in that chat (all recorded; where)
- **Review-1 fixes** (D-135, T33, eda.md "The statistics", plan V16):
  - The level encoding is cross-fitted by client fold:
    - The counts table gains `fold`: `pmod(xxhash64(unit_id), 5)` on a categorical's
      window cells only, null elsewhere.
    - `concordance.cross_fitted_concordance(cells, periods, k_rows, read=None, lagged=False) ->
      float` replaces `cross_fitted_table`. Somers' D counts pairs inside each fold only.
  - Every window SE uses effective clients:
    - `counts.window_clients(rows, window_periods) -> dict[str, float]` gives Kish's
      `(Σm)²/Σm²` per class and in all.
    - `TASK_SPECS[task]["client_support"](events, non_events, clients)` turns them into the
      SE's support.
  - A categorical's SE is multiplied by `concordance.CROSS_FIT_SE_INFLATION = 1.5` (the SDS's
    option a). A Phase 3 wishlist item checks it and possibly replaces it with a permutation
    null.
  - The pairwise cap: `PAIRWISE_ROWS = 50_000`, `MIN_SHARED_ROWS = 500`.
  - `client_constant`: notebook 03 shows the flagged features in one table so that one `keep`
    settles them; the feature-store static metadata is on the backlog.
- **Working rules** (D-072 (h)(l), `CLAUDE.md` §1 and §8):
  - Fable at most 25–30% of a stage, almost none for the rest of Stage 2.
  - "Small prompt, small diff": a small prompt touches the owner docs only, answers go in chat
    first, the secondary docs are synced at a major step's end.
  - `worknotes/log.md` keeps 7 working days and is appended only when a turn settles something.
- **The routing for steps 2–3** is reset in `plan.md` §3; the table there overrides the model
  named in §2's bullets:
  - Opus main thread.
  - m2.1 Sonnet·high; m2.2 Opus·high; m2.3 Opus·xhigh; m2.4 Opus·high.
  - One combined review per minor step (code-reviewer briefed with the silent-failure and §2
    lenses).
  - The ML audit on m2.2+m2.3 together (Opus·high).
  - One fix round for the whole major step.
  - Fable only for the whole-stage audit at the end of major step 3.
- **Review-guide questions 1, 3, 4, 5 are at their defaults:**
  - jinja2 3.1.6 is pinned in m2.1;
  - the ledger's `levels` comes from EDA;
  - `resolved_config.yml` stays without its header;
  - the run marker's `periods` is relaxed in M2.3. Q2 was answered by the 50,000 cap.

## Open questions
- None open. A worked plan exists; the SDS has not yet said "go" for major step 2 in a new chat.
  Confirm the routing once (plan §3) and start.

## Next steps
1. **Start m2.1 ∥ m2.2 in parallel** (disjoint files). Write their briefs from plan §2, the
   common brief below, and the m2.2/m2.3 notes below:
   - m2.1: Sonnet·high, `general-purpose`. It pins `jinja2==3.1.6` in `requirements.txt`.
   - m2.2: Opus·high.
   - `detect_kinds` already exists in `dataset/frames.py`: m2.2 must not rebuild it (plan §2
     still lists it).
2. **m2.3 after both** (Opus·xhigh): `eda/run.py` `run_eda(cfg, entity, env, spark) ->
   StageResult`, `STAGES["eda"]` in the existing `src/core_modelling/run.py`, `tests/test_eda.py`.
   Then **m2.4** (notebook 02, Opus·high; read every guide line yourself). Then one combined
   review per piece, the ML audit, one fix round.
3. **End of the step:**
   - the full suite in the background on the main thread;
   - `review_guide.md`: replace the review-1 section, keeping only the current review
     (worknotes are current-only);
   - the secondary doc sync (UPDATES, architecture Public API and inventory, README map);
   - report the token split per model to the SDS (see Gotchas).

## Notes for the m2.2 / m2.3 briefs (were in the scratchpad; not in any doc)
- **The EDA call sequence for `run_eda`:**
  1. `frames = build_frames(cfg, entity, env, spark, "eda")`; `kinds = frames.meta["kinds"]`.
  2. `frames.rows.persist()` before the passes, unpersist at the end.
  3. `periods = counts.compared_periods(cfg, available)` (dates; log entries carry labels).
  4. `estimate_cells(rows, kinds, cfg.eda.bins, periods["window"])` before the passes.
  5. `edges = bin_edges(frames.snapshot, kinds, cfg.eda.bins)`.
  6. `levels, over_ceiling = window_levels(rows, categoricals, periods["window"])`; both go to
     meta and `eda.json`.
  7. `target_edges = TASK_SPECS[task]["target_bins"](known snapshot targets, exact=cfg.eda.bins
     is None)`.
  8. `cells = concat(count_cells(rows, edges, levels, over_ceiling, target_edges,
     periods["window"], period_spec(cfg)), count_lagged_cells(...same...))`.
  9. `client_constant_shares(rows, [*edges, *levels], periods["window"])`;
     `population = frames.meta["population"]`.
  10. `clients = window_clients(rows, periods["window"])`, once; record it in `eda.json`.
  11. Write order: `save_ledger(ledger, folder, meta)` first, then `write_stage` (the stage json
      is the commit marker); the report is written into `result.paths["folder"]` after.
- **The statistics callers' guards:**
  - The no-events guard: read `shares()["events"]`/`["non_events"]` first and show "not
    available: no events among the non-null rows" (decided up front, never by try/except). Gate
    on the UNSCALED events before `client_support`.
  - Never call `best_order_concordance` on a categorical.
  - **A window SE:** `spec["concordance_se"](value, *spec["client_support"](events, non_events,
    clients))`, with `spec = TASK_SPECS[task]`. Per-period and snapshot SEs use their own rows
    (one per client).
  - A categorical's SE (window, period, snapshot) is multiplied by `CROSS_FIT_SE_INFLATION`.
  - **A categorical's value:** `cross_fitted_concordance(cells, window_labels, k_rows)`. The
    snapshot is `read=[snapshot label]`, a period `read=[label]`, the lagged value `lagged=True`.
    It is already rescaled with sign +1, and there is no "optimistic" marker.
  - Pass `se` to `is_non_monotone`/`ranking_value`.
  - `rare_effect` only when `lift_available(base)` and the rest's mean > 0.
  - `explained_by_others` needs the table's `method` column; `shares()["bins"]` (not `levels`).
  - `new_level_share` gets the window's bins (levels + `OTHER` + `NULL_BIN`), so only `__new__`
    counts. Skip it for `over_ceiling` features ("not available: more than 10,000 window
    levels").
  - Record the Spearman's null-mask count and its seconds in EDA's timings.
  - `base` for `shrinkage_rows` is the window's base rate.
  - The counts table's `fold`: always `pool_periods` before `two_way_table` or `merge_bins`.

## Common brief for builders (recreate as a file; the old one lived in the scratchpad)
- **The environment and tests:**
  - Python 3.11 venv: `.venv/bin/{python,pytest,ruff}`; the pins are in
    `docs/context/environment.md`.
  - No new dependency (m2.1's jinja2 pin is approved).
  - Run only your own tests plus `tests/test_code_rules.py` and ruff on your files. Never the
    full suite, never commit.
  - The 8 GB Mac: the `unit` preset fixtures in `tests/conftest.py` (`spark`, `unit`,
    `unit_env`, `cc_config`, `variant`, `write_sources`). Never a second Spark session, never
    the canonical data in a test.
- **Read before coding:**
  - your plan §2 bullet (binding), the spec docs it names (`docs/components/eda.md`,
    `reporting.md`);
  - D-134–D-137, T25–T33, the glossary for names;
  - the whole module you extend.
- **Code rules that bite:**
  - every function (tests and private ones too) has type hints and a one-line docstring;
  - functions of at most ~50 lines;
  - fail loud, naming the field or feature;
  - no pandas UDF, no `pathlib` on an `hdfs://` string, no `_trap_` names in `src/`.
- **Ownership:** edit only the files your brief lists. Changes needed elsewhere go to
  `integration_requests` in the report.
- **The report is structured:** `files_changed`/`files_created`, `functions` (one-line
  signatures), `tests` (the command, the counts, the last 30 lines), `ruff`, `deviations`,
  `integration_requests`, `doc_notes`, `open_questions`, `facts_assumed`.
- **Reviewer brief:**
  - review only the listed files (`git diff -- <files>`), edit nothing, run only the step's
    tests;
  - each finding: `file`, `line`, `severity` (high/medium/low), `summary`, `suggested_fix`;
  - then a verdict (`accept`/`fix_first`) and the plan's gaps.

## Gotchas
- **Shell edits:** use a quoted heredoc (`<<'EOF'`). An unquoted one ran a backticked `fold`
  through the shell and hung the command.
- **Line length:** ruff's limit is 100. Long docstring edits need re-wrapping by hand: ruff
  format does not wrap docstrings.
- **The panel nature of the data** drove both review-1 fixes. Any new window statistic with an
  SE must use effective clients, and any fitted order must be cross-fitted by client, never by
  period. The synthetic panel's labels persist over the 3-month target window.
- **Plan §2's model and effort per step are stale;** §3's table rules.
- **The Fable rate limit** stopped two builders on 2026-11-03. No Fable builders now.
- **Token accounting:** the transcripts under `~/.claude/projects/<repo>/<session>/` carry
  `usage` per message. Sum `output_tokens` by `message.model` for main, `subagents/` and
  `workflows/`, de-duplicating by (message id, requestId).
- **The SDS reads code, not tests:** mark at most two "read this test" per major step.
- **Small diffs:** keep a small prompt to a small diff; above about 8 files, say which and why.

## Read first
1. `docs/UPDATES.md` (status), then `worknotes/m2_2_understanding/plan.md` §2 "Major step 2",
   §3 (routing), §9 (V1–V17).
2. `docs/components/eda.md` (the whole spec: Level 2 flow, "The statistics", artifacts) and
   `docs/components/reporting.md` (chart rules, primitives).
3. `src/core_modelling/statistics/{cells,concordance,distributions,association}.py`,
   `src/core_modelling/dataset/{counts,frames}.py`, `src/core_modelling/{artifacts,ledger,tasks,run}.py`.
4. `notebooks/README.md` and `notebooks/01_target_factory.ipynb` (the guide-cell style for m2.4).
5. `worknotes/m2_2_understanding/review_guide.md` (review 1's format, to extend for review 2).
