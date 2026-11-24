# Monitoring
**Status:** designing; its input, the drift reference Evaluation writes, built 2026-11-17 (M2.3 major step 3) · **Legacy:** none (score/outcome logging was prepared in the crunch) · earlier name: Tracking
**Related:** [inference](inference.md) · [lifecycle](lifecycle.md) · [reporting](reporting.md) · [dataset](dataset.md)
(drift baselines) · [evaluation](evaluation.md) (writes the drift reference) · [model bundle](model_bundle.md)
(the run folder, `model_hash`, the encoder) · [EDA](eda.md) (the edges, levels and PSI) · [target factory](target_factory.md) (labels) · D-007, D-009, D-016, D-021, D-040, D-054, D-079, D-139, D-141 · OD-13, OD-14

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
| 2. Drift | Input and score drift vs the run's drift reference (below), computed on the true population (one PSI definition, `statistics/distributions.psi` in [eda](eda.md): fixed bins from the reference's quantile edges plus a null bin, categoricals by level with the pooled `__other__` and `__new__`; the reference stores EDA's edges and levels in that shape, so Monitoring reuses the function, D-135) | **deep frame**, a few measures with flags |
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

## The drift reference (written by Evaluation, D-054)
The only part of Monitoring that exists. Layer 2's
yardstick, one per run: Evaluation writes it into the run's `evaluation/` folder
(`evaluation/drift_reference.py::build_drift_reference(stage2, counts, features)`, called by
[evaluation](evaluation.md)), and it belongs to the bundle's `model_hash`, which
`evaluation.json` records ([model bundle](model_bundle.md)). One Spark aggregate of its own:
EDA already counted every feature on every eligible row, and the score side
(`reference_score_counts`) counts the scored test rows.
1. **The final features' distributions over the observation window** (the bundle's features,
   in its order), per test period and pooled over them, from the run's own `stage2/` copy of
   EDA's counts (D-139 (b)), so an EDA rerun never changes it:
   - a numeric: EDA's stored bins (one more than its edges, labelled as EDA's counts table
     labels them), then the null bin;
   - a categorical: EDA's kept levels (the 50 largest) in EDA's order, then `__other__` and
     `null` at EDA's bin orders;
   - per bin or level: its rows (the copy's current cells, folds and target bins added up) and
     its share of the period's rows. Every bin has a row in every period, an empty one at 0.
2. **The distribution of the test scores** (`score`), from every eligible test row Evaluation
   scored, the rows with a null target included (they are scored and count here only, never in a
   metric): their counts in the score bins, pooled over the test periods and merged into 10
   quantile groups of about equal rows (`merge_bins`, a mass point its own group), each with its
   lowest and highest score; per test period and pooled, each
   group's rows and share. It holds test clients only, while production also scores the train
   clients the model was fitted on, so an overfitted model starts Monitoring with a score PSI
   above zero.
3. **On the true eligible population:** EDA's counts and the score counts are every eligible row
   regardless of label, and test is never sampled; the training sample's skew never enters.
4. **A valid input of `psi`:** each period's shares, empty bins at 0, sum to 1 over a bin list
   fixed per feature: they are the `expected_shares` of `statistics/distributions.psi` in the
   bins Monitoring will count production rows into; a test checks it.
5. **How Monitoring bins production data:** a numeric on `drift_edges` as EDA's counts table
   did (`[e_i, e_{i+1})`); a score into the last group whose `score_min` is at or below it, the
   first group taking every lower score. **EDA's levels, not the encoder's:** Monitoring maps a
   level through the encoder (its pooled levels and `__other__`) when it is built.
6. **Fails loud** when a final feature has no cells in the copy or in a test period, when a
   level falls outside its bins, when the score counts hold no test row, or when a scored test
   row has a null or NaN score (`reference_score_counts`).
7. **Versioned** (`CLAUDE.md` §2): `DRIFT_REFERENCE_SCHEMA_VERSION = 2` (the score side
   counts every scored test row, a null target included, and the sidecar exists), stamped as
   `drift_reference_schema_version` in `evaluation.json` and in the reference's own sidecar,
   `evaluation/_drift_reference.json`, which also names the `model_hash`, the run, the
   framework version and the time, so the reference says which model it belongs to without
   the stage json. Nothing reads it yet: Monitoring checks it when it is built. An Evaluation
   rerun rewrites the reference with `evaluation/`; register takes its own snapshot of it, so
   a production model's yardstick cannot move (M2.4, not built).

**Stored tables** (`evaluation/tables/`, named with the prefix `drift_` because `features` is
already the feature table's name):

| Table | Grain | Columns |
|---|---|---|
| `drift_features` | final feature × test period or `pooled` × bin | `feature, kind, period, bin_order, bin, rows, share` |
| `drift_edges` | final numeric feature × edge | `feature, position, edge` (EDA's edges as the run copied them) |
| `drift_scores` | test period or `pooled` × score group | `period, group, score_min, score_max, rows, share` |

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
