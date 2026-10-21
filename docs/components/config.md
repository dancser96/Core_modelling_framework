# Config spine
**Status:** designing · **Legacy:** `configs/_schema.py`, `configs/_TEMPLATE.yaml`
**Related:** [dataset](dataset.md) (time model) · [feature ledger](feature_ledger.md) · [lifecycle](lifecycle.md) ·
[run modes](run_modes.md) · [environment](environment.md) · D-023, D-032, D-034, D-043, D-047, D-050,
D-052, D-058, D-075, D-076, D-077, D-086–D-090 · OD-10, OD-11, OD-25, OD-26

## Purpose
The whole definition of a use case, validated at load. It is the framework's most important contract
with its users and the thing a new framework version must never break when a use case upgrades
(D-047, `CLAUDE.md` §2). It must also
**guide**:
- every non-trivial option is listed with when to use it;
- profiles fill sensible defaults, so a first run needs only a handful of fields.

## Shape (illustrative, not final)
One file per use case is the goal, not a hard rule; split it only if it bloats (D-043). It is
written in YAML (D-086); the Pydantic model is the programmatic API.

```yaml
schema_version: 1
task: binary                        # dispatch key; panel tasks first
use_case: product_x_acquisition
domain: retail
profile: standard                   # defaults for every stage; to become an automation level (D-077)
decision: {type: top_n, n: 10000}   # how scores will be used → metric, gates, report emphasis

entities:                           # only where this use case applies; data never merged
  entity_a: {source: retail_products_a}   # per-entity overrides only where they differ

data:          # unit and month keys, eligibility (ordered steps), target spec (Target Factory) or column
time:          # observation window, target window, validation (OOT) month, inference month
features:      # candidates (lists / patterns) + human decisions (keep / exclude, with reasons)
eda:           # key features (top-N, user list), stratify_by, sampling
feature_checks:  # ordered steps and thresholds
training:      # path (automl; predefined from Phase 3), budgets, sampling, selection mode, calibration, refit
evaluation:    # slices (top_pct, top_n), baselines, views
lifecycle:     # register gates, promote / deploy settings
inference:     # output settings, schedule-facing options
monitoring:    # drift thresholds, outcome join, retrain policy
```

**"Sections per stage", clarified.** Each stage reads the shared sections (`task`, `decision`,
`entities`, `data`, `time`, `features`) plus its own. EDA can therefore run with only the shared
sections filled, and stage sections left empty take the profile's defaults. Every stage reads the
*same* data definition, so EDA, checks, training and evaluation can never quietly look at different
populations.

## Phase 2 requirements
1. Every config has `schema_version` and `task`. Unbuilt tasks are defined but fail with a clear "not
   implemented".
2. Load = `conf/base` → `conf/local` merge → Pydantic v2 validation → **frozen config** saved with every
   artifact (resolved values, including profile defaults). The frozen config is plain data (YAML,
   D-086), is never edited afterwards (decisions taken later: OD-10), and
   carries a **housekeeping block**:
   - the framework version and a version card of the key libraries;
   - when the run was made;
   - the run's identities (`run_id`, config and data-definition hashes, code version; EDA and
     Feature Checks have no `run_id` yet). The config hash excludes this block, so it doesn't
     depend on itself.
3. **Profiles** (`quick` / `standard` / `thorough`) set defaults for every stage; explicit fields
   override (D-023). They are becoming **automation levels**: two in Phase 2, `autonomous` and
   `assisted`, `manual` later; the same checks at every level, differing in what is decided by
   rule and what by a person. The field keeps the name `profile` until the levels exist and is
   renamed with a migration (D-077, D-087; the mapping per decision point: OD-25).
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
   feature store later breaks no config (D-075, OD-26).
6. **Stepwise sections:** eligibility and feature-check steps are ordered and named, and each produces
   a log entry (rows/cols in → out, reason).
7. **Features:** candidates are explicit lists or patterns. Human decisions go both ways: `exclude`
   and `keep` (despite a flag or against automated pruning), as grouped lists with one note per group
   (whether a note is required, and whether they live here or in the decision audit log: OD-10).
   Automated decisions are *not* written into the config as outcomes: the config holds the rules that make them (ordered, named steps, like eligibility), and
   their outcomes live in the feature ledger and the frozen config (D-058).
8. **Time:** observation window, target window, validation month and inference month. Validated at
   load:
   - window order;
   - `v ≥ tk + w` (no overlapping target windows);
   - `v + w ≤` the last loaded month, so every validation label has matured (otherwise partial
     maturity would null validation labels quietly);
   - backward windows fit the available history (default ≤ 6 months).
