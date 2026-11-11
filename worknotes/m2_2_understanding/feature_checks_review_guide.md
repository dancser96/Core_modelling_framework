# Stage 2 Feature Checks: the review guide for the SDS, round 2 (the code)
_Rewritten 2026-11-10, after the codebase review moved code. Round 1 covered the notebook, the
report, the questions and the vetoes (all in `answers.md`). This round is the code: the
notebook and the report first, which you have reviewed once, then the code in reading order,
each step with the stored table to keep open in `notebooks/00_eda_fc_helper.ipynb`. The
build's decisions to veto by number: `plan.md` §9, V74–V103. About two and a half hours._

## Before you start
1. **Rerun EDA, then Feature Checks, once per use case.** The ledger's sidecar changed (run
   tokens, schema 3), so the stored folders are refused with "rerun EDA". `02_eda` step 1, then
   `03_feature_checks` step 1.
2. **Run `00_eda_fc_helper` top to bottom.** It only reads the stored artifacts. The section
   numbers below are its headings; `NUMERIC` and `CATEGORICAL` in its setup cell are the two
   candidates it follows through every table.

## 1. Notebook 03 and the report (15 minutes)
Everything is as you reviewed it, except:
- **The headline** (EDA's, shown again) reads shares as percentages.
- **The timings** show one decimal; the `inputs` phase takes about 1 second where it took 7
  at 100k (the per-period table is one groupby now).
- **No finding changed.** Every Feature Checks output is identical before and after on the
  test data and, for the per-period table, on your stored 100k cells. On the canonical data
  the last recorded counts are 47 held for the card config and 29 for the term deposit
  (`docs/UPDATES.md`, after synthetic 0.6.0); your rerun should show the same.

## 2. The code, with the helper tables (about two hours)
Paths are under `src/core_modelling/`.

1. **The hold-out core.** What makes a flag act.
   - Read: `config/replay.py` → `open_flags`, `held_features`, `decisions_in_force`, `replay`;
     `ledger.py` → `resolve_features`, `render_decisions`; `feature_checks/decisions.py` →
     `flag_entries`, `proposed_decisions`, `held_summary`.
   - Helper: section 16 (the audit log: the `flag` entries a run wrote, a person's `keep` and
     `exclude` after it); section 9, last table (`features.held`, `excluded`, `kept` in the
     resolved config); section 15 (`proposed_decisions`); section 10 (`held`,
     `entries_written`).
   - Right when: a flag holds its features until a `keep` naming the finding or an `exclude`;
     a revert takes the state after its target entry; a config that was only loaded is refused
     by `resolve_features` and `render_decisions`.
2. **What every step reads.**
   - Read: `feature_checks/inputs.py` whole (129 lines): `check_inputs`, `CheckInputs`,
     `_check_eda_artifacts`; `artifacts.py` → `read_upstream`, `check_upstream`.
   - Helper: section 3 (the five EDA tables Feature Checks reads), section 2 (`eda.json`:
     `settings`, `run_token`, `compared_periods`, `clients`) and section 9 (the ledger).
   - Right when: a stale EDA is refused naming the changed setting, and a ledger from another
     EDA run by its run token.
3. **The finding table.**
   - Read: `feature_checks/findings.py` → `FINDINGS` (20 findings: kind, measure, text),
     `finding_rows`, `finding_frame`, `unavailable_rows`.
   - Helper: section 11 (`findings`: one row of each finding, and the two candidates') and
     section 12 (`unavailable`).
4. **The five checks**, `feature_checks/steps.py` (807 lines, one module), against
   `docs/components/feature_checks.md`'s finding table. What right looks like in all five: no
   check skips for support; every "not available" is decided before computing; significance
   is judged with the SE at the threshold.
   - `check_quality` (`_null_sets`, `_nulls_may_be_zeros`). Helper: section 9, the ledger's
     `missing_share*`, `null_concordance*`, `zero_share*`, `dominant_share*`, `levels`.
   - `check_leakage` (`_too_strong` on the higher of the plain and the best-order window
     concordance, `_minority_effect` on Cohen's h or d, `_nulls_below_range`, the significance
     phrase `_evidence`). Helper: section 5, `concordance_window` beside
     `concordance_best_order_window`.
   - `check_time_alignment` (`_lagged_se`, the flip; `measures.lagged_concordance`). Helper:
     section 4 (the numeric's lagged rows per period), section 6 (`client_constant`) and
     section 9 (`lagged_concordance`, `signal_kept`, `constant_share`).
   - `check_stability` (`_drift` with the PSI tiers, `_heterogeneity`, `_period_ses`;
     `measures.period_psi`). Helper: section 13 (`per_period`: `psi` per compared period) and
     section 8a, table 1 (`concordance_per_period`, which Cochran's Q reads); section 9
     (`psi_window`, `psi_latest`, `concordance_range`, `heterogeneity_p`).
   - `check_redundancy` (`cluster_features`, `explained_by_others` in
     `statistics/association.py`). Helper: section 7 (`correlation`) and section 14
     (`clusters`).
5. **The measures and the shared statistics.**
   - Read: `feature_checks/measures.py` → `per_period_table` (rewritten: one split of the
     cells, the snapshot's PSI groups cut once per feature), `period_psi`, `lagged_concordance`,
     `effective_se`; `statistics/scope.py` → `feature_se`, `unavailable_reason`,
     `cross_fit_unavailable` (the same guards EDA reads, with `lagged`);
     `statistics/distributions.py` → `cohens_h`, `cohens_d`, `variance_from_sums`, `psi`.
   - Helper: section 13 (`per_period`, the numeric across the periods).
6. **The run.**
   - Read: `feature_checks/run.py` → `run_feature_checks`, `_read_eda`, `_write_entries`,
     `_stage_meta`, `_write`.
   - Helper: section 10 (`feature_checks.json`: `settings`, `run_token`, `steps_run`,
     `findings`) and section 1 (the folder).
   - Right when: the settings recorded are the ones the steps ran with; the ledger is saved
     with EDA's run token and this run's, before the folder.
7. **The report.** `feature_checks/report.py` → `build_views`, `report_sections` (the held
   values, the redundancy views, the PSI-only per-period view, the chart from EDA's table).
   No helper table: open `report.html` beside the code.
8. **Read this test: `tests/test_traps.py`.** The mapping from each planted trap to its
   finding, `NOT_CHECKS`, the null controls and `NEVER_ON_LEGITIMATE` as the false-positive
   checks. The guard on legitimate columns is narrower than in round 1: only trap columns and
   rows whose own findings include a guarded flag are exempt.

## What I would look at first
- **`_evidence` and `_period_ses`**: the two places the first ML audit corrected (T37).
  `_period_ses` now calls `feature_se` at the window's value; the audit confirmed it is the
  same number.
- **`_minority_effect` on Cohen's h** against your Q539.
- **`per_period_table`**: the only function rewritten rather than moved.

## Known limits (documented in `feature_checks.md`)
Cochran's Q across periods that share clients is conservative; Cohen's h's SE is about 20% small
at tiny expected counts; `signal_kept`'s SE leaves out the window's own noise; a crash between the
ledger save and the folder write leaves the ledger's informational columns one run ahead, which
the run tokens now refuse (the hold-out reads the log).
