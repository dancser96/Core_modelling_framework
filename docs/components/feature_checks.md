# Feature Checks
**Status:** legacy-only (major rethink) · **Legacy:** `src/leakage.py`, `src/feature_stats.py` (`signal_persistence`), `notebooks/Feature_Checks.ipynb`
**Related:** [feature ledger](feature_ledger.md) · [EDA](eda.md) · [training](training.md) (automated selection) ·
[target factory](target_factory.md) (lineage) · [dataset](dataset.md) · D-023, D-028, D-029, D-030, D-031, D-050, D-088, D-125, D-132 · OD-12

## Purpose
The correctness and data-quality gate between candidates and model inputs. It is a standalone unit
with a stepwise, traceable log: each step states what it flagged or excluded and why, and writes it to
the feature ledger. Relevance-based selection is no longer here; it moved into Training, on the train
split only (D-028).

## Two automation levels
The checks are the same at both levels; only who decides differs (D-023; per decision point:
D-132).
- **`assisted`:** the stage ends in a review of its flags. People's decisions (exclude, or keep
  despite a flag, with reasons) are entries in the decision audit log that later runs replay, never
  config content (D-031, D-125, `config.md`). This review is not the sign-off.
- **`autonomous`:** the checks run and flag exactly the same way, and nothing waits for a person
  before training. Unresolved flags are listed on the model card and block registration until
  someone decides on them (D-031).

At both levels the **feature sign-off** follows, as one gate after training and before register: a
person must be able to defend every feature in the model, so a person signs off the model's final
feature list before any model is registered. Rejecting a feature then means a retrain. An LLM
review never passes this gate (D-031). The final list is shown with flags grouped and features
sorted by importance, with train-only model evidence; the candidate list (hundreds) is reviewed only
where flagged (D-031).

## Phase 2 requirements
1. Ordered, configured steps. Each writes a log entry (features in → out or flagged, reason,
   parameters) and its ledger columns. Thresholds are set low (sensitive) on purpose, so borderline
   cases reach the person who signs off; flags never drop (D-031).
2. **Data quality:** missingness, constant / near-constant, cardinality, type problems.
3. **Leakage screen** on every client in the window (D-030): near-perfect separators (the per-task statistic;
   binary: univariate AUC), dominance and missingness patterns, and a **time-alignment check**: a
   feature's power to predict the target forward vs to "predict" the same event backward, before
   the observation month, which catches columns shifted forward or built from the future (D-029).
   It flags and never drops; a human decides (§4.6).
4. **Automatic exclusion** of target-lineage columns (T12).
5. **Eligibility interaction:** flag features that are constant within the eligible population (T11).
6. **Stability** (§4.4, D-030):
   - per-month univariate AUC range and PSI across the window's months, on every client;
     a per-month statistic is shown only for months with at least 50 positive events (D-082,
     D-091);
   - a separate stability measure for categoricals (T10);
   - label-free drift (PSI) of the window against the gap months between the window and the
     validation month, and against the latest available month (the one production will score);
   - never against the validation month: a feature dropped because it drifted there makes the
     validation result look better than production will be.
7. **Redundancy:** pairs with high correlation or VIF are flagged with both features' AUCs side by
   side, so a human can keep both. Nothing is dropped here.
8. **Output:** ledger columns; proposed decisions ready to record in the decision audit log (D-125); the log; an HTML
   report; the months it compared (the window's, the gap months, the latest month), so a later
   change of the validation month to one of them is refused (D-088).

## Design constraints
- Reads the candidates. The model reads the resolved list ([feature ledger](feature_ledger.md) rules).
- Uses every client in the window, labels included; the train/test client split happens after
  this stage (D-030). Nothing here uses the validation month, and label-based checks never use
  months after the window.

## Lessons from the crunch
T10, T11, T12. The AUC-floor heuristic and its standard error at few positives now belong to
automated selection in [training](training.md).

## Interface
*(fill when built)*

## Open questions
- The time-alignment screen also runs on the eligibility `define` columns and the pre-model
  tags (T11; the ML audit of Stage 1's Target Factory), since eligibility SQL can select on the
  outcome outside the screens.
- Exact step catalogue and thresholds: set low (D-031), the same at every automation level (D-023).
- The core views of its report per task (OD-12).
