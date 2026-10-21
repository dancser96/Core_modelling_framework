# Holistic review of the design and plan
_Written 2026-10-20 for the SDS and the LDS, before the planning session. Everything that is not
a question is here. The open questions: `holistic_review_questions.md` (round 3, 2026-10-21). The
dates: `timeline_proposal.md`. Based on every doc in `docs/`, the decision log to D-081 and the
worknotes, plus three fresh-context audits (ML correctness, forward compatibility, cross-doc
consistency). Claims checked against the pinned library source are marked **verified**. The SDS's
answers of 2026-10-20 and 10-21 are recorded as D-082–D-102; a question number cited here that is
no longer in the questions file has been answered. Corrected after the SDS's notes: §4 (reports;
speed and automation), §5 (config validation; correlated rows; leavers; D-062 vs OD-22; the
exposure count and in-memory pickle, 10-21), §7 (sync rules), §9 (status)._

## 1. Verdict

**Proceed with changes.** The design is coherent, unusually well recorded, and right on the things
that matter most: the invariants, the time model, the ledger, oracle-backed synthetic data,
versioned artifacts, a thin-but-real lifecycle. Its weaknesses are not in the modelling ideas.
They are:

1. **The December target means two different things** (a pre-release of the skeleton, or release
   1.0 with two integrations), and nobody has said which. As release 1.0 it is not reachable.
2. **Review bandwidth, not build speed, is the binding constraint.** Claude builds faster than two
   people can read, and the rule is that every line is read.
3. **Five design holes will be expensive if M2 writes its first shared row before they close:**
   the shared-table rule, identities and hashes, the model bundle under FLAML, the calibration
   chain, and the refit.
4. **Research questions gate the config spine** (OD-10, OD-24, OD-25), and the spine gates
   everything.
5. **External dependencies have no names and no dates** (feature store, data observability,
   platform / MLOps, the inference output facts).

The most valuable outcome of the planning session: decide what December means (Q217), and settle
Q239–Q243 and Q253–Q256 so M2 starts on 2026-10-26 without reopening them.

## 2. What is strong (keep; don't re-litigate)

- **The invariants and the time model.** `v ≥ tk + w` is sufficient (adjacent target windows, not
  overlapping); D-048 is consistent across architecture, dataset, EDA, Feature Checks and the
  glossary; the client-grouped split with a seeded hash; sampling after the split; contract checks
  before sampling; the engine never sees the raw feature universe.
- **"EDA understands, Checks gate, Training selects"** (D-028), flags never drop, and a person signs
  off every feature (D-076). This is the governance content, and it is simple.
- **Synthetic data with an oracle.** It is the only way to test leakage screens and calibration
  against the truth outside the bank, and "a model that beats the oracle is leaking" is a test no
  real dataset can offer.
- **The decision log, OD rows with owners, and one owner doc per fact.** This review was possible
  because of them.
- **The right simplifications already made:** thin-but-real lifecycle (D-059), the environment
  adapter as the one seam, the per-task spec dict (D-050), regression shapes designed early
  (D-060), no pickle verified per family (D-078), FLAML limited to one family (D-080).

## 3. Top risks, ranked

