# Stage 3 (M2.3 Modelling): the answers record
_Each settled question as it was asked, the EDS's answer verbatim, and the outcome. No question is open
(2026-11-13); the research note and the settled design in one table are in `questions.md`. The folder is deleted when the stage closes; what lasts moves to the owner docs._

## Index of outcomes (68 questions, by number)

One line per question: the round that settled it, its outcome as recorded below, and in
italics what a later answer or assumption changed. The full question, the options and the
EDS's words are in the round's section. The plan assumptions A1–A51 are listed at the end of
each round; A16 is replaced by A31.

- **Q590** (round 1) The depth: section 0 as the target. Deeper than (A): between thin and deep, as M2.2 was built (the first research note above). What section 0 left for later is re-sorted in round 2's section 0; a group of testers follows the stage.
- **Q591** (round 1) What is cut first if section 0 does not fit. No cut order. When the scope does not fit, the dates move; the roadmap's dates are set with the plan.
- **Q592** (round 1) Regression in M2.3. (A), and by Q590 and Q591 regression is built end to end in M2.3. How far its entries are parametrised is Q639, open in round 2. *Later: the regression entries are settled in Q639, Q653 and Q656.*
- **Q593** (round 1) Two stages, one run folder. (A): two stages, Training never reads the test frame. *Later: the out-of-fold metric is reported as optimistic; the test split is the first honest number (A40).*
- **Q594** (round 1) `run_id`, the run folder and reruns. The run folder's layout, a new run per Training call and `list_runs` stand as proposed. The form of `run_id` and the identification scheme are re-posed as Q647. *Later: the identification is Q647; `run.json` is the identity record (A31) and a number is never reused (A32).*
- **Q595** (round 2) The `autonomous` level: who runs the upstream stages. (A): the automation level acts in `run` only.
- **Q596** (round 1) Scoring test and validation at the bank's size. (B): test and validation are scored inside Spark with `mapInPandas`, through the one pandas function `score_frame`. The only reason for (A) was that Python model libraries on the bank's executors are unverified; that check joins spike 5's trip, and the chunked driver path is built only if it fails (round 2, reply to Q596). *Later: the model is rebuilt once per Spark partition from the bundle's bytes (A28); the check inside the bank is A27.*
- **Q597** (round 1) Row-level scores as an artifact. (A): test and validation scores are stored per row.
- **Q598** (round 1) One fold assignment for everything. (A): a `fold` column from the client's hash, `training.folds: 5`, passed to FLAML as `groups`. Round 2 proposes one refinement for binary tasks (Q649: the folds balanced on converting clients). *Later: the folds are balanced on converting clients (Q649), reach FLAML as a splitter object, not as `groups` (A24), and the column is `cv_fold` (A48).*
- **Q599** (round 2) Cross-validation or a holdout inside the search. (A): always cross-validate on the K folds.
- **Q600** (round 2) Too few events to train. The EDS's proposal with Claude's two changes: EDA warns below 100 converting clients or 200 events; Training fails loud only when a fold has no positive event; no advice to use fewer folds; no warning about duplication, which cannot happen (`auto_augment` off and inactive with client folds). *Later: EDA gets no second warning: its existing events warning gains the converting-client threshold (A46).*
- **Q601** (round 2) Infinite values. (C): numeric features are clipped to ±1e30; a null stays null.
- **Q602** (round 1) FLAML searches; who fits the final model. (B): FLAML only searches; the framework's `fit` trains every model.
- **Q603** (round 2) Nulls: what `skip_transform` does, and whether to impute. (A): no imputation in M2.3; `skip_transform` is always on and is not a config field. Checked for regression on 2026-11-12 (6,000 rows, 5% nulls, the three families): with it on, `automl.predict` equals the library's estimator on the raw frame exactly; with it off they differ by 5.7 to 16.1 in the target's units.
- **Q604** (round 2) The trial budget: who gets the next trial, and how the next parameters are chosen. (B) with (i): one search per family with its own trial budget, FLAML's local search (CFO). BlendSearch is on the Phase 3 wishlist in `docs/roadmap.md` (added 2026-11-12). The starting point of each search is decided in round 3, after the measurement the EDS's note on quick early trials asked for. *Later: the start is Q652; the default list holds four families and the level budgets are 60 and 200 (Q651, A45).*
- **Q605** (round 2) The search ranges: bounded, sourced, overridable. (B): the bounded, sourced ranges, overridable per leaf, checked on `dev` before they become defaults. The "Start" column is not settled here (round 3). *Later: the start is Q652: FLAML's own start values clipped into the ranges, passed with every leaf (T39).*
- **Q606** (round 2) The search metric per decision type. (B): `log_loss` for `probability` and `threshold`, `roc_auc` for `ranking` and `top_n`. *Later: for regression the metric is Q656.*
- **Q607** (round 1) CatBoost's tree count. (B): CatBoost's tree count is searched, `use_best_model` off.
- **Q608** (round 1) What must repeat. As proposed.
- **Q609** (round 2) Categoricals: two kinds, ordered as numbers and unordered declared to the library. (B): ordered categoricals as numbers in a declared order, unordered ones declared to the library, the `native | codes` switch. *Later: the order is declared under `features.order` (Q657); an unseen level becomes `__other__` for an unordered categorical and null for an ordered one (A35).*
- **Q610** (round 1) Rare, unseen and missing levels. (A): a level is kept at `training.categoricals.min_level_client_count` distinct train clients or more (default 50). How a missing and an unseen level are coded follows Q609's outcome (declared categoricals need a code for missing), open in round 2. *Later: an unseen level follows A35; the codes follow Q609.*
- **Q611** (round 2) Automated selection: what irrelevant features cost, and importance pruning. (C): the cluster rule, the floor and importance pruning, in that order. *Later: the pruning model is LightGBM at the start configuration (A43).*
- **Q612** (round 1) The floor's rule. (B): the floor scaled to the standard error, `selection.floor_z: 2`.
- **Q613** (round 1) The chain, and where the calibrator is fitted. (A) in M2.3; (B) is decided in M3 by the oracle check.
- **Q614** (round 1) Platt on the margin, and the second method. (A), with beta calibration built in M2.3 as the second method. Platt is fitted on the margin; isotonic is not offered. What else the research suggested is listed in round 2 (reply to Q614).
- **Q615** (round 2) When the calibrator applies. (A): the calibrator follows the decision; the out-of-fold log loss of `none`, `platt` and `beta` is stored for every binary run.
- **Q616** (round 1) A base rate that moves over time. (A): the observed-to-expected ratio per period, no correction.
- **Q617** (round 1) The functions per family. (A): `FAMILIES`, a dataclass of six functions per family.
- **Q618** (round 1) The bundle's files, its manifest and a self-check. (A): the native model file, `bundle.json`, `manifest.json`, Training writes the bundle and Evaluation loads it, with the self-check at save. The manifest's hashes become one `model_hash` (Q647, round 2); the answer on later model types is in round 2 (reply to Q618). *Later: one `model_hash` over the model file and `bundle.json` (Q647, A34); the owner doc is `model_bundle.md` (A50).*
- **Q619** (round 2) A `model_hash` that repeats. (A): CatBoost's five run-specific metadata entries are deleted before saving.
- **Q620** (round 1) The recipe, and what a retrain keeps. (A): the encoder's levels are frozen in the recipe.
- **Q621** (round 1) The two parked lifecycle questions. Yes to both.
- **Q622** (round 1) The per-run ledger's columns. (A). Columns that later outcomes add (pruning, imputation) join the same table. *Later: no imputation columns (Q603); a constraint column joins (Q650); Evaluation's per-feature numbers are a table of their own (A36).*
- **Q623** (round 1) The sign-off view. (A): Training writes the sign-off view's table from train-only evidence. *Later: train-only and readable right after training; no evaluated run is needed (A39).*
- **Q624** (round 1) The sign-off entry: what it names, and how long it lasts. (B): the sign-off covers a feature list (its signature), not one run.
- **Q625** (round 2) Selection drops: the ledger only, or audit-log entries too. (A): the per-run ledger is the one record of automated drops.
- **Q626** (round 1) Evaluation's entry and the validation period. (A): Evaluation writes a `run` entry with the scored validation period.
- **Q627** (round 1) The metrics (binary). (A): the metrics as listed, without Gini and KS.
- **Q628** (round 2) What "pooled" means, and does "per period first" (D-098) make sense. (B): one curve per split on all its rows and a pooled headline; per period in a table and for the slices. D-098's wording changes with the spec.
- **Q629** (round 1) Slices are cut inside each period. As proposed: a `top_n` is a share of the period's eligible population.
- **Q630** (round 2) Intervals in M2.3. (B): a client bootstrap, 200 replicates, for every metric. *Later: the weights come from a hash of the client id, the replicate number and a fixed salt (A47).*
- **Q631** (round 1) Baselines, and what "beats the baselines" means. (A). `historic_predicted_rate` is taken in both meanings: a number is one rate in use, compared with the observed rate and the model's mean prediction (it ranks nothing); a column is a historic prediction per client, judged like `previous_model`. *Later: `single_feature` joins the baselines (A25); the comparison is shown, with no gates (Q632).*
- **Q632** (round 3) Gates: not built. (B): no gates table and no "passed / failed" anywhere in M2.3; the report's summary and the card show the model against each declared baseline at the decision's metric, with intervals. `decision.gate_metric` and `lifecycle.promotion_gate` are removed from the schema, the template and the example and test configs in the build's first major step, by the procedure of `CLAUDE.md` §2 (a `schema_version` bump, a migration that drops them, a test that loads an old config). The `lifecycle` section holds nothing else, so it leaves the schema with them until M2.4 gives it content (a plan default; the EDS can veto it with the spec). The Phase 3 wishlist asks once whether a metric gate should come back (`docs/roadmap.md`, added 2026-11-13).
- **Q633** (round 1) Stratified metrics. (A): strata columns on Evaluation's frames, with the list's composition.
- **Q634** (round 1) The views: core and extended (settles OD-12). (A), settling OD-12. "Class" is the target's value (converted against not). View 8's feature set and how far "extensive" goes (the extended views, the SHAP-style plots, intervals, a run comparison) are in round 2 (Q635, Q648). *Later: replaced by Q648's seventeen views; the summary's "gates" is the baselines comparison (Q632).*
- **Q635** (round 2) The familiar SHAP plots, in the notebook and the report. (A): the four SHAP-style charts in plotly, one implementation for the notebook and the report.
- **Q636** (round 1) A "too good to be true" warning. (B): no "too good to be true" warnings; `evaluation.warnings` is not added.
- **Q637** (round 1) The drift reference. (A): Evaluation writes the drift reference from EDA's counts. *Later: the reference uses EDA's stored edges and levels (A38), from the run's own copy (Q654).*
- **Q638** (round 1) The model card. (A): `model_card.json` and a tables-only `model_card.html`.
- **Q639** (round 2) The regression entries: objective and metric from the config, and the mean correction. (B): the objective from the config, the search metric following it, `calibration.method: mean | none`. How the mean correction is made robust (or whether it is applied by default at all) is decided in round 3, after the research asked for. *Later: the metric comes from the decision, not from the objective (Q656); the level correction is Q653.*
- **Q640** (round 1) The config changes. The table is not decided now. It is rebuilt from the settled answers and comes with the spec, for your approval there.
- **Q641** (round 1) Public API. (B): `load_bundle` and `score_frame` are public from M2.3, beside `run_training`, `run_evaluation`, `list_runs` and the sign-off. *Later: `show_run` and `compare_runs` join the public API (Q647, Q648).*
- **Q642** (round 1) The notebooks. (A): two notebooks, `04_training` and `05_evaluation`.
- **Q643** (round 1) The acceptance tests and their presets. (A). The plan lists every `dev` test with its run time and who runs it, and keeps the count small.
- **Q644** (round 1) The held honest features in the examples. (B): notebook 03 ends with the keeps recorded, so the examples train with the three honest features. Clarified in round 2: a revert reopens the flags, and an open flag holds; the sign-off never retrains (the sentence described the notebook's guide).
- **Q645** (round 1) The major steps. Three major steps as proposed, at the depth of Q590. A helper notebook for reading the code (as `00_eda_fc_helper` is for Stage 2) starts with major step 1 and grows with each step. *Later: the helper notebook is `00_modelling_helper` (A26).*
- **Q646** (round 1) Correcting the docs for the imputation finding now. Done 2026-11-12: `docs/context/environment.md`, D-094 (a), `training.md` req. 2 corrected and T38 added to `lessons.md`.
- **Q647** (round 2) One simple identification across the framework (new). (A): `run_id` is the run number (`r007`), one `model_hash` per bundle, `run.json`, `list_runs` and `show_run`. The run's start time and duration are in `run.json` and are shown by `list_runs`, `show_run` and each report's header. *Later: `run.json` is never rewritten (A31); a number is never reused (A32); Evaluation finds its run by the data-definition hash and a digest of Training's settings (A33).*
- **Q648** (round 2) How far "extensive" goes. (A): the seventeen views, `compare_runs`, the card as HTML, the regression views. *Later: view 1 shows the baselines comparison, not gates (Q632); view 13 shows the timings of A45; `compare_runs` takes its differences on the test split (Q655).*
- **Q649** (round 2) Folds that hold up at few events (new). (A): balanced client folds for binary tasks, `training.fold_repeats`, the warning's text.
- **Q650** (round 3) Monotone constraints (new, from A19). (A) as proposed, and LightGBM keeps its default method, `basic`. The EDS's question was measured on 2026-11-13: `intermediate` holds the constraint and costs no time, and it showed no gain. In 18 direct comparisons on two constructed datasets (8 and 16 constrained features of 20, 8 to 255 leaves, three seeds) its holdout log loss minus `basic`'s ranged from −0.0006 to +0.0009 with a mean of 0.0000. Through FLAML (20 trials, two seeds) both methods passed as a constant, held the constraint and refitted bit for bit, and `intermediate` ended slightly behind (fold loss 0.2388 against 0.2378, and 0.2287 against 0.2270). `basic` is one of the family's fixed parameters, not a config field. A person can try `intermediate` with a `{value: intermediate}` leaf under LightGBM in `training.search_space`; `advanced` is refused, because it broke the constraint in round 3's check; `intermediate` together with LightGBM's `colsample_bynode` is refused too, because LightGBM would fall back to `basic` with only a warning. The grid check at save guards every method. The numbers: `questions.md` → What the research found → Added on 2026-11-13.
- **Q651** (round 3) The default family list, with depth-wise XGBoost (from A5). (B): the default `estimator_list` is `lgbm`, `xgboost`, `xgb_limitdepth`, `catboost` (FLAML's names). The `autonomous` default of `training.max_iter` rises from 50 to 60, 15 trials per family; `assisted` stays 200, 50 per family. `LEVEL_DEFAULTS`, the template and D-037's list change with the spec and the build. The `dev` run that checks the ranges no longer decides the list; it reports the four families' fold loss and seconds.
- **Q652** (round 3) Where each search starts: FLAML's own start, inside the bounded ranges. (A): FLAML's own start inside the bounded ranges; a `start` can be written per leaf in `training.search_space`. Added on 2026-11-13 (trap T39 in `docs/context/lessons.md`): FLAML drops its own start values for every parameter the search space overrides, and with all of them overridden and no start given it runs no search at all. So Training passes the start with every ranged leaf (the default start, or the config's `start`, clipped into the range) and fails loud after each family's search unless trial 1 equals the starts and the trials differ. The level budgets are settled by Q651 and A45.
- **Q653** (round 3) The level correction for regression: plain, with its interval, not winsorised. (A): the plain factor on the train split's out-of-fold predictions (`mean` for `tweedie` and `poisson`, `none` for the other objectives), stored with its client-bootstrap interval and the number of rows that hold half of the target's total; a warning when the interval is wider than ±5%; never winsorised. A `cap` on the target rule (Target Factory) goes to the roadmap's backlog with the spec.
- **Q654** (round 3) What a run keeps from Stage 2. (A): a run is complete in itself. Training copies into the run folder the final features' Stage 2 ledger rows, EDA's bin edges and shares per period and the lift table; Evaluation, the card and the sign-off view read only the run folder and the data.
- **Q655** (round 3) `compare_runs` and the validation period. (A): `compare_runs` computes the differences, their intervals and the word "better" on the test split; validation's two numbers are shown side by side under "reported, never chosen on", with no difference.
- **Q656** (round 3) The regression metric: declared with the decision, not derived from the objective. (A): the metric comes from the decision (`decision.metric`, or the task's default, `rmse`; allowed for regression: `rmse`, `mae`, `r2`, `tweedie_deviance`, `poisson_deviance`). It is the search metric and the headline metric and cannot be changed through the audit log; `training.objective` is a training setting and can. This replaces Q639's "the search metric following it".
- **Q657** (round 3) Where an ordered categorical's order is declared. (A): `features.order: {feature: [levels in order]}`, beside `features.kinds`; read by Training's encoder now, and counted in Training's settings, not EDA's, until EDA reads it. This replaces Q609's `training.categoricals.ordered`.

## Round 1 (asked 2026-11-11, answered 2026-11-12)

**The EDS's general notes, verbatim.** The replies are in `questions.md`, round 2.

> Notes on research:
> - First note: just like for M2.2, I’d like this to be at least in-between the thin and deep state; the idea is that because nobody cares how things deploy, after this stage is done I’ll try to ask for a few people to test. As you see, we have two “extra days” by starting the work already, so by about the end of next week I’m hoping to still get it done
> - This research note is important, make sure you are not deleting it later
> - FLAML median impute: What happens with skip_transform = True and would it be possible to change imputation to strata median? What other useful imputation methodologies should be included?
> - Does roundrobin learning make sense? I would want to enforce some trials for every model categories, and if anything I would like to optimize (with Bayesian maybe) how new parameters are being chosen, but are there other ways to do this than roundrobin?
> - What’s the takeaway from the “The package's seams” section?
> - Boosted trees lose little accuracy to irrelevant features, okay, but how much calculation time do we lose with them?
>
> Notes on proposal:
> - Encoder: Include native categoricals and ordered kinds now
> - Model families: What does “the predefined path” mean?
> - Search: See my notes with regards to transformation and leaning options. What does trade-off chart mean?
> - Calibration: Include beta calibration and anything the research suggested to do
> - Evaluation: This and the reporting over it has to be extensive now as that’s the most “user-facing”
> - Run modes: what are “sweeps”?

The EDS on the questions: "Questions; unanswered goes with default".

### Q590. The depth: section 0 as the target
**Context.** The roadmap says thin for Training and Evaluation with the bundle and the card
"shape final", and puts "the calibration chain right" in M3 and automated selection in M4.
`training.md` lists both as Phase 2 requirements with live defaults, and the M2.3 exit criterion
is "a calibrated model beats the baselines". Stage 2 was planned thin and built between thin and
deep.

**Options.**
- (A) Section 0: every shape other stages read is final (bundle, per-run ledger, scores, card),
  the calibration chain is complete in its simple form, two cheap selection rules, the core views.
- (B) Thin as the roadmap: no selection, the offset only, a metrics table and three charts.
- (C) Deeper: importance pruning, bootstrap intervals and the comparison report now.

*Default:* (A).

**Answer (EDS, 2026-11-12).** As noted above, I want deeper solutions now

**Outcome.** Deeper than (A): between thin and deep, as M2.2 was built (the first research note above). What section 0 left for later is re-sorted in round 2's section 0; a group of testers follows the stage.

### Q591. What is cut first if section 0 does not fit
**Context.** The roadmap's response to a slip is "the exit points stay, calibration depth moves".

**The proposal, first cut first:** (1) regression end to end (its spec entries stay); (2) the
extended views; (3) the cluster rule; (4) the floor. Never cut: the three families with their
round trips, the client folds, the calibration chain, the bundle and card shapes, the oracle
tests.

*Default:* as proposed.

**Answer (EDS, 2026-11-12).** Nothing is cut, I’d rather move the timelines by even more than the two days we already has as a head start rather than cutting now

**Outcome.** No cut order. When the scope does not fit, the dates move; the roadmap's dates are set with the plan.

### Q592. Regression in M2.3
**Context.** D-050 (every task-specific choice sits in one per-task spec; Training's and
Evaluation's regression entries are designed with M2.3). The roadmap wants "shapes" at the
pre-release and end to end in M4. Stage 2 built its regression entries for real on a test-only
variant. The bundle, the scores and the card freeze at 1.0, so they should have met two tasks.

**Options.**
- (A) Thin and real on the test-only variant: the search with `split_type="group"`, squared
  error, no calibration, the metrics of Q639 and one view. No example config.
- (B) Shapes only: the entries raise "not implemented" and both stages refuse a regression config.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A), and by Q590 and Q591 regression is built end to end in M2.3. How far its entries are parametrised is Q639, open in round 2.

### Q593. Two stages, one run folder
**Context.** D-036 (every stage runs alone; Training writes artifacts only, Evaluation writes the
model results report). Today `build_frames(…, "training")` returns train and test.

**The proposal.**
- `run_training` fits on the train frame and writes a run. **It never reads the test frame:**
  nothing in Training uses it, and the train–test gap becomes Evaluation's number. Training's own
  honest figure is the out-of-fold metric on train clients.
- `run_evaluation` takes a run, loads its bundle from disk and scores test and validation. It can
  be rerun alone. By default it takes the latest run whose resolved-input hash is the config's
  current one, and refuses when there is none.
- `run --stages training evaluation` does both.

**Options.** (A) as proposed; (B) one stage, `modelling`, that always does both.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): two stages, Training never reads the test frame.

### Q594. `run_id`, the run folder and reruns
**Context.** D-088 (`run_id` = the hash of the run's resolved input + entity + timestamp);
D-136 (`<use_case>/06_models/<run_id>/`). Neither a format nor a file list exists.

**The proposal.**
- `run_id` = the 12-character hash of (resolved-input hash, entity), a dash, the UTC start time to
  the second: `3fa9c1d2e4b7-20261116T101502`. An existing folder is refused, never reused.
- The folder:
  - `training/`: `training.json`, `tables/` (trials, folds, selection, out-of-fold), `log.json`,
    FLAML's log, `resolved_config.yml`;
  - `bundle/`: the model file, `bundle.json`, `manifest.json` (Q618);
  - `ledger_run.parquet` with its sidecar (Q622);
  - `evaluation/`: `evaluation.json`, `tables/` (metrics, curves, strata, importance, effects,
    scores), `report.html`, `model_card.json`, `model_card.html`, the drift reference.
- Every Training call is a new run; local runs accumulate and are deleted by hand.
  `list_runs(env, cfg, entity)` shows them with what each has (trained, evaluated, signed off),
  as `list_data_definitions` does for Stage 2. An Evaluation rerun rewrites `evaluation/` whole.

**Options.** (A) as proposed; (B) one folder per resolved-input hash, rewritten by a rerun as
EDA's is (no timestamp, so no history of attempts).

*Default:* (A).

**Answer (EDS, 2026-11-12).** As proposed, but I’d really prefer something shorter as run_id, it’s a bit long and unnecessarily complex this way and given you hash other things as well, can you propose a simple way of identification that runs across the whole framework? I remember that in crunch as well retrieving what happened through the manifest was a bit daunting

**Outcome.** The run folder's layout, a new run per Training call and `list_runs` stand as proposed. The form of `run_id` and the identification scheme are re-posed as Q647.

### Q596. Scoring test and validation at the bank's size
**Context.** Test and validation are never sampled (§4.7). At retail scale test is 30% of about
2 million clients over 6–12 periods, 3.6–7 million rows, and validation 2 million; neither fits
the collect budget with its features. Inference has the same problem (`inference.md` req. 7).
Python on the executors is unverified inside the bank.

**Options.**
- (A) Evaluation collects in chunks no larger than the collect budget (a period, and inside a
  period a hash bucket of the client), scores each with one function, `score_frame(bundle,
  frame)`, and keeps only the keys, the target, the split, the strata columns and the scores. The
  features survive only for the seeded sample the explanation views need. Inference wraps the
  same function in M2.4.
- (B) Score inside Spark with `mapInPandas` now.
- (C) Collect both frames whole (fine on the laptop only).

*Default:* (A). The check of Python on the executors joins spike 5's trip into the bank.

**Answer (EDS, 2026-11-12).** Unless you have a good reason why you’d want to go with (A), why aren’t we going with (B) and score in Spark?

**Outcome.** (B): test and validation are scored inside Spark with `mapInPandas`, through the one pandas function `score_frame`. The only reason for (A) was that Python model libraries on the bank's executors are unverified; that check joins spike 5's trip, and the chunked driver path is built only if it fails (round 2, reply to Q596).

### Q597. Row-level scores as an artifact
**Context.** Run comparison on identical validation rows (M4), a DS exploring in a notebook copy,
re-rendering the report and the drift reference's score distribution all need the scores again.
Size at retail scale: 6–9 million rows of about six columns, 100–250 MB per run, under the same
data root as the model input.

**Options.**
- (A) Store test and validation scores: `unit_id`, `period`, `split`, `target`, `score_raw`,
  `score`, the strata columns.
- (B) Store validation's rows and test as binned counts only.
- (C) Store binned counts only (curves re-render, rows cannot be paired across runs).

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): test and validation scores are stored per row.

### Q598. One fold assignment for everything
**Context.** D-106 (no fold mixes a client's rows; calibration and selection reuse the same
folds). The modelling frames carry no folds, and no pandas-side hash exists. FLAML's `GroupKFold`
makes its own assignment from the groups.

**Options.**
- (A) `build_frames(…, "training")` adds a `fold` column in Spark: the client's salted hash draw
  (salt `'fold'`, the training seed) cut into K = 5. It depends on the client id alone, so it
  survives a change of sampling or row order. The search gets the fold number as its `groups`:
  with K groups and K splits, `GroupKFold` returns exactly these folds. The fold models of the
  calibration and the selection statistics use the same column.
- (B) FLAML keeps its own `GroupKFold` on the client ids; our hash folds serve the out-of-fold
  predictions only.

*Default:* (A), `training.folds: 5`. To check in the first build step: FLAML with the fold
number as `groups`, together with `skip_transform`.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): a `fold` column from the client's hash, `training.folds: 5`, passed to FLAML as `groups`. Round 2 proposes one refinement for binary tasks (Q649: the folds balanced on converting clients).

### Q602. FLAML searches; who fits the final model
**Context.** D-037 and D-100 (one model interface per family: `fit`, `predict`, `describe`);
D-052 (production refits the recipe on its own data). The fold models of the calibration need a
fit outside FLAML in any case.

**Options.**
- (A) The final model is `automl.model`, FLAML's own refit.
- (B) FLAML only searches. The recipe stores the winning estimator's own parameters
  (`get_params()`), and the framework's `fit` trains the final model, the fold models and, later,
  the production retrain, with the library's scikit-learn class. Production then needs no FLAML
  and no search. A test asserts that the framework's fit equals `automl.model` bit for bit.
  Verified for lgbm and xgboost; CatBoost needs Q607 (B).

*Default:* (B).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): FLAML only searches; the framework's `fit` trains every model.

### Q607. CatBoost's tree count
**Context.** FLAML's wrapper stops CatBoost early on the last 1,000 rows by position and never
records the count. Today's client ordering makes that tail whole clients, but it is about 170
clients and 30 positive rows at a 3% rate, and the final model then trains without them.

**Options.**
- (A) Keep FLAML's behaviour and read the count from the final model.
- (B) Search `n_estimators` as a range with `use_best_model` off (verified: CatBoost then trains
  exactly the set count). The three families then follow one rule: the tree count is tuned on the
  client folds, with no eval split inside any fit.

*Default:* (B).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): CatBoost's tree count is searched, `use_best_model` off.

