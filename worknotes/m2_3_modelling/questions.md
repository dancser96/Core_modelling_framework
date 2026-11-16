# Stage 3 (M2.3 Modelling): design questions (closed), the research note and the settled design
_Opened 2026-11-11 for the EDS · three rounds, all answered by 2026-11-13 · no open question ·
the 68 settled questions with the EDS's answers verbatim, and an index of their outcomes:
`answers.md` · the build plan, written 2026-11-13 and waiting for the EDS's approval: `plan.md`
beside this file (its first major step opens with the spec in the owner docs) · the folder is deleted
when the stage closes_

**Where it stands (2026-11-13).** The design questions are closed: 68 questions and the plan
assumptions A1–A51 are settled and recorded in `answers.md`. This file keeps what the spec and
the plan start from: the research note, the settled design in one table, the doc sentences the
design changes, the tests it needs and the checks left for the build. The build plan is
`plan.md`; nothing is specified in the owner docs or built yet. Where the research note points to a question ("the table is in Q605"), the question
is in `answers.md`.

**The research note below is kept on your word (2026-11-12): it is never pruned, only added to,
and it moves to a lasting doc before this folder is deleted.**

Spikes 1–3 (another chat, 2026-11-11) are taken as settled: the group split, the three round-trip
formats with CatBoost as `.cbm`, the train frame in a seeded random client order, Arrow always on.

## What the research found

Ten pieces: the crunch inventory, the package's seams, what the other docs promise, the synthetic
data and its oracle, two fact checks on the pinned versions, and four surveys with sources.

**Measured on the pinned versions** (flaml 2.7.0, lightgbm 4.6.0, xgboost 3.2.0, catboost 1.2.8,
shap 0.50.0, scikit-learn 1.8.0; throwaway scripts in the session scratchpad):
- **FLAML median-imputes numeric nulls** when it is given a DataFrame, before any learner sees
  the data (`flaml/automl/data.py`, a `SimpleImputer(strategy="median")` fitted on the whole
  frame). It also drops constant columns and moves category columns first. On 6,000 rows with 5%
  nulls the saved booster scoring the raw frame differed from `automl.predict` by up to 0.40 in
  probability. With `skip_transform=True`, or a numpy array, the difference is 0. This
  contradicts D-094 (a) and today's line in `environment.md` (Q603).
- **A search under a trial budget repeats exactly:** same trials, same best configuration, same
  predictions, for one family and for three, at 1 or 2 threads, with and without CPU load. Under
  a time budget it does not (the next learner is chosen from measured seconds). With no time
  budget FLAML always evaluates by cross-validation, so its `sample` option never runs.
- **The default search starves a family.** Of 60 trials: lgbm 26, xgboost 9, catboost 25, with
  CatBoost taking 107 of 117 seconds. `learner_selector="roundrobin"` gave exactly 20 / 20 / 20.
- **CatBoost inside FLAML** holds out the last min(10%, 1,000) rows by position for early stopping
  at every fit, the final one included, and the tree count it reaches is not in `best_config`.
- **After a cross-validated search `automl.model` is refitted on every row;** lgbm and xgboost
  train exactly the tuned `n_estimators`, with no early stopping. Refitting from the estimator's
  own parameters reproduces it bit for bit for lgbm and xgboost, not for CatBoost.
- **A failed fold metric is hidden:** a fold with no positive under `roc_auc` becomes a loss of
  infinity with a logged warning (read in the source).
- **What a loader must pin:** LightGBM accepts columns in the wrong order silently (predictions
  off by up to 0.92) and shifts with float32 input; a reloaded XGBoost booster uses every tree
  unless given the range; CatBoost writes `catboost_info/` into the working directory.
- **CatBoost's `.cbm` bytes differ on every run** (a GUID, a finish time, a parameter dump).
  Deleting five metadata keys before saving gives identical hashes across runs and thread counts.
  XGBoost's files are byte-identical; LightGBM's differ only in a `num_threads` line.
- **Predictions were bit-identical across 1, 2 and 4 threads** for all three families on this
  Mac. Across machines: unverified.
- **The libraries' own contribution outputs equal SHAP's tree explainer exactly**, on reloaded
  boosters, for all three families, in 1–4 seconds per 5,000 rows. Declaring categoricals to the
  libraries breaks several SHAP modes and makes the families treat unseen levels differently;
  integer codes passed as numbers break nothing.
- **Time:** at 100,000 rows × 50 columns under 5-fold client folds, a trial took 1–8 s for lgbm,
  1–2 s for xgboost and up to 80 s for CatBoost; peak memory about 0.5 GB.

**The crunch** (D-037: M2 is never less than the crunch) pickled the whole `AutoML` object, had no
test split, computed importance on the out-of-time month and sent features back on it, and only
echoed the declared metric (AUC was always computed). Worth keeping, and in no doc today:
`score_raw` beside `score`, a rank cross-check between two importance methods, error bars on
importance, loading an earlier run, the end-of-notebook checklist.

**The package's seams.** No `run_id` is computed and nothing builds `06_models/`. The `sign_off`
entry can carry neither features nor a run, and has no writer. A `run` entry that lists the
validation period makes every later `resolve_config` fail. The modelling frames carry no client
folds, no feature kinds and no strata columns. The per-task spec has no entry for metrics,
baselines, calibration or selection. `automation_level` changes no stage's behaviour yet.

**The docs disagree** on five points the answers settle: the calibration default (D-094: only
for `probability`; the schema: `platt` for every decision and task); whether moving the
validation period reruns EDA; `recipe_hash` (it holds the encoder levels, fitted from train, yet
"a retrain keeps it"); whether automated selection and the calibration chain are M2.3 or M3/M4;
`__missing__` against `null` as the name of a missing level.

**Best practice** (sources at the end):
- The prior-shift offset is the standard correction and exact for every period under one keep
  fraction [KZ01][He14]. Its reported failures concern random forests and poorly fitted base
  models used without a learned calibrator [Phelps24].
- Platt scaling belongs on the margin (log-odds). On the probability it cannot represent "leave
  as is" and degraded strong tabular models [Kull17][CalArena26]. Post-hoc calibration often does
  not improve a boosted model at all [CalArena26][Manokhin26]. Isotonic creates ties and outputs
  of exactly 0 or 1.
