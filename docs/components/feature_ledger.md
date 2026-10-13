# Feature ledger
**Status:** designing (sketch for review, OD-11) · **Legacy:** none (the crunch had only `features_include` / `features_exclude`)
**Related:** [EDA](eda.md) · [feature checks](feature_checks.md) · [training](training.md) ·
[evaluation](evaluation.md) · [config](config.md) · [reporting](reporting.md) · D-043 · OD-10

## Purpose
One table that answers, for every candidate feature: what we started with, what each step found,
what a human decided, what automated selection did, and what the model finally used. It gives
oversight of "initial vs selected features" while the config stays compact. The config holds the
decisions; the ledger holds the evidence and the trail.

## Sketch
- One row per candidate feature, per run lineage (data-definition hash + `run_id`).
- Each stage **appends** its own columns and never rewrites another stage's.
- It is stored as a table (parquet) with the run's artifacts, rendered in the Feature Checks report
  and summarised in the model card. The schema is versioned (`ledger_schema_version`, `CLAUDE.md`
  §2).

| Group | Columns (illustrative) | Written by |
|---|---|---|
| Identity | feature, kind (numeric / categorical), source column, readable label (optional) | load |
| EDA | missing %, distinct levels, univariate AUC and direction (train-split clients in the window), rank, key feature (top-N or user-listed) | EDA |
| Checks | one flag + value per check step (lineage, leakage, eligibility-constant, stability, redundancy with partner and both AUCs, data quality); checks verdict (pass / flagged / auto-excluded) | Feature Checks |
| Decision | human decision (keep / exclude), reason, where it lives in the config | config, read by Checks |
| Selection | automated selection result and the rule that made it (train split only) | Training |
| Use | in model (yes/no + why not), importance and rank, effect direction | Training, Evaluation |

**Example rows:**

| feature | univ. AUC | checks | human | automated selection | in model |
|---|---|---|---|---|---|
| bal_3m | 0.71 | flagged: corr 0.96 with bal_6m (AUC 0.70) | keep, both strong | protected by keep | yes |
| fwd_txn_3m | — | auto-excluded: target lineage | — | — | no |
| flag_x | 0.99 | flagged: near-perfect separator | exclude: post-outcome field | — | no |
| noise_1 | 0.50 | pass | — | dropped: below AUC floor (train) | no |

## Rules
- **Flags never drop.** A flagged feature stays in unless a human excludes it. In hands-off profiles,
  unresolved flags are listed on the model card and block registration (D-031).
- **Human decisions go both ways.** *Exclude* removes a feature that passed. *Keep* resolves a flag
  and protects the feature from automated pruning, e.g. keeping both of a highly correlated pair when
  both are strong. Every human decision carries a reason.
- **Automated decisions are recorded here** together with the rule that made them. They are not
  written back into the config; how they persist across reruns is OD-10.
- **Final features** = candidates − lineage exclusions − human excludes − automated drops (features
  with a human *keep* are never dropped automatically). This list equals the frozen config's
  resolved feature list, and its hash is the feature signature.

## Open questions
- Review this sketch (OD-11). Two issues to fix there:
  - EDA and Feature Checks write their columns before any `run_id` exists, and two training runs on
    the same data (e.g. AutoML and predefined) share them. One part per data definition and one
    per run?
  - human decisions copied in when Feature Checks runs go stale if the config is edited later.
    Record them at training time, from the frozen config?
- Config lifecycle: how accepted automated decisions persist without multiple config versions
  (OD-10).