### Q608. What must repeat
**Context.** D-094 (d) (a trial budget plus seeds gives the same model on a rerun; a time budget
is labelled "reproducible to the recipe, not the model"). Verified on one machine; unverified
across machines.

**The proposal.**
- `training.seed` drives the search's seed, the fold salt, the client order and, through
  constants in the search space, the libraries' own seeds (FLAML's are fixed constants today).
- A test trains twice on `unit` and asserts the same `model_hash` (Q619).
- With `time_budget_s` set, the search is not repeatable, the run says so in its log, report and
  card, and the final fit is still the framework's own, untruncated.
- The claim in the docs: "the same machine and library versions give the same model". The bank's
  machines are checked at the pre-release run.

*Default:* as proposed.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** As proposed.

### Q610. Rare, unseen and missing levels
**Context.** `training.md` req. 6: levels frozen from train, rare levels to `__other__`, missing
to `__missing__`, unseen to `__other__` and counted. `categoricals.min_level_count` is 50, with
no unit. Elsewhere a missing level is called `null`.

**The proposal.**
- A level is kept when at least `min_level_count` distinct train clients have it (events
  thinking, D-082), else it joins `__other__`.
- A missing value stays null, so the library's own missing branch handles it; reports call it
  `null`. `__missing__` goes.
- An unseen level maps to `__other__` when train had one, else to null. Either way it is counted
  per column, in the per-run ledger for test and validation and later in the manifest.

**Options.** (A) as proposed; (B) the count in rows; (C) missing as its own code.

*Default:* (A).

**Answer (EDS, 2026-11-12).** Option (A), but then call it min_level_client_count

**Outcome.** (A): a level is kept at `training.categoricals.min_level_client_count` distinct train clients or more (default 50). How a missing and an unseen level are coded follows Q609's outcome (declared categoricals need a code for missing), open in round 2.

### Q612. The floor's rule
**Context.** Today: drop below a train-split concordance of 0.515. That margin is under one null
standard error at 300 events, where 37% of pure-noise features pass (60% at 100 events), and
three standard errors at 3,000. A
univariate floor also drops a feature that only works in interaction [GE03]. No tool surveyed
uses one. The synthetic data carries null-control columns that would otherwise reach the sign-off.

**Options.**
- (A) The fixed 0.515.
- (B) Scaled to the standard error: drop when the concordance is below 0.5 + z · SE, with z = 2
  and the SE on effective train clients, as EDA's rules read it. About 0.509 at the card's 3,870
  events and 0.533 at 300. `selection.floor_z` replaces `univariate_floor`.
- (C) Off by default, a speed lever a person switches on.

*Default:* (B).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): the floor scaled to the standard error, `selection.floor_z: 2`.

### Q613. The chain, and where the calibrator is fitted
**Context.** D-049 and D-094 (b) (raw score → a calibration step fitted on client-grouped
out-of-fold predictions inside train → the prior-shift offset in logit space; parameters as plain
numbers). §4.7 (never fitted on test or validation).

**The proposal.** `score = sigmoid(a · m + b + offset)`, with `m` the final model's margin.
- (a, b) are fitted on the out-of-fold margins of the train rows as trained: K fold models of the
  recipe, each scoring the fold it did not see.
- `offset = logit(true rate) − logit(sampled rate)` under `negative_downsampling`; zero with no
  sampling and under `client_sample`, which does not change the class balance.
- `score_raw = sigmoid(m)` is kept beside `score`.

**Options.**
- (A) As proposed: fit on the sampled out-of-fold rows, then add the offset. Exact when the
  calibrator's form is right [KZ01].
- (B) Score every unsampled train row out of fold and fit at the true rate, with no offset. It
  does not depend on the calibrator's form [Phelps24], but needs the rows that sampling dropped.

*Default:* (A) in M2.3. (B) is decided in M3 by the planned oracle check under downsampling.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A) in M2.3; (B) is decided in M3 by the oracle check.

### Q614. Platt on the margin, and the second method
**Context.** D-049 says "Platt in M2, isotonic in M3" and does not say on what Platt is fitted.

**The proposal.**
- Platt is a two-parameter logistic regression of the label on the margin, unpenalised. Its
  family contains "leave as is" (a = 1, b = 0).
- The second method, in M3, is beta calibration (three parameters, smooth, strictly increasing)
  [Kull17][CalArena26], not isotonic.
- Isotonic is not offered in Phase 2: it ties scores, so a top-N cut becomes arbitrary and AUC
  changes; it outputs exactly 0 or 1, which breaks the offset; it needs many positives.

With only strictly increasing maps, "rank metrics are unaffected by calibration" in
`evaluation.md` holds.

**Options.** (A) as proposed; (B) isotonic in M3 as D-049 says.

*Default:* (A).

**Answer (EDS, 2026-11-12).** See comments above, but leaning to go with default  [the comment above, on the proposal's Calibration row: Include beta calibration and anything the research suggested to do]

**Outcome.** (A), with beta calibration built in M2.3 as the second method. Platt is fitted on the margin; isotonic is not offered. What else the research suggested is listed in round 2 (reply to Q614).

### Q616. A base rate that moves over time
**Context.** D-098 (the true rate is the unsampled train split's, pooled over the window). The
scoring period's rate can differ; an intercept update needs labels that arrive `w` periods late.
On the synthetic data the term deposit's rate falls 10% inside the window.

**Options.**
- (A) Report it: the observed-to-expected ratio per period on test and on validation. No
  correction.
- (B) Shift the offset to the window's last period's rate.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the observed-to-expected ratio per period, no correction.

### Q617. The functions per family
**Context.** D-100 (a) (plain functions per family, `fit`, `predict`, `describe`, behind a dict).
Saving, loading and explaining need three more.

**The proposal.** `FAMILIES = {"lgbm": Family(...), "xgboost": ..., "catboost": ...}`, a small
dataclass of six functions:
- `fit(X, y, params, task) -> booster`;
- `predict(booster, X) -> margin` (float64; log-odds for binary, the prediction for regression);
- `describe(booster) -> dict` (trees, parameters, feature names, gain and split counts);
- `save(booster, path)` and `load(path) -> booster`;
- `contributions(booster, X) -> array` (the library's own per-feature contributions).

The loader pins what the fact check found: float64 in the booster's column order, the tree count
for XGBoost, CatBoost writing no files.

**Options.** (A) as proposed; (B) keep the triple and hold the other three in separate dicts.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): `FAMILIES`, a dataclass of six functions per family.

### Q618. The bundle's files, its manifest and a self-check
**Context.** D-051 (plain data, never pickle once promoted, library versions recorded); D-094 (c)
(`model_hash` over per-part hashes). `lifecycle.md`'s parked question: the bundle is written at
training and Evaluation scores it, one scoring path.

**The proposal.**
- `model.txt` (lgbm), `model.json` (xgboost) or `model.cbm` (catboost).
- `bundle.json`: `bundle_schema_version`, the task, the family, the ordered features (name, kind,
  levels and codes, missing rule), the tree count, the calibration (method, a, b, offset, the two
  rates), the output columns, the recipe (Q620), the library versions. No timestamp, run or
  person in it.
- `manifest.json`: each file with its SHA-256 and size, `model_hash` (the SHA-256 over those
  digests in name order, the OpenSSF model-signing rule [OMS]), `recipe_hash`, the feature
  signature, the config, data-definition and resolved-input hashes, `run_id`, the time written.
- Training writes the bundle; Evaluation loads it from disk and verifies the hash first.
- **Self-check at save:** Training reloads the bundle and asserts the same scores on a fixed
  1,000-row sample, failing loud on any difference. D-051 leaves a per-model check to Phase 3;
  this is its cheapest form.

**Options.** (A) as proposed; (B) one file per part (encoder, calibration, signature, recipe);
(C) (A) without the self-check.

*Default:* (A).

**Answer (EDS, 2026-11-12).** Generally as default, but looping back to my comments earlier, could we not just use one single hash? Also, how confident are we that as we expand the framework, new model types will also fit into rhe “plain text”-type export?

**Outcome.** (A): the native model file, `bundle.json`, `manifest.json`, Training writes the bundle and Evaluation loads it, with the self-check at save. The manifest's hashes become one `model_hash` (Q647, round 2); the answer on later model types is in round 2 (reply to Q618).

### Q620. The recipe, and what a retrain keeps
**Context.** D-052 (`recipe_hash` covers the resolved config, features, hyperparameters, encoder
levels and calibration spec; a production retrain keeps it and recomputes calibration). The
levels are fitted from train, and the resolved config's housekeeping block holds a timestamp.

**The proposal.** The recipe is plain data: the task, the family, the estimator's parameters with
the tree count and seed, the final feature list in order, the encoder's rule **and its frozen
levels**, the calibration spec (method and folds, never a, b or the offset), the sampling spec,
the data-definition hash. `recipe_hash` is over that, not over the housekeeping block. A retrain
refits the model and recomputes the calibration numbers; it keeps the levels, so a level new in
production data maps to `__other__` and a code never changes meaning under a live model.

**Options.** (A) levels frozen in the recipe; (B) levels refitted at a retrain, and out of the
hash.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the encoder's levels are frozen in the recipe.

### Q621. The two parked lifecycle questions
**Context.** `lifecycle.md` still lists two questions from the pickle summary (Q297 and Q299
there; the format one, Q298, was taken today: plain data, so CatBoost is `.cbm`).

- **The promote gate.** The non-pickle bundle is written at training and Evaluation scores it;
  `promote` accepts only listed file types; a pin bump reruns stored bundles against stored
  predictions. M2.3 builds the first part (Q618); the other two are M2.4's.
- **Security's view** of `.cbm` (binary) and LightGBM's text model: the EDS raises it through the
  CDS before the pre-release.

*Default:* yes to both.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** Yes to both.

### Q622. The per-run ledger's columns
**Context.** `feature_ledger.md` leaves them to M2.3: selection with its rule and statistic, use
in the model, importance and rank, effect direction. One row per feature Training received,
joined to the Stage 2 ledger on `feature`.

**The proposal.** `ledger_run.parquet` with a sidecar (schema version, `run_id`, the
data-definition hash, the Stage 2 run tokens it pairs with).

| Written by | Columns |
|---|---|
| Training, selection | `selected`, `dropped_by`, `selection_value`, `selection_threshold`, `represents` (the cluster members dropped in its favour), `protected` (a person's keep) |
| Training, the model | `in_model`, `splits`, `gain_share`, `contribution_share` and `contribution_rank` (out of fold, on train clients), `direction_model`, `direction_agrees` (against EDA's direction) |
| Training, the encoder | `levels_kept`, `other_share`, `null_share`, `inf_share` |
| Evaluation | `contribution_share_test`, `unseen_share_test`, `unseen_share_validation`, `null_share_validation` |

**Options.** (A) as proposed; (B) the minimum: selection, `in_model`, one importance, direction.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A). Columns that later outcomes add (pruning, imputation) join the same table.

### Q623. The sign-off view
**Context.** D-031 (a person signs off the model's final feature list; the view shows Feature
Checks' flags and train-only model evidence, features sorted by importance, held features
listed). §4.4 lets test inform a choice, never validation.

**The proposal.** Training writes the view's table; nothing in it uses test or validation.
- Per feature of the final list, by out-of-fold contribution rank: the share and the running
  total, the model's direction beside EDA's and whether they agree, the cluster members it
  represents, its source, Feature Checks' notes and any flag a person kept with its reason.
- Then the held features with their open flags, and the excluded ones with their reasons.
- It is shown in notebook 04 and as a section of the model results report, where each of the top
  features also gets its effect chart.

**Options.** (A) as proposed; (B) its own HTML page written by Training; (C) the notebook only.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): Training writes the sign-off view's table from train-only evidence.

### Q624. The sign-off entry: what it names, and how long it lasts
**Context.** In the code `sign_off` can carry neither features nor a run, while `config.md`'s
worked example signs "the 61 features of `r3`". D-031: forcing an entry nobody reads is
rubber-stamping.

**The proposal.** `decide --sign-off --run <run_id> --reason …`, and `record_decision(sign_off=…)`
as a sixth operation. The entry holds the run, the feature signature and the final list.

**Options.**
- (A) Per run: every new run needs its own sign-off.
- (B) Per feature list: the sign-off covers every later run of the same data definition whose
  final list has the same signature. A higher budget or another family with the same features
  needs no new entry; a changed list does. The view of such a run says which run was signed.

*Default:* (B): a person defends features, not hyperparameters. `register` (M2.4) checks the
signature.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): the sign-off covers a feature list (its signature), not one run.

### Q626. Evaluation's entry and the validation period
**Context.** D-088 (the validation period may be moved by an audit-log entry, refused when a
Feature Checks run compared it). The refusal reads every `run` entry, so one that names the
validation period blocks every later `resolve_config`. Evaluation reads that period's labels by
design. `lifecycle.md` expects `register` to pack "any validation-period entry its Evaluation was
scored with".

**Options.**
- (A) Evaluation writes a `run` entry with its stage, the `run_id` and the validation period it
  scored, in a field of its own. The refusal reads Feature Checks' entries only. The trail then
  shows which runs were scored on which period.
- (B) Evaluation writes no entry; `evaluation.json` holds the period.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): Evaluation writes a `run` entry with the scored validation period.

