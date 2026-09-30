# Tracking: baselines, impact, drift
**Status:** designing · **Legacy:** none (score/outcome logging was prepared in the crunch)

## Purpose
Simplified impact tracking built into the framework. Once labels mature, join scores to realised
outcomes and report performance against baselines. Until then, watch input drift.

## Phase 2 requirements
1. Outcome join: scores (by `scoring_batch_id`, `model_hash`) + matured targets from the panel.
2. Realised metrics in the targeted slices vs baselines:
   - **population base rate** for business reporting
   - **previous model** and **historic predicted rate** for internal metrics
3. Input drift vs the training month (PSI for numeric features, a stability measure for
   categoricals), available immediately.
4. Output: a small tracking report per use case, plus a table suitable for a unit-wide view across
   many models.

## Design constraints
- Performance tracking is label-gated; its absence before labels mature is correct, not a gap.
- Keep the maths trivial and transparent. This is for the business and for model maintenance, not
  research.

## Open questions
- Retraining triggers and retirement policy (recorded as policy first, automation later).
