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
3. **Leakage screen** on the window's eligible rows, every eligible client, labels included
   (D-030): near-perfect separators (the per-task statistic; binary: univariate AUC), dominance
   and missingness patterns, and a **time-alignment check**: a
   feature's power to predict the target forward vs to "predict" the same event backward, before
   the observation period, which catches columns shifted forward or built from the future (D-029).
   It flags and never drops; a human decides (§4.6).
4. **Automatic exclusion** of target-lineage columns (T12).
5. **Eligibility interaction:** flag features that are constant within the eligible population (T11).
6. **Stability** (§4.4, D-030):
   - per-period univariate AUC range and PSI across the window's periods, on every eligible client;
     a per-period statistic is shown only for periods with at least 50 positive events (D-082,
     D-091);
   - a separate stability measure for categoricals (T10);
   - label-free drift (PSI) of the window against the gap periods between the window and the
     validation period, and against the latest available period (the one production will score);
   - never against the validation period: a feature dropped because it drifted there makes the
     validation result look better than production will be.
7. **Redundancy:** pairs with high correlation or VIF are flagged with both features' AUCs side by
   side, so a human can keep both. Nothing is dropped here.
8. **Output:** ledger columns; proposed decisions ready to record in the decision audit log (D-125); the log; an HTML
   report; the periods it compared (the window's, the gap periods, the latest period), so a later
   change of the validation period to one of them is refused (D-088).

## Design constraints
- Reads the candidates. The model reads the resolved list ([feature ledger](feature_ledger.md) rules).
- Runs on the window's eligible rows (`build_frames(stage="feature_checks")`): every eligible
  client, labels included, no split yet; the modelling filters' rows are gone by here, and the
  train/test client split happens after this stage (D-030). Nothing here uses the validation
  period, and label-based checks never use periods after the window, by discipline: the panel
  carries labels wherever Target Factory could build them (D-131).

## Lessons from the crunch
T10, T11, T12. The AUC-floor heuristic and its standard error at few positives now belong to
automated selection in [training](training.md).

## Interface
*(fill when built)*

## Open questions
- The label-free reads of the gap periods and the latest period: the panel and the model input
  carry `target` in every period with a complete forward window (D-131), so Feature Checks must
  take those periods through a helper that drops the label and leaves out the validation period
  (`label_free_periods(panel, cfg)` in `frames.py`, built with the stage in M2.2, with a test that
  no `target` column and no validation row reaches it); the model results report states that
  the labels exist (D-030).
- The time-alignment screen also runs on the eligibility `define` columns and the modelling
  tags (T11; the ML audit of Stage 1's Target Factory), since eligibility SQL can select on the
  outcome outside the screens; on the eligible rows every modelling tag is 1, so this needs the
  window frame (M2.2 decides).
- With Feature Checks on the eligible rows, the `eligibility_constant` step (a feature constant
  within the eligible population, T11) sees the same rows as `quality` and may fold into it
  (M2.2 decides).
- Exact step catalogue and thresholds: set low (D-031), the same at every automation level (D-023).
- The core views of its report per task (OD-12).
