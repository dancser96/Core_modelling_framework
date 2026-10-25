# Config spine
**Status:** designing · **Legacy:** `configs/_schema.py`, `configs/_TEMPLATE.yaml`
**Related:** [dataset](dataset.md) (time model) · [feature ledger](feature_ledger.md) · [lifecycle](lifecycle.md) ·
[run modes](run_modes.md) · [environment](environment.md) · D-006, D-007, D-020, D-021, D-023, D-024,
D-031, D-032, D-034, D-043, D-047, D-050, D-052, D-088, D-125, D-128 · OD-02, OD-11, OD-25, OD-26

## Purpose
The whole definition of a use case, validated at load. It is the framework's most important contract
with its users and the thing a new framework version must never break when a use case upgrades
(D-047, `CLAUDE.md` §2). It must also
**guide**:
- every non-trivial option is listed with when to use it;
- automation levels fill sensible defaults, so a first run needs only a handful of fields.

## Shape (illustrative, not final)
A use case = one config and its audit log (D-006, D-043); the config stays one file unless it
bloats. As in the crunch, a repo may hold several similar use cases, each with its own config and
audit log; extension code lives in the repo that holds the use case (which repos: OD-02). It is
written in YAML (D-043); the Pydantic model is the programmatic API.

```yaml
schema_version: 1
task: binary                        # dispatch key; panel tasks first
use_case: product_x_acquisition    # <product>_<activity>; must split at load (D-128)
domain: retail
automation_level: assisted          # defaults for every stage: autonomous or assisted (D-023)
decision: {type: top_n, n: 10000}   # how scores will be used → metric, gates, report emphasis

entities:                           # only where this use case applies; data never merged
  entity_a: {source: retail_products_a}   # per-entity overrides only where they differ

data:          # unit and month keys, eligibility (ordered steps), target spec (Target Factory) or column
time:          # observation window, target window, validation (OOT) month; inference month: a run argument
features:      # candidates (lists / patterns); human decisions: the audit log (D-125)
eda:           # key features (top-N, user list), stratify_by, sampling
feature_checks:  # ordered steps and thresholds
training:      # path (automl; predefined from Phase 3), budgets, sampling, selection mode, calibration
evaluation:    # slices (top_pct, top_n), baselines, views
lifecycle:     # register gate, promote / deploy settings, production retrain check tolerances (D-052)
inference:     # output settings, schedule-facing options
monitoring:    # drift thresholds, outcome join, retrain policy
```

**"Sections per stage", clarified.** Each stage reads the shared sections (`task`, `decision`,
`entities`, `data`, `time`, `features`) plus its own. EDA can therefore run with only the shared
sections filled, and stage sections left empty take the level's defaults. Every stage reads the
*same* data definition, so EDA, checks, training and evaluation can never quietly look at different
populations.

## Phase 2 requirements
1. Every config has `schema_version` and `task`. Unbuilt tasks are defined but fail with a clear "not
   implemented".
2. Load = `conf/base` → `conf/local` merge → migration → replay of the decision audit log's
   entries → Pydantic v2 validation (unknown keys fail loud, so a leftover `profile:` can't fall
   back to a default level) → **resolved config** saved with every artifact and report
   (resolved values, including level defaults and the entries replayed). The resolved config is
   plain data (YAML, D-043); the config itself is never edited afterwards, since decisions taken
   later are entries in the decision audit log (D-125, section below). The resolved config
   carries a **housekeeping block**:
   - the framework version and a version card of the key libraries;
   - when the run was made;
   - the run's identities (`run_id`; config, data-definition and resolved-input hashes; the last
     entry replayed; code version; EDA and Feature Checks have no `run_id` yet). The hashes exclude
     this block, so they don't depend on themselves.
3. **Automation levels** (`autonomous` / `assisted`; `manual` in Phase 3) set defaults for every
   stage; explicit fields override (D-023). The field is `automation_level` from M2.1; `profile` is
   the retired name, with no migration since 0.x promises nothing (D-007 (c)). The same checks run
   at every level, differing in what is decided by rule and what by a person. A level changes
   through a config edit or an audit-log entry, never a CLI override (D-023; the mapping per
   decision point: OD-25).
