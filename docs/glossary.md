# Glossary

**Verdict:** each term has one meaning, used the same way in docs, configs, code and artifacts. When
a term is added or changes meaning, update it here first, then use it consistently (`CLAUDE.md` §8).
Whether this glossary is also published to the wider unit is part of the open documentation question
(OD-20 in `docs/roadmap.md`).

## Organisation

- **Entity:** a legal entity (subsidiary). Data is never merged across entities, and models are
  built per entity.
- **Domain:** a business line (retail, SME, corporate). It is configuration, never a name in code.
- **Segment:** a client group *within* a population (e.g. a value tier), used for stratified metrics
  and segment comparisons. Not a domain.
- **Source:** an input dataset (table and schema) that a use case reads, named in the config by a
  logical name that the environment file maps to a physical table or path per entity (D-130). A
  domain has several, and different use cases often read different sources.
- **Governing spine:** the first of a use case's ordered feature sources per entity. Its rows are
  the population; the other feature sources and the target source are left-joined to it on the
  keys (D-129).
- **Feature mart:** a source with one row per unit per month, holding the unit's description,
  current-month values and backward rollups. What retail use cases read inside the bank, and what
  the synthetic data mimics (D-041).
- **Feature store:** a shared store of engineered features with its own framework and team. The
  first release reads from it in Stage 1 (M2.1 Foundation), where a use case's data comes in,
  alone or with other sources; no later stage knows about it (D-021).
- **Data observability framework:** the existing framework for watching data, with its own team.
  Monitoring integrates with it in the first release (D-021).
- **Unit:** what one row describes in one period (client, account, card, merchant…). Shapes say
  `unit_id`, held as a string whatever the source's type; the client is the usual unit.
- **Use case:** one modelling problem (e.g. one product's acquisition propensity), defined by one
  config and its decision audit log; a repo may hold several similar use cases (D-006). Its name
  (`use_case`) is letters, digits, underscores and hyphens, any case, compared ignoring case;
  its lower-case form names folders and columns (D-128).
- **Product / activity:** what a use case scores (e.g. Forex) and the behaviour it predicts (e.g.
  activation), carried by the master layer; explicit optional config fields, added when the
  master layer first needs them, never parsed from the use case's name (D-128).
- **Instance:** a use case applied to one entity. A use case lists the entities it applies to (often
  just one), and each gets its own models.
- **Model key:** `(entity, domain, use case, split)`, which identifies one line of model versions.
  `split` is `all` in Phase 2. It is reserved so per-segment models can be added later without
  changing schemas.

## Time

- **Period:** the unit of analysis, `time.period`: a calendar month, an ISO week (Monday to
  Sunday) or a day. A panel has one row per unit per period, the key column is `period`, and a
  period is held as its last day (a month's last day, a week's Sunday, the day itself); a config
  writes a month as its first or its last day, a week as any of its days, a day as itself.
  Steps between periods go through the period index (`periods.PERIODS`), never date arithmetic
  (D-129, T19). "Month" means a calendar month only.
- **Observation period:** features are as-of this period; the target looks forward from it.
- **Observation window:** the training periods `t1 … tk` (`time.observation_window`). Every
  eligible unit-period in it is a row.
- **Target window (`w`):** the forward periods `(t+1 … t+w)` that a target looks at
  (`time.target_window`, in periods). It excludes the current period.
- **Backward window:** the periods a rolled-up feature looks back over, including the current
  one. Upstream's business; the framework doesn't check it (D-129).
- **Validation period (`v`):** the out-of-time (OOT) period the model is judged on
  (`time.validation_period`). `v ≥ tk + w` by period index, so its target window never overlaps
  a training target window. Set in the config; changing it after the config freezes is an
  audit-log entry, refused when Feature Checks compared that period (D-088). "Validation month"
  is the retired name.
- **Inference period:** the period being scored; a run argument.
- **Panel edge:** periods near either end of the data where a full window is missing. Targets
  there are null.
- **Gap periods:** the periods between the observation window and the validation period. Their
  labels are never used; their features may be used for label-free checks (D-030).

## Data and splits

- **Train / test / validation:** train and test share the observation window and are split by
  client; validation is out of time (OOT). Some texts swap "test" and "validation". Here
  **validation always means OOT**. EDA uses every client of the window after the analysis
  filters and Feature Checks every eligible client, labels included; the client split happens
  after Feature Checks, and from Training on, fitting, selection, calibration and every choice
  use train-split clients only (D-030).
- **Eligibility:** the population a use case models and scores. It is defined by two ordered
  lists of config steps, `analysis` and `modelling`, run as one order and applied identically
  to train, test, validation and inference. An **analysis filter** drops its rows before EDA
  (who the analysis sees); a **modelling filter** keeps its rows for EDA, tagged 0/1 by the
  step's name (a **modelling tag**: a reference group and a stratum, e.g. current holders vs
  non-holders), and drops them before Feature Checks (who the model sees). `eligible` marks the
  rows every modelling filter passes (D-129; `dataset/eligibility.py`).
