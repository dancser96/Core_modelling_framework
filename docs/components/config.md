# Config spine
**Status:** built (M2.1, 2026-10-26); the Stage 2 fields, the template, the example configs and the
`keep` rename built 2026-11-03 (Stage 2 m1.1), the audit log's `findings`, `flag`, `run`, the held
set and the paths built 2026-11-03 (m1.2); the Stage 3 config sections (`training`, `evaluation`,
`decision.metric` and `baselines`, `features.order`), the `run` and `sign_off` entries and the
loggable training and evaluation settings built in M2.3 major step 1 (2026-11-13/14), in place,
for the EDS's review; Evaluation (major step 3) added no field and one load refusal, a baseline
form named twice; `schema_version` stays 1 (no bumps in 0.x until user testing, D-136
extending D-007 (c)) ·
**Legacy:** `configs/_schema.py`, `configs/_TEMPLATE.yaml`
**Related:** [dataset](dataset.md) (time model, frames, the model input) · [feature ledger](feature_ledger.md) ·
[model bundle](model_bundle.md) (the run folder, `run.json`, the run's hashes) · [training](training.md) ·
[evaluation](evaluation.md) · [lifecycle](lifecycle.md) · [run modes](run_modes.md) ·
[environment](environment.md) (the environment file) · [target factory](target_factory.md) (the
target spec) · D-006, D-007, D-020, D-021, D-023, D-024, D-030, D-031, D-032, D-034, D-043, D-047,
D-050, D-052, D-088, D-091, D-125, D-128, D-129, D-130, D-131, D-132, D-133, D-134, D-135, D-136,
D-139, D-140, D-141 · [eda](eda.md) · [feature checks](feature_checks.md) · OD-02, OD-26

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
| `decision` | Training, Evaluation (EDA: `type`, `n`) | How the scores are used; the metric and the baselines, derived from it or overridden, all declared before any result (`CLAUDE.md` §4.3) |
| `entities` | every stage | Which entities the use case applies to; their logical sources |
| `data` | every stage | Keys, eligibility, target, the client split, the contract band, the saved model input |
| `time` | every stage | The unit of analysis (`period`), the observation window, `w`, the validation period (may be null: an EDA-only config) |
| `features` | every stage | The candidates (patterns), the kind overrides and the declared level orders |
| `strata` | EDA, Evaluation, Monitoring | The stratification variables, level cap, minimum events (D-038) |
| `eda` | EDA | The snapshot, the bins, the key features |
| `feature_checks` | Feature Checks | The five steps' thresholds, one typed mapping |
| `training` | Training | Modelling path, model families, the trial budget (in total or per family), the seed, the client folds and their repeats, the objective, monotone constraints, search ranges, automated selection, categoricals, calibration, sampling |
| `evaluation` | Evaluation (slices: EDA too) | Metric slices, the views to leave out, the intervals |
| `inference` | Inference | Which model version scores |
| `monitoring` | Monitoring | Drift thresholds, the outcome join, the retrain policy |

**The layout**, with the walking skeleton's `cc_acquisition` values (`conf/base/cc_acquisition.yml`;
the template with every option's when-to-use is `conf/base/TEMPLATE.yml`). A second example,
`conf/base/td_acquisition.yml` (term deposit), shares its model input: same sources, keys,
period and `model_input`, its own target and eligibility. A `null` on a level
path (`levels.py`) takes the level default; any other `null` is off or derived (the template's
reading key). `features.kinds`, `eda` and `feature_checks` show the Stage 2 defaults and
`decision.metric`, `decision.baselines`, `features.order`, `training` and `evaluation` the Stage 3
defaults ([the modelling fields](#the-modelling-fields-stage-3)), as the template does; the two examples write `{}` for each Feature Checks step (its
defaults, `stability`'s PSI flag at 0.25 being Monitoring's drift threshold).

```yaml
schema_version: 1
task: binary
use_case: cc_acquisition                 # letters, digits, _ and -; compared ignoring case (D-128)
domain: retail
automation_level: assisted               # autonomous | assisted (D-023)

decision:                                # declared before any result; never changed through the audit log (CLAUDE.md §4.3)
  type: probability                      # top_n | threshold | ranking | probability; scores compared across products (D-049)
  n: null                                # top_n only: the list size; refused under another type
  metric: null                           # null = log_loss (probability, threshold), roc_auc (ranking, top_n); regression rmse
  baselines: [population_base_rate, single_feature]   # + {previous_model: <column>}, {historic_predicted_rate: <number or column>}

entities:                                # only the entities this use case applies to; data never merged (D-034)
  entity_a:
    sources:
      features:                          # ordered: the first is the governing spine, the rest left-join to it
        - retail_mart                    # a plain name: keys named as in data.keys
        - {source: retail_fs_extract, keys: {unit_id: customer_no, period: as_of_date}}   # own key names
      # features: [feature_store]                   # the feature-store settings ship commented out (D-021)
      # features: [feature_store, retail_mart]
      targets: retail_holdings           # left-joins to the spine; omit when the target is a feature-source column

data:
  keys: {unit_id: client_id, period: snapshot_month}   # the spine's key names (and any source's without its own); renamed to unit_id, period at load; the id cast to string
  model_input: retail_acquisition_input  # optional: the saved model input's logical name, shared with td_acquisition (D-131); omit = build in memory
                                         # one table may serve several use cases (run a.yml b.yml --stages target_factory)
  eligibility:                           # two ordered Spark SQL lists; filters log rows in -> out
    analysis:                            # rows dropped before EDA
      - {name: has_income, define: "income IS NOT NULL"}
      - {name: income_known_or_salaried, filter: "has_income OR salary_transfer_flag = 1",
         reason: "card rules need a known income"}
    modelling:                           # kept for EDA, tagged 0/1; dropped before Feature Checks
      - {name: non_holders, filter: "cc_flag = 0",
         reason: "acquisition is scored for clients without a card"}
  target:
    rule: flag_goes_up                   # the flag is 1 in some period of t+1 … t+w and 0 at t
    column: cc_flag                      # excluded from the candidates (lineage)
  split: {test_share: 0.3, seed: 42}     # by client, seeded hash; applied from Training on (D-030)
  rate_band: {max: 0.5}                  # contract check on the true population; no floor

time:
  period: month                          # the unit of analysis: month | week | day; one row per unit per period
  observation_window: {first: 2025-03-01, last: 2025-08-01}   # t1 … tk; a period is held as its last day
  target_window: 3                       # w: targets look at periods t+1 … t+w (D-129)
  validation_period: 2025-11-01          # v ≥ tk + w, by period index; v + w ≤ the sources' last period;
                                         # null allowed (an EDA-only config): EDA runs, Training refuses

features:
  # exclude: list every column that looks forward from the period (other use cases' targets,
  # 'next N months' flags; CLAUDE.md §4.1); lineage and unsupported types leave automatically
  candidates: {include: ["*"], exclude: []}             # glob patterns over the feature sources' columns
  kinds: {}                              # {<column>: numeric | categorical}; overrides the Spark-schema default
  order: {}                              # {<feature>: [levels, lowest first]}: an ordered categorical, encoded by position

strata:
  variables: [segment, onboarding_channel]
  max_levels: 10                         # the rest pooled as `__other__`; a numeric deep dive's groups
  min_events: 50                         # fewer positive events in a stratum (regression: units with a non-zero target): shown as insufficient (D-082; Evaluation counts positive rows, so pooled over periods an outcome counts once per period whose window holds it); also the shrinkage weight of the level encoding

eda:
  snapshot: last                         # last (the window's last period) | a period inside the window
  bins: 100                              # quantile bins for every numeric; null = binning off, every value
                                         # its own bin and every statistic exact (small populations)
  # top-N of the ranking plus the listed ones; a candidate associated above max_correlation
  # with a chosen key feature is skipped and shown as represented by it
  key_features: {top_n: 10, include: [], max_correlation: 0.9}

# The five steps run in a fixed order; a step left out of a present mapping is not run, the section
# left out runs every step with its defaults. Every threshold is a loggable leaf, the same at both
# levels. Flags hold a feature out of training until a person decides; notes inform (D-134).
feature_checks:
  # quality: all-null, constant, near-constant, high-missing, high-cardinality (flags); two null
  # notes
  quality:        {dominant_share_max: 0.99, missing_share_max: 0.95, max_levels: 50,
                   nulls_may_be_zeros: {missing_min: 0.2, zero_share_max: 0.005}, nulls_informative_min: 0.55}
  # leakage: too strong, missingness leak, rare-value leak (flags); rare_effect_max: beside a
  # value on ≥ dominant_share_min of the filled rows, the others' rate (mean) above its by this
  # Cohen's h (binary) or d (regression): 0.2 small, 0.5 medium, 0.8 large (feature_checks.md)
  leakage:        {concordance_max: 0.80, null_concordance_max: 0.70, rare_effect_max: 0.8,
                   dominant_share_min: 0.90}
  # time alignment: signal lost when lagged one period; constant within the client and predictive (flags)
  time_alignment: {signal_kept_min: 0.5, constant_clients_min: 0.99, concordance_min: 0.6}
  # stability: power unstable across the window (flag; the range at least concordance_range_min
  # × |concordance_window − 0.5| and at least concordance_range_floor); PSI a note from
  # psi_note_min, a flag from psi_max (Monitoring's drift threshold); new levels (note)
  stability:      {psi_note_min: 0.10, psi_max: 0.25, heterogeneity_p_max: 0.01,
                   concordance_range_min: 0.5, concordance_range_floor: 0.05,
                   new_level_share_max: 0.01}
  # redundancy: correlated and associated pairs, shown as clusters (notes)
  redundancy:     {correlation_max: 0.90, association_max: 0.90}

training:
  path: automl                           # FLAML, the only path in Phase 2 (D-020)
  estimator_list: [lgbm, xgboost, xgb_limitdepth, catboost]   # the families searched, FLAML's names; one entry fixes the family
  max_iter: null                         # the run's trial budget, split over the families: 60 autonomous, 200 assisted (D-132)
  trials: null                           # {<family>: trials}: names every listed family and replaces max_iter
  time_budget_s: null                    # a cap per family; with it a run is reproducible to the recipe, not the model (D-094)
  seed: 42                               # every seeded step of Training; never set through the audit log
  folds: 5                               # the train split's client folds (cv_fold)
  fold_repeats: 1                        # further dealings (cv_fold_2, …); 3 below 100 converting clients or 200 events
  objective: null                        # null = log_loss (binary), squared_error (regression); tweedie | poisson | absolute_error | huber
  tweedie_variance_power: null           # tweedie only: 1.5 by default, between 1 and 2
  monotone: {}                           # {<feature>: increasing | decreasing}: numerics and ordered categoricals
  search_space: {}                       # {} = the bounded ranges; {<family>: {<parameter>: {low, high, log, integer, start} | {value}}}
  selection:                             # automated feature selection, by rule, on the train split only (D-140)
    cluster: true                        # one representative per redundancy cluster
    floor_z: 2.0                         # dropped below a train concordance of 0.5 + z · SE; null = off
    prune: true                          # importance pruning against noise columns
  categoricals:
    min_level_client_count: 50           # a level seen in fewer distinct train clients → __other__
    unordered: native                    # native: declared to the library | codes: the same integers as numbers
  calibration: {method: null}            # null = binary platt for a probability decision, else none; regression mean for
                                         # tweedie and poisson, else none; platt | beta | none (binary), mean | none (regression)
  sampling: null                         # null | {method: negative_downsampling, keep_fraction: 0.1}  (binary only)
                                         #      | {method: client_sample, share: 0.3}  (D-117); the draw uses `seed` above

evaluation:
  slices:                                # cut inside each period
    top_pct: null                        # level: autonomous [0.01, 0.1], assisted [0.01, 0.05, 0.1]
    top_n: []                            # list sizes, each a share of one period's eligible population
  skip_views: []                         # the report's views to leave out, by name; every view renders by default, the summary always
  intervals: {replicates: 200, level: 0.95}   # the client bootstrap's replicates and the interval's coverage (D-141)

inference:
  model: production                      # production | a registered model version (a pin)

monitoring:
  drift: {psi_max: 0.25}
  outcome_join: true                     # join matured labels to the scores (D-054)
  retrain_policy: {max_age_months: null, psi_flags: null}   # sets "retrain recommended" (monitoring.md)
```

**Model input.** `data.model_input` names, by logical name, the one saved table every stage after
Target Factory works from; the environment file maps the name to a path or table. One table may
serve several use cases that share the entity's feature sources, `data.keys` and `time.period`
(`run a.yml b.yml --stages target_factory`): it holds the sources joined plus one target column
per use case, and eligibility, the candidates, the contract checks and the client split are
derived on read from each reader's config. Without the field the same frames are built in memory.
What it holds, what its reader refuses and when it is written: [dataset](dataset.md#model-input-d-131)
(D-131).

## The modelling fields (Stage 3)
Every field Training and Evaluation read, with its default, what it sets and whether a `set`
entry of the audit log may change it. "Reruns from" is the stage a `set` reruns
(`LOGGABLE_SETTINGS`). A `null` default is filled at load and again at every replay, so the
resolved config always states the value in force and a `set` on `training.objective` refills
`calibration.method`; the per-task allowed values and defaults are the plain dict `TASK_CHOICES`
(`schema.py`). The fields change in place, with no `schema_version` bump (D-136).

**The shared sections**

| Field | Default | What it sets | Loggable (reruns from) |
|---|---|---|---|
| `decision.metric` | `null`: `log_loss` for `probability` and `threshold`, `roc_auc` for `ranking` and `top_n`; `rmse` for regression | The search metric and the headline metric. Binary allows `log_loss`, `roc_auc`, `ap`; regression `rmse`, `mae`, `r2`, `tweedie_deviance`, `poisson_deviance`. Checked against the task at load. The Tweedie deviance is computed at a fixed variance power of 1.5. A deviance needs `training.objective: tweedie` or `poisson` (their predictions are always positive): any other objective with it is refused at load | never (§4.3) |
| `decision.baselines` | `[population_base_rate, single_feature]` | What Evaluation compares the model with: `population_base_rate` (the train mean for regression), `single_feature` (the best single feature by train concordance), `{previous_model: <column>}` (a score column of a source), `{historic_predicted_rate: <number or column>}` (a number is one rate in use; a column is judged like a previous model). Each form at most once, checked at load | never |
| `features.order` | `{}` | `{feature: [levels, lowest first]}`: the feature is an ordered categorical, encoded as its position in the list. A train level missing from the list fails loud; a name that is no candidate, or no categorical, is refused when the frames are built | yes (Training) |

**`training`**

| Field | Default | What it sets | Loggable (reruns from) |
|---|---|---|---|
| `path` | `automl` | FLAML, the only path in Phase 2 (D-020) | no |
| `estimator_list` | `[lgbm, xgboost, xgb_limitdepth, catboost]` | The families searched, by FLAML's names; one entry fixes the family | yes (Training) |
| `max_iter` | by level: 60 at `autonomous`, 200 at `assisted` | The trial budget of the run, split equally over the listed families, the remainder to the first ones | yes (Training) |
| `trials` | `null` | `{family: trials}`: a budget per family. When set it names every listed family and replaces `max_iter` | yes (Training) |
| `time_budget_s` | `null` | A cap in seconds per family. With it a run is reproducible to the recipe, not the model (D-094) | yes (Training) |
| `seed` | `42` | Every seeded step of Training | never (a test score must not pick its seed) |
| `folds` | `5` | The client folds of the train split (`cv_fold`) | yes (Training) |
| `fold_repeats` | `1` | Further dealings of the folds; every trial is judged on all of them. For few events (below 100 converting clients or 200 events): `3` | yes (Training) |
| `objective` | `null`: `log_loss` for binary, `squared_error` for regression | How the booster learns. Regression allows `squared_error`, `tweedie`, `poisson`, `absolute_error`, `huber`; binary `log_loss` only. For an amount with many zeros and a long tail: `tweedie`, with `decision.metric: tweedie_deviance`. `absolute_error` together with `monotone` is refused at load (T43): use `huber` | yes (Training) |
| `tweedie_variance_power` | `null`: 1.5 under `tweedie` | The objective's variance power, between 1 and 2. Refused with another objective | yes (Training) |
| `monotone` | `{}` | `{feature: increasing \| decreasing}`, on numeric features and ordered categoricals; applied to every fit of the run. A constraint on an unordered categorical is refused when Training starts | yes (Training) |
| `search_space` | `{}`: the bounded ranges of [training](training.md) | `{family: {parameter: leaf}}`; a leaf is `{low, high, log, integer, start}` (a range, `start` optional) or `{value}` (a constant). An entry replaces one leaf of the family's default space | yes (Training) |
| `selection.cluster` | `true` | The cluster rule: one representative per redundancy cluster | yes (Training) |
| `selection.floor_z` | `2.0` | The floor: a feature is dropped below a train concordance of 0.5 + z · SE. `null` switches it off. Below about 300 converting train clients use 1 or `null` (`training.md` → the floor) | yes (Training) |
| `selection.prune` | `true` | Importance pruning against noise columns | yes (Training) |
| `categoricals.min_level_client_count` | `50` | A level seen in fewer distinct train clients joins `__other__` | yes (Training) |
| `categoricals.unordered` | `native` | `native`: unordered categoricals are declared to the library; `codes`: the same integers passed as numbers | yes (Training) |
| `calibration.method` | `null`: binary `platt` for a `probability` decision, else `none`; regression `mean` for `tweedie` and `poisson`, else `none` | `platt`, `beta` or `none` for binary; `mean` or `none` for regression. The prior-shift offset applies under every method whenever sampling happened (`CLAUDE.md` §4.7) | yes (Training) |
| `sampling` | `null` | `negative_downsampling` (binary only) or `client_sample` (D-117), each with its one parameter. The draw uses `training.seed`: the sampling has no seed of its own, since it is loggable and a seed must not be picked after results | yes (Training) |

**`evaluation`**

| Field | Default | What it sets | Loggable (reruns from) |
|---|---|---|---|
| `slices.top_pct` | by level: `[0.01, 0.1]` autonomous, `[0.01, 0.05, 0.1]` assisted | Shares of the ranking, each in (0, 1], at which the metrics are cut; the slices are cut inside each period | yes (EDA, which shows the decision slices) |
| `slices.top_n` | `[]` | A `top_n` is a share of one period's eligible population | yes (EDA) |
| `skip_views` | `[]` | The report's views to leave out, by name (the list below). Every view renders by default and the summary always. Change it to leave out views you do not need. A name that is no view, or `summary`, is refused when Evaluation starts, before anything is scored, with the list of valid names | yes (Evaluation) |
| `intervals.replicates` | `200` | The client bootstrap's replicates, at least 20 (fewer give no usable percentile interval). More steady the bounds' last digit and cost time; fewer speed a draft run | yes (Evaluation) |
| `intervals.level` | `0.95` | The interval's coverage, strictly between 0 and 1 | yes (Evaluation) |

The names `skip_views` accepts, the same for both tasks (the report and its views:
[evaluation](evaluation.md)):
- core: `metrics`, `curves`, `capture`, `reliability`, `score_distribution`, `strata`,
  `importance`, `beeswarm`, `effects`, `waterfalls`, `sign_off`, `search`;
- extended: `thresholds`, `permutation_importance`, `pdp_ice`, `validation_test_clients`.

`curves`, `score_distribution` and `thresholds` are not available for regression (the target is
an amount, without classes): they render as that one line, and skipping them changes nothing.

**Gone,** each refused at load as an unknown key: `decision.gate_metric` and the `lifecycle`
section (no gates, D-032; the section returns when M2.4 gives it content);
`training.selection.univariate_floor` (replaced by `floor_z`) and `importance_floor` (nothing
read it); `training.categoricals.min_level_count` (replaced by `min_level_client_count`);
`evaluation.views` (replaced by `skip_views`); `training.sampling.seed` (the draw uses
`training.seed`). The calibration method `isotonic` is refused as a
method the task does not allow.

**Refused at load,** each naming the field:
- a `decision.metric`, a `training.objective` or a `calibration.method` the task does not allow;
- a family listed twice in `training.estimator_list`; `training.trials` that does not name
  exactly the listed families;
- a `training.search_space` entry for a family that is not listed; a leaf that is neither a
  range nor a constant, or whose `start` lies outside its range;
- a class-weight parameter in `training.search_space` (`scale_pos_weight`, `is_unbalance`,
  `class_weight`, `class_weights`, `auto_class_weights`, in any case): it changes the class
  balance without the calibration knowing, so the message points to
  `sampling: negative_downsampling`. A library alias of one of them is caught when Training
  starts, where every parameter name is checked against the family's allowed set;
- a name the framework owns in `training.search_space`: the objective, the seed, the thread
  count, the constraints and the categorical declarations (`objective`, `loss_function`,
  `random_state`, `n_jobs`, `monotone_constraints`, `categorical_feature`, `missing` and their
  like). They are set by `training.objective`, `training.seed`, `training.monotone` and the
  encoder; a searched constant would train one thing while the bundle scores another;
- LightGBM's `monotone_constraints_method: advanced` (it broke the constraint when measured),
  and `intermediate` together with `colsample_bynode` (LightGBM would fall back to `basic` with
  only a warning);
- a `features.order` list that is empty or repeats a level.

**Who reads what, for the stage digests** (`artifacts.SETTINGS_PATHS_BY_STAGE`; a stage's stored
artifacts are stale when a value under its paths changed):

| Stage | Its digest covers |
|---|---|
| EDA | `features.kinds`, `strata`, `eda`, `time.validation_period`, `decision.type`, `decision.n`, `evaluation.slices` |
| Feature Checks | EDA's paths and `feature_checks` |
| Training | `training`, `data.split`, `features.order`, `features.kinds`, the feature decisions (`features.excluded`, `kept`, `held`), `decision.type`, `decision.metric` |
| Evaluation | `evaluation`, `data.split`, `decision`, `strata` |

Evaluation finds its run by the data-definition hash and Training's digest, so changing an
evaluation setting or a baseline never orphans a trained run (D-139). The client split is in
both digests although it sits outside the data-definition hash: a run trained under one split
and evaluated under another would be scored on its own train clients.

## Phase 2 requirements
1. Every config has `schema_version` and `task` (`binary` or `regression`; any other value is
   refused at load). From release 1.0, a field that gains a new accepted form (as `sources.features`
   accepting `{source, keys}`) also bumps `schema_version`, so an older framework refuses the config
   by its version, not with a type error.
2. Load = the config file, migrated, the level defaults applied, validated with Pydantic v2
   (unknown keys fail loud, so a leftover `profile:` can't fall back to a default level); the
   **environment file** loaded beside it, under its own schema and never merged into the config
   (D-130; [environment](environment.md)); then the decision audit log's entries replayed into the
   **resolved config**, saved with every artifact and report (resolved values, including level
   defaults and the entries replayed). The resolved config is plain data (YAML, D-043); the
   config itself is never edited afterwards, since decisions taken later are entries in the
   decision audit log (D-125, section below). The resolved config carries a **housekeeping
   block** (`resolve_config`):
   - the framework version (`framework_version`) and when it was resolved (`resolved_at`);
   - the environment values the run used (`environment`: the physical sources, roots, Spark
     settings and the collect budget), since they sit outside every hash (D-130);
   - the identities: the entity, the config, data-definition and resolved-input hashes with
     `hash_version`, the last entry replayed (`replayed_to`) and the fields the level filled
     (`level_filled`); the nulls the task filled are recorded as `task_filled` (path → value). The
     hashes exclude this block, so they don't depend on themselves.
   - A Training run is identified by its run number and its `run.json`, which records the
     hashes it was built from, the entity, who started it and when, outside the resolved config
     ([model bundle](model_bundle.md#runjson), D-139); EDA and Feature Checks identify a run by
     its `run_token` in their stage json.
3. **Automation levels** (`autonomous` / `assisted`; `manual` later) set defaults for every
   stage; explicit fields override (D-023). The field is `automation_level`; `profile` is
   refused as an unknown key, with no migration since 0.x promises nothing (D-007 (c)). The same checks run
   at every level, differing in what is decided by rule and what by a person. A level changes
   through a config edit before the config freezes and through a `set` entry in the audit log
   after it, never a CLI override (D-023; the mapping per decision point: D-132, the table
   below).
4. **Business decision** (e.g. `top_n`, `threshold`, `ranking`, `probability`; other tasks add their
   own). It derives:
   - the metric: the search metric and the headline metric (D-140 (d));
   - a binary task's default calibration method (D-049, D-132);
   - what reports emphasise.

   The metric can be overridden in `decision.metric`, among the names the task allows, which are
   FLAML's (T9), and never through the audit log; no gate is built on it: the report and the card
   show the model against each declared baseline (D-032; [the modelling
   fields](#the-modelling-fields-stage-3)).
5. **Entities and sources:** a use case lists the entities it applies to (often one), each with
   its logical sources. Sources differ by domain and often by use case. Nothing runs or compares
   across entities by default (D-034). Per entity, `sources.features` is an **ordered list**: the
   first source is the **governing spine**, and the others are left-joined to it on the keys;
   `sources.targets` is one source, left-joined to the spine and contributing only the target,
   omitted when the target is a column of a feature source (D-129; the join rules:
   [dataset](dataset.md#sources-and-joins-d-129)). Each entry is a logical name, or
   `{source, keys}` for a source whose key columns are named unlike the spine's `data.keys`; a key
   left out falls back to `data.keys`, and the spine is always a plain name. The feature store is one more logical source, alone or
   next to a mart; the release example shows all three settings, two of them commented out, and a
   `feature_store` source is refused until OD-26 is designed (D-021). Physical names never appear
   in the config: the environment file maps each logical name per entity (D-130).
6. **Stepwise sections:** eligibility steps are ordered and named, and each produces a log entry
   (rows in → out, reason); Feature Checks' five steps run in a fixed order (quality, leakage,
   time alignment, stability, redundancy), one typed entry each in the `feature_checks` mapping,
   and each logs its findings ([feature checks](feature_checks.md)). A present mapping names at
   least one step (running no check is a mistake, `CLAUDE.md` §4.5), and
   `quality.nulls_informative_min` lies below `leakage.null_concordance_max` when both run.
   Eligibility is two ordered lists of Spark SQL entries, `data.eligibility.analysis` and
   `data.eligibility.modelling`, run as one order,
   analysis first, with step names unique across both (D-129). An entry is either a `define` (a
   named boolean condition that the entries after it, in either list, reuse by name, dropped
   before the candidates are resolved) or a `filter` with a required `reason`; a null condition
   counts as false in a filter. An **analysis filter** drops its rows before EDA (who the
   analysis sees: clients it shouldn't see at all, e.g. new clients); a **modelling filter**
   keeps its rows for EDA, tagged 0/1 by the step's name (a reference group, e.g. current
   holders of the product, whom the analysis compares with the non-holders), and drops them
   before Feature Checks. The modelling tag is a stratification column for EDA
   ([dataset](dataset.md), [eda](eda.md)). A source column named like one the framework adds
   (`unit_id`, `period`, `target`, `split`, `eligible`, `part`, `cv_fold`) is referred to as `source_<name>` in
   eligibility, the candidate patterns, strata and decisions (a decision naming the framework's
   own column is refused with that hint); `data.target.column` alone names an upstream target
   as the source does, `target` included, never a key name
   ([dataset](dataset.md#sources-and-joins-d-129)).
7. **Features:** candidates are explicit lists or patterns; `features.kinds` overrides a column's
   kind (`numeric` or `categorical`; the default comes from the Spark schema, [eda](eda.md)), and
   an override naming a column that is not a candidate fails loud; `features.order` declares an
   ordered categorical's levels, lowest first ([the modelling
   fields](#the-modelling-fields-stage-3)). Human decisions go both ways:
   `exclude` (out of every later run), `include` (reverses an exclude) and `keep` (settles the open
   flags it names and protects from automated pruning; D-134). They are entries in the decision
   audit log, one per group with one required reason, never edits to the config (D-043, D-125).
   Automated decisions are *not* written into the config as outcomes: the config holds the rules
   that make them (named steps and their thresholds). Feature Checks' outcomes are `flag` entries
   in the log and columns in the feature ledger; automated selection's drops are rows of the
   per-run ledger only (D-043, D-125 (c)). `features.kinds`, `features.order`, every `eda` field,
   every `feature_checks` threshold and the training and evaluation settings the modelling fields
   mark loggable are loggable at their stage (`set`, the list below), so a reassessment reruns
   from that stage.
8. **Time:** `time` holds the unit of analysis (`period`: `month`, `week` or `day`; one row per
   unit per period, the key column `period`), the observation window (`observation_window
   {first, last}`), the target window `w` (`target_window`, in periods, one number read by the
   target builder and the time checks alike) and the validation period (`validation_period`);
   the inference period is a run argument (D-088, D-129). The validation period may be `null`, an
   EDA-only config: EDA runs, Feature Checks compares with the latest period only, and Training
   refuses, naming the field; a later `set` entry or a new config adds it. It sits outside the
   data-definition hash (EDA and Feature Checks read it only to leave it out of the compared
   periods), so moving it never changes the data-definition hash. After the config freezes,
   the validation period changes only through a `set` entry in the audit log, refused when any
   Feature Checks `run` entry lists that period among the periods it compared (D-088;
   [feature checks](feature_checks.md); Training's and Evaluation's `run` entries never block
   it) and when it sets `null`: a frozen training config does
   not become EDA-only through the log, so `null` is written in the config file. A Phase 2
   production retrain moves only the inference period (D-052).
   A period is held as its **last day**, the framework's one convention. The typo rule at load
   depends on `time.period`: a month is written as its first or its last day (any other day is
   refused as a likely typo), a week as any of its days, a day as itself; the three dates move to
   the period's end, and the dataset moves every source's period column to the period's end on
   reading (D-129; [dataset](dataset.md#sources-and-joins-d-129)). Period arithmetic goes
   through one dict of period specs (`periods.PERIODS`), never `add_months` or added days (T19).
   Checked at config load (D-129):
   - window order (`first ≤ last`) and `w ≥ 1`;
   - `v ≥ tk + w` by period index (no overlapping target windows), when `v` is set;
   - `eda.snapshot` is `last` or a period inside the observation window.

   Checked when the frames are built, since only the data knows ([dataset](dataset.md)):
   - the window and `v + w` lie inside the sources' periods, so every validation label has
     matured (otherwise partial maturity would null validation labels quietly); with `v` null,
     the window's last period plus `w`. This replaces the
     backward-window check, which the framework can't make for upstream features.
9. **Data-definition hash:** computed from `task`, entity, sources, keys, eligibility, target spec,
   the period, the observation window, the target window and candidates (D-088; the section
   below). It keys
   the EDA and Feature Checks artifacts that training requires (D-031). It assumes a source
   period never changes after loading (`CLAUDE.md` §4.10); training recomputes the per-period
   row and positive counts on every client of the window after the analysis filters, before the
   client split, and fails loud when they differ from the EDA artifact's.
10. **Model key** (entity, domain, use case, split) is derived from the config; split = `all` in
    Phase 2.
11. **Downstream sections exist from v1** (inference, monitoring), even while those stages are
    thin, so adding depth later doesn't break configs. `lifecycle` returns with M2.4, when it has
    content; an optional section added with defaults breaks no config.
12. **Strata:** one `strata` section (variables, a cap on levels, a minimum number of positive
    events per stratum) shared by EDA, Evaluation and Monitoring (mandatory reporting, D-038;
    D-129).
13. **Metric slices:** `top_pct` and `top_n` lists; either may be empty. EDA reads them too:
    each key feature alone at the slices, a view and never a baseline, with `decision.n` as the
    first slice for a `top_n` decision ([EDA](eda.md) "At the decision's slices").
14. **Templates guide:** the base template lists every option with a one-line when-to-use, and
    validation errors say how to fix the problem. Its header key says how to read a line
    (`# required`; a plain value is the default; `null · level:` names both levels' values) and
    where a comment sits: a short comment on the line it explains, a longer one right above its
    key, and a level line always names both levels' values inline. A test checks every schema
    field against the template, so an omitted value's default is always on display.
15. **Migrations:** small functions `migrate_vN_to_vN+1(dict) -> dict`, applied automatically with a
    deprecation warning.

## Decision audit log (D-125)
**Decided (settles the audit-log design; amends D-043 and D-088); built in Stage 1's major step 1.** The EDS
and LDS build from this section.

**The model.** The config is the intent. Its **data part** (sources, keys, period, target spec,
target window) is frozen once the model input is saved, or at the first EDA run when the frames
are built in memory; the rest of the data definition (eligibility, the observation window,
candidates) changes only by a new config, which reruns EDA onwards but keeps the saved table
(D-125, D-131). Every later decision, by a person or a rule, is an append-only entry in the
decision audit log. Replaying the config plus entries 1–n gives a run's one input, the
**resolved config**, validated by the same Pydantic schema. The log never changes the data
definition (entity, sources, eligibility, target spec, period, window, candidates): changing it
means a new config, with fresh EDA and Feature Checks. Entries are never edited; a reversal is a
new entry, feature by feature (`include`) or back to an earlier state as a whole (`revert`). The
feature ledger is the same trail read per feature ([feature ledger](feature_ledger.md)).

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
| person | `keep`: settles the open flags it names (`findings`), each open on every feature it names; by default the features' open flags, which must then be the same on each (else one keep per finding set); also protects from automated pruning | changes the input |
| person | `set`: change one listed setting (next section) | changes the input |
| person | `revert`: go back to the state after an earlier entry (`to_seq`; 0 is the config as written) | changes the input: replay takes that stored state |
| person | `sign_off`: approve a run's final feature list (D-031). It holds the run number (`run_id`), the feature signature and the final list, and covers every run of the same data definition whose final list has the same signature, earlier ones included: a person defends features, not hyperparameters. Written by `sign_off(cfg, entity, env, run, reason)` or `decide --sign-off --run r007 --reason …` | trail |
| person | `register`, `promote`: written by those commands | trail |
| rule | `exclude`: none written in Phase 2 (lineage and unsupported types leave through the candidate resolution, never as entries; D-134) | changes the input |
| stage | `flag`: written by Feature Checks, one per finding (`finding: <step>.<finding>`) with its features, only when that set differs from the finding's latest entry; an empty set closes the finding | changes the input: replay writes the open flags' features into `features.held`, which Training holds out of its feature set ([feature checks](feature_checks.md), D-134) |
| stage | `run`: a marker with the entry it replayed up to and the input hash. Feature Checks' carries the `periods` it compared (D-088); Training's carries the run number (`run_id`) and no periods; Evaluation's carries the run number and, in `validation_period`, the validation period it scored | trail |

- Only `exclude`, `include`, `keep`, `set`, `revert` and `flag` (through `features.held`) change
  the resolved input; the rest are the trail and are no-ops at replay. Automated selection's
  drops are no entries: the per-run ledger is their one record, with the rule, the value and the
  threshold ([feature ledger](feature_ledger.md), D-125 (c)). A flag stays open on a
  feature until a `keep` naming that feature and its finding settles it, an `exclude` takes the
  feature out, or the finding's latest `flag` entry no longer lists the feature. A `keep` stores
  only (feature, finding) pairs open when it is written: each finding it names must be open on
  every feature it names, so a keep never settles in advance a finding raised later on another
  of its features; a `findings: []` named while flags are open on its features settles nothing
  and is refused. Notes are never entries: they live in Feature Checks' findings table. Which
  findings are flags and how the hold-out works: [feature checks](feature_checks.md) (D-134).
- A `revert` entry, `{op: revert, to_seq: 8, reason}`, goes back to an earlier state without
  deleting anything: at replay the state becomes the state after entry 8, and the entries after
  the revert continue from there. The undone entries stay in the log as the trail, and
  `resolve_config(upto=n)` still reproduces every earlier state (`to_seq: 0` is the config as
  written; a revert inside the reverted range is honoured in turn). It is written
  with `record_decision(…, revert_to=8, reason=…)` or `decide --revert-to 8`, exactly one of
  the five operations; it is refused unless `to_seq` is an earlier state than the current one
  (0 … n−1), and it carries no features, path, `from` or `to` (no other operation takes
  `to_seq`). The state it brings back is checked like a `set` of the validation period: refused
  when it moves the validation period to `null` or to one a Feature Checks `run` entry lists
  (D-088). Its default stage is the first undone entry's, overridable with `stage=`.
  `show_decisions` shows `to #8` in `what`; the resolved file's header adds one line per
  revert, `# entry 14 reverted to the state after #8`, and its per-value origins are those of
  the entries still in force. `log_schema_version` stays 1: a new op, old entries read as
  before.
- Rejecting features at sign-off is an `exclude` entry with stage `sign_off`, and the model is
  retrained without them. The sign-off in force for a run is the latest effective `sign_off`
  entry with the run's feature signature (`signed_off`), so a higher budget or another family
  with the same features needs no new entry, a changed list does, and a `revert` past the entry
  undoes it; the view of a covered run says which run was signed.
- `include` reverses a person's `exclude` only, feature by feature: each named feature must be
  excluded now and last by a person's entry, so it may restore any subset of an earlier entry's
  features. The check runs over the **effective** entries (every `revert` applied): `include`
  is refused when any effective entry is a rule's `exclude` of the feature, so neither a revert
  nor a person's no-op `exclude` on top of the rule's can launder it. A rule's `exclude` is
  reversed by changing the rule (a listed threshold); lineage is never an entry and never
  reversed (`CLAUDE.md` §4.6). A flagged feature was never dropped, only held: `keep` settles
  the flag.
- A write is refused at once when a feature isn't a candidate, the reason is missing, the change
  touches the data definition, the setting isn't listed or sits under a `feature_checks` step the
  config doesn't run, the value fails the schema, `findings` comes without `keep`, names a flag
  not open on every one of the keep's features or is `[]` while flags are open on them, a
  default keep's features have different open flags, or a `set` or a `revert` moves the
  validation period to `null` or to one a Feature Checks `run` entry lists (D-088). At replay,
  `resolve_config` refuses as stale a resolved validation period that a replayed Feature Checks
  `run` entry lists, so a hand-written entry is caught too; Training's and Evaluation's `run`
  entries are never read for it.
- An entry's evidence may cite train and test results only: the validation period never informs a
  choice (`CLAUDE.md` §4.4).

### Which settings a `set` may touch, and maintaining the list
`LOGGABLE_SETTINGS` is a plain dict in `config/replay.py`, mapping each allowed setting path to its
stage. The list (the training and evaluation leaves are the rows [the modelling
fields](#the-modelling-fields-stage-3) mark loggable, each at the stage it reruns from):

```python
LOGGABLE_SETTINGS = {
    "automation_level": "eda",  # a level move reruns every stage from EDA (D-132)
    "features.kinds": "eda",  # how a column is read; outside the data-definition hash
    "strata.variables": "eda",
    "strata.max_levels": "eda",
    "strata.min_events": "eda",
    "eda.snapshot": "eda",
    "eda.bins": "eda",
    "eda.key_features.top_n": "eda",
    "eda.key_features.include": "eda",
    "eda.key_features.max_correlation": "eda",
    "feature_checks.quality.dominant_share_max": "feature_checks",
    "feature_checks.quality.nulls_may_be_zeros.missing_min": "feature_checks",
    "feature_checks.leakage.concordance_max": "feature_checks",
    # ... every other threshold leaf of the five steps, 21 in all, at stage "feature_checks"
    "features.order": "training",  # the declared level orders: Training's encoder reads them
    "training.estimator_list": "training",
    "training.max_iter": "training",
    "training.trials": "training",
    "training.time_budget_s": "training",
    "training.folds": "training",
    "training.fold_repeats": "training",
    "training.objective": "training",  # how the booster learns; never the yardstick (decision.metric)
    "training.tweedie_variance_power": "training",
    "training.monotone": "training",
    "training.search_space": "training",
    "training.selection.cluster": "training",
    "training.selection.floor_z": "training",
    "training.selection.prune": "training",
    "training.categoricals.min_level_client_count": "training",
    "training.categoricals.unordered": "training",
    "training.calibration.method": "training",
    "training.sampling": "training",
    # EDA reads these (the compared periods, its decision-slices view), so they rerun from EDA
    "time.validation_period": "eda",  # refused when a Feature Checks run entry lists it (D-088)
    "evaluation.slices.top_pct": "eda",
    "evaluation.slices.top_n": "eda",
    "evaluation.skip_views": "evaluation",
    "evaluation.intervals.replicates": "evaluation",
    "evaluation.intervals.level": "evaluation",
}
```

Anything not listed is refused at write time ("this needs a new config"). Never listed: the
data-definition fields, and every `decision` field (the type, the metric and the baselines),
which are declared before any result is seen (`CLAUDE.md` §4.3), so changing the objective never
changes the yardstick; the client split and `training.seed`, since a test score must not pick
its own sample or seed, and every run in one log is compared on the same test clients (D-083);
`training.path`, the only path in Phase 2. `inference` and `monitoring` are decided with M2.4
and M4: they act after registration. Paths are leaves wherever a section holds independent knobs, so a `set` changes one
value without restating the others. A `set` names its stage; that stage and the later ones rerun
from the new resolved input. A `set` on `training.objective` also refills
`training.calibration.method`, whose default depends on it.

**Maintaining the list:**
- A field added to the schema isn't loggable until it is added to the list.
- A test checks that every listed path exists in the schema and that none is a data-definition
  field, the decision, a metric or a baseline.
- Entries carry `log_schema_version` and `hash_version`. From release 1.0, a config migration
  that renames or retypes a listed path must also bump `log_schema_version` and ship an entry
  migration, since `set` entries store the dotted path and the values in the old schema's
  terms; so must a new operation or a new entry field, since an older pinned reader refuses by
  version only. The entry version is checked before an entry is parsed, so a newer entry says
  "raise the pin" (`CLAUDE.md` §2). In 0.x neither bumps (D-007 (c)): a renamed loggable path
  leaves `log_schema_version` at 1, since old entries sit unreachable under the old
  data-definition hash's folder, and a `set` entry moved by hand fails naming its `seq`.
- The list and the decision-point table (below) are kept in step: D-132 maps the automation
  levels on the same decision points.

### From entries to code: replay
1. Load and migrate the config.
2. Apply entries 1–n in order through `APPLY_BY_OP`, in one pass that keeps the state after each
   entry. A later `set` of the same setting wins.
3. Write the three feature lists from the **effective** entries (the ones no revert undid):
   `features.excluded` and `features.kept` from `decisions_in_force` (an `include` after an
   `exclude` restores the feature), `features.held` from the open flags.
4. Validate the result with the schema and hash it: the resolved-input hash (Identities, below).

```python
APPLY_BY_OP = {
    "exclude": _leave_unchanged,   # the feature entries act through the lists of step 3
    "include": _leave_unchanged,
    "keep": _leave_unchanged,
    "set": _apply_set,
    "flag": _leave_unchanged,
    "sign_off": _leave_unchanged,
    "register": _leave_unchanged,
    "promote": _leave_unchanged,
    "run": _leave_unchanged,
}

states = [raw_config]  # states[n]: the state after entry n
for entry in entries[:upto]:
    if entry.op == "revert":
        states.append(states[entry.to_seq])
    else:
        states.append(APPLY_BY_OP[entry.op](copy(states[-1]), entry))
```

`revert` is not in `APPLY_BY_OP`: `replay` handles it itself, since it takes a stored state, not
the current one. It continues from the state after entry `to_seq` (so a revert inside the reverted
range is honoured in turn), and the cost of a replay is linear in the entries.
`effective_entries` walks the log the same way, keeping the effective entries after each entry,
and `decisions_in_force(entries)` reads them: per feature, the `keep` entries in force and the
`exclude` in force. It is the one meaning of exclude, include and keep, read by the replay, by
`open_flags` (an excluded feature is not held) and by the ledger's decision view
(`render_decisions`); the origins of each value walk the effective entries too, so the resolved
file points at the entries still in force.

- **Replaying to any point reproduces any run:** `upto` = a run marker's `replayed_to` gives that
  run's input, so an old run can be rerun or compared without guessing what was decided then; the
  entries a `revert` undid are still there for `upto` below it.
- **Stale entries fail loud:** an entry naming a feature that is no longer a candidate stops the
  replay, citing the entry number.
- **Rule and stage entries can be checked:** rerunning a stage on unchanged data writes no new
  entry. When restated data or a changed threshold changes a finding's feature set, the rerun
  appends the finding's new `flag` entry (an empty one closes it). Planned, not built (Open
  questions below): replay showing the difference and flagging the person entries that cited the
  old entry (entry 6 cites entry 3 below) for a look; today they apply as written. A `keep`
  stays valid for the same finding with new values; a different finding on a kept feature opens
  again (D-134).
- **The trail never changes the input:** run outputs, sign-offs, register and promote are recorded
  but leave the resolved config alone.

The replay code is expected to be a few dozen lines. That is a design target, not measured.

### Verbosity
- Feature Checks writes one `flag` entry per finding whose feature set changed, plus one `run`
  entry per run; Training and Evaluation write one `run` entry each per run; automated selection
  writes none (the per-run ledger).
- A person writes one entry per group, with one reason (D-043's one note per group), and one
  `sign_off` per feature list.
- So a use case's road to production is tens of entries, not hundreds; the worked example below
  has 18.
- `show_decisions` lists every entry, one row each; a default view that hides run outputs and
  resolved flags and filters by stage and by who decided is planned, not built.
- Each feature's trail is read through the [feature ledger](feature_ledger.md).

### One entry
Fields: `seq`, `time`, `by` (`kind`: person / rule / stage, plus `id`), `stage`, `op`, then
`features` (empty only in a `flag` entry, which closes the finding; in a `sign_off`, the run's
final list), `path` / `from` / `to` (`to` may be null, e.g. sampling off) or `to_seq` (a
`revert`), `finding` (a `flag`: `<step>.<finding>`), `findings` (a `keep`: the findings it
settles, each open on every feature it names when written; by default the features' open flags,
the same on each), `run_id` (the run number, in its canonical form `r001`: a `sign_off` and
Training's and Evaluation's `run` entries), `signature` (a `sign_off`: the feature signature of
the run's final list), plus `reason`, `evidence`, `data_definition_hash`, `hash_version` (the recipe
that computed it) and `log_schema_version` (still 1: the Stage 2 and Stage 3 fields change in
place, D-136). Run markers add `replayed_to` and `resolved_input_hash`. Feature Checks' adds
`periods` (the labels of the periods it compared, as `periods.PERIODS` writes them: `2025-06`,
`2025-W23`, `2025-06-15`; the label form is part of the entry format, since the
validation-period refusal compares labels) and has no `run_id` (a Stage 2 run is named by its
run token); Training's adds `run_id` and no periods; Evaluation's adds `run_id` and
`validation_period`, the label of the period it scored. An operand that doesn't belong to the
operation is refused, also when given as `null`: `features` goes with the feature operations and
`sign_off`, `path` / `from` / `to` with `set`, `to_seq` with `revert`, `finding` with `flag`,
`findings` with `keep`, `signature` with `sign_off`, `run_id` with `run` and `sign_off`, and
`periods`, `validation_period`, `replayed_to`, `resolved_input_hash` with `run`. Evidence cites earlier entries as `#n`, which is how replay finds the person entries that
cite a rule or stage entry. `finding` values are the names in Feature Checks' [finding
table](feature_checks.md#the-finding-table); a name or kind changed is a log-format change (from
1.0: bump `log_schema_version` and migrate). Entries 3 and 6 of the worked example, as stored:

```json
{
  "seq": 3,
  "time": "2026-10-27T15:10:00",
  "by": {"kind": "stage", "id": "feature_checks"},
  "stage": "feature_checks",
  "op": "flag",
  "finding": "leakage.too_strong",
  "features": ["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
  "reason": "A single feature this strong is usually the target under another name or a consequence of it.",
  "data_definition_hash": "d_A",
  "hash_version": 1,
  "log_schema_version": 1
}
```

```json
{
  "seq": 6,
  "time": "2026-10-27T15:40:00",
  "by": {"kind": "person", "id": "<user id>"},
  "stage": "feature_checks",
  "op": "exclude",
  "features": ["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
  "reason": "Set after the offer, so not known at scoring time",
  "evidence": ["#3", "feature_checks report: Leakage"],
  "data_definition_hash": "d_A",
  "hash_version": 1,
  "log_schema_version": 1
}
```

### The final config as one file
`resolve_config(cfg, entity, env, upto=None, save_to=None)` returns the resolved config, or writes it
as one YAML file with each value's entry number as a comment and, per revert replayed, one header
line `# entry 14 reverted to the state after #8`. It is a view, regenerated on demand and never
edited back: it takes the config as loaded and refuses a resolved one, and a resolved config
whose content no longer matches its hash is refused wherever one is needed. Every run already
saves its resolved config with its artifacts.

### Storage
- **Locally:** one small JSON file per entry, per instance, at
  `<roots.data>/<use_case>/04_feature/<ddh>/decisions/<seq>.json`: root, then use case, then
  layer; the root is the entity's area and the framework adds no entity segment, since the
  data-definition hash `<ddh>` carries the entity (D-136; the folder's other artifacts:
  [feature ledger](feature_ledger.md), [eda](eda.md), [feature checks](feature_checks.md)).
  The file is `<seq>.json`, zero-padded to four digits. No append is needed (HDFS append may be
  off in the bank: unverified). Two simultaneous writers can't interleave: each write is
  create-if-absent, and on a clash the write fails and the person re-runs the decision, since
  its checks were made against the log before the other writer's entry (that `hdfs dfs -put`
  without `-f` refuses an existing file is to be verified in the bank). Until the M2.4 transport,
  an `hdfs://` data root is refused where the log is read or written. A missing log folder reads
  as an empty log: a reader (`resolve_config`, `show_decisions`, Feature Checks' replay) logs a
  warning, since a wrong root looks like an empty log; a writer, which starts the log there,
  does not (`load_entries(…, warn_if_missing=False)`).
- **Register:** the run's slice (the entries up to its Training `run` entry, any later
  validation-period entry its Evaluation was scored with, its Evaluation's `run` entry, which
  names that period, plus the sign-off covering the run's feature signature) is packed into one file inside the registered bundle, immutable; promote reads it
  there. A folder of entries can't be registered or promoted as is ([lifecycle](lifecycle.md)).
- **Later:** a shared, queryable table may come with the registry tables in round 2 (M4). It would
  follow D-007 (shared tables only grow within a major version).

### Who writes
Any DS on the use case. The entry records the person as a user id, never a name in the repo. The
sign-off names who signed (D-031). `register` and `promote` write their own entries.

### Public functions
`record_decision`, `show_decisions`, `resolve_config` and `sign_off`, plus the CLI command
`python -m core_modelling decide`, are Public API (D-024;
[architecture](../architecture.md#public-api)); their signatures are in the Interface section
below. `sign_off(cfg, entity, env, run, reason)` reads the run's final list and signature from
its folder and writes the `sign_off` entry ([model bundle](model_bundle.md)); `decide --sign-off
--run r007 --reason …` does the same from the CLI. Writing any other entry is one call in a
notebook, or the same through `decide`:

```python
record_decision(
    "conf/base/cc_acquisition.yml",
    entity="entity_a",
    exclude=["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
    reason="Set after the offer, so not known at scoring time",
    evidence=["#3", "feature_checks report: Leakage"],
)
record_decision(
    "conf/base/cc_acquisition.yml",
    entity="entity_a",
    keep=["login_digital_mobile_cnt", "login_digital_mobile_cnt_0_2_months_avg"],
    findings=["stability.concordance_unstable"],  # optional: default every open flag on them
    reason="Digital adoption grew after the app relaunch; monitoring watches it",
    evidence=["#4", "feature_checks report: Stability"],
)
```

The CLI does the same with `decide --exclude …` or `decide --keep … --findings …`. Going back to
an earlier state is the fifth operation, `record_decision(…, revert_to=8, reason=…)` or
`decide --revert-to 8`; exactly one of the five (`exclude`, `include`, `keep`, `set`,
`revert_to`) per call (the `revert` bullet above).

`show_decisions(cfg, entity, env)` prints the log as the table below (a `revert` shows `to #8`
in `what`). Each report's choices block shows the entries up to its run, and the model card the
registered slice.

### Worked example
Card acquisition within 3 months on the synthetic mart, entity A. The target column `cc_flag`
(lineage) and the unsupported types leave through the candidate resolution and are never entries
(D-134).

| # | Date | By | Stage | Op | What | Reason | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | 10-27 | stage `feature_checks` | Feature Checks | flag `quality.all_null` | 1 feature | Every value null | report → Quality |
| 2 | 10-27 | stage `feature_checks` | Feature Checks | flag `quality.near_constant` | 1 feature | 99.9% one value | report → Quality |
| 3 | 10-27 | stage `feature_checks` | Feature Checks | flag `leakage.too_strong` | 2 features | Concordance 0.97 and 0.88 | report → Leakage |
| 4 | 10-27 | stage `feature_checks` | Feature Checks | flag `stability.concordance_unstable` | 5 features | Power differs across the window's periods | report → Stability |
| 5 | 10-27 | stage `feature_checks` | Feature Checks | run | periods: the 6 window periods, the gap 2025-09 and 2025-10, the latest 2026-02 | — | Feature Checks report |
| 6 | 10-27 | person (DS) | Feature Checks | exclude | the 2 flagged in #3 | Set after the offer, so not known at scoring time | #3; report → Leakage |
| 7 | 10-27 | person (DS) | Feature Checks | keep, findings `stability.concordance_unstable` | the 5 flagged in #4 | Digital adoption grew after the app relaunch; monitoring watches it | #4; report → Stability |
| 8 | 10-28 | stage | Training | run `r001` | input = config + #1–7; the 2 flagged in #1–2 held | — | run folder `r001` |
| 9 | 10-28 | stage | Evaluation | run `r001` | validation period 2025-11 scored | — | model results report, `r001` |
| 10 | 10-28 | person (DS) | Training | set | `training.max_iter` 200 → 300 | Search still improving at the last trials | model results report (search view), `r001` |
| 11 | 10-29 | stage | Training | run `r002` | input = config + #1–10 | — | run folder `r002` |
| 12 | 10-29 | stage | Evaluation | run `r002` | validation period 2025-11 scored | — | model results report, `r002` |
| 13 | 10-29 | person (DS) | Sign-off | exclude | `nationality` | Not used for product targeting | sign-off view, `r002` |
| 14 | 10-29 | stage | Training | run `r003` | input = config + #1–13 | — | run folder `r003` |
| 15 | 10-29 | stage | Evaluation | run `r003` | validation period 2025-11 scored | — | model results report, `r003` |
| 16 | 10-30 | person (DS) | Sign-off | sign_off | `r003`: its feature signature and its 61 features | Each defensible; the 2 held features stay out | sign-off view, `r003` |
| 17 | 10-30 | person (DS) | register | register | `r003` as version 1 | Candidate for production | model card |
| 18 | 11-02 | person (DS) | promote | promote | version 1 | Promotion PR approved | registry record |

Automated selection's drops in each run are rows of that run's ledger, not entries. A later run
with the same 61 features (a larger budget, another family) is covered by #16; one with a
changed list needs a sign-off of its own.

**Replay, state after each entry.** Each row is exactly what a run started at that point would
train on. Replay writes the open flags' features into `features.held`, so the input hash moves with them and
Training holds them out ([feature checks](feature_checks.md)). The
two features flagged in #1–2 are never decided: they stay held, which the sign-off view and the
model card list, and `register` needs no entry for them (D-134).

| After | Excluded | Kept | Held (open flags) | `max_iter` | Input hash |
|---|---|---|---|---|---|
| config only | — | — | — | 200 | `h0` |
| #5 | — | — | 9 (#1–2 quality 2, #3 leakage 2, #4 stability 5) | 200 | `h5` |
| #6 | 2 (the leaks) | — | 7 | 200 | `h6` |
| #7 → run `r001` | 2 | 5 | 2 (#1–2) | 200 | `h7` |
| #8–9 | unchanged: run markers are the trail | | | | `h7` |
| #10 → run `r002` | 2 | 5 | 2 | 300 | `h10` |
| #13 → run `r003` | 3 (+`nationality`) | 5 | 2 | 300 | `h13` |
| #14–18 | unchanged: the run markers, the sign-off, register and promote are the trail | | | | `h13` |

`resolve_config(cfg, entity, env, upto=13)` gives the state run `r003` trained on, each value pointing
at the entry that set it:

```yaml
# resolved: cc_acquisition.yml + entries 1–13 (input hash h13)
features:
  excluded:
    - cc_preapproval_score_trap_leak           # 6, person: set after the offer
    - cc_campaign_response_score_trap_leak     # 6
    - nationality                              # 13, person: not used for targeting
  kept:                                        # 7, person
    - login_digital_mobile_cnt                 # 7, person: digital adoption trend
    - login_digital_mobile_cnt_0_2_months_avg  # 7 (and three more rollups)
  held:                                        # written by replay from the open flags (D-134)
    - legacy_risk_grade_trap_all_null   # 1, stage: every value null
    - paper_statement_flag_trap_near_constant   # 2, stage: 99.9% one value
training:
  max_iter: 300                                # 10, person: search still improving
```

### Decision points and the automation levels (D-132)
"Rule" = decided by a rule in the config, "person" = a human decision. `LOGGABLE_SETTINGS` works
from the same list. The two levels differ only where the table's two columns differ (D-132); the
numbers (N, the budgets) are reversible defaults, set as each stage is built. The level acts in
`run` only: `run_training` called alone fails loud at either level when the EDA and Feature
Checks artifacts are missing, naming `run` as the fix. No gate is built: the report and the card
show the model against each declared baseline, and a person judges it (D-032).

| Decision point | `autonomous` | `assisted` |
|---|---|---|
| Target spec; eligibility, split, sampling, collect budget | the config (person); rules apply it | same |
| Null targets at the panel edge; degenerate target | rule | rule |
| Run EDA and Feature Checks before training (D-031) | `run` runs them automatically, default content | the person runs them and reads the reports |
| Key features in EDA | rule: top-N (N = 10, a correlated candidate skipped) plus the person's list | same |
| Resolving Feature Checks' flags | open flags hold their features out of training; a person reviews them at the sign-off (D-134) | open flags hold their features out of training; the stage ends in the flag review, `keep` / `exclude` entries before training |
| Training budget (`training.max_iter`, split over the listed families) | 60 trials | 200 trials; at either level a person may `set` it, or `training.trials`, through the log |
| Calibration | follows the decision (D-049) | same |
| Automated selection drops; search result; monitoring flags | rule | rule |
| Feature sign-off; register; promote; retrain / retire / roll back; a level move | person, always | person, always |
| deploy | the change-request process | same |
| Which version scores | production, or a pin in the config | same |

Top-N walks down EDA's ranking on the snapshot (the concordance, or the best-order concordance for
a feature marked `non_monotone`, D-030, D-135), skipping a candidate associated above
`eda.key_features.max_correlation` with a key feature already chosen, plus the features the person
lists in `eda.key_features.include`: EDA's key features, each with a deep dive ([eda](eda.md)).
A move between levels is a config edit
before the config freezes and a `set` on `automation_level` in the audit log after it, which
reruns every stage from EDA (D-132); at replay the move re-fills exactly the fields the level
filled at load (recorded as `housekeeping.level_filled`), and explicit values stay, including a
value a `set` entry gave a level-filled path: the `set` takes the path off the list (a `set` on a
section, for every level path under it).

## Identities (D-088, D-125): how the hashes work
The config's hashes are taken over a canonical form (keys sorted, defaults resolved, migrated to the current
schema) of a subset of the config or the resolved config (the table says which; the run's own
hashes are over its files, [model bundle](model_bundle.md#the-hashes)), and stored
beside a `hash_version` that names the recipe
that computed it. **Rule:** any change to the canonical form of a hashed section (a field added,
renamed or retyped, a default changed) changes the digests of every existing config, so it bumps
`HASH_VERSION`, and the reading of old artifacts is decided with it (D-088's "schema change, not
a data change"). Until the December pre-release nothing is kept inside the bank, so a recipe
change re-pins the digests and leaves `HASH_VERSION` at 1 (0.x promises nothing, `CLAUDE.md` §2);
the bump applies from then. A golden-hash test pins the example's data-definition and target-spec
digests, so the change can't happen unnoticed. Both hashes include `task`, so an upstream target
column read as binary and as regression has two digests.

| Identity | Covers | Excludes | Changes when |
|---|---|---|---|
| config hash | the use-case definition: every section after level resolution | the housekeeping block; the environment file (tables, paths, Spark, theme; D-130); the audit log's entries | the config file changes, which after Target Factory means a new config; decisions in the log leave it unchanged |
| data-definition hash | `task`, entity, sources, keys, eligibility steps, target spec, the `time` part `period`, `observation_window`, `target_window`, candidates | the validation period (in the config; EDA and Feature Checks read it only to leave it out of the compared periods, and a `set` to a compared period is refused); `features.kinds` (how a column is read, not which); the inference period (a run argument); the stage sections | the population, the target, the unit of analysis, the window or the candidates change. It keys the folder `<use_case>/04_feature/<ddh>/` under the entity's root: the audit log and the EDA and Feature Checks artifacts training needs (D-031, D-136) |
| target-spec hash | `task`, the target spec, the keys, the target window, the entity's target source: what one label column depends on | everything else | the label's meaning changes (the same upstream column read as binary and as regression is two labels); it keys each use case in the model input's sidecar (D-131) |
| resolved-input hash | the config plus entries 1–n, resolved (the run's one input) | the housekeeping block; the environment file; the trail entries, which change nothing (`flag` entries are not trail: the hash sees `features.held`) | every entry that changes the input: `exclude`, `include`, `keep`, `set`, `revert`, and `flag` through `features.held` |
| stage settings digest | per stage, the settings paths it reads ([the modelling fields](#the-modelling-fields-stage-3) → "Who reads what") | every other setting | a value under its paths changes: the stage's stored artifacts are stale; Evaluation finds its run by Training's digest and the data-definition hash (D-139) |
| `run_id` | the run number, `r` and at least three digits (`r001`, `r007`, `r1000`; typed `r7` or `7` on the CLI and in `find_run`, it is normalised): one Training call and its Evaluation, a running number per use case | not a hash: the hashes the run was built from, the entity, who started it and when are fields of its `run.json` ([model bundle](model_bundle.md#runjson)) | every Training run; a number an audit-log entry names is never given again, also after its folder is deleted; a crashed run that wrote no entry may see its number reused (D-139) |
| feature signature | the run's final feature list, in order ([model bundle](model_bundle.md#the-hashes)) | everything else | a feature enters or leaves; a `sign_off` covers every run of the same data definition with the same signature (D-125 (c)) |
| `recipe_hash` | the recipe, whose keys are pinned, as [model bundle](model_bundle.md#the-hashes) lists it | the calibration's fitted numbers | the recipe changes; a production retrain keeps it (D-052) |
| `model_hash` | the model file and `bundle.json` ([model bundle](model_bundle.md#the-hashes)) | the manifest and the resolved config, which carry a time | the trees, the encoder, the calibration numbers or the recipe change: every retrain (D-094, D-139) |

The saved model input is keyed by none of these as a whole: its sidecar holds the shared sources,
keys and period plus each use case's target-spec hash, never the data-definition hash, so a
changed eligibility, window or candidate list reruns EDA onwards and keeps the table (D-088,
D-131; [dataset](dataset.md#model-input-d-131)).

A worked example, one use case on two entities:
1. The DS writes the config and runs EDA and Feature Checks on entity A. The artifacts are keyed by
   the data-definition hash `d_A`.
2. Training on entity A finds `d_A`'s artifacts, replays the entries so far into the resolved input
   `i1`, and runs as `r001`, whose `run.json` records `i1`, `d_A` and the entity. The same config on
   entity B needs its own EDA and checks (`d_B`: the entity is part of the hash), its own log and
   its own runs; under one laptop root the two sit side by side as `<use_case>/04_feature/d_A/`
   and `…/d_B/`, and their runs share `<use_case>/06_models/`, each `run.json` naming its entity.
3. The DS records a human `exclude` for one feature: an entry in the audit log, not a config edit.
   The config hash stays `c1` and the candidates are unchanged, so `d_A` stays and no EDA rerun is
   needed. The resolved-input hash becomes `i2`, and training reruns as `r002`, whose `run.json`
   records `i2`.
4. Next period the DS scores: the inference period is a run argument, so no hash changes and
   nothing has to be rerun. Moving the validation period (a checked `set` entry, e.g. for a sweep
   variant) changes the resolved-input hash but not the data-definition hash, so the folder, the
   audit log and the saved model input stay; the stages rerun from EDA, since EDA's settings
   digest covers the validation period, which decides the periods EDA and Feature Checks
   compare.
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
The items marked "Stage 2 step 1" changed in Stage 2's first step, in place (no schema or log
bump, D-136): the schema's fields, the template, the examples and the `keep` rename (m1.1), the
audit log's `findings`, `flag`, `run`, the held set and the paths (m1.2). The items marked "Stage 3"
changed in M2.3's major step 1, in place as well: the modelling fields, the Training and
Evaluation `run` entries, the `sign_off` entry with `signed_off`, the loggable training and
evaluation leaves, the stage digests and `models_dir`. Package:
`core_modelling/config/` (`schema.py`, `levels.py`, `migrations.py`, `identities.py`,
`replay.py` (the entry model, the operations, the replay, `check_resolved`, `dump_resolved`),
`audit_log.py` (storage and the public functions)); `sign_off` in `core_modelling/runs.py`
([model bundle](model_bundle.md)); the CLI command `decide` in `core_modelling/__main__.py`.
- `load_config(path: str | Path) -> UseCaseConfig` (public): YAML → `migrate` →
  `apply_level_defaults` (fills nulls only) → `UseCaseConfig.model_validate`, with `extra="forbid"`
  on every model; a YAML or schema error is a `ValueError` naming the file. One validator per rule:
  the name's characters (D-128), the time rules (req. 8), `decision.type: top_n` needs `n` and
  another type refuses one, the period typo rule on the three `time` dates (a `model_validator` on
  `Time`, since it needs `time.period`), an eligibility entry has exactly one of `define` /
  `filter`, a `filter` has a `reason`, step names are unique across the `analysis` and `modelling`
  lists, `target` has `column` (any source column name, `target` included) with an optional `rule`
  (its name is checked against the task's spec when the target is built) and an optional `lineage`
  (its names checked against the sources' columns, ignoring case, when the panel is built: [target
  factory](target_factory.md)), `sampling` with its parameters, `test_share` in (0, 1). Stage 3:
  the fields and refusals of [the modelling fields](#the-modelling-fields-stage-3), and
  `decision.metric`, `training.objective` and `training.calibration.method` filled at load when
  null, so the resolved config states the value in force; `decision.gate_metric`, the `lifecycle`
  section and the other gone keys fail as unknown keys. Stage 2 step 1: `time.validation_period` is required but may be null
  (the `v` rules then skip); `eda.snapshot` is `last` or a period inside the window by period index,
  a date held as its period's last day under the typo rule (a `model_validator` on `UseCaseConfig`,
  since it needs `time`; the typo rule is one private helper, `_accepted_period_end(value, period,
  path)`, shared with `Time`); `eda.bins` is null or at least 2, `eda.key_features.max_correlation`
  in (0, 1]; `feature_checks` is a mapping of five typed step models (`Quality`, `Leakage`,
  `TimeAlignment`, `Stability`, `Redundancy`, the null note's `NullsMayBeZeros`) with a default for
  every parameter, so an unknown parameter or step fails loud (each bounded: shares in (0, 1],
  concordance thresholds from 0.5, `psi_note_min` and `psi_max` above 0, `rare_effect_max` in (0, 3]
  (Cohen's h tops out at π and a d above 3 is implausible, so a ratio-era 5 fails at load instead of
  never firing), `leakage.dominant_share_min` in (0.5, 1), `stability.concordance_range_min` in [0,
  2] (a multiple of the window's signal) and `stability.concordance_range_floor` in [0, 1] (an
  absolute range), `max_levels` at least 2), and `stability.psi_note_min` above `stability.psi_max`
  is refused naming both (a `model_validator` on `Stability`: the PSI note fires between the two); a
  step left out of a present mapping is `None` (not run), and the section left out is `EVERY_CHECK`,
  all five with their defaults; a present mapping naming no step (`feature_checks: {}`) is refused
  naming the five, and `quality.nulls_informative_min` at or above `leakage.null_concordance_max` is
  refused naming both values when both steps are present (two `model_validator`s on `FeatureChecks`;
  with `leakage` left out, the quality step takes `Leakage().null_concordance_max` as its bound);
  `features.kinds` values are `numeric` or `categorical` (a key naming no candidate is refused when
  the frames are built, since the candidates are patterns at load); `features.kept` and
  `features.held` join `features.excluded` as replay-written lists a config file may not carry;
  `eda.chart_sample_share`, `feature_checks.steps` and the `eligibility_constant` step of the Stage
  1 schema are gone, and a config still carrying them fails naming the field.
- `snapshot_period(cfg: UseCaseConfig) -> date` (`schema.py`): the period EDA collects whole, as
  its last day; `last` resolves to the window's last period.
- `LEVEL_DEFAULTS: dict[str, dict[str, object]]` (path → {autonomous, assisted}: `training.max_iter`,
  60 and 200 (Stage 3), and `evaluation.slices.top_pct`; `eda.key_features.top_n` is a plain default of 10), `MIGRATIONS:
  dict[int, Callable[[dict], dict]]` (empty at `schema_version: 1`; a version above the current
  one fails loud).
- The hashes (`identities.py`): `config_hash(cfg)`, `data_definition_hash(cfg, entity)`,
  `target_spec_hash(cfg, entity)` (both with `task` among their parts), `resolved_input_hash(resolved)`,
  `feature_signature(features)` and `recipe_hash(recipe)` (the run's hashes, [model
  bundle](model_bundle.md#the-hashes)); sha256 over canonical JSON
  of a dict that names its parts, with `HASH_VERSION = 1`, 12-character prefixes (`short`) in
  paths. The config hash excludes `housekeeping` and the three replay-written lists
  (`REPLAY_FIELDS = {"excluded", "kept", "held"}`); the resolved-input hash excludes
  `housekeeping` only.
- The audit log (public, D-024): `record_decision(config_path, entity, *, exclude=None,
  include=None, keep=None, findings=None, set=None, revert_to=None, reason, evidence=(), stage=None,
  env_path=None) -> Entry` (Stage 2 step 1: `keep` replaces the Stage 1 `keep_despite_flag`, and
  `findings` goes with `keep` only, refused otherwise before anything is read; each named finding
  must be open on every kept feature, and without `findings` the writer stores the features' open
  flags, refused when they differ between the features (one keep per finding set) and `[]` when none
  is open; a named `[]` while flags are open is refused; the replayed list becomes `features.kept`)
  (exactly one of the five operations; the writer is the current user id; a feature op checks its
  names against the saved model input's candidate list when the config names one and it is saved,
  else against the candidate patterns, saying so; `revert_to` writes a `revert` entry with `to_seq`,
  its stage the first undone entry's unless `stage` is given, refused when the state it brings back
  has a `null` validation period where the current one has a period, or a period a `run` entry
  compared); `read_resolved_config(path) -> UseCaseConfig` reads a saved resolved config back
  through the same `migrate` as every config load (a schema error names the file, as `load_config`'s
  does), otherwise as is (no level defaults, its replayed lists and housekeeping kept), which
  `load_config` refuses, since a config file carries intent only; `resolve_config(cfg, entity, env,
  upto=None, save_to=None) -> UseCaseConfig` (stale when a replayed `run` entry lists the resolved
  validation period); `show_decisions(cfg, entity, env) -> pd.DataFrame`; `load_entries(cfg, entity,
  env, *, warn_if_missing=True) -> list[Entry]`, the log's entries read through the checked reader
  (an entry under another data definition fails citing its `seq`), which Feature Checks reads the
  log with; the CLI command `decide` (`--revert-to N` writes a revert; Stage 2 step 1: `--keep …
  --findings …`, `--findings` without `--keep` refused by `record_decision`).
- `record_stage_entry(cfg, entity, env, *, stage, op: Literal["flag", "run"], reason,
  features=None, finding=None, periods=None, evidence=(), run_id=None, validation_period=None,
  replayed_to=None, resolved_input_hash=None) -> Entry` (`audit_log.py`, Stage 2 step 1; Feature Checks calls it
  from m3.2): `by = {kind: stage, id: stage}`, the same storage and data-definition check as a
  person's entry; a `flag` needs `finding` (`<step>.<finding>`) and `features` (empty closes the
  finding), a Feature Checks `run` needs `periods`, a non-empty list of labels of the config's
  period as `periods.PERIODS` writes them (`2025-06`, `2025-W23`, `2025-06-15`; a label of no
  real period, such as `2025-02-30`, is refused too: a label must survive the round trip through
  the period spec), else refused naming the label; whether a `flag` is due (its finding's feature
  set changed) is the stage's call. Stage 3: Training's `run` entry carries `run_id` and no
  `periods`; Evaluation's carries `run_id` and `validation_period`, a label checked the same
  way.
- `signed_off(entries: list[Entry], signature: str) -> Entry | None` (`replay.py`, Stage 3): over
  the effective entries, the latest `sign_off` whose `signature` is the given one, or `None`; a
  `revert` past it undoes it.
- `sign_off(cfg, entity, env, run: str, reason: str) -> Entry` (public, `runs.py`, Stage 3): reads
  run `run`'s final list and its feature signature from the run folder and writes the `sign_off`
  entry (`run_id`, `signature`, `features`) as the current user through `record_sign_off`
  (`audit_log.py`); `run` may be typed `r7` or `7`
  and is normalised to `r007`, as in `find_run`; the CLI's `decide --sign-off --run
  r007 --reason …` calls it ([model bundle](model_bundle.md)).
- `open_flags(entries: list[Entry]) -> dict[str, list[str]]` and `held_features(entries) ->
  list[str]` (`replay.py`, Stage 2 step 1): over the effective entries, per feature the findings
  whose latest `flag` entry names it and which no `keep` naming the feature and that finding
  settles; a feature with an `exclude` in force is left out. `replay` writes `features.excluded`,
  `features.kept` and `features.held` sorted and once each, so the order of entries never moves
  the resolved-input hash; a `set` under a `feature_checks` step the config leaves out is refused
  at write and stops the replay as stale (`check_settable`). A config built in code with one of
  those three lists filled is refused at replay, since the replay would overwrite the lists
  without a word; and `resolve_config` refuses a config that is already resolved, since the
  replay starts from the file's values.
- `effective_entries(entries) -> list[Entry]` and `decisions_in_force(entries) -> tuple[dict[str,
  list[int]], dict[str, int]]` (`replay.py`): the entries no revert undid, and from them per feature
  the `seq`s of its `keep` entries and of its `exclude` in force
  ([replay](#from-entries-to-code-replay)).
- `check_resolved(cfg, what: str) -> None` (`replay.py`): refuses a config that was only
  loaded where `what` needs the resolved one (no `resolved_input_hash` in its housekeeping: its
  held and excluded lists are empty), and a resolved one whose content no longer matches that
  hash (a saved file edited by hand); `build_frames` for Training, `stage_identity`,
  `check_upstream`, `resolve_features`, `render_decisions`, `create_run` and `find_run` call it. `dump_resolved(resolved)
  -> str`: the resolved config as YAML, the one serialisation every writer of it uses (the
  resolved file, a stage's `resolved_config.yml`, a report's appendix).
- Entries live at `<roots.data>/<use_case>/04_feature/<ddh>/decisions/<seq>.json` (Stage 2 step 1,
  D-136; `audit_log_dir(env, cfg, entity)` in [environment](environment.md); the run folders sit
  under `<roots.data>/<use_case>/06_models/`, from `models_dir(env, cfg, *parts) -> str`, Stage 3,
  [model bundle](model_bundle.md)), `seq` zero-padded to
  four digits, written create-if-absent, a clash failing so the person re-runs the decision; the
  writer of entry 1 prints `starting a new audit log at <folder>`, so a wrong root or a log left
  at an old path shows itself. A corrupt file, an entry under another data definition, a gap in
  the numbering, an unknown operation or another `log_schema_version` fails loud, naming the
  file or the entry. A `set` may write `null` (e.g. sampling
  off). `resolve_config` fills the housekeeping block (framework version, time, entity, the three
  hashes, `replayed_to`, `hash_version`, the environment values used, `level_filled`) and, with
  `save_to`, writes the YAML with a header naming
  the entries replayed (one line per revert: `# entry 14 reverted to the state after #8`) and
  the entry behind each changed value (a held feature: the latest `flag` entry holding it).
  `show_decisions`' `what` reads `a, b (settles leakage.too_strong)` for a `keep`,
  `leakage.too_strong: a, b` for a `flag` and `periods 2025-03 … 2026-02` for a Feature Checks
  `run`. Training and Evaluation write their `run` entries through `record_stage_entry`, and
  `sign_off` writes its entry (Stage 3); `register` and `promote` get their writers with M2.4;
  replay accepts them all. Stage 2 step 1: a
  `flag` entry carries `finding` and may have an empty feature set (no other feature operation
  may), a `keep` carries `findings`, a Feature Checks `run` entry `periods`, and an operand on
  another operation is refused (`OPS_BY_OPERAND` in `replay.py`); a `set` of
  `time.validation_period` is refused when it writes `null` (write it in the config file
  instead) and when any Feature Checks `run` entry, reverted or not, lists the period (compared
  by its label; Training's and Evaluation's entries are never read for it, Stage 3), and a
  `revert` is checked the same way on the state it brings back.

## Open questions
- The decision audit log: whether a person entry that cites a superseded rule entry blocks
  register until a person confirms it (today nothing flags it: the flag at replay is planned,
  [replay](#from-entries-to-code-replay)).
- The log folder is keyed by the short data-definition hash, so a change of the hash recipe
  (`HASH_VERSION`) would leave an old log where no reader looks; a `definition.json` beside
  `decisions/` carrying the full hash, `hash_version` and `schema_version` would let a later
  version find and re-key it. Related: a field added to a hashed section, even optional, changes
  every digest; hashing only values that differ from the schema default would leave them alone,
  at the price of a version bump for every changed default. Decide both before the December
  pre-release, when logs and artifacts start being kept inside the bank.
- Extension functions live in the use case's repo and are referenced by import path; the resolved
  config records the path and a source hash (D-006). The exact fields are set when a use case
  first needs one; the walking skeleton's examples need none.
