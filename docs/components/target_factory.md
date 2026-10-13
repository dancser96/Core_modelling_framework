# Target Factory
**Status:** legacy-only · **Legacy:** `src/rollups.py`, `notebooks/Data_Creation.ipynb` (crunch name: Data Creation)
**Related:** [config](config.md) · [dataset](dataset.md) · [feature checks](feature_checks.md) (lineage
exclusion) · [monitoring](monitoring.md) (labels) · [LLM assist](llm_assist.md) · D-029, D-050, D-054 · OD-15, OD-19

## Purpose
Builds targets. This is the one piece of data work the framework keeps: it links upstream data
engineering with modelling, and target construction is where time leakage starts. The stage is
**optional**: if a target already exists upstream, the use case points at that column and skips it.
Features come from upstream, and the stage asks nothing extra of upstream (D-029).

## Phase 2 requirements
1. **One declarative target spec** in config: source, unit and month keys, forward window and target
   rule. One function builds the targets lazily in Spark; saving is a separate call.
2. **Two modes from the same spec:**
   - **Notebook mode:** build, inspect, save. Later stages read the saved table.
   - **Config mode:** build and hand the result straight to the next stage in memory. The spec's hash
     is recorded, so the run stays reproducible without a saved table. This is also the shape a
     future LLM loop would drive.
3. **Target builders by `task`** through the per-task spec (D-050):
   - binary is a rule on a forward window (e.g. adoption, activation, reactivation);
   - at least one other task type comes in Phase 2 (OD-15).
4. Forward windows exclude the current month `(1, w)` (T8). Windows come only from config (T13).
5. **Panel-edge guard:** the target is null where the full forward window is missing. This is derived
   from the window, never hardcoded.
6. **Target lineage recorded:** the columns used to build each target are written to metadata, so
   Feature Checks excludes them automatically (T12). For targets built upstream, the DS can list the
   lineage columns in config; this is optional and asks nothing of upstream.
7. **Partial and incremental builds.** Build per source, per entity and per month without touching
   other sources' or months' outputs (partitioned, idempotent writes). Domains arrive at different
   times with different schemas, and the spec names columns per source.
8. **The sanctioned extension point** for custom target builders.
9. **Labels for scored months** (D-054): once a scored month's forward window has matured, build
   its targets from the model's frozen target spec, so monitoring can join them to the scores. Use
   cases with upstream targets skip this; monitoring reads the upstream target column.

## Design constraints
- Spark only (no `toPandas`). One read, one write per build.
- Owns invariant §4.1 (time separation) for targets.
- Eligibility is not materialised here. It is an ordered config step applied when the dataset is built
  ([dataset](dataset.md)).

## Lessons from the crunch
T8, T11, T12, T13.

## Interface
*(fill when built)*

## Open questions
- Where engineered features come from long term, and whether a feature-aggregation spec is needed
  for the LLM loop (OD-19). Phase 2: features come from upstream; only the spec's shape is kept in
  mind. The aggregation list agreed as a starting point for such a spec: sum / mean / max / min / std
  over windows, count of non-zero months, months since last non-zero, ratios between windows, and
  trend.