| # | Risk | Why it matters | What to do |
|---|---|---|---|
| 1 | **December as release 1.0 is not reachable.** 43 working days remain; the crunch took 2–3 weeks for one stage's worth; Phase 2 has ten stages, a spine, a ledger, reporting, a CLI, eight notebooks and two integrations with systems nobody on the team has used | A silent slip, or depth cut without saying so, is the one outcome that damages credibility with the CDS | Scenario A in `timeline_proposal.md`: pre-release in December, release 1.0 mid-February; say it now (Q217, Q221) |
| 2 | **Review is the bottleneck.** The LDS has eleven items on the review list after one week; M1 produced 32 modules in five days | The quality gate erodes into rubber-stamping, or the build throttles to reading speed without anyone deciding that | Cap the list at three; the LDS reviews designs and ML-critical code in full and samples the rest; review guides per major step (Q224–Q226) |
| 3 | **No rule for an old framework version reading rows a newer one wrote.** `CLAUDE.md` §2 covers migration old → new only; OD-04 defers the window to M5 | Many pinned versions share the registry, scores, monitoring and card tables from the first row written inside the bank; a renamed column in v1.4 breaks a v1.1 reader | Decide the shared-table rule now: `schema_version` + `framework_version` per row, additive-only within a major, readers ignore unknown columns (Q243) |
| 4 | **Identities are undefined and everything hangs off them.** The config hash includes `conf/local`; the data-definition hash includes the validation and inference months; `run_id` collides across entities; nothing says whether hashes are computed before or after migration | The due-diligence gate (D-031) would force fresh EDA and checks every month, or get bypassed; a migration would orphan old artifacts; laptop and bank hash differently | Settle Q242 before M2.1: hash the migrated, canonical use-case definition only; store a `hash_version` beside every hash |
| 5 | **The model bundle under FLAML is not what the docs assume.** **Verified** in FLAML 2.7.0: `DataTransformer` drops constant columns and fills `__NAN__`, and the estimator wrapper recodes categoricals to codes before the booster; `AutoML.predict` re-applies both. **Verified:** FLAML exposes no out-of-fold predictions | Saving only the native booster silently loses a preprocessing layer (a column constant in the sample is dropped, the booster expects one fewer feature). The calibration step fitted "out of fold inside train" needs our own grouped CV refitting `best_config`, which multiplies training cost | The framework encodes everything to numeric codes itself so FLAML's transformer is the identity; inference calls the booster directly; the bundle records the booster's feature names (Q253). Calibration only for `probability` decisions, with its cost stated (Q255) |
| 6 | **The refit (D-052) registers a model no metric ever touched.** Its calibration is recomputed, its encoder levels may be refrozen, and its card borrows the parent's numbers | The registered and scoring model differs from the evaluated one in ways the card does not show; OD-27 (retraining in production) multiplies this | Mark every parent metric as "parent, not this model"; a label-free agreement check against the parent on the latest month (rank correlation, score PSI) with a gate; levels inherited from the parent; evaluate the all-clients refit on `v` where `v` is outside its window |
| 7 | **Three research questions sit in front of the config spine** (OD-10, OD-24, OD-25) | The spine blocks everything (the original spine reference said so); research without a deadline becomes the deadline | Decide at the planning session with reversible defaults (Q239–Q241); the authoring format is a front end, the audit log is an append-only table, the levels are two |
| 8 | **External dependencies without names or dates.** Feature store (OD-26), data observability (OD-13), platform / MLOps (OD-06, OD-23, CR steps, Sonar), the inference output facts (OD-18) | The integrations are the only hard external deliverables and will be designed blind, or late; OD-18 shapes the most-shared table of all | Book three sessions by 11-06; OD-18 by 10-30 (Q232–Q235) |
| 9 | **Verification debt that can reshape Training.** Unverified: FLAML grouped CV honouring sample weights; non-pickle round trips for `lgbm` / `xgboost` / `catboost`; Arrow `toPandas` with dates; plotly HTML in the bank's JupyterLab; report size | Any one of these moves M2.3 by days; the format one decides the estimator list | A spike week in the background, 10-21 – 10-30, results in `docs/context/environment.md`. The SDS runs them; Claude reminds |
| 10 | **The speed claim reads as time to production.** "3 days / 3 weeks" is DS effort to a candidate; production adds the change-request calendar, which is weeks and not ours | The first use case will miss the "3 days" and the claim will be remembered | Restated as "a registered candidate in days to a few weeks"; production "through the CR calendar" (D-085) |

## 4. Scope and goals

- **The from → to table in `project.md` has thirteen target rows, and all read as Phase 2.** Several
  are mature-state (model inventory, cross-model monitoring view, pivot tools, generated model
  documentation). The depth table (OD-01, "not drafted yet") is the missing link between that
  table and the milestones; a draft is in `timeline_proposal.md` (Q218).
- **The CDS meeting added scope without adding time.** Two integrations, each behind a learn work
  stream, on the same December target. Treat them as one work stream with its own milestone (M4)
  and make them thin by construction: upstream, the seam is source resolution (a source of kind
  `feature_store`); downstream, a monitoring-table export in the observability framework's
  contract. Nothing else in the framework should know they exist.
- **Regression is kept by D-080 but barely designed.** No stated regression counterpart for: the
  leakage-screen statistic, the automated-selection floor, the contract band (needs non-degenerate
  variance and a tail band), the stratum minimum support (rows, not positives), calibration (none,
  or a mean and quantile check), the decision types, the sampling option (no minority class to
  keep whole), and what recency weighting does to a continuous target. Filling the per-task spec
  entry is half a day and is what D-060 asked for in M1; building it end to end is not an M3 item
  (Q219).
