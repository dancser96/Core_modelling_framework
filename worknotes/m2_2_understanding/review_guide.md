# Stage 2 (M2.2 Understanding): the review guide for the SDS
_Written for the SDS's review at the end of each major step (D-003, D-072 (i)); one section per
major step. What to read, in which order, and what "right" looks like. Tests appear only where
reading one matters, marked **read this test** (at most two per major step). Decisions the build
made without the SDS are numbered in `plan.md` §9 (V1–V17): silence confirms them._

## Major step 1: foundations — ready for review (2026-11-03)
**Built:** the Stage 2 config fields and the audit log's new operations; the snapshot and `rows`
frames with the kinds; the two Spark counts passes, the client-constant shares and the population
counts; the statistics engine on cells (distributions, concordance, intervals, association) and
the per-task regression entries; the artifacts (`StageResult`, the stage folder) and the feature
ledger. Every piece was built by one agent, reviewed by two or three (code, silent failures,
compatibility, ML correctness), and fixed in a second round; the full suite ran at the end:
443 passed, `ruff check` and `ruff format --check` clean (2026-11-03).

**Reading order (about two hours; the ML logic first, the plumbing last):**
1. `src/core_modelling/statistics/concordance.py`: `concordance_from_table` (Somers' D rescaled;
   for a 0/1 target exactly the AUC of the binned feature), `concordance_se` (Hanley–McNeil,
   floored), `cross_fitted_table` (V16: a period's levels ordered by the other periods' encoding),
   `best_order_concordance` and `is_non_monotone` (V2: the margin `max(0.03, 4 · SE)`),
   `cochran_q`. Right looks like: every number has an oracle in `tests/test_statistics.py`
   (`roc_auc_score`, `kendalltau`, `binomtest`, `chi2`), and the two null-control tests (a 50-level
   random code reads about 0.50 cross-fitted; a null numeric at 500 events is almost never marked
   `non_monotone`).
2. `src/core_modelling/statistics/distributions.py`: `quantile_edges` (T25: mass points as
   singleton bins, the rest cut into equal-share bins), `merge_bins`, `psi`. Right looks like: a
   90%-zero column gets the zero bin plus about 50 bins where plain quantiles gave 4.
3. `src/core_modelling/statistics/cells.py` and `association.py`: how a statistic is a sum over
   cells (`pool_periods`, `two_way_table`, `shares`); the exact pairwise-complete Spearman grouped
   by null mask (T28); `cluster_features` (average linkage, Q472); `explained_by_others` (V17).
4. `src/core_modelling/dataset/counts.py`: `compared_periods` (never the validation period, V9),
   `bin_edges` (from the snapshot's eligible rows), `window_levels` (the 50 kept levels, `__other__`,
   `__new__`, the 10,000 ceiling), `count_cells` (one `Bucketizer`, the explode, one `groupBy`;
   null and NaN as one null bin, `-0.0` normalised, T26), `count_lagged_cells` (the lag by period
   index, T19), `client_constant_shares` (chunked, T27), `population_counts` (D-088).
5. `src/core_modelling/dataset/frames.py`: `build_frames(..., "eda")` (the snapshot collected, the
   `rows` plan with the label nulled outside the window), `detect_kinds` (from the Spark schema).
6. `src/core_modelling/config/replay.py`: `open_flags`, `held_features`, `features.held` in the
   resolved config (V1). `src/core_modelling/config/audit_log.py`: `_keep_findings` (a keep
   settles only pairs open on every named feature), `_check_not_compared` (a `set` or a `revert`
   never brings back a compared validation period, D-088), `record_stage_entry`.
7. `src/core_modelling/ledger.py`: `resolve_features` (the hold-out, §4.6: candidates − lineage −
   unsupported − excluded − held) and `render_decisions`. `src/core_modelling/artifacts.py`:
   `write_stage` (the temporary folder, the commit-marker order), `check_upstream`.
8. `src/core_modelling/config/schema.py`: `Eda`, `Features.kinds`, the typed `FeatureChecks` with
   its two validators, `snapshot_period`. `conf/base/TEMPLATE.yml`: the Stage 2 fields' explanations.

**Read this test (two):**
- `tests/test_audit_log.py::test_keep_settles_only_pairs_open_on_every_feature` and
  `::test_revert_is_checked_like_a_set`: the two holes the reviewers found and closed, as scenarios.
- `tests/test_counts.py`: the pass-1 oracle test (the cells equal a pandas `groupby` on the
  collected rows) and the T25 zero-inflated test. The rest of the tests are for the reviewers.

**Try it (ten minutes):** `.venv/bin/pytest tests/test_statistics.py -q` (no Spark, 4 s) and
`tests/test_counts.py -q` (one Spark session, about a minute); open `conf/base/TEMPLATE.yml` at the
`eda` and `feature_checks` sections.

**Decisions made without you, to veto by number (`plan.md` §9):** V16 (the cross-fitted level
encoding replaces A30's "fitted once on the pooled window") and V17 (explained-by-others, the level
ceiling, the eligible-row edges) are the two from the build; V2's margin changed from 0.03 to
`max(0.03, 4 · SE)`. The measurements behind them are in `worknotes/log.md` (2026-11-03).

**Questions for you (defaults in brackets):**
1. jinja2 3.1.6 must be pinned in `requirements.txt` before the reporting primitives use pandas'
   Styler (it is in the devcontainer, not in this venv) [pin it in m2.1; the alternative is
   hand-written HTML tables with CSS classes, a third of the size].
2. The exact pairwise-complete Spearman costs 11 s at 139 × 200,000 rows with the realistic
   null-mask structure and 253 s with 76 distinct masks [keep exact; record the mask count and the
   seconds in EDA's timings; measure in the bank].
3. The ledger's `levels` column is written with EDA's statistics (the distinct count on the
   snapshot before the cap), not at creation [keep].
4. A stage folder's `resolved_config.yml` is a plain dump without the audit-log header (which entry
   set each value) [keep: `housekeeping` records `replayed_to` and the hashes].
5. Training's run marker will need `periods` relaxed (`record_stage_entry` requires it) [relax in
   M2.3 when Training writes it].

**Open risks:** the bank-side timing of the passes (measured on the Mac only: 15–18 s for pass 1,
19 s for pass 2 on the canonical window); a column with more than 10,000 window levels loses
`new_levels` (shown as not available); the cross-fitted table's pairs across periods lean slightly
discordant, so Hanley–McNeil understates a categorical's noise by about 1.7× at small sizes
(recorded; the direction rule and Cochran's Q read it conservatively).

**Deviations from the plan, all declared in the builders' reports and in `plan.md`:** `feature_dir`
instead of `stage_dir`; m1.4 built in two halves; `window_levels` returns the levels and the capped
features; the two passes take the period spec; `population_counts` runs inside `build_frames` and
lands in `Frames.meta["population"]`; `save_ledger(ledger, folder, meta)`.
