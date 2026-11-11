# Stage 2 EDA: the review guide for the SDS
_Rewritten 2026-11-10, after the codebase review moved code (D-137: every statistic now lives
in `statistics/`). The notebook and the report first, which you have reviewed once, then the
code in the order `run_eda` runs, each step with the stored table to keep open in
`notebooks/00_eda_fc_helper.ipynb`. About two hours. The LDS's guide of 11-06 is this file at
commit `500fd92`, the state the LDS runs (`worknotes/lds_run_guide.md`)._

## Before you start
1. **Rerun EDA once per use case.** The ledger's sidecar changed (run tokens, schema 3) and
   EDA's settings digest grew, so the stored `eda/` folders are refused with "rerun EDA".
   `02_eda` step 1 does it; then `03_feature_checks` step 1.
2. **Run `00_eda_fc_helper` top to bottom.** It only reads the stored artifacts. The section
   numbers below are its headings; `NUMERIC` and `CATEGORICAL` in its setup cell are the two
   candidates it follows through every table.

## 1. Notebook 02 and the report (20 minutes)
Everything is as you reviewed it, except:
- **The headline** reads like the tables: shares as percentages and the estimate in the task's
  format (64.5% and 2.66% where it read 0.6453 and 0.0266).
- **The appendix's timings caption** says how many cells were counted. The cell estimate, one
  more scan of the window, now runs with `eda.bins: null` only, so step 1 is faster.
- **No number changed.** Every table of both stages is identical before and after on the test
  data, and the ML audit recomputed every statistic from your stored 100k cells. The one
  approved exception is the slices' order for a categorical key feature (Q565), which no
  current key feature is.

Skim steps 4 to 8 of the notebook and the report's summary; nothing else needs a second read.

## 2. The code, with the helper tables (about 90 minutes)
Paths are under `src/core_modelling/`.

1. **The run.**
   - Read: `eda/run.py` → `run_eda` (the order of everything below), `_count_tables`,
     `_stage_meta`, `_write`; `artifacts.py` → `stage_identity`, `SETTINGS_PATHS_BY_STAGE`,
     `write_stage`.
   - Helper: section 1 (the folder) and section 2 (`eda.json`: the identity keys, `settings`,
     `run_token`).
   - Right when: the config is resolved first; the passes run on the persisted `rows`; the
     ledger is saved before the folder, so `eda.json` is the commit marker; `settings` lists
     the six paths a change of which makes EDA stale.
2. **The frames.**
   - Read: `dataset/frames.py` → `build_frames`, `_check_request`, `_eda_frames`. Also
     `_modelling_frames` and `_modelling_rows`: EDA does not call them, but Training will, and
     they changed (the feature list, no validation frame for Training).
   - Helper: section 8a, table 4 (`population`: the counts per compared period) and section 2
     (`collect`).
   - Right when: Training cannot get a validation-period row, a held or excluded feature, or
     run from a config that was only loaded; the select sits after the filters and before the
     sampling.
3. **The counts table.**
   - Read: `dataset/counts.py` → `count_cells`, `count_lagged_cells`,
     `client_constant_shares`; `statistics/cells.py` → `pool_periods`, `shares`,
     `two_way_table`, `population_cells`.
   - Helper: section 4 (`cells`: the numeric's bins by target bin, the categorical's folds, the
     lagged rows) and section 6 (`client_constant`).
   - Right when: every statistic below is a sum over these cells; the null bin is always its
     own; a categorical's cells carry a client fold in the window only.