- **Shapes for the tasks after regression** (D-081: multiclass, time-to-event) are not yet
  additive. A scalar `score` column cannot carry per-class or per-horizon scores, and "headline
  metrics" as columns in the registry will not survive a new task. Reserve a nullable
  `score_component` and a `task` column in the scores from v1, and store metrics as long rows
  keyed by metric name everywhere (registry, card, monitoring). Cheap now, breaking later.
- **"Every stage writes an HTML report"** (`CLAUDE.md`, `architecture.md`) was Claude's drift, not
  the SDS's intent. The intent: EDA and Feature Checks together are a **product within the
  product**, a data-analysis report in its own right rather than notebook output plus artifacts;
  the other stages write artifacts, and the remaining reports are model performance, the model
  card and monitoring. Corrected in `CLAUDE.md` and `architecture.md` (2026-10-20).
- **The speed goal and the automation levels** are consistent once stated carefully: every level
  runs the same checks; the difference is human time, and a higher-value use case brings more
  people and inputs that shape its choices. The claim itself is now "a registered candidate in
  days to a few weeks", with production following through the change-request calendar (D-085).

## 5. Stage by stage

### Config spine
- **YAML, decided now, is the right call** (Q239). A Python config runs code at load, the same class
  of risk as the pickle the CDS banned; hashing, diffs and migrations assume plain data; and a
  config that is code is the bespoke path the framework exists to replace. Programmatic users
  (sweeps, the LLM branch) get the Pydantic model as the API. Record the reasoning as an
  information item for the CDS rather than a research stream.
- **Automation levels: beware the matrix.** Three levels × seventeen decision points is a design
  nobody will maintain. Two levels in Phase 2 (`autonomous`, `assisted`), `manual` as "assisted with
  every rule decision presented for confirmation" later, and keep the `profile` field name until
  the levels exist (Q240). The decision-point inventory in `config.md` is the right artifact; it
  should stay a table, not become a framework.
- **The decision audit log: keep it a table** (Q241). The ledger for features, one per-run decision
  table appended by stage functions, human feature decisions still in the config (D-043). The flag
  case that motivated OD-10 is solved more simply: the sign-off is its own record linked to the
  run, so resolving a flag never edits the config.
- **Identities** (Q242): the config hash over the use-case definition only, after profile
  resolution, without `conf/local` and housekeeping; the data-definition hash over entity, sources,
  eligibility, target spec, observation window and candidates, so the validation and inference
  months are run arguments and the due-diligence gate does not demand monthly reruns; `run_id`
  per instance. Hashes computed on the migrated canonical form, with a `hash_version`. Also: the
  gate checks the definition, not the data; training should recompute the per-month row and
  positive counts and fail loud when they differ from the EDA artifact's (`CLAUDE.md` §4.10).
- **Extension functions** (OD-05): record the import path and a source hash in the frozen config,
  because monitoring builds labels from the frozen target spec months later and reinference needs
  the same builder (Q244).
- **Validate `v + w ≤` the last loaded month**, not only `v ≥ tk + w`; otherwise partial maturity
  nulls every validation label and the failure is quiet. Now a requirement in `config.md`
  (2026-10-20).

### Dataset and sampling
- Option 1 in M2, the oracle comparison in M3 (Q245). Mandate one negative-keep fraction across the
  window's months: with a fixed negatives-per-positive ratio per month the prior-shift offset
  varies by month, and the inference month has no month to borrow one from.
