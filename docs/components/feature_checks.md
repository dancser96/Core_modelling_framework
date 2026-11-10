# Feature Checks
**Status:** built (2026-11-06, Stage 2 major step 3; spec settled 2026-11-02; the SDS's review 1 and its answers Q539–Q545 applied 2026-11-09) · **Legacy:** `src/leakage.py`, `src/feature_stats.py` (`signal_persistence`), `notebooks/Feature_Checks.ipynb`
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

**In:** EDA's `eda.json`, counts, client-constant, correlation, ranking and
concordance-per-period tables and the ledger, for one data-definition hash. **Out:** ledger
columns, the `findings` and `unavailable` tables, `flag` entries and a `run` entry (the compared
periods) in the audit log, the proposed decisions, a report, `StageResult`.

**Key numbers**, the same at both levels. Flags: all null; constant; one value ≥ 99%; ≥ 95%
null; over 50 levels; concordance ≥ 0.80 (in bin or best order); null concordance ≥ 0.70;
beside a value on ≥ 90% of the filled rows, the other values' rate (mean) above its by Cohen's h
(d) ≥ 0.8; < half the signal kept when lagged; constant in ≥ 99% of clients with concordance
≥ 0.6; Cochran's p ≤ 0.01 with a range ≥ half the signal; PSI ≥ 0.25. Notes: ≥ 20% null and no
zeros; null concordance ≥ 0.55; PSI from 0.10 to below 0.25; new levels ≥ 1%; |association|
≥ 0.90. No check skips a feature for low support: a finding's detail says when its value is not
significant at its support.

**Run it:** `run_feature_checks(cfg, entity, env, spark)`, `python -m core_modelling run <config>
--stages eda feature_checks` or notebook `03_feature_checks.ipynb`; settle flags with
`record_decision(..., keep=[...], findings=[...])` or `decide --keep … --findings …`.

## Level 2: How it fits together

### What drives what
- **EDA computes, Feature Checks judges.** Every number a step reads is an EDA ledger column or a
  function of EDA's cells computed with `statistics/` and EDA's own functions (`measures.py`: the
  lagged concordance, a window SE in effective clients, PSI; then Cochran's Q on EDA's
  concordance per period, new levels). Feature Checks bins,
  ranks and collects nothing itself, so its numbers and EDA's differ by data, never by method
  (D-135). It refuses to run without EDA's artifact for the same data-definition hash, when EDA's
  settings digest differs from the current resolved config, or when the ledger and `eda/` come
  from two EDA runs.
- **The config sets the thresholds**: one typed mapping per step under `feature_checks:`, each
  threshold a loggable leaf, identical at both levels (D-132).
- **The audit log carries the flags and the decisions** (D-125). Feature Checks writes `flag`
  entries and one stage `run` entry; a person writes `keep`, `exclude` and `include`. Storage and
  replay: [config](config.md#decision-audit-log-d-125).
- **The ledger shows them.** It stores the statistics and the flags the latest run raised on the
  feature (open or settled; which are open is derived); `held`, `kept`, `excluded` and `verdict`
  are derived from the resolved config (replay writes the open flags'
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
2. Read `eda/` and the ledger for the data-definition hash; refuse, naming EDA, on a missing
   artifact, a settings-digest mismatch or a ledger from another EDA run.
3. Gather the steps' inputs (`check_inputs`): the read candidates, EDA's tables, the compared
   periods and the per-period table.
4. Run the five steps in their fixed order; a step left out of a present `feature_checks`
   mapping is skipped and the report says so; a present mapping that names no step is refused at
   load (running zero checks is a mistake, §4.5). Stack their findings into one `findings` table.
5. Write to the audit log: per flag finding, a `flag` entry when its feature set differs from
   that finding's latest entry (an empty set closes it); then one stage `run` entry with the
   `periods` it compared.
6. Resolve the config again and read the open flags, the new entries included; build the
   proposed decisions and the held features.
7. Append Feature Checks' columns to the ledger (a skipped step's as null).
8. Build the views and render the report; a render failure stops here, the entries written.
9. Save the ledger, then write `feature_checks/` through a temporary folder with `report.html`
   in it (`feature_checks.json` is the commit marker), and return the `StageResult`.

### Function structure
`src/core_modelling/feature_checks/`:
- `findings.py`: the finding table as plain data (`FINDINGS`: each finding's kind, measure and
  text).
- `measures.py`: the numbers read from EDA's cells that EDA does not store (a window
  concordance's SE in effective clients, the lagged concordance, PSI between two periods, the
  label-free per-period table).
- `steps.py`: `check_inputs`, the five `check_<step>(inputs, params) -> StepResult` and `STEPS`
  (name → function, in run order).
- `decisions.py`: `flag_entries` (which entries this run writes), `proposed_decisions` (the review
  view), `held_summary`.
- `report.py`: `build_views`, `report_sections`.
- `run.py`: `run_feature_checks`, the stage function, which orchestrates only.

It imports `statistics/` and EDA's functions (every calculation), `ledger.py`, `artifacts.py`,
`reporting/` and `config` (the entry writer, the replay). It saves the ledger first and writes
its folder last (the stage json is the commit marker, D-136).

### How it is checked
- **The hold-out:** `resolve_features` leaves held features out and takes them back after a
  `keep`; an empty `flag` entry closes a finding; a `keep` settles only the findings it names, a
  different finding raised later opens again, the same finding with new values does not.
- **The artifacts:** the digest refusal; the temporary folder; a rerun on unchanged data writes no
  `flag` entry.
- **The trap acceptance test** on the `dev` preset (D-064, D-137; `tests/test_traps.py`, marked
  `traps`): each synthetic trap row maps to the finding that must catch it, an explicit
  `NOT_CHECKS` dict lists the rows out of scope with a reason, any row in neither fails the test,
  the null controls (pure noise) must raise no flag, and no legitimate card column may raise a
  leak or lag flag (details below).

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
- **`eda.json`:** the hashes (`config_hash`, `data_definition_hash`, `resolved_input_hash`),
  `replayed_to`, `settings_digest` and `settings` (the digested values: `features.kinds`,
  `strata`, `eda` and `time.validation_period`, which decides the compared periods and sits
  outside the data-definition hash), `snapshot_period`, `compared_periods` (`window`, `gap`,
  `latest`), `window_levels`, `over_ceiling`, `clients` (the window's clients, which scale a
  support to effective clients: a client labelled in several periods counts about once),
  `population` (the counts per period, nullable integers, null outside the window), `headline`.
- **The ledger's EDA columns:** `kind`, `levels`, `lineage`, `unsupported`, `concordance` (the
  clusters' order), and the window twins the findings cite: `concordance_window`,
  `missing_share_window`, `null_concordance_window`, `zero_share_window`,
  `dominant_share_window`.
- **`tables/cells`, the counts table:** one row per feature, period, bin and target bin (`lagged`,
  `bin_order`, `is_null`, `n`, `sum_y`); Feature Checks reads the window periods' cells, the
  latest period's, and the lagged cells.
- **`tables/client_constant`:** `feature, constant_share, clients`.
- **`tables/correlation`** (`a, b, statistic, method, rows`, method `spearman | cramers_v | eta`);
  the redundancy step cuts the clusters from it and writes its own `tables/clusters`.
- **`tables/ranking`:** `raw_sign_window`, the window's direction every lagged concordance is
  read in (the ledger's `direction` is the snapshot's and null below 2 SE),
  `concordance_window`, compared with the ledger's, `concordance_best_order_window` (a numeric's
  best order on the window, NaN for a categorical), which `too_strong` reads, and `unavailable`,
  EDA's reason where a concordance does not exist.