- **Define / filter step:** the two kinds of eligibility entry, both Spark SQL (D-129). A
  `define` names a boolean condition that the entries after it, in either list, reuse by name
  and is dropped before the candidates are resolved; a `filter` keeps the rows where its
  condition is true (a null counts as false), with a required reason, and logs rows in → out.
- **Frames:** what the dataset hands a stage: `Frames(window, train, test, validation, log,
  meta)`. The window frame (every unit-period in the observation window after the analysis
  filters, the modelling tags as columns, every client, labels included) serves EDA; its
  eligible rows serve Feature Checks; train / test / validation serve Training on
  (D-030; `docs/components/dataset.md`).
- **Model input:** one saved table per name (`data.model_input`), written by `save_model_input`
  from the Target Factory notebook or `run a.yml b.yml --stages target_factory` for one or
  several use cases that share the entity's feature sources, keys and period: the sources
  joined plus one target column per use case, `target_<use_case>` (every period Target Factory
  could build it; null at the panel edge, for leavers and across gaps), nothing else.
  Eligibility, the candidates, the contract checks and the client split are derived on read
  from the reader's config; the reader keeps its own target as `target` and drops the others,
  which are never candidates. Its `_model_input.json` holds the shared sources, keys and
  period, the periods covered, the join log and, per use case, the target-spec hash, lineage,
  window and null share; a reader is refused on another version, other sources, keys or
  period, a missing use case, another target spec or uncovered periods, never on a changed
  eligibility, window, split or candidate list. Saving it freezes each config's data part;
  inference reads the sources instead (D-131).
- **Contract checks:** checks on the true population before any sampling, on every read of the
  model input as in memory: unique unit per period, a non-degenerate target, a plausible rate
  band, the null callout from the share Target Factory recorded. Which apply comes from the
  per-task spec (`docs/components/dataset.md`, `CLAUDE.md` §4.8).
- **Label-free check:** a check or comparison that uses no labels (e.g. PSI). It may use periods
  after the observation window, but never the validation period (D-030).
- **Positive rows vs positive events:** one conversion makes up to `w` consecutive rows positive.
  Reports show both counts. Wherever a count of positives decides something (minimum support,
  a standard error, the AUC floor, a per-period statistic) it counts events, i.e. distinct
  converting clients in that slice, and bootstraps and CV folds resample clients (D-082).
- **Data definition / data-definition hash:** the task, entity, sources, eligibility, target
  spec, the period, the observation window, the target window and candidates (D-088). Its hash keys the
  EDA and Feature Checks artifacts that training requires; the validation period sits outside
  it: EDA never reads it, and Feature Checks reads it only to leave it out of its comparisons.
  The model input is keyed without it (D-131).