- **Correlated rows: what to do, and why this does not contradict the earlier answer.** The
  earlier answer (`dataset.md`, "Is automatic downsampling safe when a client's rows are
  correlated?") was about the *fitted model*: correlated positive rows and the just-before-
  conversion negatives bias nothing, row-level negative sampling stays unbiased, regularisation
  and client-grouped CV stop memorisation. That stands, so the modelling changes nothing: keep
  every unit-month row. The new point is about *counting evidence*: one conversion makes up to
  `w` correlated positive rows, so wherever a count of positives decides something (the minimum
  support per stratum of D-038, the standard error behind the AUC floor, the per-month stability
  range, the "enough positives" rules in EDA), the row count overstates the evidence by up to
  `√w`. The rule: those counts are counts of positive **events** (distinct converting clients in
  the slice), and every bootstrap and CV fold resamples clients. Decided as D-082.
- **Leavers are null targets only when they leave inside the target window** (D-066 says exactly
  that; the review's earlier wording was loose). What remains is to name the denominators: the
  "true population" for the drift reference and the contract band is the eligible rows regardless
  of label; the prior-shift true rate comes from the unsampled train split (not train plus test,
  which lets test labels into a fitted quantity); the null-label share is reported per month and
  per scoring batch; and probabilities are stated as conditional on staying through the target
  window (Q271).
- **Recency weighting changes the effective weighted rate**, so the prior shift as defined would
  undo a deliberate recency emphasis. Decide which is intended before both exist.
- **Pooled test metrics over the window's months** count one conversion up to `w` times and mix
  seasons; a pooled top-N slice is not the monthly campaign decision. Per-month test metrics first,
  pooled second; that also makes test comparable with the single validation month.
- **A `dev` preset** of about 20k clients for daily work on the 8 GB Mac (Q247); the canonical
  100k for demos and the M3 comparison.

### Target Factory
- Sound. Two gaps for upstream targets: lineage is optional, so T12 recurs; and the shifted-column
  trap is not a near-perfect separator, so the stated leakage screen will not flag it, although
  `test_harness.md` says "a time-alignment check catches it". Make lineage mandatory for upstream
  targets (an empty list with a note is allowed) and add the alignment check to Feature Checks:
  each feature's AUC for the forward target against its AUC for the same event in the backward
  window; legitimate features predict both, shifted or leaky columns only the forward one.

### EDA, Feature Checks, ledger
- **Ledger keying** (OD-11) must be solved in M2 because EDA and checks write before any run
  exists: one part per data definition, one per run, joined on feature name (Q248).
- **The sign-off will be rubber-stamped at hundreds of candidates.** Sign off the model's final
  list (tens), flags grouped, sorted by importance; the candidate list is reviewed where flagged
  (Q249).
- **The sign-off after training sees validation results.** In hands-off runs the signer reads the
  card (test and validation metrics, importances) before deciding; a `keep` "because validation
  improves" is selection on `v`, and D-053 labels only formal sweeps as optimistic. Show train-only
  evidence in the sign-off view (flags, univariate AUC on train, train importance; D-092) and tag
  a post-rejection retrain as such. A count of validation exposures in the registry record was
  declined by the SDS (2026-10-21): local runs, and their counts, can be deleted anyway.
- **Per-month stability statistics need a minimum number of positive events per month** (Q250);
  at low prevalence a 6-month window has months with a handful of events.

### Training
- **The calibration chain is unspecified** and FLAML gives no out-of-fold predictions
  (**verified**). State it once: raw score → general calibration fitted on K client-grouped folds
  that refit `best_config` (never FLAML's folds, never in-sample) → prior shift in logit space.
  Cost: K extra fits, so on by default only for `probability` decisions (Q255). Verify against the
  oracle's reliability curve in M3.
- **FLAML's hidden preprocessing** (risk 5, **verified**): encode categoricals to integer codes in
  the framework before FLAML sees the frame; never call `AutoML.predict` at inference; record the
  booster's feature names in the bundle and fail loud if they differ from the resolved list
  (Q253).
- **`model_hash` must cover the whole bundle** (encoder, booster, calibration with the prior-shift
  offset, metadata), not "the model file": a refit with recomputed calibration would otherwise
  keep its parent's hash while scoring differently (Q256). The prior-shift offset is not listed as
  a bundle part anywhere; it must be. Platt and isotonic parameters are plain numbers in the
  bundle with our own predict code, never scikit-learn objects.
- **Estimator list:** `lgbm` only in M2; `xgboost` and `catboost` after their round trips; the
  scikit-learn forests never (Q252). FLAML's `fit` accepts `sample_weight`, `groups` and
  `split_type` (**verified** in the signature); whether the grouped CV metric honours the weights
  is the spike.
- **Sampling option 3's weights must reach every fitted or selecting statistic** (univariate floor,
  importance pruning, calibration, FLAML's CV metric), or the negatives' distorted feature
  distribution biases each of them. Mark "weight-aware" per statistic in the per-task spec before
  option 3 is offered.
- **Reproducibility is traceability, not re-execution:** a wall-clock budget gives a different
  `best_config` on rerun. Either a trial budget plus seeds for reproducible runs, or say plainly
  that seconds-budget runs reproduce the frozen config, not the model.
- **D-062 and OD-22 disagreed; settled by the SDS as D-083.** Any choice among variants or trials
  (the window, a sweep, the Phase 3 trade-off point) weighs train and test metrics only; the
  validation month never chooses and stays the one honest number. Consequences applied: `CLAUDE.md`
  §4.4 reworded (tuning choices may weigh test; validation never), OD-22 closed, D-062 amended,
  D-053's "optimistic" label and the selection month dropped (nothing picks on validation any
  more). Cost, stated in the reports: once test chooses, the test-vs-validation gap mixes
  overfitting with selection.
- **The two-paths wording survives in six docs** (`training.md` Purpose and requirements 2 and 9,
  `evaluation.md` 7, `feature_ledger.md`, `config.md`, the glossary, `CLAUDE.md` §1's `Protocol`
  example). With one path in Phase 2 the `Protocol` is an abstraction before a second use (§1
  rule 6); keep the small model interface as plain functions until the predefined path arrives.

### Evaluation
- With GBDT families only, the compatibility table is nearly trivial (SHAP's tree explainer works
  for all three). Don't over-build the slot mechanism in M2; a dict of view → function with a
  "not available" entry is enough until a second family exists.
- Per-month test metrics as the primary view (above). The paired bootstrap and comparison reports
  are M3 items; "validation on test clients only" is well defined and cheap.
- "Beats the oracle = leak" needs a tolerance (about two standard errors on events); the oracle's
  AUC is an expectation.

### Lifecycle
- **One stable pointer per model key** (`production.json` at an adapter-resolved path: model key,
  version, `run_id`, `model_hash`, bundle path, framework version, schema version) is the one
  record every pinned version must read; make every registry implementation write it, and a later
  move to MLflow or to the platform team's registry (OD-08, OD-23) becomes a mapping. Events
  append-only with ids; derived tables rebuilt by replay; metrics long-form (Q260).
- **Recipe vs model identity** (OD-27): add `recipe_hash` now (frozen config, features,
  hyperparameters, encoder levels, calibration spec); a fitted model is one fit of a recipe with
  `model_hash` and `parent_run_id`; manifests carry both, the drift reference is keyed by
  `model_hash`. Then both OD-27 options share one shape and no work is doubled (Q261).
- **Sign-off wording mixes CR and PR:** `lifecycle.md` says "CR + code review, recorded as the
  approved PR". The PR approves `promote`; the CR runs `deploy`. Say so, and add "promotion
  sign-off" to the glossary next to "feature sign-off".
- OD-23 remains the structural risk: if the platform team builds the registry, the thin records
  are throwaway, which D-059 accepts; the pointer format above is what must survive.

### Inference
- The scores table is the most shared table of all, and OD-18 (its columns and layout) is a fact
  the LDS holds. Nothing in M2.4 should write a score before that answer or an explicit
  placeholder decision. The first consumer format arrived on 2026-10-21 (Q291–Q295).
- Reserve `task` and `score_component` (above); `infer_date` vs the glossary's "inference month"
  is a naming mismatch to settle with OD-18.
- Broadcasting a model to executors serialises it in memory (cloudpickle). Settled by the SDS
  (D-101): only saved and moved artifacts must avoid pickle; runtime formats don't matter.

### Monitoring
- "Deep" health and drift by December is not realistic; thin tables with flags are, with drift
  deep in M4 (Q262). What is computed, stored and shown still needs the design the doc itself
  asks for; the learn session with the data observability team should come before that design,
  not after.
- The survivor-denominator problem (dataset, above) appears here as the label join: say which
  population realised performance is measured on.
- Labels for scored months depend on the extension function identity (config spine, above).

### Reporting and notebooks
- **Report size and rendering inside the bank are unverified and testable today** with any plotly
  file (the SDS tests it inside later). At 4–5 MB per report, per stage, per run, per entity, storage and opening time add
  up; the alternative (one shared JS file per folder) breaks "self-contained". Verify before
  choosing (Q263).
- **The guided notebooks are the product users see**, and "well-written instructions" is the
  underestimated part. Thin in M2 (run and display), guidance matured in M3 with the LDS as the
  proxy user (D-097).
- The three-level template (D-072) applies to one of sixteen component docs. Don't retrofit the
  other fifteen now; apply it when each is rewritten as its component is built.

### Environment adapter and run modes
- Sound. The `getOrCreate` trap (re-running a setup cell with different arguments) must fail loud;
  the notebooks will hit it on day one.
- **A rule for what becomes public:** every function a shipped notebook calls, the stage
  functions, `run`, the CLI commands and the config schema, with a small test that greps notebook
  calls against the Public API table. Otherwise the notebooks make private functions public by
  use.
- The CLI lists differ between `architecture.md` §7, §11 and `run_modes.md`, and the notebook
  plan has `06_register_promote` with no deploy or sign-off step. One list, one owner.

### Synthetic data and tests
- Done well. Two limitations that matter downstream: dirty defects don't reach the rollups
  (a real mart rolls up its own bad values), and the oracle under-predicts two rare paths. Both
  are recorded; neither blocks M2.
- Real local Spark in every test costs a session start per run; keep the e2e on the `unit` preset
  under two minutes and the canonical run nightly, or the suite stops being run.
- "Every function tested" plus CI / Sonar readiness before migration is a real M4 bill (a fifth
  to a third of build time) and the Sonar quality gate is unknown (Q235; the test depth per
  milestone is D-097).

## 6. Forward compatibility, summarised

- **An artifact inventory is missing.** Of about fifteen artifacts, three name a version field
  (config `schema_version`, bundle `bundle_schema_version`, ledger `ledger_schema_version`); the
  card, manifest, scores, drift reference and registry records say "versioned" without a field;
  monitoring tables, the decision log, labels for scored months, EDA and Feature Checks artifacts,
  target lineage, training metadata and evaluation results are not declared versioned at all,
  although later framework versions read several of them through the gate. One table in
  `architecture.md`: artifact → owner doc → version field → writer → readers → compatibility rule.
- **The shared-table rule** (risk 3) and **hashes on the migrated canonical form** (risk 4).
- **"Loads and scores identically under a newer version"** has no mechanism: a new base image
  moves lightgbm or xgboost and nothing detects a changed prediction. Store a probe fingerprint in
  the bundle (predictions on a deterministic synthetic probe frame derived from the encoder levels
  and the drift reference's ranges, so no client data); `load` recomputes it and fails loud; and
  add a test that loads a bundle written by the previous package version.
- **The deprecation window:** `CLAUDE.md` §2's "one minor version" and OD-04's "images live a year"
  resolve with one rule: migrations are cumulative for the life of a major version; shared-table
  and bundle formats change only additively within a major; a major bump keeps old readers for one
  image lifetime; the one-minor rule applies to code deprecations only. **Cut 1.0 at the first
  bank release** and freeze shared formats from the first row written inside; 0.x promises nothing
  under semver.
- Minor disagreements: D-051 "CatBoost binary" vs `training.md` and `environment.md` "CatBoost
  JSON"; `infer_date` vs "inference month".

## 7. Process and working rules

- **Designing in prose has reached its limit.** About 5,700 lines of docs stand on two code
  modules, and the remaining questions are the kind only building answers. Freeze the baseline,
  let M2 deviate with a one-line "built differs from design" note per component, and hold no more
  doc-only review rounds before M4 (Q228).
- **Velocity vs review.** The rule that every line is read is the right rule; the consequence is
  that the SDS's reading time is the project's throughput. Review guides per major step (D-067)
  and the LDS's list capped at five are the levers; the subagent reviews per minor step are
  cheap and should keep running, but they are not the gate (D-084).
- **The sync page's review list** now distinguishes "needs decision" from "for information", with
  at most five "needs decision" items (D-084, `worknotes/README.md`).
- **The 8 GB Mac** limits M3 (FLAML on hundreds of thousands of rows beside a Spark session, the
  three-way sampling comparison). Prepare the WSL2 PC in a background slot now (Q229).
- **The CDS check-ins** need one artifact: the timeline with the depth table. Everything he
  delegated (D-073) is covered by the OD rows; what he must hear is the date and what it includes.

## 8. Doc hygiene found by the sweep (one pass, about two hours)

- Two-paths wording: `training.md` (Purpose; requirements 2, 9; open questions on Optuna and the
  pick rule), `evaluation.md` requirement 7, `feature_ledger.md` open questions, `config.md`'s
  `path (automl | predefined)` and the "trade-off chart" inventory row, the glossary's model
  interface and trade-off chart entries, `CLAUDE.md` §1 rule 2's `Protocol` example,
  `context/environment.md`'s Optuna note (no D-080 reference).
- Stale references: D-050's status still cites OD-15 as under review; `UPDATES.md` "M1 still needs
  OD-15"; D-024 cites "OD-02–OD-05" (OD-03 is gone).
- Definition-of-done wording: OD-01 says "stub of every major component", everywhere else says
  "thin"; the M2 row says Monitoring thin, the backlog says Monitoring stub (M2).
- Profiles described by depth or time rather than automation: glossary "Profile" ("hands-off to
  deep"), `CLAUDE.md` line 5, `project.md` Speed row.
- Where human decisions live: `feature_ledger.md` Purpose ("the config holds the decisions"), the
  glossary's "Human decision" ("always with a reason"), `conf/base/README.md` ("every decision"),
  `run_modes.md` requirement 4; the hedged wording of `config.md` is the right one.
- Lifecycle sign-off: CR vs PR mixed (above); no glossary entry for the promotion sign-off.
- CLI and notebooks: three different command lists; `06_register_promote` has no deploy and no
  sign-off step.
- Package layout in `architecture.md` §11 is by stage and never mentions the role subfolders that
  `CLAUDE.md` §1 rule 5 and D-070 require; `config.md`'s inventory lists "Dataset" as a stage.
- Stage lists: `project.md` → Registry row omits promote; the "every stage writes a report" wording.
- Phase 3 lists disagree: `project.md` puts retraining in production under Later while the
  roadmap has it as M4 research; multiclass and time-to-event (D-081) are missing from the
  roadmap's Phase 3 list; the corporate theme is Phase 3 in the roadmap and a Phase 2 requirement
  in `reporting.md`.
- Stale paths: `lessons.md` T1 cites the legacy `src/_compat.py`; D-065 cites
  `synthetic/products.py`; `CLAUDE.md`'s repo map puts `spec/`, `mechanisms/` directly under
  `synthetic/` (they sit under `synthetic/src/synthetic/`).
- `components/README.md`'s status values omit `legacy-only` and `blocked`, which eight docs use.
- Glossary gaps: housekeeping block, recipe, decision point, pathway, contract checks,
  due-diligence gate, human gate / stage gate, label-free, selection month, learning-curve check,
  oracle, config mode / notebook mode, deepening round, recency weighting, promotion gate.
- Term clashes: `test_harness.md` uses "profile" for the four client tiers and "segment" for
  three groups, against the glossary's meanings of both; "PSB" is never spelled out (and may be
  internal jargon; check).
- `skills_and_agents.md` still says "local sync notes" (D-044 committed them).

## 9. Do before M2.1 starts (2026-10-26)

Status after the SDS's answers of 2026-10-20 and 10-21 (recorded as D-082–D-102; the rest in
`holistic_review_questions.md`, round 3):

1. Decide what December means and agree the depth table (Q217, Q218): **open**, with the LDS.
   The exact plan goes to the CDS once agreed (D-097).
2. Agree the M3 candidate order (Q223): **open**.
3. Config spine defaults: YAML, two levels, identities, the shared-table rule, extension code in
   use-case repos: **decided** (D-086–D-090). The audit log's Phase 2 scope is restated (Q241).
4. Training shape: own encoding before FLAML, booster-direct inference, the calibration chain,
   `model_hash` over parts, all three families in M2: **decided** (D-093, D-094). The grouped-CV
   fallback is restated (Q254); the refit checks are a new question (Q276).
5. The spikes, the bank-side plotly test included: the SDS runs them, Claude reminds at session
   start; previously
   **open**, for the LDS.
6. Book the three external sessions (Q232): **open**, for the LDS. The retail platform's output
   format arrived on 10-21; its design questions are Q291–Q295.
7. Fill regression's per-task spec entry (D-060): M1 close; reserve the task-agnostic score
   columns (Q267).
8. The review list is capped at five with a "needs decision" tag (D-084); the doc-hygiene pass
   (§8) is a question (Q288).

Every suggestion in §4–§6 that had no question now has one (Q266–Q289).
