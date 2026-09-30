# Inference
**Status:** legacy-only · **Legacy:** `src/inference.py`, `notebooks/Inference.ipynb`

## Purpose
Pure scoring. Load registered/production models, score the eligible population for a month (or
another table with the same schema), and write one batch-scoped output with a manifest. No
promotion happens here.

## Phase 2 requirements
1. Model selection per use case: production pointer (default), a registered `run_id`, or a dict
   `{use_case: run_id}`. Local runs only in dev mode.
2. Eligibility and features come from the model's frozen config, so a model always scores its own
   definition.
3. Output is task-agnostic and long format: `id, use_case, model_hash, infer_date, score` (plus
   task-specific columns only when needed).
4. **Batch-scoped and written once:** `<outputs>/<scoring_batch_id>/{scores, manifest}`. Collect,
   then write once; assert that every "ok" use case is present on disk (T6, T7).
5. **Reinference** from a manifest: rescore the same registered models on a new month or table
   without local runs.
6. Scale: score in Spark (e.g. model broadcast / pandas UDF) or in pruned chunks; never collect the
   full population at once.

## Design constraints
- Hash verification before loading any model.
- The manifest schema is versioned (`CLAUDE.md` §2).

## Lessons from the crunch
T2–T7; the per-use-case run-pin dict; reinference worked without local runs.

## Interface
*(fill when built)*

## Open questions
- Scoring in Spark vs driver-side chunks for the largest populations (decide by measurement).
