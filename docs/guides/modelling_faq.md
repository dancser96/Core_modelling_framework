# Training and Evaluation: questions and answers

**What this is:** short answers to the questions a data scientist or a reviewer asks about the
Modelling stage (M2.3: Training and Evaluation), and the stage's research note in full. Each
answer gives the reason and names the doc that owns the detail; when the two disagree, the owner
is right. **Status:** Training and Evaluation are built (major steps 2 and 3, 2026-11-16/17). The
Expert DS's joint review of steps 2 and 3 is still open, so an answer may change with it.

**Related:** [training](../components/training.md) · [evaluation](../components/evaluation.md) ·
[model bundle](../components/model_bundle.md) (the run folder, the bundle, the calibration's
formulas, the hashes) · [reporting](../components/reporting.md) (the views, the model card) · [monitoring](../components/monitoring.md) (the drift reference) ·
[config](../components/config.md#the-modelling-fields-stage-3) · [feature
ledger](../components/feature_ledger.md) · [EDA and Feature Checks
FAQ](eda_fc_faq.md) · `notebooks/00_modelling_helper.ipynb` (each artifact's grain and columns,
beside the function that wrote it)

## Runs, stages and reruns

**Why are Training and Evaluation two stages?**
Training is where labels choose features, a configuration and a calibration, so it reads the train
split only and never sees a test or validation row (`CLAUDE.md` §4.4). Evaluation fits and chooses
nothing (§4.5), so it can be rerun on any trained run with today's evaluation settings, without
training again (D-036: every stage runs alone and writes its own artifacts). `run --stages
training evaluation` does both; a bare `run` runs every built stage.

**What is a run, and where do I see what it did?**
One Training call and its Evaluation, in a numbered folder `<use_case>/06_models/r007/` (D-139: a
person uses three names, the data definition, the run number and later a model version).
`run.json` is written first and never again. `list_runs` gives one row per run (started, family,
features, trials, the headline, trained / evaluated / signed off) and `show_run` prints one run's
record. A refused run takes no number; a folder without `training/` is a crashed run, listed as
incomplete ([model bundle](../components/model_bundle.md) → The run folder).

**Which run does Evaluation take, and can I evaluate an older one?**
By default the latest run with the config's data-definition hash and the same digest of
Training's settings, so changing an evaluation setting or a baseline never orphans a run.
`run="r007"` (CLI `--run r007`) evaluates any run of the same data definition with the current
evaluation settings. A rerun rewrites `evaluation/` whole and never touches `training/`, the
bundle or the per-run ledger, and gives the same tables to the binning's tolerance (the headline
metrics to four digits), not bit for bit: the score bins' edges come from an approximate quantile
that moves inside its rank error with the partition layout
([evaluation](../components/evaluation.md) → Finding the run, Score cells).

**EDA was rerun with another setting. Can an older run still be evaluated?**
Yes. Training copies into the run's `stage2/` every candidate's Stage 2 ledger rows and EDA's
cells, edges, bins and levels of the final features. Evaluation, the model card, the sign-off view
and the drift reference read only the run folder and the data (D-139 (b): a run is complete in
itself), and `register` (M2.4) needs that anyway ([training](../components/training.md) → What
Training writes).

**Does the same config give the same model?**
Under a trial budget, on the same machine and library versions: the same trials, configuration,
predictions and `model_hash` (D-094 (d): a trial budget and the seeds repeat the model). CatBoost's
run-specific metadata and LightGBM's thread-count line are left out of the saved files, so the
hash repeats in every family. Under a time budget FLAML picks by measured seconds, and the run
says "reproducible to the recipe, not the model". Across machines it is unverified until the
pre-release run ([training](../components/training.md) → The search, item 12).

## Folds, the search and selection

**Why client folds, and why are the converting clients dealt in turn?**
A client is in up to six periods of the window, so a fold that split its rows would judge a model
on a client it was fitted on (§4.11). For a binary task the dataset deals the converting train
clients to the K folds in turn, so each holds its share: 20 of 100, where a plain hash gives
anything from about 12 to 28. A fold without a positive can then only happen with fewer converting
clients than folds, and Training fails loud on it (D-106: client folds, dealt by the dataset and
given to FLAML as a splitter). One fold assignment serves the search, pruning, the fold models and
the calibration ([training](../components/training.md) → The frame and the folds).

**There are few events. Should I use fewer folds?**
No. Fewer folds train every trial on less data, which biases the estimate down, and buy no
precision: every event is judged out of fold once whatever K is [Kohavi95][Krstajic14]
[Varoquaux18]. Below 100 converting clients or 200 events the log warns and advises
`training.fold_repeats: 3`, a small trial budget, and reading differences between runs against
their intervals; automated tuning adds instability at few events [Riley23]. Copying or weighting
the rare class buys no AUC and damages the probabilities [Goorbergh22][Carriero25].

**Why does FLAML only search, and why is its transformer off?**
The framework's own `fit` trains every model it keeps (pruning, the fold models, the final model)
from the best configuration, so the bundle holds one native booster and a production retrain needs
no FLAML (D-140 (a): FLAML only searches; one rule gives every fit its parameters). Given a
DataFrame, FLAML fills numeric nulls with the median before the folds are cut, so the search would
judge data the saved booster never scores (0.40 apart in probability on a 6,000-row check).
`skip_transform=True` is therefore on for every fit and is no config field (T38, D-094 (a)). Nulls
go to the libraries, which learn where they belong; nothing is imputed
([training](../components/training.md) → The search, items 1 and 6).

**What do the trial budgets mean?**
`training.max_iter` is the run's total: 60 at `autonomous`, 200 at `assisted`, split equally over
the listed families (15 or 50 each for the default four), unless `training.trials` names every
family's count. A trial is one configuration fitted on every fold and judged by its mean fold
loss. Each family has a search of its own because FLAML's own selector starved a family (9 of 60
trials) and ignores the seed (D-140 (b)); inside a family FLAML's local search (CFO) steps out from
FLAML's start, clipped into the bounded ranges. The search view draws the best fold metric so far
against the cumulative seconds, per family: a line still falling at its last trial wants more
trials in the next run. Whether 60 and 200 are enough is open
([training](../components/training.md) → Open questions).

**Why such narrow search ranges?**
At 15 to 50 trials a wide space is noise (one rule of thumb asks 50 to 100 evaluations per
dimension [Bischl23]), so each family searches four or five parameters in ranges taken from the
tools surveyed, every one narrower than FLAML's own [Spaces]; the rest stay at the library's
default (the penalties are worth about 0.003 AUC [Probst19]). With FLAML's unbounded ranges the
search was still climbing at 17 trials and its time was erratic (the research note below). Every
ranged leaf reaches FLAML with its start, since without one FLAML searches nothing (T39). A person
overrides one leaf in `training.search_space` ([training](../components/training.md) → The search,
items 7 and 8).

**Which metric does the search use, and can I change it later?**
The decision's: `log_loss` for a `probability` or `threshold` decision, since the score is used or
cut as a probability and log loss rewards the level as well as the order [Gneiting07]; `roc_auc` for
`ranking` and `top_n`; `rmse` or the declared metric for regression. It is also the headline metric,
declared before any result, so no audit-log entry changes it (§4.3). `training.objective` is a
training setting and may change, which is why the regression metric follows the decision and not
the objective. Average precision is an override for a shallow list with plenty of events, not a
default: no study shows selecting on it gives better lists, and a noisy criterion overfits the
selection [Cawley10][Boyd13][McDermott24] ([training](../components/training.md) → The search,
item 9).