- **`tables/concordance_per_period`:** the window's concordance per period, in the window's
  direction, with its SE and support ([EDA](eda.md)); `concordance_unstable` and the stability
  chart read it.
- Refused, naming what is missing ("run EDA": an EDA run of an older version lacks the last two
  columns or tables): a missing ledger column (`EDA_LEDGER_COLUMNS`), a missing table
  (`EDA_TABLES`: `cells`, `client_constant`, `correlation`, `ranking`,
  `concordance_per_period`), a missing ranking column (`raw_sign_window`, `concordance_window`,
  `concordance_best_order_window`, `unavailable`), a missing `concordance_per_period` column
  (`feature, period, rows, support, concordance, se, unavailable`), a missing `eda.json` key
  (`compared_periods`, `snapshot_period`, `over_ceiling`, `clients`, `headline`), and a read
  candidate without rows in `cells`, `client_constant`, `ranking` or `concordance_per_period`.
- **The digest check:** Feature Checks recomputes the digest of `features.kinds`, `strata`, `eda`
  and `time.validation_period` from the current resolved config and refuses on a difference,
  naming the changed path. An EDA run removes `feature_checks/` and Feature Checks' ledger
  columns, so a stale judgement cannot survive it.
- **One EDA run:** a ledger whose `concordance_window` differs from `tables/ranking`'s for a read
  candidate is refused (a crash between EDA's ledger save and its folder write, which a reverted
  setting would hide from the digest check).

### The finding table
The table is plain data in `findings.py` (`FINDINGS`: each finding's full name
`<step>.<finding>`, kind, text and `measure`, the name of the statistic its `value` holds: the
one its condition below names, `association` for the two redundancy pairs; the held features'
`flag_values` are keyed by it). Every finding is one row of `findings`: `feature, step, finding,
kind (flag | note), value, threshold, text, detail`, `finding` the full name and `detail` what the
row adds to the text ('' when nothing: a minority's effect, a pair's partners, the periods
tested). A text names no threshold, since the threshold is a config leaf the row
states; a `flag` entry's reason is the finding's text. **A finding's name and kind are part of
the audit-log format** (`CLAUDE.md` §2): renaming, removing or turning a flag into a note needs a
log migration (the migration writes a closing empty `flag` entry), else its open flags are
refused. What a step cannot compute is decided before computing (D-035) and goes to
`tables/unavailable` (`feature, finding, reason`): "not available: …" when no value can exist;
it is not a finding. "Window" means the window periods' cells pooled (the `*_window` ledger
columns). A concordance per period or lagged is taken in the window's direction
(`raw_sign_window`), so a flip reads below 0.5. Every default below is also a template leaf
(D-137). How each statistic is computed: [EDA](eda.md).