### Q627. The metrics (binary)
**Context.** D-050; `evaluation.md` req. 1 (AUC, PR-AUC, base rate; precision, recall and lift at
the slices).

**The proposal.** Each per period first (D-098), on test and on validation:

| Group | Metrics |
|---|---|
| Support | rows, positive events, base rate |
| Ranking | AUC; average precision, always with the base rate beside it |
| At each slice | rows, events captured, precision, capture, lift |
| Probability | log loss and Brier as skill against the base-rate forecast; the observed-to-expected ratio; the calibration slope and intercept |

Not shown: Gini and KS, which restate the ranking on other scales; accuracy, F1 and a confusion
matrix at 0.5, which mean nothing at a rare rate.

**Options.** (A) as proposed; (B) Gini and KS added to the ranking group, if the bank's readers
expect them.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the metrics as listed, without Gini and KS.

### Q629. Slices are cut inside each period
**Context.** Inference scores one period at a time, so a list is the top of one period's eligible
population. Test holds 30% of each period's clients, so `top_n: 10000` means another depth there
than on validation.

**The proposal.** A `top_n` is read as a share of the period's whole eligible population and cut
at that share inside the split. Example: 10,000 of 61,884 eligible validation rows is the top
16.2%; on a test period of about 18,400 rows the same depth is about 2,970 rows. A `top_n` above the
population is "not available". Ties at the cut are broken by a seeded hash of the client.

*Default:* as proposed.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** As proposed: a `top_n` is a share of the period's eligible population.

### Q631. Baselines, and what "beats the baselines" means
**Context.** D-009 (the population base rate for business reporting; the previous model and the
historic predicted rate internally). The base rate ranks nothing. No config field says where a
previous model or a historic rate comes from.

**The proposal.**
- `population_base_rate`: always; it anchors lift and the skill scores.
- `single_feature` (new, on by default): the best single feature by train-split concordance, its
  values used as the score in the direction train gives, judged at the same slices. It is chosen
  on train, so it is a fair reference: does the model beat its best column alone?
- `previous_model`: a score column of a source (`{previous_model: <column>}`), judged like a
  model. A previous run of the framework joins in M4 with the comparison.
- `historic_predicted_rate`: refused as not built until it is defined.

**Options.** (A) as proposed; (B) a small logistic regression on the key features as well (it
needs imputation and scaling code); (C) the base rate only.

*Default:* (A). What did `historic_predicted_rate` mean: one rate in use, or a score column?

**Answer (EDS, 2026-11-12).** Default, and historic_predicted_rate could mean both

**Outcome.** (A). `historic_predicted_rate` is taken in both meanings: a number is one rate in use, compared with the observed rate and the model's mean prediction (it ranks nothing); a column is a historic prediction per client, judged like `previous_model`.

### Q633. Stratified metrics
**Context.** D-038 (mandatory; levels capped; a minimum of positive events per stratum). The
modelling frames carry no strata columns unless a stratum is also a model feature.

**The proposal.**
- `build_frames(…, "evaluation")` adds the strata variables and the modelling tags. They never
  reach the model.
- Per level: rows, events, base rate, the AUC inside the level, the observed-to-expected ratio,
  and at the decision's slice the level's share of the list beside its share of the population,
  with the capture inside it.
- A level below `strata.min_events` is greyed, never hidden. No tests across levels; a note says
  that many levels are read together.

**Options.** (A) as proposed; (B) without the list's composition.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): strata columns on Evaluation's frames, with the list's composition.

### Q634. The views: core and extended (settles OD-12)
**Context.** OD-12 (which views are core in the Evaluation report). Twelve tools were compared
for what they show by default; the count is in the last column.

| # | View | Part | Tools showing it |
|---|---|---|---|
| 1 | Choices, how to read, headline, warnings, gates | Summary | — |
| 2 | Metrics by split and period: a table and one line chart | Core | 12 (the table) |
| 3 | Capture curve with the slice table at fixed depths (1, 2, 5, 10, 20, 30, 50%) | Core | 4–5 |
| 4 | Reliability: predicted against observed in quantile groups of the score, axes fitted to the data, the level and slope beside it; flagged under 200 events | Core | 5 |
| 5 | Score distribution by class, each class to its own scale | Core | 1 |
| 6 | Strata table | Core | 3 |
| 7 | Feature importance: contribution shares, train out of fold beside test | Core | 7 |
| 8 | Feature effects for the top ten: mean contribution by feature group, EDA's lift beside it; a level table for categoricals | Core | 3 |
| 9 | The sign-off view | Core | — |
| 10 | What the search did: trials, best loss and time per family | Core | 4 |
| 11 | Threshold table (core when the decision is `threshold`) | Extended | 7 |
| 12 | Permutation importance per cluster, with a rank check against the contributions | Extended | 7 |
| 13 | PDP and ICE | Extended | 3 |
| 14 | ROC and precision–recall curves | Extended | 8 |
| 15 | Validation on test clients only | Extended | — |

**Options.** (A) views 1–10 core in M2.3, 11–15 as they fit; (B) 1–7 and 9 in M2.3, 8 and 10 in
M3.

*Default:* (A).

**Answer (EDS, 2026-11-12).** What does “class” mean in #5? In #8 it should be key features, or what “top ten” means here? Otherwise I’m good with default  [and, on the proposal's Evaluation row: This and the reporting over it has to be extensive now as that’s the most “user-facing”]

**Outcome.** (A), settling OD-12. "Class" is the target's value (converted against not). View 8's feature set and how far "extensive" goes (the extended views, the SHAP-style plots, intervals, a run comparison) are in round 2 (Q635, Q648).

### Q636. A "too good to be true" warning
**Context.** D-100 (e) (beating the oracle by about two standard errors means a leak). Real data
has no oracle. Feature Checks' `too_strong` screens single features, not a model.

**Options.**
- (A) Two rule-based warnings in the report, thresholds in the config: test or validation AUC
  above 0.95 (the crunch's cut), and one feature holding more than half of the contributions.
- (B) None: Feature Checks is the screen.

*Default:* (A).

**Answer (EDS, 2026-11-12).** Option (B), besides feature checks, if a DS can’t deduct these basics from a report, they should be fired

**Outcome.** (B): no "too good to be true" warnings; `evaluation.warnings` is not added.

### Q637. The drift reference
**Context.** D-054 (Training saves the features' distributions over the window and a score
distribution, computed in Spark on the true eligible population). EDA's counts table already
holds every candidate's counts per period and bin on every eligible client, with the edges.
Scores of train clients are in sample, so they spread more than scores on unseen clients will.

**Options.**
- (A) Evaluation writes it, with no extra Spark pass: the final features' edges and shares from
  EDA's counts (pooled over the window and per period), the categoricals in the encoder's
  levels, and the score's distribution on the test split per period (20 quantile groups). The
  shape is the PSI function's input, keyed by `model_hash`.
- (B) Training scores the whole eligible window and bins the features in a Spark pass of its own.

*Default:* (A). D-054's wording changes: the reference is saved with the run, by Evaluation.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): Evaluation writes the drift reference from EDA's counts.

### Q638. The model card
**Context.** `reporting.md` req. 4 (structured facts only, a versioned schema); the roadmap wants
its shape final at the pre-release.

**The proposal.** `model_card.json`, written by Evaluation from the run's artifacts, never typed
by hand, with these sections:
- **Details:** model key, `run_id`, the hashes, framework and library versions, family, dates.
- **Intended use:** the decision, the slices, the population (eligibility), the target and its
  window, "a probability conditional on staying through the window".
- **Data:** logical sources, the window, the validation period, rows and events per period,
  sampling, the split.
- **Features:** the final list (kind, source, share, direction), the held ones with their flags,
  the excluded with reasons, the kept with their findings.
- **Training:** families searched, trials, the recipe, calibration numbers.
- **Performance:** the long metric rows (metric, split, period, stratum, level, value, interval,
  rows, events), the baselines, the gates.
- **Considerations:** the warnings raised, as codes with their values; no free text.
- **Sign-off and lifecycle:** empty until `decide` and `register` fill them (M2.4).

It is rendered as `model_card.html`, tables only, a small page.

**Options.** (A) as proposed; (B) the JSON only in M2.3.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): `model_card.json` and a tables-only `model_card.html`.

### Q640. The config changes
**Context.** D-129 (one section per stage; an unknown key fails loud); D-007 (c) (0.x changes the
shape in place).

| Field | Change |
|---|---|
| `training.folds` | new, 5 |
| `training.search_space` | default = the bounded ranges (Q605); a leaf is `{low, high, log, integer}` or `{value}` |
| `training.selection` | `cluster: true`; `floor_z: 2.0` replaces `univariate_floor`; `importance_floor` stays null until M4 |
| `training.categoricals.min_level_count` | counts distinct train clients |
| `training.calibration.method` | `platt` or `none`; `isotonic` goes; filled from the decision |
| `decision.baselines` | adds `single_feature` (in the default) and `{previous_model: <column>}` |
| `decision.metric`, `gate_metric` | checked against the task |
| `evaluation.views` | the names of the extended views of Q634 |
| `evaluation.warnings` | `auc_max: 0.95`, `contribution_share_max: 0.5` |

Unchanged: `evaluation.slices` stays in EDA's digest, so changing a slice reruns EDA; slices are
declared before results.

*Default:* as listed.

**Answer (EDS, 2026-11-12).** This should be derived once all other questions are settled

**Outcome.** The table is not decided now. It is rebuilt from the settled answers and comes with the spec, for your approval there.

### Q641. Public API
**Context.** D-024 (the stage functions, `run` and the CLI are public; the notebooks call only
these).

**The proposal.** Public: `run_training`, `run_evaluation`, `list_runs`, `record_decision`'s
`sign_off`, the CLI's `run --stages training evaluation [--run-id]` and `decide --sign-off`.
Private until Inference is built: `load_bundle` and `score_frame`.

**Options.** (A) as proposed; (B) `load_bundle` and `score_frame` public now, for a DS scoring a
frame in a notebook copy.

*Default:* (A).

**Answer (EDS, 2026-11-12).** Option (B)

**Outcome.** (B): `load_bundle` and `score_frame` are public from M2.3, beside `run_training`, `run_evaluation`, `list_runs` and the sign-off.

### Q642. The notebooks
**Context.** D-039 (interface-only notebooks; the guide cells are the deliverable).
`notebooks/README.md` plans `04_training` and `05_evaluation`.

**The proposal.**
- `04_training`: the gate and the feature set in force, the run, what the search did, selection,
  calibration, the sign-off view. Its guide ends on how to iterate: `keep`, `exclude` or `set`,
  then train again.
- `05_evaluation`: pick a run (`list_runs`, or the latest), evaluate, read the report section by
  section, then sign off. The crunch's end-of-notebook checklist becomes its last guide cell.

**Options.** (A) two notebooks; (B) one `04_modelling`.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): two notebooks, `04_training` and `05_evaluation`.

### Q643. The acceptance tests and their presets
**Context.** The M2.3 exit: a calibrated model beats the baselines and never the oracle; three
families round-trip; no fold mixes a client. D-100 (d) (the end-to-end test on `unit` stays under
two minutes). On `unit` the two-standard-error band is 0.05–0.10, so the oracle test proves
little there.

**The proposal.**
- **`unit`, in the default suite** (lgbm, a tiny budget): no client in two folds or in both
  splits; `automl.predict` equals the booster on the encoded frame; the bundle round trip; the
  offset is zero without sampling and the log of the keep fraction with it; the calibrator sees
  out-of-fold rows only; a held feature is refused; two runs give one `model_hash`; Evaluation
  refuses a feature list that differs from the bundle's.
- **`dev`, in the default suite** (lgbm, about 30 trials):
  - the model beats the single-feature baseline on validation;
  - its validation AUC is not above the oracle's on the same rows by more than two standard
    errors (Hanley–McNeil in events, about 0.03 for the card on `dev`);
  - with a leak trap kept by a person, the oracle is beaten, so the check is shown to catch a
    leak;
  - the observed-to-expected ratio is within 10%, with and without `negative_downsampling`.
- **`dev`, marked slow:** the three families through the search, with their round trips.
- **Canonical, M3:** the calibration curve against the oracle's probabilities.

**Options.** (A) as proposed; (B) the oracle tests on canonical only, marked slow.

*Default:* (A).

**Answer (EDS, 2026-11-12).** I’m perfectly fine with testing on dev if you don’t overtest, so you build the plan with attention to test efforts (token usage) and timing

**Outcome.** (A). The plan lists every `dev` test with its run time and who runs it, and keeps the count small.

### Q644. The held honest features in the examples
**Context.** `income`, `onboarding_channel` and `subsegment` are held as `client_constant`, and
the stored example log ends in a revert. Notebook 04 and the tests would train without them.

**Options.**
- (A) Notebooks 04 and 05 run as an `autonomous` user would, without them. The sign-off section
  then shows them among the held features, keeps them, retrains and compares: the loop the guide
  teaches. One test covers each state.
- (B) Notebook 03 ends with the keeps recorded, so training starts with them.

*Default:* (A).

**Answer (EDS, 2026-11-12).** If the log ends in a revert, doesn’t that mean they won’t be held? I would go with option (B), but also I don’t understand what you mean by “The sign-off section then shows them among the held features, keeps them, retrains and compares”, the sign-off retrains and compares?