**What does the floor do, and when should I lower it?**
The floor and the cluster rule are the screen: it fits no model and runs before the run number is
taken, so a screen that leaves no feature takes none. The floor drops a feature unless its train
concordance, or its null indicator's, reaches 0.5 + z · SE, with `floor_z: 2` and each SE on
effective train clients: about 0.509 at 3,870 converting clients, 0.533 at 300. The nulls count
because the libraries take them natively and nothing is imputed, so a feature whose being filled
predicts the target is used by the model. Features null on the same rows share one null
indicator, so that pattern clears at most one of them (`represented_by` names it): otherwise one
pattern, such as "fewer than six months on the book" nulling every six-month rollup, would pass
ten features on the synthetic data whatever their values. With few converting clients the floor is high and drops
real but weak features: below about 300, set `floor_z` to 1 or `null` and rely on kept features and
pruning. A univariate floor also drops a feature that only works in interaction [GE03], which
pruning would keep; a `keep` is measured and never dropped. Open: a feature non-monotone on train
is judged on its best-order concordance, which sits 2.5 to 2.8 SE above 0.5 on noise
([training](../components/training.md) → Selection, with the table of drop chances).

**Trees ignore noise. Why select features at all, and what does pruning add?**
Accuracy hardly suffers (0.004 to 0.008 AUC to 390 noise columns [Grinsztajn22]), but search time
grows in a straight line with the features, and noise fills the importance chart and the sign-off
list. Pruning asks whether the model still needs a feature once the others are there: five seeded
noise columns join the frame, LightGBM's fold models rank every feature's out-of-fold contribution
share, and the features doing no better than the best noise column are the candidates to drop. The
pruning model has its own size, set by the frame: 4 leaves, ⌈10 · P / 3⌉ trees for P columns and
three columns a tree, so each column is offered to about ten trees. A model of the search's start
size cannot split every column of a wide frame; with no split on any noise column the threshold is
0 and every unsplit real feature would look like noise, so a best noise share of 0 prunes nothing
and the run warns. With candidates, two more fits, with and without them, each offer every column
to every tree on at most 300 trees and are compared on the out-of-fold loss; any rise undoes the
drops. (At three columns a tree the two frames would draw different columns, and that chance alone
would move the loss.) The comparison judges the candidates as a set: one needed feature keeps them
all, many weak ones go together, and a feature that works only jointly with another is not
reliably caught, so a `keep` is the answer there ([training](../components/training.md) →
Selection, with the measurements). The AutoML tools do this in place of a univariate floor [AG-FS][mljar][probatus]. Every drop
is a row of the per-run ledger, never an audit-log entry, since the next run recomputes its own
(D-125: the audit log holds what shapes a run's input).

**Why are class weights refused?**
`scale_pos_weight`, `is_unbalance`, `class_weight`, `class_weights` and `auto_class_weights` count a
positive several times, so the model believes positives more common than they are and its
probabilities come out too high [LGBM-P][XGB-T]. The calibration undoes exactly one change of the
class balance, the declared sampling with its one keep fraction (§4.12); a weight would be a second
change it does not know about. For a rare target declare `sampling: negative_downsampling`, which
the prior-shift offset undoes.

**Why is the out-of-fold metric called optimistic?**
Selection, the search and the calibration were chosen or fitted on the same folds, so the fold
metric has been selected on. The test split is the first honest number for those choices; weak
evidence puts the gap at about 0.018 AUC at 300 train events with 150 noise candidates.
`training.json` and the report say so ([training](../components/training.md) → The honesty
notes).

## Calibration

**Why is the calibrator fitted out of fold inside train?**
Fitted on the final model's own training rows it would learn from scores of rows the model has
seen; fitted on test or validation it would use rows the evaluation must keep untouched (§4.7). So
K fold models at the chosen configuration each score the fold they did not see, the calibrator is
fitted on those out-of-fold margins, and the fold models are discarded
([training](../components/training.md) → Fold models and calibration).

**How does the prior-shift offset relate to sampling?**
Under `negative_downsampling` the model trains at the sampled rate, so its scores come out too
high; the offset, logit(true rate) − logit(sampled rate), added to every margin puts them back on
the true scale and leaves the order untouched (D-049: the offset whenever sampling happened, the
calibration step by the decision). It is exact for every period under one keep fraction for the
whole train split [KZ01][He14], which is why sampling uses one (§4.12; D-117: sampling only when
the config declares it). It is zero without sampling and under `client_sample`, by rule, and always
zero for regression. The calibrator is fitted on margins at the sampled rate and the offset is
added after it, so Training's level metrics leave the offset out ([model
bundle](../components/model_bundle.md) → The calibration and the output columns).

**Why does the method follow the decision and not the evidence?**
`platt` for a `probability` decision, `none` otherwise; a person may set `platt`, `beta` or `none`.
Following the decision fixes the steps before any result and makes a production retrain run its
parent's steps; choosing by evidence would need a noise threshold nobody can source. The evidence
is still stored: every binary run keeps the out-of-fold log loss of all three methods. Each is in
sample for its own calibrator, so a gap in the fourth decimal is no reason to switch, and
post-hoc calibration often does not improve a boosted model at all [CalArena26][Manokhin26].

**Why Platt on the margin, beta, and no isotonic?**
Platt on the margin is a logistic regression of the label on the log-odds; its family holds "leave
as is" (a = 1, b = 0). On the probability it cannot, and it degraded strong tabular models
[Kull17][CalArena26]. Beta, with three parameters and kept increasing, is the second method
[Kull17]. Isotonic ties scores, so a top-N cut becomes arbitrary, and outputs exact 0 and 1, which
breaks the offset. Every calibration map is increasing, so the rank metrics are the same on `score`
and `score_raw`.

**What is the level factor for regression, and why is it not winsorised?**
Tweedie and Poisson predict on a log scale and lose the average when the boosting stops early
(Tweedie predicted 4–5% low, measured) [Wuthrich20]. One factor, the total observed over the total
predicted out of fold, repairs it; it is stored with its client-bootstrap interval and the number
of rows that hold half the target's total, and the log warns when the interval is wider than ±5%.
Winsorising made the level worse than no correction (0.90 against 1.00, measured): it drops the
part of the total in the tail [McNeil97]. Squared error keeps the level by itself and gets `none`;
under a very heavy tail the mean itself is a poor target [Manning98], and a capped target is a
Target Factory item in the backlog ([training](../components/training.md) → Fold models and
calibration, item 7).

## Evaluation's numbers

**What may test and validation decide?**
Nothing inside the stages: Training never reads them, and Evaluation only measures (the single
feature comes from train concordances, the skill scores' base from the train rate, the calibration
slope is a measurement). A person may choose between runs on test, as `compare_runs` does, never on
validation, which stays the one honest number (D-083: any choice among variants weighs train and
test only). Once test has chosen, the test-to-validation gap mixes overfitting with selection, and
people's feature decisions in EDA and Feature Checks have seen test labels (D-030); the report
states both ([evaluation](../components/evaluation.md) → What the report states).

**Why are the metrics computed from score cells?**
Test and validation are scored inside Spark and no metric reads a collected or sampled row (§4.8),
so every metric reads one aggregate per scorer: rows and sums per part, period, score bin and
target bin, as EDA's statistics read its counts table (D-141 (b): the driver holds test rows only
for the two seeded samples of the explanation views). A bootstrap replicate is the same cells
weighted by its client weights, so 200 replicates of every metric cost seconds. The losses and
errors are exact per-row sums; the rank metrics, slices, curves and calibration slope carry the
binning's tolerance. The score bins grow finer towards the top, where average precision and the
top slices are read, and a second quantile pass cuts the tail: average precision from cells is
within 0.0015 of the row value from a 0.05% to a 5% base rate, where bins of 0.1% read up to 61%
too low (the grids and their counts: [evaluation](../components/evaluation.md) → Score cells).

