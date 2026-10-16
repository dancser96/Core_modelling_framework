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
- **Positive rows vs positive events:** one conversion makes up to `w` consecutive rows positive.
  Reports show both counts.
- **Data definition / data-definition hash:** entity, source, eligibility, target, time settings and
  candidates. Its hash keys the EDA and Feature Checks artifacts that training requires.
- **Row budget:** the maximum number of rows collected from Spark for training.
- **Downsampling:** train-only sampling (of negative rows or of clients). It is always recorded, and
  the prior-shift offset undoes any change it makes to the class balance.

## Features

- **Candidates:** the feature list before screening (explicit names or patterns).
- **Features (model inputs):** what the model finally uses. See the resolution rule in
  `docs/components/feature_ledger.md`.
- **Target lineage:** the columns a target was built from. They are excluded automatically.
- **Flag:** a check's finding. A flag never drops a feature by itself.
- **Human decision:** in config, either *exclude* or *keep* (despite a flag or against automated
  pruning), always with a reason.
- **Automated selection:** relevance pruning inside Training, on the train split only.
- **Feature ledger:** the table recording every candidate's path through EDA, checks, decisions,
  selection and use in the model.
- **Key features:** the top-N features by univariate ranking, plus the ones the user lists. EDA
  deep-dives them.
- **Feature signature:** a hash of the final feature list.

## Config and guidance

- **Config:** the file that defines a use case (one file is the goal). **Frozen config:** the fully
  resolved config saved with every artifact.
- **Base / local config:** `conf/base/` (committed, generic) merged with `conf/local/` (gitignored,
  environment-specific).
- **Profile:** `quick`, `standard` or `thorough`. Profiles set the defaults for every stage, from
  hands-off (~3 days) to deep (~3 weeks).
- **Decision (business decision):** how the scores will be used (e.g. top-N list, threshold, ranking,
  probability). It drives the optimisation metric, the gates and what reports emphasise.
- **Choices block:** the opening section of every report: what was chosen, the alternatives, and
  rule-based warnings.

## Stages and modelling

- **Target Factory:** the optional stage that builds targets (crunch name: Data Creation).
- **EDA**, **Feature Checks**, **Training**, **Evaluation**, **Inference**, **Monitoring** (earlier
  name: Tracking): the stages, in run order with the lifecycle steps between Evaluation and
  Inference.
- **Modelling path:** `automl` (FLAML) or `predefined` (a named model family tuned with Optuna).
- **Model interface:** the small `fit` / `predict` / `describe` contract that both paths implement.
- **Trade-off chart:** tuning trials plotted as in-time metric vs train–test gap. The user (or a
  profile rule) picks the point.
- **Calibration (prior shift):** a log-odds offset that undoes the class-balance change caused by
  sampling, computed from the effective (weighted) training rate, so it is zero when the balance is
  unchanged. **Calibration step:** a general calibration (e.g. Platt or isotonic) fitted on
  out-of-fold predictions inside train (D-049).
- **Refit:** an optional retrain of an evaluated run on all clients or an extended window, with the
  same features and hyperparameters. It is a new run linked to its evaluated parent (D-052).
- **Per-task spec:** the plain dict, one entry per task, that holds every task-specific hook
  (target builder, ranking statistic, metrics, baselines, calibration, output columns…) (D-050).
- **Window ablation:** the same config trained on windows of different lengths and compared on one
  validation month.
- **Experiment sweep / variant:** a sweep runs one config several times with a single field changed
  (e.g. the observation window); each run is a variant. A sweep that picks a variant labels the
  winner's validation result as optimistic (D-053).

## Lifecycle

- **Local / registered / production:** the three model tiers.
- **Register:** local → registered, producing an immutable, hashed version of a model key. The gates
  are open (OD-09).
- **Promote:** choosing a registered version for production. The approved PR is the sign-off, and
  promotion builds the verified deployment bundle.
- **Deploy:** the change-request process copies the bundle to production paths and records it. A
  data scientist's session never deploys.
- **CR (change request):** the process for production changes: pre-agreed windows, platform and
  security approval.
- **Model version:** one registered model of a model key. A retrain creates a new version.
- **Run / `run_id`:** one training run. **Model hash:** a content hash of the model file.
- **Code version:** framework version + use-case repo commit, recorded with every model.
- **Scoring batch / `scoring_batch_id`:** one inference run. **Manifest:** links a scoring batch to
  the models that produced it.
- **Model card:** the generated, versioned record of a model's facts.
- **Model bundle:** the saved model a run produces (encoder, model, calibration), in a versioned
  format (D-051).
- **Drift reference:** the feature and score distributions saved at training, on the true
  population, that monitoring compares against (D-054).
- **Framework pin:** the framework version a use case runs with. Its models are scored with it, and
  the use case upgrades it at its own pace (D-047).
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
- **Major step:** a new component, config section, public function or dependency, or a redesign the
  user flags. It starts with research and a holistic review (`CLAUDE.md` §1).
- **D-nnn / OD-nn / T-nn:** identifiers for a decision (`docs/decisions.md`), an open decision
  (`docs/roadmap.md`) and a trap (`docs/context/lessons.md`).
- **Bank parity:** matching the internal environment's versions and behaviour. **One-way code
  flow:** code goes into the bank; nothing comes out.
- **Worknotes:** committed notes in `worknotes/`, written for the builder and the Lead DS: the sync
  page (what to review, shared open questions), the verbose log, and per-topic chat handovers.
