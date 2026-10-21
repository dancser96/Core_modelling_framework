# Questions for the planning session, round 3
_Updated 2026-10-21 after the SDS's second round of answers. Only open questions are listed;
answered ones are recorded in `docs/decisions.md` (D-082–D-102) and the owner docs. Each question
carries Claude's proposed default, so "default" is enough as an answer. Findings behind the
questions: `holistic_review.md`. Dates: `timeline_proposal.md`. New numbers continue from Q289._

**Who:** SDS, LDS, or both.

## A. For the SDS and the LDS

| # | Question | Default | Who |
|---|---|---|---|
| Q217 | Which December do we mean: an internal pre-release of the walking skeleton plus one deepening round (scenario A), or release 1.0 with both integrations (scenario B)? D-097 already puts the definition of done at release 1.0, which implies A | A; release 1.0 around mid-February 2027 | both |
| Q218 | OD-01: accept the depth-per-component draft in `timeline_proposal.md` (three columns: M2, December pre-release, release 1.0), with edits? | Yes | both |
| Q223 | M3 priorities (2.5 weeks, Nov 25 – Dec 11): which candidates make the cut? | Sampling comparison (OD-17), EDA deep dives, Feature Checks stability, calibration + categoricals, evaluation core views, monitoring drift | both |
| Q260 | OD-07 / OD-08: one production version per key; append-only event records (UUID, model key, version, hashes, framework version) with derived tables; a tiny `production.json` per model key at an adapter-resolved path as the one record every pinned version reads; shadow challengers in Phase 3 | Yes | both |
| Q262 | Monitoring in December: health and drift tables with flags (thin+), realised performance thin, impact stub; "deep" drift in M4. Categorical drift measure: PSI on level shares with `__other__` | Yes | both |
| Q263 | Report size: self-contained HTML with plotly.js embedded (4–5 MB each, per stage, per run, per entity), or one shared JS file per report folder (smaller, no longer self-contained)? | Self-contained; revisit after the SDS's own test of plotly in the bank's JupyterLab (spike 5) | both |
| Q291 | **Two layers for scores** (OD-18). The retail platform team's table (customer id, product, activity, score, source, refresh date; `inference.md` requirement 4) carries no traceability: no entity, model, run, scoring batch or inference month. Proposal: (1) the framework writes its own scores table, long format and fully traceable (unit id, entity, domain, use case, product, activity, task, score, inference month, scoring batch id, run id, model hash, framework and schema version), shared across versions under D-089; (2) each consumer's table is written from it through a column mapping in the use case's config (rename columns, add constants such as Source from `conf/local/`, pick the date). The retail platform's format is the first mapping and the default for retail propensity use cases; a regression use case, whose score isn't 0–1, maps to its own consumer | Yes | both |
| Q293 | **One shared consumer table.** Every retail propensity use case writes into the same table. Each write must replace only its own slice, never another use case's rows: the crunch lost scores exactly this way (T6, T7). Partition by refresh date, product and activity, and overwrite only the partitions the batch owns? | Yes | both |
| Q295 | **Comparable across products?** One table holding every product's scores invites comparing them per customer (e.g. picking the next best offer). That only works if every score is a calibrated probability on the true scale: the prior shift applied, and the use case's decision set to `probability`, so the calibration step is on (D-049, D-094). Is the table used that way downstream? | Assume yes: retail propensity use cases writing to this table default to `probability` | both |

### Q241. The config and the audit log (OD-10)
**Your framing:** the config is set once Target Factory has run; every later decision is logged in
an audit trail; loading the config plus the log always gives one obvious final input for the
modelling step, from which the other artifacts follow.

**Claude's view: it aligns.** The proposal below follows it, with two clarifications built in: the
data definition can't change through the log (point 4), and the run's identity moves to the
replayed input (point 7).

1. **The config is the intent, fixed after Target Factory.** It holds the data definition (entity,
   sources, eligibility, target spec, observation window, candidates), the stage rules and
   settings, and the business decision. It can be edited freely until Target Factory has built the
   target (or the upstream target column is named); from then on nobody edits it.
2. **The audit log holds every later decision, in order.** It is append-only, one entry per
   decision:
   - a sequence number and the time;
   - who decided: a person (role or user id), or a rule (its step name);
   - the stage and decision point (the inventory in `config.md`);
   - the operation: exclude features, keep features despite a flag, change a setting, sign off
     the feature list, choose a variant, register, promote;
   - the reason (one note per group) and a link to the evidence (report, ledger rows).

   Entries are never edited; a reversal is a new entry.