- Class weights and balancing damage probabilities, by the libraries' own documentation
  [LGBM-P][XGB-T].
- No primary study supports optimising precision at k in a search; noisy selection criteria
  overfit the selection [Cawley10].
- A pooled AUC over periods counts cross-period pairs that no per-period list uses; AUC and the
  calibration slope do not average across groups [Matos26][vK14].
- A client-level Poisson bootstrap on binned scores gives client-aware intervals cheaply
  [Najmi15][TFMA].
- The base-rate baseline has AUC 0.5 by construction; the sources add a simple transparent
  baseline [MLTS17][DC-SMC].
- Boosted trees lose little accuracy to irrelevant features [Grinsztajn22]; none of the AutoML
  tools surveyed uses a univariate floor, they prune by importance against a noise feature
  [AG-FS][mljar][probatus].
- Integer codes as numbers were the weakest encoding for boosting in one benchmark [Pargent22];
  a second benchmark found the ranking of encoders unstable [Matteucci23].
- Hand-written model-card sections decay, generated facts stay complete [Liang24].

**The synthetic data** (canonical, 100k clients): the card use case gives Training 123 features
(111 numeric, 12 categoricals of at most 10 levels) on about 257,000 train rows with about 3,870
converting clients; the term deposit 141 features and about 1,550 converting clients. The
oracle's AUC on the use-case population is 0.844 (card) and 0.744 (term deposit) on the window,
0.848 and 0.751 on the validation period. Two standard errors around it: 0.012 / 0.022 on
canonical, 0.028 / 0.049 on `dev`, 0.054 / 0.10 on `unit`. The oracle's mean probability is 2.6%
below the observed rate for the term deposit and about 5% above for the card on `dev`. Three
strong honest features (`income`, `onboarding_channel`, `subsegment`) are held today, because the
stored audit log ends in a revert.

### Added in round 2 (2026-11-12)

Seven more pieces: two fact checks and two measurements on the pinned versions, two literature
surveys and a plot prototype. Scripts and outputs are in the session scratchpad (`r9/`, `r10a/`,
`r10b/`, `r13/`, `main/`).

**Measured on the pinned versions.**
- **Round robin is nothing more than one independent search per family, taking turns.** A joint
  search of 30 trials over the three families gave, per family, exactly the configurations and
  losses of three separate 10-trial searches. No setting gives a family a minimum number of
  trials under FLAML's default selector, which also ignores the seed (it draws families with a
  fixed generator).
- **FLAML's optimiser (CFO) is a local search, not Bayesian.** It starts from a cheap
  configuration, steps in a random direction, tries the opposite direction when that fails, and
  shrinks the step when neither helps. BlendSearch (`hpo_method="bs"`) adds Optuna's TPE on
  top; it needs Optuna, which is not installed on the Mac, so it is untested. `"optuna"` as a
  method fails in 2.7.0.
- **Every family starts from a deliberately tiny model** (lgbm: 4 trees, 4 leaves; xgboost the
  same; catboost at a learning rate of 0.1). In a 25-trial lgbm search on a small frame the tree
  count reached 60 at trial 8 and 130 at trial 12, the leaves never passed 16, and two of the
  first five trials repeated earlier ones. A start can be set per family (`starting_points`, or
  `init_value` in the search space).
- **`auto_augment` never acts when folds are given by client.** It copies the rows of a class
  under 20 rows only under FLAML's own row-wise splits, and there the copies land in different
  folds.
- **Cross-validation or holdout:** without a time budget FLAML always cross-validates; its
  holdout is one random 10% of the clients with a fixed seed. Under cross-validation nothing
  else is held out, CatBoost's wrapper aside.
- **Our folds work as planned:** the fold number as `groups` gives exactly one fold per
  validation part; that, `skip_transform`, a custom range and round robin run together, for
  binary and for regression. A splitter object is also honoured (`PredefinedSplit`, or one of
  our own: 2 × 5 gave ten fits per trial).
- **Categoricals through FLAML:** LightGBM takes `categorical_feature` on integer codes through
  the fit arguments; XGBoost takes `enable_categorical` and `feature_types` as constants in the
  search space (by default FLAML gives XGBoost plain codes); CatBoost's wrapper only declares
  pandas `category` columns.
- **Infinite values:** LightGBM reads ±inf as the largest and smallest value; XGBoost refuses to
  train on them; CatBoost reads +inf as the largest and merges −inf with null. ±1e30 is accepted
  by all three and stays apart from null; the float32 maximum does not (CatBoost). XGBoost and
  CatBoost store float32: above 3.4e38 XGBoost fails and CatBoost turns the value into inf.
- **Declared categoricals from integer codes:** the three round trips stay bit-identical, the
  contributions sum to the margin on reloaded boosters, threads do not matter. LightGBM pools
  null, negative and unseen codes in one branch. XGBoost refuses a negative code at fit, sends
  an unseen code to the "not in the set" side and a null to the learned default side. CatBoost
  refuses nulls and float codes in such a column and gives an unseen level its prior.
- **Declared against numeric codes, a constructed test** (100,000 rows, 3 seeds, not a
  benchmark): within ±0.006 AUC everywhere; +0.002 for all three at 8 levels; LightGBM −0.006 at
  300 unpooled levels, CatBoost +0.004. An ordered feature declared as a category cost CatBoost
  0.002–0.003. CatBoost fits 2–2.4 times slower with a declared categorical.
- **Time against the number of features** (100,000 rows, 300 trees, 10 real features plus
  noise): 10 → 400 features multiplied the fit time by 11 (LightGBM), 10 (XGBoost) and 6
  (CatBoost), in a straight line; a five-fold trial cost 4.6 single fits; scoring and
  contribution time hardly moved; AUC fell by 0.004–0.008; at 400 features the noise held about
  half of LightGBM's and XGBoost's split gain.
- **Scoring inside Spark works locally:** `mapInPandas`, with the model shipped as the bytes of
  its native file, gave margins identical to the driver's for the three families (60,000 rows,
  PySpark 3.4.3, pandas 2.2.3, pyarrow 19.0.1). Inside the bank: unverified.
