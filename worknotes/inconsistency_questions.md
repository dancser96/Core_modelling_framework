# Inconsistency questions
_Written 2026-10-22 for the SDS · from the sweep of decisions vs open decisions vs descriptions that
followed the compaction of `docs/decisions.md` · Q302–Q341, continuing the planning set · each
question has a proposed default; cited decisions are summarised in brackets (D-072 (l)) · an answered
question leaves this file and becomes a D-row, an OD row or a doc fix_

**How to answer.** By number. "Default" accepts the proposal. Block C can be answered as a whole
("C: all defaults") with vetoes by number. Line numbers are as of 2026-10-22 and may drift.

**Fixed directly during the compaction, no question** (all inside rows merged today, where one of
the merged statements was the later, explicit one): D-016 (b) no longer states a path layout that
OD-18 keeps open; D-020 says a use case *may* limit FLAML to one family (D-037 lists three); D-024
says the image sets the default version, which a use case pins and may raise (D-047); D-037 offers
each family only once its round trip is verified (none is yet); D-020 and D-050 no longer claim the
regression per-task spec was designed in M1; the library-upgrade probe moved from the lost D-121 text
into D-051; soft clauses are tagged inline in D-021, D-023 and D-047; D-040's status credits the CDS
with the scope only; `docs/UPDATES.md` no longer cites the deleted OD-07.

## A. Decisions that disagree with each other (your call)

- **Q302. Does production retrain in Phase 2, or does deploy copy the bundle?** D-052 (refit and
  recipe; "Phase 2: production retrains the same recipe and gets different parameters") says
  production trains; D-033 (lifecycle vocabulary: deploy copies the bundle to production paths) and
  OD-27 (retraining in production: whether production has the data and compute is open until M4)
  say it doesn't yet; `lifecycle.md:25-26` states the retrain as settled and `project.md:90` puts it
  under "Later". *Default:* D-033 wins for Phase 2: deploy copies the fitted bundle, which also carries
  the recipe; D-052's Phase 2 clause becomes "when retraining in production arrives (OD-27), it keeps
  the data definition".
- **Q303. Where exactly does pickle stop?** D-051 (bundle and formats: no pickle for what is promoted;
  the sandpit may pickle) versus the bundle being plain data at every tier in `training.md:79`,
  `glossary.md:202`, `CLAUDE.md:146`, and D-037 needing non-pickle round trips in M2. Registered
  models live on sandpit paths (`lifecycle.md:36-37`), so "sandpit" must be defined (local only, or
  local + registered). *Default:* the bundle is non-pickle at every tier (one loader, Evaluation
  scores what is promoted); the sandpit allowance covers only objects outside the bundle (FLAML
  objects, caches, notebook scratch); the glossary gets "sandpit = local and registered tiers".