- **Collect budget / collect printout:** `collect_budget_gb` in the environment file is the
  memory a collected frame may take in the Python process. Before any frame leaves Spark the
  dataset prints its rows, columns, the estimated size (rows × measured bytes per row × 2) and
  the budget; above the budget the printout becomes a callout naming the two ways out (declare
  sampling, or raise the budget and the Spark settings), and the collect proceeds (D-133). "Row
  budget" is the retired name.
- **Learning-curve check:** training on 25 / 50 / 100% of the sampled rows and comparing the
  results, to tell whether sampling costs accuracy (`docs/components/dataset.md`).
- **Downsampling:** train-only sampling (of negative rows or of clients), only when the config
  declares it; the framework never samples on its own (D-117). It is always recorded, and the
  prior-shift offset undoes any change it makes to the class balance.
- **Recency weighting:** sample weights that give the later periods of the observation window
  more weight; not in Phase 2 (D-117).

## Features

- **Candidates:** the feature list before screening (explicit names or patterns).
- **Features (model inputs):** what the model finally uses. See the resolution rule in
  `docs/components/feature_ledger.md`.
- **`__other__`:** the reserved categorical level that rare and unseen levels map to, counted
  wherever it is used (D-037).
- **Target lineage:** the columns a target was built from. They are excluded automatically.
- **Flag:** a check's finding. A flag never drops a feature by itself.
- **Human decision:** either *exclude* or *keep* (despite a flag or against automated pruning),
  in groups with one note per group, recorded as entries in the decision audit log (D-125;
  `docs/components/config.md`).
- **Human gate:** the feature sign-off's place in the flow: one gate, after training and before
  register, at every automation level (D-031). At the `assisted` level Feature Checks ends in a
  review of its flags, whose keep / exclude decisions go into the audit log; that review is not the
  sign-off (`docs/components/feature_checks.md`).
- **Feature sign-off:** a person's recorded approval of the features a model may use, given over the
  model's final feature list after training, with flags grouped and features sorted by importance;
  the candidate list is reviewed only where flagged. Required before any model is registered, at
  every automation level (D-031).
- **Promotion sign-off:** the approved PR that lets `promote` pick a registered version for
  production (D-033). Separate from the feature sign-off, and from the CR process that runs
  `deploy`. Phase 2 builds no log of who signs off or approves a model: approvals stay in the PR
  and the change request, outside the framework; which source of people logs to build in is a
  later question (D-033). The feature sign-off is an audit-log entry that `register`
  checks (D-031, D-125).
- **Automated selection:** relevance pruning inside Training, on the train split only; its
  importance pruning reuses the calibration step's client-grouped out-of-fold folds (D-106).
- **Feature ledger:** the table recording every candidate's path through EDA, checks, decisions,
  selection and use in the model.
- **Key features:** the top-N features by univariate ranking, plus the ones the user lists. EDA
  deep-dives them.
- **Feature signature:** a hash of the final feature list.

## Config and guidance

- **Config / resolved config:** the config is the YAML file that holds a use case's intent (one
  file unless it bloats, D-043); its data part (sources, keys, period, target spec, target
  window) is frozen once the model input is saved, or at the first EDA run when the frames are
  built in memory, and the rest of the data definition changes only by a new config, which
  reruns EDA onwards and keeps the saved table (D-125). The **resolved config** is the config with the
  audit-log entries replayed: saved with every artifact and report, it reproduces a run and is what
  `recipe_hash` covers (D-125). "Frozen config" is the retired name for the resolved config.
- **Housekeeping block:** the part of the resolved config that records the framework and key-library
  versions, when the run was made and the run's identities. The config hash excludes it
  (`docs/components/config.md` req. 2, D-088).
- **Environment file:** `conf/local/environment.yml` (gitignored), the one file of environment
  facts: Spark settings, roots, the physical sources per entity by logical name, the collect
  budget, the theme. It has its own schema (an unknown key fails loud), is loaded beside the
  config by a path argument or `CORE_MODELLING_ENVIRONMENT`, is never merged into it and sits
  outside every hash (D-130). `conf/base/` holds the committed use-case configs, the template and
  the environment file's example. "Base / local config" and the merge are retired.
