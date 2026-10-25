# Monitoring
**Status:** designing · **Legacy:** none (score/outcome logging was prepared in the crunch) · earlier name: Tracking
**Related:** [inference](inference.md) · [lifecycle](lifecycle.md) · [reporting](reporting.md) · [dataset](dataset.md)
(drift baselines) · [training](training.md) (drift reference) · [target factory](target_factory.md) (labels) · D-007, D-009, D-016, D-021, D-040, D-054, D-079 · OD-13, OD-14

## Purpose
Keep every production model honest. Is it running? Are its inputs and scores stable? Once outcomes
exist, is it delivering against its baselines? The audience is model owners, the Lead DS, the business,
and the strategy team that relays results to the business. Who acts on flags, and who owns a live
model after its builder moves on, are for the platform / MLOps team to handle (D-079).

## Layers and Phase 2 depth

Phase 2 builds the frame properly and keeps the content light (D-040). The frame is
all four layers present, their tables with `schema_version`, `framework_version` (D-007 (b)) and
flags, where they are written, and the seam to the data observability framework, whose needs shape
the tables only once we have seen it in use (D-021, OD-13). The content is a few health and drift
measures with flags; little usage is expected before Phase 3.

| Layer | What | Phase 2 depth |
|---|---|---|
| 1. Operational | Scoring ran; row counts; eligible population size vs history; score distribution; share of unseen categorical levels | **deep frame**, a few measures with flags |
| 2. Drift | Input and score drift vs the drift reference saved at training, computed on the true population (PSI for numeric features; for categoricals, PSI on level shares with `__other__`) | **deep frame**, a few measures with flags |
| 3. Realised performance | Scores joined to matured outcomes (labels from Target Factory for the scored months, or the upstream target column, D-054); metrics in the targeted slices vs baselines (population base rate for business reporting; previous model and historic predicted rate internally) | **thin**: must work quickly once conversion labels arrive |
| 4. Business impact | Campaign results; needs campaign outcome data from the campaign system | **stub** |

## Phase 2 requirements
1. Monitoring tables (one row per model × scoring batch × metric, keyed by metric name, D-016),
   each with `schema_version`, `framework_version` and flags and written where the adapter
   resolves; and an HTML report per use case. The cross-model view belongs to the model inventory
   (OD-14), not to monitoring.
2. Thresholds raise flags; there is no alerting in Phase 2. A retrain policy declared in config (e.g.
   maximum age, drift threshold) sets a "retrain recommended" flag.
3. The outcome join is keyed by `scoring_batch_id` and model hash, and is built and tested on synthetic
   data, so it works the day labels exist.
4. Monitoring outputs are integrated with the **data observability framework** (D-021). How is
   designed after the work stream that learns it; its needs shape the monitoring tables only once
   we have seen it in use (OD-13).

## Design constraints
- Performance monitoring is label-gated. Its absence before labels mature is correct, not a gap.
- Simple, transparent maths: this serves the business and model maintenance, not research.

## Open questions
- Tooling and dashboards: the platform / MLOps team's to handle (D-079). The data observability
  integration is ours, designed after the work stream (D-021, OD-13). MLflow suits the registry and experiment tracking better than tracking
  decay over time. Richer content (more measures, deeper realised performance and impact) waits
  for Phase 3 (D-040).
- How monitoring feeds the model inventory (OD-14).
- Retraining automation and retirement policy (recorded as policy first, automation later).
