# Monitoring
**Status:** designing · **Legacy:** none (score/outcome logging was prepared in the crunch) · earlier name: Tracking
**Related:** [inference](inference.md) · [lifecycle](lifecycle.md) · [reporting](reporting.md) · [dataset](dataset.md)
(drift baselines) · [training](training.md) (drift reference) · [target factory](target_factory.md) (labels) · D-009, D-040, D-054 · OD-13, OD-14

## Purpose
Keep every production model honest. Is it running? Are its inputs and scores stable? Once outcomes
exist, is it delivering against its baselines? The audience is model owners, the Lead DS, the business,
and the strategy team that relays results to the business.

## Layers and Phase 2 depth

| Layer | What | Phase 2 depth |
|---|---|---|
| 1. Operational | Scoring ran; row counts; eligible population size vs history; score distribution; share of unseen categorical levels | **deep** |
| 2. Drift | Input and score drift vs the drift reference saved at training, computed on the true population (PSI for numeric features, a separate measure for categoricals) | **deep** |
| 3. Realised performance | Scores joined to matured outcomes (labels from Target Factory for the scored months, or the upstream target column, D-054); metrics in the targeted slices vs baselines (population base rate for business reporting; previous model and historic predicted rate internally) | **thin**: must work quickly once conversion labels arrive |
| 4. Business impact | Campaign results; needs campaign outcome data from the campaign system | **thin** |

## Phase 2 requirements
1. Monitoring tables (one row per model × scoring batch × metric), an HTML report per use case, and a
   cross-model view.
2. Thresholds raise flags; there is no alerting in Phase 2. A retrain policy declared in config (e.g.
   maximum age, drift threshold) sets a "retrain recommended" flag.
3. The outcome join is keyed by `scoring_batch_id` and model hash, and is built and tested on synthetic
   data, so it works the day labels exist.

## Design constraints
- Performance monitoring is label-gated. Its absence before labels mature is correct, not a gap.
- Simple, transparent maths: this serves the business and model maintenance, not research.

## Open questions
- Tooling: MLflow or not, what to expose, where dashboards live (OD-13, after the Chief DS meeting).
  MLflow suits the registry and experiment tracking better than tracking decay over time, and the
  Chief DS is expected to see it the same way. The monitoring design itself (what is computed,
  stored and shown, and where) needs much more work.
- How monitoring feeds the model inventory (OD-14).
- Who acts on a flag and owns a live model after its builder moves on. Proposal for the CDS: a
  central team monitors the live models.
- Whether the existing data observability framework can be reused for monitoring (OD-13).
- Retraining automation and retirement policy (recorded as policy first, automation later).