**Outcome.** (B): notebook 03 ends with the keeps recorded, so the examples train with the three honest features. Clarified in round 2: a revert reopens the flags, and an open flag holds; the sign-off never retrains (the sentence described the notebook's guide).

### Q645. The major steps
**Context.** D-072 (a) (major steps end in the EDS's review; minor steps in the review skills).

**The proposal.** Three major steps, each ending in your review with a guide:
1. Foundations: the frames' additions, the encoder, the families with their round trips, the
   bundle, the config fields.
2. Training: the search, selection, the fold models and calibration, the per-run ledger, the run
   artifacts, notebook 04.
3. Evaluation: scoring, the metrics, the views, the report, the card, the drift reference, the
   sign-off, notebook 05.

Routing as D-072 (l): Fable on the main thread and one ML audit per major step; builders on Opus
and Sonnet. The plan with its routing table follows your answers.

*Default:* as proposed.

**Answer (EDS, 2026-11-12).** See comment above on stages; also, if foundation is a separate stage make sure that just like for EDA/FC, there is a helper notebook for walking through abstract code bits

**Outcome.** Three major steps as proposed, at the depth of Q590. A helper notebook for reading the code (as `00_eda_fc_helper` is for Stage 2) starts with major step 1 and grows with each step.

### Q646. Correcting the docs for the imputation finding now
**Context.** `environment.md` says, since today, that FLAML's transformer is the identity on a
numeric frame with nulls; D-094 (a) and `training.md` req. 2 rest on it. The spikes chat's
changes to these files are uncommitted.

**The proposal.** Correct the three places and add the trap to `lessons.md` now, as one small
change: the identity holds for a numpy array or with `skip_transform=True`, never for a DataFrame
with numeric nulls. The other stale lines found wait for the stage's spec.

*Default:* yes, on your word, since another chat may still be writing those files.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** Done 2026-11-12: `docs/context/environment.md`, D-094 (a), `training.md` req. 2 corrected and T38 added to `lessons.md`.

### Assumptions accepted in round 1 (not vetoed)

- **A1.** Numeric features are cast to float64 before the learner (a decimal arrives as `Decimal`
  objects, spike 3). An object column whose kind is not categorical fails loud.
- **A2.** The train frame's seeded client order is made in Spark before the collect; test and
  validation stay sorted by the keys.
- **A6.** FLAML's log is saved in the run folder and read into the trials table (learner,
  configuration, loss, seconds, improving). No train loss per trial.
- **A7.** CatBoost runs with `allow_writing_files=False` (T5).
- **A9.** Selection statistics use the train frame as collected. A rank statistic is unbiased
  under label-dependent sampling.
- **A10.** The floor reads the best-order concordance for a feature EDA marked `non_monotone`.
  That marker saw test clients' labels, the same cost the report already states (D-030).
- **A11.** Fold models are discarded once their out-of-fold margins and contributions are saved.
- **A12.** Rows with a null target are dropped as the frames do, the share is reported, and
  scores read as conditional on staying (D-098).
- **A13.** The count check against EDA's population table compares `eligible_rows`,
  `known_target` and `positive_rows` per period. Kinds come from the ledger; a changed type
  fails loud.
- **A15.** Moving the validation period reruns from EDA, as the code does; the `config.md`
  sentence that says otherwise is corrected.
- **A16.** No separate run record: `training.json` holds the run's identity and its parameters as
  flat dotted strings, the form MLflow takes.
- **A17.** Each stage json gets its own schema version; the one global constant is split.
- **A18.** The report states the cost of EDA and Feature Checks using every client (D-030), that
  PR-AUC is not comparable across use cases, and that validation never chooses.
- **A20.** Columns another use case's target was built from stay ordinary candidates. The card's
  look-ahead trap columns do enter the term deposit's set, at a concordance of 0.51–0.53; the
  floor and Feature Checks are the guards.
- **A21.** `td_acquisition`'s stored artifacts are on older schemas: EDA and Feature Checks are
  rerun before its first training.
- **A22.** The glossary gains: score and raw score, margin, out-of-fold, trial, model results
  report, sign-off view, per-run ledger.

A3, A4, A5, A8, A14 and A19 were asked about; they are explained in `questions.md`, round 2, and stay
open to a veto.

## Round 2 (asked and answered 2026-11-12)

**The EDS's message, verbatim.** The replies are in `questions.md`, round 3.

> Notes:
> - On the skip_transform pushback: Okay, got your point, we’ll go with skip_transform; how will this work with regression though?
> - Fewer folds: Okay, we won’t do that then
> - What does it mean that “FLAML starts every family from a 4-tree model ”?
> - Add Bayesian Optuna variant into Phase 3 wishlist
> - “Every family starts from a deliberately tiny model ” - this also means that early trials run quicker, therefore the gain by resetting starting points is marginal, no?
> - What is Tweedie?
> Questions, unanswered go with default:
> Q647. If runtime timestamp is recorded anywhere and can be displayed, then Option (A)
> Q603. I accept option (A) if as noted above it’s not a problem for regression
> Q604. Accepting default, but add the blendsearch to Phase 3 wishlist
> Q632. In real life, at least on this floor, we never say (unfortunately) that this model exercise did not bring desired results, therefore let’s scrap the whole thing and restart, something will be used. In this context, do we really want to build gates into the framework?
> Q639. Accepting your proposal here, with one question: Should mean correction not be winsorized/capped? If I just think about a dataset with power law values (e.g. market cap of companies), mean correction multiplier will heavily be decided by performance at a few data points and the correction potentially does more harm than good. What does research say about this?
> A5. Wouldn’t it add value to include xgb_limitdepth then? You just said the other three are fairly similar and this is a bit different
> A19. Let’s include monotone constraints now, this would be useful in a bank context
>
> Record answers, explain points raised, then do one (smaller than original) research on whether any other design choice is required before planning

### Q647. One simple identification across the framework (new)
**Your notes.** Q594: "I'd really prefer something shorter as run_id, it's a bit long and
unnecessarily complex this way and given you hash other things as well, can you propose a simple
way of identification that runs across the whole framework? I remember that in crunch as well
retrieving what happened through the manifest was a bit daunting." Q618: "could we not just use
one single hash?"

**Where it stands.** The framework computes about ten identifiers today or by plan: the config
hash, the data-definition hash, a settings digest and a sources digest per stage, a random token
per stage run, the resolved-input hash, and for Stage 3 the feature signature, `recipe_hash`,
`model_hash` and `run_id`. Each exists for one check the framework makes itself (is EDA still
valid for this config; did a decision change; is this the recipe that was evaluated; is this file
the model that scored). None of them can replace another, because they change at different
moments. The fault is that a person is shown all of them.

**The proposal: three names for people, everything else is bookkeeping.**

| A person uses | Form | Names |
|---|---|---|
| The data definition | the 12-character hash that already names Stage 2's folder | the data, population, target and candidates; EDA and Feature Checks belong to it |
| The run | `r007`: a running number per use case | one Training call and its Evaluation |
| The model version (M2.4) | `v3` of the model key | a registered model |

- **`run_id` is the run number.** Training takes the next free number under
  `<use_case>/06_models/` and creates `r007/` before it starts; when the folder already exists
  (two people at once) it takes the next. A number is never reused while its folder exists.
  `--run r7`, the report's header, the sign-off entry and `list_runs` all use it. D-088's
  "hash + entity + timestamp" form goes; the run's record keeps the resolved-input hash, the
  entity and the start time as fields. `config.md`'s worked example already writes "the 61
  features of `r3`".
- **One hash per bundle.** `model_hash` is one SHA-256 over the bundle's files read in name
  order. `manifest.json` holds the file names and that one hash, not a digest per file.
  Evaluation, and later Inference, recompute it at load and refuse a difference.
- **One place per run for the bookkeeping.** `run.json` in the run folder holds every identifier
  the run was built from (the data-definition, config and resolved-input hashes, the feature
  signature, `recipe_hash`, `model_hash`, the Stage 2 run tokens it paired with, versions, who and
  when). Reports and the card show `r007`, the data definition and the date in their header, and
  the full table once, in the appendix.
- **Finding what happened.** `list_runs` returns one row per run: number, started, by whom,
  data definition, family, features, trials, the headline metric, trained / evaluated / signed
  off. `show_run(r007)` prints the run's record as a short page: what went in, what the search
  did, what came out, where the files are. That is the crunch's manifest, read for you.

**Options.**
- (A) As proposed: `r007`.
- (B) A time stamp, `1116-1015` (month, day, hour, minute): no numbering to look up, and it says
  when; two runs in one minute collide and the year is missing.
- (C) Round 1's form (`3fa9c1d2e4b7-20261116T101502`): unique across machines, unreadable.

*Default:* (A). The number is unique inside one use case in one environment, which is where runs
live; what leaves the environment is a registered model, named by its key and version and tied
to its `model_hash`. `show_run` is one more public function (Q641).

**Answer (EDS, 2026-11-12).** If runtime timestamp is recorded anywhere and can be displayed, then Option (A)

**Outcome.** (A): `run_id` is the run number (`r007`), one `model_hash` per bundle, `run.json`, `list_runs` and `show_run`. The run's start time and duration are in `run.json` and are shown by `list_runs`, `show_run` and each report's header.

### Q595. The `autonomous` level: who runs the upstream stages
**Your note.** "Can you elaborate the pros and cons of either options? Also, even in the
autonomous level one might want to make some decisions after feature checks, how would the user
do that?"

| | (A) The level acts in `run` only | (B) `run_training` runs the upstream stages itself |
|---|---|---|
| What a call does | `run_training` trains or refuses, always. Only `run` (and the CLI) adds a missing stage | `run_training` may start EDA and Feature Checks, minutes of Spark, unasked |
| In a notebook | notebook 04 behaves the same at both levels and never rewrites a report someone has open | at `autonomous`, notebook 04 can rewrite Stage 2's artifacts as a side effect |
| In the code | one function knows what the level does to the order of stages | Training imports EDA and Feature Checks; two routes to the same state |
| The cost | at `autonomous`, calling `run_training` on stale inputs is refused with the fix named (`run`) | none for that person |

**Decisions after Feature Checks at `autonomous`.** The level only decides what happens when
nobody steps in. A person can stop between stages at either level:
1. `run --stages eda feature_checks` (or notebooks 02 and 03);
2. read the report, record `keep` or `exclude` with `decide` (the audit log takes entries at
   both levels);
3. `run --stages training evaluation` (or notebook 04).

The entries change the run's resolved input, not the data definition, so EDA and Feature Checks
stay valid and are not run again.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the automation level acts in `run` only.

### Q625. Selection drops: the ledger only, or audit-log entries too
**Your note.** "Please explain the question deeper."

- **The audit log** (D-125) is the list of decisions that shape a run's input: a person's `keep`
  and `exclude`, a changed setting, Feature Checks' flags. Replaying it onto the config gives
  the resolved input.
- **An automated drop** ("the floor dropped these 14 features in run `r7`") shapes nothing later:
  the next run recomputes its own drops from its own train data. `config.md`'s worked example
  nevertheless writes one `dropped` entry per rule and run into the log, as a trail; replay
  skips it.
- **The per-run ledger** (Q622) records the same fact per feature, with the rule, the value and
  the threshold, and the report shows it.

So the question is whether the drop is written twice.
- (A) Once, in the per-run ledger. The log stays short and holds only what changes an input.
  Someone reading only the log does not see automated drops; the run's report and ledger show
  them. The `dropped` operation leaves the schema and the worked example.
- (B) Twice. The log is then the full history of every feature in one place, at the price of
  several entries per run that nothing reads back, and an operation with a writer and a replay
  rule to maintain.

*Default:* (A).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the per-run ledger is the one record of automated drops.

### Q599. Cross-validation or a holdout inside the search
**Your note.** "What I don't understand here is that FLAML holds out rows on top of the K folds
we are already breaking the data up into, and if yes, does it just take randomly 10% of the rows
or how does that work? I'll need better understanding to decide."

**It is one or the other, never both** (read in the source and run, round 2).
- **Cross-validation** is what runs under a trial budget with no time budget. Every trial is
  fitted K times, each time on K−1 folds, and judged on the fold left out; the trial's loss is
  the mean of the K fold losses. Nothing else is held out. The one exception was FLAML's
  CatBoost wrapper, which took the last 1,000 rows of each training part for its early
  stopping; Q607 (B), settled, removes it.
- **Holdout** is what FLAML switches to by itself only under a time budget, on data it judges
  too large for cross-validation (100,000 rows or more, or too many cells for the time given).
  One split is made once: 10% of the clients, drawn at random with a fixed seed (whole clients,
  because it gets the groups), judge every trial, and each trial is fitted once on the other
  90%. Five times cheaper per trial, and judged on a tenth of the events.
- After the search the final model is fitted on every train row, in both cases.

So round 1's option (B) was not a holdout on top of the folds. It was a switch for very large
data: skip the K fits per trial and judge every trial on our own fold 0 (20% of the clients).

**Options.**
- (A) Always cross-validate on the K folds.
- (B) `training.eval: cv | holdout`, default `cv`; `holdout` judges on fold 0.

*Default:* (A) now; (B) only when a run inside the bank shows the need. With the round-2
finding that a search needs a sensible starting point (Q604), 17 to 67 trials per family at
five fits each is the cost to plan for.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): always cross-validate on the K folds.

### Q600. Too few events to train
**Your note.** "What does 'auto_augment' do? The issue is that for corporate models, I can very
much imagine positive counts in the 100-200 range (I had an FX Activation project with around
that amount of positives). I would prefer no loud fails unless needed; what I think should be
done is that the EDA report should include an additional warning if less than 100 unique
converting clients or 200 events are there, noting the risk you highlighted and proposing a
lower k fold number for CV; Training should only fail loud with any fold having zero positive
events, but give report warning if the duplication happened for any fold. What do you think of
this?"

**I agree with the shape and would change two details.**
- **`auto_augment`** is a FLAML switch: when a class has fewer than 20 rows, it copies those
  rows until there are 20. Read in the source and run (round 2): it acts only on FLAML's own
  row-wise splits, never when the folds are given by client, so in this framework the
  duplication cannot happen and there is nothing to warn about. Where it does act, copies of
  one row land in different folds, which is a leak. It stays off (A3).
- **The EDA warning: yes,** below 100 converting clients or 200 events, as you say.
- **Training fails loud only when a fold has no positive event: yes.** Round 1's refusal below
  20 events goes.
- **The warning should not advise fewer folds.** No source recommends it. Fewer folds train
  every trial on less data, which biases the estimate downwards [Kohavi95], and it does not
  buy precision: with 100 converting clients every event is judged out of fold exactly once
  whatever K is, and the mean fold AUC has a standard error near 0.03 either way (Hanley–McNeil,
  my calculation). What the sources recommend at small samples is to stratify and to repeat
  [Kohavi95][Krstajic14][Varoquaux18], and to tune less: automated tuning itself adds
  instability when events are few [Riley23]. Copying or weighting the rare class buys no AUC
  and damages the probabilities [Goorbergh22][Carriero25].

*Default:* your proposal with those two changes; what replaces "fewer folds" is Q649.

**Answer (EDS, 2026-11-12).** Fewer folds: Okay, we won’t do that then

**Outcome.** The EDS's proposal with Claude's two changes: EDA warns below 100 converting clients or 200 events; Training fails loud only when a fold has no positive event; no advice to use fewer folds; no warning about duplication, which cannot happen (`auto_augment` off and inactive with client folds).

### Q649. Folds that hold up at few events (new)
**The proposal.**
- **Balanced client folds for binary tasks.** The converting train clients are put in the order
  of their seeded hash and dealt to the K folds in turn; every other client keeps its plain hash
  fold (Q598). Each fold then holds its share of converting clients: 20 of 100, where the plain
  hash gives anything from about 12 to 28. A fold without a positive event can then happen only
  when there are fewer converting clients than folds. Train labels arrange train folds, which
  §4.4 allows. Regression keeps the plain hash.
- **Repeats.** `training.fold_repeats`, default 1. With R above 1 every trial is judged on R
  different dealings of the K folds, so the choice among trials depends less on one lucky
  split. FLAML takes our folds as a splitter object and ran ten fits per trial for 2 × 5
  (verified, round 2). The calibration's out-of-fold predictions use the first dealing.
- **The warning's text,** in EDA's report and Training's log below 100 converting clients or 200
  events: the fold metric is noisy at this size (about ±0.06 AUC per fold at 20 events); set
  `fold_repeats: 3`, keep the trial budget small, and read differences between runs against
  their intervals (Q630).
- `training.folds` stays a field, default 5.

**Options.** (A) as proposed; (B) the balanced folds without repeats; (C) Q598's plain hash
and the warning only.

*Default:* (A). The corporate case you describe is the reason to build it now rather than in M4.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): balanced client folds for binary tasks, `training.fold_repeats`, the warning's text.

### Q601. Infinite values
**Your note.** "Is encoding infinite values as Null recommended? Is that not an inconsistency
where the same nominator would give the highest value in data with an epsilon denominator, but
Null with a zero denominator?"

You are right, and the measurement backs you. A tree uses only the order of values, and +inf has
an obvious place in that order: above everything. Reading it as null throws that away and mixes
it with "no value", which the libraries route by another rule.

What the three libraries do with ±inf as it arrives (measured, round 2):

| | +inf | −inf |
|---|---|---|
| LightGBM | the largest value | the smallest value |
| XGBoost | refuses to train | refuses to train |
| CatBoost | the largest value | merged with null (its default puts nulls at the low end) |

**The new proposal.** The encoder clips every numeric feature to ±1e30, at training and at
scoring alike: +inf becomes 1e30, −inf becomes −1e30, null stays null.
- Measured: all three accept 1e30, keep it apart from null and sort it beyond every real value,
  so each family treats it as "the largest" (or "the smallest"). The float32 maximum cannot be
  used: CatBoost merges it with null.
- It is a constant, so nothing is fitted and nothing is stored in the bundle.
- The share of clipped values per feature goes to the log and the per-run ledger (`inf_share`);
  reports print the value as "inf".
- It agrees with EDA, where ±infinity is a value that lands in the outer bin.

So x / 0 lands with the highest values, as x / epsilon does, and only "no value at all" (a null,
or 0 / 0, which arrives as null) takes the missing branch.