- **The four SHAP plots in plotly:** bar, beeswarm, waterfall and dependence scatter drawn from
  the libraries' own contributions, beside `shap`'s pictures, in
  `scratchpad/r13/shap_like_plots.html`. The beeswarm at 1,500 clients per feature is 0.5 MB and
  already has `shap`'s shape. `shap`'s own plots also work from a hand-built `Explanation`
  without an explainer.

**Best practice, round 2** (sources at the end).
- **Nulls in boosted trees:** the libraries' native handling was the best single method at
  every sample size in the largest benchmark; filling with a mean or median was level with it
  only when a "was missing" indicator was added, and clearly worse without; KNN and iterative
  imputation did not beat a constant [PerezLebel22][LeMorvan25][Josse19]. No study of strata
  medians was found; group-specific filling can hurt [Jeanselme22]. AutoGluon and H2O pass
  nulls to their boosters; FLAML, auto-sklearn and PyCaret fill.
- **Categoricals:** LightGBM's docs advise numeric treatment at high cardinality and name
  `min_data_per_group` and `cat_smooth` as guards; scikit-learn's comparison found the encodings
  comparable with a slight edge for native handling at low cardinality; no source tests ordered
  codes for ordered features, but a tree split uses order alone
  [LGBM-A][SK-cat][Pargent22][Matteucci23].
- **Few events:** no source recommends fewer folds; fewer folds bias the estimate downwards and
  the sources recommend stratifying and repeating [Kohavi95][Krstajic14][Varoquaux18]. Tree
  ensembles need far more events per variable than logistic regression, and automated tuning
  adds instability at few events [vdPloeg14][Riley23]. Copying or weighting the rare class buys
  no AUC and damages probabilities [Goorbergh22][Carriero25][Elor22].
- **Irrelevant features:** accuracy holds up [Grinsztajn22][Cherepanova23], less so at few
  events (0.792 → 0.777 AUC from 10 to 200 features at about 230 events, a toy run); histogram
  building costs rows × features [Ke17].
- **Search ranges:** every tool surveyed searches far narrower ranges than FLAML's, on five to
  eight dimensions, and all but FLAML set the tree count by early stopping under a cap; the
  per-parameter table is in Q605. Good defaults hold two thirds of what tuning XGBoost can win
  (0.043 AUC against package defaults, 0.014 against tuned defaults) [Probst19]; CatBoost's
  defaults are the strongest and LightGBM gains the most from tuning [TabRepo24]; tuning gains
  flatten by about 200 configurations [TabArena25]. No source ties a bound to the number of
  events; LightAutoML sets the learning rate and tree count from the row count.
- **Overtuning:** in about one case in ten the tuned configuration generalised worse than the
  default; five-fold cross-validation reduces it against a holdout and repeats reduce it
  further; CatBoost and XGBoost overtune more than a linear model [Schneider25].
- **Optimisers:** Bayesian optimisation beats random search at about 130 evaluations (not shown
  on boosted trees) [Turner21]; FLAML's local search alone did well on LightGBM and worse on
  XGBoost, BlendSearch at least as well as either [BlendSearch21]. Nothing compares them at
  17–67 trials. Only fixed-order tools (H2O) give every family a set number of models.
- **The metric to search on:** log loss is a proper scoring rule and rewards the level as well
  as the order; AUC ignores the level [Gneiting07]. No study shows that selecting on average
  precision gives better top-N lists; it is noisy at few positives and "not generally better
  under imbalance" [Boyd13][McDermott24]. Tool defaults split: mljar log loss, H2O ranks on AUC
  and stops on log loss, TabArena and FLAML AUC.
- **Regression of amounts with zeros:** squared error and the Tweedie and Poisson deviances aim
  at the mean, the absolute error at the median [Gneiting11]; Tweedie with a variance power
  between 1 and 2 has the zero mass and the skew [Yang18]; a gamma objective cannot take zeros;
  a log-link model stopped early loses the average, repaired by one multiplicative factor
  [Wuthrich20]. All three libraries have Tweedie.
- **Pooled against per-period AUC:** a pooled AUC over k periods is made of within-period pairs
  and, for about (k − 1) / k of them, cross-period pairs that no decision makes; the formal
  treatment is the covariate-adjusted ROC [JanesPepe09]. Evaluation tools show one overall
  metric plus slices, none a within-slice weighted AUC.

### Added in round 3 (2026-11-12)

Four more pieces and one check on the main thread: a cross-component review of the settled
design, a fact check of monotone constraints and FLAML's depth-wise XGBoost, a measurement of
the search's starting point and of Tweedie with a level correction, and one literature survey.
Scripts and outputs: the session scratchpad (`r14/`, `r15/`, `main/`).

**Measured on the pinned versions.**
- **`skip_transform` for regression:** on 6,000 rows with 5% nulls, FLAML's prediction equals
  the library's estimator on the raw frame exactly with it on, for the three families; with it
  off they differ by 5.7 to 16.1 in the target's units.
- **Monotone constraints hold** on real values in all three libraries (no violation in 300
  rows × 50 grid values), after a save and reload too, and the contributions still sum to the
  margin. LightGBM's `advanced` method broke the constraint (28 of 300 rows; 11–20 wrong steps
  on three seeds); `basic` (the default) and `intermediate` held.
- **The form of a constraint differs per library, and mistakes fail silently.** LightGBM takes
  a list, a tuple or a comma string, and silently drops the first entry of a bracketed string;
  XGBoost takes a tuple, a bracketed string or a dict by name, rejects a list and pads a short
  tuple; CatBoost takes a list, a bracketed string or a dict and rejects a tuple.
- **A constraint on a categorical:** LightGBM aborts the Python process (no exception);
  XGBoost accepts it and ignores it; CatBoost raises.