4. **Business decision** (e.g. `top_n`, `threshold`, `ranking`, `probability`; other tasks add their
   own). It derives:
   - the optimisation metric;
   - the promotion gate metric;
   - what reports emphasise.

   It can be overridden, and metric names are validated against the engine's names (T9) (D-032).
5. **Entities and domain:** a use case lists the entities it applies to (often one) and overrides only
   what differs per entity. Sources differ by domain and often by use case. Nothing runs or compares
   across entities by default (D-034). A use case may read several sources per entity (e.g. the
   feature store and a mart, joined on unit and month); the shape allows it from v1, so adding the
   feature store later breaks no config (D-021, OD-26).
6. **Stepwise sections:** eligibility and feature-check steps are ordered and named, and each produces
   a log entry (rows/cols in → out, reason).
7. **Features:** candidates are explicit lists or patterns. Human decisions go both ways: `exclude`
   and `keep_despite_flag` (which also protects against automated pruning). They are entries in the
   decision audit log, one per group with one required reason, never edits to the config (D-043,
   D-125). Automated decisions are *not* written into the config as outcomes: the config holds the
   rules that make them (ordered, named steps, like eligibility), and their outcomes are rule
   entries in the log and columns in the feature ledger (D-043, D-125).
8. **Time:** the observation window, target window and validation month are set in the config;
   the inference month is a run argument (D-088). The validation month sits outside the
   data-definition hash (EDA never reads it; Feature Checks reads it only to leave it out of its
   comparisons), so moving it never changes the data-definition hash. After the config freezes, the validation month changes only through a
   `set` entry in the audit log, refused when any Feature Checks run compared that month (Feature Checks
   records the months it compared, [feature_checks](feature_checks.md); D-088). A Phase 2
   production retrain moves only the inference month (D-052).
   Validated at load:
   - window order;
   - `v ≥ tk + w` (no overlapping target windows);
   - `v + w ≤` the last loaded month, so every validation label has matured (otherwise partial
     maturity would null validation labels quietly);
   - backward windows fit the available history (default ≤ 6 months).
9. **Data-definition hash:** computed from entity, sources, eligibility, target spec, observation
   window and candidates (D-088; the section below). It keys the EDA and Feature Checks artifacts
   that training requires (D-031). It assumes a source month never changes after loading
   (`CLAUDE.md` §4.10); training recomputes the per-month row and positive counts on every client
   in the window, before the client split, and fails loud when they differ from the EDA artifact's.
10. **Model key** (entity, domain, use case, split) is derived from the config; split = `all` in
    Phase 2.
11. **Downstream sections exist from v1** (lifecycle, inference, monitoring), even while those
    stages are thin, so adding depth later doesn't break configs.
12. **Stratification variables** (mandatory reporting, D-038), with a cap on levels and a minimum
    number of positives per stratum.
13. **Metric slices:** `top_pct` and `top_n` lists; either may be empty.
14. **Templates guide:** the base template lists every option with a one-line when-to-use, and
    validation errors say how to fix the problem.
15. **Migrations:** small functions `migrate_vN_to_vN+1(dict) -> dict`, applied automatically with a
    deprecation warning.

## Decision audit log (D-125)
**Decided (settles the audit-log design; amends D-043 and D-088); planned, not built.** The SDS
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
- `include` reverses a person's `exclude` only. A rule's `exclude` is reversed by changing the
  rule (a listed threshold); a lineage exclusion is never reversed (`CLAUDE.md` §4.6).
- A write is refused at once when a feature isn't a candidate, the reason is missing, the change
  touches the data definition, the setting isn't listed, the value fails the schema, or it moves
  the validation month to one Feature Checks compared (D-088).
- An entry's evidence may cite train and test results only: the validation month never informs a
  choice (`CLAUDE.md` §4.4).

### Which settings a `set` may touch, and maintaining the list
`LOGGABLE_SETTINGS` is a plain dict next to the config schema, mapping each allowed setting path to
its stage. Illustrative, names fixed when built:

```python
LOGGABLE_SETTINGS = {
    "training.max_iter": "training",
    "training.time_budget": "training",
    "training.sampling.keep_fraction": "training",
    "training.calibration.method": "training",
    "feature_checks.stability.psi_max": "feature_checks",
    # Refused when Feature Checks compared the new month (D-088).
    "time.validation_month": "evaluation",
}
```

