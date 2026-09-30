# Data Creation
**Status:** legacy-only · **Legacy:** `src/rollups.py`, `notebooks/Data_Creation.ipynb`

## Purpose
Turn the raw monthly panel into one enriched panel: targets built with forward rollups, engineered
features built with backward rollups, and eligibility flags. It is a single input and a single
output covering many use cases. With a real feature store this stage would shrink, which is why it
gets a light touch until upstream integration is clear.

## Phase 2 requirements
1. Config-driven rollups. Forward windows exclude the current month `(1, m)`; backward windows
   include it `(-(m-1), 0)` (T8). Windows come only from config (T13).
2. Target builders by `task`. Binary is a threshold on a forward rollup; other task types are
   defined but not implemented.
3. Panel-edge guard: the target is null where the full forward window is missing (derived from the
   window, never hardcoded).
4. **Target lineage recorded:** the columns used to build a target are listed in metadata so
   Feature Checks can auto-exclude them (T12).
5. The only sanctioned place for use-case custom code: a named extension point for custom target or
   feature builders.

## Design constraints
- Spark-only (no `toPandas`). One read, one write.
- Time separation is the invariant this stage owns (`CLAUDE.md` §4.1).

## Lessons from the crunch
T8, T11, T12, T13.

## Interface
*(fill when built)*

## Open questions
- Upstream integration (feature store / DE-materialised targets) is still TBD.
