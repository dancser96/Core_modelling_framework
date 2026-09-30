# Evaluation
**Status:** legacy-only · **Legacy:** `src/evaluate.py`, `src/importance.py`, `src/analysis.py`

## Purpose
Judge a model out-of-time against declared baselines, outside the engine. Produce the numbers and
views needed for promotion gates, the model card and the business conversation.

## Phase 2 requirements
1. Metrics dispatched by `task` (dict). For binary:
   - AUC, PR-AUC, base rate
   - precision / recall / lift at `top_pct` and `top_n` slices (config lists)
2. **Segment-stratified metrics** (config-declared segment columns), so pooled AUC isn't mistaken
   for within-segment skill.
3. Baselines: population base rate (always), previous model, historic predicted rate — as declared.
4. Views:
   - cumulative gains
   - calibration / reliability curve
   - score distribution
   - permutation importance
   - numeric direction (PDP/ICE)
   - categorical per-level direction table
   - optional SHAP beeswarm (sampled)
5. Results are structured data first (dicts/tables); plots and reports are rendered from them.

## Design constraints
- Rank metrics are unaffected by calibration; reliability curves use calibrated scores.
- PR-AUC is not comparable across use cases (its floor is the base rate). Say so in reports.

## Lessons from the crunch
Pooled AUC inflation; importance caveats (collinearity splits credit; native importance
misaligned with raw-string categoricals; SHAP cost).

## Interface
*(fill when built)*

## Open questions
- Which views are mandatory in the model card vs optional.
