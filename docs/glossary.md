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
- **Source:** an input dataset (table and schema) that a use case reads. A domain has several, and
  different use cases often read different sources.
- **Feature mart:** a source with one row per unit per month, holding the unit's description,
  current-month values and backward rollups. What retail use cases read inside the bank, and what
  the synthetic data mimics (D-056).
- **Feature store:** a shared store of engineered features with its own framework and team. The
  first release reads from it, alone or with other sources (D-075).
- **Data observability framework:** the existing framework for watching data, with its own team.
  Monitoring integrates with it in the first release (D-075).
- **Unit:** what one row describes at one point in time (client, account, card, merchant…). Shapes
  say `unit_id`; the client is the usual unit.
- **Use case:** one modelling problem (e.g. one product's acquisition propensity), defined by one
  config.
- **Instance:** a use case applied to one entity. A use case lists the entities it applies to (often
  just one), and each gets its own models.
- **Model key:** `(entity, domain, use case, split)`, which identifies one line of model versions.
  `split` is `all` in Phase 2. It is reserved so per-segment models can be added later without
  changing schemas.

## Time

- **Observation month (`obs_date`):** features are as-of this month.
- **Observation window:** the training months `t1 … tk`. Every eligible unit-month in it is a row.
- **Target window (`w`):** the forward months `(t+1 … t+w)` that a target looks at. It excludes the
  current month.
- **Backward window:** the months a rolled-up feature looks back over, including the current one.
  Default ≤ 6 months.
- **OOT validation month (`v`):** the out-of-time month the model is judged on. `v ≥ tk + w`, so its
  target window never overlaps a training target window.
- **Inference month:** the month being scored.
- **Panel edge:** months near either end of the data where a full window is missing. Targets there
  are null.
- **Gap months:** the months between the observation window and the validation month. Their labels
  are never used; their features may be used for label-free checks (D-048).

## Data and splits

- **Train / test / validation:** train and test share the observation window and are split by
  client; validation is out of time (OOT). Some texts swap "test" and "validation". Here
  **validation always means OOT**.
- **Eligibility:** the population a use case models and scores. It is defined by ordered config
  steps and applied identically to train, test, validation and inference.
- **Contract checks:** checks on the true population before any sampling: unique unit per month,
  a non-degenerate target, a plausible rate band. Which apply comes from the per-task spec
  (`docs/components/dataset.md`, `CLAUDE.md` §4.8).
- **Label-free check:** a check or comparison that uses no labels (e.g. PSI). It may use months
  after the observation window, but never the validation month (D-048).
- **Positive rows vs positive events:** one conversion makes up to `w` consecutive rows positive.
  Reports show both counts. Wherever a count of positives decides something (minimum support,
  a standard error, the AUC floor, a per-month statistic) it counts events, i.e. distinct
  converting clients in that slice, and bootstraps and CV folds resample clients (D-082).
- **Data definition / data-definition hash:** entity, source, eligibility, target, time settings and
  candidates. Its hash keys the EDA and Feature Checks artifacts that training requires.
- **Row budget:** the maximum number of rows collected from Spark for training.
- **Learning-curve check:** training on 25 / 50 / 100% of the row budget and comparing the
  results, to tell whether the cap costs accuracy (`docs/components/dataset.md`).
- **Downsampling:** train-only sampling (of negative rows or of clients). It is always recorded, and
  the prior-shift offset undoes any change it makes to the class balance.
- **Recency weighting:** optional sample weights that give the later months of the observation
  window more weight; off by default (`docs/components/dataset.md`).

## Features

- **Candidates:** the feature list before screening (explicit names or patterns).
- **Features (model inputs):** what the model finally uses. See the resolution rule in
  `docs/components/feature_ledger.md`.
- **Target lineage:** the columns a target was built from. They are excluded automatically.
- **Flag:** a check's finding. A flag never drops a feature by itself.
- **Human decision:** either *exclude* or *keep* (despite a flag or against automated pruning),
  as grouped lists with one note per group (whether a note is required is OD-10; proposal: only for
  a `keep` that resolves a flag). In the config today; whether it moves to the decision audit log
  is OD-10 (`docs/components/feature_ledger.md`).
- **Human gate:** the feature sign-off's place in the flow: it closes Feature Checks in manual
  runs and follows training in hands-off runs, always before register
  (`docs/components/feature_checks.md`, D-076).
- **Feature sign-off:** a person's recorded approval of the features a model may use: the list after
  Feature Checks (automated selection can only drop from it) or, in hands-off runs, the model's final
  list after training. Required before any model is registered, at every automation level (D-076).
  It is given over the model's final list, with flags grouped and features sorted by importance;
  the candidate list is reviewed only where flagged (D-092).
- **Promotion sign-off:** the approved PR that lets `promote` pick a registered version for
  production (D-033). Separate from the feature sign-off, and from the CR process that runs
  `deploy`. The **sign-off log** (Phase 3) records PR approvers in the registry; the feature
  sign-off is recorded with the run already in Phase 2.
- **Automated selection:** relevance pruning inside Training, on the train split only.
- **Feature ledger:** the table recording every candidate's path through EDA, checks, decisions,
  selection and use in the model.
- **Key features:** the top-N features by univariate ranking, plus the ones the user lists. EDA
  deep-dives them.
- **Feature signature:** a hash of the final feature list.

## Config and guidance

- **Config:** the file that defines a use case (one file is the goal). **Frozen config:** the fully
  resolved config saved with every artifact.
- **Housekeeping block:** the part of the frozen config that records the framework and key-library
  versions, when the run was made and the run's identities. The config hash excludes it
  (`docs/components/config.md` req. 2, D-088).
- **Base / local config:** `conf/base/` (committed, generic) merged with `conf/local/` (gitignored,
  environment-specific).
- **Profile:** the config field (`quick`, `standard` or `thorough`) that sets the defaults for
  every stage. It is becoming the automation level; the field keeps its name until the levels
  exist (D-087). In the synthetic data spec (`docs/components/test_harness.md`), "profile" means a
  client tier (Private, Priority, Affluent, Mass), not this field.
- **Automation level:** how much of a run is decided by rules and how much by a person: Phase 2
  has `autonomous` (today's `quick`) and `assisted` (today's `standard`); `manual` comes later.
  Every level runs the same checks; the difference is human time, and a higher-value use case
  brings more people and inputs that shape its choices (D-077, D-085, D-087). Not a lifecycle
  tier.
- **Decision audit log:** (direction, OD-10) the record of every decision taken after the config,
  automated or human; the config itself never changes. The feature ledger is its per-feature part.
- **Decision point / pathway:** a decision point is a place in a run where something is chosen, by
  a rule or a person (draft inventory in `docs/components/config.md`); a run's pathway is the
  chain of decision points it passed and what was chosen at each (direction, OD-10).
- **Decision (business decision):** how the scores will be used (e.g. top-N list, threshold, ranking,
  probability). It drives the optimisation metric, the gates and what reports emphasise.
- **Choices block:** the opening section of every report: what was chosen, the alternatives, and
  rule-based warnings.

## Stages and modelling

- **Target Factory:** the optional stage that builds targets (crunch name: Data Creation).
- **Notebook mode / config mode:** Target Factory's two ways of running one spec: build, inspect
  and save a table that later stages read, or hand the result to the next stage in memory with
  the spec's hash recorded (`docs/components/target_factory.md`).
- **EDA**, **Feature Checks**, **Training**, **Evaluation**, **Inference**, **Monitoring** (earlier
  name: Tracking): the stages, in run order with the lifecycle steps between Evaluation and
  Inference.
- **Due-diligence gate:** Training refuses to run unless EDA and Feature Checks artifacts exist for
  the same data-definition hash; hands-off profiles run them first (`CLAUDE.md` §4.13, D-031).
- **Modelling path:** `automl` (FLAML) or `predefined` (a named model family tuned with Optuna;
  Phase 3, D-080).
- **Model interface:** the small `fit` / `predict` / `describe` contract every model family
  follows: plain functions per family in Phase 2, wrapped in a `Protocol` once the predefined path
  exists (Phase 3, D-100).
- **Trade-off chart:** (Phase 3) tuning trials plotted as in-time metric vs train–test gap; it
  weighs train and test metrics, never validation (D-083). The user (or a profile rule) picks the
  point.
- **Calibration (prior shift):** a log-odds offset that undoes the class-balance change caused by
  sampling, computed from the effective (weighted) training rate, so it is zero when the balance is
  unchanged. Example: at a true rate of 0.2%, keeping every positive and 5% of negatives trains on
  about 4% positives, so the model's scores come out about 20 times too high; subtracting
  `log(20) ≈ 3.0` from every score's log-odds puts them back on the true scale and leaves the
  ranking untouched. **Calibration step:** a general calibration (e.g. Platt or isotonic) fitted on
  out-of-fold predictions inside train (D-049).
- **Refit:** an optional retrain of an evaluated run on all clients or an extended window, with the
  same features and hyperparameters. It is a new run linked to its evaluated parent (D-052).
- **Per-task spec:** the plain dict, one entry per task, that holds every task-specific hook
  (target builder, ranking statistic, metrics, baselines, calibration, output columns…) (D-050).
- **Window ablation:** the same config trained on windows of different lengths and compared on one
  validation month.
- **Experiment sweep / variant:** a sweep runs one config several times with a single field changed
  (e.g. the observation window); each run is a variant. A sweep that picks a variant picks on
  train and test metrics, weighted; the validation month is reported, never chosen on (D-083).

## Lifecycle

- **Local / registered / production:** the three model tiers.
- **Register:** local → registered, producing an immutable, hashed version of a model key. A
  registered model is any model a person has defended (the feature sign-off, D-076) and wants to
  keep; `promote` picks the production candidate among them (D-095).
- **Promote:** choosing a registered version for production. The approved PR is the promotion
  sign-off, and promotion builds the verified deployment bundle.
- **Promotion gate:** the metric check a model must pass on its way to production; its metric is
  derived from the declared decision (`docs/components/config.md` req. 4, D-032).
- **Deploy:** the change-request process copies the bundle to production paths and records it. A
  data scientist's session never deploys.
- **CR (change request):** the process for production changes: pre-agreed windows, platform and
  security approval.
- **Model version:** one registered model of a model key. A retrain creates a new version.
- **Run / `run_id`:** one training run of one instance (config hash + entity + timestamp, D-088).
  **Model hash:** a hash over the bundle's per-part hashes (encoder, model, calibration with the
  prior-shift offset, metadata), so any part changing changes it (D-094).