**Options.** (A) ±inf read as null (round 1's default); (B) fail loud naming the columns;
(C) clip to ±1e30.

*Default:* (C).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (C): numeric features are clipped to ±1e30; a null stays null.

### Q603. Nulls: what `skip_transform` does, and whether to impute
**Your notes.** "FLAML median impute: What happens with skip_transform = True and would it be
possible to change imputation to strata median? What other useful imputation methodologies
should be included?" and "skip_transform should definitely be a parameter in config with
possibly True being the default option."

**What happens with `skip_transform=True`.** FLAML hands the frame to the learner untouched, so
each library applies its own rule for a null:

| Library | A null in a numeric feature |
|---|---|
| LightGBM | at every split the nulls go to whichever side reduces the loss more |
| XGBoost | the same: a default direction is learned per split |
| CatBoost | a null counts as smaller than every value (fixed, not learned) |

**Why the switch itself cannot be a config field.** With `skip_transform=False` the filling is
done by an object inside FLAML. The final model, the fold models and the production retrain are
fitted by the framework, not by FLAML (Q602, settled), and the bundle may hold no pickled
object (D-051). The search would judge filled data while the saved model scores raw nulls,
which is exactly the trap just recorded (T38). So what you want from the switch has to be the
framework's own step: `training.imputation`, fitted on the train split, stored in the bundle as
plain numbers, applied by `score_frame`. That is possible, strata medians included.

**What the evidence says about doing it for boosted trees.**
- In the largest benchmark (13 tasks, up to 100,000 rows, histogram boosting) the native
  handling was the best single method at every sample size (mean rank 4.3). Mean or median
  filling **with** a "was missing" indicator column was level with it (5.2, 5.5); **without**
  the indicator it was clearly worse (7.5, 9.2). KNN and iterative imputation did not beat a
  constant, at up to 200 times the cost [PerezLebel22].
- Better imputation buys almost nothing in prediction: at most a tenth of the gain in imputation
  quality, and nothing beat XGBoost's native handling without an indicator at 50% missing
  [LeMorvan25]. For trees, sending nulls to the better side is the recommended treatment
  [Josse19].
- **Strata medians:** no study found that tests them against native handling. The nearest one
  (group-specific means, clinical data) found they can hurt, depending on why values are
  missing [Jeanselme22].
- In bank data a null usually means "no product" or "no activity", which is signal. Filling it
  with a median hides that unless an indicator is added, and then the indicator carries what
  the null carried before.
- Where filling **is** needed: linear models and neural networks. The evidence there favours a
  constant plus an indicator over anything elaborate. `training.md` already says so for the
  predefined path.

**Options.**
- (A) No imputation in M2.3. Nulls go to the libraries; `skip_transform` is always on and is not
  a field. Imputation arrives with the first family that needs it (Phase 3), as a constant with
  an indicator.
- (B) `training.imputation: none | median | strata_median`, default `none`, built now as the
  framework's own step: medians from the train split (per level of the declared strata for
  `strata_median`), an indicator column per filled feature, the table in the bundle and the
  recipe. Cost: a second encoder path with its tests, a fitted table that a retrain must
  recompute, and indicator columns in the sign-off list.
- (C) (B) with `none | median` only.

*Default:* (A). I would not build (B): the evidence gives it no gain for the three families
Phase 2 has, and each option is a path to maintain. If you want the lever anyway, to let people
see the difference for themselves, (C) is the smallest honest form.

**Answer (EDS, 2026-11-12).** I accept option (A) if as noted above it’s not a problem for regression  [the note above: Okay, got your point, we’ll go with skip_transform; how will this work with regression though?]

**Outcome.** (A): no imputation in M2.3; `skip_transform` is always on and is not a config field. Checked for regression on 2026-11-12 (6,000 rows, 5% nulls, the three families): with it on, `automl.predict` equals the library's estimator on the raw frame exactly; with it off they differ by 5.7 to 16.1 in the target's units.

### Q604. The trial budget: who gets the next trial, and how the next parameters are chosen
**Your notes.** "Does roundrobin learning make sense? I would want to enforce some trials for
every model categories, and if anything I would like to optimize (with Bayesian maybe) how new
parameters are being chosen, but are there other ways to do this than roundrobin?" On Q604:
"why would catboost be dropped for a quick run, isn't xgboost slower?"

A search makes two separate choices, and your note asks about both.

**1. Which family gets the next trial.** FLAML has two rules and nothing else (read in the
source): its default, which draws the family by estimated improvement per second and starved
XGBoost in round 1's run, and round robin. No setting gives a family a minimum number of trials.
What the check added: under round robin the families do not influence each other at all. So
round robin *is* one independent search per family, and round 1's option (B), a separate search
per family, is the same thing with one more freedom: a budget per family. H2O works that way (a
fixed number of models per family, in a fixed order); no tool surveyed combines a free
allocation with a minimum.

**2. How a family's next parameters are chosen.** This is already an optimiser, not random
search. FLAML's method (CFO) starts from one configuration, steps in a random direction, keeps
the step when the loss improves, tries the opposite direction when it does not, and shrinks the
step when neither helps. It is a local search, not Bayesian. FLAML's Bayesian variant
(BlendSearch: the same local search plus Optuna's TPE proposing distant candidates) needs
Optuna, which is not installed on the Mac, so it is untested here. The evidence at this budget
is thin: Bayesian optimisation clearly beats random search at about 130 evaluations, though
not shown on boosted trees [Turner21]; FLAML's own paper found the local search alone good for
LightGBM and weaker for XGBoost, and BlendSearch at least as good as either [BlendSearch21];
nothing compares them at 17 to 67 trials. Tuning gains flatten by about 200 configurations [TabArena25], and good
defaults already hold two thirds of what tuning XGBoost can win [Probst19].

**3. What matters more than either: where the search starts.** FLAML was built for time
budgets, so it starts every family from a deliberately tiny model (4 trees, 4 leaves) and
climbs. In a 25-trial check the tree count reached 60 at trial 8 and 130 at trial 12, the leaves
never passed 16, and two of the first five trials repeated earlier ones. At the `autonomous`
budget (17 trials per family) most of the budget is spent leaving that corner. FLAML lets the
start be set, so the proposal starts each family from an ordinary model (Q605). Trial 1 of
every family is then a sound model in its own right, and the tuned configuration has to beat it
on the folds, which also guards against a tuned model that is worse than the default (about one
case in ten in [Schneider25]).

**CatBoost and XGBoost.** Measured in round 1, at FLAML's defaults: a trial took 1–2 s for
XGBoost, 1–8 s for LightGBM and up to 80 s for CatBoost, because FLAML lets CatBoost grow up to
8,192 trees and stop early. XGBoost was the fastest of the three, not the slowest. FLAML's own
cost table rates CatBoost at 15 times LightGBM. With the tree count bounded (Q607, settled)
CatBoost gets cheaper; how much is on the list to measure. With a budget per family the
template says "give `catboost` fewer trials" instead of "drop it".

**Options.**
- (A) Round robin, `max_iter` the total, equal shares (round 1).
- (B) One search per family. `training.max_iter` stays the total and is split equally, unless
  `training.trials: {lgbm: 30, xgboost: 30, catboost: 15}` gives each family its own count. The
  best family by the fold loss wins. Each search starts from the ordinary model.
- (C) FLAML's default selector.

And the optimiser inside a family:
- (i) CFO, as verified: repeatable under a trial budget.
- (ii) `training.search_method: cfo | blendsearch` now. It needs Optuna in the dev
  requirements (a dependency to add, and its 5.0 API is unverified), and its repeatability is
  unknown until tested.

*Default:* (B) with (i). Bayesian search arrives with the predefined path, which is built on
Optuna (D-020); if you want it sooner, say so and I test BlendSearch after installing Optuna.

**Answer (EDS, 2026-11-12).** Accepting default, but add the blendsearch to Phase 3 wishlist  [and the note: Add Bayesian Optuna variant into Phase 3 wishlist]

**Outcome.** (B) with (i): one search per family with its own trial budget, FLAML's local search (CFO). BlendSearch is on the Phase 3 wishlist in `docs/roadmap.md` (added 2026-11-12). The starting point of each search is decided in round 3, after the measurement the EDS's note on quick early trials asked for.

### Q605. The search ranges: bounded, sourced, overridable
**Your note.** "Bounded defaults, but overridable in config and they have to be researched.
Also, as an M3/M4 todo for EDA (or Feature checks), there should be suggestions for these bounds
based on data."

**What the sources use** (round 2 survey: AutoGluon, TabRepo, TabArena, TabZilla, Optuna's
LightGBM tuner, mljar, LightAutoML, H2O, [Probst19], [Grinsztajn22]; "L" is a log scale):

| Parameter | The sources' ranges | FLAML's own | Proposed | Start |
|---|---|---|---|---|
| **lgbm** `learning_rate` | L 0.005–0.1, 0.005–0.2, 0.01–0.3 | L 0.001–1 | L 0.01–0.3 | 0.05 |
| `n_estimators` | early stopping under a cap of 1,000–10,000 | L 4–32,768, no early stopping | L 50–2,000 | 300 |
| `num_leaves` | 16–96, 16–255, L 2–200 | L 4–32,768 | L 4–255 | 31 |
| `min_child_samples` | 2–60, L 1–64, 5–100; the LightGBM guide: "hundreds" on large data | L 2–129 | L 5–500 | 20 |
| `colsample_bytree` | 0.4–1, 0.5–1, 0.75–1 | 0.01–1 | 0.4–1 | 1 |
| **xgboost** `learning_rate` | L 0.005–0.1, 0.005–0.2, 0.01–0.3 | L 0.001–1 | L 0.01–0.3 | 0.05 |
| `n_estimators` | as above | L 4–32,768 | L 50–2,000 | 300 |
| `max_leaves` (leaf-wise) | L 8–1,024 [TabArena25] | L 4–32,768 | L 4–255 | 31 |
| `max_depth` (`xgb_limitdepth`) | 3–10, 4–10, 1–11; best found 6–14 [Probst19] | 1–15 | 3–10 | 6 |
| `min_child_weight` | 1–5, L 0.001–5, 1–100, 1–128; best found 1.3–7 [Probst19] | L 0.001–128 | L 0.5–20 | 1 |
| `colsample_bytree` | 0.5–1; best found 0.42–0.86 [Probst19] | 0.01–1 | 0.4–1 | 1 |
| **catboost** `learning_rate` | L 0.005–0.1, 0.005–0.2, 0.01–0.3 | L 0.005–0.2 | L 0.01–0.3 | 0.05 |
| `n_estimators` | early stopping | fixed 8,192, early stopping | L 50–2,000 | 300 |
| `depth` | 4–8, 5–8; the CatBoost guide: 4–10 | not tuned (6) | 4–8 | 6 |
| `l2_leaf_reg` | 1–5, L 0.0001–5, L 0.5–30 | not tuned | L 1–10 | 3 |

- **Few dimensions on purpose.** Five per family (four for CatBoost); everything else stays at
  the library's default (the L1 and L2 penalties, row subsampling, the bin count). At 17 to 67
  trials a wide space is noise: one rule of thumb asks for 50 to 100 evaluations per dimension
  [Bischl23], LightAutoML adds dimensions only as the trial count grows, and the penalties are
  worth about 0.003 AUC in the tunability study [Probst19].
- **`min_child_weight` is not a row count.** It bounds the sum of p(1 − p) in a leaf, so at a 2%
  rate a weight of 1 already means about 50 rows (my derivation from XGBoost's docs). That is
  why its upper bound is lower than round 1's.
- **No source ties a bound to the number of events.** The upper bound of `min_child_samples` is
  my reading of the LightGBM guide, not a derivation.
- **Overridable per leaf** in `training.search_space`, as `{low, high, log, integer, start}` or
  `{value}`; the defaults are printed in the template and in every resolved config.
- **Before they become defaults** they are run against FLAML's own ranges and start on `dev`
  and judged against the oracle, together with the two XGBoost variants (A5).
- **Your M3/M4 item** is recorded for the roadmap: EDA or Feature Checks suggests bounds from
  the data. The precedent is LightAutoML, which sets the learning rate, the tree count and the
  starting leaves from the row count in five bands.

**Options.** (A) FLAML's own ranges and start; (B) the table above.

*Default:* (B).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): the bounded, sourced ranges, overridable per leaf, checked on `dev` before they become defaults. The "Start" column is not settled here (round 3).

### Q606. The search metric per decision type
**Your note.** "Two questions: Why did you suggest these exactly (while roc_auc is the default
for binary classification)? Also, what about regression?" (Regression: Q639.)

**Why not `roc_auc` for everything.** AUC looks only at the order of the scores. Two models with
the same order and very different probabilities have the same AUC, so a search on AUC puts no
pressure on the probability at all [Gneiting07]. When the score is consumed as a probability,
or cut at a probability, the log loss is the criterion that rewards both the order and the
level. That is the reason for the first two rows, and tools split the same way: mljar tunes and
stops on log loss, H2O ranks on AUC but stops on log loss, TabArena and FLAML use AUC.

**Where round 1 went beyond the evidence.** I proposed `ap` for `top_n` on an argument (average
precision weighs mistakes among the highest scores) and the round 2 survey found no study
showing that selecting on it gives better lists. It is the noisier criterion at few positives,
its usual estimators are shaky on small data [Boyd13], and a noisy selection criterion overfits
the selection [Cawley10]. It is "not generally better under imbalance" [McDermott24]. So I
withdraw it as a default.

**The proposal now.**

| `decision.type` | Search metric | Why |
|---|---|---|
| `probability` | `log_loss` | the score is used as a probability |
| `threshold` | `log_loss` | a cut acts on the probability scale |
| `ranking` | `roc_auc` | order only; the convention |
| `top_n` | `roc_auc` | order only; `decision.metric: ap` is the documented override for a shallow list with plenty of events |

No study compares "search on log loss" with "search on AUC, then calibrate" for boosted trees;
both are workable, since the calibrator repairs the level afterwards. The table follows the
principle; the trials table stores AUC and log loss for the winning configuration either way,
so the cost of the choice is visible.

**Options.** (A) round 1's table (`ap` for `top_n`); (B) the table above; (C) `roc_auc` for
every decision, FLAML's default.

*Default:* (B). `decision.metric` overrides it and is checked against the task at load.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): `log_loss` for `probability` and `threshold`, `roc_auc` for `ranking` and `top_n`.

### Q609. Categoricals: two kinds, ordered as numbers and unordered declared to the library
**Your notes.** "Encoder: Include native categoricals and ordered kinds now." On Q609: "I think
option (B) would be the best, but then it means categoricals have to be null-filled even if
skip_transform = True. One question: What is the expected performance difference between option
(A) and (B)? One idea: what if we have two sets of categoricals, ordered categoricals which
probably perform well in numerals (like credit rating) and unordered categoricals (like
geography) where numeric conversion would probably be a performance issue?"

**The expected difference between (A) and (B): small, and its sign depends on the family.**
- No source gives effect sizes for declared categoricals against numeric codes by number of
  levels. scikit-learn's own comparison on ten low-cardinality features found the encodings
  comparable "with a slight edge for the native handling". LightGBM's docs advise treating a
  high-cardinality feature as numeric. Integer codes did poorly with boosting on features of
  many levels in [Pargent22], against target encoding; declared categoricals were not tested
  there.
- A constructed test run for this round (100,000 rows, 3 seeds, one unordered feature of 8, 50
  or 300 levels, no pooling of rare levels; not a benchmark): every difference was within
  ±0.006 AUC, most within the spread between seeds.

  | Levels | LightGBM | XGBoost | CatBoost |
  |---|---|---|---|
  | 8 | +0.002 | +0.002 | +0.002 |
  | 50 | 0.000 | −0.004 | −0.001 |
  | 300 | −0.006 | +0.005 | +0.004 |

  (Declared minus codes, holdout AUC. At 8 levels the gain held on every seed for all three. At
  300 levels LightGBM was worse on every seed in log loss; CatBoost better on every seed.)
- **Your two-kinds idea is supported.** A tree splits on order alone, so codes in the true
  order lose nothing for an ordered feature, while a declared category throws the order away. In
  the same test, declaring the ordered feature as a category cost CatBoost 0.002–0.003 AUC.

So (B) is mainly the right meaning (no invented order between regions) and CatBoost's strength,
not a large accuracy gain. Its costs are below.

**The proposal.**
- **Ordered categoricals** are declared with their order,
  `training.categoricals.ordered: {rating: [C, B, A, AA, AAA]}`. The encoder gives codes in that
  order and every family reads the column as a number. A null stays null. A train level missing
  from the declared list fails loud (the list is a contract); an unseen level at scoring
  becomes null and is counted. EDA keeps treating the column as a categorical; teaching EDA the
  order is a later item.
- **Unordered categoricals** (every other categorical) get integer codes from the frozen train
  levels and are declared categorical to each library:
  - codes: 0 for a missing value, 1 to K for the kept levels by train frequency, K + 1 for
    `__other__` (the levels below `min_level_client_count`, and any unseen level at scoring);
  - **yes, a missing value gets its own code.** That is the natural reading of a missing
    category ("no segment"), CatBoost refuses nulls in such a column, and LightGBM would
    otherwise pool nulls with unseen levels (measured). Reports call the level `null`;
  - measured on the pinned versions: the round trips stay bit-identical with categorical splits,
    the contributions still sum to the margin on reloaded boosters, and the thread count does
    not matter.
