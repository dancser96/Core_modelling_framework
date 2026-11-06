# Stage 2 EDA: the review guide for the LDS
_Written 2026-11-06 at the SDS's request (D-072 (i)) for the LDS's review of EDA as built, with
the Target Factory changes it needed. About 1.5 hours: the two notebooks first (an hour), then
six key points (about 30 minutes); the code is optional. Your feedback may still change EDA;
Feature Checks, which reads EDA's output, is being built meanwhile._

## What EDA is
- **One run per use case** (`run_eda`): it reads the model input, computes every number over the
  observation window and on the **snapshot** (the window's last period, every client), writes
  `eda/` with a self-contained HTML report, and changes nothing: it drops no row or feature and
  records no decision. Feature Checks, next, is the gate that holds features out.
- **Nothing is sampled** (D-135): the window is counted in Spark as one table of counts per
  feature, bin and target value; the snapshot is analysed whole in pandas.
- **One ranking scale, concordance**: AUC for a binary target, its generalisation (Somers' D)
  for an amount; 0.5 is chance, 1 a perfect ordering, either way round. The **key features**
  are the top 10 without near-duplicates, plus any the config lists.
- **Labels in sample** (D-030): EDA reads every client's labels in the window, before the
  train/test split, so decisions taken here have seen test labels; the model report will say so.
  The validation period's labels are never read.

## 1. Notebook 01 · Target Factory (15 minutes)
Setup: `docs/guides/setup_macos.md` or `setup_windows_wsl2.md`, the synthetic data generated.
The data is the canonical synthetic preset: about 100,000 clients per month and 160 candidate
features, among them planted problems whose names end in `_trap_<kind>` (a leak, a look-ahead,
a shifted target, …), so you can see where each lands. Run top to bottom and look at:
- **Step 1, the summary per period.** The label columns (`mean_target`, `positive_rows`,
  `positive_events`) are filled up to 2025-08, the window's last period, and blank after: those
  periods' 3-month targets would reach the validation period's outcomes.
- **Step 1, the occurrences.** The conversions per period (the flag going 0 → 1), up to 2025-11
  (the window's last + 3 months); the first period has none, since it has no previous month.
- **Step 3, the snapshot per use case**: rows, candidates, the eligible share, the target mean.

**Feedback wanted:** is a conversion counted as you would count an acquisition, and is the cut
of the labels where you would put it?

## 2. Notebook 02 · EDA (45 minutes)
Read each step's guide cell before its output: the guide cells are a deliverable in their own
right, written for a data scientist new to the framework. Then the report (step 8) in a browser.
What right looks like on this data:
- **Step 4, the population.** Steady rows per period through the funnel; every feature source
  matching close to all of the spine's rows; the card rate about 3% per period.
- **Step 5, the ranking.** The traps lead it: the upstream target at concordance 1.00, the two
  leak scores at 0.97 and 0.89, the look-ahead count at 0.80, the shifted limit at 0.70. The real
  signals follow at 0.65–0.67: income, the account inflows and outflows, the onboarding channel.
  Seven of the ten key features are traps; Feature Checks is where they are held out.
- **Step 5, the decision's slices.** Each key feature alone as a list, cut at the evaluation
  slices: at the top 10% the upstream target captures every positive, the leak score 88%, income
  24% (lift 2.4). Context for the decision, never a baseline for a model.
- **Step 6, the key features.** Lift by group, the same by stratum (segment, channel), the
  concordance per period (flat is stable), boxes by target class, one pivot per stratum.
- **Step 7, the four exploration functions**: a pivot, lift within another variable, the two
  sides of a modelling filter, the target per period by group.
- **Step 8, the report only:** the reference group (the current card holders the filter keeps
  out), the correlation overview of the key features, the value profile, the appendix.

**Feedback wanted:**
1. Are these the views you would want first, in this order? Is anything missing that you would
   check on a real card or deposit use case?
2. Is concordance readable as the one ranking scale, and are the key features the ones you would
   look into?
3. Do the guide cells tell a new user what to look at and what to decide, without being long?
4. Does any chart mislead you (axes, grey points, colours)? The rules: `docs/components/
   reporting.md` → "Chart rules".

## 3. Key points to judge (about 30 minutes)
Each: the choice, where to read it, the feedback wanted.
1. **No sampling.** D-135; `docs/components/eda.md` → Level 1 and "The counts table". On this
   data the snapshot takes about 1 GB in Python: is that safe for the bank's retail size?
2. **Panel-aware statistics.** A client appears in every window period, so a window's standard
   error counts effective clients, and a categorical's level order is learnt on other clients
   (five client folds), so a noise code cannot look predictive. `eda.md` → "The statistics" (its
   table first). Is the `direction` rule (only when clear of chance) the reading you want?
3. **The key features.** `eda.md` → "The views" (the ranking and key features): the top 10
   without pairs above `eda.key_features.max_correlation`; each one lists the candidates it
   represents. Is 10 the right default?
4. **Labels and time.** `docs/components/target_factory.md` → Level 1; `eda.md` → "The snapshot
   and the compared periods": labels up to the window's last, later periods compared without
   labels, the validation period never read.
5. **The decision's slices.** D-138; `eda.md` → "The views", "At the decision's slices": in
   sample, the categorical order cross-fitted, never a baseline (models are judged against
   `decision.baselines`). Useful, or noise in the report?
6. **What EDA records.** The feature ledger (`docs/components/feature_ledger.md` → Level 1): one
   row per candidate with its kind, source and EDA's statistics; Feature Checks adds its
   findings, Training the use in the model.

## 4. Code, if you have time (optional, 20 minutes)
- `src/core_modelling/eda/ranking.py` → `select_key_features`: the key-feature rule.
- `src/core_modelling/statistics/concordance.py` → `cross_fitted_concordance`,
  `kendall_null_se`: the categorical's out-of-fold order and the regression's standard error.
- `src/core_modelling/eda/slices.py` → `ordered_categorical_bins`, `capture_table`.
- `src/core_modelling/tasks.py` → `_summarise`, `_occurrences`: the two cut-offs of notebook 01.

## Known limits
- The report is checked in a desktop browser, not yet in the bank's JupyterLab (it may need
  **Trust HTML** there).
- The run time on bank data is unverified; on the synthetic data `run_eda` takes a few minutes.
- A target flag that is null between a 0 and a 1 counts as a positive for the target rule but
  not as a conversion; notebook 01 says so.
