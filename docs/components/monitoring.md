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
flags, and where they are written. The content is a few health and drift measures with flags.

| Layer | What | Phase 2 depth |
|---|---|---|
| 1. Operational | Scoring ran; row counts; eligible population size vs history; score distribution; share of unseen categorical levels | **deep frame**, a few measures with flags |
| 2. Drift | Input and score drift vs the drift reference saved at training, computed on the true population (PSI for numeric features; for categoricals, PSI on level shares with `__other__`) | **deep frame**, a few measures with flags |
| 3. Realised performance | Scores joined to matured outcomes (labels from Target Factory for the scored periods, or the upstream target column, D-054); metrics in the targeted slices vs baselines (population base rate for business reporting; previous model and historic predicted rate internally) | **thin**: must work quickly once conversion labels arrive |
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

## Design constraints
- Source-table quality (schema, freshness, nulls, ranges) is the **data observability
  framework's**: a Great Expectations-style suite run on production tables, to which a production
  model's source tables are pointed at deploy (D-021, [lifecycle](lifecycle.md)). Monitoring
  doesn't repeat those checks and doesn't feed that framework; it watches what only the model
  knows: the inputs as the model sees them against the drift reference, the scores, and
  realised performance.
- Performance monitoring is label-gated. Its absence before labels mature is correct, not a gap.
- Simple, transparent maths: this serves the business and model maintenance, not research.

## Open questions
- Tooling and dashboards: the platform / MLOps team's to handle (D-079, OD-13). MLflow suits the
  registry and experiment tracking better than tracking decay over time.
- How monitoring feeds the model inventory (OD-14).
- Retraining automation and retirement policy (recorded as policy first, automation later).