9. **Data-definition hash:** computed from entity, sources, eligibility, target spec, observation
   window and candidates (D-088; the section below). It keys the EDA and Feature Checks artifacts
   that training requires (D-031). It assumes a source month never changes after loading
   (`CLAUDE.md` §4.10); training recomputes the per-month row and positive counts and fails loud
   when they differ from the EDA artifact's.
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

## Decision audit log (direction, OD-10)
Direction from the CDS, not settled: the config is the starting point and never changes, and every
decision taken downstream, automated or human, is recorded in an audit log next to the run. How it
is built and saved is OD-10. The SDS's idea is to save each run's **pathway**: the chain of decision
points it passed and what was chosen at each, the way a path through a neural network lights up.
The feature ledger is already that pathway for features.

**Draft inventory of decision points.** "Rule" = decided by a rule in the config, "person" = a
human decision, "level" = either, depending on the automation level (D-077, OD-25).

| Where | Decision point | By |
|---|---|---|
| Target Factory | Target spec: rule, window, leavers | Person (config) |
| Target Factory | Null targets at the panel edge; refusing a degenerate target | Rule |
| Dataset | Eligibility steps; client split; sampling and row budget | Rule |
| EDA | Key features | Rule (top-N) + person (listed) |
| Feature Checks | Lineage exclusions; one flag per check step | Rule |
| Feature Checks | Exclude / keep, resolving flags | Person |
| Feature Checks | Feature sign-off before register (D-076) | Person, always |
| Training | Modelling path, budgets, calibration, refit | Level |
| Training | Automated selection drops; search result (family, hyperparameters) | Rule |
| Training | Point picked on the trade-off chart (Phase 3) | Level |
| Evaluation | Gates passed or failed | Rule |
| register / promote | Register a version; choose the production version (approved PR) | Person |
| deploy | Run by the change-request process | Person (CR) |
| Inference | Which version scores (production by default, or a pin) | Level |
| Monitoring | Flags; "retrain recommended" | Rule |
| Monitoring | Retrain, retire, roll back | Person |
| Any | Move the use case to another automation level | Person |

**To settle in OD-10:**
- what one record holds (decision point, options, choice, rule or person, evidence, time);
- how it enters reproducibility: a run = frozen config + the decisions it used, and the run's hash
  covers both;
- whether human feature decisions stay in the config (D-043) or move to the log;
- how records are keyed: EDA and Feature Checks run before any `run_id` exists (as in OD-11);
- kept simple: append-only records in a table, not a graph engine.

## Identities (D-088): how the hashes work
Every hash is taken over a canonical form (keys sorted, defaults resolved, migrated to the current
schema) of a subset of the frozen config, and stored beside a `hash_version` that names the recipe
that computed it.

| Identity | Covers | Excludes | Changes when |
|---|---|---|---|
| config hash | the use-case definition: every section after profile resolution | the housekeeping block; every `conf/local` value (tables, paths, Spark, theme) | any modelling choice changes: a feature decision, a budget, a threshold, a stage setting |
| data-definition hash | entity, sources, eligibility steps, target spec, observation window, candidates | the validation and inference months (run arguments); the stage sections | the population, the target or the candidates change. It keys the EDA and Feature Checks artifacts training needs (D-031) |
| `run_id` | config hash + entity + timestamp | — | every training run of one instance |
| `recipe_hash` | frozen config + final features + hyperparameters + encoder levels + calibration spec | the fitted numbers | the recipe changes; a refit keeps it (D-096) |
| `model_hash` | the bundle's per-part hashes | — | any part changes, a refit included (D-094) |

A worked example, one use case on two entities:
1. The DS writes the config and runs EDA and Feature Checks on entity A. The artifacts are keyed by
   the data-definition hash `d_A`.
2. Training on entity A finds `d_A`'s artifacts and runs with `run_id = c1 + A + <timestamp>`. The
   same config on entity B needs its own EDA and checks (`d_B`: the entity is part of the hash) and
   gets its own `run_id`.
3. The DS adds a human `exclude` for one feature. The config hash becomes `c2`; the candidates are
   unchanged, so `d_A` is unchanged and no EDA rerun is needed. Training reruns under `c2`.
4. Next month the DS scores: the inference month is a run argument, so neither hash changes and
   nothing has to be rerun. Likewise, moving the validation month for a sweep variant changes
   neither hash.
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
- The decision audit log's Phase 2 scope (OD-10, section above).
- Automation levels: what `autonomous` and `assisted` each decide by rule at each decision point
  (OD-25).
- Profile defaults per stage (set as each stage is built).
- Extension functions live in the use case's repo and are referenced by import path; the frozen
  config records the path and a source hash (D-090). The exact fields are set when a use case
  first needs one; the walking skeleton's examples need none.