- **Profile:** the retired name of the automation level and its config field (D-023). In the
  synthetic data spec (`docs/components/test_harness.md`), "profile" means a client tier (Private,
  Priority, Affluent, Mass), not this field.
- **Automation level:** the config field `automation_level`, which sets the defaults for every
  stage and says how much of a run is decided by rules and how much by a person: Phase 2 has
  `autonomous` (formerly `quick`) and `assisted` (formerly `standard`); `manual` comes later.
  Every level runs the same checks; the difference is human time, and a higher-value use case
  brings more people and inputs that shape its choices. What each level decides by rule and by a
  person at each decision point is the mapping D-132 (`docs/components/config.md`). A level
  changes through a config edit before the config freezes and a `set` entry in the audit log
  after it, never a CLI override (D-023). Not a lifecycle tier.
- **Decision audit log:** the append-only record of every decision taken after Target Factory, by
  a person or a rule; the config itself never changes (D-125). Replaying the config plus entries
  1–n gives the **resolved config**, a run's one input; it can be saved as one file. The feature
  ledger is its per-feature part (`docs/components/config.md`).
- **Revert:** the audit-log operation that goes back to the state after an earlier entry
  (`to_seq`; 0 is the config as written): replay restarts from there and the later entries
  continue; the undone entries stay in the log as the trail, and `upto` still reproduces every
  earlier state. Written with `record_decision(…, revert_to=n)` or `decide --revert-to n`
  (D-125).
- **Decision point / pathway:** a decision point is a place in a run where something is chosen, by
  a rule or a person (the table in `docs/components/config.md`, D-132); a run's pathway is the
  chain of decision points it passed and what was chosen at each, read from the decision audit log.
- **Decision (business decision):** how the scores will be used (e.g. top-N list, threshold, ranking,
  probability). It drives the optimisation metric, the gates and what reports emphasise.
- **Choices block:** the opening section of every report: what was chosen, the alternatives, and
  rule-based warnings.

## Stages and modelling

- **Target Factory:** the optional stage that builds targets (crunch name: Data Creation).
- **Notebook mode / config mode:** Target Factory's two ways of running one spec: build, inspect
  and save the model input that later stages read, or hand the result to the next stage in memory
  with the spec's hash recorded (`docs/components/target_factory.md`, D-131).
- **EDA**, **Feature Checks**, **Training**, **Evaluation**, **Inference**, **Monitoring** (earlier
  name: Tracking): the stages, in run order with the lifecycle steps between Evaluation and
  Inference.
- **Due-diligence gate:** Training refuses to run unless EDA and Feature Checks artifacts exist for
  the same data-definition hash; the `autonomous` level runs them first (`CLAUDE.md` §4.13, D-031).
- **Modelling path:** `automl` (FLAML, the only path in Phase 2) or `predefined` (a named model
  family tuned with Optuna; later, D-020).
- **Model interface:** the small `fit` / `predict` / `describe` contract every model family
  follows: plain functions per family in Phase 2, written so a `Protocol` can wrap them unchanged
  once the predefined path exists (D-100), which is why the shape is fixed now.
