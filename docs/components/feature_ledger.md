# Feature ledger
**Status:** designing (sketch for review, OD-11) · **Legacy:** none (the crunch had only `features_include` / `features_exclude`)
**Related:** [EDA](eda.md) · [feature checks](feature_checks.md) · [training](training.md) ·
[evaluation](evaluation.md) · [config](config.md) · [reporting](reporting.md) · D-030, D-031, D-043, D-125 · OD-11

## Purpose
One table that answers, for every candidate feature: what we started with, what each step found,
what a human decided, what automated selection did, and what the model finally used. It gives
oversight of "initial vs selected features" while the config stays compact. Human decisions live
in the decision audit log ([config](config.md#decision-audit-log-d-125), D-125, amending D-043),
not in the config; the ledger holds the evidence and is the audit log read per feature. Each row
shows that feature's entries, e.g. "flagged #4 (rule), excluded #6 (person): set after the
offer".

## Sketch
- One row per candidate feature, per run lineage (data-definition hash + `run_id`).
- Each stage **appends** its own columns and never rewrites another stage's.
- It is stored as a table (parquet) with the run's artifacts, rendered in the Feature Checks report
  and summarised in the model card. The schema is versioned (`ledger_schema_version`, `CLAUDE.md`
  §2).

| Group | Columns (illustrative) | Written by |
|---|---|---|
| Identity | feature, kind (numeric / categorical), source column, readable label (optional) | load |
| EDA | missing %, distinct levels, univariate AUC and direction (the window's eligible rows, D-030), rank, key feature (top-N or user-listed) | EDA |
| Checks | one flag + value per check step (lineage, leakage, eligibility-constant, stability, redundancy with partner and both AUCs, data quality); checks verdict (pass / flagged / auto-excluded) | Feature Checks |
| Decision | human decision (keep / exclude), its group's reason, the entry numbers | the audit log entries the run replayed (D-125) |
| Selection | automated selection result, the rule that made it and its statistic (e.g. the univariate AUC behind the floor), all on the train split, never EDA's pre-split column (D-030) | Training |
| Use | in model (yes/no + why not), importance and rank, effect direction | Training, Evaluation |

**Example rows:**

| feature | univ. AUC | checks | human | automated selection | in model |
|---|---|---|---|---|---|
| bal_3m | 0.71 | flagged: corr 0.96 with bal_6m (AUC 0.70) | keep, both strong | protected by keep | yes |
| fwd_txn_3m | — | auto-excluded: target lineage | — | — | no |
| flag_x | 0.99 | flagged: near-perfect separator | exclude: post-outcome field | — | no |
| noise_1 | 0.50 | pass | — | dropped: below AUC floor (train) | no |

## Rules
- **Flags never drop.** A flagged feature stays in unless a human excludes it. At the `autonomous`
  level, unresolved flags are listed on the model card and block registration (D-031).
- **A person signs off the features** before any model is registered, at every automation level, in
  one gate after training over the model's final list (D-031). At the `assisted` level Feature
  Checks first ends in a review of its flags, whose keep / exclude decisions are audit-log entries;
  that review is not the sign-off. The sign-off is a `sign_off`
  entry in the audit log that names the run and the person (D-031, D-125). It is given over the
  model's final list, flags grouped, features sorted by importance, with train-only model evidence; the
  candidate list is reviewed only where flagged (D-031). If the sign-off rejects a
  feature, that is an `exclude` entry, and the model is retrained without it.
- **Human decisions go both ways.** They are audit-log entries the run replays, never config
  content; the config holds the candidates and the rules (D-043 (d), D-125). *Exclude* removes a
  feature that passed. *Keep* resolves a flag
  and protects the feature from automated pruning, e.g. keeping both of a highly correlated pair when
  both are strong. A person writes one entry per group, with one reason, which is required
  (D-043, D-125).
- **Automated decisions are recorded here** together with the rule that made them. The config holds
  only the rule, so a rerun on unchanged data gives the same outcome; the model bundle freezes the
  features it uses (D-043).
- **Final features** = candidates − lineage exclusions − human excludes − automated drops (features
  with a human *keep* are never dropped automatically). This list equals the resolved config's
  feature list, and its hash is the feature signature.

## Open questions
- Review this sketch (OD-11); not urgent, decided when the ledger is built (M2.2). Leaning: two
  parts, one per data definition keyed by the data-definition hash (EDA + checks) and one per run
  keyed by `run_id` (selection + use), joined on feature name; human decisions read at training
  time from the audit log entries the run replayed (D-125). The open issue:
  - EDA and Feature Checks write their columns before any `run_id` exists, and two training runs on
    the same data (e.g. two FLAML runs with different budgets) share them. One part per data
    definition and one per run?

  Human decisions copied in can't go stale: entries are append-only and each run records the
  entry it replayed up to (D-125).