**What are the baselines, and which should I declare?**
`decision.baselines`, by default `[population_base_rate, single_feature]` (D-009, D-141 (e)):
- `population_base_rate`: the unsampled train rate (regression: the train mean); it ranks nothing
  (AUC 0.5 by construction) and anchors lift and the skill scores.
- `single_feature`: the numeric or ordered categorical with the highest train concordance in the
  per-run ledger, used as the score in train's direction. It answers "does the model beat its best
  column alone?", is chosen without a test row, and a null takes the lowest score.
- `{previous_model: <column>}`: a score column of a source, judged like the model; declare it when
  the model replaces one in use.
- `{historic_predicted_rate: <number or column>}`: a number is one rate in use, compared on its
  level; a column is a historic prediction per client, judged like a previous model.

The base rate alone ranks nothing, which is why the sources add a simple, transparent baseline
[MLTS17][DC-SMC]. A cell a baseline cannot fill (the log loss of a raw feature) reads "not
available: reason" ([evaluation](../components/evaluation.md) → Baselines).

**Where is the line that says the model passed?**
There is none. A pass or fail line nobody acts on is decoration and teaches readers to skip the
summary; the summary and the card show the model against each baseline at the decision's metric,
with intervals, and the person who approves a promotion judges (D-032: no gate built; Phase 3 asks
once whether a metric gate returns). Likewise there is no "too good to be true" warning: Feature
Checks screens single features, and the report shows the numbers (D-141 (i)).

**How do I read the intervals?**
Each is the middle 95% of the metric over 200 client-bootstrap replicates
(`evaluation.intervals`). Each client gets one Poisson(1) weight per replicate from a hash of its
id, the replicate number and a fixed salt, so its rows move together: a client sits in up to six
test periods, so a formula counting rows would be too narrow, and none exists for lift, average
precision or the skill scores [Najmi15][TFMA] (D-141 (c)). The model is held fixed: the interval
says how far the number moves with another draw of clients, not how another training would score.
A metric undefined in any replicate has no interval rather than a narrower one. Two scorers'
intervals overlapping is no test of their difference; for two runs, read `compare_runs`' interval
of the difference ([evaluation](../components/evaluation.md) → Intervals).

**Why is the headline pooled, but the slices cut per period?**
A reader looks for one curve and one headline per part, so they use all of a part's rows. A list
is cut inside one period, as a campaign scores one period, and a converting client is positive in
up to `w` rows; so slices are cut inside each period and then added up, and a `top_n` is a share of
the period's whole eligible population (D-098: curves and headline pooled, the table and slices
per period). A pooled AUC also counts pairs across periods that no list uses [JanesPepe09][Matos26]:
when it and the mean of the per-period AUCs differ beyond their intervals, the summary says the base
rate moved inside the window and the per-period values are the ones to read
([evaluation](../components/evaluation.md) → Pooled and per period, Slices).

**The score's level drifts from period to period. Why is it not corrected?**
Observed to expected is shown per period on test and on validation, with no correction: an
intercept update would need labels that arrive `w` periods late, and the true rate the offset uses
is the train split's, pooled over the window (D-098). Scores read as conditional on staying through
the target window: a row with a null target is in no metric (Evaluation scores the test part's
null-target rows for the drift reference only, and drops them at the validation period).

**What is "validation on test clients only"?**
The validation period holds every eligible client of both splits, and train clients' earlier
periods were fitted on. View 17 measures the validation period once more on test-split clients
alone: unseen clients at an unseen period ([reporting](../components/reporting.md) → The model
results report).

**Can I compare average precision across use cases?**
No. Its floor is the base rate, so 0.10 is strong at a 1% rate and weak at 20%; the report shows
the base rate beside it.

## Explanations, the sign-off and comparing runs

**What can the explanation views say, and what can they not?**
They describe the model, not the world, and nothing is chosen on them (§4.4). The contributions are
the families' own, equal to SHAP's tree explainer on the pinned versions, on the margin's scale
(log-odds; the log scale for Tweedie and Poisson), from 5,000 seeded test rows plus three waterfall
rows. Correlated features split credit arbitrarily, so permutation importance permutes a redundancy
cluster as one and flags where its ranks disagree with the contributions'. It runs on its own
seeded test sample of up to 50,000 rows, since 5,000 rows hold too few events at a rare rate, and
reads "Not available" below `strata.min_events` events in it, for a target of one value, or for a
deviance without a log link. The effects view sets
the mean contribution per EDA group beside EDA's lift: lift is the feature alone, a contribution is
given the other features, so the two may differ for a correlated feature. Partial dependence moves
one feature while the others stay, which creates unlikely rows when features are correlated; the 50
ICE lines show whether rows respond alike ([evaluation](../components/evaluation.md) → The
explanation tables).

**Why are the SHAP-style charts drawn without `shap`?**
The libraries' own contributions equal SHAP's tree explainer exactly on reloaded boosters, while
declared categoricals break several of `shap`'s modes. The bar, the beeswarm, the waterfall and the
dependence scatter are drawn in plotly with `shap`'s colours, one implementation for the notebook
and the report (D-141 (f); [reporting](../components/reporting.md) → The explanation charts).

**What is the sign-off, and why must a person give it?**
A person must be able to defend every feature in a model, so one gate after training and before
`register` asks a person to sign off the final feature list, at every automation level; an LLM never
passes it (§4.13; D-031: no model without data knowledge, and the human feature sign-off). The
sign-off view is train-only (out-of-fold contributions, the model's direction beside EDA's, the
held and excluded features with their reasons), so it can be read right after training.
`decide --sign-off --run r007 --reason …` records the run, the feature signature and the list; it
covers every run of the data definition with that signature, because a person defends features,
not hyperparameters. Rejecting a feature is an `exclude` entry and a retrain; `register`'s check is
M2.4's ([training](../components/training.md) → The sign-off view).

**What does `compare_runs` compare, and what does it refuse?**
It answers "did it help?" after a person keeps a feature or changes a budget (D-141 (h)). The two
runs' stored scores are joined on the rows both scored; on the test part each directed metric gets
its difference, the interval of the replicates' differences (the weights are shared) and `better`,
`worse` or `no clear difference`. Validation's numbers stand side by side under "reported, never
chosen on", with no difference (D-083). Beside them: the features that entered or left, the largest
moves in importance rank, and each run's budget and seconds per family. It refuses runs of two data
definitions or another entity, a run not evaluated, shared rows whose target or client split
differ, and a part without a shared row; a loss of two different objectives is shown, never
differenced ([evaluation](../components/evaluation.md) → `compare_runs`).