- **One switch,** `training.categoricals.unordered: native | codes` (default `native`), for the
  whole use case. `codes` passes the same integers as plain numbers (round 1's option (A)). It
  exists because the evidence is mixed, above all for LightGBM at many levels, and two runs with
  `compare_runs` settle it on the use case's own data.

**What it costs** (measured):
- Each library is told in its own way, and FLAML's wrappers differ: LightGBM through a fit
  argument, XGBoost through two constants in the search space (FLAML's own XGBoost default is
  codes as numbers), CatBoost only through a pandas `category` column. That lives inside the
  family's functions.
- CatBoost fits 2 to 2.4 times slower with a declared categorical.
- An unseen code is handled three ways (LightGBM: a "none of these" branch; XGBoost: the same
  side, not the missing branch; CatBoost: its prior). Mapping unseen levels to `__other__`
  before the model sees them makes this matter only when train had no rare level.
- The loader must pass CatBoost integers, never floats, in those columns.
- To check in the first build step: that the framework's own fit still equals FLAML's model bit
  for bit with declared categoricals.

**Options.**
- (A) Codes as numbers for every categorical (round 1's first option).
- (B) As proposed: ordered as numbers in the declared order, unordered declared, the switch.
- (C) (B) without the switch.

*Default:* (B).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): ordered categoricals as numbers in a declared order, unordered ones declared to the library, the `native | codes` switch.

### Q611. Automated selection: what irrelevant features cost, and importance pruning
**Your notes.** "What is the difference between (A) and (C), what is the importance pruning?"
and "Boosted trees lose little accuracy to irrelevant features, okay, but how much calculation
time do we lose with them?"

**The cost, measured** (round 2: 10 real features plus pure-noise columns, 100,000 rows, 300
trees, 4 threads, other jobs running, so read the ratios):

| Features | LightGBM fit | XGBoost fit | CatBoost fit |
|---|---|---|---|
| 10 | 0.9 s | 1.6 s | 2.2 s |
| 50 | 1.6 s | 3.2 s | 4.0 s |
| 100 | 2.7 s | 4.4 s | 4.9 s |
| 200 | 5.2 s | 7.9 s | 7.9 s |
| 400 | 10.3 s | 15.8 s | 12.4 s |

- **Time grows in a straight line with the number of features:** about 2.4 s per 100 extra
  features per LightGBM fit, 3.7 s for XGBoost and 2.6 s for CatBoost at this size. A search
  trial under five folds cost 4.6 single fits, so 100 irrelevant features add about 11 s to
  every LightGBM trial, about 12 minutes over a 67-trial budget (my arithmetic on the measured
  numbers). Scoring time and contribution time hardly move.
- **Accuracy lost to 390 noise columns:** 0.004 AUC for LightGBM, 0.006 for XGBoost, 0.008 for
  CatBoost. Small, as the literature says.
- **What the clock does not show:** at 400 features the noise columns held about half of
  LightGBM's and XGBoost's split gain, and a quarter of CatBoost's importance. The importance
  chart stops being readable and the sign-off list fills with features that do nothing.

So selection pays in search time, roughly in proportion to what it removes, and in a sign-off
list a person can defend. It does not pay in accuracy.

**Importance pruning, the third rule.** The floor asks "does this feature tell anything on its
own?". Pruning asks "does the model still need it once the others are there?", which is what
removes the dozens of behavioural aggregates that each carry signal alone and add nothing
together.
1. Add five seeded columns of random numbers to the train frame.
2. Fit the K fold models once, with ordinary fixed parameters, and take every feature's
   out-of-fold contribution share.
3. The candidates to drop are the features that do no better than the best random column. A
   person's `keep` survives.
4. Fit the fold models again without the candidates. The pruning is accepted only when the
   out-of-fold loss is no worse; otherwise nothing is pruned and the run says so.
5. The search runs on what is left, and every drop is in the per-run ledger with its value and
   the threshold.

This is what the AutoML tools do in place of a univariate floor [AG-FS][mljar]. Unlike the
floor, a feature that only works together with another survives, because the model sees the
two together. The cost: two rounds of K fits before the search (my estimate from the table
above: a minute or two at the card's size) and one more rule to build and test.

**Options.**
- (A) The cluster rule and the floor now; pruning in M4. Round 1's default.
- (B) No selection in M2.3.
- (C) All three now, in this order: cluster, floor, pruning (D-106 already fixes that pruning
  comes before the calibration's out-of-fold predictions, on the same folds).

*Default:* (C), following Q590. The floor (Q612, settled) stays as the cheap first pass; the
two rules answer different questions.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (C): the cluster rule, the floor and importance pruning, in that order.

### Q615. When the calibrator applies
**Your note.** "What are the pros and cons going with (A) vs (B)?"

| | (A) By decision, declared | (B) By evidence, kept only if it helps |
|---|---|---|
| The rule | `probability` → `platt`; every other decision → `none`; a person may set `platt`, `beta` or `none` | fit the calibrator, keep it only when the out-of-fold log loss improves by more than its noise |
| For | the config says what will happen before any result; a retrain in production runs the same steps as the evaluated parent; nothing to tune | never keeps a calibrator that made the out-of-fold loss worse |
| Against | may apply a calibrator that changes little | the model's steps depend on the data: a production retrain can come out calibrated when its parent was not; "more than its noise" needs a rule of its own (a client bootstrap of the loss difference) and a threshold nobody can source |
| Risk when it changes little | none: Platt on the margin contains "leave as is", so with enough events it fits a ≈ 1, b ≈ 0 | — |

(A) keeps the evidence without the branch: the out-of-fold log loss of `none`, `platt` and
`beta` is in the run and the report for every binary run, whatever the decision. A DS who sees
that `beta` is clearly better sets it with one audit-log entry and trains again.

*Default:* (A). `calibration.method` is `platt`, `beta` or `none`; the schema fills it from the
decision when it is not set and refuses a calibrator for regression (Q639).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the calibrator follows the decision; the out-of-fold log loss of `none`, `platt` and `beta` is stored for every binary run.

### Q619. A `model_hash` that repeats
**Your note.** "If still relevant with above comments, please explain the questions and choices
deeper."

Still relevant with one hash (Q647): the question is what that hash is taken over.
- **What the hash is for.** (1) Every score names the model that made it. (2) A loader refuses a
  file that changed. (3) The drift reference is keyed by it. (4) "A rerun of the same resolved
  config gives the same model" (D-094 (d)) becomes a test: train twice, compare two hashes.
- **The problem.** Uses 1–3 work with any hash. Use 4 fails for CatBoost: its file embeds a
  random id, the finish time and a dump of its parameters, so two identical trainings give
  different bytes and different hashes, although every tree and every prediction is the same
  (verified). LightGBM's file differs only in a line recording the thread count.

**Options.**
- (A) Before saving, delete CatBoost's five run-specific metadata entries (the id, the finish
  time, three parameter dumps). Verified: the hashes of two trainings are then equal and the
  model scores the same. The parameters are in the recipe anyway. About ten lines in CatBoost's
  `save`. The same model then has the same hash in all three families.
- (B) Hash the predictions on a fixed table instead of the file. No file surgery, but the bundle
  must carry a table of rows to score, and the last decimals can differ between machines.
- (C) Do nothing: a CatBoost model gets a new hash at every training. Uses 1–3 are unaffected;
  the repeat test compares predictions for CatBoost instead of hashes, and "did this rerun give
  the same model?" has no one-look answer for that family.

*Default:* (A): small, verified, and it keeps one rule for the three families. (C) is the
choice if you would rather not touch CatBoost's file.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): CatBoost's five run-specific metadata entries are deleted before saving.

### Q628. What "pooled" means, and does "per period first" (D-098) make sense
**Your note.** "Critically, does D-098 makes sense in the context? Like I have never seen an
evaluation with more than one AUC chart and I'm pretty sure it's been pooled every single time."

**You are right about the charts, and round 1 went too far.** D-098 (test metrics per
observation period as the primary view, pooled second) has two reasons behind it, and only one
of them needs anything per period.

- **Reason 1, the slices.** A list is cut inside one period, because a campaign scores one
  period. Cutting "the top 10,000" out of six periods of rows thrown together is not a decision
  anyone takes, and a client who converts is positive in up to `w` rows, so the pooled count is
  rows, not events. Slices therefore stay per period, then added up (Q629, settled). This part
  of D-098 holds.
- **Reason 2, comparing test with the single validation period.** For this a table is enough.
  It never needed one chart per period.
- **What a plain pooled AUC does differently.** It also compares a row of March with a row of
  July. With six periods about five sixths of all pairs are such cross-period pairs, which no
  decision ever makes (my derivation; the formal version is the covariate-adjusted ROC of
  [JanesPepe09]). It only moves the number when the base rate drifts across the window and the
  scores drift with it. Inside a six-period window I expect the third decimal (not measured;
  the report will show both). The search's own fold metric pools rows the same way, so the
  pooled number is also the one that matches what the search optimised.

**The proposal now.**
- **One curve per split,** drawn on all its rows: ROC, precision–recall, capture, reliability.
  Validation is one period anyway. Nothing is drawn per period.
- **The headline number per split is the plain pooled one,** the number everyone knows.
- **One table and one small line chart** give the metric per period (view 2), with the mean of
  the periods in its last row, so stability over the window is visible at a glance.
- **A note, not a rule:** when the pooled AUC and the mean of the per-period AUCs differ by more
  than their intervals, the summary says that the base rate moved inside the window and that
  the per-period values are the ones to read.
- D-098's wording changes to match: per period in the table and for the slices; curves and
  headline pooled.

**Options.**
- (A) Round 1: pooled means within periods only; the plain pooled AUC is not shown.
- (B) As proposed: plain pooled curves and headline, per-period table, slices per period.
- (C) Plain pooled everywhere, slices included.

*Default:* (B).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): one curve per split on all its rows and a pooled headline; per period in a table and for the slices. D-098's wording changes with the spec.

### Q630. Intervals in M2.3
**Your note.** "Please explain the question with more context."

- **What an interval is for.** "AUC 0.84 (0.82–0.86)" says how far the number could move by
  chance. Without it nobody can tell whether 0.84 against a baseline's 0.82, or against the last
  run's 0.835, is a difference at all.
- **The complication.** Rows are not independent. A client is in up to six periods of test, and
  a converting client is positive in up to `w` of them. A formula that counts rows treats
  180,000 rows as 180,000 separate observations and gives intervals that are too narrow.
- **(A) Formulas, counted in clients and events.** Hanley–McNeil for the AUC (EDA has it),
  Wilson for a rate at a slice. No simple formula exists for lift, average precision, the
  log-loss skill or the observed-to-expected ratio, so those would carry no interval.
- **(B) A bootstrap by client.** Redraw the clients 200 times, recompute every metric each time,
  report the middle 95% of the 200 values. In practice each client gets a random weight drawn
  from its id, so all of its rows move together [Najmi15][TFMA]. It covers every metric the same
  way, and two runs scored on the same rows share the weights, so the interval of their
  difference is right too (the run comparison needs exactly that). Computed on binned scores; my
  estimate is a fraction of a second per replicate at the bank's size, to be measured.
- **(C) None.**

Round 1's default was (A) now and (B) in M4. With Q590 and "Evaluation has to be extensive",
the new default is (B) in M2.3: one method for every metric. The formulas stay where they are
used today (EDA, and the oracle test's two-standard-error tolerance).

*Default:* (B) now, 200 replicates, `evaluation.intervals: {replicates: 200, level: 0.95}`.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (B): a client bootstrap, 200 replicates, for every metric.

### Q635. The familiar SHAP plots, in the notebook and the report
**Your note.** "The 'real' decision is how can we ensure that the same familiar SHAP-like plot
types (feature importance, swarm, waterfall, color coded) can be printed in notebook and report?
I could be fine with a number of different implementations as long as the design output is there
and is right."

**A prototype answers it: look at
`/private/tmp/claude-501/-Users-danielszabo-Work-Core-modelling-Core-modelling-framework/c06c6caf-2ac5-4570-a5ac-624b4b09e191/scratchpad/r13/shap_like_plots.html`**
(throwaway; a toy model; each of the four plots drawn in plotly beside `shap`'s own picture).
I looked at the rendered page: the bar and the beeswarm are near-identical to `shap`'s, the
waterfall and the dependence scatter are close.

**The proposal.**
- Four chart functions beside the existing ones in `reporting/charts`: the importance bar, the
  beeswarm, the waterfall for one row and the dependence scatter. Each takes the contributions
  the family's own function returns (equal to SHAP's tree explainer, Q617). One figure serves
  the notebook and the report, so the two cannot differ.
- They use `shap`'s colours (red raises, blue lowers; blue to red for a low to high feature
  value; grey for missing), so a DS recognises them at once. The fonts, titles and margins are
  the house style.
- The beeswarm draws 1,500 seeded clients per feature (about 0.5 MB in the report; the shape is
  already `shap`'s at that size); the bar uses the whole explanation sample.
- The waterfall is drawn for three example rows of the test sample: the highest score, a row at
  the decision's cut, a typical row. Labels read `feature = value`.
- Two rules of `reporting.md` change: "distributions are box plots, never raw points" gets the
  beeswarm and the dependence scatter as named exceptions, and the theme gets a contribution
  colour pair.
- The framework still imports no `shap`. A DS who wants `shap`'s own pictures builds a
  `shap.Explanation` from the stored contributions table in three lines; the helper notebook
  shows how.

What the prototype did not match: `shap`'s arrow-shaped waterfall bars (rectangles with a small
arrow head instead), and values printed inside wide bars. Not checked: hover text, the look
inside the bank's JupyterLab (spike 5 covers plotly there).

**Options.**
- (A) As proposed: plotly, one implementation.
- (B) `shap`'s own matplotlib pictures embedded as images. The exact look and no chart code, but
  static images in an otherwise interactive report, `shap` and matplotlib become imports of the
  framework, and `shap`'s plotting calls have changed between its versions.
- (C) Plotly in the report and `shap`'s pictures in the notebook: two looks for one thing.

*Default:* (A). The importance method itself stays as round 1 proposed (the libraries' own
contributions; permutation importance among the further views).

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the four SHAP-style charts in plotly, one implementation for the notebook and the report.

### Q648. How far "extensive" goes
**Your note.** "Evaluation: This and the reporting over it has to be extensive now as that's the
most 'user-facing'."

**The proposal: everything round 1 listed for later joins M2.3, and two familiar charts move
up.** The report shows every view by default, in this order; `evaluation.views` can switch any
of them off.

| # | View | Change from round 1 |
|---|---|---|
| 1 | Summary: choices, how to read, headline, gates | the warnings of Q636 are gone |
| 2 | Metrics by split and period: a table and one line chart, with intervals | intervals (Q630) |
| 3 | ROC and precision–recall curves, one chart each per split | was extended (Q628) |
| 4 | Capture curve with the slice table | — |
| 5 | Reliability, with the level and slope | — |
| 6 | Score distribution, converters against the rest, each to its own scale | — |
| 7 | Strata table | — |
| 8 | Feature importance: the bar, train out of fold beside test | SHAP style (Q635) |
| 9 | The beeswarm | new (Q635) |
| 10 | Feature effects: the dependence scatter with the mean contribution per group and EDA's lift beside it; a level table for categoricals | which features: A23 |
| 11 | Waterfalls for three example rows | new (Q635) |
| 12 | The sign-off view | — |
| 13 | What the search did: trials, best loss and time per family | — |
| 14 | Threshold table | was extended |
| 15 | Permutation importance per cluster, with a rank check against the contributions | was extended |
| 16 | PDP and ICE for the same features as view 10 | was extended |
| 17 | Validation on test clients only | was extended |

Beside the report:
- **A run comparison.** `compare_runs(run_a, run_b)` returns the two runs' metrics side by side
  on the rows both scored, each difference with its client-bootstrap interval, the features that
  entered or left, and the largest changes in importance rank; notebook 05 shows it. Testers
  will iterate (keep a feature, train again), and without this "did it help?" has no answer.
  The comparison report over many runs and the sweeps stay in M4.
- **The model card** as HTML (Q638) and the regression views (Q639).

**Options.** (A) as proposed; (B) as (A) without `compare_runs`; (C) round 1's split (views
14–17 only as they fit).

*Default:* (A). `compare_runs` is one more public function.

**Answer (EDS, 2026-11-12).** No answer; unanswered questions take their default (the EDS, 2026-11-12).

**Outcome.** (A): the seventeen views, `compare_runs`, the card as HTML, the regression views.

### Q639. The regression entries: objective and metric from the config, and the mean correction
**Your note.** "Why would the search metric/objective not as parametrized as it is for binary?
What does 'mean correction' calibration mean?"

No good reason: round 1 kept regression thin, and Q590 has changed that.

**What a mean correction is.** After training, every prediction is multiplied by one number:
the total observed amount divided by the total predicted amount, taken on the train split's
out-of-fold predictions. It makes the average prediction equal the average outcome. It is the
regression counterpart of fixing the level of a probability, and it matters for objectives that
do not keep the average by themselves (a log link, as Tweedie and Poisson use, loses it when
the boosting stops before convergence [Wuthrich20]). One plain number in the bundle.

**What the evidence says for amounts with many zeros and a long right tail** (the test variant:
18% zeros):
- Squared error and the Tweedie and Poisson deviances all aim at the mean; the absolute error
  aims at the median, which under such skew is far below the mean and understates totals
  [Gneiting11].
- A Tweedie objective with a variance power between 1 and 2 is the distribution with exactly
  this shape: a mass at zero and a skewed positive part [Yang18]. All three libraries have it.
  A gamma objective needs strictly positive targets, so zeros rule it out.
- Squared error is right on average but its fit is driven by the largest amounts.
- Among the AutoML tools H2O offers Tweedie and Poisson and LightAutoML a few robust losses;
  AutoGluon, mljar and FLAML stay with squared error and RMSE or R².

**The proposal.**

| Entry | Regression |
|---|---|
| Objective | `training.objective`: `squared_error` (default), `tweedie` (with `variance_power`, default 1.5), `poisson`, `absolute_error`, `huber`. The per-task spec lists what each task allows; binary allows `log_loss` only |
| Search metric | follows the objective, so a trial is judged by the loss it was trained for: `rmse` for `squared_error` and `huber`, the Tweedie or Poisson deviance for those two, `mae` for `absolute_error`. `decision.metric` overrides it (`rmse`, `mae`, `r2`, the deviances). The decision type does not change it |
| Calibration | `calibration.method: mean` or `none`. Filled as `mean` for `tweedie` and `poisson`, `none` for the others (`absolute_error` and `huber` do not aim at the mean on purpose). `platt` and `beta` are refused |
| Sampling | `client_sample`; no offset |
| Metrics | RMSE, MAE (with the note that it rewards predicting the median), R², the objective's deviance, the concordance (EDA's scale), the share of the total amount captured at each slice, the ratio of mean predicted to mean observed per period |
| Views | predicted against observed in 20 groups of the prediction; the capture curve of the amount; error by stratum; the importance and SHAP-style views as for binary |
| Baselines | the train mean; the single feature |

The template explains when to choose `tweedie` (a non-negative amount with zeros and a long
tail). A suggestion from the data belongs with your M3/M4 item on suggested bounds.

**Options.**
- (A) Round 1: squared error and `rmse`, fixed; no calibration.
- (B) As proposed.
- (C) (B) without `absolute_error` and `huber` (three objectives, all aiming at the mean).

*Default:* (B). To check in the first build step: `tweedie` passes through FLAML's search for
the three families (round 1 verified it as a constant in the search space), and the deviance as
a custom metric.

**Answer (EDS, 2026-11-12).** Accepting your proposal here, with one question: Should mean correction not be winsorized/capped? If I just think about a dataset with power law values (e.g. market cap of companies), mean correction multiplier will heavily be decided by performance at a few data points and the correction potentially does more harm than good. What does research say about this?

**Outcome.** (B): the objective from the config, the search metric following it, `calibration.method: mean | none`. How the mean correction is made robust (or whether it is applied by default at all) is decided in round 3, after the research asked for.

### Assumptions accepted in round 2 (explained or new, not vetoed)