3. **Replay gives the final input.** Loading means the config plus the log's entries applied in
   order up to a chosen point, validated by the same schema. The result is the resolved config,
   saved as the frozen config with every artifact. "The final input for the modelling step" is the
   replay up to the start of training. A training run records the entry it replayed up to, so its
   input is exactly "config c1 + entries 1–17".
4. **The data definition can't change through the log.** Changing the entity, sources,
   eligibility, target, window or candidates changes the population or the target, so it means a
   new config: a new data-definition hash and fresh EDA and Feature Checks. The log can never
   quietly change what EDA looked at.
5. **Rule decisions are logged too.** Rule outcomes before training (lineage exclusions, check
   flags) are entries made by a rule, so the final input can be read without rerunning anything,
   and a rerun on restated data shows up as a difference against the log. Decisions inside
   training (automated selection drops, the winning family) are outputs of the run: logged for the
   pathway and recorded in the ledger, but not part of the input.
6. **After training, the same trail continues.** The feature sign-off, register and promote are
   entries. A sign-off that rejects a feature appends an exclude, and the retrain replays up to
   that new entry.
7. **Identities.** The config hash and the data-definition hash never change after Target
   Factory. The run's identity uses the hash of the replayed input: `run_id` = replayed-input hash
   + entity + timestamp (amends D-088). In the worked example in `config.md`, step 3 changes: a
   human exclude is an entry, both config hashes stay, and the replayed-input hash changes.
8. **Storage.** One append-only file per instance (JSON lines) next to its artifacts, keyed by the
   data-definition hash. Registering copies the run's slice of the log into the registered bundle,
   where it is immutable. Local logs go with local runs, as today.
9. **Entry points.** One public function records a person's decision from a notebook, and one CLI
   command does the same; stages append rule entries themselves.
10. **What it replaces.** Human keep / exclude lists move from the config to the log (amends
    D-043). Automated filters stay rules in the config (D-058), with their outcomes logged.

**Questions:**
- (a) Adopt this? **Default:** yes; D-043 and D-088 amended, `config.md` and `feature_ledger.md`
  updated. **Who:** both.
- (b) May settings (budgets, thresholds, sampling) also change through the log after Target
  Factory, with a reason, or only feature decisions and sign-offs, so that any settings change is a
  new config? **Default:** settings may change through the log, so the config truly never
  changes. **Who:** LDS.
- (c) Who may write a person's entry: any DS on the use case, or only its owner? **Default:** any
  DS; the sign-off names the person. **Who:** LDS.
- (d) Is a file per instance enough for oversight, or should registered slices also land in a
  queryable table? **Default:** a file now; a table with the registry tables in M4. **Who:** LDS.

### Q254. Client-grouped validation inside training
**The problem.** Training has one row per client per month over the observation window, so with a
6-month window each client appears up to six times. A client's rows are near-copies: holdings and
balances are sticky, and one conversion makes up to `w` consecutive rows positive. FLAML picks
among its trials (model family, hyperparameters) with an internal validation that by default
splits by **rows**. A client's March row then sits in the fit fold and its April row in the scoring
fold. A model that memorises clients (deep trees, many leaves, small leaves) recognises them in the
scoring fold, scores well, and wins.

The test split (unseen clients) and the validation month stay honest, so no reported number is
wrong. The damage is that the wrong model is picked, and its overfitting only shows afterwards as
a large train–test gap.

**Why it is new.** The crunch trained on a single month, so every client appeared once and a row
split was a client split. The multi-month window (D-030) creates the problem.

**What the answer decides, beyond a fallback:**
1. How FLAML picks trials: client-grouped CV, one client-grouped holdout, or row CV.
2. Whether the in-train metric that picks trials resembles the test metric. D-083 lets choices
   weigh train and test metrics, which only makes sense if the in-train choice was itself made on
   unseen clients.
3. Cost: K-fold grouped CV costs K fits per trial; one holdout costs one, so more trials fit the
   same budget.
4. The calibration step's out-of-fold predictions (D-094) and automated selection's importance
   pruning need client-grouped folds too; one fold assignment can serve all three.
5. The same rule carries into the Phase 3 Optuna path.
6. FLAML's `sample=True` (early trials on subsamples) may subsample rows rather than clients:
   unverified, part of spike 1.

**Options:**
- **A. One client-grouped holdout we build**, passed to FLAML as `X_val`, `y_val` (its `fit`
  accepts them). Simple and fast; noisier when the holdout has few positive events.