**What is the drift reference for?**
It is Monitoring's yardstick: what a production model's inputs and scores should look like, keyed
by `model_hash` (D-054: monitoring's inputs are produced upstream, by Evaluation). It takes the
final features' shares per period from the run's copy of EDA's counts, which cover every eligible
row and not the training sample, and the test scores' distribution in ten quantile groups, from
every eligible test row scored, null targets included. Test scores rather than train ones,
because train scores are in sample and spread more than unseen clients' will. Each feature's shares are a valid input to the PSI function
([monitoring](../components/monitoring.md) → The drift reference).

## The research note

What the stage's research found while the design was settled, 2026-11-11 to 2026-11-13, kept whole.
It records findings as they stood then; where the build settled a point, the owner docs state the
outcome. The measurements ran in throwaway scripts on the pinned versions, which were not kept.
Spikes 1–3 (2026-11-11) settled the group split, the three round-trip formats with CatBoost as
`.cbm`, the train frame in a seeded random client order, and Arrow always on.

### 2026-11-11: the first survey

Ten pieces: the crunch inventory, the package's seams, what the other docs promised, the synthetic
data and its oracle, two fact checks on the pinned versions, and four surveys with sources.

**Measured on the pinned versions** (flaml 2.7.0, lightgbm 4.6.0, xgboost 3.2.0, catboost 1.2.8,
shap 0.50.0, scikit-learn 1.8.0):
- **FLAML median-imputes numeric nulls** when given a DataFrame, before any learner sees the data
  (`flaml/automl/data.py`, a `SimpleImputer(strategy="median")` fitted on the whole frame). It also
  drops constant columns and moves category columns first. On 6,000 rows with 5% nulls the saved
  booster scoring the raw frame differed from `automl.predict` by up to 0.40 in probability. With
  `skip_transform=True`, or a numpy array, the difference is 0. This corrected D-094 (a) and
  `environment.md`, and is T38.
- **A search under a trial budget repeats exactly:** the same trials, best configuration and
  predictions, for one family and for three, at 1 or 2 threads, with and without CPU load. Under a
  time budget it does not (the next learner is chosen from measured seconds). With no time budget
  FLAML always evaluates by cross-validation, so its `sample` option never runs.
- **The default search starves a family.** Of 60 trials: lgbm 26, xgboost 9, catboost 25, with
  CatBoost taking 107 of 117 seconds. `learner_selector="roundrobin"` gave exactly 20 / 20 / 20.
- **CatBoost inside FLAML** holds out the last min(10%, 1,000) rows by position for early stopping
  at every fit, the final one included, and the tree count it reaches is not in `best_config`.
- **After a cross-validated search `automl.model` is refitted on every row;** lgbm and xgboost
  train exactly the tuned `n_estimators`, with no early stopping. Refitting from the estimator's
  own parameters reproduces it bit for bit for lgbm and xgboost, not for CatBoost.
- **A failed fold metric is hidden:** a fold with no positive under `roc_auc` becomes a loss of
  infinity with a logged warning (read in the source).
- **What a loader must pin:** LightGBM accepts columns in the wrong order silently (predictions off
  by up to 0.92) and shifts with float32 input; a reloaded XGBoost booster uses every tree unless
  given the range; CatBoost writes `catboost_info/` into the working directory.
- **CatBoost's `.cbm` bytes differ on every run** (a GUID, a finish time, a parameter dump).
  Deleting five metadata keys before saving gives identical hashes across runs and thread counts.
  XGBoost's files are byte-identical; LightGBM's differ only in a `num_threads` line.
- **Predictions were bit-identical across 1, 2 and 4 threads** for all three families on this Mac.
  Across machines: unverified.
- **The libraries' own contribution outputs equal SHAP's tree explainer exactly**, on reloaded
  boosters, for all three families, in 1–4 seconds per 5,000 rows. Declaring categoricals to the
  libraries breaks several SHAP modes and makes the families treat unseen levels differently;
  integer codes passed as numbers break nothing.
- **Time:** at 100,000 rows × 50 columns under 5-fold client folds, a trial took 1–8 s for lgbm,
  1–2 s for xgboost and up to 80 s for CatBoost; peak memory about 0.5 GB.

**The crunch** (D-037: M2 is never less than the crunch) pickled the whole `AutoML` object, had no
test split, computed importance on the out-of-time month and sent features back on it, and only
echoed the declared metric (AUC was always computed). Worth keeping, and in no doc at the time:
`score_raw` beside `score`, a rank cross-check between two importance methods, error bars on
importance, loading an earlier run, the end-of-notebook checklist.

**The package's seams, before the build.** No `run_id` was computed and nothing built
`06_models/`. The `sign_off` entry could carry neither features nor a run, and had no writer. A
`run` entry that listed the validation period made every later `resolve_config` fail. The modelling
frames carried no client folds, no feature kinds and no strata columns. The per-task spec had no
entry for metrics, baselines, calibration or selection. `automation_level` changed no stage's
behaviour. Each is built or fixed since ([model bundle](../components/model_bundle.md),
[training](../components/training.md), [evaluation](../components/evaluation.md)).

**The docs disagreed** on five points, each settled since: the calibration default (D-094 said only
for `probability`, the schema `platt` for every decision and task; now it follows the decision,
D-049); whether moving the validation period reruns EDA (it does, [config](../components/config.md));
`recipe_hash` (it holds the encoder levels, fitted from train, yet "a retrain keeps it"; now the
levels are frozen in the recipe and a retrain keeps them, D-139 (c)); whether automated selection
and the calibration chain were M2.3 or M3/M4 (both built in M2.3); `__missing__` against `null` as
the name of a missing level (an unordered categorical's missing value has its own code, shown as
`null`, [model bundle](../components/model_bundle.md) → The encoder).

**Best practice:**
- The prior-shift offset is the standard correction and exact for every period under one keep
  fraction [KZ01][He14]. Its reported failures concern random forests and poorly fitted base models
  used without a learned calibrator [Phelps24].
- Platt scaling belongs on the margin (log-odds). On the probability it cannot represent "leave as
  is" and degraded strong tabular models [Kull17][CalArena26]. Post-hoc calibration often does not
  improve a boosted model at all [CalArena26][Manokhin26]. Isotonic creates ties and outputs of
  exactly 0 or 1.
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
- Integer codes as numbers were the weakest encoding for boosting in one benchmark [Pargent22]; a
  second benchmark found the ranking of encoders unstable [Matteucci23].
- Hand-written model-card sections decay, generated facts stay complete [Liang24].

**The synthetic data** (canonical, 100k clients): the card use case gives Training 123 features
(111 numeric, 12 categoricals of at most 10 levels) on about 257,000 train rows with about 3,870
converting clients; the term deposit 141 features and about 1,550 converting clients. The oracle's
AUC on the use-case population is 0.844 (card) and 0.744 (term deposit) on the window, 0.848 and
0.751 on the validation period. Two standard errors around it: 0.012 / 0.022 on canonical, 0.028 /
0.049 on `dev`, 0.054 / 0.10 on `unit`. The oracle's mean probability is 2.6% below the observed
rate for the term deposit and about 5% above for the card on `dev`. Three strong honest features
(`income`, `onboarding_channel`, `subsegment`) were held then, because the stored audit log ended in
a revert; notebook 03 now ends with their `keep` recorded.

### 2026-11-12: two fact checks, two measurements, two surveys, a plot prototype

**Measured on the pinned versions:**
- **Round robin is nothing more than one independent search per family, taking turns.** A joint
  search of 30 trials over the three families gave, per family, exactly the configurations and
  losses of three separate 10-trial searches. No setting gives a family a minimum number of trials
  under FLAML's default selector, which also ignores the seed (it draws families with a fixed
  generator).
- **FLAML's optimiser (CFO) is a local search, not Bayesian.** It starts from a cheap
  configuration, steps in a random direction, tries the opposite direction when that fails, and
  shrinks the step when neither helps. BlendSearch (`hpo_method="bs"`) adds Optuna's TPE on top; it
  needs Optuna, which was not installed on the Mac, so it is untested. `"optuna"` as a method fails
  in 2.7.0.