- **A null under a constraint:** LightGBM and XGBoost leave the null branch free (the null's
  margin sat inside the row's range). CatBoost puts a null at the low end (`nan_mode=Min`), so
  on a feature with 10% nulls a correct constraint cost it 0.011 AUC (0.8539 → 0.8427) and
  nothing without nulls.
- **Through FLAML** a constraint passes as a constant in the search space for all four learner
  names, each in its library's form; it cannot pass as a fit argument. The final models obey
  it and a refit from the estimator's own parameters is bit-identical for lgbm and both
  XGBoost variants (CatBoost under the settled tree-count rule).
- **The price of a constraint, constructed example:** correct constraints +0.002 AUC; a wrong
  one on a U-shaped feature −0.033.
- **`xgb_limitdepth`** is XGBoost growing level by level to a searched depth (1–15 in FLAML,
  from 6); `xgboost` in FLAML grows leaf by leaf with no depth limit. Both give the same
  estimator class, the same JSON file and loader, and a bit-identical refit. In one 20-trial
  run from the same start the depth-wise variant reached a fold loss of 0.4436 in 89 s, the
  leaf-wise one 0.4466 in 165 s (one run, one dataset).
- **A start can be set exactly:** `init_value` in the search space (or `starting_points`)
  makes trial 1 the given configuration, up to float rounding of the learning rate.

**Best practice, round 3.**
- **A level correction under a heavy tail.** One global factor (total observed over total
  predicted) is exactly as unstable as the sample mean of the target. In a simulation with a
  perfect model, its 5th–95th percentile range was 0.91–1.14 at a tail index of 1.5 and 10,000
  rows, 0.50–1.50 at 1.1, and within ±3% from an index of 2. Capping the target at its 99.5th
  percentile made the factor tight and biased it down (median 0.85 at an index of 1.5), unless
  the capped excess is added back, which is the actuarial practice of capping large losses and
  loading them [McNeil97]. No study of the factor under heavy tails was found; shrinking it or
  only reporting it is unstudied. A squared-error model keeps the average in sample by
  construction; a log-link model stopped early does not [Denuit21]. Corrections per prediction
  band exist (isotonic recalibration, a local GLM) [WuthrichZiegel24][Denuit21]. Below a tail
  index of about 2 the mean itself is a poor target; people model a capped amount, the log
  amount with a correction per group, or a quantile [Manning98].
- **Monotone constraints in banks:** used so that each feature's effect runs one way and can be
  defended; directions come from domain knowledge and are checked for a wrong sign; the price
  was under 0.2% AUC on large credit datasets and 2–3% on small ones with many constraints
  [Koklev25]; constraints pull individual predictions toward the mean [Alonso25]. The guarantee
  holds for real values with everything else fixed; no regulator text naming monotone
  constraints was found.

**The cross-component review** found no reason to rethink. It found five choices that would
cause rework if made late (Q654–Q657 and Q632), about twenty details the plan can default
(A31–A51), seven places where settled answers contradicted each other (each resolved by one of
those), and the list of doc sentences the design changes (kept under "For the spec write-up").

**Two more measurements, round 3** (read from the measurement's output files; the agent was
stopped before it wrote its report, so whether a refit reproduces a Tweedie model exactly is
not confirmed).
- **Where the search starts** (70,000 rows × 60 features, 3.5% positive, five-fold, 67 trials,
  two seeds, LightGBM and leaf-wise XGBoost). Starting from an ordinary model (300 trees, 31
  leaves) instead of FLAML's low-cost start, inside the same bounded ranges, improved the fold
  log loss by 0.0001–0.0004 and cost four to five times the seconds; for equal seconds the two
  were level. With FLAML's own unbounded ranges the search was still climbing at 17 trials for
  XGBoost (0.1365 against 0.1340–0.1343) and its time was erratic (67 trials took between 232
  and 1,279 s). The winning models had 4 to 8 leaves. The table is in Q652.
- **Tweedie through FLAML** ran for `lgbm`, `xgboost`, `xgb_limitdepth` and `catboost` with the
  objective as constants in the search space and the mean Tweedie deviance as a custom metric.
- **The level of a regression model** (60,000 rows, LightGBM; ratio of mean prediction to mean
  outcome). Squared error kept the level by itself (1.00 in train, out of fold and on the
  holdout). Tweedie predicted 4–5% too low everywhere, and one plain factor from the
  out-of-fold predictions repaired it (holdout 0.96 → 1.00; the factor's bootstrap interval
  1.02–1.08). A factor from a target winsorised at its 99th percentile made the level worse
  than no correction (0.90–0.91). On a power-law target (tail index 1.5; half of the total in
  about 1,000 rows) the holdout level was 0.73–0.77 whatever was done; the plain factor moved
  it the right way (0.73 → 0.79) with an interval twice as wide, the winsorised one to 0.56–0.58.
  The table is in Q653.

### Added on 2026-11-13 (with the EDS's round-3 answers)

One measurement on the main thread and one read of LightGBM's docs and source. Scripts and
outputs: the session scratchpad (`r16/`).

- **LightGBM's `basic` against `intermediate`** (the EDS's question on Q650). By the docs,
  `basic` over-constrains the predictions, `intermediate` is much less constraining and "may
  slow down the training speed very slightly", and `advanced` is less constraining again
  [LGBM-P46]. Measured on two constructed datasets (60,000 rows × 20 features, 30% held out,
  three seeds, 300 trees at a learning rate of 0.05): (i) 8 constrained features, at 8 and 31
  leaves and at 31 leaves with `colsample_bytree` 0.5; (ii) 16 constrained features with strong
  interactions between them, at 15, 63 and 255 leaves. In the 18 comparisons the holdout log
  loss of `intermediate` minus that of `basic` ran from −0.0006 to +0.0009, mean 0.0000: lower
  in 11, higher in 7, and higher in all three at 255 leaves. Both held the constraint on the
  grid (200 rows × 40 values, two features), and `intermediate` took between 0.1 s less and
  0.3 s more per fit.
- **What a correct constraint cost.** Nothing in (i) (`basic` against no constraint: −0.0015 to
  +0.0006). In (ii) it worked as regularisation: at 255 leaves the unconstrained model's log
  loss was 0.265–0.283 against 0.224–0.228 with `basic`, at 63 leaves 0.226–0.233 against
  0.224–0.228.
- **Through FLAML** (20 trials, five folds, the bounded ranges with a start on each, two data
  seeds): the method passes as a constant in the search space, the final model carries it,
  holds the constraint and refits bit for bit under either method. The best fold loss was
  0.2378 and 0.2270 with `basic`, 0.2388 and 0.2287 with `intermediate`; the search took
  another path and ended at another configuration, which at 20 trials is the search's own
  noise.
