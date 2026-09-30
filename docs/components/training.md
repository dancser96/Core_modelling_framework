# Training
**Status:** legacy-only · **Legacy:** `src/run.py`, `src/dataset.py`, `src/calibration.py`, `src/contract.py`

## Purpose
Fit a model on the training month using only the vetted features, and write a **local**-tier run
with a frozen config, hashes and training metadata.

## Phase 2 requirements
1. The engine (FLAML) sits behind one small function. A hand-built model must be addable by config
   later.
2. Contract checks on the true population before any sampling:
   - unique id per month
   - non-degenerate target (`nunique > 1`)
   - a plausibility band on the target rate (`CLAUDE.md` §4.8)
3. Scale handling: prune in Spark; sample negatives **in Spark** before `toPandas` when configured
   (per use case `neg_per_pos`; stratified as an option). Keep all positives.
4. Calibration by `task` via a dict. Binary uses `prior_shift`, applied only when downsampling
   happened.
5. Record what the engine actually did:
   - `best_estimator`, `best_config`
   - trials per learner (`config_history`) (T14)
6. Runtime levers are exposed in config: time budget, estimator list, sampling. Defaults scale
   with population size.

## Design constraints
- The engine never sees the raw feature universe; evaluation happens outside it.
- No hidden retries or silent fallbacks.

## Lessons from the crunch
T9, T14; downsampling, calibration and FLAML-search lessons in `docs/context/lessons.md`.

## Interface
*(fill when built)*

## Open questions
- Verify FLAML 2.7 + xgboost 3.2 before enabling xgboost by default.