4. **One feature's concordance.** The part most worth your time: this is the one rule Training
   and Evaluation will call.
   - Read: `statistics/scope.py` whole (162 lines): `scope_statistics`, `feature_se`,
     `concordance_direction`, `unavailable_reason`, `cross_fit_unavailable`,
     `null_concordance`, `encoding_prior_rows`. Then `statistics/concordance.py` →
     `concordance_from_table`, `fold_encodings`, `cross_fitted_concordance`,
     `best_order_concordance`.
   - Helper: section 5 (`ranking`), the two candidates' rows: `concordance`, `concordance_se`,
     `direction`, `raw_sign`, `unavailable` and their `*_window` twins.
   - Right when: the SE is taken at `max(value, 1 − value)`, a window's on effective clients, a
     categorical's inflated once; the direction is 0 below 0.5 + 2 SE; "not available" is
     decided before computing; a categorical's level order is fitted on the other client folds.
5. **The ranking and the key features.**
   - Read: `eda/ranking.py` → `feature_statistics`, `rank_features`, `select_key_features`;
     `statistics/association.py` → `association_table`.
   - Helper: section 5 (the top rows: `ranking_value`, `rank`, `key_feature`,
     `represented_by`) and section 7 (`correlation`).
   - Right when: a non-monotone numeric ranks by its best order; a key feature's
     near-duplicates are skipped and name it in `represented_by`.
6. **The concordance per period.**
   - Read: `eda/deep_dives.py` → `per_period_concordance`, `concordance_per_period`.
   - Helper: section 8a, table 1 (the two candidates across the window periods).
   - Right when: each period is read in the window's direction, so a flipped period reads below
     0.5; its SE is the scope's own (`scope["se"]`); a thin period is marked `insufficient`.
7. **The decision's slices.**
   - Read: `eda/slices.py` → `slice_tables`, `ordered_numeric_bins`,
     `ordered_categorical_bins`; `statistics/capture.py` → `capture_table`, `capture_curve`.
   - Helper: section 8a, table 2 (the first key feature's `slices` and five points of its
     `capture_curve`).
   - Right when: a categorical's list follows the encoding the concordance read
     (`fold_encodings` with the run's prior: the one approved behaviour change); the cut is
     linear inside the boundary bin.
8. **The deep dives.**
   - Read: `eda/deep_dives.py` → `group_table`, `numeric_groups`, `bin_orders`.
   - Helper: section 8a, table 3 (`bins` and `quartiles` of one key feature); section 8 for
     `levels` and `strata`.
   - Right when: one function builds the group table for a numeric and a categorical; the
     groups are cut from the snapshot's eligible rows and equal the cells' (a test compares
     them).
9. **The population views.**
   - Read: `eda/population.py` → `headline_numbers`, `headline_formats`, `target_per_period`,
     `funnel_per_period`, `sources_per_period`, `reference_groups`.
   - Helper: section 8a, table 4 (`target_per_period`, `population`); section 8 (`funnel`,
     `sources`, `reference_groups`).
10. **The ledger.**
    - Read: `ledger.py` → `create_ledger`, `add_columns`, `save_ledger`, `read_ledger`,
      `read_candidates`.
    - Helper: section 9 (a flagged, a clean and a lineage row) and section 1 (`_ledger.json`).
    - Right when: the sidecar holds one run token per stage, and `read_ledger(..., expect=…)`
      refuses a ledger from another run than the stage folder's.
11. **The report.**
    - Read: `eda/report.py` → `build_views`, `report_sections`; `reporting/blocks.py` →
      `headline`, `choices_block`, `appendix`; `reporting/formats.py` → `format_of`.
    - No helper table: open `report.html` beside the code.
    - Right when: a number without a format is refused; every later report can call the same
      blocks unchanged.

## What I would look at first
- `statistics/scope.py`: it is new as a module, and four copies of the SE rule became
  `feature_se`.
- `fold_encodings` with `ordered_categorical_bins`: the only place a number may differ.
- `dataset/frames.py` → `_check_request`: what Training is refused.

## Known limits
- The report is checked in a desktop browser, not yet in the bank's JupyterLab.
- The run time on bank data is unverified.
- `per_period_concordance` still refits a categorical's fold encodings for each period: fitting
  them once per feature needed a parameter with no caller.
