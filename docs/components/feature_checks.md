# Feature Checks
**Status:** legacy-only (major rethink) · **Legacy:** `src/leakage.py`, `src/feature_stats.py` (`signal_persistence`), `notebooks/Feature_Checks.ipynb`
**Related:** [feature ledger](feature_ledger.md) · [EDA](eda.md) · [training](training.md) (automated selection) ·
[target factory](target_factory.md) (lineage) · [dataset](dataset.md) · D-028, D-031, D-048, D-050, D-076, D-077 · OD-10, OD-25

## Purpose
The correctness and data-quality gate between candidates and model inputs. It is a standalone unit
with a stepwise, traceable log: each step states what it flagged or excluded and why, and writes it to
the feature ledger. Relevance-based selection is no longer here; it moved into Training, on the train
split only (D-028).

## Two modes
- **Human:** flags are reviewed, and decisions (exclude, or keep despite a flag, with reasons) are
  recorded: in the config today; whether they move to the decision audit log is OD-10.
- **Automated** (hands-off profiles): the checks run and flag exactly the same way, and nothing waits
  for a human before training. Unresolved flags are listed on the model card and block registration
  until someone decides on them (D-031).

Either way a **human gate** follows: a person must be able to defend every feature in the model, so
a person signs off the features before any model is registered, at every automation level. In human
mode it closes this stage, on the list after the checks (automated selection can only drop from
it). In hands-off runs it comes after training, on the model's final list, and rejecting a feature
then means a retrain. An LLM review never passes this gate (D-076). The sign-off is given over the
model's final list, shown with flags grouped and features sorted by importance, with train-only
evidence; the candidate list (hundreds) is reviewed only where flagged (D-092).

## Phase 2 requirements
1. Ordered, configured steps. Each writes a log entry (features in → out or flagged, reason,
   parameters) and its ledger columns. Thresholds are set low (sensitive) on purpose, so borderline
   cases reach the person who signs off; flags never drop (D-076).
2. **Data quality:** missingness, constant / near-constant, cardinality, type problems.
3. **Leakage screen** on train-split clients: near-perfect separators (the per-task statistic;
   binary: univariate AUC), dominance and missingness patterns. It flags and never drops; a human
   decides (§4.6).
4. **Automatic exclusion** of target-lineage columns (T12).
5. **Eligibility interaction:** flag features that are constant within the eligible population (T11).
6. **Stability** (§4.4, D-048):
   - per-month univariate AUC range and PSI across the window's months, on train-split clients;
     a per-month statistic is shown only for months with at least 50 positive events (D-082,
     D-091);
   - a separate stability measure for categoricals (T10);
   - label-free drift (PSI) of the window against the gap months between the window and the
     validation month, and against the latest available month (the one production will score);
   - never against the validation month: a feature dropped because it drifted there makes the
     validation result look better than production will be.
7. **Redundancy:** pairs with high correlation or VIF are flagged with both features' AUCs side by
   side, so a human can keep both. Nothing is dropped here.
8. **Output:** ledger columns; proposed decisions ready to record (in the config, or the decision audit log: OD-10); the log; an HTML
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
- Exact step catalogue and thresholds: set low (D-076), the same at every automation level (D-077).
- How decisions persist across reruns (config lifecycle, OD-10).
