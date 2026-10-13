# Feature Checks
**Status:** legacy-only (major rethink) · **Legacy:** `src/leakage.py`, `src/feature_stats.py` (`signal_persistence`), `notebooks/Feature_Checks.ipynb`
**Related:** [feature ledger](feature_ledger.md) · [EDA](eda.md) · [training](training.md) (automated selection) ·
[target factory](target_factory.md) (lineage) · [dataset](dataset.md) · D-028, D-031, D-048, D-050 · OD-10

## Purpose
The correctness and data-quality gate between candidates and model inputs. It is a standalone unit
with a stepwise, traceable log: each step states what it flagged or excluded and why, and writes it to
the feature ledger. Relevance-based selection is no longer here; it moved into Training, on the train
split only (D-028).

## Two modes
- **Human:** flags are reviewed, and decisions (exclude, or keep despite a flag, with reasons) go into
  the config.
- **Automated** (hands-off profiles): the checks run and flag exactly the same way, and nothing waits
  for a human before training. Unresolved flags are listed on the model card and block registration
  until someone decides on them (D-031).

## Phase 2 requirements
1. Ordered, configured steps. Each writes a log entry (features in → out or flagged, reason,
   parameters) and its ledger columns.
2. **Data quality:** missingness, constant / near-constant, cardinality, type problems.
3. **Leakage screen** on train-split clients: near-perfect separators (the per-task statistic;
   binary: univariate AUC), dominance and missingness patterns. It flags and never drops; a human
   decides (§4.6).
4. **Automatic exclusion** of target-lineage columns (T12).
5. **Eligibility interaction:** flag features that are constant within the eligible population (T11).
6. **Stability** (§4.4, D-048):
   - per-month univariate AUC range and PSI across the window's months, on train-split clients;
   - a separate stability measure for categoricals (T10);
   - label-free drift (PSI) of the window against the gap months between the window and the
     validation month, and against the latest available month (the one production will score);
   - never against the validation month: a feature dropped because it drifted there makes the
     validation result look better than production will be.
7. **Redundancy:** pairs with high correlation or VIF are flagged with both features' AUCs side by
   side, so a human can keep both. Nothing is dropped here.
8. **Output:** ledger columns; proposed decisions ready to paste into the config; the log; an HTML
   report.

## Design constraints
- Reads the candidates. The model reads the resolved list ([feature ledger](feature_ledger.md) rules).
- Nothing here uses test clients' labels or the validation month.

## Lessons from the crunch
T10, T11, T12. The AUC-floor heuristic and its standard error at few positives now belong to
automated selection in [training](training.md).

## Interface
*(fill when built)*

## Open questions
- Exact step catalogue and thresholds per profile.
- How decisions persist across reruns (config lifecycle, OD-10).
