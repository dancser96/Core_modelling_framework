# Stage 1 (M2.1 Foundation): design questions
_Written 2026-10-23 for the SDS, rewritten 2026-10-25 after round 1, closed 2026-10-26 · Q349–Q373
(Q374 and Q379–Q386 were other files', both deleted) · cited decisions are summarised in brackets
(D-072 (k)) · outcomes are in `docs/` and in `plan.md` beside this file; the folder is deleted when
the stage is done_

**Where it stands (2026-10-26): every question is answered.** The plan is `plan.md`. Round 2's
answers (defaults where not named):
- Q354: all defaults, (a)–(c) included: the layout below is the schema Stage 1 builds.
- Q358: default (A), the environment file with its own schema.
- Q364: default (A), `w` in `time`.
- Q365: (A), the saved model input named in the config, for your reason too: a source holding
  only targets will probably never exist; a use case imports one, two or three real sources, which
  may or may not carry the target, and (A) is the easiest shape for all of those. Assumption A4
  (a separate targets table) falls away.
- Q367: (A), and nothing is built for it: the leakage screen shows it, and no use case has ever
  looked like this (nobody predicts loan maturities). The requirement is reworded to guidance.
- Q371: (A) for the estimate, but **as a printout, not a stop**: the numbers (rows, columns, the
  estimated size, the budget) are printed on every collect, in the notebook and from a function
  call alike, and when the estimate exceeds the budget the printout becomes a callout saying what
  to do: declare sampling, or raise the budget and the Spark settings. Inside the bank one simply
  raises the Spark settings, so a hard stop would be in the way. The collect proceeds. The adapter
  therefore does not derive `spark.driver.maxResultSize` from the budget; the callout names it.

Stage 1's synthetic step shrank while the questions were open: the other chat built the `dev`
preset and the LDS's trap columns (synthetic 0.5.0, both datasets regenerated), so major step 2's
synthetic part is the holdings table only (Q352).

**Stage 1 as planned** (`worknotes/timeline_proposal.md`, D-022 (the Phase 2 plan: skeleton
first, two rounds)): 10-26 – 11-02, six days. Done when one config gives the frames, with
eligibility, join and split logs. Depth at the pre-release: config spine deep, environment adapter
deep, dataset thin, Target Factory thin (one binary rule family with lineage).

**One change since round 1.** D-030 (observation window and splits) now says EDA and Feature
Checks use every client in the window, labels included, and the train/test split applies from
Training on (`CLAUDE.md` §4.4). The frames below follow it: a window frame for EDA and Feature
Checks, train / test / validation frames from Training on.

## Open questions

### Q354. The config layout, with your round 1 points worked in

**Context.** The config is the use case's whole intent, validated at load and immutable once
Target Factory has built the target (D-125 (the decision audit log: later decisions are entries,
never config edits)). It is the framework's most important contract with users: a later framework
version must keep loading it (`CLAUDE.md` §2). The template must list every option with a one-line
when-to-use (`config.md` req. 14), and the config spine is "deep" at the pre-release, so Stage 1
writes the **whole** schema and template, not only the fields Stage 1's code reads. That answers
your question about the training fields: round 1 showed only what Stage 1 reads; the full
`training` section is below.

**What the stage sections do.** Every stage reads the **shared sections** (`task`, `decision`,
`entities`, `data`, `time`, `features`), which together are the data definition, so EDA, Feature
Checks, Training and Evaluation can never look at different populations. Each stage also reads
**its own section**, which holds that stage's knobs and nothing else. A section left out takes the
automation level's defaults, so a first run needs only the shared sections. Fields of stages not
built yet are validated from Stage 1 with their defaults and are read once their stage is built.

| Section | Read by | Holds |
|---|---|---|
| `decision` | Training, Evaluation, lifecycle | How the scores are used; the metric, gate metric and baselines derived from it or overridden, all declared before any result (§4.3) |
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

**The proposal** (the template's content, with the walking skeleton's `cc_acquisition` values;
values marked `null` take the level default, set when that stage is built):

```yaml
schema_version: 1
task: binary
use_case: cc_acquisition                 # <product>_<activity>; must split at load (D-128)
domain: retail
automation_level: assisted               # autonomous | assisted (D-023)

decision:                                # declared before any result; never changed through the audit log (§4.3)
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
  model_input: cc_acquisition_input      # optional: the saved model input's logical name (Q365); omit = build in memory
  eligibility:                           # ordered; `define` names a condition, `filter` keeps rows; each logs rows in → out
    - {name: has_income, define: "income IS NOT NULL"}
    - {name: non_holders, filter: "cc_flag = 0", reason: "acquisition is scored for clients without a card"}
    - {name: income_known_or_salaried, filter: "has_income OR salary_transfer_flag = 1",
       reason: "card rules need a known income"}
  target:                                # Q364
    rule: flag_in_window                 # the M2 rule family (D-091); an upstream target gives only `column`
    column: cc_flag                      # the column the rule reads; excluded from the candidates (lineage)
    leavers: null                        # null (default) | negative: what a client leaving inside the window gets
  split: {test_share: 0.3, seed: 42}     # by client, seeded hash; applied from Training on (D-030)
  rate_band: {max: 0.5}                  # contract check on the true population; no floor

time:
  train_months: {first: 2025-03-01, last: 2025-08-01}   # the observation window t1 … tk
  target_window_months: 3                               # w: targets look at months t+1 … t+w (Q364)
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
  steps:                                 # ordered; each flags and logs, never drops (§4.6); thresholds low (D-031)
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
    auc_floor: 0.515
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

**Your points, and where they went:**
- Sources (Q373): `features` is an ordered list whose first entry is the governing spine; the
  other feature sources and the target source left-join to it. Duplicate keys in any source fail
  loud, and the join log prints each source's distinct units per month and the share of spine rows
  it matches.
- Combined expressions (Q355): `col_a > 0 OR col_b > 0` is plain Spark SQL in a `filter`. Reusing
  named conditions (`expr_1 OR expr_2`) works through `define` entries: a `define` creates a
  boolean column without filtering, and later steps use it by name. `define` columns are dropped
  before the candidates are resolved.
- The saved model input (your (a)): `data.model_input`, explained in Q365.
- Training's decisions: the whole `training` section, with model families, budgets, seeds, search
  ranges, selection, categoricals, calibration and sampling.

**Still to decide here:**
- (a) Group the decision, both metric overrides and the baselines in one `decision` block, since
  `CLAUDE.md` §4.3 requires all of them declared before any result and the audit log may never
  change them. The alternative keeps the baselines in `evaluation` and the metric in `training`,
  as `config.md` sketches today.
- (b) A shared `strata` section, since EDA, Evaluation and Monitoring all report by the same
  variables. The alternative is `eda.stratify_by` and `evaluation.stratify_by` kept apart, as
  `config.md` sketches today.
- (c) The whole schema and template in Stage 1, every section validated now. The alternative adds
  each stage's fields when that stage is built (0.x promises nothing, D-007 (c)), which means a
  schema change in every stage.

*Default:* (a), (b) and (c) as shown; field names may still be refined when each stage is built.

### Q358. `conf/local`: an environment file with its own schema, not a merge over the config

**Context.** A use case has two kinds of settings. The use-case config holds the intent (sources
by logical name, window, target, training choices) and is committed to the use case's repo.
`conf/local/` is gitignored and holds the environment: physical tables and paths, Spark settings,
storage roots, the report theme. Today `config.md` req. 2 says load is a "`conf/base` →
`conf/local` merge". Read literally, `conf/local` is a second copy of the config whose values
override any field of the first. The config hash excludes "every `conf/local` value" (D-088
(identities)), so the same config hashes identically on the laptop and inside the bank.

**The problem.** A free merge lets an environment file change the model without anyone seeing it
in the config or the hash.

*Example:* a DS sets `training.max_iter: 5` in their `conf/local` to make a test run quick and
forgets it. Inside the bank the committed config says 300. Both runs carry the same config hash,
but the models differ, and nothing in the resolved config tells a reviewer why.

**Options:**
- (A) **An environment file with a fixed schema.** `conf/local/environment.yml` holds only
  environment facts: Spark settings, roots, physical sources per entity, the collect budget
  (Q371), the theme. It has its own Pydantic model, and a key it doesn't know fails loud, so a
  modelling field there is refused. The use-case config never holds a physical name. "Merge" then
  means "load the environment file next to the config and resolve logical names through it". The
  resolved config's housekeeping block records the environment values a run used, outside the
  hashes.
- (B) A free merge with a list of fields `conf/local` may not override. More flexible, but the
  deny-list must grow with every new field.
- (C) A free merge, as written today.

*Default:* (A). Since `conf/local` only has to be structurally right and work on this laptop
(Q362), the laptop file is:

```yaml
# conf/local/environment.yml (gitignored); the example is conf/base/environment.example.yml
spark:
  master: "local[*]"
  driver_memory: 2g
  shuffle_partitions: 8
  time_zone: UTC
  extra: {}                              # any other spark.* setting
roots:
  data: /ABSOLUTE/PATH/data              # the layers of data/README.md hang off it
  registered: null                       # set when M2.4 builds register / promote / deploy
  production: null
sources:                                 # logical name → physical, per entity
  entity_a:
    retail_mart:          {format: parquet, path: /ABSOLUTE/PATH/data/01_raw/synthetic_dev/mart}
    retail_holdings:      {format: parquet, path: /ABSOLUTE/PATH/data/01_raw/synthetic_dev/holdings}
    cc_acquisition_input: {format: parquet, path: /ABSOLUTE/PATH/data/05_model_input/cc_acquisition/entity_a}
collect_budget_gb: 1.5                   # Q371
theme: null
```

Today's `conf/local/sources.yml` folds into it.

### Q364. The target spec: where the target window `w` lives

**Context.** The target spec says how the target is built, and four things read it:
1. Target Factory builds the target from it.
2. Lineage exclusion removes the column it reads from the candidates (§4.6).
3. The data-definition hash covers it, so EDA and Feature Checks artifacts match the target they
   were made for (D-088).
4. Monitoring builds labels for scored months from the model's frozen spec (D-054).

The target window `w` (targets look at months `t+1 … t+w`) is part of the target, but the time
checks need it too: `v ≥ tk + w`, so the validation target window doesn't overlap a training
target window (§4.2), and `v + w ≤` the sources' last month, so every validation label has
matured. EDA and Feature Checks also need it to know which months' labels exist.

**Two variants of the spec:**
1. Built by Target Factory: `rule` names the builder in the per-task spec (`flag_in_window`: the
   flag is 1 in any month of the window, for a row that passed eligibility), `column` is the
   column the rule reads and the lineage that gets excluded, and `leavers` says what a client who
   leaves inside the window gets.
2. Built upstream: only `column` (e.g. `cc_acquire_next_3_months_flag`) and an optional
   `lineage: [...]` (D-029 (no lineage list is required for upstream targets)). Nothing is built
   and Target Factory is skipped. The time checks still need `w`, because an upstream target also
   looks some number of months ahead, and only the DS can declare it.

**Options:**
- (A) `w` in `time` as `target_window_months`, required for both variants, read by the target
  builder and the time checks alike. One number in one place, next to the months it constrains.
- (B) `w` inside `data.target`, so the target spec is self-contained (the monitoring labels read
  one block), and the time checks read it from there.

*Default:* (A). The monitoring labels read the resolved config, which has both blocks anyway, so
(B)'s gain is small.

### Q365. The model input: the crunch's saved table, in this design

**Context: the crunch.** Data Creation read the input panel, added the targets and the rollups as
columns, and wrote one enriched table. Each product's config pointed at it (`table:`), and every
later notebook read that table and applied `eligibility_expr` on load. One inspectable table, fast
reads, and a pointer in the config.

**Context: what is different now.**
- A use case may read several sources per entity: feature sources joined on unit and month, plus
  a target source (Q373: left joins to the governing spine).
- Eligibility is a list of ordered config steps, each logging rows in and out.
- The data-definition hash (entity, sources, eligibility, target spec, window, candidates) keys
  the EDA and Feature Checks artifacts that Training requires (D-031 (no model without EDA and
  Feature Checks for the same data definition)).
- The config is immutable once Target Factory has built the target (D-125).
- D-029 (Target Factory) names two modes: notebook mode (build, inspect, save) and config mode
  (build in memory and hand on, with the spec's hash recorded).

**How the crunch pattern fits.** The **model input** is the table every stage after Target
Factory works from. It holds the governing spine's rows, the candidate columns of every feature
source, the target, and the `split` column. The months run from the window's first month to the
latest month the spine holds, because Feature Checks compares the gap months and the latest
month without labels. Eligibility is applied, with the define columns dropped. It sits next to a
`metadata.json` holding its data-definition hash, the target spec's hash, the lineage, the join,
eligibility and null-target logs, the framework version and when it was built.

**Options:**
- (A) **A saved model input, named in the config** (the crunch's pattern, made safe by the
  hash).
  - `data.model_input` names it by logical name, and `conf/local` maps the name to a table or
    path per entity (Q358).
  - `save_model_input(cfg, entity)` builds and writes it. It is called from the Target Factory
    notebook (notebook mode), or by `run --stages target_factory`.
  - Every later stage reads it when the config names it, and fails loud when its data-definition
    hash differs from the config's: "the model input was built from another data definition;
    rebuild it with `save_model_input`".
  - Without the field, every stage builds the same frames in memory (config mode), with the same
    logs.
  - Saving is also the moment the config freezes (D-125).
  - No separate targets table is saved in Stage 1: the model input carries the target, so
    assumption A4 below falls away. Labels for scored months (M4) build their own.
- (B) **A hash-keyed cache with no config field.** The same table, written to a path built from
  the data-definition hash and read whenever present. Nothing to keep in step, but nobody can
  see in the config which table a use case works from.
- (C) **Always in memory.** No copy of the data. Every stage reruns the join and the eligibility
  steps: seconds on the laptop, minutes on a bank mart.

*Example:* the DS writes `cc_acquisition.yml` and runs the Target Factory notebook. The notebook
shows the target rate per month and the join, eligibility and null-target logs. The DS then calls
`save_model_input`, which writes the table to the path `conf/local` names and freezes the
config. EDA, Feature Checks and Training all read that table. Next month, inference reads the
**sources**, not the model input, and applies the model's own eligibility to the new month
(§4.9).

*Default:* (A). It is what the crunch did, it gives one table to inspect, and the hash check
removes the crunch's risk of a stale table. The cost is one save function and one hash check per
reader.

### Q367. "Refuse a target fixed by an as-of column": a check, or guidance?

**Context.** `target_factory.md` req. 5 says: "A target fixed by an as-of column (e.g. a loan
closing, set by its maturity) is degenerate and should be refused with a reason." The case is a
target that is already decided by a column visible at the observation month, so there is nothing
to predict.

*Example (synthetic data):* loans close only at maturity (`test_harness.md`). A target "the
personal loan closes in the next 3 months" equals `loan_personal_maturity_months ≤ 3` row for row.
A model on it reaches AUC 1.0 by learning one column and is useless.

**What the framework can see.** Target Factory runs before EDA and doesn't look at the candidates.
It can't tell in general whether some column determines the target. The leakage screen in Feature
Checks already flags any candidate with a near-perfect univariate AUC, and that is where the
maturity column would light up. It flags; a person decides (§4.6).

**Options:**
- (A) **Guidance plus the leakage screen.** Req. 5 is reworded to: a target already decided at
  the observation month is useless. The template says so with the loan example, and the leakage
  screen flags the column that decides it. No code in Target Factory.
- (B) **A check in Target Factory or the dataset.** After building, compute every candidate's
  univariate AUC against the target and refuse the target when one is ≥ 0.999. This duplicates the
  leakage screen, and it must also not refuse a legitimate target with one leaky column, which is
  the screen's job to flag.
- (C) **Refuse rule families known to be degenerate** (e.g. a count going down for loans). That
  bakes in domain knowledge, against D-034 (domains are configuration).

*Default:* (A).

### Q371. The collect budget: what fails, and how the size is estimated

**Context: where the memory goes.**
- Spark builds the frames lazily; nothing is in memory until a frame is collected with
  `toPandas()`.
- With Arrow on, the executors send record batches to the driver JVM, which passes them to the
  Python process, where pandas builds the DataFrame.
- On the laptop Spark runs in local mode: the executors are threads inside the driver JVM, and
  `spark.driver.memory` (2 GB) is all of Spark.
- **The frame lives in the Python process**, outside that 2 GB. Its peak is about twice the final
  frame, because the Arrow buffers and the pandas copy exist at the same time.
- `spark.driver.maxResultSize` (default 1 GB) caps what one action may send to the driver. It
  probably applies to the Arrow collect too (to verify on 3.4.3). A frame over it fails with a
  Spark error that doesn't say what to do.
- The crunch's out-of-memory error was a full-width `toPandas()`, and sampling after collecting
  doesn't prevent it (`docs/context/environment.md`).

So the comparison that matters is **the estimated frame size against the memory the Python
process may use**, not against Spark's memory. Free memory can't be measured reliably inside a
shared bank container, so that limit is a configured number: `collect_budget_gb` in the
environment file (Q358), with 1.5 GB on the 8 GB laptop.

**Estimating the frame size.**
1. **Rows, exactly:** one Spark `count()` on the frame about to be collected, after eligibility,
   the split and any declared sampling. Seconds.
2. **Bytes per row, measured:** collect a small fixed sample (about 10,000 rows, a few seconds)
   and read pandas' own `memory_usage(deep=True)`. That measures strings, categoricals and nulls as
   they really are, which a type-based guess gets wrong by a factor of two or more for string
   columns.
3. **Estimate** = rows × bytes per row × 2 for the conversion peak. The estimate and, after the
   collect, the real size both go into the frames' metadata, so every run checks the estimate.

**What fails, and when.** Before any `toPandas()` in the dataset, the estimate is compared with
the budget. If it exceeds it, nothing is collected and nothing is sampled on its own (D-117
(sampling only when the config declares it)). The error names the frame, the numbers and the two
ways out:

```
train frame: 4,210,000 rows × 141 columns ≈ 6.1 GB estimated (2 × 3.0 GB), budget 1.5 GB.
Declare sampling in training.sampling:
  negative_downsampling: rare binary targets; keeps every positive and a keep fraction of the
                         negatives, prior shift applied (D-049)
  client_sample:         common targets and regression; all rows of a random share of clients
or raise collect_budget_gb in conf/local/environment.yml on a machine with more memory.
```

The adapter also sets `spark.driver.maxResultSize` to the budget, so the framework's message
fires before Spark's.

*Rough sizes,* for orientation: the `dev` preset's window frame (20k clients × 6 months × 141
columns) is about 0.15 GB. The canonical one (100k clients) is about 0.7 GB, with a peak near the
laptop's budget. A retail mart inside the bank (2M clients a month × 6 months, about half
eligible, 150 columns) is about 7 GB, so it needs sampling or a larger budget there.

**Options:**
- (A) Rows counted, bytes per row measured on a sample, a budget in GB (as above).
- (B) Bytes per row from the schema: 8 per numeric or date column, a declared width per string.
  No sample collect, but wrong for strings.
- (C) A plain row budget. Simplest, but blind to width, which ranges from 30 to 400 columns across
  use cases.

*Default:* (A).

## Settled in round 1 (2026-10-25)
Defaults unless noted. These go into `docs/` with the plan.

**Scope**
- Q349: in Stage 1 are the config spine, the adapter's session settings, source resolution with
  several sources per entity, local-tier paths, Target Factory thin and the dataset thin. The
  `hdfs dfs` transport and the registered / production roots go to M2.4.
- Q350: three major steps, each ending in your review: (1) config spine + adapter; (2) Target
  Factory + the synthetic additions; (3) dataset + `run` + the thin notebook + the LDS review
  guide.
- Q351: one use case, `cc_acquisition` on entity A. A second flag use case may join at the
  run-through.
- Q352 (your change): the synthetic package also writes a **super slim** `holdings` table, since
  the feature store's shape is unknown: the keys plus the six 0/1 holding flags (`casa_flag`,
  `cc_flag`, `td_flag`, `wealth_digital_flag`, `wealth_trad_flag`, `ebanking_flag`). The loan
  counts join it when M4 builds the count-rise rules. The mart keeps every column. The release
  example has the three source settings in one config: the mart active, the feature store alone
  and the feature store with the mart commented out (D-021 (the first release's feature store
  example)); a `feature_store` source format is refused with "not implemented until OD-26".
- Q353 (your change): Phase 3 references leave the component docs, except where a Phase 3
  requirement shapes how something is built now (e.g. the reserved `split` in the model key, the
  model interface shaped for a later `Protocol`). There the rule stays and says why. Every item
  removed is in the roadmap's Phase 3 wishlist. `llm_assist.md` is itself the Phase 3 doc and
  stays.

**Config spine**
- Q355 (your condition): eligibility steps are Spark SQL. Combined expressions work in a
  `filter`, and named conditions are reused through `define` entries (Q354 shows both). Your
  form `expr_1 == True OR expr_2 == True` works as written; `expr_1 OR expr_2` is the same.
- Q356: "non-holder at the observation month" is an eligibility step. Target Factory builds the
  target over every row of the target source, and the dataset filters afterwards.
- Q357: key columns are renamed to `unit_id` and `month` at load; the resolved config records the
  sources' names. Phase 2 requires the same key names in every source of a use case; a
  per-source rename comes when a use case needs it.
- Q359: the whole decision audit log in Stage 1: entries, storage, replay, `LOGGABLE_SETTINGS`
  with its test, `record_decision`, `show_decisions`, `resolve_config` and `decide`. Stages
  write their own entries when they are built.
- Q360 (table approved): OD-25 closes with this mapping, which becomes a D-row; the numbers
  (budgets) are set as each stage is built. On the draft inventory in `config.md` the two levels
  differ at four points only.

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

  A move between levels is a config edit before the config freezes, and a `set` on
  `automation_level` in the audit log after it, which reruns every stage from EDA.

  **Top-N** (your question) is not the first N columns by name: it is the N highest candidates
  in EDA's univariate ranking (binary: direction-agnostic AUC against the target, on every
  client in the window, D-030), plus the features the person lists. These are EDA's key
  features, each with a deep dive (`eda.md` req. 4).
- Q361: the backward-window check is replaced by "the window and `v + w` lie inside the sources'
  months".

**Environment adapter**
- Q362 (your change): `conf/local` only has to be structurally right and work on this laptop (the
  file in Q358). The local layout: the audit log and, from M2.2, the EDA and Feature Checks
  artifacts at `04_feature/<use_case>/<entity>/<data_definition_hash>/`; the model input where
  `conf/local` points (Q365); runs at `06_models/<use_case>/<entity>/<run_id>/` (M2.3).
- Q363: a `dev` preset of 20k clients × 24 months, written with the holdings table to
  `data/01_raw/synthetic_dev/`.

**Target Factory**
- Q366: the regression builder (`forward_sum` over `t+1 … t+w`) is built now; the rest of
  regression waits for M4.

**Dataset**
- Q368: `build_frames(cfg, entity, spark, stage)` joins the Public API (compat-guardian runs).
- Q369: the client split: `xxhash64(unit_id, seed) mod 1000 < 1000 × test_share`, stable across
  months, reruns and machines; test share 0.3.
- Q370: both sampling options in Stage 1: train-only, after the split, recorded with the true and
  sampled rates.
- Q372: contract checks from the per-task spec, on the eligible population before sampling; the
  rate band has no floor and a ceiling of 0.5, on the window's pooled rate, reported per month.
  Binary: a unique unit per month, a non-constant target, the rate band. Regression: unique keys,
  a non-constant and finite target.
- Q373 (your change): all joins are left joins from the governing spine. Duplicate keys in any
  source fail loud, and the join log prints each source's distinct units per month and the share
  of spine rows it matches. The target source contributes only the target. A non-key column
  present in two feature sources fails loud (renamed upstream, or by a per-source alias later).
  Rows with a null target are dropped from the modelling frames, with the share logged per
  month.

**Assumptions (accepted)**
- A1. Immutability is enforced by hashes: every artifact and audit-log entry carries the hash it
  was built from, and readers fail loud on a mismatch.
- A2. Migrations: `schema_version: 1`, an empty migrations dict with its loop, and a test that an
  unknown version fails loud.
- A3. Hashes are sha256 over canonical JSON, with `hash_version: 1` and 12-character prefixes in
  paths and `run_id`.
- A4. A separate saved targets table. *Falls away if Q365 (A) is chosen*, since the model input
  carries the target.
- A5 (updated for D-030). `Frames(window, train, test, validation, log, meta)`.
  - `window` holds every eligible unit-month in the observation window with the target, for EDA
    and Feature Checks.
  - `train` and `test` are the window split by client; `validation` is every eligible unit at `v`,
    with the `split` column so Evaluation can also show test clients only.
  - `meta` holds the per-month rows, positive rows and positive events (D-082), the null-target
    share, the sampling record, the size estimate (Q371) and the data-definition hash.
  - `build_frames(..., stage)` collects only what that stage needs.
- A6. Candidates are resolved against the joined feature schema at load (patterns, minus the keys,
  the target and its lineage) and listed in the resolved config.
- A7. The period is the month in Phase 2.
- A8. Stage functions take one entity; `run` loops over the config's entities unless `--entity`
  is given; Stage 1 ships `run` and `decide`.
- A9. `get_spark_session(settings=None)` becomes public, reads the environment file, and fails loud
  when called again with different settings (D-100 (c)).
- A10. Stage 1's tests:
  - the schema and its time rules;
  - what changes each hash;
  - the audit log's worked example;
  - Target Factory against the oracle's `realised_target`, nulls included;
  - time separation;
  - identical eligibility across frames;
  - no client in both train and test;
  - sampling train-only and after the split;
  - contract checks before sampling;
  - the budget failure;
  - duplicate keys failing loud.
- A11. A thin `01_target_factory` notebook: load the config, build, show the target rate per month,
  the lineage and the logs, then save the model input.