**Support never skips a check** (the SDS's Q540). Every check computes on the support there is;
only a value that cannot exist (no labelled row on a side, no events, one target value) is "not
available". A finding with a standard error ends its detail with `support n effective <support
name>, SE s` (the support name the task's: positive events, or units with a non-zero target; the
support the events the statistic reads, for `rare_value_leak` the minority's), then `; not
significant at this support` unless its value is more than 2 SE past its threshold on the side it
fires (`steps._evidence`; 4 SE for a best-order `too_strong`, below). A noisy flag thus holds the
feature and a person keeps it (D-031: the `autonomous` model is the cautious one). The SE printed
is the one judged with, in effective clients (a client labelled in several periods counts about
once: the task's `client_support` on `eda.json`'s `clients`), and taken **at the threshold**, not
at the estimate, since an SE at an estimate near 0 or 1 is tiny on any support:
- a window concordance (`too_strong`; the null indicator's for `missingness_leak` and
  `nulls_informative`): `measures.effective_se` at the threshold, the task's SE as EDA's ranking
  computes a window's (EDA stores none), at max(A, 1 − A), a categorical's times
  `CROSS_FIT_SE_INFLATION`. A `too_strong` read in best order is significant only more than
  `NON_MONOTONE_SE_MULTIPLE` = 4 SE past the threshold, EDA's margin for the in-sample gain of
  ordering the bins by the data; a plain value 2 SE;
- `lagged_signal_drop`: the flip with the lagged SE at 0.5; `signal_kept` with the lagged SE at
  the value the threshold implies, 0.5 + `signal_kept_min` · (`concordance_window` − 0.5), over
  `concordance_window` − 0.5;
- `rare_value_leak`: the task's `rare_effect` SE at its estimate, √(1/n₁ + 1/n₂) for h,
  √((n₁ + n₂)/(n₁n₂) + d²/(2(n₁ + n₂))) for d (when the flag fires the larger, as d is above the
  threshold), both sides' rows in effective clients.
- **Known limits:**
  - `signal_kept`'s SE leaves out the window concordance's own noise, so "significant" is
    slightly too easy there;
  - Cohen's h's SE √(1/n₁ + 1/n₂) is about 20% small at tiny expected counts (a rate of 0.05 on
    40 rows: 0.16 against 0.20 simulated);
  - the other `quality` findings (`near_constant`'s detail gives the minority's effect without its
    SE), `client_constant`, the PSI findings, `new_levels` and the pairs state no SE;
    `concordance_unstable`'s p-value is its own test.

#### `quality`
The first four are exclusive, in this order: a feature gets the first that applies, so an all-null
column is not also constant or high-missing. `high_cardinality` and the two notes apply
independently.
- **`all_null`** · flag · no parameter. `missing_share_window = 1`. "Every value is null." Catches
  the `all_null` trap and T11's dead columns under an eligibility.
- **`constant`** · flag · no parameter. `dominant_share_window = 1`: one value only, null counted
  as a value (so a 1/null column is not constant: its null indicator carries its signal). "One
  value only, null counted as a value." Catches the two `constant` traps and
  `eligibility_defining` (columns fixed by the eligibility, T11).
- **`high_missing`** · flag · `missing_share_max: 0.95`. `missing_share_window ≥ 0.95`. "Almost
  every value is null." Catches the two `low_fill` traps (1% and 0.3% filled).
- **`near_constant`** · flag · `dominant_share_max: 0.99`. `dominant_share_window ≥ 0.99`, null
  counted as a value. "One value covers almost every row, null counted as a value." Its detail is
  the minority's effect, computed as for `rare_value_leak` where it exists: a 99%-zero flag can
  carry real lift at low prevalence (Q440). Catches `near_constant` (99.9% zeros).
- **`high_cardinality`** · flag · `max_levels: 50`. A categorical with `levels > 50` (the ledger's
  distinct non-null levels, counted on the snapshot before the counts table's 50-level cap).
  "Codes or free text? Held until a person confirms the levels are meaningful." Catches the
  300-level code; `nationality` (64 levels) is flagged too, for a person to settle once.
- **`nulls_may_be_zeros`** · note · `nulls_may_be_zeros: {missing_min: 0.2, zero_share_max: 0.005}`.
  A numeric with `missing_share_window ≥ 0.2` and a zero share among its non-null values ≤ 0.005
  (the detail). "Many nulls and never a zero: if a null means 0 here, fill it upstream; the
  framework never imputes." (D-029 (c)) Catches the wait time (`support_wait_min_trap_drift_window`,
  30% null, never 0) and `months_since_last_spend_cc` (90.6% null among the non-holders, never 0);
  leaves `months_since_last_fx` alone (79.4% null, zeros among its values).
- **`nulls_informative`** · note · `nulls_informative_min: 0.55`. `0.55 ≤ null_concordance_window <
  leakage.null_concordance_max`, where a labelled null and a labelled non-null window row exist
  (else "not available"); with `leakage` left out of a present mapping the upper bound is
  `Leakage()`'s default (0.70), and the config refuses a `nulls_informative_min` at or above the
  bound in use (the note could never fire). "Whether the value is filled carries information; keep
  the nulls as their own group; a family that imputes must impute outside the value range, never the
  median." **Null sets** (the SDS's Q543): the noted features with the same null counts in every
  current cell of EDA's table (every target bin of the window, labelled or not, and the gap and
  latest periods: in practice the same null rows; the unlabelled and later counts tell apart two
  sets that coincide on the labelled ones) share a null set, numbered 1… by size; the detail opens
  with "null set k: the same null counts per period and target as m other feature(s)", then the
  evidence, and the rows are ordered by set, largest first, the features alone last. A shared null
  set often marks a population, such as the clients too new for a six-month roll-up: worth an
  eligibility filter (a minimum relationship length) or a model of its own, which a person decides
  at EDA or Target Factory. Catches the six-month roll-ups' shared null set
  (`casa_bal_0_5_months_avg`, null concordance 0.577 on `dev`); leaves alone the weak nulls of
  `residence_days` and `income` (0.516 and 0.506) and the random nulls of the one-value column and
  the wait time.

#### `leakage`
- **`too_strong`** · flag · `concordance_max: 0.80`. The higher of `concordance_window` and
  `concordance_best_order_window` ≥ 0.80 (the SDS's Q541: a U-shaped leak, both ends filled because
  of the outcome, is strong only in best order; a categorical's cross-fitted value is in its best
  order already); when the best order is the higher, the detail opens "best order; in bin order
  0.xxx", then the evidence. Without a window concordance, EDA's reason (the ranking's
  `unavailable`). "A single feature this strong is usually the target under another name or a
  consequence of it." Why 0.80: the oracle's ceiling for card acquisition with every feature is
  0.84. Catches `leak` (0.97, 0.87; the U-shaped `cc_review_score_trap_leak` in best order only,
  0.857 against 0.501 in bin order) and `upstream_target` (1.0); leaves alone the honest score
  (0.748) and the vendor score (0.566 pooled).
- **`missingness_leak`** · flag · `null_concordance_max: 0.70`. `null_concordance_window ≥ 0.70`,
  where a labelled null and a labelled non-null window row exist (else "not available"). **Below
  0.5% nulls:** EDA reads the null concordance only for a missing share in `NULL_SHARE_RANGE =
  (0.005, 0.995)`, but a field blanked when a client converts has a null share equal to the
  prevalence (0.04–0.2% at the bank). For a window missing share above 0 and below 0.005, the step
  computes the null concordance from the pooled window cells with EDA's function (the same guard)
  and judges it the same way; the detail says it was read below EDA's null-share range, then the
  evidence. `nulls_informative` stays on EDA's value. "Whether the value is filled predicts the
  target this strongly: ask how and when the field gets filled." Catches `missing_leak` (0.89)
  and, below the range, the deposit's blanked rate (`td_offer_rate_trap_missing_leak`: 0.42% null,
  0.751 on the deposit config; on the card config its 0.30% nulls carry no signal and raise
  nothing); legitimate informative missingness scores about 0.52–0.58 (the shared null set 0.577,
  the weak nulls 0.51, none held).
- **`rare_value_leak`** · flag · `rare_effect_max: 0.8`, `dominant_share_min: 0.90`. Over the
  filled (non-null) window rows (the nulls are the null concordance's business): one value (bin)
  holding at least `dominant_share_min` of them, every other value pooled as the **minority**
  (Q441, A28). The effect is the task's `rare_effect` of the minority's labelled rows against the
  dominant value's (the SDS's Q539), signed, so a minority below the dominant value reads
  negative and never fires:
  - binary, **Cohen's h**, 2·asin√p₁ − 2·asin√p₂ on the two rates: the arcsine-square-root scale,
    on which a proportion's variance no longer depends on the proportion, so a small rate must
    move far before h grows (0.002 → 0.01 reads 0.11, 0.05 → 0.25 reads 0.60, where a ratio reads
    5 for both);
  - regression, **Cohen's d**, the minority's mean minus the dominant value's over their pooled
    standard deviation (from the cells' `sum_y` and `sum_y2`).

  It fires at ≥ 0.8, Cohen's "large" (0.2 small, 0.5 medium), the same at a 0.2% and a 5% base
  rate. Decided before computing (`rare_effect_unavailable`): "not available" for a side without
  labelled rows (h) or with fewer than two, or no spread in the target on either side (d). The
  detail names the minority's share, the dominant value, both rates (means) and the effect, then
  the evidence. "Beside one dominant value, the other values' target rate (an amount: mean) is
  far above the dominant value's: a code set after the outcome?" Catches the card process leak
  (`process_leak`: 98.7% zeros, the non-zero rows converting at about 80%), its status on the
  categorical path (`application_cc_status_trap_process_leak`: the rare levels 1.3% of the rows,
  71.3% against 1.9%, h 1.74 on `dev`), the shifted column and the upstream target; on the
  regression variant the spend leak by Cohen's d (`cc_spend_review_trap_spend_leak`, about 5).
  Measured on the canonical card data before the change: the traps at h 1.77–3.14, the legitimate minorities at 0.43–0.64 (`segment` outside its main level 0.64, the
  travel-spend roll-ups 0.43–0.48), so none of the latter is held; `segment` and two roll-ups are
  the trap test's `dominant_level` control.
- **Known limit:** the time-alignment screen on the eligibility `define` columns and the modelling
  tags (T11) is not in Stage 2; on the eligible rows every tag is 1, so it needs a design of its
  own (M4).

#### `time_alignment`
Both findings look only at features with `concordance_window ≥ concordance_min` (and above 0.5):
without signal there is nothing to lose or to stamp.
- **`lagged_signal_drop`** · flag · `signal_kept_min: 0.5`. `signal_kept = (lagged_concordance −
  0.5) / (concordance_window − 0.5) < 0.5`, the lagged concordance (each row's value one period
  earlier against its current target, in the window's direction, so `signal_kept` may go negative)
  read on the **lagged pool**: the window's periods after the first (the first period's lagged cells
  are null by construction: its previous period is not in EDA's rows), on whatever support it holds;
  "not available" for a one-period window (no lagged value), when the pool has no events or one
  target value, without a window direction, or when a categorical's cross-fit lacks two client
  folds. The detail gives the share of the pool's rows without a lagged value (N11), "read one
  period earlier it orders clients the other way" when the lagged value is more than 2 SE below 0.5
  (a flip; the SE at 0.5), then the evidence of `signal_kept` (its SE above). "The feature loses
  most of its signal when lagged one period: its value may be stamped after the period." Catches
  `shifted` (next month's value; lagged once it is the legitimate current value, whose signal
  collapses). A slow legitimate feature keeps nearly all its signal; a fast one may be flagged and
  kept. This replaces D-029 (d)'s forward-vs-backward comparison. **Known limit:** the numerator is
  read on the rows with a lagged value over the later periods, the denominator is
  `concordance_window` over every window period, so a population that changes over the window shifts
  `signal_kept` slightly.
- **`client_constant`** · flag · `constant_clients_min: 0.99`, `concordance_min: 0.6`.
  `constant_share ≥ 0.99` and `concordance_window ≥ 0.6`, the detail empty (the concordance shows
  once, in the step table's `concordance_window`); "not available" when no client has two
  non-null values. "Constant within the client across the window and predictive: a static
  attribute, or one date's value stamped onto every period." Catches `lookahead`
  (`holding_cnt_trap_lookahead`, 0.81, which the lag check cannot see). Static legitimate
  attributes with signal are flagged too: no statistic on the counts tells a static attribute
  from one date's value stamped onto every period, only lineage does. The step's findings table
  shows each flagged feature's constant share and window concordance side by side, so one `keep`
  settles the static ones once per use case and an `exclude` the stamped one (the SDS,
  2026-11-04); the feature store's static/time-varying metadata, once available, would let the
  check skip static attributes (backlog).

#### `stability`
- **`concordance_unstable`** · flag · `heterogeneity_p_max: 0.01`, `concordance_range_min: 0.5`
  and `concordance_range_floor: 0.05`.
  Over every window period with a concordance in EDA's `concordance_per_period` (a period below
  `strata.min_events` included: its `insufficient` is a display mark): weights `w_i = 1/SE_i²`
  (`steps._period_ses`): binary, Hanley–McNeil at the window's concordance, max(cw, 1 − cw), on the
  period's own rows and support from EDA's table (one row per client, so no client scaling), a
  categorical's times `CROSS_FIT_SE_INFLATION`, so a thin period whose own value sits near 0 or 1
  cannot take the SE floor and dominate Q; regression, EDA's `se` as stored (Kendall's null SE,
  halved, does not depend on the value: the per-task flag `period_se_at_window_value`; D-082). The
  pooled `c̄ = Σ w_i c_i / Σ w_i`, `Q = Σ w_i (c_i − c̄)²`, `p = 1 − χ²_{k−1}(Q)`. Flag when `p ≤
  0.01` and the range `max c_i − min c_i ≥ max(0.05, 0.5 × |concordance_window − 0.5|)`:
  relative to the window's signal (the SDS's Q544: 0.06 is the whole signal of a 0.55 feature and
  a fifth of a 0.80 one's; 0.5, the periods differ by half the signal), never below the floor
  (Q547: near no signal the relative bound nears 0 and Q alone would decide, so on a large
  population a signal-less feature's 0.04 wobble was held) (`heterogeneity_p`,
  `concordance_range`; the detail gives the range, the periods tested and "support n … in the
  thinnest period"). Guards: no
  window concordance → EDA's reason (the ranking's `unavailable`); fewer than two periods with a
  concordance → "not available"; a concordance of 1 → the SE floor. "The feature's power differs
  across the window's periods." Catches a signal present in one period only or a flipped direction:
  the vendor score delivered every other month (`cc_vendor_score_trap_unstable`, 0.63–0.65 in even
  periods, 0.49–0.50 in odd ones, range 0.160). The effect-size condition stops a large sample
  from flagging everything: the honest score's real swing (range 0.078, p 0.0001) clears the 0.05
  floor but stays below half its signal (0.124), so it is not held. **Known limit:** the
  periods share clients, so their concordances are positively correlated and Q, which assumes them
  independent, is conservative (fewer flags than the nominal level); each per-period SE is right on
  its own rows.
- **PSI in two tiers** (the SDS, 2026-11-09): each PSI raises a note from `psi_note_min: 0.10`
  and a flag from `psi_max: 0.25` (Monitoring's drift threshold), never both: the flag replaces
  the note. The config refuses a `psi_note_min` above `psi_max`. A PSI's "not available" reason
  applies to its flag and its note alike.
  - **`psi_window`** · note · `0.10 ≤ psi_window < 0.25`, PSI(the window's first period, the
    window's last period); "not available" for a one-period window. "The distribution moved while
    the model's data was collected." Catches the contact channel's moderate shift
    (`contact_channel_trap_drift_moderate`, 0.157), which stays below the flag.
  - **`psi_window_large`** · flag · `psi_window ≥ 0.25`. "The distribution moved strongly while
    the model's data was collected: find the cause before a keep." Catches the wait time's step
    inside the window (`support_wait_min_trap_drift_window`, 0.394 card, 0.384 deposit).
  - **`psi_latest`** · note · `0.10 ≤ psi_latest < 0.25`, PSI(the window's last period, the latest
    period), whatever `eda.snapshot` says, so the finding means the same thing in every run: the
    most recent period the model's data comes from against the most recent data there is.
    "Production will score a different distribution: expect Monitoring to see it." Catches the
    contact channel's new level after the validation period (0.184); the wait time, stable after
    its step (0.002), raises nothing.
  - **`psi_latest_large`** · flag · `psi_latest ≥ 0.25`. "Production will score a strongly
    different distribution: find the cause before a keep." Catches `drift`: the four login
    roll-ups after the app relaunch (0.43–0.50 on the canonical card data; the raw login column's
    0.23 is a note); the contact channel's 0.184 stays a note.
  - On the canonical card data (42 held in all, measured 2026-11-09) the two flags hold six
    features no other flag holds: those four roll-ups,
    `inflow_casa_vol_0_2_vs_3_5_months_ratio` (window PSI 0.26) and the shifted loan trap column
    (no config for the loan target catches it otherwise); the other two trap columns they raise
    on are held already.
- **`new_levels`** · note · `new_level_share_max: 0.01`. A categorical's share, in the latest
  period, of the rows in bins holding no row in any window period ≥ 0.01 (`__new__` always, null
  only when no window period had one, N5). "Levels unseen in the window cover a share of the
  latest period's rows." Catches the contact channel's `chat` (3.2% of the latest period);
  leaves the one-value column's `paper` alone (0.39%). For a categorical with more than 10,000
  window levels (EDA's `over_ceiling` list) the note reads "not available: more than 10,000 window levels", decided
  up front (D-035).
- PSI (`measures.period_psi`): a numeric on about ten groups merged from the expected period's
  non-null bins (`merge_bins`, a mass point its own group), the same `bin_order` ranges applied to
  the actual period, plus the null bin; a categorical on its bins as they are (kept levels,
  `__other__`, `__new__`, null), aligned on their union; shares over all the period's rows;
  `psi` takes shares in [0, 1] (counts are refused), floors each
  at `PSI_FLOOR = 1e-4` and never renormalises; the Lewis bands
  0.10 / 0.25 are labels, not tests. Moderate drift is a note because it is Monitoring's concern:
  a flag at 0.10 would hold every trending legitimate feature out of an `autonomous` model; from
  0.25, the level at which Monitoring would flag the feature in production, it holds.

#### `redundancy`
- **`correlated_pair`** · note · `correlation_max: 0.90`. A numeric pair with |Spearman| ≥ 0.90
  on EDA's snapshot association table, one row per member: its largest |statistic| the value,
  its partners with their statistics the detail.
- **`associated_pair`** · note · `association_max: 0.90`. A pair with a categorical member and
  Cramér's V or η ≥ 0.90, the same way.
- Text: "Near-duplicates; the cluster table shows which carries the signal." Catches `redundant`
  (0.99997 with `relationship_days`) and `collinearity`.
- **Shown as clusters** (`tables/clusters`, one row per member): average linkage on 1 −
  |association|, cut at 1 − `correlation_max`; per cluster the members sorted by snapshot
  concordance, each with |association| with the first (best) member and `explained_by_others`
  (the within-cluster R² on ranks: the multiple correlation of the member with the cluster's
  other Spearman members, from the correlation submatrix by least squares, so an exact identity
  reads 1, T32; a VIF without imputation and without rows; "not available" for a cluster holding
  a pair that was not compared, for the non-numeric members of a mixed-kind cluster, and when the
  pairwise-complete correlations are inconsistent, R² outside [0, 1]). A pair with fewer than 500
  shared non-null rows is "not compared": it sits at distance 1, which average linkage links only
  inside a cluster of near-identical members (single linkage would chain it through one strong
  neighbour, Q472).
- **What the report says** (`NEAR_DUPLICATES`): a note holds nothing, every member stays a
  candidate. Where members measure the same thing (a total beside its parts, one measure over two
  windows), consider excluding those that add nothing and keeping the one easiest to explain and
  to keep filled, often the first; otherwise Training's selection picks among them, and a boosted
  model, which loses little accuracy to collinearity, splits their importance, so a cluster's
  importances are read together at the sign-off. The choice stays a person's.

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
  non-null values ≤ 0.005; `nulls_informative`: 0.55 ≤ null concordance < 0.70, where a labelled
  null and a labelled non-null row exist; `missingness_leak`: null concordance ≥ 0.70, the same
  condition.
  `rare_value_leak` and `near_constant`'s detail look at the filled rows only.
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
    that moment, so the stored entry is explicit. Every stored (feature, finding) pair must be open
    at write time: a named finding open on only some of the features, a default where the
    features' open sets differ ("one keep per finding set"), and `findings=[]` while flags are
    open are all refused, so a keep never settles in advance a finding raised later on another of
    its features. A different finding raised later opens again; the same finding with new values
    does not.
  - `exclude`: the person's decision; the feature is out of every later run.
  - `include`: reverses a person's `exclude`; a flag still open on the feature holds it again.
  - Each is one entry per group of features with one reason (D-125).
- **Log mechanics** (A19–A21 of the record):
  - Feature Checks writes one `flag` entry per finding per run (`by: {kind: stage, id:
    feature_checks}`, `finding: "<step>.<finding>"`, the features sorted, the finding's text as
    the reason), only when the finding's feature set differs from its latest effective entry
    (`flag_entries`).
  - An empty feature set is allowed for `flag` only and closes the finding (its reason: "No
    feature raises this finding any more"): a column fixed upstream is released by the next run.
    A finding with no earlier entry and no features writes nothing.
  - The steps judge every read candidate, excluded ones included, so an `exclude` never closes a
    flag and a later `include` finds it still open.
  - A skipped step writes nothing, so its earlier flags stay as the log has them.
  - An open flag of a finding this version's table does not know (renamed or removed), or holds
    as a note (no run could close it, since only flags are written), is refused before anything
    is written: settle it with a `keep` naming it, or an `exclude`.
  - Notes are never entries: they live in the `findings` table.
  - No lineage entry: the candidate resolution drops the lineage, and the ledger's `lineage`
    column comes from it.
  - The ledger stores statistics and the flags the latest run raised on the feature (open or
    settled; which are open is derived); `held`, `kept` (with the entry numbers), `excluded` and
    `verdict` (`pass | held | kept | excluded | auto_excluded`) are derived from the resolved config
    at read time, because a stored verdict is stale the moment a person records an entry.
- **`open_flags(entries)`** (in `config/replay.py`): over the effective entries (every `revert`
  applied), per feature, the findings whose latest `flag` entry names the feature and which no
  `keep` naming that feature and finding settles; excluded features are excluded, not held.
  `held_features(entries)` is its keys, and replay writes it into the resolved config as
  `features.held` (refused in a config file, like `excluded` and `kept`), so the run's
  resolved-input hash sees the held set. **`resolve_features(ledger, resolved)`** (in `ledger.py`)
  reads `features.excluded` and `features.held` from the resolved config and gives Training's
  feature set: candidates − lineage − unsupported − excluded − held.
- **Proposed decisions** (the review view; `tables/proposed_decisions`,
  `decisions.proposed_decisions`): one row per open flag finding, in table order, with its features
  (sorted), this run's value of each (none where this run did not raise it: open from an earlier run
  or a skipped step), the threshold, the finding's text and two call texts to copy, the verb left to
  the person (no suggested verb): `record_decision(CONFIG, entity="…", keep=[…],
  findings=["<step>.<finding>"], reason="<why>", env_path=ENVIRONMENT)` and `record_decision(CONFIG,
  entity="…", exclude=[…], reason="<why>", evidence=["feature_checks: <step>.<finding>"],
  env_path=ENVIRONMENT)`. Both list every feature of the finding, and each call takes any subset of
  them (keep some, exclude others, leave the rest held), as the calls' header comment says. A keep
  names its finding in `findings`, which scopes it; an exclude is unconditional, so its evidence
  names the finding instead. `CONFIG` and `ENVIRONMENT` are the names notebook 03's setup cell
  defines, so a copied call writes to the audit log the notebook reads. A feature with two open
  flags appears in both rows; keeping it in one settles only that finding.
- **Held features** (`decisions.held_summary`, a view, not a stored table): one row per held
  feature with its kind, its open flags, `flag_values` (per open flag, its `measure` → this run's
  value, `'not raised'` when the flag is open from an earlier run or a skipped step), and the
  window's `concordance_window` and `missing_share_window`.

A `flag` entry as stored (fields as in [config](config.md#one-entry)):
```json
{"seq": 4, "by": {"kind": "stage", "id": "feature_checks"}, "stage": "feature_checks",
 "op": "flag", "finding": "leakage.too_strong",
 "features": ["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
 "reason": "A single feature this strong is usually the target under another name or a consequence of it.",
 "evidence": ["feature_checks report: leakage"], "data_definition_hash": "d_A",
 "log_schema_version": 1}
```

### The compared periods
- **Which periods** (EDA's `Frames.rows`, [dataset](dataset.md)): every window period, the gap
  periods between the window and the validation period, and the latest period the data holds;
  never the validation period. Outside the window the label was dropped before EDA aggregated
  (D-030). With `time.validation_period: null` there is no gap: the window and the latest period.
  The latest period is included only when it lies after the validation period
  ([dataset](dataset.md)); when there is none, `psi_latest`, `psi_latest_large` and `new_levels`
  are shown as "not available: no period after the validation period" (decided up front, D-035),
  never computed against a window period.
- **What uses which:**
  - `concordance_unstable`: every window period with a concordance (EDA's
    `concordance_per_period`, labelled);
  - `lagged_signal_drop`: the lagged cells of the window's periods after the first;
  - `psi_window` and `psi_window_large`: the window's first and last periods; `psi_latest` and
    `psi_latest_large`: the window's last period and the latest period; `new_levels`: the latest
    period against every window period (label-free);
  - the per-period table (`tables/per_period`), label-free: every compared period's rows,
    missing share and PSI against the snapshot, shown for every candidate as information.
- **The `run` entry:** one stage `run` entry per run (`by: {kind: stage, id: feature_checks}`, its
  `replayed_to` and resolved-input hash) with a `periods` field listing every compared period as
  the config's period labels (the writer refuses any other form, and an empty list). `set` or
  `revert` moving `time.validation_period` to any period a run entry lists, reverted or not, is
  refused, and `resolve_config` refuses as stale a resolved validation period a replayed run
  entry lists (D-088): a validation period whose drift was looked at would make the validation
  result look better than production will be.

### The report
Standalone, beside its artifacts (`feature_checks/report.html`); the writer, the chart rules and
the `CHOICES` table are [reporting](reporting.md)'s. Pre-aggregated figures only, plotly.js once.
`report.py` builds the views (`build_views`, also `StageResult.views` for notebook 03) and
arranges them (`report_sections`). A skipped step reads "Not run"; what cannot be shown reads
"Not available: <reason>" (D-035).
1. **Summary:** the choices block (the level, the task, the periods, the support rule, each step's
   thresholds or "not run", the skipped steps, the compared periods, the hashes); the five
   how-to-read notes (concordance in the window's direction, a flag, a note, grey, `null`), as in
   EDA's report; EDA's headline numbers; the warnings (the skipped steps, whose earlier flags stay
   as the log has them, and always the all-client one, D-030); "Flags and notes": per finding of
   the steps that ran, its kind and count, a flag's features named, a note's only counted (they
   run to dozens); the held features with their `flag_values`, the hold-out sentence the table's
   caption.
2. **Core:** the findings per step in run order, each step a subsection ("Quality", "Leakage",
   "Time alignment", "Stability", "Redundancy"): the raised findings' texts, one table with each
   row's value and threshold, the ledger's statistics beside it and the detail last, then what
   the step could not test, grouped by finding and reason. Redundancy shows first a cluster
   summary, one row per cluster (`cluster, feature` (the member with the highest snapshot
   concordance), `concordance, size, features` (every member, strongest first),
   `association_min, explained_by_others_max`) with `NEAR_DUPLICATES` in its caption, then the
   feature table (`finding, cluster, feature, kind, value, threshold, concordance_window,
   association_with_best, explained_by_others, detail`), sorted by finding, cluster and value
   descending. Then the proposed decisions, a table (per open flag finding its threshold and
   each feature with this run's value, "not raised" when open from an earlier run) plus the two
   calls per finding in one code block; the ledger with the derived decisions (held, kept,
   excluded, verdict).
3. **Extended:** "Per period": a line pointing to EDA's report for every candidate's
   concordance per window period; one feature × period table of PSI against the snapshot per
   compared period, every candidate (the caption naming `psi_note_min` and `psi_max`); a line
   chart of the per-period concordance (EDA's `concordance_per_period`, greyed below
   `strata.min_events`) of the features `concordance_unstable` raised ("Not available" without
   one).
4. **Appendix:** the resolved config after the run's entries, the audit log replayed, the entries
   this run wrote, the timings. The per-value origins are the header `resolve_config(save_to=…)`
   writes into a saved `resolved_config.yml`, not the report's.

### Trap acceptance test
`tests/test_traps.py` on the `dev` preset (20,000 clients), asserting on the window statistics.
The scope and its rules are owned by [test harness](test_harness.md) ("Framework tests assert
against the ground truth"); in short:

| Step | Trap kinds it must catch |
|---|---|
| `quality` | `constant`, `near_constant`, `all_null`, `low_fill`, `high_cardinality`, `eligibility_defining`; `shared_null_set` (`nulls_informative`); `recency_null_zero`, `drift_window` (`nulls_may_be_zeros`) |
| `leakage` | `leak` (the U-shaped one in best order), `missing_leak` (the deposit's below EDA's null-share range), `upstream_target`, `process_leak` (`rare_value_leak`: the count and the status) |
| `time_alignment` | `shifted` (`lagged_signal_drop`), `lookahead` (`client_constant`) |
| `stability` | `drift` (`psi_latest_large`, on the login column or a roll-up); `unstable` (`concordance_unstable`); `drift_window` (`psi_window_large`); `drift_moderate` (`psi_window`, `psi_latest`, `new_levels`) |
| `redundancy` | `redundant`, `collinearity` (the `<product>_status` ⇔ `<product>_flag` identity) |
| kinds (EDA) | `decimal_type` read as numeric |

- **Keyed by trap kind and target:** a card or term-deposit row runs on its config, an "any
  product" row on both; every personal-loan row goes to `NOT_CHECKS` ("no config: loan target"),
  with the EDA views, the spend leak and the off-by-default kinds, so a trap row added later fails
  the test until it is placed.
- **Controls, the second mapping** (`CONTROL_FINDINGS`): the findings a row's columns must not
  raise, for the rows close to a threshold on the safe side (the honest score, the vendor score,
  the one-value column, the wait time, the six natural-control rows on real columns; a row may
  be a trap and a control). `test_each_control_raises_no_forbidden_finding` asserts each control
  column read, each forbidden finding's measure computed on it (where the ledger holds it, so no
  check passes by never running) and none raised. Only findings that could fire there and that
  no trap assertion already excludes are listed (a note and its flag are exclusive).
- **The cross-config control** (`test_sub_range_missing_leak_fires_on_its_target_only`):
  the deposit's blanked rate reads below EDA's null-share range on both configs; it raises the
  missingness leak on the deposit config through the below-range path and no missingness leak on
  the card config, where its nulls carry no signal.
- **The Cohen's d trap** (the spend leak) is asserted on the regression variant in
  `tests/test_feature_checks.py` (`unit` preset): `rare_value_leak` with a detail naming Cohen's d.
- **Per kind:** the process leak is caught by `rare_value_leak` (and also raises
  `lagged_signal_drop`); the drift shows on the login roll-ups more than on the raw column, which
  sits just below `psi_max`'s 0.25 (a note); the look-ahead asserts `client_constant` only,
  since its `dev` concordance (about 0.78 card, 0.77 term deposit) sits near `too_strong`'s 0.80;
  no per-period finding is asserted on the term-deposit config (about 35 events per period).
- **Bins (T25):** every numeric candidate has at least min(distinct values, `eda.bins // 2`)
  bins in the snapshot's cells, no non-singleton bin above 5% of its non-null rows.
- **False positives are checked on the controls** (above), **on the null controls** (pure noise:
  window concordance below 0.55 and no flag) and, count-free, on the card config's legitimate
  columns: none raises `too_strong`, `missingness_leak` or `lagged_signal_drop`
  (`NEVER_ON_LEGITIMATE`, the SDS's Q545) unless a trap row allows it; the real columns named only
  for a note or as a control stay under this guard. There is no bound on the count of non-trap
  holds (the SDS, 2026-11-09): the legitimate features a flag holds by design (`rare_value_leak`,
  `client_constant`, the PSI flags) are a person's to keep. The D-088 counts per period come from
  `eda.json`.
- **Running it:** the default `pytest` runs it (about 5.5 minutes of compute on the Mac);
  `pytest -m "not slow and not traps"` skips it in a quick loop.


### Code map
- `core_modelling/feature_checks/`
  - `findings.py`: the finding table as plain data.
    - `FINDING_COLUMNS` (`feature, step, finding, kind, value, threshold, text, detail`),
      `STEP_ORDER`, `FINDINGS` (full name → `kind`, `measure`, `text`, in run order);
      `step_findings(step) -> list[str]`.
  - `measures.py`: the numbers from EDA's cells that EDA does not store.
    - `effective_se(value, events, non_events, target_bin_shares, *, kind, task, clients) ->
      tuple[float, float]` (the SE and the support in effective events);
    - `lagged_concordance(cells, kind, *, task, window, prior_rows, exact, sign) -> dict`
      (`value`, `missing_share`, `reason`, and `events`, `non_events`, `target_bin_shares`: the
      counts `effective_se` reads at whichever value a judgement needs);
    - `period_psi(cells, kind, expected, actual) -> float`;
    - `per_period_table(cells, kinds, *, periods, snapshot_period) -> pd.DataFrame`
      (`PER_PERIOD_COLUMNS`, label-free).
  - `steps.py`: the five checks, one job each.
    - `CheckInputs` (frozen dataclass: the read candidates' ledger rows, EDA's tables, the
      per-period table, the compared periods and the run's settings) and `check_inputs(ledger,
      eda_tables, eda_meta, resolved) -> CheckInputs`, which refuses incomplete EDA artifacts.
    - `StepResult(findings, columns, unavailable, tables)`: the findings rows, the step's ledger
      columns for every read candidate, what it could not compute with the reason, and its own
      tables (redundancy's `clusters`).
    - `check_quality(inputs: CheckInputs, params: Quality) -> StepResult`, and likewise
      `check_leakage`, `check_time_alignment`, `check_stability`, `check_redundancy`, each with
      its step's Pydantic parameter model.
    - `STEPS` (name → function, the dict order being the run order), `STEP_COLUMNS` (each step's
      ledger columns), `stack_parts(parts, columns)`; `EDA_TABLES` and the column lists
      `check_inputs` refuses without.
  - `decisions.py`: from findings to the log and the review.
    - `flag_entries(findings: pd.DataFrame, entries: list[Entry], steps: list[str]) ->
      list[dict]`: the `flag` entries this run writes (changed sets only; empty sets close).
    - `proposed_decisions(findings: pd.DataFrame, open_flags: dict[str, list[str]], entity: str)
      -> pd.DataFrame` (`REVIEW_COLUMNS`).
    - `held_summary(ledger: pd.DataFrame, open_flags: dict[str, list[str]], findings:
      pd.DataFrame) -> pd.DataFrame` (`HELD_COLUMNS`: `feature, kind, findings, flag_values,
      concordance_window, missing_share_window`).
  - `report.py`: `build_views(tables, concordance_per_period, meta, resolved, ledger, held,
    decisions) -> dict` (`concordance_per_period` EDA's table),
    `report_sections(views) -> list[tuple[str, list]]`.
  - `run.py`: `run_feature_checks(cfg, entity, env, spark) -> StageResult`.
- `core_modelling/config/replay.py`: `open_flags(entries: list[Entry]) -> dict[str, list[str]]`,
  `held_features(entries: list[Entry]) -> list[str]`.
- `core_modelling/ledger.py`: `resolve_features(ledger: pd.DataFrame, resolved: UseCaseConfig) ->
  list[str]`; reading and appending columns ([feature ledger](feature_ledger.md)).
- `core_modelling/statistics/`: `pool_periods`, `shares`, `group_shares`, `support_by_bin`,
  `target_shares`, `null_table`, `concordance_from_table`, `cross_fitted_concordance`,
  `cochran_q`, `merge_bins`, `psi`, `new_level_share`, `cluster_features`,
  `explained_by_others`; from EDA, `encoding_prior_rows` and `NULL_SHARE_RANGE`; from `tasks.py`'s
  per-task spec, `rare_effect`, `rare_effect_unavailable`, `rare_effect_name`, `concordance_se`
  and `client_support` ([EDA](eda.md)).
- `core_modelling/artifacts.py`: `read_stage`, `check_upstream` (the digest check), `write_stage`
  (the temporary folder).

**Call flow of one run:** `run_feature_checks` → `resolve_config` → `read_stage` and
`check_upstream` on `eda/`, `read_ledger`, the one-EDA-run check → `check_inputs` → `STEPS` in
order → `stack_parts` → `flag_entries` → `record_stage_entry` (flags, then the `run` entry) →
`resolve_config` again → `open_flags` → `proposed_decisions` → `add_columns` → `held_summary` →
`render_decisions` → `build_views` → `render_report` → `save_ledger` → `write_stage`.

**Reading order for review:** `config/replay.py` (`open_flags`) and `ledger.resolve_features`,
the hold-out being the stage's correctness core; then `decisions.py`; then `findings.py` and
`steps.py` against the finding table, with `measures.py`; then `run.py`; then `report.py`.

### Interface
- **Public:** `run_feature_checks(cfg, entity, env, spark) -> StageResult` (D-137; resolves the
  config itself; `spark` is kept only because every stage function in `STAGES` has the one shape
  `run` loops over, Q422, and is never used); `StageResult(tables, ledger, log, meta, paths, views,
  frame, config)`, `frame` is `None` here (nothing is collected). Listed in
  [architecture](../architecture.md#public-api).
- **CLI:** `python -m core_modelling run <configs> --stages eda feature_checks` (over every
  config; the asked stages run in `STAGES` order whatever order they are given in); `python -m
  core_modelling decide <config> --entity … --keep f1 f2 --findings leakage.too_strong --reason
  "…"`.
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
| `leakage.rare_effect_max` | 0.8 | Cohen's h (binary) or d (regression) of the minority against the dominant value, for `rare_value_leak`; in (0, 3], so a ratio-era 5 fails at load |
| `leakage.dominant_share_min` | 0.90 | the filled rows' share one value needs before the rest is a minority (`rare_value_leak`, `near_constant`'s detail) |
| `time_alignment.signal_kept_min` | 0.5 | share of signal a lag must keep |
| `time_alignment.constant_clients_min` | 0.99 | share of clients constant for `client_constant` |
| `time_alignment.concordance_min` | 0.6 | signal needed before either check looks |
| `stability.heterogeneity_p_max` | 0.01 | Cochran's p for `concordance_unstable` |
| `stability.concordance_range_min` | 0.5 | its effect-size condition: the range at least this × \|`concordance_window` − 0.5\| |
| `stability.concordance_range_floor` | 0.05 | the range that condition never goes below, so a feature with no signal needs a real swing |
| `stability.psi_note_min` | 0.10 | PSI from which `psi_window` and `psi_latest` note |
| `stability.psi_max` | 0.25 | PSI from which `psi_window_large` and `psi_latest_large` flag (Monitoring's drift threshold) |
| `stability.new_level_share_max` | 0.01 | share of unseen levels for `new_levels` |
| `redundancy.correlation_max` | 0.90 | \|Spearman\| for `correlated_pair`; the cluster cut |
| `redundancy.association_max` | 0.90 | Cramér's V or η for `associated_pair` |

- **Audit-log entries** ([config](config.md#decision-audit-log-d-125)): writes `flag` (with
  `finding`; the features may be empty) and the stage `run` entry (with `periods`); reads `keep`
  (with `findings`), `exclude`, `include`, `set` and `revert` through the replay.
- **Artifacts** (`<use_case>/04_feature/<ddh>/feature_checks/`, D-136):
  - `feature_checks.json`: the stamp (`schema_version: 1`, `stage`, `framework_version`,
    `written_at`, `tables`); `entity`, `config_hash`, `data_definition_hash`,
    `resolved_input_hash`, `hash_version`, `replayed_to` of the run's input; `settings_digest` and
    `settings` over EDA's paths plus `feature_checks` (Training checks it); `snapshot_period`,
    `compared_periods`, `steps_run`, `steps_skipped`; `findings` (per finding of the steps that
    ran: `kind`, `count`, `features`; the values stay in the table);
    `held`; `entries_written` (`seq`, `op`, `finding` of each entry this run wrote);
    `eda_headline`; `timings`.
  - `tables/`:
    - `findings` (`FINDING_COLUMNS`);
    - `unavailable` (`feature, finding, reason`, decided before computing);
    - `per_period` (`PER_PERIOD_COLUMNS`, label-free: `feature, period, group, rows,
      missing_share, psi`; the concordance per period is EDA's `concordance_per_period`);
    - `clusters` (`CLUSTER_COLUMNS`: `cluster` (Int64), `feature, kind, concordance,
      association_with_best, explained_by_others, unavailable`; one row per member, the
      report's cluster summary a view of it);
    - `proposed_decisions` (`REVIEW_COLUMNS`: `finding, step, features` (a list), `values` (a
      list, None where this run did not raise it), `threshold` (float), `text, keep_call,
      exclude_call` (with `evidence=["feature_checks: <finding>"]`)).
  - `log.json`, `resolved_config.yml` (the body, without the origins header), `report.html`.
  - Plus the ledger's columns ([feature ledger](feature_ledger.md)), saved first with Feature
    Checks' sidecar; a skipped step's columns are null.
  - A rerun rewrites the folder whole; the latest run per data definition is the one Training
    reads. A render failure raises before the ledger or the folder is written: the entries stay
    written and the previous ledger and folder stay; the next run then writes no new `flag`
    entry, so its `entries_written` lists only its `run` entry.

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
- **Bank-side timing:** the stage reads tables only, but a regression counts table is about twenty
  times a binary one; unverified at the bank's size.
- **Grouped importance and the cluster rule for automated selection** (the top member per cluster
  unless a person kept the others, ranked inside a cluster on the train split only): M2.3's
  questions.
