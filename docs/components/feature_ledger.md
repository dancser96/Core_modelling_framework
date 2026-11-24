# Feature ledger
**Status:** built (spec settled 2026-11-02; `ledger.py` built in Stage 2's m1.5, 2026-11-03; EDA writes the identity and EDA columns since 2026-11-04, Stage 2 major step 2; the identity column `source` and `ledger_schema_version` 2 since 2026-11-06; the sidecar's run tokens and `ledger_schema_version` 3 since 2026-11-10; Feature Checks writes its columns since 2026-11-06, major step 3; the per-run part specified 2026-11-13 and built 2026-11-16, M2.3 major step 2) · **Legacy:** none (the crunch had only `features_include` / `features_exclude`)
**Related:** [EDA](eda.md) · [feature checks](feature_checks.md) · [training](training.md) ·
[evaluation](evaluation.md) · [model bundle](model_bundle.md) (the run folder) · [config](config.md) (the
decision audit log) · [reporting](reporting.md) · D-030, D-031, D-043, D-125, D-134, D-135, D-136,
D-137, D-139, D-140 · settles OD-11

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
The feature ledger is **one wide table per data definition, one row per candidate**: the
per-feature view of the decision audit log plus every statistic EDA and Feature Checks computed
for that feature. It answers, for each candidate, what we started with, what each stage found and
what a person decided. **It decides nothing**: the statistics come from EDA's tables, the flags
from Feature Checks, the decisions from the audit log ([config](config.md#decision-audit-log-d-125),
D-125).

- **Where:** `<root>/<use_case>/04_feature/<data-definition hash>/ledger.parquet` plus
  `_ledger.json` (`ledger_schema_version: 3`, the data-definition hash and, per stage whose
  columns it holds, the run token also in that stage's json), beside the `eda/`,
  `feature_checks/` and `decisions/` folders (D-136).
- **Who writes:** EDA creates it (identity and EDA statistics); Feature Checks appends its columns.
  No stage rewrites another's columns.
- **Derived at render time, never stored:** `held`, `kept`, `excluded` and `verdict`, read from
  the resolved config (the audit log replayed: `features.held`, `excluded`, `kept`) whenever a
  report, the sign-off view or Training reads the ledger, so they can never go stale.
- **Who reads:** both Stage 2 reports, the notebooks (`StageResult.ledger`), Training (through
  `resolve_features`, the feature set it trains on), the sign-off view and the model card.
- **The per-run part** is a separate file per training run, `<use_case>/06_models/r007/ledger_run.parquet`:
  one row per feature that entered selection, with each rule's outcome, use in the model,
  importance, direction, the encoder's shares and the declared constraint. Training writes it
  once; it is the one record of automated drops.

This spec settles OD-11 (the ledger's shape).

## Level 2: How it fits together

### Relationships
- **EDA creates** the ledger for a data definition: one row per candidate with its identity
  columns and the ranking statistics ([EDA](eda.md) owns the statistics).
- **Feature Checks appends** its columns: the flags and notes it raised and the statistics behind
  them ([feature checks](feature_checks.md) owns the steps, the findings and the hold-out rule).
- **The audit log's entries give the decisions.** The ledger stores no decision; a person's
  `keep`, `exclude` and `include` and the framework's `flag` entries are joined in when the ledger
  is read (D-125, D-134).
- **Training's per-run part** is its own file in the run folder, `<use_case>/06_models/r007/`,
  joined on `feature`, so two training runs on one data definition share the Stage 2 file and
  never rewrite it. Training writes it once, before its `training/` folder; Evaluation never
  rewrites it and keeps its own per-feature numbers in a table under `evaluation/`.
- **The reports and the model card render it:** the EDA report's appendix shows the identity and
  EDA columns; the Feature Checks report's core shows every column with the decisions; the model
  card (M2.3/M2.4) summarises it ("held: n features with open flags"; [reporting](reporting.md)).
  The sign-off view, the model results report and the card read the per-run part beside the
  run's own copy of the Stage 2 rows.

### The file through a Stage 2 run and a rerun
1. EDA resolves the candidates, finds the lineage and unsupported columns, decides the kinds and
   calls `create_ledger`; it adds its ranking columns with `add_columns(..., stage="eda")`.
2. EDA saves it with `save_ledger` **before** it writes its `eda/` folder, so `eda.json` is the
   commit marker: a crash in between leaves a new ledger beside the old `eda.json`, which
   `read_ledger` refuses by its run token, never an old ledger beside a new `eda.json`. An EDA
   run starts from a fresh ledger, so **an EDA rerun removes Feature Checks' columns** (and EDA
   removes the `feature_checks/` folder).
3. Feature Checks reads `eda/` with `read_upstream` (refused when EDA's settings digest differs from
   the current resolved config's, or a source moved in the environment file) and the ledger with `read_ledger(folder, data_definition_hash,
   expect={"eda": <eda.json's run_token>})` (another data definition, or a ledger from another EDA
   run than `eda/`, is refused), refuses one without EDA's columns, runs its steps and adds its
   columns with `add_columns(..., stage="feature_checks")`, a skipped step's as null. A Feature
   Checks rerun replaces its own columns.
4. Feature Checks writes its `flag` entries to the audit log, renders its report, saves the
   ledger with the EDA run's token it read and its own, and writes its `feature_checks/` folder
   last, the same order as EDA.
5. A report, the notebook's review view or Training reads the ledger with `read_ledger` and calls
   `render_decisions` (the view; it takes the resolved config and the entries, for the entry
   numbers) or `resolve_features` (the feature set; it takes the resolved config).

### Functions in brief
`src/core_modelling/ledger.py`, one module:
- `create_ledger`, `add_columns`: build the table;
- `save_ledger`, `read_ledger`: the artifact, with its schema version and run tokens;
- `read_candidates`: the rows a step reads (neither lineage nor unsupported);
- `render_decisions`: the derived columns, for a view;
- `resolve_features`: Training's feature set.

The per-run part: `training/ledger_run.py` holds `build_run_ledger`, `save_run_ledger` and
`ledger_warnings`; `training/signoff.py` holds `signoff_table`, which reads it;
`run_artifacts.py` holds `read_run_ledger` and the constants Training and the readers share
(`LEDGER_RUN_SCHEMA_VERSION`, `LEDGER_RUN_FILE`, `SIDECAR_FILE`, `RULES`, `OUTCOMES`).

### How it is checked
Light tests (`CLAUDE.md` §7). The open-flag cases (an empty `flag` entry closes a finding; a
`keep` with `findings` settles those findings only; a different finding raised later holds the
feature again; the same finding with new values does not) are `open_flags`' in the audit-log
tests ([config](config.md)). `resolve_features` is tested against hand-built resolved configs
(lineage, unsupported, excluded and held out; a name that is no ledger row refused);
`add_columns` refuses another stage's column, a repeated feature and a read candidate left out;
a stage's rerun leaves none of its earlier columns; `save_ledger` refuses a derived column and an
incomplete meta, and a failed save keeps the previous ledger; another `ledger_schema_version`,
data definition or stage run token is refused; the list, nullable-int and bool columns survive
the parquet round trip unchanged. The per-run part: its columns and sidecar; a declared
constraint against EDA's direction marks the row and raises the warning, and so does a final
feature the final model never split on.

## Level 3: Details

### Requirements and design constraints
1. **One row per candidate per data definition**, keyed by `feature`, stored under the
   data-definition hash's folder. The candidates are the config's candidate list resolved
   against the input's columns; lineage and unsupported columns keep a row (identity columns
   only, statistics null).
2. **It decides nothing.** No ledger function writes an audit-log entry or changes the
   candidates; it records statistics and flags and derives the rest.
3. **Versioned per `CLAUDE.md` §2.** `_ledger.json` carries `ledger_schema_version` (2: the identity
   column `source`; 3: the run tokens), read before the parquet; another version is refused and EDA
   reruns (0.x; from 1.0 an older one is migrated). Columns are only added within a major version
   (D-007); in 0.x a column a reader needs bumps the version, everything else changes in place
   (D-136). From 1.0, readers keep or drop a column they do not know instead of refusing it, so a
   ledger written by a later patch still reads.
4. **Stages append, never rewrite.** `add_columns` refuses a column that belongs to another
   stage; a stage's rerun replaces only its own columns; an EDA rerun starts a new ledger.
5. **Derived columns are never stored.** `held`, `kept`, `excluded` and `verdict` exist only in
   `render_decisions`' output; `save_ledger` refuses a frame that holds them.
6. **The per-run part is separate:** Training never writes to the Stage 2 file, and nothing
   rewrites the per-run file once Training has written it ([below](#the-per-run-part)).
7. **Task-agnostic column names.** One column set for every task: `concordance`, never AUC (for a
   binary task it equals the AUC of the binned feature; the definition per task is
   [EDA](eda.md)'s); no column assumes a 0/1 target.
8. **The ledger computes no statistic.** Every number is copied from EDA's or Feature Checks'
   tables (`core_modelling/statistics/` computes them, D-135).
9. **Labels.** The EDA and Feature Checks columns are computed on every eligible client, labels
   included (D-030); Training's automated selection recomputes every label-using statistic it
   decides on, on the train split, including whether a numeric is judged on its best order
   ([training](training.md#selection)). Its rules read only the identity columns and the
   label-free `cluster` from these columns; EDA's `direction` and `non_monotone` mark reach the
   per-run ledger for display and the wrong-sign warning only.

### Columns
Types are pandas / parquet types; "list" is a parquet list column. Every statistic's definition,
period set and support rule is [EDA](eda.md)'s or [feature checks](feature_checks.md)'s; the
meanings below are one line each.

| Group | Column | Type | Written by | Meaning |
|---|---|---|---|---|
| Identity | `feature` | str | EDA | the candidate column's name (the key) |
| Identity | `kind` | str | EDA | `numeric`, `categorical` or `unsupported`, after `features.kinds` overrides |
| Identity | `source` | str | EDA | the source the column comes from (the frames' `meta["column_sources"]`, from the join entries' `columns`); every candidate has one, a lineage column of an upstream target may have none |
| Identity | `lineage` | bool | EDA | a target-lineage column, excluded automatically |
| Identity | `unsupported` | bool | EDA | an unsupported type (date, timestamp, array, map, struct, binary), excluded automatically |
| EDA | `levels` | int | EDA | distinct non-null values on the snapshot's eligible rows, before the level cap (counted from the rows, not the cells) |
| EDA | `concordance` | float | EDA | the snapshot's concordance with the target; a categorical's is cross-fitted and read in the encoding's direction, so it may read below 0.5 |
| EDA | `concordance_se` | float | EDA | its standard error |
| EDA | `direction` | str | EDA | `+`, `-`, or null below 0.5 + 2 SE; a categorical's is `+` when its concordance reaches 0.5 + 2 SE, else null |
| EDA | `concordance_best_order` | float | EDA | the concordance with the bins ordered by their shrunk target rate; the ranking uses it only for `non_monotone` features |
| EDA | `non_monotone` | bool | EDA | the best order beats the value order by ≥ max(0.03, 4 · SE) |
| EDA | `concordance_window` | float | EDA | the concordance over the window periods pooled |
| EDA | `missing_share`, `missing_share_window` | float | EDA | the null share (snapshot; window) |
| EDA | `null_concordance`, `null_concordance_window` | float | EDA | the null indicator's concordance (snapshot; window) |
| EDA | `zero_share`, `zero_share_window` | float | EDA | the share of zeros (snapshot; window) |
| EDA | `dominant_share`, `dominant_share_window` | float | EDA | the most frequent value's share, null counted as a value (snapshot; window) |
| EDA | `rank` | int | EDA | the position by the ranking value: `concordance`, or `concordance_best_order` for a `non_monotone` feature |
| EDA | `key_feature` | str | EDA | `top_n | listed | ''`: in the top N, or the person's `include` list, or neither |
| EDA | `represented_by` | str | EDA | the key feature it was skipped for (association above `eda.key_features.max_correlation`) |
| Checks | `flags` | list[str] | Feature Checks | the flags the latest run raised on the feature (open or settled), full names (`step.finding`) in the finding table's order; empty when none |
| Checks | `notes` | list[str] | Feature Checks | the notes the latest run raised, the same way |
| Checks | `lagged_concordance` | float | Feature Checks | the concordance of the value lagged one period |
| Checks | `signal_kept` | float | Feature Checks | the share of the signal (concordance − 0.5) kept when lagged one period |
| Checks | `constant_share` | float | Feature Checks | the share of clients whose value never changes in the window |
| Checks | `concordance_range` | float | Feature Checks | the range of the per-period concordances |
| Checks | `heterogeneity_p` | float | Feature Checks | Cochran's Q p-value across the window periods |
| Checks | `psi_window` | float | Feature Checks | PSI between the window's first and last period |
| Checks | `psi_latest` | float | Feature Checks | PSI between the window's last period and the latest period |
| Checks | `new_level_share` | float | Feature Checks | the latest period's share of levels unseen in the window |
| Checks | `cluster` | Int64 | Feature Checks | the redundancy cluster's number (null when alone) |
| Checks | `explained_by_others` | float | Feature Checks | the within-cluster R² on ranks over the Spearman members; null when a pair was not compared, for a non-numeric member, or when the correlations are inconsistent |
| Checks | `partners` | list[str] | Feature Checks | the features it is correlated or associated with above either threshold, strongest first |
| Derived | `held` | bool | `render_decisions` | an open flag holds it out of training: for Training, an excluded feature without a final decision |
| Derived | `kept` | list[int] | `render_decisions` | the numbers of the `keep` entries in force for it |
| Derived | `excluded` | int | `render_decisions` | the number of the `exclude` entry in force (the latest no `include` reversed), null when none |
| Derived | `verdict` | str | `render_decisions` | `pass`, `held`, `kept`, `excluded` or `auto_excluded` |

The columns Training needs are written now: `kind` and `levels` (the encoder), `cluster`
(grouped importance and a top-per-cluster rule, M2.3), `lineage` and `unsupported`.
Feature Checks writes every one of its columns on every run: a skipped step's are null (floats
NaN, `cluster` a null Int64, `partners` None), so readers always find the column set.

### How the derived columns are read
From the resolved config, where replay writes `features.held`, `features.excluded` and
`features.kept` from the effective entries (every `revert` applied, D-125, D-134), and from the
entries' numbers, up to the point being rendered:
- a finding is **open** on a feature when the latest `flag` entry for that finding names the
  feature (an empty `flag` entry closes the finding for every feature) and no effective `keep`
  entry names both the feature and that finding;
- `held`: at least one open flag and not excluded;
- `kept`: the effective `keep` entries naming the feature;
- `excluded`: the latest effective `exclude` from any writer that no later `include` reversed;
- `verdict`: `auto_excluded` (lineage or unsupported), else `excluded`, else `held`, else `kept`,
  else `pass`.

### Example rows (rendered with decisions)

| feature | kind | concordance | flags | notes | decisions (from the log) | verdict |
|---|---|---|---|---|---|---|
| `fwd_txn_3m` | numeric | — | — | — | lineage: excluded by the candidate resolution | `auto_excluded` |
| `open_date` | unsupported | — | — | — | unsupported type | `auto_excluded` |
| `flag_x` | categorical | 0.99 | `leakage.too_strong` | — | #6 exclude: "set after the offer" | `excluded` |
| `prod_code` | categorical | 0.63 | `quality.high_cardinality` | — | none yet | `held` |
| `tenure_m` | numeric | 0.64 | `time_alignment.client_constant` | — | #7 keep (`time_alignment.client_constant`): "static attribute, known at the period" | `kept` |
| `bal_3m` | numeric | 0.71 | — | `redundancy.correlated_pair` | — | `pass` |

`prod_code` stays a candidate, in every report and on the model card; Training runs without it
until a person records `keep` or `exclude`. `bal_3m`'s note never affects training; its
`partners` and `cluster` show the correlated `bal_6m`.

### Rules
The hold-out rule is [feature checks](feature_checks.md)'s (D-134); in short:
- **Flags hold out, never drop.** An open flag keeps a feature out of training at both
  automation levels; the feature stays a candidate and in the ledger, and one entry brings it
  back. Notes never affect training.
- **A person settles a flag** with `keep` (the finding is accepted; the feature returns to the
  next run and is protected from Training's automated pruning) or `exclude` (out of every later
  run); `include` reverses an `exclude`. Lineage and unsupported columns are automatic exclusions,
  never entries. Entries are recorded per group with one required reason (D-043, D-125).
- **The sign-off** is given over the model's final list after training, at every level (D-031);
  rejecting a feature there is an `exclude` entry and the model is retrained without it.
- **Automated decisions** are recorded in the per-run part with the rule that made them, never
  as audit-log entries; the config holds only the rule, so a rerun on unchanged data gives the
  same outcome (D-043).
- **Final features** = `resolve_features` (candidates − lineage − unsupported − excluded − held)
  minus Training's automated drops; a feature with a `keep` is never dropped automatically. The
  **feature signature** is the hash of the final list, and the model bundle freezes the list.

### The artifact
- `ledger.parquet`: the stored columns above (identity, EDA, checks); `flags`, `notes` and
  `partners` are parquet list columns.
- `_ledger.json`: `ledger_schema_version`, the framework version, when, the
  `data_definition_hash` (also the folder's name) and `runs`, `{stage: run_token}` for each stage
  whose columns the file holds, in stage order: `{"eda": …}` after EDA (its save starts afresh),
  `{"eda": …, "feature_checks": …}` after Feature Checks (the EDA run's it read and its own).
  Each token (`artifacts.new_run_token`, 12 hex characters) is the one the stage wrote as
  `run_token` into its `<stage>.json`.
- Both files are written to temporary names (removed when a write fails) and renamed, the
  sidecar first, so a crash never leaves half a ledger and one between the two renames
  leaves the new run's tokens beside the old table, which a reader refuses. The stage folder is written after the ledger, so the stage's
  json is the commit marker, and a reader passing the tokens of the stage jsons it read
  (`expect`) refuses a ledger from another run: Feature Checks passes EDA's, Training (M2.3) both.
- Size: one row per candidate and about 40 columns (the canonical synthetic data: about 150
  rows), far below pandas Styler's 262,144-cell render limit.
- Local paths only in Stage 2; the HDFS transport arrives in M2.4 for every artifact at once
  (D-136).

### The per-run part
`<use_case>/06_models/r007/ledger_run.parquet` with its sidecar, in the run folder ([model
bundle](model_bundle.md#the-run-folder)).
1. **One row per feature that entered selection** (Training's feature set from
   `resolve_features`), keyed by `feature` and joined to the run's own copy of the Stage 2 rows
   (`stage2/`). Held and excluded features have no row here; the sign-off view lists them from
   the Stage 2 rows and the audit log.
2. **Written by Training once,** by `build_run_ledger` and `save_run_ledger`, after the bundle and
   before `training/` (D-139 (a)). A second save into the same run folder is refused. Both files
   go to temporary names first, then are renamed, the parquet first and the sidecar last: the
   sidecar is what the reader looks for, so a crash between the renames leaves no readable
   ledger.
3. **The one record of automated drops:** no audit-log entry repeats them (D-125).
4. **Evaluation never rewrites it.** Its per-feature numbers (the test contribution shares, the
   unseen and null shares on test and validation) are a table of its own under `evaluation/`,
   joined when the report is drawn ([evaluation](evaluation.md)).
5. **The sidecar**, `_ledger_run.json`, holds `ledger_run_schema_version` (2),
   `framework_version`, `written_at`, `run_id`, `data_definition_hash` and `stage2` (the run
   tokens of the EDA and Feature Checks runs the run paired with); `read_run_ledger` refuses
   another version, as for the Stage 2 file.

| Group | Column | Type | Meaning |
|---|---|---|---|
| Identity | `feature` | str | the key |
| Selection | `selected` | bool | in the final list: no rule dropped it |
| Selection | `dropped_by` | str | `cluster`, `floor` or `prune`; null when selected |
| Selection | `cluster_value`, `cluster_threshold`, `cluster_outcome` | float, float, str | the cluster rule: the train concordance it ranked on, the representative's, the outcome |
| Selection | `floor_value`, `floor_threshold`, `floor_outcome` | float, float, str | the floor: the train concordance (best order for a numeric the train split shows as non-monotone, by EDA's rule), 0.5 + z · SE, the outcome; a feature that passed on its null indicator's concordance shows that one and its own 0.5 + z · SE |
| Selection | `floor_cleared_by` | str | the statistic that cleared the floor: `concordance`, `concordance_best_order` or `null_concordance` (the null indicator's); null when the floor dropped the feature or did not run |
| Selection | `prune_value`, `prune_threshold`, `prune_outcome` | float, float, str | pruning: the out-of-fold contribution share, the best noise column's, the outcome |
| Selection | `represents` | list[str] | the cluster members dropped in its favour; clusters only, never a floor drop |
| Selection | `protected` | bool | a person's `keep` in force: measured by every rule, dropped by none |
| Model | `in_model` | bool | used by the final model: at least one split, or gain above zero when `splits` is null; a final feature with false stays in the bundle's list and changes no score, and Training warns |
| Model | `splits`, `gain_share` | int, float | the split count and the share of the gain, from the family's `describe`; `splits` is null for CatBoost, whose `describe` gives no split counts |
| Model | `contribution_share`, `contribution_rank` | float, int | the share of the mean absolute out-of-fold contribution on train clients, and its rank |
| Model | `direction_model` | str | `+` or `-`: the sign of the rank correlation between the feature's values and its out-of-fold contributions; null for an unordered categorical or a constant |
| Model | `direction_agrees` | bool | the model's direction against EDA's `direction`, for a numeric only |
| Encoder | `levels_kept` | int | the levels the encoder kept (categoricals) |
| Encoder | `null_share`, `infinite_share`, `other_share` | float | on the train frame: nulls, values clipped to ±1e30, values coded `__other__` |
| Constraint | `monotone` | str | the declared constraint, `increasing` or `decreasing`; null when none |
| Constraint | `monotone_agrees` | bool | the declared sign against EDA's direction, for a numeric only: false when it is the opposite or EDA marked the feature `non_monotone` (the wrong-sign warning) |
| Train | `train_concordance` | float | the concordance with the target on the train split, direction taken out (`training/train_statistics.py`) |
| Train | `train_sign` | int | the raw sign of its direction there: 1, −1, or 0 when unavailable |

- The selection columns come from Training's long `selection` table (`training/tables/`; `feature,
  rule, value, threshold, outcome, represented_by, cleared_by`, one row per feature and rule;
  [training](training.md#what-training-writes)): per rule its value, threshold and outcome,
  `floor_cleared_by` (the floor row's `cleared_by`), `dropped_by` (the rule with a `dropped`
  row) and `represents` (the features whose `cluster` row is `dropped` with this one as
  `represented_by`). A `floor` row's `represented_by`, the member that carries a shared null
  pattern ([training](training.md#selection)), stays in the `selection` table and is not
  carried into `represents`. A `protected` or `undone` row is not a drop.
- An outcome is `passed`, `dropped`, `protected` (the rule would drop it; a `keep` holds it) or
  `undone` (pruning only: the decision's metric as a loss, out of fold and averaged over the
  folds, rose without the candidates, so nothing was pruned). A rule switched off,
  or one after the rule that dropped the feature, leaves its three columns null.
- `direction_agrees` and `monotone_agrees` compare with EDA's direction for a numeric only: a
  categorical's comes from a cross-fitted target encoding and reads `+` whenever there is
  signal, so it says nothing about the order of an ordered categorical. Both are null when there
  is nothing to compare (no EDA direction, a categorical, no constraint).
- A final model with a total gain or a total mean |contribution| of zero fails loud ("the final
  model made no split"): no feature would have a share.
- `train_concordance` and `train_sign` are there for Evaluation's single-feature baseline, which
  reads them also when a selection rule is switched off.
- The unseen share is zero on the train frame by construction; on test and validation it is
  Evaluation's.

### Code map
- `src/core_modelling/ledger.py`: the column lists as plain data (`COLUMNS_BY_STAGE`: `identity`,
  `eda`, `feature_checks`; `DERIVED_COLUMNS` apart), the seven functions below and
  `missing_stage2` (EDA and Feature Checks when they have not run on a data definition, which
  `run` reads at `autonomous` and Training's gate refuses on); the files go through
  `artifacts.py` (`write_parquet`, `read_parquet`, `write_json`). The callers:
  - EDA's stage function: `create_ledger`, `add_columns(..., "eda")`, `save_ledger`;
  - Feature Checks' stage function: `read_ledger(..., expect={"eda": …})`,
    `add_columns(..., "feature_checks")`, `save_ledger`, and `render_decisions` for its report and
    review view; its steps' `read_candidates`;
  - Training: `read_ledger(..., expect={"eda": …, "feature_checks": …})`, `resolve_features`;
    `training/ledger_run.py` for the per-run part (`read_run_ledger` and the constants it shares
    with the readers are `run_artifacts.py`'s).
- Reading order for review: `resolve_features` and `render_decisions` first (the hold-out lives
  there), then `add_columns`.

### Interface
One public function, `read_ledger`, promoted as it is in 0.3.0 for the helper notebook
`00_eda_fc_helper`, which reads the stored artifacts read-only
([architecture](../architecture.md#public-api)); otherwise the ledger is read through the
reports, `StageResult.ledger` in the notebooks and the versioned artifact. The interface, the
rest private:

```python
LEDGER_SCHEMA_VERSION = 3


def create_ledger(
    candidates: list[str],
    kinds: dict[str, str],
    lineage: list[str],
    unsupported: list[str],
    sources: dict[str, str],
) -> pd.DataFrame: ...
def add_columns(ledger: pd.DataFrame, columns: pd.DataFrame, stage: str) -> pd.DataFrame: ...
def save_ledger(ledger: pd.DataFrame, folder: str, meta: dict) -> None: ...
def read_ledger(
    folder: str, data_definition_hash: str | None = None, expect: dict[str, str] | None = None
) -> pd.DataFrame: ...
def read_candidates(ledger: pd.DataFrame) -> pd.DataFrame: ...
def render_decisions(
    ledger: pd.DataFrame, resolved: UseCaseConfig, entries: list[Entry]
) -> pd.DataFrame: ...
def resolve_features(ledger: pd.DataFrame, resolved: UseCaseConfig) -> list[str]: ...

# training/ledger_run.py, the per-run part (private)
def build_run_ledger(
    selection: pd.DataFrame,
    statistics: pd.DataFrame,
    description: dict,
    contributions: pd.DataFrame,
    values: pd.DataFrame,
    encoder: dict,
    encoder_shares: pd.DataFrame,
    monotone: dict[str, str],
    stage2: pd.DataFrame,
    kept: list[str],
) -> pd.DataFrame: ...
def ledger_warnings(run_ledger: pd.DataFrame) -> list[str]: ...
def save_run_ledger(ledger: pd.DataFrame, run_folder: str, meta: dict) -> None: ...

# run_artifacts.py, shared with every reader of a run (private)
LEDGER_RUN_SCHEMA_VERSION = 2
def read_run_ledger(run_folder: str) -> pd.DataFrame: ...
```

- `build_run_ledger` gives one row per feature of `encoder_shares` (the features that entered
  selection), in its order, with `LEDGER_RUN_COLUMNS`. `statistics` are the train-split
  statistics, `description` the final model's `describe`, `contributions` and `values` the
  out-of-fold contributions and encoded values of the final features on the train rows, `kept`
  the features with a `keep` in force. It refuses a selection table that does not fit the
  features (an unknown feature, rule, outcome or representative, a repeated feature and rule, two
  drops), model inputs that are not exactly the final list, and a feature the encoder or the
  train statistics lack.
- `ledger_warnings` gives the two warnings the ledger shows: a constraint against EDA's direction
  or its `non_monotone` mark (the constraint holds), and a final feature the final model never
  split on (it stays in the bundle's feature list and changes no score).
- `save_run_ledger` refuses columns other than `LEDGER_RUN_COLUMNS` in order, and a `meta` other
  than `run_id`, `data_definition_hash` and `stage2`. `read_run_ledger` refuses a missing sidecar
  and another `ledger_run_schema_version` before it reads the parquet.

- `create_ledger` writes the identity columns: an unsupported column's kind is `unsupported`, a
  lineage column EDA did not read may have none, every other candidate needs `numeric` or
  `categorical`; `source` comes from `sources` (column → source). It refuses a repeated
  candidate, a lineage or unsupported column that is no candidate, another kind, an unsupported
  column given a kind, and a candidate (not lineage) without a source, naming the features.
- `add_columns` (`stage` is `eda` or `feature_checks`) joins on `feature`, refuses a feature not in
  the ledger, a repeated feature, a read candidate (neither lineage nor unsupported) left out (a
  null value is fine) and a column outside the stage's list (naming its owner), and first drops
  every column the stage wrote before, so a rerun that skips a step leaves none of its earlier
  columns. The lineage and unsupported rows hold None in the stage's object and list columns, so
  the frame in memory equals the one read back.
- `save_ledger` refuses a derived column, a column no stage owns, a `meta` other than
  `data_definition_hash` and `runs`, and `runs` that do not name exactly the stages whose columns
  the ledger holds. A stage calls it before `write_stage`. `read_ledger` refuses another
  `ledger_schema_version`, a missing ledger ("run EDA first"), when `data_definition_hash` is
  given a ledger written for another one, naming both, and, per stage in `expect`, a sidecar
  token that is missing or differs ("the ledger and `<stage>/` come from different runs: rerun
  `<stage>`"). List columns read back as Python lists.
- `read_candidates` gives the rows a step reads, `~(lineage | unsupported)`, in the ledger's
  order.
- `render_decisions` adds `held`, `kept`, `excluded` and `verdict`; it refuses a config that was
  only loaded (`check_resolved`), a name in `features.excluded`, `held` or `kept` that is no
  ledger row (a mistyped entry is never ignored) and entries that do not end at the resolved
  config's `replayed_to` (pass the entries it was resolved from).
- `resolve_features` returns candidates − lineage − unsupported − excluded − held, in the
  ledger's order, and refuses a name that is no ledger row as `render_decisions` does, and a
  config that was only loaded (`check_resolved`: its held and excluded lists are empty until the
  replay fills them).

### Lessons from the crunch
None specific: the crunch had include and exclude lists only, which is why it could not say why a
feature was in or out.

## Open questions
- Readable labels per feature: not in Stage 2 (D-046).