Anything not listed is refused at write time ("this needs a new config"). Never listed: the
data-definition fields, and the decision, metric and baselines, which are declared before any
result is seen (`CLAUDE.md` §4.3). A `set` names its stage; that stage and the later ones rerun
from the new resolved input.

**Maintaining the list:**
- A field added to the schema isn't loggable until it is added to the list.
- A test checks that every listed path exists in the schema and that none is a data-definition
  field, the decision, a metric or a baseline.
- Entries carry `log_schema_version`. A schema migration that renames a listed field migrates the
  entries too, like configs (`CLAUDE.md` §2).
- The list and the decision-point inventory (below) are kept in step: OD-25 maps the automation
  levels on the same inventory.

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
`features` or `path` / `from` / `to`, plus `reason`, `evidence`, `data_definition_hash` and
`log_schema_version`. Run markers add `run_id`, `replayed_to` and `resolved_input_hash`. Evidence
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
`resolve_config(config, entity, upto=None, save_to=None)` returns the resolved config, or writes it
as one YAML file with each value's entry number as a comment. It is a view, regenerated on demand
and never edited back. Every run already saves its resolved config with its artifacts.

### Storage
- **Locally:** one small JSON file per entry, `decisions/<seq>.json`, per instance, under a folder
  keyed by the data-definition hash and the entity (the root comes from the environment adapter).
  No append is needed (HDFS append may be off in the bank: unverified). Two simultaneous writers
  can't interleave: each write is create-if-absent, and on a clash it retries with the next number
  (that `hdfs dfs -put` without `-f` refuses an existing file is to be verified in the bank).
- **Register:** the run's slice (the entries up to its run marker, any later validation-month entry
  its Evaluation was scored with, plus the sign-off that approved
  the run) is packed into one file inside the registered bundle, immutable; promote reads it
  there. A folder of entries can't be registered or promoted as is ([lifecycle](lifecycle.md)).
- **Later:** a shared, queryable table may come with the registry tables in round 2 (M4). It would
  follow D-007 (shared tables only grow within a major version).

### Who writes
Any DS on the use case. The entry records the person as a user id, never a name in the repo. The
sign-off names who signed (D-031). `register` and `promote` write their own entries.