- **Q304. How many families must round-trip before M2.3 training?** D-037 (target list `lgbm`,
  `xgboost`, `catboost`, each offered once verified) and `timeline_proposal.md:57` ("three families
  round-trip without pickle") versus `roadmap.md:97` ("at least one family verified before M2's
  training, the rest ongoing"); spike 2 is due 11-09. *Default:* at least one verified before M2.3
  starts, three by the end of M2.3 (M2 is never lesser than the crunch, D-037); the roadmap says so.
- **Q305. One sign-off gate or two?** D-031 (data knowledge and the human sign-off) places the
  sign-off both as a stage gate at the end of Feature Checks and "over the model's final feature
  list, sorted by importance", which exists only after training; `glossary.md:86-93` and
  `notebooks/README.md:36-37` mirror both. *Default:* one gate, after training, over the final list at
  every level; Feature Checks ends in a review of flags, not the sign-off. If the assisted level
  should also stop at Feature Checks, D-031 must say what is signed there.
- **Q306. Is the Phase 2 sign-off external or in the audit log?** D-033 ("sign-off is external in
  Phase 2: CR + code review; Phase 3 adds a sign-off log") versus D-125 (decision audit log) and
  `config.md:136-137, 301-302`, where `sign_off`, `register` and `promote` are entries naming the
  person and citing the PR. *Default:* both, stated once: the Phase 2 `promote` entry records who ran
  it and the PR; the Phase 3 sign-off log pulls the PR approvers automatically.
- **Q307. What is the model interface?** D-037 ("one model interface returns scikit-learn-compatible
  models") versus D-100 (a) (plain functions per family: `fit`, `predict`, `describe`), D-094 (b)
  (calibration parameters as plain numbers with the framework's own predict code) and
  `training.md:69` ("never as scikit-learn objects"). *Default:* D-037 drops "scikit-learn-compatible";
  the interface is the function triple per family, and SHAP gets the booster.
- **Q308. D-106's fallback can't trigger in Phase 2.** D-106 (validation inside training: "if the
  group split fails with sample weights, a client-grouped holdout goes in") versus D-117 (sampling:
  Phase 2 trains without sample weights); `timeline_proposal.md:142` already says "a failed group
  split falls back". *Default:* the trigger becomes "if the group split fails at all"; the weights
  clause moves to the wishlist's option 3.
- **Q309. When does sampling happen: rare targets, or only when the rows exceed the budget?** D-117
  carries both readings ("option 1 for rare binary targets" and "no sampling when the training rows
  fit the row budget"); `dataset.md:55` versus `dataset.md:61, 153-154`. *Default:* budget-driven only
  (the LDS dislikes sampling; the prior shift makes it safe, not free); the negatives-per-positive
  ratio is a speed lever a use case sets explicitly; stated once in D-117 and `dataset.md`.
- **Q310. Feature store: three worked examples or one?** D-021 (definition of done) asks for "a use
  case reading from the feature store, from other sources, and from both" and, in the same row, "one
  worked example each". *Default:* one use case config run in three source settings for the feature
  store, one example for data observability; D-021 reworded.
- **Q311. "Full tests before migration" after the December pre-release?** D-014 (tests: full coverage
  + CI/Sonar before migration), `CLAUDE.md:274`, `tests/README.md:23`, `project.md:182` and the
  UPDATES row "Before migration (M5)" versus D-022 (e) (light suite at the pre-release, every
  function and CI/Sonar by release 1.0) and D-021 (the pre-release moves the code into the bank's
  internal repo). Related: the depth level "Full" owns "per-function tests" while release 1.0 is at
  most "deep" everywhere with every function tested. *Default:* "by release 1.0 (M5b)" everywhere;
  tests leave the level definitions and stay a milestone criterion.
- **Q312. D-128 bakes a retail naming rule into the master layer.** D-128 (product and activity parsed
  from `<product>_<activity>`; a name that doesn't split fails at load; the master layer carries both)
  versus D-016 (d) (task-agnostic, nullable reserved columns), D-020 and D-034 (any domain; an SME
  amount model has no "activity") and `CLAUDE.md` §3. *Default:* `product` and `activity` are
  nullable, parsed only when the name splits or set explicitly in config; nothing fails at load.
- **Q313. Is §4 non-negotiable while D-030 keeps a clause soft?** `CLAUDE.md:196` ("non-negotiable")
  and §4.4 fix label checks to train-split clients; D-030 (observation window and splits) marks that
  scope "soft, may be reopened". *Default:* harden D-030 (the LDS accepted the scope); otherwise §4.4
  names its train-split clause as the one soft part.
- **Q314. §4.12 "unless weights undo it" versus the prior shift.** `CLAUDE.md:225` versus D-117
  (Phase 2 keeps every positive row, no weights, undone by the prior-shift offset) and D-082 (row-level
  negative sampling stays unbiased). *Default:* reword the invariant to "unless the prior-shift offset
  or weights undo it (D-049, D-117)".
- **Q315. Are the design docs live or frozen?** `CLAUDE.md:282` ("docs describe the current state,
  updated in the same change") and the component template versus D-072 (j) (design docs frozen at the
  M0 baseline until M4; deviations get a one-line "built differs from design" note); the docs have in
  fact been edited daily (D-125's section in `config.md`, D-094 in `training.md`). *Default:* docs stay
  live and (j) is dropped; if you want the freeze, §8 and the template say where the deviation note
  goes and what "frozen" excludes.
- **Q316. Where does a use case live, and is one file a rule or a goal?** D-006 (extension code in
  "the use case's own repo") assumes a repo per use case while OD-02 (distribution: where a use case
  lives) leans to one repo per entity × domain; D-043 (b) ("one file per use case is the goal, not a
  hard rule") versus D-006 and `CLAUDE.md` §3 ("a use case = one config file"). *Default:* D-006 says
  "the use case's repo (OD-02 decides which)"; keep "one file" as the rule with "split only if it
  bloats" as the stated exception, in D-043 and §3 alike.
- **Q317. Rename `profile` now or at M4?** D-023 (automation levels: the field stays `profile` until
  the levels exist, renamed with a migration at M4) versus OD-25 (the level mapping is written at
  M2.1), the December config spine being "deep" with levels, and D-007 (c) (0.x promises nothing, so
  there is no old config to migrate). *Default:* the field is `automation_level` with values
  `autonomous` / `assisted` from M2.1, no migration; the glossary keeps `profile` only as the retired
  name.
- **Q318. Where does a domain-specific default live?** D-049 (calibration: "retail propensity use cases
  default to the `probability` decision") versus D-034 (domains are configuration, never names in
  code). *Default:* a template comment in the retail example config, not a code default; D-049 says
  "the retail examples default to".

## B. Design points where a doc and a decision disagree

- **Q319. Validation and inference months: config section or run arguments?** `config.md:31, 87`
  put them in the `time:` section; D-088 (identities: the validation and inference months are run
  arguments) and `config.md:370` versus `:388` contradict each other on whether moving them changes
  the config hash. *Default:* D-088 wins: both are CLI / API run arguments (or one named block excluded
  from every hash), said in requirement 8.
- **Q320. Do sweeps show validation per variant before the pick?** `run_modes.md:22` ("compares the
  variants on the same validation set"), `llm_assist.md:18`, `glossary.md:165` versus D-083 (choices
  weigh train and test only; validation never informs a choice). *Default:* the comparison view shows
  train and test per variant; validation only for the picked variant, after the pick is an audit-log
  entry; `run_modes.md`, `dataset.md` and the glossary say so.
- **Q321. A CLI `--profile` override changes the resolved config without a file change or an entry.**
  `run_modes.md:12` versus `config.md:370` (config hash changes only when the file changes) and
  D-023 / OD-25 (a move between levels is recorded). *Default:* drop the override; a level change is a
  config edit or an audit-log entry.
- **Q322. Public API: the audit-log functions and the Spark session.** D-024 (consumption: Public API
  = stage functions, `run`, CLI commands, config schema) omits `record_decision`, `show_decisions`,
  `resolve_config` and the `decide` command that `architecture.md:244-246` and `notebooks/README.md`
  list; `environment.md:54-55` has notebooks call the adapter's session function, which is private.
  *Default:* extend D-024 and `CLAUDE.md` §2 with the audit-log functions; the session function joins
  the Public API too (notebooks need a session).
- **Q323. "Frozen config" means two things.** D-125 (the config is the intent, frozen once Target
  Factory has built the target) versus `glossary.md:107`, `config.md:53, 246`, `architecture.md:90`
  ("the fully resolved config saved with every artifact"); D-043 (c) and D-052 (`recipe_hash` over the
  "frozen config") can be read either way; `feature_ledger.md:57` equates the final list with "the
  frozen config's". Also: Target Factory is optional, so when does the config freeze for an upstream
  target? *Default:* "config" (the intent, immutable after Target Factory or, for an upstream target,
  the first EDA run) and "resolved config" (after replay, saved with every artifact); `recipe_hash`
  names the resolved one; the glossary gets both.
- **Q324. Backlog milestone tags that lag the decisions.** (a) "categorical handling (M4)" versus
  D-094 (a) (the framework encodes categoricals before FLAML; inference calls the booster) and D-051
  (encoder levels in the bundle), both M2 needs; (b) "Evaluation ... (M4)" with no M2 entry versus
  D-038 (stratified reporting mandatory in Phase 2) and D-100 (b) (the compatibility dict is M2
  shape); (c) notebooks "M2 thin, M4 deep" versus D-022 (e) (guidance written in M3). *Default:* split
  (a) into M2 encoder / M4 richer handling; add an M2 line to (b); add M3 to (c).
- **Q325. Target Factory's other rule families: M3 or M4?** D-091 (M2 defaults: one binary rule family
  in M2, "the other rules in M3") versus `timeline_proposal.md:73` (deep at release 1.0, M4); the
  Phase 2 backlog has no Target Factory and no Inference row. *Default:* the plan wins (M4); D-091
  updated; both backlog rows added.
- **Q326. Window ablation: requirement or nice to have?** `dataset.md:78-79, 172-173` (requirement 10,
  "built once in Phase 2") versus `roadmap.md:63-64` and OD-17 (a nice to have in M4). *Default:*
  demote requirement 10 to "nice to have (M4)".
- **Q327. Do the integrations shape the build or not?** `roadmap.md:86-88` ("the seams are designed
  only when the code moves toward the bank; until then they don't shape the build") versus
  `roadmap.md:100-101` ("the data observability session before M3, since its needs shape the
  monitoring tables") and D-040 (the seam to the data observability framework is part of the M2
  frame). *Default:* the session shapes the monitoring tables (final at the pre-release); only the
  plug-in mechanics wait; reword 86-88.
- **Q328. Phase 2 selection and the train–test gap.** `training.md:52-53` ("importance-based pruning
  inside CV") versus D-106 (no own CV loop in Phase 2; the only in-train folds are calibration's,
  D-094 (b)); `training.md:48-50` (the gap "may penalise a choice among trials") versus D-037 and
  D-106 (the trade-off chart and anything around FLAML's trial selection are Phase 3). *Default:*
  pruning reuses the calibration folds, stated explicitly; in Phase 2 the gap is reported and used
  only by a sweep that picks (D-083); penalising trials is Phase 3.
- **Q329. "Manual" means three things.** `architecture.md:163` (run mode "Manual: guided notebooks"),
  `glossary.md:86-87` and `notebooks/README.md:37` ("manual runs" / "hands-off runs"),
  `feature_checks.md:12-23` ("human / automated mode") versus D-023 (`manual` is a Phase 3 level;
  Phase 2 has `autonomous` and `assisted`). *Default:* run mode → "interactive (notebooks)"; runs and
  modes → the level names; the gate's placement stated per level, pending OD-25.
- **Q330. The optional refit has no Phase 2 use.** D-052 (refit off by default, same recipe) and
  `training.md:85` ("the evaluated model is the one registered") while Phase 2 extends neither clients
  nor window. *Default:* no `refit` command in Phase 2; the shape stays for the production retrain
  (Q302) and the Phase 3 wishlist row is added.
- **Q331. Which stages write reports?** `reporting.md:14` ("Target Factory, Training, Inference and
  the lifecycle steps write artifacts, not reports") versus `config.md:294-299` (evidence cites a
  "training report") and `CLAUDE.md:182` ("each ... writes their own artifacts and report").
  *Default:* `reporting.md` wins; `config.md` cites the evaluation report; §3 says "artifacts and,
  where one exists, a report".
- **Q332. EDA report content under OD-12?** `eda.md:69-70` points its report content at OD-12
  (Evaluation's core views per task). *Default:* widen OD-12 to the EDA and Evaluation reports, since
  summary + core + extended is shared (`reporting.md`).
- **Q333. "The gap separates overfitting from decay."** `evaluation.md:14-15`, `dataset.md:92` versus
  D-083 (once test chooses, the test-vs-validation gap mixes overfitting with selection). *Default:*
  add the caveat: the separation holds for a run nothing was picked on; a sweep's winner states the
  mix.
- **Q334. Horizons and statuses.** OD-08 (registry storage after Phase 2) sits in short-term although
  its Phase 2 part is settled (D-111); OD-12 (core views, needed at M2.3) sits in medium-term; the
  UPDATES status column calls Target Factory, EDA, Feature Checks, Training, Evaluation, Reporting
  and Inference "legacy-only" although each has a design doc and decisions, while Dataset, Lifecycle
  and Monitoring in the same state are "designing"; the adapter is "built (partial)" where `stub` fits.
  *Default:* swap the two OD rows; "designing" for every component with a design doc; the adapter row
  says "stub + shim built".

## C. Docs lagging settled decisions (default: apply the decision)

- **Q335. Profiles → levels, one sweep.** `architecture.md:85`, `config.md:62`, `glossary.md:114`,
  `conf/base/README.md:3` and `README.md:5` still list `quick` / `standard` / `thorough` (no
  `thorough` exists, D-023); "hands-off profiles" and "profile rule" in `CLAUDE.md:187, 228`,
  `architecture.md:61, 185`, `glossary.md:145, 152`, `docs/README.md:46`, `training.md:14, 43, 114`,
  `eda.md:22`, `feature_checks.md:15`, `feature_ledger.md:41`; `project.md:4-5` still promises "a
  monitored production model in days to weeks" (the D-023 claim is a registered candidate). *Default:*
  apply D-023 everywhere, with Q317's field name.
- **Q336. Human decisions still in the config.** `conf/base/README.md:4-6` ("pending OD-10"),
  `lessons.md:69-71`, OD-11's leaning ("read from the frozen config at training time"),
  `feature_ledger.md:57`. *Default:* apply D-125 and D-043 (d): the config holds candidates and rules,
  decisions are audit-log entries the run replayed.
- **Q337. Glossary.** Stale: refit (Phase 3 wording; D-052), `run_id` (config hash + entity +
  timestamp; D-088 uses the resolved-input hash), data definition ("time settings" would pull the
  validation month into the hash; D-088), window ablation ("compared on one validation month";
  D-083), "a model that beats the oracle is leaking" (D-100 (e) adds a two-standard-error tolerance;
  also `test_harness.md:49-50`). Missing: sandpit (Q303), pre-release and release 1.0, run-through,
  the agreement check, product and activity, `hash_version`, `production.json`, registry events, the
  resolved-input hash, `__other__`, the segment short forms of D-041. `notebooks/README.md:27`
  "decision-log entry" → "audit-log entry". *Default:* fix and add.
- **Q338. Lifecycle doc and wishlist.** `lifecycle.md:25-26` states the production retrain as settled
  (Q302); `:36-39` keeps "production at sandpit paths, to be confirmed (OD-06)" although D-033 and
  D-051 assume separate production paths and OD-06 is only the folder layout; `:86-88` keeps an
  MLflow-shaped proposal that D-111 superseded; `:50-51` links a retrain to the previous version
  citing D-111 where D-052's `parent_run_id` applies; `:16` and `config.md:37` speak of register
  "gates" where D-033 names one. The Phase 3 wishlist lacks the refit row D-052, `training.md:93`,
  `dataset.md:81-82` and `architecture.md:138` point at. *Default:* apply the decisions; add the row.
- **Q339. Monitoring.** `monitoring.md:15, 28` and D-040 give the tables `schema_version` only; D-007
  (b) gives every shared-table row `framework_version` too. `monitoring.md:28` adds an HTML report
  per use case and a cross-model view that overlaps the inventory (OD-14). *Default:* add
  `framework_version` (D-007 wins; D-040 reworded); the inventory owns the cross-model view.
- **Q340. Training and dataset wording.** `training.md:20` (requirement 2: "time budget") versus
  D-094 (d) (trial budget by default; "per-learner budgets" unverified for FLAML 2.7);
  `training.md:39-44` (the Phase 3 predefined path listed under Phase 2 requirements);
  `dataset.md:150-152` states the oracle check of option 1's offset as a result while
  `training.md:115-117` still plans it; `config.md:352` and `reporting.md:23` list "modelling path"
  as a Phase 2 decision point (D-020: FLAML only); `environment.md:144` "FLAML is time-budgeted";
  `environment.md:101-102` "CatBoost JSON" versus D-051's `.cbm`; `CLAUDE.md` §5 lists FLAML 2.7 as
  unverified while D-020 and D-094 record verifications (D-051's formats stay unverified).
  *Default:* apply the decisions; mark the oracle check as planned; narrow §5.
- **Q341. OD rows and small open-question leftovers.** OD-25: drop "whether depth stays a separate
  knob" (D-023 answered it); OD-13: drop "until then, quick registry tables" (D-111); OD-06: lift the
  LDS's leaning from `lifecycle.md:36-39` into the row; OD-18: leaning "separate them, the LDS supplies
  the layout"; `project.md:118` says per-entity permissions are open (D-079 and OD-06: the
  platform's); `dataset.md:190` and `target_factory.md:61` list settled points (D-091's default
  window; D-029 (a) features from upstream) as open; `evaluation.md:26` versus `:59` put SHAP in
  extended and in core; `evaluation.md:14-17` doesn't say whether D-091's 50-positive floor applies to
  its per-month view. *Default:* apply; the floor applies.