- **Trade-off chart:** (later, with the predefined path) tuning trials plotted as in-time metric
  vs train–test gap; it
  weighs train and test metrics, never validation (D-083). The user (or a level's rule) picks the
  point.
- **Calibration (prior shift):** a log-odds offset that undoes the class-balance change caused by
  sampling, computed from the effective (weighted) training rate (in Phase 2, with no sample
  weights, the sampled rate, D-117), so it is zero when the balance is unchanged. Example: at a true
  rate of 0.2%, keeping every positive and 5% of negatives trains on about 4% positives, so the
  model's scores come out about 20 times too high; subtracting `log(20) ≈ 3.0` from every score's
  log-odds puts them back on the true scale and leaves the ranking untouched. **Calibration step:**
  a general calibration (e.g. Platt or isotonic) fitted on out-of-fold predictions inside train
  (D-049).
- **Refit:** one more fit of the same recipe, linked to its evaluated parent by `parent_run_id`
  (D-052). In Phase 2 it is the production retrain, on the same data definition, which keeps the
  window and the clients and moves only the inference period; there is no refit command in the
  sandpit. Refits on moved or extended data (later periods, all clients, a longer window) come
  later (D-052).
- **Per-task spec:** the plain dict, one entry per task, that holds every task-specific hook
  (target builder, ranking statistic, metrics, baselines, calibration, output columns…) (D-050).
- **Window ablation:** the same config trained on windows of different lengths; the choice between
  them weighs train and test metrics, and the validation period is reported, never chosen on
  (D-083).
- **Experiment sweep / variant:** a sweep runs one config several times with a single field changed
  (e.g. the observation window); each run is a variant. A sweep that picks a variant picks on
  train and test metrics, weighted; the validation period is reported, never chosen on (D-083).

## Lifecycle

- **Local / registered / production:** the three model tiers.
- **Sandpit:** the local and registered (HDFS) tiers. Anything saved there may be in any format,
  pickle included; what is promoted to production is never pickle, so `register` always writes the
  lossless plain-data model too, which `promote` takes (D-051).
- **Register:** local → registered, producing an immutable, hashed version of a model key. A
  registered model is any model a person has defended (the feature sign-off, D-031) and wants to
  keep; `promote` picks the production candidate among them (D-033).
- **Promote:** choosing a registered version for production. The approved PR is the promotion
  sign-off, and promotion builds the verified deployment bundle.
- **Promotion gate:** the metric check a model must pass on its way to production; its metric is
  derived from the declared decision (`docs/components/config.md` req. 4, D-032).
- **Deploy:** the change-request process moves the promoted bundle to production paths and records
  it. By default production then retrains the recipe on the same data definition before it scores;
  deploying the fitted model without a retrain is also allowed (D-033, D-052). A data scientist's
  session never deploys.
- **Production retrain check:** the check a production retrain passes against its evaluated parent
  before it scores: label-free agreement on the inference period; its own test-split AUC and
  calibration per window period; per-period rows and positive events against the parent's EDA
  artifact; each within tolerances declared in the config, never on the validation period. Failing
  keeps whatever production model is current and is recorded; at a first deploy the deploy fails
  loud (D-052).
- **CR (change request):** the process for production changes: pre-agreed windows, platform and
  security approval.
- **Model version:** one registered model of a model key. A retrain in the sandpit creates a new
  version; what a production retrain records is open (OD-27).
- **Run / `run_id`:** one training run of one instance (resolved-input hash + entity + timestamp,
  D-088).
- **Resolved-input hash / `hash_version`:** the resolved-input hash is the hash of a run's config
  plus its audit-log entries, resolved (D-125). Every hash is computed on the migrated canonical
  form and stored with a `hash_version`, so a migration doesn't orphan old artifacts (D-088).
  **Model hash:** a hash over the bundle's per-part hashes (encoder, model, calibration with the
  prior-shift offset, metadata), so any part changing changes it (D-094).
- **Recipe / `recipe_hash`:** what a model is a fit of: the resolved config, features,
  hyperparameters, encoder levels and calibration spec. A refit (in Phase 2, the production
  retrain) is one more fit of the same recipe, linked by `parent_run_id` (D-052).
- **Code version:** framework version + use-case repo commit, recorded with every model.
- **Scoring batch / `scoring_batch_id`:** one inference run. **Manifest:** links a scoring batch to
  the models that produced it.
- **Scores table (master layer):** the framework's own scores output: long format, fully traceable
  to model, run and config, shared by every pinned version (D-007). **Consumable tables** in a
  consumer platform's format are built from it outside the framework (D-016).