- **B. FLAML's grouped CV** (`split_type="group"`, `groups=client_id`), if spike 1 shows it works
  with sample weights. Less noisy; K times the cost per trial.
- **C. Row CV, relying on regularisation.** No extra code, but it picks overfit models. Not
  recommended.
- **D. Our own CV loop around FLAML's tuner.** Most control, most code.

**Proposal.** One client-grouped fold assignment (a seeded hash of the client id, like the
train/test split) is the single source of every split inside train: FLAML's trial selection, the
calibration step's out-of-fold predictions, and automated selection. FLAML receives it through B
if spike 1 passes, otherwise through A built from the same assignment; never row-level. Measure the
size of the effect once on the synthetic data (row-CV AUC vs grouped-CV AUC vs test AUC) and keep
the numbers in `training.md`.

**Questions:**
- (a) Adopt this? **Default:** yes. **Who:** both.
- (b) Did any of the unit's existing multi-month models handle this, and how? **Default:** none
  known; noted as a lesson either way. **Who:** LDS.

### Q286. How long old framework versions must keep working
**Background.** Each use case pins the framework version it runs with (D-047), and the base image
it starts on lives a year (D-074). A year-old version can therefore run beside new ones, all
reading and writing the same shared tables (registry, scores, monitoring, model cards) and loading
the same kind of model bundles. `CLAUDE.md` §2 says a deprecated path is kept "at least one minor
version". That rule fits some changes and not others:
- **Code changes** (a renamed public function or config field): a use case meets them only when it
  raises its pin, and the migration plus the deprecation warning handle them at that moment. One
  minor version is enough.
- **Shared formats** (rows several versions write and read at the same time, and bundles a newer
  version must load): an old version keeps running for up to a year, so these need a longer
  promise. D-089 already says columns are only added within a major version.
- **Version numbers:** the package is 0.1.0. Under semantic versioning 0.x promises nothing, so the
  promises only start at 1.0.0.

**Proposal:**
1. Code deprecations: one minor version, as today.
2. Config and artifact migrations are cumulative within a major version: any 1.x version loads any
   1.x config or bundle.
3. Shared formats change only additively within a major version (D-089).
4. A major version bump keeps readers for the previous major's formats for at least one image
   lifetime (12 months).
5. 1.0.0 is release 1.0 (D-097). The December pre-release (0.x) writes only to sandpit and local
   paths, never to shared production tables, so its rows can be thrown away; shared formats freeze
   from the first row 1.0.0 writes inside the bank.
6. `CLAUDE.md` §2 is reworded to say this.

**Questions:**
- (a) Adopt this? **Default:** yes. **Who:** both.
- (b) Can a use case take a newer framework version within its image's year (a newer package in
  the same image), or only by moving to a newer image (OD-04)? **Default:** unknown; ask the
  platform team in the Q232 session. **Who:** LDS.

## B. Facts from outside the code

| # | Question | Default | Who |
|---|---|---|---|
| Q232 | Who are the contacts, and can three 30-minute sessions be booked by Nov 6: platform / MLOps (change-request steps, registry owner OD-23, permissions OD-06, Sonar quality gate, scheduling); the feature store team (OD-26); the data observability team (OD-13)? | The LDS books them; the SDS leads them with a one-page question list each | LDS |
| Q235 | Sonar and CI: what are the quality gates (coverage threshold, duplication, complexity, security rules)? They size M4's test work | Ask the platform team; assume 80% coverage until answered | LDS |
| Q237 | Real-data facts still open: are source months ever restated after loading (the `CLAUDE.md` §4.10 assumption); when does the monthly mart land; do storage permissions differ per entity (OD-06)? | The LDS answers from experience; verified inside the bank at M5-lite | LDS |
| Q238 | Change requests: how long from "promote" to a deployed model in practice (days? weeks?), and can a first `deploy` inside the bank realistically run in January? | The LDS estimates; D-055's inside step goes to M4 | LDS |
| Q294 | **Column meanings in the retail platform's table:** (a) `Date_Refreshed`: the date the scoring ran, or the month the features are as of (our inference month)? (b) `Activity`: what does "Build" mean (acquisition, balance build-up, cross-sell?), and which kinds of target map to Retention, Activation and Build? (c) `Score`: what decimal precision? (d) `CustomerID`: is it the same pseudonymised id the feature marts carry, or is a mapping needed? (e) `Source`: one fixed value per producing team? | (a) the run date, with the inference month kept in the framework's own table; (b) to be answered; (c) decimal(10,8); (d) the same id; (e) a constant from `conf/local/` | SDS |