- **A3.** *"What do those parameters fix and why isn't it a risk to 'hardcode' them?"* They are
  five switches of FLAML's `fit`, not modelling choices. Each one, left free, would break
  something the framework promises:

  | Switch | What it would do | Why it is fixed |
  |---|---|---|
  | `auto_augment=False` | copy the rows of a class with fewer than 20 rows until it has 20 | It changes the class balance without telling the calibration. Read in the source: it never runs when client groups or our own splitter are given, so the setting only makes that explicit |
  | `ensemble=False` | stack the best learners into one scikit-learn ensemble at the end | The bundle holds one booster in one native file; a stack has no such format (D-051). FLAML's default is already off |
  | `early_stop=False` | let FLAML end the *search* early when it judges it has converged | A trial budget then no longer means that many trials, and a rerun may stop elsewhere. It is not the boosting's early stopping. FLAML's default is already off |
  | `sample=False` | train early trials on a subsample of the rows | It only acts under a holdout on large data, never under cross-validation; fixing it keeps the behaviour the same if the evaluation method ever changes |
  | `log_type="all"` | (default: log improving trials only) | The trials table needs every trial |

  The risk of fixing them is that a use case one day needs one. Then it is a code change with a
  reason, which is the right size for a switch that breaks a guarantee. They are listed in
  `training.md`, so nothing is hidden.
- **A4.** *"Explain this."* `scale_pos_weight` (XGBoost, LightGBM), `is_unbalance` (LightGBM),
  `class_weight` (the scikit-learn wrappers) and `auto_class_weights` (CatBoost) all tell the
  learner to count each positive row several times. The model then believes positives are more
  common than they are, and its probabilities come out too high; the libraries' own docs say to
  use them only when the ranking matters and the probability does not [LGBM-P][XGB-T]. The
  framework's calibration undoes exactly one change of the class balance, the declared sampling
  with its one keep fraction (§4.12). A weight slipped in through `training.search_space` would
  be a second change it does not know about, and every score would be silently too high. So the
  config refuses those four names at load and points to `sampling: negative_downsampling`, which
  does the same job with the offset applied.
- **A8.** *"What does this mean?"* A person's `keep` protects a feature from the automated rules
  (D-134). The assumption says the rules still *measure* a kept feature; they just never drop
  it. Concretely: the ledger shows its floor value and whether the floor would have dropped it;
  it still counts as a member of its redundancy cluster (so the cluster's representative is
  chosen with it in the comparison, and both stay if the kept one loses); it still gets an
  importance. The person who kept it sees what the rules thought of it.
- **A14.** *"What's the effect of this?"* Plumbing only. The audit log's `run` entry was shaped
  for Feature Checks, which must list the periods it compared (so that a later move of the
  validation period can be refused, D-088), and the code demands that list on every `run`
  entry. Training compares no periods, so its entry has none and the code stops demanding it for
  Training. The effect for a user: a Training run never blocks moving the validation period.
- **A23.** The feature-effect views (10 and 16 in Q648) cover the model's ten largest features
  by contribution share plus every key feature of EDA that the model uses (a person's `include`
  list among them), twenty at most. Each chart shows EDA's lift beside the model's effect.
- **A24.** FLAML gets our folds as a splitter object for both tasks (verified for one and for
  two dealings), not the fold number as `groups`. One route, and regression no longer needs
  `split_type="group"`.
- **A25.** `decision.baselines` takes `population_base_rate`, `single_feature`,
  `{previous_model: <column>}` and `{historic_predicted_rate: <number or column>}` (Q631's
  outcome: a number is one rate in use, a column is judged like a previous model).
- **A26.** The helper notebook is `00_modelling_helper`, in the form of `00_eda_fc_helper`: it
  loads a stored run and shows each artifact's grain, columns and a few telling rows, beside the
  function that wrote it. It starts in major step 1 with the encoder, the families and the
  bundle.
- **A27.** One more item for spike 5's trip into the bank: the three model libraries import and
  score one batch on an executor (Q596).
- **A28.** In `score_frame` the model is rebuilt once per Spark partition from the bundle's
  bytes, never per batch, and the driver ships the bytes, not a path.
- **A29.** For regression, `decision.type: probability` reads as "the predicted amount is used
  as a number". The name stays for now; a clearer one would be a schema change, weighed with
  the spec.
- **A30.** The roadmap gains your M3/M4 item when the spec is written: EDA or Feature Checks
  suggests search bounds, and an objective for regression, from the data.

A5 (the EDS: "Wouldn’t it add value to include xgb_limitdepth then? You just said the other three are fairly similar and this is a bit different") and A19 (the EDS: "Let’s include monotone constraints now, this would be useful in a bank context") changed: `xgb_limitdepth` joins the estimator list and monotone constraints join M2.3; their design is in `questions.md`, round 3. Q632 (gates) is open there too.

## Round 3 (asked 2026-11-12, answered 2026-11-13)

**The EDS's message, verbatim.**

> Remarks/Questions/Answers, unanswered goes with default:
> Q650. I agree with the proposal, only one additional question: Is running LightGBM at “basic” a good decision if monotone constraints also should work with “intermediate”? A quick search told me intermediate is better than basic, does it hold up within FLAML as well?
> Q651. Option (B), with autonomous default budget increased to 60
> Q632. I asked this question of the LDS too and he said “I’d also tend towards not having a it has to be >= x for these metrics and more leaving for the user to decide”. For this reason I’d go with option (B), and put it in phase 3 to ask once whether we want to reopen this gating
> A45: One question: Will training times be a part of the reports? Asking because of the following reasonable scenario: We start with a low max_iter budget, distributed equally, but then based on runtimes and performance, we have a “main run” later with a higher, but unequally distributed budget
>
> Do not start the planning exercise yet, just make sure these last few questions are settled and that answers contain everything needed so after a compacting the planning can go onwards.

### Q650. Monotone constraints (new, from A19)
**Your note.** "Let's include monotone constraints now, this would be useful in a bank context."

**What the check found** (pinned versions, round 3).
- **The constraint holds.** All three libraries kept it exactly on real values (no violation in
  300 rows swept over 50 values each), also after a save and reload, and the contributions
  still sum to the margin. One exception: LightGBM's `advanced` method broke it (28 of 300
  rows). Its default, `basic`, and `intermediate` held.
- **Every library wants its own form and fails in its own way on a mistake.** A bracketed
  string is silently dropped by LightGBM; a short vector is silently padded by XGBoost; a
  constraint on a categorical aborts the whole Python process in LightGBM, is ignored without a
  word by XGBoost and raises in CatBoost. So the framework builds the vector itself for the
  final feature list and checks before any library is called.
- **A null.** LightGBM and XGBoost leave the null branch free: a null scores wherever the data
  puts it. CatBoost counts a null as the smallest value, inside the constraint. On a feature
  with 10% nulls a correct constraint cost CatBoost 0.011 AUC, and nothing once the nulls were
  gone.
- **The price.** A correct constraint cost nothing and helped a little (+0.002 AUC); a wrong
  one, on a U-shaped feature, cost 0.033 (constructed example). The one benchmark found puts
  the price under 0.2% AUC on large credit datasets and at 2–3% on small ones with many
  constraints [Koklev25].
- **Practice in banks:** the directions come from domain knowledge and are checked against the
  data for a wrong sign [Alonso25].

**The proposal.**
- `training.monotone: {income: increasing, utilisation: decreasing}`. A person declares it;
  nothing is derived from the data.
- Allowed on numeric features and ordered categoricals (Q657). On an unordered categorical it
  is refused when Training starts, naming the feature.
- It applies to every fit of the run (the search's trials, the pruning and fold models, the
  final model) in every family, and it is part of the recipe, so a production retrain keeps it.
- **A wrong-sign check, as a warning.** When EDA's direction for the feature is the opposite,
  or EDA marked it `non_monotone`, Training's log and the sign-off view say so. It does not
  refuse: the person may know more than six periods of data show.
- A constraint does not protect a feature from selection; `keep` does. A constrained feature
  that is held or dropped is listed as "declared, not in the model".
- **A check at save.** For each constrained feature the reloaded model is swept over a grid on
  200 rows, and Training fails loud on any step in the wrong direction. It is cheap, and it is
  what catches a library failure such as LightGBM's `advanced`.
- LightGBM runs with its default method, `basic`.
- **CatBoost and nulls:** the log warns when a constrained feature has nulls and `catboost` is
  in the list. Nothing more: CatBoost's fold loss carries the cost, and another family wins
  where it matters.
- It shows as a column in the per-run ledger and the sign-off view, a mark on the feature's
  effect chart and a list on the model card.
- `training.monotone` may be changed through the audit log, so a person can add a constraint
  after reading the sign-off view and train again.

**Options.**
- (A) As proposed.
- (B) As (A), and a wrong sign refuses until a person confirms it.
- (C) Numeric features only; ordered categoricals later.

*Default:* (A).

**Answer (EDS, 2026-11-13).** I agree with the proposal, only one additional question: Is running LightGBM at “basic” a good decision if monotone constraints also should work with “intermediate”? A quick search told me intermediate is better than basic, does it hold up within FLAML as well?

**Outcome.** (A) as proposed, and LightGBM keeps its default method, `basic`. The EDS's question was measured on 2026-11-13: `intermediate` holds the constraint and costs no time, and it showed no gain. In 18 direct comparisons on two constructed datasets (8 and 16 constrained features of 20, 8 to 255 leaves, three seeds) its holdout log loss minus `basic`'s ranged from −0.0006 to +0.0009 with a mean of 0.0000. Through FLAML (20 trials, two seeds) both methods passed as a constant, held the constraint and refitted bit for bit, and `intermediate` ended slightly behind (fold loss 0.2388 against 0.2378, and 0.2287 against 0.2270). `basic` is one of the family's fixed parameters, not a config field. A person can try `intermediate` with a `{value: intermediate}` leaf under LightGBM in `training.search_space`; `advanced` is refused, because it broke the constraint in round 3's check; `intermediate` together with LightGBM's `colsample_bynode` is refused too, because LightGBM would fall back to `basic` with only a warning. The grid check at save guards every method. The numbers: `questions.md` → What the research found → Added on 2026-11-13.

### Q651. The default family list, with depth-wise XGBoost (from A5)
**Your note.** "Wouldn't it add value to include xgb_limitdepth then? You just said the other
three are fairly similar and this is a bit different."

Yes. Checked: FLAML's `xgb_limitdepth` is XGBoost growing level by level to a searched depth,
which is XGBoost's own default behaviour. It gives the same kind of booster as `xgboost`, saves
and loads with the same code and refits bit for bit. In one constructed 20-trial run from the
same start it reached a lower fold loss than leaf-wise `xgboost` (0.4436 against 0.4466) in
about half the time (89 s against 165 s). That is one run on one dataset: a hint, not a result.

The open point is the default list, because every family in it takes a share of the budget.
Four families at the `autonomous` budget means 12 trials each instead of 17.

**Options.**
- (A) Swap. The default list is `lgbm`, `xgb_limitdepth`, `catboost`: three tree shapes that
  really differ (leaf-wise, level-wise, symmetric). Leaf-wise `xgboost` stays accepted in
  `estimator_list`.
- (B) Four by default.
- (C) Round 2's list by default, `xgb_limitdepth` accepted.

*Default:* (A), confirmed or reversed by the `dev` run that also checks the ranges. D-037's
list is reworded either way. The config keeps FLAML's names.

**Answer (EDS, 2026-11-13).** Option (B), with autonomous default budget increased to 60

**Outcome.** (B): the default `estimator_list` is `lgbm`, `xgboost`, `xgb_limitdepth`, `catboost` (FLAML's names). The `autonomous` default of `training.max_iter` rises from 50 to 60, 15 trials per family; `assisted` stays 200, 50 per family. `LEVEL_DEFAULTS`, the template and D-037's list change with the spec and the build. The `dev` run that checks the ranges no longer decides the list; it reports the four families' fold loss and seconds.

### Q652. Where each search starts: FLAML's own start, inside the bounded ranges
**Your note.** "'Every family starts from a deliberately tiny model' - this also means that early
trials run quicker, therefore the gain by resetting starting points is marginal, no?"

You are right, and I measured it (round 3: 70,000 rows × 60 features, 3.5% positive, five-fold,
67 trials, two seeds; fold log loss, lower is better).

| Arm | LightGBM at 17 trials | at 67 trials | XGBoost at 17 trials | at 67 trials |
|---|---|---|---|---|
| (a) FLAML's start, bounded ranges | 0.1343 / 0.1355 in 34 / 30 s | 0.1342 / 0.1352 in 132 / 154 s | 0.1343 / 0.1356 in 33 / 31 s | 0.1343 / 0.1353 in 119 / 155 s |
| (b) an ordinary start (300 trees, 31 leaves), bounded ranges | 0.1341 / 0.1355 in 139 / 115 s | 0.1340 / 0.1354 in 499 / 374 s | 0.1340 / 0.1354 in 183 / 161 s | 0.1339 / 0.1352 in 520 / 436 s |
| (c) FLAML's start, FLAML's own ranges | 0.1341 / 0.1353 in 46 / 33 s | 0.1339 / 0.1350 in 232 / 1,279 s | 0.1365 / 0.1364 in 20 / 13 s | 0.1338 / 0.1351 in 628 / 296 s |

(Each cell: seed 1 / seed 2.)

- **Per trial** the ordinary start is ahead by 0.0001 to 0.0004 in log loss, at 17 trials and at
  67 alike (in one of the four cases at 67 it was behind). **Per second** it is behind: it costs four to five times the time, and arm (a)
  at 67 trials reaches about the same loss in the time arm (b) needs for 17.
- **The corner I warned about is a problem of FLAML's own ranges, not of the start.** With the
  ranges bounded, FLAML's first model already has 50 trees or more. Only arm (c) was still
  climbing at 17 trials (XGBoost: 0.1365 against 0.1340–0.1343), and its time was erratic (one
  run took 1,279 s for 67 trials).
- On this data the winning models were small (4 to 8 leaves), so 31 leaves was no better a
  place to start than 4. Holdout differences between the arms were inside the noise.

So round 2's "started from an ordinary model" goes. The bounded ranges stay: they are what
makes a 17-trial budget work.

**Options.** (A) FLAML's own start inside the bounded ranges; a `start` can still be written
per leaf in `training.search_space`. (B) Round 2's ordinary start.

*Default:* (A). Since trials are cheap this way, the level defaults for `max_iter` can be
higher than 50 and 200; they are set after the timing check on the canonical frame.

**Answer (EDS, 2026-11-13).** No answer; unanswered questions take their default (the EDS, 2026-11-13).

**Outcome.** (A): FLAML's own start inside the bounded ranges; a `start` can be written per leaf in `training.search_space`. Added on 2026-11-13 (trap T39 in `docs/context/lessons.md`): FLAML drops its own start values for every parameter the search space overrides, and with all of them overridden and no start given it runs no search at all. So Training passes the start with every ranged leaf (the default start, or the config's `start`, clipped into the range) and fails loud after each family's search unless trial 1 equals the starts and the trials differ. The level budgets are settled by Q651 and A45.

### Q653. The level correction for regression: plain, with its interval, not winsorised
**Your note.** "Should mean correction not be winsorized/capped? If I just think about a dataset
with power law values (e.g. market cap of companies), mean correction multiplier will heavily be
decided by performance at a few data points and the correction potentially does more harm than
good. What does research say about this?"

**The research.** Your worry is right about the cause and the literature does not offer
winsorising as the cure.
- The factor (total observed over total predicted) is exactly as unstable as the sample mean of
  the target. In a simulation with a perfect model its 5th–95th percentile range was within ±3%
  from a tail index of 2, 0.91–1.14 at an index of 1.5 and 0.50–1.50 at 1.1 (10,000 rows).
- Capping the target before computing the factor makes it stable and wrong: it drops the part
  of the total that sits in the tail, so the factor is biased down, unless the capped excess is
  added back, which is what actuaries do (cap large losses, load them separately) [McNeil97].
- No study of such a factor under heavy tails was found. Below a tail index of about 2 the mean
  itself is the problem: people then model a capped amount, the log amount, or a quantile, and
  say so [Manning98].

**The measurement** (round 3; LightGBM, 60,000 rows; the ratio is mean prediction over mean
outcome on the holdout, 1.00 is right):

| Target | Objective | No correction | Plain factor applied (the factor's 95% interval) | Factor from a target winsorised at the 99th percentile |
|---|---|---|---|---|
| Zeros and a long tail | squared error | 1.00 | 1.00 (0.98–1.03) | 0.90 |
| Zeros and a long tail | Tweedie | 0.96 | 1.00 (1.02–1.08) | 0.91 |
| The same with a power-law tail (index 1.5) | squared error | 0.77 | 0.77 (0.95–1.07) | 0.56 |
| The same with a power-law tail | Tweedie | 0.73 | 0.79 (1.03–1.15) | 0.58 |

- Squared error keeps the level by itself (factor 1.00), so it needs no correction.
- Tweedie predicted 4–5% too low, in train, out of fold and on the holdout alike; the plain
  factor repaired it.
- Winsorising made the level worse than no correction on both targets.
- On the power-law target nothing fixes the holdout: half of its total sits in about 1,000 of
  60,000 rows, and the holdout happened to hold larger ones. The plain factor still moved the
  level the right way, with an interval twice as wide.

**The proposal.**
- The factor is plain, computed on the train split's out-of-fold predictions, as round 2 had
  it: `mean` for `tweedie` and `poisson`, `none` for the others.
- Training stores the factor **with its client-bootstrap interval** and how many rows hold half
  of the target's total. The report shows both beside the level ratio per period.
- **A warning** when the interval is wider than ±5%: "the level of this target is decided by a few rows; the factor, and any model's level,
  is uncertain; consider a capped target". No automatic switch: the method stays what the
  config says.
- Capping belongs to the target, where it changes what is estimated and is stated as such: a
  `cap` on the target rule in Target Factory. Not in M2.3; I would add it to the backlog.

**Options.** (A) as proposed; (B) no correction by default for any objective, the factor only
reported; (C) a winsorised factor.

*Default:* (A).

**Answer (EDS, 2026-11-13).** No answer; unanswered questions take their default (the EDS, 2026-11-13).

**Outcome.** (A): the plain factor on the train split's out-of-fold predictions (`mean` for `tweedie` and `poisson`, `none` for the other objectives), stored with its client-bootstrap interval and the number of rows that hold half of the target's total; a warning when the interval is wider than ±5%; never winsorised. A `cap` on the target rule (Target Factory) goes to the roadmap's backlog with the spec.

### Q654. What a run keeps from Stage 2
**Context.** EDA's and Feature Checks' folders are rewritten whole when those stages are rerun
(D-136). Evaluation, the sign-off view, the model card and the drift reference all read them:
the flags, EDA's directions and lift, the bin edges and shares. So once someone reruns EDA with
another setting, an older run can no longer be re-evaluated or re-rendered as it was, and Q593's
"Evaluation can be rerun alone" breaks. `register` (M2.4) will need the run to be complete in
itself anyway.

**Options.**
- (A) A run is complete in itself. Training copies into `r007/` what later steps need for the
  final features: their Stage 2 ledger rows (kinds, flags, findings, EDA's statistics and
  direction), EDA's bin edges and shares per period (the drift reference's input), and the lift
  table the effect charts show. Evaluation, the card and the sign-off view read only the run
  folder and the data. Small tables: a few hundred rows per feature.