- **Exit point:** an output another team builds on: the scores table and manifest, the model
  bundle, registry records, monitoring tables, the model card. Their shapes come close to final
  before their contents deepen (D-022).
- **Model card:** the generated, versioned record of a model's facts.
- **Model bundle:** the saved model a run produces (encoder, model, calibration), in a versioned
  format (D-051); what is promoted is never pickle.
- **Drift reference:** the feature and score distributions saved at training, on the true
  population, that monitoring compares against (D-054).
- **Framework pin:** the framework version a use case runs with. Its models are scored with it, and
  the use case upgrades it at its own pace (D-047).
- **Base image:** the internal devcontainer image the package ships in, through Nexus. Images are
  supported for a year, and the image a use case starts on sets its default framework version,
  which the use case pins and may raise within the image's year (D-024, D-047).
- **Registry tables:** the registered-models and production-models tables that people query.
- **Registry events / `production.json`:** the Phase 2 lifecycle records, each mapping one-to-one
  onto an MLflow concept (run, parameters, metrics, registered model version): registry events are
  append-only records (UUID, model key, version, hashes, framework version) from which the registry
  tables derive; a small `production.json` per model key is the one record every pinned version
  reads to find the production model, for the whole of major version 1. MLflow, once integrated
  (M4, OD-08), is a store beside these records, never a replacement (D-111).
- **Model inventory:** the overview of every model across use cases and entities (design open,
  OD-14).

## Reports and evaluation

- **Report:** a self-contained HTML artifact. EDA, Feature Checks, the model results (Evaluation)
  and Monitoring write one each, plus the model card; the other stages write artifacts only (D-036).
- **Core / extended views:** views every model family must render / views rendered where compatible.
- **View slot:** a place in a report filled by the first compatible method (e.g. feature effects).
- **Compatibility table:** maps view × model family → method or "not available: reason", decided
  before anything runs.
- **Stratified metrics:** every metric overall and per level of the configured variables.
- **Baselines:** population base rate (business reporting); previous model and historic predicted
  rate (internal metrics).

## Process

- **Crunch:** the 2–3 week prototype (`legacy/propensity_crunch/`). **Phase 2:** the current
  build-out (`docs/context/project.md`).
- **Depth levels:** full · deep · thin · stub (definitions in `docs/roadmap.md`). Not to be confused
  with STUB / BUILD / MIN in `docs/reference/`.
- **Walking skeleton:** every stage built thin end to end before any is deepened.
- **Deepening round:** a milestone after the walking skeleton that takes chosen components from
  thin towards deep; at most 2–3 per phase (`docs/roadmap.md`).
- **Pre-release / release 1.0:** the December 2026 pre-release moves the code into the bank's
  internal repo, committed and demonstrated, not into production; release 1.0 meets Phase 2's
  definition of done and is the first change request (D-021, D-022).
- **Run-through:** the end-to-end pass that follows each build round: the pre-release, then
  release 1.0 (D-022).
- **Oracle:** the hidden per-row truth beside the synthetic mart: each client's hidden traits and
  the true chance behind every event. A model that beats its AUC by more than about two standard
  errors on positive events is leaking (D-100 (e), `docs/components/test_harness.md`).
- **Major step:** a new component, config section, public function or dependency, or a redesign the
  user flags. It starts with research and a holistic review (`CLAUDE.md` §1).
- **D-nnn / OD-nn / T-nn:** identifiers for a decision (`docs/decisions.md`), an open decision
  (`docs/roadmap.md`) and a trap (`docs/context/lessons.md`).
- **Bank parity:** matching the internal environment's versions and behaviour. **One-way code
  flow:** code goes into the bank; nothing comes out.
- **Worknotes:** committed notes in `worknotes/`, written for the SDS and the LDS: the sync
  page (what to review, shared open questions), the verbose log, and per-topic chat handovers.
