# Config spine
**Status:** designing · **Legacy:** `configs/_schema.py`, `configs/_TEMPLATE.yaml`
**Related:** [dataset](dataset.md) (time model) · [feature ledger](feature_ledger.md) · [lifecycle](lifecycle.md) ·
[run modes](run_modes.md) · [environment](environment.md) · D-023, D-032, D-034, D-043, D-047, D-050, D-052 · OD-05, OD-10

## Purpose
The whole definition of a use case, validated at load. It is the framework's most important contract
with its users and the thing a new framework version must never break when a use case upgrades
(D-047, `CLAUDE.md` §2). It must also
**guide**:
- every non-trivial option is listed with when to use it;
- profiles fill sensible defaults, so a first run needs only a handful of fields.

## Shape (illustrative, not final)
One file per use case is the goal, not a hard rule; split it only if it bloats (D-043).

```yaml
schema_version: 1
task: binary                        # dispatch key; panel tasks first
use_case: product_x_acquisition
domain: retail
profile: standard                   # quick | standard | thorough: defaults for every stage
decision: {type: top_n, n: 10000}   # how scores will be used → metric, gates, report emphasis

entities:                           # only where this use case applies; data never merged
  entity_a: {source: retail_products_a}   # per-entity overrides only where they differ

data:          # unit and month keys, eligibility (ordered steps), target spec (Target Factory) or column
time:          # observation window, target window, validation (OOT) month, inference month
features:      # candidates (lists / patterns) + human decisions (keep / exclude, with reasons)
eda:           # key features (top-N, user list), stratify_by, sampling
feature_checks:  # ordered steps and thresholds
training:      # path (automl | predefined), budgets, sampling, selection mode, calibration, refit
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
   artifact (resolved values, including profile defaults).
3. **Profiles** (`quick` / `standard` / `thorough`) set defaults for every stage; explicit fields
   override (D-023).
4. **Business decision** (e.g. `top_n`, `threshold`, `ranking`, `probability`; other tasks add their
   own). It derives:
   - the optimisation metric;
   - the promotion gate metric;
   - what reports emphasise.

   It can be overridden, and metric names are validated against the engine's names (T9) (D-032).
5. **Entities and domain:** a use case lists the entities it applies to (often one) and overrides only
   what differs per entity. Sources differ by domain and often by use case. Nothing runs or compares
   across entities by default (D-034).
6. **Stepwise sections:** eligibility and feature-check steps are ordered and named, and each produces
   a log entry (rows/cols in → out, reason).
7. **Features:** candidates are explicit lists or patterns. Human decisions go both ways: `exclude`
   and `keep` (despite a flag or against automated pruning), as grouped lists with one note per group
   (whether a note is required: OD-10). Automated decisions are *not* written into the config as
   outcomes: the config holds the rules that make them (ordered, named steps, like eligibility), and
   their outcomes live in the feature ledger and the frozen config (D-058).
8. **Time:** observation window, target window, validation month and inference month. Validated at
   load:
   - window order;
   - `v ≥ tk + w` (no overlapping target windows);
   - backward windows fit the available history (default ≤ 6 months).
9. **Data-definition hash:** computed from entity, source, eligibility, target, time and candidates.
   It keys the EDA and Feature Checks artifacts that training requires (D-031). It assumes a source
   month never changes after loading (`CLAUDE.md` §4.10).
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
- How a use-case extension function is referenced, and where its code lives (OD-05).
- The config lifecycle from Target Factory to promotion: persisting human decisions without
  multiple config versions, including the flag case (OD-10).
- Profile defaults per stage (set as each stage is built).
- Identities, to specify when the config is built (M2):
  - the config hash covers the frozen config, including `conf/local/` values (paths, tables), so
    the same use case hashes differently on a laptop and in the bank. Hash only the use-case
    definition?
  - the data-definition hash includes the whole `time` section, including the validation and
    inference months. Every monthly scoring run and every sweep variant would then need fresh EDA
    and Feature Checks (D-031). Which time fields belong in it, and should the inference month be a
    run argument rather than config?
  - `run_id` = config hash + timestamp, but one config covers several entities, so it isn't unique
    per instance.
