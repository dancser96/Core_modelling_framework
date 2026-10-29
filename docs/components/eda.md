# EDA
**Status:** legacy-only (major rethink) · **Legacy:** `src/feature_stats.py`, `src/plots.py`, `notebooks/EDA.ipynb`
**Related:** [dataset](dataset.md) · [feature ledger](feature_ledger.md) · [feature checks](feature_checks.md) ·
[reporting](reporting.md) (chart rules) · D-023, D-030, D-031, D-036, D-050 · OD-12

## Purpose
The first stage after the target exists, and it has to be worth running first. It gives a fast,
readable picture of the population, the target and the features that matter, built for low
prevalence. It informs decisions and never changes data. In the crunch, EDA produced so little insight
that the notebooks were run in reverse order. Phase 2 fixes the content, not the order.

## What belongs where
- **EDA understands:** population, target, key features, segment differences. It computes the
  univariate ranking once and writes it to the feature ledger, where Feature Checks and key-feature
  selection reuse it. Training's automated selection never does: it recomputes its statistics on the
  train split (D-030).
- **Feature Checks gates:** pass / flag per feature ([feature checks](feature_checks.md)).
- **Training selects:** relevance-based selection on the train split only
  ([training](training.md)).

## Phase 2 requirements
1. Runs alone from a config and produces an HTML report through [reporting](reporting.md) (D-036).
   The `autonomous` level runs it automatically with the default content (D-031).
2. **Population and target:**
   - sizes and the eligibility funnel per period of the window: the analysis filters' drops and,
     per modelling filter, the rows it tags (D-129);
   - **reference groups:** each modelling tag (e.g. current holders vs non-holders) is a
     stratification column, so the excluded group's behaviour is compared with the modelling
     population's on the strata and the key features, on every row of the window frame; which
     views show tagged rows is settled when EDA is built (M2.2). A tag whose filter is the
     rule's own precondition (current holders under `flag_goes_up`) has a target rate of 0 by
     construction, so its comparison is label-free;
   - base rate per period over every period up to the window's end (population level: seasonality,
     how representative the window is). Later periods stay hidden, because their target windows
     overlap the validation period's (D-030);
   - positive rows vs positive events;
   - per-period row and positive counts are also saved as data in the EDA artifacts, so a later run
     on the same data definition shows when a source period was restated (`CLAUDE.md` §4.10);
   - base rate by segment and by each stratification variable.

   Base-rate views, like the ranking statistic, come from the per-task spec (D-050).
3. **Univariate ranking** of every candidate on the eligible rows of the window frame (every
   eligible client, labels included; a row filter in pandas on the one collected frame, never a
   second collect; D-030). The statistic comes from the per-task spec (D-050); binary:
   direction-agnostic AUC plus direction, missingness, number of levels. Written to the ledger.
   MI only above a prevalence threshold, or not at all.
4. **Key features** = the top-N by the ranking plus user-listed ones. Each gets a deep dive:
   - lift vs base rate across quantile bins, with Wilson intervals and positive counts;
   - distribution by target (violin / box; log scale for heavy tails);
   - target-rate pivots by segment, styled to highlight what stands out;
   - categorical level tables (rate, lift, count, interval).
5. **Segment comparisons** for the configured stratification variables: headline rates and
   key-feature behaviour side by side.
6. **Low prevalence by design:**
   - rates shown as lift vs base rate, with intervals and counts;
   - cells with too few positives suppressed;
   - axes follow the data ([reporting](reporting.md) chart rules);
   - no chart whose bars are all near zero.
7. **Iterative analysis:** notebook functions for styled pivots (rate / lift with counts and
   intervals, by any dimensions, with any filter), so analysts can play around without writing code.
   The report itself stays tight.
8. **Every client of the window after the analysis filters**, labels included, for the
   population and reference-group views (§4.4, D-030): EDA is a product in its own right, and
   the notebooks' data-analysis tools need the whole population, the rows the modelling filters
   tag included (the analysis filters alone remove rows, D-129). The univariate ranking and
   every label statistic that feeds a choice (the top-N key features) run on the eligible rows
   of the same frame, a row filter in pandas on the one collected frame, never a second collect.
   The train/test client split happens after Feature Checks. Label-based views never show periods
   after the window; population-level rates may show every period up to the window's end.
9. **Fast at 2M+ rows per period:** aggregate in Spark or on declared samples, and say so in the report.

## Design constraints
- Report content comes from functions; notebooks display it and add exploration.
- Every number is reproducible from the resolved config and the data-definition hash.

## Lessons from the crunch
MI uselessness at 0.04–0.2% prevalence; the 30–40 min runtime; notebooks copied per product; charts
that showed nothing at low prevalence (T16); EDA run last because it gave no insight.

## Interface
*(fill when built)*

## Open questions
- Default number of key features per automation level; exact report sections (structure agreed: summary page
  + core + extended, see [reporting](reporting.md); the core views per task: OD-12).
- Which pivot dimensions to pre-compute in the report vs leave to the notebook functions.
- Ranking statistic and base-rate views for the second task type (regression, D-050, D-020).
- `strata.variables` naming a key or a column the dataset adds (`unit_id`, `period`, `target`,
  `split`, `eligible`): a source column of that name is read as `source_<name>`, so such a
  stratum would silently use the framework's column; refuse it with that hint when the stage
  is built (found in the 10-29 silent-failure audit).