## C. For the SDS

| # | Question | Default | Who |
|---|---|---|---|
| Q267 | Shapes for later tasks (D-081): reserve nullable `task` and `score_component` columns, and store metrics as long rows keyed by metric name in the registry, the card and monitoring. With the consumer format now known (Q291), these columns belong in the framework's own scores table, not in the consumer's | Yes, in the framework's own table only | SDS |
| Q290 | "PSB": the synthetic spec groups Affluent and Mass as "PSB" (D-056, `test_harness.md`). If "PSB" is the bank's own segment name, it breaks the no-identifiers rule. Rename it in the spec and docs to a neutral label (e.g. "mass market")? | Rename, if it is the bank's term | SDS |
| Q292 | **Product and activity as explicit fields** in the use-case config (e.g. `product: Credit Cards`, `activity: Activation`), never parsed from the use case's name; the values a consumer accepts are listed in `conf/local/` and validated at load | Yes | SDS |

### Q268. One keep fraction across months (and what "offset" means)
**The offset.** When negatives are downsampled, the model trains on a much higher positive rate
than the real one, so its scores come out too high by a known factor. The prior-shift offset is one
number subtracted from every score's log-odds to undo that factor. Example: at a true rate of 0.2%,
keeping every positive and 5% of negatives trains on about 4% positives, so scores are about 20
times too high; subtracting `log(20) ≈ 3.0` from each score's log-odds puts them back on the true
scale. The ranking doesn't change, only the level (`glossary.md` → Calibration). Every "offset" in
these questions means this number.