- **Every family starts from a deliberately tiny model** (lgbm: 4 trees, 4 leaves; xgboost the
  same; catboost at a learning rate of 0.1). In a 25-trial lgbm search on a small frame the tree
  count reached 60 at trial 8 and 130 at trial 12, the leaves never passed 16, and two of the first
  five trials repeated earlier ones. A start can be set per family (`starting_points`, or
  `init_value` in the search space).
- **`auto_augment` never acts when folds are given by client.** It copies the rows of a class under
  20 rows only under FLAML's own row-wise splits, and there the copies land in different folds.
- **Cross-validation or holdout:** without a time budget FLAML always cross-validates; its holdout
  is one random 10% of the clients with a fixed seed. Under cross-validation nothing else is held
  out, CatBoost's wrapper aside.
- **Our folds work as planned:** the fold number as `groups` gives exactly one fold per validation
  part; that, `skip_transform`, a custom range and round robin run together, for binary and for
  regression. A splitter object is also honoured (`PredefinedSplit`, or one of our own: 2 × 5 gave
  ten fits per trial).
- **Categoricals through FLAML:** LightGBM takes `categorical_feature` on integer codes through the
  fit arguments; XGBoost takes `enable_categorical` and `feature_types` as constants in the search
  space (by default FLAML gives XGBoost plain codes); CatBoost's wrapper only declares pandas
  `category` columns.
- **Infinite values:** LightGBM reads ±inf as the largest and smallest value; XGBoost refuses to
  train on them; CatBoost reads +inf as the largest and merges −inf with null. ±1e30 is accepted by
  all three and stays apart from null; the float32 maximum does not (CatBoost). XGBoost and CatBoost
  store float32: above 3.4e38 XGBoost fails and CatBoost turns the value into inf.
- **Declared categoricals from integer codes:** the three round trips stay bit-identical, the
  contributions sum to the margin on reloaded boosters, threads do not matter. LightGBM pools null,
  negative and unseen codes in one branch. XGBoost refuses a negative code at fit, sends an unseen
  code to the "not in the set" side and a null to the learned default side. CatBoost refuses nulls
  and float codes in such a column and gives an unseen level its prior.
- **Declared against numeric codes, a constructed test** (100,000 rows, 3 seeds, one unordered
  feature, not a benchmark): within ±0.006 AUC everywhere; +0.002 for all three at 8 levels;
  LightGBM −0.006 at 300 unpooled levels, CatBoost +0.004. An ordered feature declared as a
  category cost CatBoost 0.002–0.003. CatBoost fits 2–2.4 times slower with a declared categorical.
- **Time against the number of features** (100,000 rows, 300 trees, 10 real features plus noise):
  10 → 400 features multiplied the fit time by 11 (LightGBM), 10 (XGBoost) and 6 (CatBoost), in a
  straight line; a five-fold trial cost 4.6 single fits; scoring and contribution time hardly moved;
  AUC fell by 0.004–0.008; at 400 features the noise held about half of LightGBM's and XGBoost's
  split gain.
- **Scoring inside Spark works locally:** `mapInPandas`, with the model shipped as the bytes of its
  native file, gave margins identical to the driver's for the three families (60,000 rows, PySpark
  3.4.3, pandas 2.2.3, pyarrow 19.0.1). Inside the bank: unverified.
- **The four SHAP plots in plotly:** bar, beeswarm, waterfall and dependence scatter drawn from the
  libraries' own contributions, beside `shap`'s pictures, on a throwaway prototype page. The
  beeswarm at 1,500 clients per feature is 0.5 MB and already has `shap`'s shape. `shap`'s own plots
  also work from a hand-built `Explanation` without an explainer.

**Best practice** (the tools' search ranges are in the table after this list):
- **Nulls in boosted trees:** the libraries' native handling was the best single method at every
  sample size in the largest benchmark; filling with a mean or median was level with it only when a
  "was missing" indicator was added, and clearly worse without; KNN and iterative imputation did not
  beat a constant [PerezLebel22][LeMorvan25][Josse19]. No study of strata medians was found;
  group-specific filling can hurt [Jeanselme22]. AutoGluon and H2O pass nulls to their boosters;
  FLAML, auto-sklearn and PyCaret fill.
- **Categoricals:** LightGBM's docs advise numeric treatment at high cardinality and name
  `min_data_per_group` and `cat_smooth` as guards; scikit-learn's comparison found the encodings
  comparable with a slight edge for native handling at low cardinality; no source tests ordered
  codes for ordered features, but a tree split uses order alone
  [LGBM-A][SK-cat][Pargent22][Matteucci23].
- **Few events:** no source recommends fewer folds; fewer folds bias the estimate downwards and the
  sources recommend stratifying and repeating [Kohavi95][Krstajic14][Varoquaux18]. Tree ensembles
  need far more events per variable than logistic regression, and automated tuning adds instability
  at few events [vdPloeg14][Riley23]. Copying or weighting the rare class buys no AUC and damages
  probabilities [Goorbergh22][Carriero25][Elor22].
- **Irrelevant features:** accuracy holds up [Grinsztajn22][Cherepanova23], less so at few events
  (0.792 → 0.777 AUC from 10 to 200 features at about 230 events, a toy run); histogram building
  costs rows × features [Ke17].
- **Search ranges:** every tool surveyed searches far narrower ranges than FLAML's, on five to eight
  dimensions, and all but FLAML set the tree count by early stopping under a cap. Good defaults hold
  two thirds of what tuning XGBoost can win (0.043 AUC against package defaults, 0.014 against
  tuned defaults) [Probst19]; CatBoost's defaults are the strongest and LightGBM gains the most from
  tuning [TabRepo24]; tuning gains flatten by about 200 configurations [TabArena25]. No source ties a
  bound to the number of events; LightAutoML sets the learning rate and tree count from the row
  count.
- **Overtuning:** in about one case in ten the tuned configuration generalised worse than the
  default; five-fold cross-validation reduces it against a holdout and repeats reduce it further;
  CatBoost and XGBoost overtune more than a linear model [Schneider25].
- **Optimisers:** Bayesian optimisation beats random search at about 130 evaluations (not shown on
  boosted trees) [Turner21]; FLAML's local search alone did well on LightGBM and worse on XGBoost,
  BlendSearch at least as well as either [BlendSearch21]. Nothing compares them at 17–67 trials.
  Only fixed-order tools (H2O) give every family a set number of models.
- **The metric to search on:** log loss is a proper scoring rule and rewards the level as well as
  the order; AUC ignores the level [Gneiting07]. No study shows that selecting on average precision
  gives better top-N lists; it is noisy at few positives and "not generally better under imbalance"
  [Boyd13][McDermott24]. Tool defaults split: mljar log loss, H2O ranks on AUC and stops on log
  loss, TabArena and FLAML AUC.
- **Regression of amounts with zeros:** squared error and the Tweedie and Poisson deviances aim at
  the mean, the absolute error at the median [Gneiting11]; Tweedie with a variance power between 1
  and 2 has the zero mass and the skew [Yang18]; a gamma objective cannot take zeros; a log-link
  model stopped early loses the average, repaired by one multiplicative factor [Wuthrich20]. All
  three libraries have Tweedie.
- **Pooled against per-period AUC:** a pooled AUC over k periods is made of within-period pairs
  and, for about (k − 1) / k of them, cross-period pairs that no decision makes; the formal treatment
  is the covariate-adjusted ROC [JanesPepe09]. Evaluation tools show one overall metric plus slices,
  none a within-slice weighted AUC.

The tools' search ranges ([Spaces], [Probst19], [Grinsztajn22]; L is a log scale). The ranges the
framework chose are in [training](../components/training.md) → The search, item 7.

| Parameter | The sources' ranges | FLAML's own |
|---|---|---|
| lgbm `learning_rate` | L 0.005–0.1, 0.005–0.2, 0.01–0.3 | L 0.001–1 |
| lgbm `n_estimators` | early stopping under a cap of 1,000–10,000 | L 4–32,768, no early stopping |
| lgbm `num_leaves` | 16–96, 16–255, L 2–200 | L 4–32,768 |
| lgbm `min_child_samples` | 2–60, L 1–64, 5–100; the LightGBM guide: "hundreds" on large data | L 2–129 |
| lgbm `colsample_bytree` | 0.4–1, 0.5–1, 0.75–1 | 0.01–1 |
| xgboost `learning_rate` | L 0.005–0.1, 0.005–0.2, 0.01–0.3 | L 0.001–1 |
| xgboost `n_estimators` | early stopping under a cap | L 4–32,768 |
| xgboost `max_leaves` (leaf-wise) | L 8–1,024 [TabArena25] | L 4–32,768 |
| xgboost `max_depth` (depth-wise) | 3–10, 4–10, 1–11; best found 6–14 [Probst19] | 1–15 |
| xgboost `min_child_weight` | 1–5, L 0.001–5, 1–100, 1–128; best found 1.3–7 [Probst19] | L 0.001–128 |
| xgboost `colsample_bytree` | 0.5–1; best found 0.42–0.86 [Probst19] | 0.01–1 |
| catboost `learning_rate` | L 0.005–0.1, 0.005–0.2, 0.01–0.3 | L 0.005–0.2 |
| catboost `n_estimators` | early stopping | fixed 8,192, early stopping |
| catboost `depth` | 4–8, 5–8; the CatBoost guide: 4–10 | not tuned (6) |
| catboost `l2_leaf_reg` | 1–5, L 0.0001–5, L 0.5–30 | not tuned |

### 2026-11-12: the cross-component review, two fact checks and a survey

**Measured on the pinned versions:**
- **`skip_transform` for regression:** on 6,000 rows with 5% nulls, FLAML's prediction equals the
  library's estimator on the raw frame exactly with it on, for the three families; with it off they
  differ by 5.7 to 16.1 in the target's units.
- **Monotone constraints hold** on real values in all three libraries (no violation in 300 rows ×
  50 grid values), after a save and reload too, and the contributions still sum to the margin.
  LightGBM's `advanced` method broke the constraint (28 of 300 rows; 11–20 wrong steps on three
  seeds); `basic` (the default) and `intermediate` held.
