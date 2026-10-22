# Inference
**Status:** legacy-only · **Legacy:** `src/inference.py`, `notebooks/Inference.ipynb`
**Related:** [lifecycle](lifecycle.md) · [training](training.md) (categorical handling) · [monitoring](monitoring.md) ·
[environment](environment.md) · D-016, D-033, D-047, D-051, D-078, D-089, D-103, D-104, D-113, D-116 · OD-18, OD-27, OD-28

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
4. **Output ends at the master layer** (D-103): the framework's own scores table, task-agnostic,
   long format and fully traceable: `unit_id, entity, use_case, model_hash, infer_date, score`,
   plus task-specific columns only when needed. It covers everything a consumer could need
   (candidates: unit id, entity, domain, use case, product, activity, task, score, inference month,
   scoring batch id, run id, model hash, framework and schema version; the exact ones are designed
   when Inference is built). It reserves nullable `task` and `score_component` columns for later
   tasks (D-116). It is a shared table under D-089, and each write replaces only its own slice,
   never another use case's rows (T6, T7). Consumable tables for consumer platforms are built
   outside the framework, by others.

   **Where it is written** (D-113): one schema everywhere, at the place the adapter resolves from
   `conf/local/`. Ideally that is one table per entity × domain, mirroring the repo per entity ×
   domain (OD-02); scores may also be written to separate places. Entities' scores never share a
   table (D-034).

   **The first known consumer format** (received 2026-10-21): the table the retail platform team
   expects today for propensity scores. It is a guide to what the master layer must carry; other
   entities and domains may expect different formats. One table holds every product's scores.

   | Column | Type | Meaning |
   |---|---|---|
   | CustomerID | string | The customer's pseudonymised id |
   | Product | string | The product, e.g. Forex, Credit Cards, Wealth |
   | Activity | string | The model's activity: Retention, Activation or Build |
   | Score | decimal | The model's output, between 0 and 1 |
   | Source | string | The producing team or system (a bank identifier: its value lives in `conf/local/` only) |
   | Date_Refreshed | date | The date the score was refreshed |

   It carries none of the framework's traceability (entity, model hash, run, scoring batch,
   inference month); the master layer keeps it. Because one table holds every product's scores,
   they are compared across products downstream. Retail propensity use cases therefore default to
   the `probability` decision (calibration step on, prior shift applied), and correct calibration
   is a release requirement (D-104; calibration in [training](training.md)).
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
- Spark ships a broadcast model to executors serialised in memory (cloudpickle). That is fine:
  only what is promoted to production must avoid pickle (D-110).
- With retraining in production (OD-27), the manifest's `model_hash` points at the model retrained
  in production, linked to its evaluated parent; the drift reference may need recomputing there.
- The master layer's exact columns (requirement 4) and how product and activity are set (Q292,
  in `worknotes/holistic_review_questions.md`).
- Whether a rank score should sit beside the probability in the long run (OD-28, D-104).
- Output path layout, the part of OD-18 still open: manifests (JSON) currently sit next to the
  score files, which breaks a Hive table built over the scores folder. Separate them. Details to
  come from the LDS.
