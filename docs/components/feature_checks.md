# Feature Checks
**Status:** legacy-only (major rethink) · **Legacy:** `src/leakage.py`, `src/feature_stats.py` (`signal_persistence`), `notebooks/Feature_Checks.ipynb`

## Purpose
The correctness gate between candidates and model inputs. It runs as a standalone unit and
produces a **stepwise, traceable** screening log. Each step states what it flagged or removed and
why, so every exclusion can be audited.

## Phase 2 requirements
1. Ordered, configured screening steps. Each writes a log entry (features in → out, reason, step
   parameters).
2. Leakage screen:
   - univariate AUC
   - dominance / missingness
   - a near-perfect-separator flag

   It **flags, never drops**; a human decision (recorded in config) excludes.
3. **Automatic lineage exclusion** of target-construction columns (T12).
4. Eligibility-interaction check: flag features that are constant within the eligible population
   (T11).
5. Signal persistence obs → OOT:
   - univariate AUC drift
   - PSI for numeric features
   - a separate stability measure for categoricals (T10)
6. Optional low-signal pruning (univariate AUC floor ~0.515) as a declared speed step.
7. Output: the proposed `features_exclude`, ready to paste or apply to config, plus the log.

## Design constraints
- Reads the candidates view; the model reads the survivors.
- No automated selection on full data; selection that uses the target happens only on the training
  period (`CLAUDE.md` §4.4).

## Lessons from the crunch
T10, T11, T12; the AUC-floor heuristic and its standard error at few positives.

## Interface
*(fill when built)*

## Open questions
- Exact step catalogue and log format. **The user will provide more input** on traceable
  stepwise configs.