- (B) Nothing is copied. The run records which EDA and Feature Checks runs it was trained
  against (their run tokens), and Evaluation refuses when either was rerun since, naming the
  fix: train again.

*Default:* (A).

**Answer (EDS, 2026-11-13).** No answer; unanswered questions take their default (the EDS, 2026-11-13).

**Outcome.** (A): a run is complete in itself. Training copies into the run folder the final features' Stage 2 ledger rows, EDA's bin edges and shares per period and the lift table; Evaluation, the card and the sign-off view read only the run folder and the data.

### Q655. `compare_runs` and the validation period
**Context.** D-083 (any choice among variants weighs train and test metrics only; validation
never informs a choice; reports still show validation everywhere and people are trusted not to
choose on it). `compare_runs` exists to answer "did it help?" between two runs, which is a
choice among variants. `evaluation.md` req. 7 pairs runs on validation clients.

**Options.**
- (A) The differences with their intervals, and the word "better", are computed on the test
  split. Validation's two numbers are shown side by side under the line "reported, never chosen
  on", with no difference and no interval of the difference.
- (B) Differences on test and on validation alike.
- (C) Validation is left out of the comparison.

*Default:* (A). It keeps D-083's promise in the one function built for choosing.

**Answer (EDS, 2026-11-13).** No answer; unanswered questions take their default (the EDS, 2026-11-13).

**Outcome.** (A): `compare_runs` computes the differences, their intervals and the word "better" on the test split; validation's two numbers are shown side by side under "reported, never chosen on", with no difference.

### Q656. The regression metric: declared with the decision, not derived from the objective
**Context.** In round 2 (Q639, accepted) I wrote that the regression search metric follows the
objective. The review caught the flaw: §4.3 (the metric is declared before any result is seen)
is why `decision` cannot be changed through the audit log, while training settings can. If the
metric followed `training.objective`, changing the objective after a look at the results would
change the yardstick too.

**The correction.** The same shape as binary:
- The metric comes from the decision: `decision.metric`, or the task's default (`rmse`). It is
  the search metric and the headline metric, and it cannot be changed through the log. Allowed
  for regression: `rmse`, `mae`, `r2`, `tweedie_deviance`, `poisson_deviance`.
- The objective is a training setting like the family: it says how the booster learns, and a
  trial is judged on the folds by the declared metric whatever the objective. It may be changed
  through the log.
- The template says: for an amount with many zeros and a long tail, declare
  `decision.metric: tweedie_deviance` together with `training.objective: tweedie`; RMSE on such
  a target is decided by a handful of rows.

**Options.** (A) as corrected; (B) round 2's wording, with `training.objective` barred from the
audit log instead.

*Default:* (A).

**Answer (EDS, 2026-11-13).** No answer; unanswered questions take their default (the EDS, 2026-11-13).

**Outcome.** (A): the metric comes from the decision (`decision.metric`, or the task's default, `rmse`; allowed for regression: `rmse`, `mae`, `r2`, `tweedie_deviance`, `poisson_deviance`). It is the search metric and the headline metric and cannot be changed through the audit log; `training.objective` is a training setting and can. This replaces Q639's "the search metric following it".

### Q657. Where an ordered categorical's order is declared
**Context.** Q609 (settled) put it under `training.categoricals.ordered`. The order is a fact
about the feature, like its kind, and EDA will want it later (bins in the true order, a trend
that means something). Moving a field after release 1.0 is a migration.

**Options.**
- (A) `features.order: {subsegment: [mass, …, private]}`, beside `features.kinds`. Training's
  encoder reads it now; EDA reads it when that is built. It is in Training's settings, not in
  EDA's, until EDA uses it, so setting it does not rerun EDA today.
- (B) `training.categoricals.ordered`, as round 2 wrote it.

*Default:* (A). The synthetic `subsegment` (nine wealth-ordered levels) is the test case.

**Answer (EDS, 2026-11-13).** No answer; unanswered questions take their default (the EDS, 2026-11-13).

**Outcome.** (A): `features.order: {feature: [levels in order]}`, beside `features.kinds`; read by Training's encoder now, and counted in Training's settings, not EDA's, until EDA reads it. This replaces Q609's `training.categoricals.ordered`.

### Q632. Gates: not built
**Your note.** "In real life, at least on this floor, we never say (unfortunately) that this
model exercise did not bring desired results, therefore let's scrap the whole thing and
restart, something will be used. In this context, do we really want to build gates into the
framework?"

No. A pass or fail line that nobody acts on is decoration, and it teaches readers to skip the
summary. What stays useful is the information: the model against each declared baseline at the
decision's metric, with intervals (Q631, Q630), in the report's headline and on the card. A
model that does not beat its best single feature is then plain to whoever approves the
promotion, and that approval is `promote`'s real gate (D-033).

**Options.**
- (A) No gates table and no "passed / failed" anywhere in M2.3. The card's performance section
  and the summary view show the baselines comparison instead. The two config fields that nothing
  reads (`decision.gate_metric`, `lifecycle.promotion_gate.min`) are left as they are, marked
  "not built", for M2.4's design of `promote` to use or remove; D-032's "and the gates" is
  reworded then.
- (B) As (A), and both fields are removed from the schema and the example configs now, so
  nobody sets a gate that does nothing.
- (C) Round 2's table that warns.

*Default:* (A).

**Answer (EDS, 2026-11-13).** I asked this question of the LDS too and he said “I’d also tend towards not having a it has to be >= x for these metrics and more leaving for the user to decide”. For this reason I’d go with option (B), and put it in phase 3 to ask once whether we want to reopen this gating

**Outcome.** (B): no gates table and no "passed / failed" anywhere in M2.3; the report's summary and the card show the model against each declared baseline at the decision's metric, with intervals. `decision.gate_metric` and `lifecycle.promotion_gate` are removed from the schema, the template and the example and test configs in the build's first major step, by the procedure of `CLAUDE.md` §2 (a `schema_version` bump, a migration that drops them, a test that loads an old config). The `lifecycle` section holds nothing else, so it leaves the schema with them until M2.4 gives it content (a plan default; the EDS can veto it with the spec). The Phase 3 wishlist asks once whether a metric gate should come back (`docs/roadmap.md`, added 2026-11-13).

### Assumptions accepted in round 3 (plan defaults from the review, not vetoed)

**Runs and identity**
- **A31.** `run.json` is the run's one identity record and is never rewritten; `training.json`
  holds what Training did. Whether a run is evaluated or signed off is read from its folder and
  the log when runs are listed. This replaces A16.
- **A32.** A run number is never given twice in a use case: the next one is one above the
  highest among the existing folders and the runs the audit log names, so deleting a folder
  does not free its number.
- **A33.** Evaluation picks its run by the data-definition hash and a digest of the settings
  Training read (`training`, the feature decisions, `decision`, `features.order`), not by the
  resolved-input hash. Changing an evaluation setting then does not orphan a run, which round
  1's rule would have done. `run_evaluation(run="r007")` evaluates any run of the same data
  definition with the current evaluation settings.
- **A34.** `model_hash` covers the model file and `bundle.json`. The manifest and the resolved
  config, which carries a timestamp, sit beside them outside the hash.
- **A49.** Write order: the run folder first (it reserves the number), then the bundle, the
  per-run ledger, `training/` last as the commit marker, then the `run` entry. A crashed run
  stays listed as incomplete.

**Stored tables**
- **A35.** An unseen level always becomes the `__other__` code for an unordered categorical and
  null for an ordered one, counted either way. This replaces Q610's "else null", which CatBoost
  cannot take.
- **A36.** Evaluation's per-feature numbers (test contribution shares, unseen and null shares)
  are a table of their own under `evaluation/`, joined when the report is drawn. Evaluation
  never rewrites Training's `ledger_run.parquet`.
- **A37.** The scores table has one row per client, period and part, with `part` (test or
  validation) beside the client's `split`: validation rows hold clients of both splits.
- **A38.** The drift reference uses EDA's stored edges and levels (a categorical's 50 largest
  levels and the rest), not the encoder's levels; Monitoring maps through the encoder when it
  is built.
- **A42.** For log-link objectives (Tweedie, Poisson) the margin is the model's raw output on
  the log scale, `score_raw` its exponential and `score` that times the correction factor;
  contribution charts are on the margin's scale and say so. `bundle.json` stores calibration as
  `{method, parameters}`, one shape for both tasks.

**ML correctness**
- **A39.** The sign-off view is train-only, as D-031 says: its table and its charts come from
  Training's out-of-fold contributions (a seeded sample is stored), so it can be read right
  after training. A sign-off does not need an evaluated run; `register` (M2.4) will need both.
- **A40.** The report says that Training's out-of-fold metric is optimistic, because the
  features and the configuration were chosen on the same folds. The test split is the first
  honest number. Round 1 called the out-of-fold figure "honest"; it is not.
- **A41.** Training stores the in-sample AUC on the rows the model was fitted on, and
  Evaluation shows the train–test gap from it (D-106).
- **A43.** The pruning model is LightGBM at the start configuration, whatever families are
  searched; "no worse" means the mean out-of-fold loss did not rise.
- **A47.** The bootstrap's weights come from a hash of the client id, the replicate number and
  a fixed salt, so two runs always share them.

**Reports, config and docs**
- **A44.** The headline metric (report header, `list_runs`, card) is the decision's metric,
  with AUC (the concordance for regression) always beside it.
- **A45.** `training.max_iter` is split equally over the listed families unless
  `training.trials` names counts; a time budget, when set, is per family. The level defaults
  are set after the timing check on the canonical frame.
- **A46.** EDA gets no second events warning: its existing one gains the converting-client
  threshold. EDA's settings digest is narrowed from the whole `decision` section to the fields
  EDA reads (`type`, `n`), so a new baseline does not rerun EDA. This amends D-137, and stored
  EDA artifacts go stale once.
- **A48.** `reporting.md`'s rule that no chart carries row-level data gets the beeswarm, the
  dependence scatter and the waterfall as named exceptions, each capped (1,500 clients per
  feature). CLI: `--run` with several configs is refused; `runs` and `show-run` list and show;
  a bare `run` still runs every built stage, training and evaluation included. The fold column
  is named `cv_fold`, apart from EDA's encoding folds.
- **A50.** A new owner doc, `docs/components/model_bundle.md`, for the bundle, the manifest and
  `run.json`. The card stays in `reporting.md`, the drift reference in `monitoring.md`, the
  scores and metrics in `evaluation.md`. The glossary gains A22's terms and: run number, fold
  dealing, ordered and unordered categorical, beta calibration, mean correction, importance
  pruning, explanation sample, run comparison.
- **A51.** The synthetic data lacks three things the new tests need, and the tests build them
  on small constructed frames instead of changing the generator: infinite values, a use case
  with fewer converting clients than folds, a categorical of many levels that is not held
  (`nationality`, about 60 levels, is flagged and reaches Training only through a `keep`).

**A45, the EDS's question (2026-11-13).** "One question: Will training times be a part of the
reports? Asking because of the following reasonable scenario: We start with a low max_iter
budget, distributed equally, but then based on runtimes and performance, we have a “main run”
later with a higher, but unequally distributed budget"

**Reply.** Yes, and that scenario is what the search view is for. Already settled: the run's
start time and duration in `run.json` (Q647), the trials table with the seconds of every trial
(A6), and view 13 of the report, "what the search did: trials, best loss and time per family"
(Q648). Made explicit now, so that a quick run tells a person how to spend the main run's
budget:
- **Per family, in view 13 and in `show_run`:** the trials run; the seconds in total, per trial
  (the median) and of the longest trial; the best fold metric and the trial that reached it;
  the family's share of the run's time.
- **One chart:** the best fold metric so far against the cumulative seconds, one line per
  family. A line still falling at its last trial wants more trials; a flat one does not.
- **The other steps' seconds** (selection and pruning, the fold models and calibration, the
  final fit, the bundle with its self-check), stored in `training.json`, so that the run's
  duration adds up.
- **The main run** sets `training.trials: {lgbm: 120, xgboost: 40, xgb_limitdepth: 60,
  catboost: 20}` through the audit log, as `training.max_iter` is set; `compare_runs` shows the
  two runs' budgets and seconds beside their metrics.
- The fold metric is train-only, so choosing a budget on it stays inside D-083 (a choice weighs
  train and test metrics, never validation). Seconds depend on the machine: they enter no hash
  and no test compares them.

**Outcome.** A45 as written, with: the `autonomous` default 60 and the `assisted` default 200
(Q651); the timings above in view 13, `show_run`, `training.json` and `compare_runs`;
`training.trials` changeable through the audit log. Plan defaults: a total that does not divide
gives its remainder, one trial each, to the first families of the list; `training.trials`, when
set, names every listed family and replaces `max_iter`. To check with the build: that a larger
budget repeats the smaller budget's trials as its first trials, so that a main run continues
the quick run's search.

### Replies to the round-2 notes (given with round 3, no decision needed)

- **`skip_transform` and regression.** It works the same way, checked on 2026-11-12 (6,000
  rows, 5% nulls, the three families): with it on, FLAML's prediction equals the library's
  estimator on the raw frame exactly; with it off they differ by 5.7 to 16.1 in the target's
  units, because FLAML's filling acts on the features whatever the task. The target itself is
  never transformed for regression (FLAML recodes labels only for classification), and rows
  with a null target are dropped before Training, as for binary. Q603 is settled as (A).
- **"FLAML starts every family from a 4-tree model."** A search has to try some configuration
  first. FLAML's first try for LightGBM is a model of 4 trees with 4 leaves each, far smaller
  than anything one would use (hundreds of trees, tens of leaves). Each later trial moves one
  step away from the best configuration so far. So the first trials are all near-trivial
  models, and the search needs a number of trials before it reaches the sizes that matter.
  Whether that costs anything real is Q652.
- **"What is Tweedie?"** A family of distributions for an amount that is exactly zero for many
  rows and positive and right-skewed for the rest: what a card holder spends in three months,
  what a policy claims in a year. Picture a random number of purchases, each of a random size;
  many clients have none. One parameter, the variance power, runs from 1 (pure counts, the
  Poisson case) to 2 (strictly positive amounts, the gamma case); 1.5 is the usual middle. As a
  training objective it does two things squared error does not. It predicts on a log scale, so
  a prediction is never negative. And it judges an error relative to the size of the
  prediction: being 1,000 off on a client expected to spend 50,000 counts less than being 1,000
  off on one expected to spend 500. Under squared error every unit of error counts the same, so
  the few largest spenders steer the fit.
- **Q647, the timestamp.** Yes. The run's start time and duration are in `run.json`;
  `list_runs` has a "started" column, `show_run` prints both, and every report's header shows
  the run number with its date. Settled as (A).
- **The wishlist.** FLAML's BlendSearch, its Bayesian variant on Optuna, is on the Phase 3
  wishlist in `docs/roadmap.md`.
- **Fewer folds.** Recorded: the warning does not advise them (Q600, Q649).

## Review 1 of major step 1 (asked 2026-11-14, answered 2026-11-16)

### Q658. The roadmap's dates
The M2.3 row (11-16 to 11-24), its risk trigger and "a spike fails before 11-16" are stale.
*Default:* M2.3 as 11-13 to 12-02 and M2.4 as 12-03 to 12-10.

**The EDS:** "Ignore roadmap dates for now; especially because going onwards my time allocation
will be split with another project (tbd percentages) which will redraw the whole timeline
anyways"

**Outcome.** The roadmap's dates are left as they are; no date is edited until the EDS's time
split is known and the timeline is redrawn.

### Q659. Split `config/schema.py`?
It is 924 lines. *Default:* keep one file.

**The EDS:** "Keep as-is for now, but will have to be split at some point if it goes above 1000
lines"

**Outcome.** One file. The split is due when the file passes 1,000 lines.

### Q660. Stricter type coercion in the config?
`folds: "5"` loads as 5, in every section. *Default:* leave as is.

**The EDS:** "Default"

**Outcome.** Left as is.

### Q661. `conf/local/cc_acquisition.yml`
A gitignored copy from 11-11 that used six removed fields and no longer loaded. *Default:*
delete it.

**The EDS:** "Fix it so that my additions stay but is up to date"

**Outcome.** Rebuilt on 2026-11-16 from the current `conf/base/cc_acquisition.yml` plus the
EDS's two additions (the `established_client` analysis filter and the three listed
`eda.key_features.include` features); it loads.

### Remarks of review 1 (answered in chat, 2026-11-16)
The encoder's local constants and `unit_id`; the unordered coding; where `ENCODE_BY_KIND`
sits; a declared level absent from the data; the families under a single chosen family; one
file per family (kept, the EDS left it to Claude); scoring for a deployed model; "salted
hash"; how the folds are dealt; A67, A69, A76. No default A65–A81 was vetoed.

### Q662–Q665. The edits from the remarks
Q662: the encoder uses the literal `"unit_id"` and `ENCODER_SCHEMA_VERSION`. Q663: Training's
log lists each declared level without a train row (step 2's list in the plan). Q664: measure
prediction threads on an executor and pin them inside `score_spark` (step 3's list). Q665: the
split of `config/schema.py` past 1,000 lines as a roadmap backlog line.

**The EDS:** "All questions go with the default"

**Outcome.** All four applied on 2026-11-16.

### Q666. Guidance beside `floor_z` (from the A69 follow-up)
**The EDS:** "My concern is also a bit from the other side, that of a low amount of converting
clients with a "true signal" but "unlucky" concordance would get filtered, could this happen a
lot? Also, back to a previous comment of mine with regards to Corporate models, with few
converting clients this floor could be a bit too high, no?" Then: "Apply Q666".

**Outcome.** Yes to both: at 50 to 100 converting clients a true 0.55 is dropped more often
than kept at z = 2. The default stays 2 and is never derived from the event count; the
template, the config table and `training.md` (with the table) say to set 1 or `null` below
about 300 converting train clients.