**The question.** "Row-level negative sampling, stratified by month" can be set up two ways:
- **One keep fraction for every month** (e.g. keep 5% of each month's negatives). Months with more
  conversions keep their higher rate in the sample, so the model still sees the seasonal
  differences, and one offset (`log(1/0.05)`) undoes the sampling exactly for any month, including
  the inference month.
- **A fixed ratio per month** (e.g. 20 negatives per positive in each month). Every month then has
  the same sampled rate (about 5%), so the model can't see that some months convert more, and the
  true offset differs per month. At inference there is no month-specific offset to apply, so the
  level is off by however much the inference month differs from the average.

**Default:** one keep fraction across months, chosen from the row budget.

### Q269. Recency weighting in Phase 2?
**Your question:** is it actually important in this phase? **Claude's answer: no.**
- It is already off by default.
- The window is short (6 months by default, D-091), so the oldest rows are half a year old.
- Drift is handled by retraining and monitoring.
- It interacts with the offset: recency weights change the effective training rate, so the offset
  would partly undo them.
- The window ablation answers the underlying question ("do older months hurt?") without it.

**Question:** drop recency weighting from Phase 2 (remove `dataset.md` requirement 7) and revisit
only if the window ablation shows that older months hurt? **Default:** yes.

### Q272. Upstream targets: does Feature Checks cover it?
**Your question:** if Feature Checks is designed properly, this shouldn't be a requirement, should
it? **Half right**, because the question had two parts:
- **The time-alignment check is part of designing Feature Checks properly.** It belongs in the step
  catalogue, not in a separate requirement. It compares each feature's power to predict the target
  forward with its power to "predict" the same event backward, in the months before the
  observation month. A legitimate feature does both about equally; a column shifted forward or
  built from the future does only the forward one. It is called out because the step list as
  written (near-perfect separators, dominance, missingness) would miss the traps that look strong
  but not perfect: the moderate leak (AUC 0.877 against the oracle's 0.842) and the column shifted
  a month ahead.
- **The lineage list can't come from Feature Checks.** Only the DS knows which upstream columns an
  upstream team used to build a target. Without that list, a leaking column is caught only if the
  screen happens to flag it.

**Question:** add the time-alignment check to Feature Checks' step catalogue, and for upstream
targets keep the lineage list optional but warn in the report's choices block when it is empty?
**Default:** yes.

### Q275. Weight-aware statistics for sampling option 3
**The three sampling options** (`dataset.md` requirement 6), all train-only and after the client
split:
1. **Row-level negative sampling, stratified by month:** keep every positive row and a fraction of
   the negative rows in each month. For rare binary targets; M2's default.
2. **Client-level random sampling:** keep all rows of a random sample of clients. For common
   targets and regression.
3. **Outcome-stratified client sampling with weights:** keep every client who converts at least
   once in the window, with all their months, plus a random sample of the other clients. Each
   sampled non-converter gets a weight of 1 / (its sampling fraction), so the weighted sample
   matches the population.

**The question.** Option 3 over-represents converters' months, including their quiet months before
converting. Every statistic computed on the sample that selects or fits something must use the
weights, or it sees a distorted population: the univariate AUC floor, importance pruning, the
calibration step, and FLAML's internal metric. Mark in the per-task spec which statistics take the
weights, before option 3 is offered? **Default:** yes, as part of the sampling research (the
literature round after M2.1, then M3).

### Q276. Refit checks
**What a refit is** (D-052): after a model is evaluated and accepted, it is retrained with the same
features and hyperparameters on more data. There are two kinds:
- **All clients:** the same observation window, with train and test clients together. The
  validation month is still later and unseen, so this refit *can* be scored on it.
- **Extended window ("all data"):** the window moves forward to the latest months whose labels have
  matured, usually including the validation month. You're right: then no month is left to
  validate on, in the sandpit or in production.

**Why it needs checks.** With the extended window, the model that gets registered, or that scores
in production, is one no metric ever touched; its card can only show the parent's evaluation. The
checks are what remains possible without labels:
1. the card labels every metric as "the parent's evaluation, not this model";
2. before registering or scoring, the parent and the refit both score the latest month, and their
   scores are compared: rank correlation, overlap of the top-N lists, and the shift of the score
   distribution (PSI). Close agreement means the parent's evaluation carries over; a large
   difference stops the refit until a person has looked;
3. the refit inherits the parent's encoder levels (new levels go to `__other__` and are counted),
   so it sees the data the same way.

**Question:** adopt these three for every refit, and also score the all-clients kind on the
validation month? **Default:** yes.

### Q281. Which functions are "public"?
**Your question:** do we need to talk about APIs when it's shipped as a package? **Yes, in a narrow
sense only.** A package's API is simply the functions people import. Because use cases pin
versions and upgrade at their own pace (D-047), `CLAUDE.md` §2 promises not to break public
functions between versions; everything else may change freely. The Public API table in
`architecture.md` is where that promise is written down. Without a rule, every function a guided
notebook calls becomes public in practice, since users copy the notebooks, and renaming it later
breaks their copies. No service API is involved.

**Question:** public = the stage functions, `run`, the CLI commands, the config schema, and any
function the shipped notebooks call; everything else gets a leading underscore; a small test
checks the notebooks' calls against the table? **Default:** yes.

### Q284. An inventory of versioned artifacts
**The problem.** The framework will write about fifteen kinds of files and tables: the frozen
config, the decision audit log, EDA artifacts, the Feature Checks log, the feature ledger, target
lineage, the model bundle, training metadata, evaluation results, the model card, the drift
reference, registry records, scores, manifests, monitoring tables and labels for scored months.
Several are read later by a *different* framework version:
- EDA artifacts written under 0.3 are read by training under 0.4 (the due-diligence gate, D-031);
- a bundle registered under 1.0 is loaded by inference under 1.2;
- scores written by many versions are read by monitoring.

Each such artifact needs two things: a version field saying which format it is in, and a rule for
what a newer reader does with an older file (migrate it on read; read it as is, because the format
only grows; or refuse it). Today 3 of the ~15 have a named version field (config, bundle, ledger).

**Question:** at M2.1, add one table to `architecture.md` (artifact → owner doc → version field
name → the stage that writes it → the stages that read it, possibly under another version → the
compatibility rule), and give every artifact its version field from its first version?
**Default:** yes.

### Q285. Detecting a model that scores differently after an upgrade
**The problem.** A production model trained under framework 1.0 with lightgbm 4.6 is still scoring
a year later. The use case raises its pin, and the new base image has a newer lightgbm. The saved
model file loads without error, but a changed default (e.g. in how missing values are routed)
makes it predict slightly differently. Nothing today notices: scores shift silently, and
monitoring would read it as drift.

**Proposal.** When a bundle is saved, build a small fixed "probe" table (about 200 synthetic rows,
built deterministically from the model's own encoder levels and the numeric ranges in its drift
reference, so no client data), score it, and store those predictions in the bundle. Every load
scores the probe again and compares; any difference fails loud with "this model predicts
differently in this environment: retrain it or keep the old version". Add one test that loads a
bundle written by the previous framework version. Cost: about 50 lines, and milliseconds per load.

**Question:** build the probe with the bundle (M2.3), and the cross-version test once a previous
version exists to test against (M4)? **Default:** yes.
