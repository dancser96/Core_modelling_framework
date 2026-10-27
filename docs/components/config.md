# Config spine
**Status:** building (M2.1, from 2026-10-26) · **Legacy:** `configs/_schema.py`, `configs/_TEMPLATE.yaml`
**Related:** [dataset](dataset.md) (time model, frames, the model input) · [feature ledger](feature_ledger.md) ·
[lifecycle](lifecycle.md) · [run modes](run_modes.md) · [environment](environment.md) (the environment file) ·
[target factory](target_factory.md) (the target spec) · D-006, D-007, D-020, D-021, D-023, D-024, D-030,
D-031, D-032, D-034, D-043, D-047, D-050, D-052, D-088, D-091, D-125, D-128, D-129, D-130, D-131, D-132,
D-133 · OD-02, OD-11, OD-26

## Purpose
The whole definition of a use case, validated at load. It is the framework's most important contract
with its users and the thing a new framework version must never break when a use case upgrades
(D-047, `CLAUDE.md` §2). It must also
**guide**:
- every non-trivial option is listed with when to use it;
- automation levels fill sensible defaults, so a first run needs only a handful of fields.

## Layout (D-129)
A use case = one config and its audit log (D-006, D-043); the config stays one file unless it
bloats. As in the crunch, a repo may hold several similar use cases, each with its own config and
audit log; extension code lives in the repo that holds the use case (which repos: OD-02). It is
written in YAML (D-043); the Pydantic model is the programmatic API. The whole schema and the
template are built in Stage 1: every section is validated from the start with the level's
defaults, and fields of stages not built yet are read once their stage is built. Field names may
still be refined as each stage is built (D-129).

**Sections.** Every stage reads the **shared sections** (`task`, `decision`, `entities`, `data`,
`time`, `features`), which together are the data definition, so EDA, Feature Checks, Training and
Evaluation can never look at different populations. Each stage also reads **its own section**,
which holds that stage's knobs and nothing else. A section left out takes the automation level's
defaults, so a first run needs only the shared sections.

| Section | Read by | Holds |
|---|---|---|
| `decision` | Training, Evaluation, lifecycle | How the scores are used; the metric, gate metric and baselines derived from it or overridden, all declared before any result (`CLAUDE.md` §4.3) |
| `entities` | every stage | Which entities the use case applies to; their logical sources |
| `data` | every stage | Keys, eligibility, target, the client split, the contract band, the saved model input |
| `time` | every stage | The observation window, `w`, the validation month |
| `features` | every stage | The candidates (patterns) |
| `strata` | EDA, Evaluation, Monitoring | The stratification variables, level cap, minimum events (D-038) |
| `eda` | EDA | Key features, chart sampling |
| `feature_checks` | Feature Checks | The ordered check steps and their thresholds |
| `training` | Training | Modelling path, model families, budgets, seeds, search ranges, automated selection, categoricals, calibration, sampling |
| `evaluation` | Evaluation | Metric slices, extra views |
| `lifecycle` | register, promote | The promotion gate's threshold |
| `inference` | Inference | Which model version scores |
| `monitoring` | Monitoring | Drift thresholds, the outcome join, the retrain policy |

**The layout**, with the walking skeleton's `cc_acquisition` values (`conf/base/cc_acquisition.yml`;
the template with every option's when-to-use is `conf/base/TEMPLATE.yml`). A `null` on a level
path (`levels.py`) takes the level default; any other `null` is off or derived (the template's
reading key).