- **Recipe / `recipe_hash`:** what a model is a fit of: the frozen config, features,
  hyperparameters, encoder levels and calibration spec. A refit, or a retrain in production, is
  one more fit of the same recipe, linked by `parent_run_id` (D-096).
- **Code version:** framework version + use-case repo commit, recorded with every model.
- **Scoring batch / `scoring_batch_id`:** one inference run. **Manifest:** links a scoring batch to
  the models that produced it.
- **Model card:** the generated, versioned record of a model's facts.
- **Model bundle:** the saved model a run produces (encoder, model, calibration), in a versioned
  format (D-051), never pickle (D-078).
- **Drift reference:** the feature and score distributions saved at training, on the true
  population, that monitoring compares against (D-054).
- **Framework pin:** the framework version a use case runs with. Its models are scored with it, and
  the use case upgrades it at its own pace (D-047).
- **Base image:** the internal devcontainer image the package ships in, through Nexus. Images are
  supported for a year, and the image a use case starts on pins its framework version (D-074).
- **Registry tables:** the registered-models and production-models tables that people query.
- **Model inventory:** the overview of every model across use cases and entities (design open,
  OD-14).

## Reports and evaluation

- **Report:** a self-contained HTML artifact produced by one stage.
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
- **Oracle:** the hidden per-row truth beside the synthetic mart: each client's hidden traits and
  the true chance behind every event. A model that beats its AUC is almost certainly leaking
  (`docs/components/test_harness.md`).
- **Major step:** a new component, config section, public function or dependency, or a redesign the
  user flags. It starts with research and a holistic review (`CLAUDE.md` §1).
- **D-nnn / OD-nn / T-nn:** identifiers for a decision (`docs/decisions.md`), an open decision
  (`docs/roadmap.md`) and a trap (`docs/context/lessons.md`).
- **Bank parity:** matching the internal environment's versions and behaviour. **One-way code
  flow:** code goes into the bank; nothing comes out.
- **Worknotes:** committed notes in `worknotes/`, written for the builder and the Lead DS: the sync
  page (what to review, shared open questions), the verbose log, and per-topic chat handovers.