- **`intermediate` falls back to `basic` without an error** when `feature_fraction_bynode`
  (`colsample_bynode`) is not 1, or when training is distributed: LightGBM logs a warning and
  resets the method [LGBM-src]. The plain `feature_fraction` (`colsample_bytree`) is not
  tested, although the warning's text says "feature fraction". Confirmed: with
  `colsample_bynode=0.8` the two methods gave identical predictions on three seeds, and with
  `colsample_bytree=0.5` they differed.
- **A trap found on the way (T39).** FLAML's `custom_hp` replaces a hyperparameter's whole
  spec, FLAML's own start values included. With every hyperparameter of LightGBM overridden
  and no `init_value` given, a 20-trial search returned an empty best configuration, the
  library's defaults; in a logged 3-trial run every trial had `config: {}` and the same loss.
  The constants in the search space, the monotone constraint among them, were not applied
  either (175 of 200 rows broke it). With an `init_value` on each range
  the same call searched normally: 20 distinct configurations, trial 1 at the start. Round 3's
  start-point measurement passed starts in every arm that set ranges, so its numbers stand.

## 0. The settled design: what Stage 3 builds

Every row is settled; the question behind each cell is in the index of `answers.md`.

| Component | M2.3 builds | Left for later |
|---|---|---|
| Frames | client folds (`cv_fold`) balanced on converting clients, with optional repeats; the strata and tag columns for Evaluation; test and validation scored inside Spark | — |
| Encoder | levels frozen from train, rare levels pooled by client count; ordered categoricals as numbers in the order declared under `features.order`, unordered ones declared to the library, with a switch back to codes; ±inf clipped to ±1e30; numeric casts; no imputation | EDA reading the declared order |
| Model families | `lgbm`, `xgboost` (leaf-wise), `xgb_limitdepth` (depth-wise) and `catboost`, all four in the default list: fit, predict, describe, save, load, contributions; round-trip tests; monotone constraints declared per feature (LightGBM's `basic` method), with the wrong-sign warning and the grid check at save | the predefined path (Phase 3) |
| Search | FLAML on our folds, one search per family with its own trial budget (60 trials at `autonomous`, 200 at `assisted`, split equally, or `training.trials` per family), the local search (CFO); bounded, sourced ranges, every leaf passed with its start (T39); the metric from the decision; the trials table with the seconds of every trial | BlendSearch and the trade-off chart (Phase 3); ranges suggested from the data (M3/M4) |
| Selection | the cluster rule, the floor scaled to the standard error, importance pruning against noise columns; every drop in the per-run ledger | — |
| Calibration | fold models → out-of-fold margins → Platt on the margin or beta → the offset; the out-of-fold log loss of `none`, `platt` and `beta` stored; for regression a plain level factor for Tweedie and Poisson, stored with its interval, with a warning when that is wide | fitting at the true rate (M3, by the oracle check); a `cap` on the target rule (backlog) |
| Bundle | the native model file, `bundle.json`, `manifest.json` with one `model_hash`; `recipe_hash`; a self-check at save | a probe at every load (Phase 3) |
| Runs | `r007` run numbers, `run.json`, `list_runs`, `show_run`; a run complete in itself: it keeps its own copy of what it needs from Stage 2 | — |
| Per-run ledger | selection, use in the model, importance, direction, encoder shares, constraints | — |
| Evaluation | stored scores; metrics per period and pooled; slices cut per period; client-bootstrap intervals; the baselines compared in the headline and on the card, with no gates; strata; seventeen views with the SHAP-style four and the search's timings per family; the drift reference; the model card; `compare_runs`, which takes its differences on the test split | the comparison report over many runs, sweeps (M4); a metric gate (a Phase 3 question) |
| Sign-off | the view (train-only evidence), `decide --sign-off`, the entry per feature list | `register`'s check (M2.4) |
| Regression | end to end on the test variant: the objective from the config, the metric from the decision, its metrics and views | an example config (M4) |
| Config | the new `training`, `evaluation` and `features.order` fields; `decision.gate_metric` and `lifecycle.promotion_gate` removed, with a schema bump and a migration; the full table of changes comes with the spec (Q640) | — |
| Public API | `run_training`, `run_evaluation`, `list_runs`, `show_run`, `compare_runs`, `load_bundle`, `score_frame`, the sign-off; `run --stages training evaluation` | — |
| Notebooks | `04_training`, `05_evaluation`, `00_modelling_helper` begun in major step 1 | — |
| Tests | `unit`: the plumbing and the invariants; `dev`: the oracle ceiling, a kept leak detected, the calibration level; every `dev` test listed in the plan with its run time | calibration curves on canonical (M3) |

Deliberately **not** built: class weights or any balancing; isotonic calibration; imputation; a
confusion matrix at 0.5; "too good to be true" warnings; pass or fail gates; an own
cross-validation loop around the tuner (Phase 3, D-106); a refit command in the sandpit
(D-052); `shap` as an import.

**The build's shape (Q645, Q590, Q591).** Three major steps, each ending in the EDS's review:
Foundations, Training, Evaluation. The depth is between thin and deep, as M2.2 was built.
Nothing is cut: when the scope does not fit, the dates move, and the roadmap's dates are set
with the plan. This is about the size of Stage 2 against a six-day sizing for a thin build;
monotone constraints and a fourth family were added in rounds 2 and 3. The plan shows where it
runs past the EDS's target of about 2026-11-20.

## For the spec write-up (from the review and the round-3 answers)

**Doc sentences the settled design changes.** The spec edits each in place.
- `CLAUDE.md` §4.7: "(e.g. Platt or isotonic)" becomes Platt on the margin, or beta.
- `decisions.md`:
  - D-088: `run_id` is the run number; the hashes are fields of `run.json`.
  - D-094 (b), D-049: Platt on the margin or beta, isotonic not offered; the framework's own
    fold models. D-094 (c): one hash over the model file and `bundle.json`.
  - D-098: curves and headline pooled; per period in the table and for the slices.
  - D-054: Evaluation writes the drift reference from EDA's counts.
  - D-037, D-100 (a): six functions per family, the libraries' own contributions, declared
    categoricals, the family list.
  - D-106: our splitter object with balanced, repeatable folds; no `sample=True` ordering.
  - D-125 (c): no `dropped` entries; the per-run ledger records automated drops.
  - D-132 (4): calibration follows the decision, not the level.
  - D-136: runs under `06_models/` are numbered, not kept apart by a hash.
  - D-051: the self-check at save is built in M2.3. D-032: "and the gates" (Q632).
  - D-137: EDA's digest narrowed (A46).
- `training.md`: req. 2 (the triple; `groups`; `sample=True`), req. 5 (the fixed floor), req. 6
  (`__missing__`), req. 8 (isotonic), req. 11 (per-part hash), req. 12 (Training writes the
  drift reference); "The predefined path" loses its monotone bullet; several open questions
  close.
- `evaluation.md`: req. 1 (the metric list), req. 2 (per period first), req. 4 (adds
  `single_feature`), req. 5 (SHAP's tree explainer; core against extended), req. 7 (the
  comparison pairs on validation, Q655); OD-12 closes.
- `config.md`: the layout's `metric`, `univariate_floor`, `min_level_count`,
  `platt | isotonic | none`, the `search_space` leaf, `evaluation.views`, `inference.model`;
  the operation table (`dropped`, `sign_off`); `LOGGABLE_SETTINGS`; the Identities table; the
  worked example (the `run_id` form, and "moving the validation period … EDA and Feature Checks
  don't rerun", which A15 corrects).
- `architecture.md`: the Identities bullets, "Training saves a drift reference", the Public API
  table, the artifact inventory.
- `glossary.md`: run and `run_id`, model hash, calibration step, `__other__`, drift reference,
  housekeeping block, manifest (two kinds), promotion gate.
- `reporting.md`: Level 3 req. 5 (no row-level data in a figure) and chart rule 8; the "only
  events warning" sentence there and in `eda.md`.
- `lifecycle.md`: the two parked questions close; the registry's "run id" needs the model key.
- `inference.md`: req. 1 (`{model key: run_id}`), req. 3 (unseen levels); the broadcast and the
  Spark-or-chunks open questions close.
- `monitoring.md` (the drift reference "saved at training"), `dataset.md` (Evaluation's frames
  are no longer collected whole), `run_modes.md` (the CLI), `roadmap.md` (depth row 3, the
  backlog, the risk row on calibration depth, OD-12).

**Tests the design needs,** beyond round 1's list (Q643): balanced folds; R × K fits per trial;
the ±1e30 clip; the ordered-level contract; unseen codes per family; a monotone constraint
holding on a grid; exact trial counts per family; the `xgb_limitdepth` round trip; Tweedie and
Poisson through the search; beta's refit on a negative coefficient; the mean correction; the
self-check at save; run numbering under a clash and after a deletion; a crashed run's folder;
Evaluation's entry not blocking a move of the validation period; the sign-off by signature; the
class-weight names refused; bootstrap weights shared across runs; scoring in Spark equal to the
driver; the drift reference as the PSI function's input; notebooks 04 and 05 on the public API
only. The plan decides which are `unit` and which are `dev`, and keeps the `dev` list short
(Q643).

**Added by the round-3 answers (2026-11-13).**
- **Gates (Q632).** `decision.gate_metric`, `lifecycle.promotion_gate` and the then-empty
  `lifecycle` section leave `config/schema.py`, `conf/base/TEMPLATE.yml`, the two example
  configs and `tests/conf/`, with a `schema_version` bump, a migration and an old-config test
  (`CLAUDE.md` §2). Docs: `config.md` (the sections table's `decision` and `lifecycle` rows,
  the layout, "the promotion gate metric" among the derived settings, "gates" in the
  automation table), `glossary.md` ("Promotion gate", and "the gates" under the decision),
  `architecture.md` ("the metric, the gates"), D-032 and D-132 ("gates"), `evaluation.md` (the
  Related line's "(gates)" and Level 1's "views needed for gates"), `lifecycle.md`. View 1
  shows the baselines comparison.
- **The family list and the budgets (Q651, A45).** D-037's list; `LEVEL_DEFAULTS` in
  `config/levels.py` (`training.max_iter` 50 → 60 at `autonomous`), the template's comment,
  `config.md` (the layout, the automation table, the `LEVEL_DEFAULTS` line);
  `training.trials` in the layout and among the loggable settings.
- **Monotone constraints (Q650).** `training.monotone` in the layout and among the loggable
  settings; `basic` among LightGBM's fixed parameters; the refusals (a constraint on an
  unordered categorical, the `advanced` method, `intermediate` with `colsample_bynode`).
- **The search's starts (Q652, T39).** `training.md` states that every leaf reaches FLAML with
  its start, and the check after each family's search.
- **The timings (A45).** View 13's contents, `show_run`, the step seconds in `training.json`,
  the budget and seconds columns of `compare_runs`.
- **The roadmap.** The M3/M4 item on ranges and an objective suggested from the data (A30); a
  `cap` on the target rule in the backlog (Q653); the dates, set with the plan (Q591).

**Tests added by the round-3 answers:** every leaf reaching FLAML with a start, trial 1 at the
start and the trials distinct (T39); a config with the gate fields migrating; the equal split
of a budget with a remainder, and `training.trials`; the refusals of Q650.

## To check before or during the build

1. The framework's own fit equals FLAML's model for each family: CatBoost under the settled
   tree-count rule, all families with declared categoricals, and a Tweedie model.
2. FLAML with our splitter object, declared categoricals, a custom range and a monotone
   constraint together (each verified alone or in pairs).
3. The bounded ranges against FLAML's own on `dev`, judged against the oracle; the four
   families' fold loss and seconds reported (Q651).
4. Seconds per family on the canonical card frame, to confirm the level budgets of 60 and
   200 (Q651, A45).
5. Declared categoricals against numeric codes on `dev`, one run each way. The synthetic
   categoricals that reach Training have at most 10 levels, so this says nothing about high
   cardinality.
6. Poisson, the absolute error and Huber through FLAML's search (Tweedie ran).
7. CatBoost's file with its five metadata entries deleted scores identically.
8. The bootstrap's seconds per replicate at the bank's size.
9. scikit-learn 1.8's unpenalised logistic regression, for Platt and beta.
10. Inside the bank: the three model libraries on an executor (A27); the same model on the
    bank's machines; plotly in JupyterLab (spike 5); LightGBM's abort on a constrained
    categorical and CatBoost's null handling under a constraint, on the bank's build.
11. XGBoost's JSON writer under another locale (its docs warn of locale-dependent floats).
12. Security's view of `.cbm` and LightGBM's text model (Q621).
13. A larger trial budget repeats the smaller budget's trials as its first trials, so that
    a main run continues the quick run's search (A45).
14. Only if someone wants `intermediate` as LightGBM's default: one run each way on `dev`.
    The constructed check found no difference (Q650).

## Sources

- [AG-FS] AutoGluon, `FeatureSelector`,
  https://github.com/autogluon/autogluon/blob/master/core/src/autogluon/core/utils/feature_selection.py
- [CalArena26] Berta, Holzmüller, Bach and Jordan 2026, CalArena, https://arxiv.org/abs/2605.30188
- [Cawley10] Cawley and Talbot 2010, On Over-fitting in Model Selection, JMLR,
  https://www.jmlr.org/papers/v11/cawley10a.html
- [DC-SMC] deepchecks, Simple Model Comparison,
  https://docs.deepchecks.com/stable/tabular/auto_checks/model_evaluation/plot_simple_model_comparison.html
- [GE03] Guyon and Elisseeff 2003, An Introduction to Variable and Feature Selection, JMLR,
  https://jmlr.org/papers/v3/guyon03a.html
- [Grinsztajn22] Grinsztajn, Oyallon and Varoquaux 2022, Why do tree-based models still
  outperform deep learning on tabular data?, https://arxiv.org/abs/2207.08815
- [He14] He et al. 2014, Practical Lessons from Predicting Clicks on Ads at Facebook,
  https://quinonero.net/Publications/predicting-clicks-facebook.pdf
- [Kull17] Kull, Silva Filho and Flach 2017, Beta calibration, AISTATS,
  https://proceedings.mlr.press/v54/kull17a.html
- [KZ01] King and Zeng 2001, Logistic Regression in Rare Events Data,
  https://gking.harvard.edu/files/0s.pdf
- [LGBM-P] LightGBM, Parameters, https://lightgbm.readthedocs.io/en/latest/Parameters.html
- [Liang24] Liang et al. 2024, an analysis of 32,111 model cards, Nature Machine Intelligence,
  https://arxiv.org/abs/2402.05160
- [Manokhin26] Manokhin and Grønhaug 2026, When Post-Hoc Calibration Hurts,
  https://proceedings.mlr.press/v329/manokhin26a.html
- [Matos26] Matos, Van Calster, Riley, Dhiman and Collins 2026, Collapsibility of Performance
  Metrics in Clinical Predictive AI (preprint), https://arxiv.org/abs/2608.30568
- [Matteucci23] Matteucci, Arzamasov and Böhm 2023, a benchmark of categorical encoders,
  https://arxiv.org/abs/2307.09191
- [mljar] mljar-supervised, feature selection,
  https://supervised.mljar.com/features/features_selection/
- [MLTS17] Breck et al. 2017, The ML Test Score, https://research.google/pubs/pub46555/
- [Najmi15] Najmi 2015, An introduction to the Poisson bootstrap,
  https://www.unofficialgoogledatascience.com/2015/08/an-introduction-to-poisson-bootstrap26.html
- [OMS] OpenSSF Model Signing specification v1.0,
  https://github.com/ossf/model-signing-spec/blob/main/spec/v1.0.md
- [Pargent22] Pargent, Pfisterer, Thomas and Bischl 2022, Regularized target encoding outperforms
  traditional methods, https://arxiv.org/abs/2104.00629
- [Phelps24] Phelps, Lizotte and Woolford 2024, Using Platt's scaling for calibration after
  undersampling, https://arxiv.org/abs/2410.18144
- [probatus] probatus, `ShapRFECV`, https://ing-bank.github.io/probatus/api/feature_elimination.html
- [TFMA] TensorFlow Model Analysis, Poisson bootstrap,
  https://github.com/tensorflow/model-analysis/blob/master/tensorflow_model_analysis/evaluators/poisson_bootstrap.py
- [vK14] van Klaveren et al. 2014, Assessing discriminative ability of risk models in clustered
  data, https://pmc.ncbi.nlm.nih.gov/articles/PMC3897966/
- [XGB-T] XGBoost, Notes on Parameter Tuning,
  https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html

**Added in round 2.** "Not opened" marks a source the survey cited from an abstract, a secondary
citation or memory.

- [Bischl23] Bischl et al. 2023, Hyperparameter optimization: foundations, algorithms, best
  practices and open challenges, https://arxiv.org/abs/2107.05847
- [BlendSearch21] Wang, Wu, Huang and Saied 2021, Economic hyperparameter optimization with
  blended search strategy, ICLR, https://mlanthology.org/iclr/2021/wang2021iclr-economic
- [Boyd13] Boyd, Eng and Page 2013, Area under the precision-recall curve: point estimates and
  confidence intervals, https://doi.org/10.1007/978-3-642-40994-3_29 (not opened)
- [Carriero25] Carriero et al. 2025, The harms of class imbalance corrections for machine
  learning based prediction models, https://arxiv.org/abs/2404.19494
- [Cherepanova23] Cherepanova et al. 2023, A performance-driven benchmark for feature selection
  in tabular deep learning, https://arxiv.org/abs/2311.05877
- [Elor22] Elor and Averbuch-Elor 2022, To SMOTE, or not to SMOTE?,
  https://arxiv.org/abs/2201.08528
- [Gneiting07] Gneiting and Raftery 2007, Strictly proper scoring rules, prediction, and
  estimation, https://doi.org/10.1198/016214506000001437
- [Gneiting11] Gneiting 2011, Making and evaluating point forecasts,
  https://doi.org/10.1198/jasa.2011.r10138 (not opened)
- [Goorbergh22] van den Goorbergh et al. 2022, The harm of class imbalance corrections for risk
  prediction models, https://pmc.ncbi.nlm.nih.gov/articles/PMC9382395
- [JanesPepe09] Janes and Pepe 2009, the covariate-adjusted ROC curve, Biometrika,
  https://doi.org/10.1093/biomet/asp002 (not opened)
- [Jeanselme22] Jeanselme et al. 2022, Imputation strategies under clinical presence,
  https://arxiv.org/abs/2208.06648 (not opened)
- [Josse19] Josse, Prost, Scornet and Varoquaux 2019, On the consistency of supervised learning
  with missing values, https://arxiv.org/abs/1902.06931 (not opened)
- [Ke17] Ke et al. 2017, LightGBM: a highly efficient gradient boosting decision tree,
  https://proceedings.neurips.cc/paper/2017/file/6449f44a102fde848669bdd9eb6b76fa-Paper.pdf
- [Kohavi95] Kohavi 1995, A study of cross-validation and bootstrap for accuracy estimation and
  model selection, https://ijcai.org/proceedings/1995/147
- [Krstajic14] Krstajic et al. 2014, Cross-validation pitfalls when selecting and assessing
  regression and classification models, https://pmc.ncbi.nlm.nih.gov/articles/PMC3994246/
- [LeMorvan25] Le Morvan and Varoquaux 2025, Imputation for prediction: beware of diminishing
  returns, https://arxiv.org/abs/2407.19804
- [LGBM-A] LightGBM, Advanced Topics, https://lightgbm.readthedocs.io/en/latest/Advanced-Topics.html
- [McDermott24] McDermott et al. 2024, A closer look at AUROC and AUPRC under class imbalance,
  https://arxiv.org/abs/2401.06091 (not opened)
- [PerezLebel22] Perez-Lebel et al. 2022, Benchmarking missing-values approaches for predictive
  models on health databases,
  https://academic.oup.com/gigascience/article/doi/10.1093/gigascience/giac013/6568998
- [Probst19] Probst, Boulesteix and Bischl 2019, Tunability, JMLR,
  https://www.jmlr.org/papers/volume20/18-444/18-444.pdf
- [Riley23] Riley and Collins 2023, Stability of clinical prediction models developed using
  statistical or machine learning methods, https://pmc.ncbi.nlm.nih.gov/articles/PMC10952221/
- [Schneider25] Schneider, Bischl and Feurer 2025, Overtuning in hyperparameter optimization,
  https://arxiv.org/abs/2506.19540
- [SK-cat] scikit-learn, Categorical feature support in gradient boosting,
  https://scikit-learn.org/stable/auto_examples/ensemble/plot_gradient_boosting_categorical.html
- [Spaces] The tools' search spaces, read in their source: AutoGluon
  (https://github.com/autogluon/autogluon/tree/master/tabular/src/autogluon/tabular/models),
  TabArena (https://github.com/autogluon/tabarena), TabZilla
  (https://github.com/naszilla/tabzilla), Optuna's LightGBM tuner
  (https://github.com/optuna/optuna-integration), mljar-supervised
  (https://github.com/mljar/mljar-supervised), LightAutoML
  (https://github.com/sb-ai-lab/LightAutoML), H2O AutoML
  (https://docs.h2o.ai/h2o/latest-stable/h2o-docs/automl.html)
- [TabArena25] Erickson et al. 2025, TabArena, https://arxiv.org/abs/2506.16791
- [TabRepo24] Salinas and Erickson 2024, TabRepo, https://arxiv.org/abs/2311.02971
- [Turner21] Turner et al. 2021, Bayesian optimization is superior to random search for machine
  learning hyperparameter tuning, https://arxiv.org/abs/2104.10201
- [Varoquaux18] Varoquaux 2018, Cross-validation failure: small sample sizes lead to large error
  bars, https://arxiv.org/abs/1706.07581
- [vdPloeg14] van der Ploeg, Austin and Steyerberg 2014, Modern modelling techniques are data
  hungry, https://pmc.ncbi.nlm.nih.gov/articles/PMC4289553
- [Wuthrich20] Wüthrich 2020, European Actuarial Journal, on the balance property of models
  trained by early-stopped gradient descent (not opened; the title is not verified)
- [Yang18] Yang, Qian and Zou 2018, a boosted Tweedie compound Poisson model (TDboost),
  https://doi.org/10.1080/07350015.2016.1200981 (not opened)

**Added in round 3.**

- [Alonso25] Alonso-Robisco, Carbó, de Haro and Guillén 2025, Constrained machine learning models
  for credit default prediction (conference abstract),
  https://crc.business-school.ed.ac.uk/sites/crc/files/2025-11/Constrained-machine-learning-models-for-credit-default-prediction_-who-wins_-and-who-loses-abstract.pdf
- [Denuit21] Denuit, Charpentier and Trufin 2021, Autocalibration and Tweedie-dominance for
  insurance pricing with machine learning, https://arxiv.org/abs/2103.03635 (not opened)
- [Koklev25] Koklev 2025, on the price of monotonicity in credit models (a single-author
  preprint), https://arxiv.org/abs/2512.17945 (not opened in full)
- [Manning98] Manning 1998, The logged dependent variable, heteroscedasticity, and the
  retransformation problem, https://ideas.repec.org/a/eee/jhecon/v17y1998i3p283-295.html (not
  opened)
- [McNeil97] McNeil 1997, Estimating the tails of loss severity distributions using extreme
  value theory, https://www.casact.org/library/astin/vol27no1/117.pdf (not opened)
- [WuthrichZiegel24] Wüthrich and Ziegel 2024, Isotonic recalibration under a low
  signal-to-noise ratio, https://arxiv.org/abs/2301.02692 (not opened)

**Added on 2026-11-13.**

- [LGBM-P46] LightGBM 4.6.0, Parameters (`monotone_constraints_method`),
  https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html
- [LGBM-src] LightGBM 4.6.0, `Config::CheckParamConflict` in `src/io/config.cpp`,
  https://github.com/microsoft/LightGBM/blob/v4.6.0/src/io/config.cpp
- The report LightGBM's docs link for the two newer methods (HAL, hal-02862802) was not opened.