### Public functions (planned, not built)
`record_decision`, `show_decisions` and `resolve_config`, plus the CLI command
`python -m core_modelling decide`, are Public API (D-024;
[architecture](../architecture.md#public-api)).
Writing an entry is one call in a notebook, or the same through `decide`:

```python
record_decision(
    "conf/base/cc_acquisition.yml", entity="entity_a",
    exclude=["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
    reason="Set after the offer, so not known at scoring time",
    evidence=["#4", "feature_checks report: Leakage"],
)
```

`show_decisions(config, entity)` prints the log as the table below. Each report's choices block
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
| 10 | 10-28 | person (DS) | Training | set | `training.max_iter` 100 → 300 | AUC still rising at the last trials | model results report (Evaluation), `r1` |
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
| config only | — | — | — | 100 | `h0` |
| #3 | 3 (#1 lineage, #2–3 quality) | — | — | 100 | `h3` |
| #5 | 3 | — | 7 (#4 leakage 2, #5 stability 5) | 100 | `h5` |
| #6 | 5 (+2 leaks) | — | 5 | 100 | `h6` |
| #7 → run `r1` | 5 | 5 | 0 | 100 | `h7` |
| #9 | unchanged: a run output, not an input | | | | `h7` |
| #10 → run `r2` | 5 | 5 | 0 | 300 | `h10` |
| #12 → run `r3` | 6 (+`nationality`) | 5 | 0 | 300 | `h12` |
| #14–16 | unchanged: the sign-off, register and promote are the trail | | | | `h12` |

`resolve_config(config, entity, upto=12)` gives the state run `r3` trained on, each value pointing
at the entry that set it:

```yaml
# resolved: cc_acquisition.yml + entries 1–12 (input hash h12)
features:
  exclude:
    - cc_flag                                  # 1, rule target_lineage
    - legacy_risk_grade_trap_all_null          # 2, rule quality.all_null
    - paper_statement_flag_trap_near_constant  # 3, rule quality.near_constant
    - cc_preapproval_score_trap_leak           # 6, person: set after the offer
    - cc_campaign_response_score_trap_leak     # 6
    - nationality                              # 12, person: not used for targeting
  keep_despite_flags:
    - login_digital_mobile_cnt                 # 7, person: digital adoption trend
    - login_digital_mobile_cnt_0_2_months_avg  # 7 (and three more rollups)
training:
  max_iter: 300                                # 10, person: AUC still rising
```

### Draft inventory of decision points
"Rule" = decided by a rule in the config, "person" = a human decision, "level" = either, depending
on the automation level (D-023, OD-25). `LOGGABLE_SETTINGS` and OD-25 both work from this list.

| Where | Decision point | By |
|---|---|---|
| Target Factory | Target spec: rule, window, leavers | Person (config) |
| Target Factory | Null targets at the panel edge; refusing a degenerate target | Rule |
| Dataset | Eligibility steps; client split; sampling and row budget | Rule |
| EDA | Key features | Rule (top-N) + person (listed) |
| Feature Checks | Lineage exclusions; one flag per check step | Rule |
| Feature Checks | Exclude / keep, resolving flags | Person |
| Training | Budgets, calibration; modelling path from Phase 3 (FLAML only in Phase 2, D-020); refits on more data: Phase 3 (D-052) | Level |
| Training | Automated selection drops; search result (family, hyperparameters) | Rule |
| Training | Point picked on the trade-off chart (Phase 3) | Level |
| Sign-off | Feature sign-off, after training and before register (D-031) | Person, always |
| Evaluation | Gates passed or failed | Rule |
| register / promote | Register a version; choose the production version (approved PR) | Person |
| deploy | Run by the change-request process | Person (CR) |
| Inference | Which version scores (production by default, or a pin) | Level |
| Monitoring | Flags; "retrain recommended" | Rule |
| Monitoring | Retrain, retire, roll back | Person |
| Any | Move the use case to another automation level | Person |

## Identities (D-088, D-125): how the hashes work
Every hash is taken over a canonical form (keys sorted, defaults resolved, migrated to the current
schema) of a subset of the config or the resolved config (the table says which), and stored
beside a `hash_version` that names the recipe
that computed it.

| Identity | Covers | Excludes | Changes when |
|---|---|---|---|
| config hash | the use-case definition: every section after level resolution | the housekeeping block; every `conf/local` value (tables, paths, Spark, theme); the audit log's entries | the config file changes, which after Target Factory means a new config; decisions in the log leave it unchanged |
| data-definition hash | entity, sources, eligibility steps, target spec, observation window, candidates | the validation month (in the config; EDA never reads it, Feature Checks only to leave it out); the inference month (a run argument); the stage sections | the population, the target or the candidates change. It keys the EDA and Feature Checks artifacts training needs (D-031) |
| resolved-input hash | the config plus entries 1–n, resolved (the run's one input) | the housekeeping block; `conf/local`; trail entries, which change nothing | every entry that changes the input: `exclude`, `include`, `keep_despite_flag`, `set` |
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
6. The same config on a laptop and inside the bank hashes identically, because `conf/local`
   values are outside the config hash.

## Design constraints
- No bank identifiers; physical names only in `conf/local/`.
- Pydantic models stay flat and readable. No clever validators: one validator per rule, with a clear
  message.
- Adding optional fields with defaults is non-breaking. Renaming or removing fields is breaking
  (`CLAUDE.md` §2).

## Lessons from the crunch
T9, T13. The crunch's two feature views (candidates vs survivors) and its validated temporal ordering
were its best ideas. They now become candidates + decisions + the feature ledger, and the window-aware
time checks.

## Interface
*(fill when built)*

## Open questions
- Exact section layout and field names (settled while building the walking skeleton).
- The decision audit log: whether a person entry that cites a superseded rule entry blocks
  register until a person confirms it (today it is only flagged at replay).
- Automation levels: what `autonomous` and `assisted` each decide by rule at each decision point
  (OD-25).
- Level defaults per stage (set as each stage is built).
- Extension functions live in the use case's repo and are referenced by import path; the resolved
  config records the path and a source hash (D-006). The exact fields are set when a use case
  first needs one; the walking skeleton's examples need none.
