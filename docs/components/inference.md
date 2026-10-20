# Inference
**Status:** legacy-only · **Legacy:** `src/inference.py`, `notebooks/Inference.ipynb`
**Related:** [lifecycle](lifecycle.md) · [training](training.md) (categorical handling) · [monitoring](monitoring.md) ·
[environment](environment.md) · D-016, D-033, D-047, D-051, D-078 · OD-18, OD-27

## Purpose
Pure scoring. Load production (or pinned registered) models, score the eligible population for a
month (or another table with the same schema), and write one batch-scoped output with a manifest. No
registering, promoting or deploying happens here.

## Phase 2 requirements
1. **Model selection per model key:** the production version (default), a pinned registered version,
   or a dict `{model key: run_id}`. Local runs only in dev mode. Scoring routes by model key; split =
   `all` in Phase 2.
2. **Eligibility and features come from the model's frozen config,** so a model always scores its own
   definition.
3. **Unseen categorical levels** map to `__other__` and are counted per column, reported in the
   manifest and monitored. A missing column or a changed type fails loud ([training](training.md)).
4. **Output is task-agnostic and long format:** `unit_id, entity, use_case, model_hash, infer_date,
   score`, plus task-specific columns only when needed. The exact format, including extra columns
   for the campaign system, is open (OD-18).
5. **Batch-scoped and written once.** Collect, then write once, and assert that every "ok" model
   landed on disk (T6, T7). The path layout is under review (manifests vs score files, OD-18).
6. **Reinference** from a manifest: rescore the same registered models on a new month or table,
   without local runs.
7. **Scale:** score in Spark (e.g. model broadcast / pandas UDF) or in pruned chunks; never collect the
   full population at once.
8. Production scoring runs from the CLI under the production setup, never from a DS notebook. The
   exact scheduling setup inside the bank is unverified.
9. **Framework version** (D-047): models are scored with the use case's pinned framework version.
   When a use case raises its pin, its production model must still load (versioned bundle, D-051;
   never pickle, D-078)
   and score identically under the new version, or be retrained.

## Design constraints
- Hash verification before loading any model.
- The manifest and scores schemas are versioned (`CLAUDE.md` §2).
- Entities' scores are never combined into one output.

## Lessons from the crunch
T2–T7; the per-use-case run-pin dict; reinference worked without local runs.

## Interface
*(fill when built)*

## Open questions
- Scoring in Spark vs driver-side chunks for the largest populations (decide by measurement).
- Spark ships a broadcast model to executors serialised in memory (cloudpickle). D-078 is about
  model files; confirm that in-memory serialisation is acceptable, or load the bundle's plain-data
  format on the executors (unverified).
- With retraining in production (OD-27), the manifest's `model_hash` points at the model retrained
  in production, linked to its evaluated parent; the drift reference may need recomputing there.
- Extra output columns (e.g. product) needed for seamless integration with the downstream campaign /
  decisioning system. Details to come from the Lead DS (OD-18).
- Output path layout: manifests (JSON) currently sit next to the score files, which breaks a Hive
  table built over the scores folder. Separate them. Details to come from the Lead DS (OD-18).