```yaml
schema_version: 1
task: binary
use_case: cc_acquisition                 # <product>_<activity>; must split at load (D-128)
domain: retail
automation_level: assisted               # autonomous | assisted (D-023)

decision:                                # declared before any result; never changed through the audit log (CLAUDE.md §4.3)
  type: probability                      # top_n | threshold | ranking | probability; scores compared across products (D-049)
  n: null                                # top_n only: the list size
  metric: null                           # null = derived from type; else a FLAML metric name (T9)
  gate_metric: null                      # null = derived from type; the promotion gate's metric
  baselines: [population_base_rate]      # + previous_model, historic_predicted_rate (D-009)

entities:                                # only the entities this use case applies to; data never merged (D-034)
  entity_a:
    sources:
      features: [retail_mart]            # ordered: the first is the governing spine, the rest left-join to it
      # features: [feature_store]                   # the feature-store settings ship commented out (D-021)
      # features: [feature_store, retail_mart]
      targets: retail_holdings           # left-joins to the spine; omit when the target is a feature-source column

data:
  keys: {unit_id: client_id, month: snapshot_month}   # the sources' key names; renamed to unit_id, month at load
  model_input: cc_acquisition_input      # optional: the saved model input's logical name (D-131); omit = build in memory
  eligibility:                           # ordered; `define` names a condition, `filter` keeps rows; each logs rows in → out
    - {name: has_income, define: "income IS NOT NULL"}
    - {name: non_holders, filter: "cc_flag = 0", reason: "acquisition is scored for clients without a card",
       before: model}                    # before: model: the rows stay for EDA, tagged `non_holders`; dropped before modelling
    - {name: income_known_or_salaried, filter: "has_income OR salary_transfer_flag = 1",
       reason: "card rules need a known income", before: eda}   # before: eda: the rows are dropped before EDA
  target:                                # the target spec (target_factory.md)
    rule: flag_goes_up                   # the Stage 1 rule (D-029 (c)); count and amount rules later (D-091); an upstream target gives only `column`
    column: cc_flag                      # the column the rule reads; excluded from the candidates (lineage)
    leavers: null                        # null (default) | negative: what a client leaving inside the window gets
    null_as: null                        # built target only; the value a null in `column` stands for (e.g. 0); null: a null never counts
  split: {test_share: 0.3, seed: 42}     # by client, seeded hash; applied from Training on (D-030)
  rate_band: {max: 0.5}                  # contract check on the true population; no floor

time:
  train_months: {first: 2025-03-01, last: 2025-08-01}   # the observation window t1 … tk
  target_window_months: 3                               # w: targets look at months t+1 … t+w (D-129)
  validation_month: 2025-11-01                          # v ≥ tk + w; v + w ≤ the sources' last month

features:
  candidates: {include: ["*"], exclude: []}             # glob patterns over the feature sources' columns

strata:
  variables: [segment, onboarding_channel]
  max_levels: 10                         # the rest pooled as other
  min_events: 50                         # fewer positive events in a stratum: shown as insufficient (D-082)

eda:
  key_features: {top_n: null, include: []}   # top-N by univariate ranking (level default) plus the listed ones
  chart_sample_share: null               # optional: charts on a share of clients, stated in the report

feature_checks:
  steps:                                 # ordered; each flags and logs, never drops (CLAUDE.md §4.6); thresholds low (D-031)
    - {name: quality, params: {}}
    - {name: leakage, params: {}}
    - {name: time_alignment, params: {}}
    - {name: eligibility_constant, params: {}}
    - {name: stability, params: {psi_max: 0.25}}
    - {name: redundancy, params: {}}

training:
  path: automl                           # FLAML, the only path in Phase 2 (D-020)
  estimator_list: [lgbm, xgboost, catboost]   # the families FLAML searches; one entry fixes the family (D-037)
  max_iter: null                         # the trial budget (level default): a rerun gives the same model (D-094)
  time_budget_s: null                    # optional cap; with it a run is reproducible to the recipe, not the model
  seed: 42
  search_space: {}                       # per-family range overrides (FLAML custom_hp), e.g. {lgbm: {num_leaves: …}}
  selection:                             # automated feature selection, by rule, on the train split only
    univariate_floor: 0.515            # the per-task ranking statistic (binary: univariate AUC)
    importance_floor: null
  categoricals: {min_level_count: 50}    # rarer and unseen levels → __other__ (D-037)
  calibration: {method: platt}           # platt | isotonic | none; on by default for probability decisions (D-049)
  sampling: null                         # null | {method: negative_downsampling, keep_fraction: 0.1, seed: 42}
                                         #      | {method: client_sample, share: 0.3, seed: 42}  (D-117)

evaluation:
  slices: {top_pct: [0.01, 0.10], top_n: [10000]}
  views: []                              # extended views to add; the core views always render (OD-12)

lifecycle:
  promotion_gate: {min: null}            # the gate metric's minimum; register's gate is the sign-off (D-031)

inference:
  model: production                      # production | a registered run_id (a pin)

monitoring:
  drift: {psi_max: 0.25}
  outcome_join: true                     # join matured labels to the scores (D-054)
  retrain_policy: {max_age_months: null, psi_flags: null}   # sets "retrain recommended" (monitoring.md)
```