- **The form of a constraint differs per library, and mistakes fail silently.** LightGBM takes a
  list, a tuple or a comma string, and silently drops the first entry of a bracketed string;
  XGBoost takes a tuple, a bracketed string or a dict by name, rejects a list and pads a short
  tuple; CatBoost takes a list, a bracketed string or a dict and rejects a tuple.
- **A constraint on a categorical:** LightGBM aborts the Python process (no exception); XGBoost
  accepts it and ignores it; CatBoost raises.
- **A null under a constraint:** LightGBM and XGBoost leave the null branch free (the null's margin
  sat inside the row's range). CatBoost puts a null at the low end (`nan_mode=Min`), so on a feature
  with 10% nulls a correct constraint cost it 0.011 AUC (0.8539 → 0.8427) and nothing without
  nulls.
- **Through FLAML** a constraint passes as a constant in the search space for all four learner
  names, each in its library's form; it cannot pass as a fit argument. The final models obey it,
  and a refit from the estimator's own parameters is bit-identical for lgbm and both XGBoost
  variants (CatBoost under the rule that searches its tree count).
- **The price of a constraint, constructed example:** correct constraints +0.002 AUC; a wrong one on
  a U-shaped feature −0.033.
- **`xgb_limitdepth`** is XGBoost growing level by level to a searched depth (1–15 in FLAML, from 6);
  `xgboost` in FLAML grows leaf by leaf with no depth limit. Both give the same estimator class, the
  same JSON file and loader, and a bit-identical refit. In one 20-trial run from the same start the
  depth-wise variant reached a fold loss of 0.4436 in 89 s, the leaf-wise one 0.4466 in 165 s (one
  run, one dataset).
- **A start can be set exactly:** `init_value` in the search space (or `starting_points`) makes
  trial 1 the given configuration, up to float rounding of the learning rate.

**Best practice:**
- **A level correction under a heavy tail.** One global factor (total observed over total
  predicted) is exactly as unstable as the sample mean of the target. In a simulation with a perfect
  model, its 5th–95th percentile range was 0.91–1.14 at a tail index of 1.5 and 10,000 rows,
  0.50–1.50 at 1.1, and within ±3% from an index of 2. Capping the target at its 99.5th percentile
  made the factor tight and biased it down (median 0.85 at an index of 1.5), unless the capped excess
  is added back, which is the actuarial practice of capping large losses and loading them
  [McNeil97]. No study of the factor under heavy tails was found; shrinking it or only reporting it
  is unstudied. A squared-error model keeps the average in sample by construction; a log-link model
  stopped early does not [Denuit21]. Corrections per prediction band exist (isotonic
  recalibration, a local GLM) [WuthrichZiegel24][Denuit21]. Below a tail index of about 2 the mean
  itself is a poor target; people model a capped amount, the log amount with a correction per
  group, or a quantile [Manning98].
- **Monotone constraints in banks:** used so that each feature's effect runs one way and can be
  defended; directions come from domain knowledge and are checked for a wrong sign; the price was
  under 0.2% AUC on large credit datasets and 2–3% on small ones with many constraints [Koklev25];
  constraints pull individual predictions toward the mean [Alonso25]. The guarantee holds for real
  values with everything else fixed; no regulator text naming monotone constraints was found.

**The cross-component review** found no reason to rethink. It found five choices that would cause
rework if made late (what a run keeps from Stage 2, `compare_runs` and the validation period, where
the regression metric comes from, where an ordered categorical's order is declared, and gates),
about twenty details the plan could default, seven places where settled answers contradicted each
other (each resolved by one of those), and the doc sentences the design changed, which the spec
edited in place.

**Two more measurements** (read from the measurement's output files: the agent was stopped before it
wrote its report, so whether a refit reproduces a Tweedie model exactly was not confirmed then):
- **Where the search starts** (70,000 rows × 60 features, 3.5% positive, five-fold, 67 trials, two
  seeds, LightGBM and leaf-wise XGBoost; fold log loss, lower is better; each cell seed 1 / seed 2).
  Starting from an ordinary model (300 trees, 31 leaves) instead of FLAML's low-cost start, inside
  the same bounded ranges, improved the fold log loss by 0.0001–0.0004 and cost four to five times
  the seconds; for equal seconds the two were level. With FLAML's own unbounded ranges the search
  was still climbing at 17 trials for XGBoost (0.1365 against 0.1340–0.1343) and its time was
  erratic (67 trials took between 232 and 1,279 s). The winning models had 4 to 8 leaves, and the
  holdout differences between the arms were inside the noise.

  | Arm | LightGBM, 17 trials | 67 trials | XGBoost, 17 trials | 67 trials |
  |---|---|---|---|---|
  | FLAML's start, bounded ranges | 0.1343 / 0.1355 in 34 / 30 s | 0.1342 / 0.1352 in 132 / 154 s | 0.1343 / 0.1356 in 33 / 31 s | 0.1343 / 0.1353 in 119 / 155 s |
  | An ordinary start, bounded ranges | 0.1341 / 0.1355 in 139 / 115 s | 0.1340 / 0.1354 in 499 / 374 s | 0.1340 / 0.1354 in 183 / 161 s | 0.1339 / 0.1352 in 520 / 436 s |
  | FLAML's start, FLAML's own ranges | 0.1341 / 0.1353 in 46 / 33 s | 0.1339 / 0.1350 in 232 / 1,279 s | 0.1365 / 0.1364 in 20 / 13 s | 0.1338 / 0.1351 in 628 / 296 s |

- **Tweedie through FLAML** ran for `lgbm`, `xgboost`, `xgb_limitdepth` and `catboost` with the
  objective as constants in the search space and the mean Tweedie deviance as a custom metric.
- **The level of a regression model** (60,000 rows, LightGBM; the ratio of mean prediction to mean
  outcome, 1.00 is right). Squared error kept the level by itself (1.00 in train, out of fold and on
  the holdout). Tweedie predicted 4–5% too low everywhere, and one plain factor from the out-of-fold
  predictions repaired it. A factor from a target winsorised at its 99th percentile made the level
  worse than no correction. On a power-law target (tail index 1.5; half of the total in about 1,000
  rows) the holdout level was 0.73–0.77 whatever was done; the plain factor moved it the right way
  with an interval twice as wide, the winsorised one the wrong way.

  | Target | Objective | No correction | Plain factor (the factor's 95% interval) | Winsorised factor |
  |---|---|---|---|---|
  | Zeros and a long tail | squared error | 1.00 | 1.00 (0.98–1.03) | 0.90 |
  | Zeros and a long tail | Tweedie | 0.96 | 1.00 (1.02–1.08) | 0.91 |
  | The same, power-law tail (index 1.5) | squared error | 0.77 | 0.77 (0.95–1.07) | 0.56 |
  | The same, power-law tail | Tweedie | 0.73 | 0.79 (1.03–1.15) | 0.58 |

### 2026-11-13: LightGBM's constraint methods

One measurement and one read of LightGBM's docs and source.
- **LightGBM's `basic` against `intermediate`.** By the docs, `basic` over-constrains the
  predictions, `intermediate` is much less constraining and "may slow down the training speed very
  slightly", and `advanced` is less constraining again [LGBM-P46]. Measured on two constructed
  datasets (60,000 rows × 20 features, 30% held out, three seeds, 300 trees at a learning rate of
  0.05): (i) 8 constrained features, at 8 and 31 leaves and at 31 leaves with `colsample_bytree`
  0.5; (ii) 16 constrained features with strong interactions between them, at 15, 63 and 255 leaves.
  In the 18 comparisons the holdout log loss of `intermediate` minus that of `basic` ran from
  −0.0006 to +0.0009, mean 0.0000: lower in 11, higher in 7, and higher in all three at 255 leaves.
  Both held the constraint on the grid (200 rows × 40 values, two features), and `intermediate` took
  between 0.1 s less and 0.3 s more per fit.
- **What a correct constraint cost.** Nothing in (i) (`basic` against no constraint: −0.0015 to
  +0.0006). In (ii) it worked as regularisation: at 255 leaves the unconstrained model's log loss was
  0.265–0.283 against 0.224–0.228 with `basic`, at 63 leaves 0.226–0.233 against 0.224–0.228.
- **Through FLAML** (20 trials, five folds, the bounded ranges with a start on each, two data
  seeds): the method passes as a constant in the search space, the final model carries it, holds
  the constraint and refits bit for bit under either method. The best fold loss was 0.2378 and
  0.2270 with `basic`, 0.2388 and 0.2287 with `intermediate`; the search took another path and ended
  at another configuration, which at 20 trials is the search's own noise.
- **`intermediate` falls back to `basic` without an error** when `feature_fraction_bynode`
  (`colsample_bynode`) is not 1, or when training is distributed: LightGBM logs a warning and resets
  the method [LGBM-src]. The plain `feature_fraction` (`colsample_bytree`) is not tested, although
  the warning's text says "feature fraction". Confirmed: with `colsample_bynode=0.8` the two methods
  gave identical predictions on three seeds, and with `colsample_bytree=0.5` they differed.
- **A trap found on the way (T39).** FLAML's `custom_hp` replaces a hyperparameter's whole spec,
  FLAML's own start values included. With every hyperparameter of LightGBM overridden and no
  `init_value` given, a 20-trial search returned an empty best configuration, the library's
  defaults; in a logged 3-trial run every trial had `config: {}` and the same loss. The constants in
  the search space, the monotone constraint among them, were not applied either (175 of 200 rows
  broke it). With an `init_value` on each range the same call searched normally: 20 distinct
  configurations, trial 1 at the start. The start-point measurement above passed starts in every arm
  that set ranges, so its numbers stand.

### Sources

"Not opened" marks a source cited from an abstract, a secondary citation or memory.

- [AG-FS] AutoGluon, `FeatureSelector`,
  https://github.com/autogluon/autogluon/blob/master/core/src/autogluon/core/utils/feature_selection.py
- [Alonso25] Alonso-Robisco, Carbó, de Haro and Guillén 2025, Constrained machine learning models
  for credit default prediction (conference abstract),
  https://crc.business-school.ed.ac.uk/sites/crc/files/2025-11/Constrained-machine-learning-models-for-credit-default-prediction_-who-wins_-and-who-loses-abstract.pdf
- [Bischl23] Bischl et al. 2023, Hyperparameter optimization: foundations, algorithms, best
  practices and open challenges, https://arxiv.org/abs/2107.05847
- [BlendSearch21] Wang, Wu, Huang and Saied 2021, Economic hyperparameter optimization with blended
  search strategy, ICLR, https://mlanthology.org/iclr/2021/wang2021iclr-economic
- [Boyd13] Boyd, Eng and Page 2013, Area under the precision-recall curve: point estimates and
  confidence intervals, https://doi.org/10.1007/978-3-642-40994-3_29 (not opened)
- [CalArena26] Berta, Holzmüller, Bach and Jordan 2026, CalArena, https://arxiv.org/abs/2605.30188
- [Carriero25] Carriero et al. 2025, The harms of class imbalance corrections for machine learning
  based prediction models, https://arxiv.org/abs/2404.19494
- [Cawley10] Cawley and Talbot 2010, On Over-fitting in Model Selection, JMLR,
  https://www.jmlr.org/papers/v11/cawley10a.html
- [Cherepanova23] Cherepanova et al. 2023, A performance-driven benchmark for feature selection in
  tabular deep learning, https://arxiv.org/abs/2311.05877
- [DC-SMC] deepchecks, Simple Model Comparison,
  https://docs.deepchecks.com/stable/tabular/auto_checks/model_evaluation/plot_simple_model_comparison.html
- [Denuit21] Denuit, Charpentier and Trufin 2021, Autocalibration and Tweedie-dominance for
  insurance pricing with machine learning, https://arxiv.org/abs/2103.03635 (not opened)
- [Elor22] Elor and Averbuch-Elor 2022, To SMOTE, or not to SMOTE?, https://arxiv.org/abs/2201.08528
- [GE03] Guyon and Elisseeff 2003, An Introduction to Variable and Feature Selection, JMLR,
  https://jmlr.org/papers/v3/guyon03a.html
- [Gneiting07] Gneiting and Raftery 2007, Strictly proper scoring rules, prediction, and estimation,
  https://doi.org/10.1198/016214506000001437
- [Gneiting11] Gneiting 2011, Making and evaluating point forecasts,
  https://doi.org/10.1198/jasa.2011.r10138 (not opened)
- [Goorbergh22] van den Goorbergh et al. 2022, The harm of class imbalance corrections for risk
  prediction models, https://pmc.ncbi.nlm.nih.gov/articles/PMC9382395
- [Grinsztajn22] Grinsztajn, Oyallon and Varoquaux 2022, Why do tree-based models still outperform
  deep learning on tabular data?, https://arxiv.org/abs/2207.08815
- [He14] He et al. 2014, Practical Lessons from Predicting Clicks on Ads at Facebook,
  https://quinonero.net/Publications/predicting-clicks-facebook.pdf
- [JanesPepe09] Janes and Pepe 2009, the covariate-adjusted ROC curve, Biometrika,
  https://doi.org/10.1093/biomet/asp002 (not opened)
- [Jeanselme22] Jeanselme et al. 2022, Imputation strategies under clinical presence,
  https://arxiv.org/abs/2208.06648 (not opened)
- [Josse19] Josse, Prost, Scornet and Varoquaux 2019, On the consistency of supervised learning with
  missing values, https://arxiv.org/abs/1902.06931 (not opened)
- [Ke17] Ke et al. 2017, LightGBM: a highly efficient gradient boosting decision tree,
  https://proceedings.neurips.cc/paper/2017/file/6449f44a102fde848669bdd9eb6b76fa-Paper.pdf
- [Kohavi95] Kohavi 1995, A study of cross-validation and bootstrap for accuracy estimation and
  model selection, https://ijcai.org/proceedings/1995/147
- [Koklev25] Koklev 2025, on the price of monotonicity in credit models (a single-author preprint),
  https://arxiv.org/abs/2512.17945 (not opened in full)
- [Krstajic14] Krstajic et al. 2014, Cross-validation pitfalls when selecting and assessing
  regression and classification models, https://pmc.ncbi.nlm.nih.gov/articles/PMC3994246/
- [Kull17] Kull, Silva Filho and Flach 2017, Beta calibration, AISTATS,
  https://proceedings.mlr.press/v54/kull17a.html
- [KZ01] King and Zeng 2001, Logistic Regression in Rare Events Data,
  https://gking.harvard.edu/files/0s.pdf
- [LeMorvan25] Le Morvan and Varoquaux 2025, Imputation for prediction: beware of diminishing
  returns, https://arxiv.org/abs/2407.19804
- [LGBM-A] LightGBM, Advanced Topics, https://lightgbm.readthedocs.io/en/latest/Advanced-Topics.html
- [LGBM-P] LightGBM, Parameters, https://lightgbm.readthedocs.io/en/latest/Parameters.html
- [LGBM-P46] LightGBM 4.6.0, Parameters (`monotone_constraints_method`),
  https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html
- [LGBM-src] LightGBM 4.6.0, `Config::CheckParamConflict` in `src/io/config.cpp`,
  https://github.com/microsoft/LightGBM/blob/v4.6.0/src/io/config.cpp
- [Liang24] Liang et al. 2024, an analysis of 32,111 model cards, Nature Machine Intelligence,
  https://arxiv.org/abs/2402.05160
- [Manning98] Manning 1998, The logged dependent variable, heteroscedasticity, and the
  retransformation problem, https://ideas.repec.org/a/eee/jhecon/v17y1998i3p283-295.html (not
  opened)
- [Manokhin26] Manokhin and Grønhaug 2026, When Post-Hoc Calibration Hurts,
  https://proceedings.mlr.press/v329/manokhin26a.html
- [Matos26] Matos, Van Calster, Riley, Dhiman and Collins 2026, Collapsibility of Performance
  Metrics in Clinical Predictive AI (preprint), https://arxiv.org/abs/2608.30568
- [Matteucci23] Matteucci, Arzamasov and Böhm 2023, a benchmark of categorical encoders,
  https://arxiv.org/abs/2307.09191
- [McDermott24] McDermott et al. 2024, A closer look at AUROC and AUPRC under class imbalance,
  https://arxiv.org/abs/2401.06091 (not opened)
- [McNeil97] McNeil 1997, Estimating the tails of loss severity distributions using extreme value
  theory, https://www.casact.org/library/astin/vol27no1/117.pdf (not opened)
- [mljar] mljar-supervised, feature selection,
  https://supervised.mljar.com/features/features_selection/
- [MLTS17] Breck et al. 2017, The ML Test Score, https://research.google/pubs/pub46555/
- [Najmi15] Najmi 2015, An introduction to the Poisson bootstrap,
  https://www.unofficialgoogledatascience.com/2015/08/an-introduction-to-poisson-bootstrap26.html
- [OMS] OpenSSF Model Signing specification v1.0 (hashing a model's files in name order, which
  `model_hash` follows), https://github.com/ossf/model-signing-spec/blob/main/spec/v1.0.md
- [Pargent22] Pargent, Pfisterer, Thomas and Bischl 2022, Regularized target encoding outperforms
  traditional methods, https://arxiv.org/abs/2104.00629
- [PerezLebel22] Perez-Lebel et al. 2022, Benchmarking missing-values approaches for predictive
  models on health databases,
  https://academic.oup.com/gigascience/article/doi/10.1093/gigascience/giac013/6568998
- [Phelps24] Phelps, Lizotte and Woolford 2024, Using Platt's scaling for calibration after
  undersampling, https://arxiv.org/abs/2410.18144
- [probatus] probatus, `ShapRFECV`, https://ing-bank.github.io/probatus/api/feature_elimination.html
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
  TabArena (https://github.com/autogluon/tabarena), TabZilla (https://github.com/naszilla/tabzilla),
  Optuna's LightGBM tuner (https://github.com/optuna/optuna-integration), mljar-supervised
  (https://github.com/mljar/mljar-supervised), LightAutoML (https://github.com/sb-ai-lab/LightAutoML),
  H2O AutoML (https://docs.h2o.ai/h2o/latest-stable/h2o-docs/automl.html)
- [TabArena25] Erickson et al. 2025, TabArena, https://arxiv.org/abs/2506.16791
- [TabRepo24] Salinas and Erickson 2024, TabRepo, https://arxiv.org/abs/2311.02971
- [TFMA] TensorFlow Model Analysis, Poisson bootstrap,
  https://github.com/tensorflow/model-analysis/blob/master/tensorflow_model_analysis/evaluators/poisson_bootstrap.py
- [Turner21] Turner et al. 2021, Bayesian optimization is superior to random search for machine
  learning hyperparameter tuning, https://arxiv.org/abs/2104.10201
- [Varoquaux18] Varoquaux 2018, Cross-validation failure: small sample sizes lead to large error
  bars, https://arxiv.org/abs/1706.07581
- [vdPloeg14] van der Ploeg, Austin and Steyerberg 2014, Modern modelling techniques are data
  hungry, https://pmc.ncbi.nlm.nih.gov/articles/PMC4289553
- [vK14] van Klaveren et al. 2014, Assessing discriminative ability of risk models in clustered
  data, https://pmc.ncbi.nlm.nih.gov/articles/PMC3897966/
- [Wuthrich20] Wüthrich 2020, European Actuarial Journal, on the balance property of models trained
  by early-stopped gradient descent (not opened; the title is not verified)
- [WuthrichZiegel24] Wüthrich and Ziegel 2024, Isotonic recalibration under a low signal-to-noise
  ratio, https://arxiv.org/abs/2301.02692 (not opened)
- [XGB-T] XGBoost, Notes on Parameter Tuning,
  https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html
- [Yang18] Yang, Qian and Zou 2018, a boosted Tweedie compound Poisson model (TDboost),
  https://doi.org/10.1080/07350015.2016.1200981 (not opened)
