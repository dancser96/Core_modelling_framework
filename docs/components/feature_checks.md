# Feature Checks
**Status:** designing (spec settled 2026-11-02; built in Stage 2, M2.2) · **Legacy:** `src/leakage.py`, `src/feature_stats.py` (`signal_persistence`), `notebooks/Feature_Checks.ipynb`
**Related:** [feature ledger](feature_ledger.md) · [EDA](eda.md) · [training](training.md) ·
[target factory](target_factory.md) (lineage) · [dataset](dataset.md) · [config](config.md) (the
audit log) · [reporting](reporting.md) · [lifecycle](lifecycle.md) (register) · D-023, D-028,
D-029, D-030, D-031, D-050, D-082, D-088, D-125, D-132, D-134, D-135, D-136, D-137 · OD-12 (its
Feature Checks part is settled by this spec)

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail. This doc owns the **hold-out rule** and the **finding table**; every other doc links
here for them.

## Level 1: Summary
**What it is.** The correctness and data-quality gate between the candidates and the model inputs
(D-028). It reads EDA's artifacts only (no Spark pass, no collect) and judges them in five steps,
in a fixed order: `quality`, `leakage`, `time_alignment`, `stability`, `redundancy`. Each step
returns **findings**: a **flag** ("should not enter a model as it is") or a **note** ("look at
this"). An open flag **holds the feature out of training at both automation levels** until a
person records `keep` or `exclude`; a note never affects training; nothing is dropped (D-134).

**In:** EDA's `eda.json`, counts, client-constant and correlation tables and the ledger,
for one data-definition hash. **Out:** ledger columns, the `findings` table, `flag` entries and a
`run` entry (the compared periods) in the audit log, the proposed decisions, a report, `StageResult`.

**Key numbers**, the same at both levels. Flags: all null; constant; one value ≥ 99%; ≥ 95% null; over
50 levels; concordance ≥ 0.80; null concordance ≥ 0.70; a rare value 5× the rest; < half the
signal kept when lagged; constant in ≥ 99% of clients with concordance ≥ 0.6; Cochran's p ≤ 0.01
with a range ≥ 0.05. Notes: ≥ 20% null and no zeros; null concordance ≥ 0.55; PSI ≥ 0.10; new
levels ≥ 1%; |association| ≥ 0.90.

**Run it:** `run_feature_checks(cfg, entity, env, spark)`, `python -m core_modelling run <config>
--stages eda feature_checks` or notebook `03_feature_checks.ipynb`; settle flags with
`record_decision(..., keep=[...], findings=[...])` or `decide --keep … --findings …`.

## Level 2: How it fits together

### What drives what
- **EDA computes, Feature Checks judges.** Every number a step reads is an EDA ledger column or a
  function of EDA's cells computed with `statistics/` (the lagged and per-period concordances,
  Cochran's Q, PSI, new levels). Feature Checks bins, ranks and collects nothing itself, so its
  numbers and EDA's differ by data, never by method (D-135). It refuses to run without EDA's
  artifact for the same data-definition hash, or when EDA's settings digest differs from the
  current resolved config.
- **The config sets the thresholds**: one typed mapping per step under `feature_checks:`, each
  threshold a loggable leaf, identical at both levels (D-132).
- **The audit log carries the flags and the decisions** (D-125). Feature Checks writes `flag`
  entries and one stage `run` entry; a person writes `keep`, `exclude` and `include`. Storage and
  replay: [config](config.md#decision-audit-log-d-125).
- **The ledger shows them.** It stores the statistics and the flags the latest run raised on the feature (open or settled; which are open is derived); `held`, `kept`,
  `excluded` and `verdict` are derived from the resolved config (replay writes the open flags'
  features into `features.held`, the person's decisions into `features.excluded` and
  `features.kept`) and the entries' numbers whenever a report, the sign-off view or Training
  reads it, never stored ([feature ledger](feature_ledger.md)).
- **Training's feature set** = candidates − lineage − unsupported − excluded − held
  (`resolve_features`). Lineage and unsupported types are automatic exclusions, never findings.
- **The two levels differ only in when the review happens** (D-132 (3)). `assisted` ends Feature
  Checks with the review of the proposed decisions; `autonomous` trains at once without the held
  features. Both reach the one feature sign-off after training (D-031).
- **`register` needs the sign-off and no open flag on a feature of the model's final list**, which
  holds none by construction; held features may stay held, undecided ([lifecycle](lifecycle.md)).

### How one run flows
1. Resolve the config: the config plus the audit log replayed (D-125); an unknown
   `feature_checks` parameter fails at load.
2. Read `eda/` and the ledger for the data-definition hash; refuse, naming `run_eda`, on a missing
   artifact or a settings-digest mismatch.
3. Run the five steps in their fixed order over the ledger's EDA columns and EDA's tables; a step
   left out of a present `feature_checks` mapping is skipped and the report says so.
4. Stack their findings into one `findings` table.
5. Write to the audit log: per finding, a `flag` entry when its flagged feature set differs from
   that finding's latest entry (an empty set closes it); then one stage `run` entry with the
   `periods` it compared.
6. Read the open flags from the log, the new entries included, and build the proposed decisions.
7. Append Feature Checks' columns to the ledger.
8. Write the artifacts to a temporary folder, renamed to `feature_checks/` on success.
9. Write the report and return the `StageResult`.

### Function structure
- `feature_checks/steps.py`: the `STEPS` dict (name → function, in run order) and the five step
  functions, each `(ledger, tables, params, task) -> findings`.
- `feature_checks/decisions.py`: `flag_entries` (which entries this run writes) and
  `proposed_decisions` (the review view).
- `feature_checks/run.py`: `run_feature_checks`, the stage function.
- It imports `statistics/` (every calculation), `ledger.py` (read, append, `resolve_features`),
  `artifacts.py` (EDA's artifact, the digest check, the temporary folder), `reporting/` (the
  writer, charts, the choices block) and `config` (the entry writer, `open_flags`,
  `held_features`).

### How it is checked
- **The hold-out:** `resolve_features` leaves held features out and takes them back after a
  `keep`; an empty `flag` entry closes a finding; a `keep` settles only the findings it names, a
  different finding raised later opens again, the same finding with new values does not.
- **The artifacts:** the digest refusal; the temporary folder; a rerun on unchanged data writes no
  `flag` entry.
- **The trap acceptance test** on the `dev` preset (D-064, D-137): each synthetic trap kind maps to
  the step that must catch it, an explicit `NOT_CHECKS` dict lists the kinds out of scope with a
  reason, and any kind in neither fails the test (details below).

## Level 3: Details

### Requirements and design constraints
1. **A gate, not a selector.** Correctness and data quality only (D-028); nothing here prunes by
   relevance.
2. **EDA's artifacts only.** No Spark pass, no collect, no binning; a missing EDA artifact or a
   settings-digest mismatch is refused, naming `run_eda` (D-031, D-135).
3. **Five steps in a fixed order** (`quality`, `leakage`, `time_alignment`, `stability`,
   `redundancy`); each is a function of the ledger and EDA's tables that returns findings and
   changes nothing else. Leaving a step out of a present `feature_checks` mapping skips it; the
   section left out runs every step with its defaults.
4. **Screens flag** (`CLAUDE.md` §4.6, as worded by D-134): "Screens flag; a flag never removes a
   feature from the candidates: it holds the feature out of training until a person keeps or
   excludes it." Testable: `resolve_features` returns candidates − lineage − unsupported −
   excluded − held, and a held feature is still a ledger row and a candidate.
5. **Thresholds are the same at both levels** (D-132); every threshold is a loggable leaf with its
   default explained in `TEMPLATE.yml`; an unknown parameter fails at load.
6. **Population** (`CLAUDE.md` §4.4, D-030): every eligible client of the window, labels included,
   before the client split; the person's decisions here have therefore seen test labels, which
   the model results report states. **Nothing reads the validation period**: it is never a
   compared period, and outside the window EDA drops the label before any aggregation.
7. **Automatic exclusions are not findings:** target lineage (`CLAUDE.md` §4.6, T12) and
   unsupported types never reach a step.
8. **Task-agnostic** (D-050): every task-specific choice (support, standard error, rare-value
   effect) comes from the per-task spec; the findings table has one shape for every task.
9. **Idempotent:** a rerun on unchanged data and config writes no `flag` entry; a changed
   threshold writes the new feature sets.
10. **Notes are never entries;** the ledger never stores a decision.
11. **The compared periods are a `run` entry,** and `set time.validation_period` to any period a
    run entry lists is refused (D-088).
12. **The report opens with what was chosen** (D-032): the thresholds per step, the skipped steps,
    the compared periods.

### The two automation levels and the review
- **The checks are identical at both levels** (D-023, D-132): the same steps, thresholds and
  findings. Only the review's timing differs.
- **`assisted`:** the stage ends in the flag review. Notebook 03 shows the proposed decisions
  grouped by finding with the call text to record them; the person records `keep` or `exclude`
  entries, then trains. This review is not the sign-off.
- **`autonomous`:** EDA and Feature Checks run automatically before training (D-031) and Training
  starts at once without the held features. The held features are listed in Training's log, the
  sign-off view and the model card ("held: n features with open flags").
- **The feature sign-off** follows at both levels: one gate after training and before `register`;
  a person must be able to defend every feature in the model, so a person signs off the model's
  final list (flags grouped, features sorted by importance, train-only evidence); an LLM never
  passes it (D-031). Rejecting a feature then is an `exclude` with stage `sign_off` and a retrain.
- **`register`'s rule:** the sign-off and no open flag on a feature of the final list. Held
  features may stay held and undecided: forcing an entry for every held feature (a dozen PSI-level
  questions on features the model never used) would be rubber-stamping, which D-031 avoids.
- **What "sensitive thresholds" mean now** (D-031): the `autonomous` model is the conservative one,
  with fewer features; a person brings features back, never the other way round.

### Inputs: what EDA provides
All under `<use_case>/04_feature/<ddh>/` (D-136); the columns and how each statistic is computed
are owned by [EDA](eda.md) and the [feature ledger](feature_ledger.md).
- **`eda.json`:** the hashes, `replayed_to`, the settings digest (`features.kinds`, `strata.*`,
  `eda.*`), the snapshot period, the compared periods, the population counts per period.
- **The ledger's EDA columns:** `kind`, `levels`, `lineage`, `unsupported`, `concordance`,
  `concordance_se`, `direction`, `concordance_best_order`, `non_monotone`, and the window twins
  the findings cite: `concordance_window`, `missing_share_window`, `null_concordance_window`,
  `zero_share_window`, `dominant_share_window`.
- **`tables/cells`, the counts table:** one row per feature, period, bin and target bin (`lagged`,
  `bin_order`, `is_null`, `n`, `sum_y`); Feature Checks reads the window periods' cells, the
  latest period's, and the lagged cells.
- **`tables/client_constant`:** `feature, constant_share, clients`.
- **`tables/correlation`** (`a, b, statistic, method, rows`, method `spearman | cramers_v | eta`);
  the redundancy step cuts the clusters from it and writes its own `tables/clusters`.
- **The digest check:** Feature Checks recomputes the digest of `features.kinds`, `strata.*` and
  `eda.*` from the current resolved config and refuses on a difference. An EDA run removes
  `feature_checks/` and Feature Checks' ledger columns, so a stale judgement cannot survive it.

### The finding table
Every finding is one row of `findings`: `feature, step, finding, kind (flag | note), value,
threshold, text`. "Window" means the window periods' cells pooled (the `*_window` ledger columns).
A concordance per period or lagged is taken in the window's direction, so a flip reads below 0.5.
Every default and its one-line text below is also a template leaf (D-137). How each statistic is
computed: [EDA](eda.md); the support rules (`strata.min_events` in events for binary, in units with
a non-zero target for regression; `MIN_BIN_SUPPORT = 20`): the same.

#### `quality`
The first four are exclusive, in this order: a feature gets the first that applies, so an all-null
column is not also constant or high-missing. `high_cardinality` and the two notes apply
independently.
- **`all_null`** · flag · no parameter. `missing_share_window = 1`. "Every value is null." Catches
  the `all_null` trap and T11's dead columns under an eligibility.
- **`constant`** · flag · no parameter. One value only, null counted as a value (so a 1/null column
  is not constant: its null indicator carries its signal). "One value only." Catches the two
  `constant` traps and `eligibility_defining` (columns fixed by the eligibility, T11).
- **`high_missing`** · flag · `missing_share_max: 0.95`. `missing_share_window ≥ 0.95`. "At least
  95% null." Catches the two `low_fill` traps (1% and 0.3% filled).
- **`near_constant`** · flag · `dominant_share_max: 0.99`. `dominant_share_window ≥ 0.99`, null
  counted as a value. "One value covers at least 99% of rows." Catches `near_constant` (99.9%
  zeros).
- **`high_cardinality`** · flag · `max_levels: 50`. A categorical with `levels > 50` (the ledger's
  distinct non-null levels, counted on the snapshot before the counts table's 50-level cap).
  "Codes or free text? Held until a person confirms the levels are meaningful." Catches the
  300-level code; `nationality` (64 levels) is flagged too, for a person to settle once.
- **`nulls_may_be_zeros`** · note · `nulls_may_be_zeros: {missing_min: 0.2, zero_share_max: 0.005}`.
  A numeric with `missing_share_window ≥ 0.2` and a zero share among its non-null values ≤ 0.005.
  "Many nulls and never a zero: if a null means 0 here, fill it upstream (D-029 (c)); the
  framework never imputes."
- **`nulls_informative`** · note · `nulls_informative_min: 0.55`. `0.55 ≤
  null_concordance_window < leakage.null_concordance_max`, with at least 20 null and 20 non-null
  rows. "Whether the value is filled carries information; keep the nulls as their own group; a
  family that imputes must impute outside the value range, never the median."

#### `leakage`
- **`too_strong`** · flag · `concordance_max: 0.80`. `concordance_window ≥ 0.80`. "A single feature
  this strong is usually the target under another name or a consequence of it." Why 0.80: the
  oracle's ceiling for card acquisition with every feature is 0.84. Catches `leak` (0.97, 0.87) and
  `upstream_target` (1.0).
- **`missingness_leak`** · flag · `null_concordance_max: 0.70`. `null_concordance_window ≥ 0.70`,
  with at least 20 null and 20 non-null rows. "Whether the value is filled predicts the target
  this strongly: ask how and when the field gets filled." Catches `missing_leak` (0.89);
  legitimate informative missingness scores about 0.52–0.58.
- **`rare_value_leak`** · flag · `rare_effect_max: 5`. A rare cell (a level, a discrete value or a
  bin; not the null bin) with a window share below 1% and at least `MIN_BIN_SUPPORT` rows whose
  `rare_effect` against the rest of the non-null rows is ≥ 5 (binary: the rate ratio; regression:
  the mean ratio). "A rare value with a target rate 5× the rest: a code set after the outcome?"
  Catches `process_leak` (98.7% zeros; the non-zero rows convert at about 80%).
- **Known limit:** the time-alignment screen on the eligibility `define` columns and the modelling
  tags (T11) is not in Stage 2; on the eligible rows every tag is 1, so it needs a design of its
  own (M4).

#### `time_alignment`
Both findings look only at features with `concordance_window ≥ concordance_min`: without signal
there is nothing to lose or to stamp.
- **`lagged_signal_drop`** · flag · `signal_kept_min: 0.5`. `signal_kept = (lagged_concordance − 0.5) /
  (concordance_window − 0.5) < 0.5`, the lagged concordance read from the window's lagged cells
  (each row's value one period earlier against its current target). "The feature loses more than
  half its signal when lagged one period: its value may be stamped after the period." Catches
  `shifted` (next month's value; lagged once it is the legitimate current value, whose signal
  collapses). A slow legitimate feature keeps nearly all its signal; a fast one may be flagged and
  kept. This replaces D-029 (d)'s forward-vs-backward comparison.
- **`client_constant`** · flag · `constant_clients_min: 0.99`, `concordance_min: 0.6`.
  `constant_share ≥ 0.99` and `concordance_window ≥ 0.6`. "Constant within the client across the
  window and predictive: a static attribute, or one date's value stamped onto every period."
  Catches `lookahead` (`holding_cnt_trap_lookahead`, 0.81, which the lag check cannot see). Static
  legitimate attributes with signal are flagged once and kept.

#### `stability`
- **`concordance_unstable`** · flag · `heterogeneity_p_max: 0.01` and `concordance_range_min:
  0.05`. Over every window period with support ≥ `strata.min_events`: weights `w_i = 1/SE_i²`
  (Hanley–McNeil in events; regression: Kendall's null SE, halved; D-082), the pooled `c̄ = Σ w_i
  c_i / Σ w_i`, `Q = Σ w_i (c_i − c̄)²`, `p = 1 − χ²_{k−1}(Q)`. Flag when `p ≤ 0.01` and the range
  `max c_i − min c_i ≥ 0.05` (`heterogeneity_p`, `concordance_range`). Guards: fewer than two
  supported periods → not tested, shown as such; a concordance of 1 → the SE floor. "The
  feature's power differs across the window's periods." Catches a signal present in one period
  only or a flipped direction; the effect-size condition stops a large sample from flagging
  everything.
- **`psi_window`** · note · `psi_max: 0.10`. PSI(the window's first period, the window's last
  period) ≥ 0.10. "The distribution moved while the model's data was collected."
- **`psi_latest`** · note · `psi_max: 0.10`. PSI(the window's last period, the latest period) ≥ 0.10,
  whatever `eda.snapshot` says, so the note means the same thing in every run: the most recent
  period the model's data comes from against the most recent data there is. "Production will
  score a different distribution: expect Monitoring to see it." Catches `drift` (the login
  roll-ups after the app relaunch).
- **`new_levels`** · note · `new_level_share_max: 0.01`. The share, in the latest period, of the
  levels unseen in any window period ≥ 0.01. "Levels unseen in the window cover more than 1% of the
  latest rows."
- PSI: ten bins merged from the cells on the snapshot's quantile edges plus the null bin;
  categoricals on the window's levels with `__other__`; each share floored at 1e-4; the Lewis bands
  0.10 / 0.25 are labels, not tests. Drift is a note because it is Monitoring's concern: a flag at
  0.10 would hold every trending legitimate feature out of an `autonomous` model.

#### `redundancy`
- **`correlated_pair`** · note · `correlation_max: 0.90`. A numeric pair with |Spearman| ≥ 0.90.
- **`associated_pair`** · note · `association_max: 0.90`. A pair with a categorical member and
  Cramér's V or η ≥ 0.90.
- Text: "Near-duplicates; the cluster table shows which carries the signal." Catches `redundant`
  (0.99997 with `relationship_days`) and `collinearity`.
- **Shown as clusters:** average linkage on 1 − |association|, cut at 1 − `correlation_max`; per
  cluster the members sorted by concordance, each with |association| with the best member and
  `explained_by_others` (the within-cluster R² on ranks, computed from the correlation table as the
  multiple correlation of the member with the other members: the correlation submatrix solved
  with a small ridge, so an exact identity reads 1; a VIF without imputation and without rows). A
  pair with
  fewer than 1,000 shared non-null rows is "not compared" and never linked. The report never
  suggests dropping either of two strong features: boosted trees lose little accuracy to
  collinearity but split their importance, so a person decides.

### Nulls
The framework never fills a null (D-029 (c)); the full register lives in [EDA](eda.md). The rules
Feature Checks relies on:
- **N4** Shares are over all eligible rows of the periods: `missing_share` = null rows / rows;
  `dominant_share` and `constant` count null as a value, so one value plus nulls is not constant,
  one value and no nulls is `constant`, every value null is `all_null`.
- **N5** Null is its own bin for every feature: PSI includes it, and a null share that appears in
  the latest period but in no window period counts towards `new_levels` (a field stopped being
  filled). Status: assumption, open to the SDS's veto.
- **N6** Every concordance (window, per period, lagged) is on the feature's non-null rows and its
  support counts those rows only; the nulls' own signal is `null_concordance`.
- **N11** A lagged value is null when the client has no row in the previous period or that value
  was null; both mean "no lagged value", such rows are out of the lagged concordance, and their
  share is shown with `lagged_signal_drop`. Status: assumption.
- **N12** `client_constant` ignores nulls (Spark's `min` and `max`): a client whose non-null values
  are all equal counts as constant, whatever nulls lie between them; the denominator is the
  clients with at least two non-null values. Status: assumption.
- **N15** `nulls_may_be_zeros`: missing share (over all rows) ≥ 0.2 and zero share among the
  non-null values ≤ 0.005; `nulls_informative`: 0.55 ≤ null concordance < 0.70 with ≥ 20 nulls and
  ≥ 20 non-nulls; `missingness_leak`: null concordance ≥ 0.70.
- **N18** No row is ever dropped for a null; `high_missing` is a flag like any other.

### Flags act: the hold-out
- **Flag or note.** A flag says "this feature should not enter a model as it is"; a note says
  "look at this" and never affects training. The kind of each finding is fixed in the finding
  table, the same at both levels (D-134).
- **Held.** A feature with an open flag is held: out of training at both levels, still a candidate,
  still in the ledger, every report, Training's log, the sign-off view and the model card. In
  effect, for Training, a held feature is an excluded feature without a final decision: the model
  is built without it until a person keeps or excludes it. The report, Training's log, the
  ledger's `held` column and notebook 03's guide say so in those words (the SDS, 2026-11-03).
- **Settling a flag.**
  - `keep`: the finding is accepted; the feature returns to the next training run and is
    protected from Training's automated pruning. The entry carries `findings`, the flags it
    settles; when the call names none, the writer fills in every flag open on those features at
    that moment, so the stored entry is explicit. A different finding raised later opens again;
    the same finding with new values does not.
  - `exclude`: the person's decision; the feature is out of every later run.
  - `include`: reverses a person's `exclude`; a flag still open on the feature holds it again.
  - Each is one entry per group of features with one reason (D-125).
- **Log mechanics** (A19–A21 of the record):
  - Feature Checks writes one `flag` entry per finding per run (`by: {kind: stage, id:
    feature_checks}`, `finding: "<step>.<finding>"`, the features, the finding's text as the
    reason), only when the finding's feature set differs from its latest entry.
  - An empty feature set is allowed for `flag` only and closes the finding: a column fixed upstream
    is released by the next run. A finding with no earlier entry and no features writes nothing.
  - A skipped step writes nothing, so its earlier flags stay as the log has them.
  - Notes are never entries: they live in the `findings` table.
  - No lineage entry: the candidate resolution drops the lineage, and the ledger's `lineage`
    column comes from it.
  - The ledger stores statistics and the flags the latest run raised on the feature (open or settled; which are open is derived); `held`, `kept` (with the entry
    numbers), `excluded` and `verdict` (`pass | held | kept | excluded | auto_excluded`) are
    derived from the resolved config at read time, because a stored verdict is stale the moment a
    person records an entry.
- **`open_flags(entries)`** (in `config/replay.py`): over the effective entries (every `revert`
  applied), per feature, the findings whose latest `flag` entry names the feature and which no
  `keep` naming that feature and finding settles; excluded features are excluded, not held.
  `held_features(entries)` is its keys, and replay writes it into the resolved config as
  `features.held` (refused in a config file, like `excluded` and `kept`), so the run's
  resolved-input hash sees the held set. **`resolve_features(ledger, resolved)`** (in `ledger.py`)
  reads `features.excluded` and `features.held` from the resolved config and gives Training's
  feature set: candidates − lineage − unsupported − excluded − held.
- **Proposed decisions** (the review view; `tables/proposed_decisions`): one row per open flag
  finding with its features, their values, the threshold, the finding's text and two call texts
  to copy, the verb left to the person (no suggested verb):
  `record_decision(CONFIG, entity="…", keep=[…], findings=["<step>.<finding>"], reason="<why>")`
  and `record_decision(CONFIG, entity="…", exclude=[…], reason="<why>")`. `CONFIG` is the
  placeholder notebook 03's setup cell defines. A feature with two open flags appears in both
  rows; keeping it in one settles only that finding.

A `flag` entry as stored (fields as in [config](config.md#one-entry)):
```json
{"seq": 4, "by": {"kind": "stage", "id": "feature_checks"}, "stage": "feature_checks",
 "op": "flag", "finding": "leakage.too_strong",
 "features": ["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
 "reason": "concordance ≥ 0.80: usually the target under another name",
 "evidence": ["feature_checks report: leakage"], "data_definition_hash": "d_A",
 "log_schema_version": 1}
```

### The compared periods
- **Which periods** (EDA's `Frames.rows`, [dataset](dataset.md)): every window period, the gap
  periods between the window and the validation period, and the latest period the data holds;
  never the validation period. Outside the window the label was dropped before EDA aggregated
  (D-030). With `time.validation_period: null` there is no gap: the window and the latest period.
  The latest period is included only when it lies after the validation period
  ([dataset](dataset.md)); when there is none, `psi_latest` and `new_levels` are shown as "not
  available: no period after the validation period" (decided up front, D-035), never computed
  against a window period.
- **What uses which:**
  - `concordance_unstable`: every window period with support (labelled);
  - `lagged_signal_drop`: the window's lagged cells;
  - `psi_window`: the window's first and last periods; `psi_latest`: the window's last period and
    the latest period; `new_levels`: the latest period against every window period (label-free);
  - the per-period table (`tables/per_period`): every compared period against the snapshot (PSI,
    missing share, concordance where labelled), shown for every candidate as information.
- **The `run` entry:** one stage `run` entry per run (`by: {kind: stage, id: feature_checks}`, its
  `replayed_to` and resolved-input hash) with a `periods` field listing every compared period.
  `set time.validation_period` to any period a run entry lists, reverted or not, is refused
  (D-088): a validation period whose drift was looked at would make the validation result look
  better than production will be.

### The report
Standalone, beside its artifacts (`feature_checks/report.html`); the writer, the chart rules and
the `CHOICES` table are [reporting](reporting.md)'s. Pre-aggregated figures only, plotly.js once.
1. **Summary:** EDA's headline numbers; the choices block (the level, the thresholds per step with
   their template text, the skipped steps, the compared periods); the flags and notes per step
   (counts and features); the held features.
2. **Core:** the findings per step in run order, each with its value and threshold; the proposed
   decisions; the ledger with the derived decisions (held, kept, excluded, verdict).
3. **Extended:** the per-period table for every candidate; the redundancy clusters for every
   candidate in one.
4. **Appendix:** the resolved config with each entry-written value's origin, the entries this run
   wrote, timings, the how-to-read notes (concordance in two sentences).

### Trap acceptance test
On the `dev` preset (20,000 clients), asserting on the window statistics; only `client_constant`
for the look-ahead trap (its 0.81 sits too close to 0.80 to assert `too_strong`); no per-period
finding on the term-deposit config (about 35 events per period); the D-088 counts from `eda.json`.
The scope (owned with [test harness](test_harness.md)):

| Step | Trap kinds it must catch |
|---|---|
| `quality` | `constant`, `near_constant`, `all_null`, `low_fill`, `high_cardinality`, `eligibility_defining` |
| `leakage` | `leak`, `missing_leak`, `process_leak`, `upstream_target` |
| `time_alignment` | `shifted` (`lagged_signal_drop`), `lookahead` (`client_constant`) |
| `stability` | `drift` (`psi_latest`) |
| `redundancy` | `redundant`, `collinearity` |
| kinds (EDA) | `decimal_type` read as numeric |

The mapping is keyed by trap kind **and** target: rows whose target is one of the run configs'
(card, term deposit, "any product") are mapped; rows with another target (the personal loan's
`inverted_u`, `rare_level`, `hidden_openings` and its `eligibility_defining`) go to `NOT_CHECKS`
with the reason "no config: loan target". `NOT_CHECKS` maps every other kind to its reason ("an
EDA view", "no config", "off by default"), so a trap kind added later fails the test until it is
placed. False-positive bound: on the `dev` preset's card config at most two non-trap candidates
may be held, named in the failure message, so `concordance_unstable` and the other flags are
checked against legitimate features too.

### Code map
Planned layout; final names in the plan.
- `core_modelling/feature_checks/`
  - `steps.py`: the five checks, one job each.
    - `STEPS = {"quality": check_quality, "leakage": check_leakage, "time_alignment":
      check_time_alignment, "stability": check_stability, "redundancy": check_redundancy}`, the
      dict order being the run order.
    - `check_quality(ledger: pd.DataFrame, tables: dict[str, pd.DataFrame], params:
      QualityParams, task: str) -> pd.DataFrame`, and likewise `check_leakage`,
      `check_time_alignment`, `check_stability`, `check_redundancy`, each with its step's
      Pydantic parameter model; each returns findings rows.
  - `decisions.py`: from findings to the log and the review.
    - `flag_entries(findings: pd.DataFrame, entries: list[Entry]) -> list[dict]`: the `flag`
      entries this run writes (changed sets only; empty sets close).
    - `proposed_decisions(findings: pd.DataFrame, open_flags: dict[str, list[str]], entity: str)
      -> pd.DataFrame`.
  - `run.py`: `run_feature_checks(cfg, entity, env, spark) -> StageResult`.
- `core_modelling/config/replay.py`: `open_flags(entries: list[Entry]) -> dict[str, list[str]]`,
  `held_features(entries: list[Entry]) -> list[str]`.
- `core_modelling/ledger.py`: `resolve_features(ledger: pd.DataFrame, resolved: UseCaseConfig) ->
  list[str]`; reading and appending columns ([feature ledger](feature_ledger.md)).
- `core_modelling/statistics/`: `pool_periods`, `two_way_table`, `concordance_from_table`,
  `concordance_se`, `cochran_q`, `merge_to_deciles`, `psi`, `new_level_share` ([EDA](eda.md)).
- `core_modelling/artifacts.py`: EDA's artifact read, the digest check, the temporary folder.

**Call flow of one run:** `run_feature_checks` → resolve the config → `artifacts` reads `eda/` and
checks the digest → `STEPS` in order → `flag_entries` → the audit-log writer (flags, then the
`run` entry) → `open_flags` → `proposed_decisions` → the ledger append → the artifacts → the report.

**Reading order for review:** `config/replay.py` (`open_flags`) and `ledger.resolve_features`,
the hold-out being the stage's correctness core; then `decisions.py`; then `steps.py` against the
finding table; then `run.py`; then the hold-out and acceptance tests.

### Interface
- **Public:** `run_feature_checks(cfg, entity, env, spark) -> StageResult` (D-137; resolves the
  config itself; `spark` is kept only because every stage function in `STAGES` has the one shape
  `run` loops over, Q422, and is never used); `StageResult(tables, ledger, log, meta, paths, views, frame, config)`, `frame`
  is `None` here (nothing is collected). Listed in [architecture](../architecture.md#public-api).
- **CLI:** `python -m core_modelling run <configs> --stages eda feature_checks` (in order, over
  every config); `python -m core_modelling decide <config> --entity … --keep f1 f2 --findings
  leakage.too_strong --reason "…"`.
- **Config** (`feature_checks:`, a mapping with one typed model per step; every leaf loggable at
  stage `feature_checks`; [config](config.md) owns the schema):

| Parameter | Default | Meaning |
|---|---|---|
| `quality.dominant_share_max` | 0.99 | one value covering this share flags `near_constant` |
| `quality.missing_share_max` | 0.95 | this null share flags `high_missing` |
| `quality.max_levels` | 50 | more levels flags `high_cardinality` |
| `quality.nulls_may_be_zeros.missing_min` | 0.2 | null share from which the note looks |
| `quality.nulls_may_be_zeros.zero_share_max` | 0.005 | "never a zero" among the values |
| `quality.nulls_informative_min` | 0.55 | null concordance for the `nulls_informative` note |
| `leakage.concordance_max` | 0.80 | concordance that flags `too_strong` |
| `leakage.null_concordance_max` | 0.70 | null concordance that flags `missingness_leak` |
| `leakage.rare_effect_max` | 5 | rate (mean) ratio of a rare value for `rare_value_leak` |
| `time_alignment.signal_kept_min` | 0.5 | share of signal a lag must keep |
| `time_alignment.constant_clients_min` | 0.99 | share of clients constant for `client_constant` |
| `time_alignment.concordance_min` | 0.6 | signal needed before either check looks |
| `stability.heterogeneity_p_max` | 0.01 | Cochran's p for `concordance_unstable` |
| `stability.concordance_range_min` | 0.05 | its effect-size condition |
| `stability.psi_max` | 0.10 | PSI for the two PSI notes |
| `stability.new_level_share_max` | 0.01 | share of unseen levels for `new_levels` |
| `redundancy.correlation_max` | 0.90 | \|Spearman\| for `correlated_pair`; the cluster cut |
| `redundancy.association_max` | 0.90 | Cramér's V or η for `associated_pair` |

- **Audit-log entries** ([config](config.md#decision-audit-log-d-125)): writes `flag` (with
  `finding`; the features may be empty) and the stage `run` entry (with `periods`); reads `keep`
  (with `findings`), `exclude`, `include`, `set` and `revert` through the replay.
- **Artifacts** (`<use_case>/04_feature/<ddh>/feature_checks/`, D-136): `feature_checks.json`
  (`schema_version: 1`, the framework version, when, the hashes, `replayed_to`, the periods
  compared, the flag summary, the entries written), `tables/` (`findings`, `per_period`,
  `clusters`, `proposed_decisions`), `resolved_config.yml`, `report.html`; plus the ledger's columns
  ([feature ledger](feature_ledger.md)). A rerun rewrites the folder whole; the latest run per data
  definition is the one Training reads.

### Lessons from the crunch
- **T10:** PSI on categoricals crashed on `np.quantile`; categoricals get their own bins (the
  window's levels with `__other__`).
- **T11:** a feature built from the eligibility-defining activity is dead on the eligible rows;
  `quality.constant` and `all_null` catch it.
- **T12:** the raw forward column the target was built from sat beside it; lineage is excluded
  automatically, never remembered.
- The AUC-floor heuristic and its standard error at few positives belong to automated selection in
  [training](training.md).

## Open questions
- **`rare_value_leak`'s small-cell guard:** at `MIN_BIN_SUPPORT = 20` rows a cell with two positives
  at a 2% base rate reaches 5×; measured on the `dev` preset's null controls in the build, and
  moved to the cell's events (`strata.min_events`) if they flag. Unverified.
- **Bank-side timing:** the stage reads tables only, but a regression counts table is about twenty
  times a binary one; unverified at the bank's size.
- **`concordance_unstable` has no synthetic trap yet:** the `unstable` trap kind arrives in M4.
- **Grouped importance and the cluster rule for automated selection** (the top member per cluster
  unless a person kept the others, ranked inside a cluster on the train split only): M2.3's questions.
