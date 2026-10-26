# Evaluation
**Status:** legacy-only · **Legacy:** `src/evaluate.py`, `src/importance.py`, `src/analysis.py`
**Related:** [reporting](reporting.md) · [training](training.md) · [dataset](dataset.md) · [lifecycle](lifecycle.md)
(gates) · D-030, D-035, D-036, D-037, D-038, D-049, D-050, D-082, D-083, D-091, D-098, D-100 · OD-12

## Purpose
Judge a model out of time against declared baselines, outside the engine. Produce the numbers and
views needed for gates, the model card, model comparison and the business conversation: the widest
practical set of metrics and charts, produced reliably for every model family.

## Phase 2 requirements
1. **Metrics from the per-task spec** (D-050). Binary: AUC, PR-AUC, base rate; precision / recall / lift at the
   `top_pct` and `top_n` slices. What gets emphasised follows the declared decision.
2. **Test vs validation:** metrics on test (unseen clients, same months) and on validation (OOT).
   For a run nothing was picked on, the gap separates overfitting from decay over time, apart from
   the cost below; a sweep's winner states that its test-vs-validation gap mixes overfitting with
   selection (D-083). The model results report states the cost of EDA and Feature Checks using
   every client (D-030): people's feature decisions there have seen test clients' labels, so test
   is not untouched by them; the validation month, whose labels EDA and Feature Checks never see,
   stays the one honest number. Test
   metrics are shown per observation month first and pooled second, so test compares with the
   single validation month (D-098); a per-month statistic is shown only for months with at least
   50 positive events (D-091). Optional:
   validation on test clients only (unseen clients and an unseen month), the cleanest estimate.
3. **Stratified metrics are mandatory** (D-038). Every metric is shown overall and per level of each
   configured variable. Levels are capped (top levels + "other"), and strata below the per-task
   minimum support (binary: positive events, D-082) are shown as insufficient.
4. **Baselines:** population base rate (always), previous model, historic predicted rate, as declared.
5. **Views are organised as slots**, each with an ordered list of methods. The method is chosen per
   model family from a **compatibility table** (view × family → method, or "not available: reason"):
   - **core** (which ones: OD-12): gains / lift, calibration (reliability), score distribution,
     stratified metrics, permutation importance, one feature-effects slot (SHAP on the booster,
     D-037: the tree explainer where supported, otherwise model-agnostic on a sample; proposed,
     OD-12);
   - **extended:** PDP / ICE, categorical per-level direction tables, …

   Complementary methods from different families share a slot: one cell shows whichever the model
   supports, labelled with the method used.
6. **Failure policy** (D-035): a view the table declares compatible must work, and a failure is an
   error. Incompatible views are skipped by design and shown as "not available: reason".
7. **Model comparison is first-class.** Several runs (challenger vs champion, window variants) are shown on the identical validation set, overlaid and side
   by side. Where the rows match, differences come from a **paired bootstrap** over validation
   clients, which gives much tighter intervals than comparing two separate ones. The window ablation's design is owned by
   [dataset](dataset.md). A sweep picks on train and test metrics; the validation month is
   reported for every variant and never chooses (D-083). Reports show validation
   everywhere, sweep tables included, and people are trusted not to choose on it (D-083).
8. Results are structured data first; plots and reports are rendered from them. Evaluation writes
   the model results report, after FLAML training; Training itself writes artifacts only (D-036).

## Design constraints
- Rank metrics are unaffected by calibration. Reliability curves use calibrated scores, on axes
  fitted to the data (T16).
- PR-AUC is not comparable across use cases (its floor is the base rate). Say so in reports.
- A view's runtime is not a reason to drop it; compatibility and reliability are.

## Lessons from the crunch
Pooled AUC inflation. Importance caveats: collinearity splits credit; native importance misaligned
with raw-string categoricals. SHAP failed across the original estimator set and had to be disabled
(T17).

## Interface
*(fill when built)*

## Open questions
- **To decide when Evaluation is built (M2.3):** the mandatory core set per task (OD-12, which
  covers the EDA, Feature Checks and Evaluation reports).
  Proposal for binary: core = gains / lift, reliability (correct calibration is a release
  requirement, D-049), score distribution, the stratified metrics table, permutation importance,
  one feature-effects slot (SHAP's tree explainer, which covers all three M2 families); extended
  = PDP / ICE, per-level categorical tables. In M2 the compatibility table is a dict of view →
  function with "not available: reason" entries (D-100).
- Parked proposal: store all results as tidy tables, with bootstrap intervals by default. Revisit when
  evaluation is designed in depth.