**Model input.** `data.model_input` names, by logical name, the one saved table every stage after
Target Factory works from; the environment file maps the name to a path or table. Without the
field the same frames are built in memory. What it holds, its hash check and when it is written:
[dataset](dataset.md#model-input-d-131) (D-131).

## Phase 2 requirements
1. Every config has `schema_version` and `task`. Unbuilt tasks are defined but fail with a clear "not
   implemented".
2. Load = the config file, migrated, the level defaults applied, validated with Pydantic v2
   (unknown keys fail loud, so a leftover `profile:` can't fall back to a default level); the
   **environment file** loaded beside it, under its own schema and never merged into the config
   (D-130; [environment](environment.md)); then the decision audit log's entries replayed into the
   **resolved config**, saved with every artifact and report (resolved values, including level
   defaults and the entries replayed). The resolved config is plain data (YAML, D-043); the
   config itself is never edited afterwards, since decisions taken later are entries in the
   decision audit log (D-125, section below). The resolved config carries a **housekeeping
   block**:
   - the framework version and a version card of the key libraries;
   - when the run was made;
   - the environment values the run used (the physical sources, roots, Spark settings and the
     collect budget), since they sit outside every hash (D-130);
   - the run's identities (`run_id`; config, data-definition and resolved-input hashes; the last
     entry replayed; code version; EDA and Feature Checks have no `run_id` yet). The hashes exclude
     this block, so they don't depend on themselves.
3. **Automation levels** (`autonomous` / `assisted`; `manual` later) set defaults for every
   stage; explicit fields override (D-023). The field is `automation_level` from M2.1; `profile` is
   the retired name, with no migration since 0.x promises nothing (D-007 (c)). The same checks run
   at every level, differing in what is decided by rule and what by a person. A level changes
   through a config edit before the config freezes and through a `set` entry in the audit log
   after it, never a CLI override (D-023; the mapping per decision point: D-132, the table
   below).
4. **Business decision** (e.g. `top_n`, `threshold`, `ranking`, `probability`; other tasks add their
   own). It derives:
   - the optimisation metric;
   - the promotion gate metric;
   - what reports emphasise.

   It can be overridden, and metric names are validated against the engine's names (T9) (D-032).
5. **Entities and sources:** a use case lists the entities it applies to (often one), each with
   its logical sources. Sources differ by domain and often by use case. Nothing runs or compares
   across entities by default (D-034). Per entity, `sources.features` is an **ordered list**: the
   first source is the **governing spine**, and the others are left-joined to it on the keys;
   `sources.targets` is one source, left-joined to the spine and contributing only the target,
   omitted when the target is a column of a feature source (D-129; the join rules:
   [dataset](dataset.md#sources-and-joins-d-129)). The feature store is one more logical source, alone or
   next to a mart; the release example shows all three settings, two of them commented out, and a
   `feature_store` source is refused until OD-26 is designed (D-021). Physical names never appear
   in the config: the environment file maps each logical name per entity (D-130).
6. **Stepwise sections:** eligibility and feature-check steps are ordered and named, and each
   produces a log entry (rows/cols in → out, reason). An eligibility entry is Spark SQL, either a
   `define` (a named boolean condition that later entries reuse by name, dropped before the
   candidates are resolved) or a `filter` with a required `reason`; a null condition counts as
   false in a filter (D-129). A filter is one of two kinds: `before: eda` drops its rows before
   EDA (clients the analysis shouldn't see at all, e.g. new clients); `before: model` keeps its
   rows for EDA, tagged by the step's name as a 0/1 column, and drops them before modelling (e.g.
   current holders of the product, whom the analysis compares with the non-holders). The tag is a
   stratification column for EDA ([dataset](dataset.md), [eda](eda.md)).
7. **Features:** candidates are explicit lists or patterns. Human decisions go both ways: `exclude`
   and `keep_despite_flag` (which also protects against automated pruning). They are entries in the
   decision audit log, one per group with one required reason, never edits to the config (D-043,
   D-125). Automated decisions are *not* written into the config as outcomes: the config holds the
   rules that make them (ordered, named steps, like eligibility), and their outcomes are rule
   entries in the log and columns in the feature ledger (D-043, D-125).
8. **Time:** `time` holds the observation window (`train_months {first, last}`), the target
   window `w` (`target_window_months`, one number read by the target builder and the time checks
   alike) and the validation month; the inference month is a run argument (D-088, D-129). The validation month sits outside the
   data-definition hash (EDA never reads it; Feature Checks reads it only to leave it out of its
   comparisons), so moving it never changes the data-definition hash. After the config freezes, the validation month changes only through a
   `set` entry in the audit log, refused when any Feature Checks run compared that month (Feature Checks
   records the months it compared, [feature_checks](feature_checks.md); D-088). A Phase 2
   production retrain moves only the inference month (D-052).
   A month is held as its **last day**, the framework's one convention: a config may write it as
   its first or its last day (any other day is refused as a likely typo), and the dataset moves
   every source's month column to its month's last day on reading (D-129;
   [dataset](dataset.md#sources-and-joins-d-129)).
   Checked at config load (D-129):
   - window order (`first ≤ last`) and `w ≥ 1`;
   - `v ≥ tk + w` (no overlapping target windows).

   Checked when the frames are built, since only the data knows ([dataset](dataset.md)):
   - the window and `v + w` lie inside the sources' months, so every validation label has
     matured (otherwise partial maturity would null validation labels quietly). This replaces the
     backward-window check, which the framework can't make for upstream features.
9. **Data-definition hash:** computed from entity, sources, eligibility, target spec, observation
   window and candidates (D-088; the section below). It keys the EDA and Feature Checks artifacts
   that training requires (D-031). It assumes a source month never changes after loading
   (`CLAUDE.md` §4.10); training recomputes the per-month row and positive counts on every client
   in the window, before the client split, and fails loud when they differ from the EDA artifact's.
10. **Model key** (entity, domain, use case, split) is derived from the config; split = `all` in
    Phase 2.
11. **Downstream sections exist from v1** (lifecycle, inference, monitoring), even while those
    stages are thin, so adding depth later doesn't break configs.
12. **Strata:** one `strata` section (variables, a cap on levels, a minimum number of positive
    events per stratum) shared by EDA, Evaluation and Monitoring (mandatory reporting, D-038;
    D-129).
13. **Metric slices:** `top_pct` and `top_n` lists; either may be empty.
14. **Templates guide:** the base template lists every option with a one-line when-to-use, and
    validation errors say how to fix the problem. Its header key says how to read a line
    (`# required`; a plain value is the default; `null · level:` names both levels' values), and
    a test checks every schema field against it, so an omitted value's default is always on
    display.
15. **Migrations:** small functions `migrate_vN_to_vN+1(dict) -> dict`, applied automatically with a
    deprecation warning.

## Decision audit log (D-125)
**Decided (settles the audit-log design; amends D-043 and D-088); built in Stage 1's major step 1.** The SDS
and LDS build from this section.

**The model.** The config is the intent, immutable once Target Factory has built the target, or
at the first EDA run for an upstream target. Every
later decision, by a person or a rule, is an append-only entry in the decision audit log. Replaying the config plus entries 1–n gives a run's one input, the **resolved config**,
validated by the same Pydantic schema. The log never changes the data definition (entity, sources,
eligibility, target spec, window, candidates): changing it means a new config, with fresh EDA and
Feature Checks. Entries are never edited; a reversal is a new entry. The feature ledger is the same
trail read per feature ([feature ledger](feature_ledger.md)).

**The cost.** The current state can't be read from the config file alone: a person reads it with
`show_decisions` or `resolve_config` (below).

### Allowed decisions: a closed list of operations
Each operation is one small function in a plain dict, `APPLY_BY_OP` (`CLAUDE.md` §1 rule 7). An
entry whose `op` isn't in the dict is refused. A new operation is a code change with a test, like
any extension-point entry.

| By | Operation | At replay |
|---|---|---|
| person | `exclude`: drop features from the candidates | changes the input |
| person | `include`: reverse a person's `exclude` | changes the input |
| person | `keep_despite_flag`: resolve a flag; also protects from automated pruning | changes the input |
| person | `set`: change one listed setting (next section) | changes the input |
| person | `sign_off`: approve a run's final feature list (D-031) | trail |
| person | `register`, `promote`: written by those commands | trail |
| rule | `exclude`: lineage, quality filters | changes the input |
| rule | `flag`: one entry per check step | trail; flags never drop (`CLAUDE.md` §4.6) |
| rule | `dropped`: a run output, e.g. automated selection | trail |
| stage | `run`: a marker with `run_id`, the entry it replayed up to and the input hash | trail |

- Only `exclude`, `include`, `keep_despite_flag` and `set` change the resolved input; the rest are
  the trail and are no-ops at replay. A flag stays open until a person's entry resolves it.
- Rejecting features at sign-off is an `exclude` entry with stage `sign_off`, and the model is
  retrained without them.
- `include` reverses a person's `exclude` only, feature by feature: each named feature must be
  excluded now and last by a person's entry, so it may restore any subset of an earlier entry's
  features. A rule's `exclude` is reversed by changing the rule (a listed threshold); a lineage
  exclusion is never reversed (`CLAUDE.md` §4.6). A flagged feature was never dropped:
  `keep_despite_flag` settles the flag.
- A write is refused at once when a feature isn't a candidate, the reason is missing, the change
  touches the data definition, the setting isn't listed, the value fails the schema, or it moves
  the validation month to one Feature Checks compared (D-088).
- An entry's evidence may cite train and test results only: the validation month never informs a
  choice (`CLAUDE.md` §4.4).

### Which settings a `set` may touch, and maintaining the list
`LOGGABLE_SETTINGS` is a plain dict next to the config schema, mapping each allowed setting path to
its stage. Planned (Stage 1):

```python
LOGGABLE_SETTINGS = {
    "automation_level": "eda",   # a level move reruns every stage from EDA (D-132)
    "strata.variables": "eda", "strata.max_levels": "eda", "strata.min_events": "eda",
    "eda.key_features.top_n": "eda", "eda.key_features.include": "eda",
    "eda.chart_sample_share": "eda",
    "feature_checks.steps": "feature_checks",
    "training.estimator_list": "training", "training.max_iter": "training",
    "training.time_budget_s": "training", "training.search_space": "training",
    "training.selection.univariate_floor": "training",
    "training.selection.importance_floor": "training",
    "training.categoricals.min_level_count": "training",
    "training.calibration.method": "training", "training.sampling": "training",
    "time.validation_month": "evaluation",   # refused once a Feature Checks run compared it (D-088)
    "evaluation.slices.top_pct": "evaluation", "evaluation.slices.top_n": "evaluation",
    "evaluation.views": "evaluation",
}
```

Anything not listed is refused at write time ("this needs a new config"). Never listed: the
data-definition fields, and the decision, metric and baselines, which are declared before any
result is seen (`CLAUDE.md` §4.3); the client split and `training.seed`, since a test score must
not pick its own sample or seed, and every run in one log is compared on the same test clients
(D-083). `lifecycle`, `inference` and `monitoring` are decided with M2.4 and M4: they act after
registration. Paths are leaves wherever a section holds independent knobs, so a `set` changes one
value without restating the others. A `set` names its stage; that stage and the later ones rerun
from the new resolved input.

**Maintaining the list:**
- A field added to the schema isn't loggable until it is added to the list.
- A test checks that every listed path exists in the schema and that none is a data-definition
  field, the decision, a metric or a baseline.
- Entries carry `log_schema_version` and `hash_version`. A config migration that renames or
  retypes a listed path must also bump `log_schema_version` and ship an entry migration, since
  `set` entries store the dotted path and the values in the old schema's terms; the entry version
  is checked before an entry is parsed, so a newer entry says "raise the pin" (`CLAUDE.md` §2).
- The list and the decision-point table (below) are kept in step: D-132 maps the automation
  levels on the same decision points.

### From entries to code: replay
1. Load and migrate the config.
2. Apply entries 1–n in order through `APPLY_BY_OP`. A later entry on the same feature or setting
   wins: an `include` after an `exclude` restores the feature.
3. Validate the result with the schema and hash it: the resolved-input hash (Identities, below).

```python
APPLY_BY_OP = {
    "exclude": _apply_exclude, "include": _apply_include,
    "keep_despite_flag": _apply_keep, "set": _apply_set,
    "flag": _leave_unchanged, "dropped": _leave_unchanged, "sign_off": _leave_unchanged,
    "register": _leave_unchanged, "promote": _leave_unchanged, "run": _leave_unchanged,
}

for entry in entries[:upto]:
    cfg = APPLY_BY_OP[entry["op"]](cfg, entry)
```

- **Replaying to any point reproduces any run:** `upto` = a run marker's `replayed_to` gives that
  run's input, so an old run can be rerun or compared without guessing what was decided then.
- **Stale entries fail loud:** an entry naming a feature that is no longer a candidate stops the
  replay, citing the entry number.
- **Rule entries can be checked:** rerunning the rules on unchanged data reproduces their entries.
  When restated data makes a rule decide differently, the rerun appends the step's new outcome;
  replay shows the difference and flags the person entries that cited the old rule entry (entry 6
  cites entry 4 below) for a look, rather than applying them silently.
- **The trail never changes the input:** run outputs, sign-offs, register and promote are recorded
  but leave the resolved config alone.

The replay code is expected to be a few dozen lines. That is a design target, not measured.

### Verbosity
- A rule writes one entry per step, with its list of features.
- A person writes one entry per group, with one reason (D-043's one note per group).
- So a use case's road to production is tens of entries, not hundreds; the worked example below
  has 16.
- The default view hides run outputs and resolved flags, and filters by stage and by who decided.
- Each feature's trail is read through the [feature ledger](feature_ledger.md).

### One entry
Fields: `seq`, `time`, `by` (`kind`: person / rule / stage, plus `id`), `stage`, `op`, then
`features` or `path` / `from` / `to` (`to` may be null, e.g. sampling off), plus `reason`,
`evidence`, `data_definition_hash`, `hash_version` (the recipe that computed it) and
`log_schema_version`. Run markers add `run_id`, `replayed_to` and `resolved_input_hash`. An
operand that doesn't belong to the operation is refused. Evidence
cites earlier entries as `#n`, which is how replay finds the person entries that cite a rule
entry. Entry 6 of the worked example, as stored:

```json
{
  "seq": 6,
  "time": "2026-10-27T15:40:00",
  "by": {"kind": "person", "id": "<user id>"},
  "stage": "feature_checks",
  "op": "exclude",
  "features": ["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
  "reason": "Set after the offer, so not known at scoring time",
  "evidence": ["#4", "feature_checks report: Leakage"],
  "data_definition_hash": "d_A",
  "log_schema_version": 1
}
```

### The final config as one file
`resolve_config(cfg, entity, env, upto=None, save_to=None)` returns the resolved config, or writes it
as one YAML file with each value's entry number as a comment. It is a view, regenerated on demand
and never edited back. Every run already saves its resolved config with its artifacts.

### Storage
- **Locally:** one small JSON file per entry, `decisions/<seq>.json`, per instance, under a folder
  keyed by the data-definition hash and the entity (the root comes from the environment adapter).
  The file is `<seq>.json`, zero-padded to four digits. No append is needed (HDFS append may be
  off in the bank: unverified). Two simultaneous writers can't interleave: each write is
  create-if-absent, and on a clash the write fails and the person re-runs the decision, since
  its checks were made against the log before the other writer's entry (that `hdfs dfs -put`
  without `-f` refuses an existing file is to be verified in the bank). Until the M2.4 transport,
  an `hdfs://` data root is refused where the log is read or written. A missing log folder reads
  as an empty log with a warning; once the model input exists (major step 3), a missing folder
  for a frozen config is an error.
- **Register:** the run's slice (the entries up to its run marker, any later validation-month entry
  its Evaluation was scored with, plus the sign-off that approved
  the run) is packed into one file inside the registered bundle, immutable; promote reads it
  there. A folder of entries can't be registered or promoted as is ([lifecycle](lifecycle.md)).
- **Later:** a shared, queryable table may come with the registry tables in round 2 (M4). It would
  follow D-007 (shared tables only grow within a major version).

### Who writes
Any DS on the use case. The entry records the person as a user id, never a name in the repo. The
sign-off names who signed (D-031). `register` and `promote` write their own entries.

### Public functions
`record_decision`, `show_decisions` and `resolve_config`, plus the CLI command
`python -m core_modelling decide`, are Public API (D-024;
[architecture](../architecture.md#public-api)); their signatures are in the Interface section
below. Writing an entry is one call in a notebook, or the same through `decide`:

```python
record_decision(
    "conf/base/cc_acquisition.yml", entity="entity_a",
    exclude=["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
    reason="Set after the offer, so not known at scoring time",
    evidence=["#4", "feature_checks report: Leakage"],
)
```

`show_decisions(cfg, entity, env)` prints the log as the table below. Each report's choices block
shows the entries up to its run, and the model card the registered slice.

### Worked example
Card acquisition within 3 months on the synthetic mart, entity A.

| # | Date | By | Stage | Op | What | Reason | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | 10-27 | rule `target_lineage` | Target Factory | exclude | `cc_flag` | Builds the target | lineage file |
| 2 | 10-27 | rule `quality.all_null` | Feature Checks | exclude | 1 feature | No values in the window | checks log, step 1 |
| 3 | 10-27 | rule `quality.near_constant` | Feature Checks | exclude | 1 feature | 99.9% one value | checks log, step 2 |
| 4 | 10-27 | rule `leakage.too_strong` | Feature Checks | flag | 2 features | Univariate AUC 0.97 and 0.88 | report → Leakage |
| 5 | 10-27 | rule `stability.psi` | Feature Checks | flag | 5 features | PSI above 0.25 across the window | report → Stability |
| 6 | 10-27 | person (DS) | Feature Checks | exclude | the 2 flagged in #4 | Set after the offer, so not known at scoring time | #4; report → Leakage |
| 7 | 10-27 | person (DS) | Feature Checks | keep_despite_flag | the 5 flagged in #5 | Digital adoption trend; monitoring watches it | #5; report → Stability |
| 8 | 10-28 | stage | Training | run `r1` | input = config + #1–7 | — | model results report (Evaluation) |
| 9 | 10-28 | rule `selection.importance` | Training | dropped | 71 features | Below the importance floor | ledger, run `r1` |
| 10 | 10-28 | person (DS) | Training | set | `training.max_iter` 200 → 300 | AUC still rising at the last trials | model results report (Evaluation), `r1` |
| 11 | 10-29 | stage | Training | run `r2` | input = config + #1–10 | — | model results report (Evaluation) |
| 12 | 10-29 | person (DS) | Sign-off | exclude | `nationality` | Not used for product targeting | sign-off view, `r2` |
| 13 | 10-29 | stage | Training | run `r3` | input = config + #1–12 | — | model results report (Evaluation) |
| 14 | 10-30 | person (DS) | Sign-off | sign_off | the 61 features of `r3` | Each defensible; flags reviewed | sign-off view, `r3` |
| 15 | 10-30 | person (DS) | register | register | `r3` as version 1 | Candidate for production | model card |
| 16 | 11-02 | person (DS) | promote | promote | version 1 | Promotion PR approved | registry record |

**Replay, state after each entry.** Each row is exactly what a run started at that point would
train on.

| After | Excluded | Kept despite a flag | Open flags | `max_iter` | Input hash |
|---|---|---|---|---|---|
| config only | — | — | — | 200 | `h0` |
| #3 | 3 (#1 lineage, #2–3 quality) | — | — | 200 | `h3` |
| #5 | 3 | — | 7 (#4 leakage 2, #5 stability 5) | 200 | `h5` |
| #6 | 5 (+2 leaks) | — | 5 | 200 | `h6` |
| #7 → run `r1` | 5 | 5 | 0 | 200 | `h7` |
| #9 | unchanged: a run output, not an input | | | | `h7` |
| #10 → run `r2` | 5 | 5 | 0 | 300 | `h10` |
| #12 → run `r3` | 6 (+`nationality`) | 5 | 0 | 300 | `h12` |
| #14–16 | unchanged: the sign-off, register and promote are the trail | | | | `h12` |

`resolve_config(cfg, entity, env, upto=12)` gives the state run `r3` trained on, each value pointing
at the entry that set it:

```yaml
# resolved: cc_acquisition.yml + entries 1–12 (input hash h12)
features:
  excluded:
    - cc_flag                                  # 1, rule target_lineage
    - legacy_risk_grade_trap_all_null          # 2, rule quality.all_null
    - paper_statement_flag_trap_near_constant  # 3, rule quality.near_constant
    - cc_preapproval_score_trap_leak           # 6, person: set after the offer
    - cc_campaign_response_score_trap_leak     # 6
    - nationality                              # 12, person: not used for targeting
  kept_despite_flags:
    - login_digital_mobile_cnt                 # 7, person: digital adoption trend
    - login_digital_mobile_cnt_0_2_months_avg  # 7 (and three more rollups)
training:
  max_iter: 300                                # 10, person: AUC still rising
```

### Decision points and the automation levels (D-132)
"Rule" = decided by a rule in the config, "person" = a human decision. `LOGGABLE_SETTINGS` works
from the same list. The two levels differ at four points only (D-132); the numbers (N, the
budgets) are reversible defaults, set as each stage is built.

| Decision point | `autonomous` | `assisted` |
|---|---|---|
| Target spec; eligibility, split, sampling, collect budget | the config (person); rules apply it | same |
| Null targets at the panel edge; degenerate target | rule | rule |
| Run EDA and Feature Checks before training (D-031) | automatically, default content | the person runs them and reads the reports |
| Key features in EDA | rule: top-N (N = 10) | rule: top-N (N = 20) plus the person's list |
| Resolving Feature Checks' flags | not awaited: open flags go to the sign-off view and the model card | the stage ends in a flag review; keep / exclude entries before training |
| Training budgets (`max_iter`, seeds), calibration | smaller level defaults | larger level defaults; a person may `set` through the log |
| Automated selection drops; search result; gates; monitoring flags | rule | rule |
| Feature sign-off; register; promote; retrain / retire / roll back; a level move | person, always | person, always |
| deploy | the change-request process | same |
| Which version scores | production, or a pin in the config | same |

Top-N is the N highest candidates in EDA's univariate ranking (binary: direction-agnostic AUC
against the target, on every client in the window, D-030), plus the features the person lists:
EDA's key features, each with a deep dive ([eda](eda.md)). A move between levels is a config edit
before the config freezes and a `set` on `automation_level` in the audit log after it, which
reruns every stage from EDA (D-132); at replay the move re-fills exactly the fields the level
filled at load (recorded as `housekeeping.level_filled`), and explicit values stay, including a
value a `set` entry gave a level-filled path: the `set` takes the path off the list (a `set` on a
section, for every level path under it).

## Identities (D-088, D-125): how the hashes work
Every hash is taken over a canonical form (keys sorted, defaults resolved, migrated to the current
schema) of a subset of the config or the resolved config (the table says which), and stored
beside a `hash_version` that names the recipe
that computed it. **Rule:** any change to the canonical form of a hashed section (a field added,
renamed or retyped, a default changed) changes the digests of every existing config, so it bumps
`HASH_VERSION`, and the reading of old artifacts is decided with it (D-088's "schema change, not
a data change"). Until the December pre-release nothing is kept inside the bank, so a recipe
change re-pins the digests and leaves `HASH_VERSION` at 1 (0.x promises nothing, `CLAUDE.md` §2);
the bump applies from then. A golden-hash test pins the example's data-definition and target-spec
digests, so the change can't happen unnoticed.

| Identity | Covers | Excludes | Changes when |
|---|---|---|---|
| config hash | the use-case definition: every section after level resolution | the housekeeping block; the environment file (tables, paths, Spark, theme; D-130); the audit log's entries | the config file changes, which after Target Factory means a new config; decisions in the log leave it unchanged |
| data-definition hash | entity, sources, eligibility steps, target spec, observation window, candidates | the validation month (in the config; EDA never reads it, Feature Checks only to leave it out); the inference month (a run argument); the stage sections | the population, the target or the candidates change. It keys the EDA and Feature Checks artifacts training needs (D-031) |
| resolved-input hash | the config plus entries 1–n, resolved (the run's one input) | the housekeeping block; the environment file; trail entries, which change nothing | every entry that changes the input: `exclude`, `include`, `keep_despite_flag`, `set` |
| `run_id` | resolved-input hash + entity + timestamp | — | every training run of one instance |
| `recipe_hash` | resolved config + final features + hyperparameters + encoder levels + calibration spec | the fitted numbers | the recipe changes; a retrain in production keeps it (D-052) |
| `model_hash` | the bundle's per-part hashes | — | any part changes, a retrain included (D-094) |

A worked example, one use case on two entities:
1. The DS writes the config and runs EDA and Feature Checks on entity A. The artifacts are keyed by
   the data-definition hash `d_A`.
2. Training on entity A finds `d_A`'s artifacts, replays the entries so far into the resolved input
   `i1`, and runs with `run_id = i1 + A + <timestamp>`. The same config on entity B needs its own
   EDA and checks (`d_B`: the entity is part of the hash), its own log and its own `run_id`.
3. The DS records a human `exclude` for one feature: an entry in the audit log, not a config edit.
   The config hash stays `c1` and the candidates are unchanged, so `d_A` stays and no EDA rerun is
   needed. The resolved-input hash becomes `i2`, and training reruns with a new
   `run_id = i2 + A + <timestamp>`.
4. Next month the DS scores: the inference month is a run argument, so no hash changes and
   nothing has to be rerun. Moving the validation month (a checked `set` entry, e.g. for a sweep
   variant) changes the resolved-input hash but not the data-definition hash, so EDA and Feature
   Checks don't rerun.
5. A framework upgrade migrates the config at load. Hashes are computed on the migrated canonical
   form; if the migration changes that form, the hashes change too, and the artifacts carry their
   `hash_version`, so the due-diligence gate can say "schema change, not a data change: rerun EDA
   or accept the old artifacts explicitly" instead of failing with a bare mismatch.
6. The same config on a laptop and inside the bank hashes identically, because the environment
   file's values are outside the config hash (D-130).

## Design constraints
- No bank identifiers; physical names only in the environment file (`conf/local/`, D-130).
- Pydantic models stay flat and readable. No clever validators: one validator per rule, with a clear
  message.
- Adding optional fields with defaults is non-breaking. Renaming or removing fields is breaking
  (`CLAUDE.md` §2).

## Lessons from the crunch
T9, T13. The crunch's two feature views (candidates vs survivors) and its validated temporal ordering
were its best ideas. They now become candidates + decisions + the feature ledger, and the window-aware
time checks.

## Interface
Built in Stage 1's major step 1 (2026-10-26; under the SDS's review). Package:
`core_modelling/config/` (`schema.py`, `levels.py`, `migrations.py`, `identities.py`,
`replay.py` (the entry model, the operations, the replay), `audit_log.py` (storage and the public
functions)); the CLI command `decide` in `core_modelling/__main__.py`.
- `load_config(path: str | Path) -> UseCaseConfig` (public): YAML → `migrate` →
  `apply_level_defaults` (fills nulls only) → `UseCaseConfig.model_validate`, with `extra="forbid"`
  on every model. One validator per rule: the name split (D-128), the time rules (req. 8),
  `decision.type: top_n` needs `n`, an eligibility entry has exactly one of `define` / `filter`,
  a `filter` has a `reason` and a `before` (`eda` / `model`) and a `define` has no `before`,
  `target` has `rule` + `column` (with `null_as` and `leavers` only then) or `column` alone,
  `sampling` with its parameters, `metric` in FLAML's names when set (T9), `test_share` in
  (0, 1).
- `LEVEL_DEFAULTS: dict[str, dict[str, dict]]` (path → {autonomous, assisted}), `MIGRATIONS:
  dict[int, Callable[[dict], dict]]` (empty at `schema_version: 1`; a version above the current
  one fails loud).
- The hashes (`identities.py`): `config_hash(cfg)`, `data_definition_hash(cfg, entity)`,
  `target_spec_hash(cfg, entity)`, `resolved_input_hash(resolved)`; sha256 over canonical JSON
  of a dict that names its parts, with `HASH_VERSION = 1`, 12-character prefixes (`short`) in
  paths and `run_id`. The config hash excludes `housekeeping` and the two replay-written lists;
  the resolved-input hash excludes `housekeeping` only.
- The audit log (public, D-024): `record_decision(config_path, entity, *, exclude=None,
  include=None, keep_despite_flag=None, set=None, reason, evidence=(), stage=None,
  env_path=None) -> Entry` (the writer is the current user id; rule and stage entries get their
  own writers with their stages; a feature op says it was checked against the candidate patterns
  only, until the model input brings the resolved list); `read_resolved_config(path) ->
  UseCaseConfig` reads a saved resolved config back as is (no level defaults, its replayed lists
  and housekeeping kept), which `load_config` refuses, since a config file carries intent only; `resolve_config(cfg, entity, env, upto=None, save_to=None) ->
  UseCaseConfig`; `show_decisions(cfg, entity, env) -> pd.DataFrame`; the CLI command `decide`.
  Entries live at `04_feature/<use_case>/<entity>/<data_definition_hash>/decisions/<seq>.json`
  ([environment](environment.md)), `seq` zero-padded to four digits, written create-if-absent with
  a retry on a clash; an entry under another data definition, a gap in the numbering, an unknown
  operation or another `log_schema_version` fails loud. A `set` may write `null` (e.g. sampling
  off). `resolve_config` fills the housekeeping block (framework version, time, entity, the three
  hashes, `replayed_to`, `hash_version`, the environment values used, `level_filled`) and, with
  `save_to`, writes the YAML with a header naming
  the entries replayed and the entry behind each changed value. The rule and stage entries
  (`flag`, `dropped`, `run`, `sign_off`, `register`, `promote`) get their writers with their
  stages; replay already accepts them.

## Open questions
- `training.calibration.method` defaults to `platt` for every task; regression needs its own
  default (likely `none`) through the per-task spec, decided when Training is built (M2.3).
- Feature Checks (M2.2): how a rerun with a changed threshold supersedes the step's earlier
  `exclude` entry (a rule-written `include`, or a step's latest outcome replacing its earlier
  one), and whether a person may overrule a quality rule for one feature (a rare flag that is
  99.9% zeros) without changing the threshold for all.
- The decision audit log: whether a person entry that cites a superseded rule entry blocks
  register until a person confirms it (today it is only flagged at replay).
- The log folder is keyed by the short data-definition hash, so a change of the hash recipe
  (`HASH_VERSION`) would leave an old log where no reader looks; a `definition.json` beside
  `decisions/` carrying the full hash, `hash_version` and `schema_version` would let a later
  version find and re-key it. Related: a field added to a hashed section, even optional, changes
  every digest; hashing only values that differ from the schema default would leave them alone,
  at the price of a version bump for every changed default. Decide both before the December
  pre-release, when logs and artifacts start being kept inside the bank.
- Until the model input exists (major step 3), `record_decision` checks a feature name against
  the candidate patterns only, so a misspelt name passes; the dataset then fails loud when a
  name in `features.excluded` or `kept_despite_flags` is not a column.
- Extension functions live in the use case's repo and are referenced by import path; the resolved
  config records the path and a source hash (D-006). The exact fields are set when a use case
  first needs one; the walking skeleton's examples need none.
