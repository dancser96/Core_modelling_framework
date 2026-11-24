# Stage 3 major steps 2 and 3 (Training, Evaluation): independent audit

**Verdict:** no leak, no split or time violation and no broken `CLAUDE.md` §4 invariant in either
stage, and binary's numbers agree with scikit-learn. Four things come first: two places write
wrong numbers without saying so (items 1 and 2), and two selection rules drop real signal at the
default settings (items 3 and 4). After them: ten should-fix items, six report and card defects,
a list to design before the 1.0 freeze, what will bite first inside the bank, and the refactors.

**Related:** [`review_guide.md`](review_guide.md) and [`review_guide_3.md`](review_guide_3.md)
(§11 says what they already declare), [`training.md`](../../docs/components/training.md),
[`evaluation.md`](../../docs/components/evaluation.md).

_Written 2026-11-22 on `main` at `38e2ce3`. Nothing in the repo was changed: this file is the
audit's only output, and nothing here is decided._

**How to read it**
- The item numbers are this file's own, so an answer can be "fix 1 to 14, drop 52".
- Code paths are relative to `src/core_modelling/`.
- Each item says how it was checked:
  - **reproduced**: the main thread ran it again and got the same result;
  - **read**: the main thread read the code at that line and the mechanism is there;
  - **agent ran** / **agent read**: the auditing agent's evidence, not checked again;
  - **suspicion**: not shown.
- A second pass the same day ran eight checks on local Spark (§13), which confirmed items 1,
  2, 6 and 13, withdrew one bullet of item 7 and added item 83. No full suite was run;
  `ruff check src tests` passes. The last full suite is the one of 2026-11-17.

## 1. Fix first

**1. Regression list slices narrower than 0.4% of a period's rows read low** (reproduced, also
on the Spark path).
- **What happens.** For a regression target, the capture, rate and lift of a short list come
  out too low: about 30% low for a top 0.1% list and about 10% low for a top 0.3% list. From
  0.4% on the numbers are right.
- **Why.** Evaluation reads no rows for its metrics. It sums the scores table into score bins
  (the cells) and reads everything from them. A list that ends inside a bin is given a
  proportional share of that bin's amount (`statistics/metrics.py:264`, a straight line between
  the bin's ends). That is right only when the amount is spread evenly inside the bin.
  Regression's top bins hold 0.4% of the rows each (`statistics/score_cells.py:41`: 25 bins over
  the top 10%), and inside the top bin the amount sits at the top. A list shorter than the bin
  is therefore credited with the bin's average. Binary does not have the problem: its top bins
  are 0.001% wide and cut by a second quantile pass (`TAIL_START`), which regression lacks.
- **When it bites.** Any `top_pct` below 0.4%, and any `top_n` below 0.4% of a period's eligible
  rows, such as a list of 3,000 on 1 million rows. `top_pct` only has to be above 0 and nothing
  warns. The decision's slice also sets the explanation cut and the strata's list composition,
  which inherit it.
- **Evidence.** Capture from the cells against the row-level top-k of the same rows. The
  simulation has 1 million rows, exact quantiles and three tail weights; the Spark column is
  200,000 rows through the real `score_edges` and `score_cells`.

  | Slice | Simulation | Real Spark path |
  |---|---|---|
  | top 0.05% | 40 to 44% low | 30% low |
  | top 0.1% | 26 to 30% low | 28% low |
  | top 0.2% | 16 to 24% low | 13% low |
  | top 0.3% | 9 to 17% low | 9% low |
  | top 0.4% | within 0.3% | within 0.3% |
  | top 1% | not run | 1.8% high |
  | top 5% | not run | within 0.1% |

  On the Spark path the four narrow captures are exact multiples of each other (0.00499,
  0.00998, 0.01996, 0.02994): the straight line inside the top bin.
- **Already declared.** A103 (the score bins dense at the top) gave binary 380 bins and left
  regression at 50, and the tolerance in `evaluation.md` was measured on binary. It is T50
  (metrics from binned scores need bins as fine as the decision) again, for the other task.
- **Fix.** Two parts:
  - top bins for regression as fine as the lists people declare, with a tail pass like binary's;
  - a guard for whatever stays below the finest bin: such a slice is "not available: narrower
    than the score bins", decided up front (D-035: an output that cannot be produced is decided
    before running). `evaluation.md`'s measured tolerance then gets a regression row.

**2. A stratum level named `mean` or `pooled` gets another row's numbers** (reproduced, also on
the Spark path).
- **What happens.** When a stratification variable has a value that is literally `mean` or
  `pooled`, the report's row for that level shows other levels' numbers. Nothing is raised.
- **Why.** The metric tables have two special rows: `pooled` (every period together) and `mean`
  (the plain mean of the periods' values). `_scoped_metrics` (`evaluation/tables.py:163-173`)
  takes a list of scopes and recognises the two special ones by their text. For periods that is
  safe, since a period's label is a date. For strata, `_strata_tables` passes the levels as the
  scopes (`:239`), so a level of that name is taken for the special row: `pooled` is computed on
  every level's cells and `mean` as the average of the other levels. A real level named like a
  reserved bin (`null`, `__other__`) is quoted (`dataset/counts.py:40`); these two words are not
  on that list.
- **When it bites.** Only with such a value: a segment or product called "pooled", a category
  "mean". Rare, and silent when it happens.
- **Evidence** (the real stratum path in Spark, 60,000 rows, part `test`):

  | Level | Metrics table | Strata table | Truth |
  |---|---|---|---|
  | `low` | 10,000 rows, rate 0.0496 | the same | 10,000 rows, 0.0496 |
  | `mean` | 20,000 rows, rate 0.2225 | 5,000 rows, 4,450 events | 5,000 rows, 0.0972 |
  | `pooled` | 30,000 rows, rate 0.1972 | 5,000 rows, 5,915 events | 5,000 rows, 0.1958 |
  | `high` | 10,000 rows, rate 0.3954 | the same | 10,000 rows, 0.3954 |

  `mean` reads the average of `low` and `high`, and `pooled` reads the whole part. The strata
  table pairs the level's own rows with those wrong events, so `pooled` shows more events than
  rows.
- **Fix.** `_scoped_metrics` and `_scope_rows` take two flags, `pooled` and `mean`, in place of
  looking for the words among the scopes; strata call with both off. One test with a level of
  each name.
- **Same family** (read): a stratum variable named `all` would overwrite the pooled cells at
  `evaluation/run.py:276`. Refuse the name at config load.

**3. Pruning drops every feature the start-size model did not split, when no noise column was
split either** (reproduced).
- **What happens.** On a wide feature set, importance pruning can remove dozens of features
  that carry real signal, and the check that should undo a harmful pruning cannot notice.
- **How pruning is meant to work.** Five random noise columns are added and a small LightGBM is
  fitted on the folds. A feature whose share of the out-of-fold contributions is no larger than
  the best noise column's is a candidate to drop. The model is then fitted with and without the
  candidates, and the drop is undone if the loss rose.
- **Why it goes wrong.** The pruning model is LightGBM at the search's start configuration: 50
  trees of 4 leaves, so 150 splits per fold model at most (`training/search_space.py:24-30`).
  With more columns than that model can use, most columns get no split, the noise columns among
  them. The best noise share is then exactly 0, and `share <= best_noise`
  (`training/selection.py:152`) reads "no split in a tiny model" as "no better than noise" for
  every unsplit feature. The undo check compares the same tiny model with and without features
  it never used, so the two losses are equal and it never fires.
- **When it bites.** When the features left by the cluster rule and the floor outnumber what
  150 splits can use and the signal is spread over many of them.
  - On the tests' quick config it does not: 19 features reached pruning, the best noise share
    was 0.0078 and no feature had a share of 0 (Spark check P6).
  - Whether the canonical run's 10 pruned features (`review_guide.md` §5) went this way is not
    checked: no run folder is stored under `data/`. The `selection` table shows it at a glance:
    a `threshold` of 0 on the `prune` rows is this case.
- **Evidence.** The real `prune_by_importance` on 45,000 simulated rows with 7,210 positives,
  3 strong and 120 weak real features that all pass the floor:
  - 65 real features were dropped, at a best noise share of 0.0;
  - at the start configuration the loss is 0.36941 with and without them, so the undo check
    sees no difference;
  - a model of realistic size does use them:

    | Features | Log loss | AUC |
    |---|---|---|
    | all 123 | 0.34588 | 0.8187 |
    | the 58 left | 0.34914 | 0.8118 |

  - with 34 features, 2 of 30 real ones went the same way (agent ran).
- **Fix.** Three parts:
  - a best noise share of 0 is no evidence: prune nothing and warn;
  - the pruning model is sized to the frame (splits a multiple of the column count, or a
    column share below 1 so every column gets its turn);
  - the undo check runs at a size that can use the candidates.

**4. The floor judges a feature on its non-null rows only** (reproduced).
- **What happens.** The floor drops a feature whose value says little but whose being filled or
  not predicts the target, such as "months since the last X", null for clients who never had X.
- **Why.** A feature passes the floor when its train concordance is at least
  `0.5 + floor_z · SE`. That concordance is computed on the rows where the feature is known
  (`training/train_statistics.py:164-188`, read by `training/selection.py:117`), so the null
  pattern never enters it. A tree model would use the pattern: the encoder imputes nothing and
  each library sends nulls down their own side of a split. The statistic that measures it exists
  (`statistics/scope.py:74`, `null_concordance`), and Feature Checks' `nulls_informative` note
  advises keeping such a feature (agent read). Training does not read it.
- **When it bites.** Features with many nulls whose nulls mean something. A mostly-null feature
  is hit twice: its few known rows give a large SE, so the threshold is high as well. On the
  tests' quick config 7 of the 46 features the floor dropped have more than 20% nulls (Spark
  check P6), for example:

  | Feature | Null share | Value | Threshold |
  |---|---|---|---|
  | `loan_auto_maturity_months` | 94% | 0.63 | 0.73 |
  | `months_since_last_spend_cc` | 91% | 0.58 | 0.61 |
  | `loan_personal_maturity_months` | 83% | 0.53 | 0.61 |

  Whether their null patterns carry signal on that data was not measured.
- **Evidence** (the real `train_statistics` and `apply_floor` on simulated rows). A column that
  is null for 60% of the clients, with noise values and a null-indicator AUC of 0.62, gets a
  floor value of 0.510 against a threshold of 0.522 and is dropped. Grouped-CV AUC is 0.739
  with it and 0.699 without.
- **Fix.** A feature passes the floor when either its value concordance or its null-indicator
  concordance on train clears the threshold, and the selection table records which one did.

## 2. Should fix

**5. Regression's test concordance reads up to 0.016 above the row value** (reproduced).
- **What happens.** For regression the report sets train's concordance, computed on rows,
  beside test's, computed on cells. Test's reads higher than the same number on rows would, so
  the train-to-test gap that shows overfitting looks smaller than it is.
- **Why.** The cells hold the target in 20 bins. Two rows whose targets fall in one bin count
  as tied, so they leave the pairs the concordance is taken over. Those are the pairs hardest
  to order, and what is left is easier.
- **Evidence.** Cells against rows on 200,000 simulated rows:

  | Row concordance | Cells read |
  |---|---|
  | 0.65 | +0.007 |
  | 0.75 | +0.011 |
  | 0.85 | +0.015 |
  | 0.92 | +0.016 |

- **Already declared.** A105 (train on rows, test on cells) says "about 0.01", and the gap
  sentence (`evaluation/views.py:78`) adds that a test value above train's is no finding.
- **Fix.** Count the within-bin pairs or cut more target bins, or put train's in-sample
  concordance on the same cells. At the least the sentence says 0.016.

**6. The judged-model check does not run with `training.fold_repeats > 1`** (read; confirmed on
a run).
- **What the check is for.** FLAML only searches and the framework refits. After the fold
  models, Training recomputes the winning configuration's fold loss from its own fits and
  compares it with the loss FLAML logged (`check_judged_model`). Equal means FLAML judged this
  configuration on the client folds, unshuffled (T42), with the framework's parameters and
  untruncated trees (T45). It is the only run-time proof of that.
- **What happens.** With more than one dealing the comparison is skipped
  (`training/run.py:230`), since FLAML's loss covers every dealing and the fold models the
  first. Nothing records the skip: a run with `fold_repeats: 2` has no warning and no key about
  the check in `training.json` (Spark check P7).
- **Why it matters.** `fold_repeats: 3` is what the few-events warning recommends
  (`:205-208`), so the small, noisy use cases are the ones that run unchecked.
- **It can be closed.** At two dealings the framework's own mean over 2 × 5 folds equalled
  FLAML's logged loss to the last digit (agent ran).
- **Fix.** Fit the winning configuration on the other dealings too ((R − 1) · K more fits) and
  compare the means. At the least a line in `training.json` says the check did not run.

**7. Three refusals that need no model come after the run number** (read).
- **What happens.** `training.md` promises that every refusal that needs no fit comes before
  `create_run`, so a refused run takes no number and leaves no folder. Three cases fail after
  it and leave a crashed run folder; the third fails after the bundle is written.
- **The cases.**
  - A negative target under `tweedie` or `poisson`. The contract checks finite and non-constant
    only (`tasks.py:279`), and the first fit dies inside the library (agent ran, all three
    libraries). A `forward_sum` of net amounts can be negative. Refuse in `_open_run` from the
    contract entry's `min`, naming the objective.
  - The cluster rule or the floor leaving no feature, and a feature named like a noise column
    (`training/selection.py:52-55`, `:175`). Selection runs after the number is taken although
    these two rules fit nothing: see item 42.
  - A regression fold whose targets take one value. `check_folds` checks rows only for
    regression (`dataset/folds.py:100`). The search and the fits go through, and the per-fold
    concordance then raises in `train_metrics` (`training/tables.py:101`), after the bundle,
    the per-run ledger and `stage2/` are written. Under `r2` such a fold silently scores 0
    (agent ran). Refuse in `check_folds`.
- **Withdrawn.** The code review also listed an empty feature set. The Spark check P8 shows it
  is refused before the number with a clear message ("`features` is empty: the training frames
  need at least one…"), and the run folders are the same before and after.

**8. Training's warnings never reach the model results report** (read).
- **What happens.** A reader of the report or the card sees Evaluation's warnings only.
  Training's stay in `training.json` and notebook 04.
- **Why.** The Warnings section renders Evaluation's own list
  (`evaluation/views_summary.py:173`). Evaluation copies `training.json`'s `metrics` into its
  meta and not its `warnings`.
- **What is lost.** Held features released by a revert, the few-events note, the time-budget
  note, a judged-model mismatch under a time budget, the level-factor interval warning,
  CatBoost's null note.
- **Already declared.** A108 (Training's warnings stay free text) covers the card, not the
  report. The run of the Spark checks raised no Training warning, so this stays a reading of
  the code.
- **Fix.** Show them in the Warnings section under "from Training".

**9. A baseline value that is undefined on a part goes to the card as `available: true`**
(read).
- **What happens.** The card's baselines comparison can hold a row with a null value that is
  marked available, with no reason anywhere.
- **Why.** `_comparison_rows` sets a reason only when one was declared up front
  (`evaluation/baselines.py:344-348`). A value the cells cannot define, such as an AUC on a
  one-class part or a calibration line on separated scores, is stored as NaN with an empty
  reason, and the card takes "empty reason" for available (`evaluation/card.py:293`).
- **Fix.** Available means no reason and a finite value; otherwise the reason says why.

**10. `find_run` picks an older run without saying which newer ones it passed over** (read).
- **What happens.** `run --stages evaluation` with no `--run` evaluates the newest run that
  matches the config. After a crashed retrain, or one under other settings, that is an older
  run, and the run number in the printout is the only sign.
- **Why.** `find_run` walks the runs newest first and returns the first match
  (`runs.py:237-240`). It collects the reasons the newer ones did not match, and prints them
  only when nothing matches.
- **Fix.** When the run returned is not the newest, print the skipped ones with those reasons.

**11. `partial_dependence` fails the whole stage when an effect feature is null on every
sample row** (read; two agents found it independently).
- **What happens.** Evaluation stops with "the feature … is null on every sample row" after
  the scoring and the metric tables are done.
- **Why.** `_grid` raises on a feature with no known value in the 5,000-row explanation sample
  (`evaluation/explain.py:392`). An EDA key feature that is null on more than 99.9% of the rows
  is likely all-null there. The effects table beside it already handles nulls.
- **Fix.** Decide it before running: leave such a feature out of the partial dependence and
  record "not available: null on every sample row" under `unavailable` (D-035).

**12. Permutation importance counts as available with one positive row in the sample** (read).
- **What happens.** At a rare rate the permutation table rests on a handful of events, and the
  view's guidance overstates what its numbers mean.
- **Why.** The sample is 5,000 unstratified test rows, about 2.5 positives at a 0.05% rate.
  `permutation_unavailable` only requires two target values (`evaluation/explain.py:288`; A107
  declares that rule). `loss_change_sd` covers the five permutations and not the draw of the
  rows, while the view says a change within one SD is noise, so a larger change reads as
  signal although one or two rows drive it.
- **Fix.** Not available below `strata.min_events` events in the sample, with the count shown.
  A deviance metric on non-positive predictions would also crash mid-permutation where it
  should be declared up front (agent read).

**13. The drift reference's score side holds known-target rows only** (read; confirmed on a
run).
- **What happens.** Monitoring's yardstick for the score distribution is built on a population
  that differs from the one Inference will score.
- **Why.** The frames drop null-target rows before scoring (`dataset/frames.py:419`), and the
  reference reads the test part's cells (`evaluation/drift_reference.py:44`). Its feature side
  comes from EDA's counts on every eligible row. `monitoring.md`, `dataset.md` and
  `evaluation.md` all say every eligible row regardless of label.
- **Evidence.** On the run of the Spark checks the scores table holds 5,416 test and 3,099
  validation rows and no null target, while 2.8% to 3.4% of each period's eligible rows have a
  null target (P6).
- **Why it matters.** When those rows score differently (leavers, a window with a gap), the
  first score PSI in production starts above zero for a reason that is not drift.
- **Fix.** Keep the null-target test rows for the reference only, or state the conditioning in
  the reference and in `monitoring.md`.

**14. View 14 shows validation at validation's own thresholds** (read).
- **What happens.** The thresholds view answers "which score reaches this depth on this part"
  for each part separately (`evaluation/views.py:316`). What a threshold fixed on test does on
  the validation period, which is the question for a `threshold` decision, is never shown, so
  a score drift between the window and the validation period stays invisible there.
- **Related, declared (A115).** The score edges are cut over test and validation together
  (`evaluation/cells.py:113`), so validation's scores, and for regression its labels through
  the target bins, shape test's binning and `compare_runs`' verdict on test. §4.4 says the
  validation period informs no choice.
- **How large.** Negligible in numbers: with validation's odds doubled, cutting the edges on
  test only moves test's AUC by 5e-6 and its average precision by 5e-5 (Spark check P4). The
  case for changing it is the rule and what view 14 could then show.
- **Fix.** One change answers both: cut the edges on test, bin validation on them, and add
  validation at test's thresholds to view 14.

## 3. Report, card and chart defects

No crash and no wrong stored number: each is what a reader sees on the page.

**15. The permutation view reads "Not available: not available: one target value…"**
(reproduced). The stored reason already starts with "not available: "
(`evaluation/explain.py:49`) and the block that renders it adds the prefix again
(`evaluation/views_explain.py:195`). It shows whenever the explanation sample's target has one
value, which is plausible at a rare rate. Fix: store the bare reason and let the block add the
prefix; check that the card does not rely on it.

**16. Waterfall labels in scientific notation** (reproduced). `_format_value` formats with
`.4g` (`reporting/explain_charts.py:77`), so an income of 250,000 reads `2.5e+05` and a small
ratio `1.234e-05`; the hovers at `:154` and `:331` do the same. `reporting.md` says amounts are
never shown that way, and `formats.plain_number` exists for it. Fix: call `plain_number`.

**17. The card page shows a seed as a quantity** (reproduced). `_cell` sends every integer
through the thousands format (`reporting/card.py:73`), so `training.seed: 20240101` reads
`20,240,101`, and floats are cut to four significant digits on the page while the JSON keeps
them whole. Fix: integers as they are, the number format for floats only.

**18. `render_card` never checks the card's `schema_version`** (read;
`reporting/card.py:22`). A card of another version raises a bare `KeyError` or renders without
the sections it does not know. The section order is also written twice, as a literal in
`evaluation/card.py:65` and a tuple in `reporting/card.py:18`, tied by one test. Fix: one
module owns the version and the sections, and the renderer refuses another version.

**19. The importance bar draws test in the red that means "raises the score"** (read;
`reporting/explain_charts.py:167`). Every other chart of the report gives test the first
sequence colour, and red has a meaning in the explanation charts that an importance does not
carry. The lone bar in Training's views is red too. Fix: the part colours from one helper.

**20. The search table has no number formats** (read; `training/views.py:87`). Seconds, shares
and the fold metric print raw (`123.456789`, `0.431235`) in notebook 04 and report view 13,
while Evaluation's tables are formatted. Fix: pass the formats, as the other tables do.

## 4. Before the 1.0 freeze

Today's code reads everything it wrote itself. These are about what a later version does to
what an earlier one wrote, and several are cheap now and dear after 1.0. Items 21 to 23 matter
before M2.4, which builds register on them.

**21. A run's `stage2/` copy is checked against the live EDA and ledger versions** (read;
`training/gate.py:168`). Any EDA schema bump makes every earlier run unreadable to Evaluation,
the card and the drift reference, although the copy did not change. D-139 says a run is
complete in itself. Fix: the copy gets its own schema version with frozen columns; the source
versions stay as provenance.

**22. The contract between Training and Evaluation is scattered** (read in part). Two
`TRAINING_TABLES` constants hold different tables (`evaluation/run.py:116`,
`evaluation/card.py:44`); the key lists sit in `evaluation/card.py:42-45`,
`evaluation/run.py:221-236`, `training/tables.py:120` and `evaluation/compare.py:473`; nested
keys of `run.json`'s `training_settings` follow a list in code, not `run_schema_version`. A
missing nested key is a bare `KeyError`, and the card's fire in `_write` after all the Spark
work. Fix: one contract (keys, nested keys, tables, columns) checked once when the run is
opened.

**23. The drift reference has no sidecar and lives inside `evaluation/`** (agent read), which
every re-evaluation replaces. A production model's yardstick can move under one `model_hash`.
Fix: a sidecar with its version and `model_hash`; register takes a snapshot.

**24. FLAML's vocabulary would freeze** (agent read): the metric values `ap`, `roc_auc`,
`log_loss`; `estimator_list`, `max_iter`, `path: automl`; the families `lgbm` and
`xgb_limitdepth`; FLAML's parameter names in `search_space` and the stored recipe; the summary
keys `oof_<metric>` and `test_<metric>`. The Optuna path of Phase 3 would have to keep them
all. Fix: settle the 1.0 names now and map to FLAML's inside `search.py` only.

**25. Every reader accepts exactly the current version and answers "train again"** (agent
read). At the first bump after 1.0 a raised pin cannot load its production bundle, which D-047
(each use case pins its version and upgrades at its own pace) requires. No test loads a stored
older artifact. Fix: a reader per version within a major for the bundle, the manifest, the
encoder and `run.json`, and one committed run folder that every version must load and score.

**26. All-null parquet columns (T44) reach Evaluation's tables too** (agent ran):
`metrics.stratum` and `level` are written as type `null` when no strata are configured, and an
empty `strata` or `permutation_importance` table with every column `null`. The architecture
inventory names T44 for Training only.

**27. Column names derived from feature names can collide** (read: no guard in
`training/tables.py:65-70`). A feature named `base_value`, or `x__contribution` beside `x`,
fails the parquet write at the end of the stage. Fix: refuse those names when the frames are
built.

**28. `run`'s default is "every built stage"** (agent read; `run.py:131`), so each release that
builds a stage changes what an unchanged `run <config>` does. Fix: freeze the default at 1.0.

**29. Public API** (agent read): `Bundle`, the return type of the public `load_bundle`, is
missing from the table in `architecture.md`; `model/__init__.py` exports nine names the table
does not list; `tests/test_run.py:39` holds a second copy of the table; the stages take
`(cfg, entity, env)` while `list_runs` and `show_run` take `(env, cfg, entity)`.

**30. In the step 1 foundations both stages rest on** (reviewed 2026-11-16; listed for M2.4):
- Every identity hash covers defaulted fields (read; `config/identities.py:46`). One added
  field with a default moves the data-definition hash, which orphans the audit log and every
  earlier run. `config.md` states the rule; no remedy is designed.
- `load_bundle` refuses another `hash_version` (read; `model/bundle.py:243`), although the
  model hash is over file bytes. The remedy for the point above would make stored bundles
  unloadable.
- One `run.json` of another version, or a truncated one, breaks `list_runs` and `find_run` for
  the whole use case (agent ran; `runs.py:352`).
- `create_run` reads every audit log of the use case through the strict reader to collect run
  numbers, so one newer entry stops every older-pinned Training (agent ran).
- A `run` entry that loses a race between two sessions raises after `training/` or
  `evaluation/` is committed (agent read; `config/audit_log.py:377`).
- The run number rests on a local `mkdir` and the stage swap on a POSIX rename; HDFS behaves
  differently for both (suspicion; M2.4's transport).

**31. `reproducible_to: model` rests on facts the run does not record** (agent read): the
thread count and the versions of FLAML, the losing families' libraries, numpy and scikit-learn.
Only the winning library's version is written. Fix: write them into `training.json`.

## 5. Inside the bank: environment and scale

Installed versions equal the pins throughout, and nothing failed locally on them.

**32. The scores table assumes a local filesystem** (agent read; `evaluation/scores.py:98`).
Spark writes to a bare path and Python then renames and removes it (`evaluation/run.py:505`).
With a cluster master, or HDFS as the default filesystem, the two point at different places.
`model_bundle.md` says `score_spark` does not depend on the transport, which is true of that
function and not of `write_scores`.

**33. A Spark executor needs `core_modelling` itself and all three model libraries**
(reproduced for the import; the pickled closures, agent ran). Importing `model/scoring.py`
loads LightGBM, XGBoost and CatBoost whatever the bundle's family. The docs list "the model
libraries on an executor" only. It belongs on the bank trip beside T40 (Spark's Python workers
are not the driver's Python).

**34. Importing Evaluation imports FLAML and plotly** (reproduced), through
`training/__init__.py`. See item 40.

**35. Threads** (agent read). `os.cpu_count()` sets every library's thread count
(`training/run.py:134`; A87 declares the machine's cores), and on Python 3.11 it ignores a
container's limit. The predict paths pass `threads=None`, and nothing caps BLAS.

**36. First import writes matplotlib's font cache into `$HOME`** (agent ran), on the driver and
on each worker; a read-only home would hit it. LightGBM, CatBoost and scikit-learn import
matplotlib.

**37. Temporary siblings are named by process id** (agent read; `artifacts.py:203`,
`evaluation/scores.py:91`), which is unique per host only.

**38. Three library internals are read** (agent ran on the pins): `Booster._get_loaded_param`
(`model/lgbm_family.py:155`), XGBoost's JSON layout (`model/xgb_family.py:127`) and
`SparkSession._instantiatedSession` (`environment.py:194`). A patch release could move any.

**39. Scale, read from the code and not measured:**
- Nothing is cached, so each action recomputes the panel: about 25 full plans in a Training
  run and about 15 in Evaluation. `dataset.md` already says persisting is undecided. Measured
  on the tests' quick config (§13, P5): 74 to 106 Spark jobs in 14 s for Training and 83 to
  114 in 18 s for Evaluation; one action starts several jobs.
- The explanation sample of 5,000 rows costs three full-lineage passes and two global sorts
  (`evaluation/explain.py:120-136`); `encoding_shares` adds one.
- A `count()` and a 10,000-row collect run before the train collect, for the printout and the
  budget check (`dataset/frames.py:476-479`).
- The feature matrix is float64 throughout. About four matrix-size copies are alive at the
  fold-fit peak (`training/fold_models.py:44`), `encode_frame` peaks at twice its output
  (`model/encoder.py:230`), and the out-of-fold contributions are copied once more and kept to
  the end.
- The split cells at 201 replicates are about 2 million rows on the driver, more per stratum
  (a formula estimate).
- Each ranking baseline runs the full `metric_tables` and keeps the metric rows: 0.38 s against
  0.07 s at 20 replicates (agent ran). See item 49.
- The bundle is loaded and hash-checked three times, the `stage2/` copy read twice and
  `check_skip_views` run twice per Evaluation.

## 6. Refactors

**40. The run folder's readers leave `training/`** (reproduced for the import chain). Eight
Evaluation modules import `read_stage2_copy`, `read_run_ledger`, `train_level`, `BASE_COLUMN`,
`sample_contributions`, `split_budget` and the sign-off view from `training/`, and
`evaluation/cells.py` and `effects.py` take `cap_levels` from `eda/population.py`. M2.4's
register, Inference and Monitoring will read the same folder. Move the readers and their
constants beside `runs.py` (or one module per artifact), `cap_levels` to `statistics/` or
`dataset/`. This also retires item 34.

**41. One contract check when a run is opened**: the fix of item 22.

**42. Selection in two parts**: a model-free screen (train statistics, cluster rule, floor)
that `_open_run` calls before `create_run`, and `prune_by_importance` after it; the noise-name
clash moves into the gate. This is the third bullet of item 7.

**43. The fold loss is written three times** (`training/selection.py:203`,
`training/run.py:231`, `training/tables.py:100`): margins to the uncalibrated score to
`mean_fold_loss`. One helper in `fold_models.py`.

**44. One rule, two formulations**: Training's "Platt a ≤ 0, or beta a ≤ 0 and b ≤ 0"
(`training/calibrate.py:81-99`) and the bundle's "a ≥ 0, b ≥ 0, not both 0"
(`model/calibration.py:118-132`) agree only because `fit_beta` zeroes one coefficient on a
refit. Call the bundle's check from `calibrate`.

**45. `training/ledger_run.py` (458 lines) holds two concepts**: the per-run ledger and the
sign-off table. The second moves to `training/signoff.py`.

**46. `training/search.py` (425 lines) mixes FLAML's plumbing with the search's contract**, and
knows families outside `FAMILIES` (`if family != "catboost"` in `search_frame`). The plumbing
moves to its own module; the branch becomes a dict.

**47. `training/run.py` computes although it says it only orchestrates**: the judged-loss
check, the feature-name check of the final booster, the in-sample predict. `_write_bundle` does
three jobs. Smaller: `check_order` runs three times, `describe` twice, and the bundle is loaded
twice.

**48. `evaluation/tables.py` (441 lines) mixes four concerns**; the slices move to
`evaluation/slices.py`. `_list_by_level` (`:282`) is a second implementation of the slice cut
that `slice_metrics` makes: one helper, which is also where item 1's fix lands.

**49. `metric_rows` for the baselines**: `_baseline_metrics` calls it, `metric_tables` reuses
it (item 39).

**50. `evaluation/run.py` (511 lines) and `explain.py` (412 lines)**: the single-feature
warnings move to `baselines.py`, permutation importance to its own module, `effect_features`
to `effects.py`, `curve_at_depths` to `statistics/metrics.py`. `Opened` has 13 fields and
`_write` seven parameters.

**51. Per-task dicts outside `TASK_SPECS`** (D-050: every task-specific choice dispatches
through one per-task spec): `SCORE_GRID`, `STRATA_STEP`, `TAIL_START`, `OBJECTIVE_LOSSES`,
`VIEWS_BY_TASK`, `CALIBRATION_BY_TASK`, and `_scale_note` branching on the task.

**52. `evaluation/report.py`**: `VIEWS`, `TITLES` and `EXTENDED` are three structures keyed by
view name, so a new view takes three edits. `evaluation/views.py` holds whatever is in no other
views module.

**53. `evaluation/compare.py` (484 lines)**: `_stage_meta` re-implements
`artifacts.read_stage_meta`, and `Metric` is a copy of `tables.py`'s.

**54. Flat string keys** (`"scope|name"`, `"period|slice|rate"`) exist only because
`bootstrap_intervals` takes a flat dict; `_slice_rows` glues the period into the slice label
and splits it back.

**55. One owner for the card's version and section order**: the fix of item 18.

**56. Defined twice.**
- Constants: `PARTS` and `PART_ORDER`; `METRIC_COLUMNS` and `CARD_METRIC_COLUMNS`;
  `DEVIANCE_METRICS` and `POSITIVE_LOSSES`; `STAGES` and `STAGE2`; the two 1e-6 tolerances.
- Formulas: the row losses and the clipping as Spark columns (`evaluation/cells.py:321-352`)
  and as their pandas mirror (`statistics/score_cells.py:84-120`), with a third Tweedie in
  `statistics/losses.py:39`. A test ties them.
- Names: `run` is the run number in `evaluation/run.py` and a `{features, single_feature}`
  dict in `evaluation/baselines.py`; `Opened` is two classes.

**57. Dead or test-only code** (read by grep): `WATERFALL_ROWS` (`evaluation/explain.py:40`) is
used nowhere; the `lift=` branch of `dependence` and `_beside_lift`
(`reporting/explain_charts.py:382-448`) have no production caller; `build_report`
(`evaluation/report.py:154`) and `cells_from_rows` (`statistics/score_cells.py:152`) are called
from tests only.

**58. Table names owned by the views**: `evaluation/run.py:98-99` imports `TRAINING_SIGNOFF`,
`TRAINING_TRIALS` and `TRAIN_SAMPLE` from the views modules, so what is stored depends on what
is drawn.

## 7. Tests

The statistics, the folds, the calibration fits and the run's identity are well protected,
mostly against scikit-learn or scipy. The dataset tests outside this audit's files cover
train-only frames, train-only downsampling, the unsampled contract checks and lineage.

| # | Gap | Where |
|---|---|---|
| 59 | No test shows the run calibrating on its own out-of-fold margins; every test hands `calibrate` the margins | `tests/test_calibration.py`, `tests/test_training.py` |
| 60 | Regression runs only through end-to-end fixtures: no regression variant of the fold-model, selection or acceptance tests, and one regression search metric | `tests/test_fold_models.py`, `tests/test_selection.py`, `tests/test_search.py` |
| 61 | Slices are checked against their own sums, with no row-level oracle; item 1 is what that misses | `tests/test_metric_tables.py` |
| 62 | No test loads a stored older `run.json`, `training.json`, bundle or card (item 25) | `tests/data/` |
| 63 | End-to-end assertions check presence: non-empty tables, an `all(...)` over warnings that passes on none, headings only for the thirteen view functions | `tests/test_evaluation.py:76-92`, `tests/test_evaluation_report.py:195` |
| 64 | XGBoost and CatBoost go through the whole stage only in the slow test | `tests/test_training.py` |
| 65 | About 36 `raise` statements have no test (the agent's grep) | the two packages |
| 66 | Two tests fake behaviour where the policy asks for real data | `tests/test_selection.py:199`, `tests/test_fold_models.py:107` |
| 67 | Tests that read `list_runs(...).iloc[0]` from a shared module environment depend on what earlier tests wrote | `tests/test_training.py` |
| 68 | The bootstrap's percentile is checked for coverage, not against `np.quantile` | `tests/test_bootstrap.py:63` |

## 8. Docs and notebooks

No behaviour differs between docs and code; the docs are the stale side wherever one is.

| # | Mismatch | Where |
|---|---|---|
| 69 | The calibration intercept's binning error is 0.0013 in the doc and 0.0015 in the docstring; on a miscalibrated score at a 0.05% rate it measured 0.0024 (agent ran) | `evaluation.md:215`, `statistics/score_cells.py:58` |
| 70 | "Five fixed switches"; `FLAML_SWITCHES` holds six | `training.md:262`, `training/search_space.py:64` |
| 71 | The judged-model tolerance is 1e-6 in the doc, relative above a loss of 1 in the code | `training.md:374`, `training/search.py:410` |
| 72 | `evaluation.md` says test and validation are every eligible row; null-target rows are dropped (item 13) | `evaluation.md:111` |
| 73 | Average precision on tied scores is the expected value under random tie-breaking on cells and scikit-learn's in Training: 0.1937 against 0.1664 on nine distinct scores (agent ran). No doc states it | `statistics/metrics.py:88` |
| 74 | "The validation period … is the one honest number": the headline validation pools both splits, about 70% of them train clients; only view 17 says so | `evaluation/views_summary.py:113` |
| 75 | Missing from the code maps: `train_level`, `sample_contributions`, `read_stage2_copy`, `build_bundle` | `training.md`, `model_bundle.md` |
| 76 | Stale docstrings: `evaluation/__init__.py` omits `views_summary.py`, `card.py` and `effects.py`; `tables.py:3`, `effects.py:3` and `drift_reference.py:36` point at the wrong place | |
| 77 | 100 references to A-, Q-, R- and V-numbers in `src/`; those records go when the stage closes, so each sentence has to stand without its number | 31 files |
| 78 | No glossary entry for the per-run ledger, the `stage2/` copy, the sign-off table, "protected" and "headline" | `glossary.md` |
| 79 | `check_card_inputs` is called public but is not in the Public API table | `reporting.md:292` |
| 80 | "Categoricals: not tested" is stale; the round trips hold (agent ran) | `docs/context/environment.md:143` |
| 81 | "Seventeen views" and "380 bins" are restated in six or more docs each | |

**82. Notebooks 04 and 05** (reproduced by reading the cells). No definitions, no stored
outputs, no machine-specific numbers, and every call is a Public API name.
- Notebook 04 (cells 5, 9, 11, 15) and notebook 05 (cell 5) display package-built `<p>`
  paragraphs as HTML output, which `notebooks/README.md` forbids. They are run facts, not guide
  text, so the rule gets an exception or the lines become one-row tables.
- Notebook 05 cell 25 builds a `shap.Explanation` by hand. Nothing in `src/` imports `shap`, so
  the pinned dependency serves that one optional cell.

## 9. Small things

**Training**
- `_few_events_notes` (`training/run.py:196`) repeats half of `tasks.py::_events_warning`.
- The `calibration` table's column `oof_log_loss` names binary's loss in a shape both tasks
  share (`training/calibrate.py:31`); renaming it is an artifact change.
- `_bin_orders` re-implements `distributions.bin_orders` with another null code
  (`training/train_statistics.py:125`).
- CatBoost's null warning is computed before selection and can name dropped features
  (`training/train_data.py:122`).
- `resolve_config` and `load_entries` read the audit log separately; an entry appended between
  them leaves the two apart (suspicion; `training/run.py:171`).
- `seconds["tables"]` includes the ledger and `stage2/` writes; the summary leaves out the
  final write; `summary["oof_<metric>"]` is a key that changes with the metric.
- A final feature with no split gets `in_model` false and no warning
  (`training/ledger_run.py:156`).
- A NaN floor value would pass the floor (suspicion; `training/selection.py:117`).
- `level_factor` gives a null interval without naming the cause when a replicate's weighted
  total is 0 (`statistics/calibration.py:139`).
- Under `negative_downsampling`, `min_level_client_count` counts clients after sampling
  (`model/encoder.py:215`).
- `train_level` reads `training.json` without the version check, and `compare_runs` calls it
  before its own (`training/tables.py:117`).

**Evaluation**
- The timings are patched into the meta after `_build_result`; the "scoring" lap includes
  opening the run, and no lap covers the views, the card or the write (`evaluation/run.py:180`).
- `loss` is a name in `score_cells` and a boolean in `metric_tables`
  (`evaluation/run.py:277`).
- `tables |= {…}` merges five sets of table names with no collision check
  (`evaluation/run.py:176`).
- The sample statistics run on 5,000 hashed rows plus the two hand-picked waterfall rows
  (`evaluation/explain.py:119`).
- A replicate that draws no client of one period blanks every slice interval of the part,
  where the metric rows blank that period only (`evaluation/tables.py:372`).
- With k positive clients an interval exists with chance (1 − e^−k)^200: 0.26 at 5, 0.94 at 8.
  A narrow slice then shows no interval and no reason (`statistics/bootstrap.py`).
- `CONDITIONAL_ON` and `"column": "score"` are hand-typed facts on a card documented as
  generated; `framework_versions.card` is the config's resolving version
  (`evaluation/card.py:38`, `:186`).
- `rows_per_period` on the card also holds `pooled` and `validation_test_clients`
  (`evaluation/card.py:220`).

**Views and charts**
- Sentences repeat numbers that constants hold: "every fourth edge", "depths 1 to 50%",
  "20 groups" (`evaluation/views.py:66`, `:212`; `reporting/model_charts.py:159`).
- The "fewer than {min_events}" sentence is written three times.
- Both y axes of the score distribution carry the title (`reporting/model_charts.py:204`);
  `metric_lines` drops `pooled` but not `mean` (`:228`).
- The collect table formats two of its columns; the EDA report builds the same table
  (`evaluation/report.py:124`).
- Untitled y axes in the importance bar, the beeswarm and the waterfall; the waterfall's `+.2f`
  turns a small step into `+0.00`.
- Ten view functions take `meta` or `resolved` and never read them (one signature for the
  dispatch).

**Outside this scope, noticed**
- Six `decide` flags have no help text and appear in no doc: `--exclude`, `--include`, `--set`,
  `--revert-to`, `--evidence`, `--stage`.

## 10. Checked and found sound

- **Train only.** No test-split or validation-period row reaches Training. Stage 2 contributes
  kinds, label-free cluster ids and the held and excluded lists only; no EDA bin edge or
  `non_monotone` mark is copied.
- **Folds.** Dealt after sampling with their own salt and grouped by client in every fit,
  FLAML's included; FLAML's own refit is never read.
- **Calibration** (agent ran). Fitted on first-dealing out-of-fold margins, then the offset in
  logit space: the offset was −3.002 against ln 0.05 = −2.996, and on a fresh unsampled
  population the mean score over the rate was 1.014 with Platt and 1.019 with beta.
- **Monotone constraints** (agent ran) hold with the right sign in all four families.
- **Thread counts** (agent ran) leave the model bytes identical for LightGBM, XGBoost and
  CatBoost.
- **Binary metrics from cells against scikit-learn on rows** (agent ran; 1 to 2 million rows at
  5%, 0.5% and 0.05%): the losses, the skills and observed to expected are exact, AUC within
  1.2e-4, average precision within 7e-4, the slope within 3.4e-4. Binary slices are within 0.01%
  of row-level top-k.
- **Regression metrics** (agent ran): RMSE, MAE, R², both deviances and predicted to observed
  equal the row values.
- **The bootstrap** draws Poisson(1) weights per client with one salt, shared by parts,
  baselines and runs, so differences are paired.
- **The rows judged**: test is the window's test-split clients, validation is the validation
  period with both splits, eligibility is one filter, and only the train frame is sampled.
- **`compare_runs`** differences test only and refuses other parts, another data definition,
  split or sources.
- **The write boundary**: leftovers are refused before Spark, a failure before the commit
  removes the staged scores, `evaluation/` is swapped in whole, and a re-evaluation never
  touches `training/`, `bundle/` or the per-run ledger.
- **Self-contained output**: plotly.js is embedded once, no remote reference, and no client id
  or row-level frame reaches the HTML or the card.
- **Up-front skips** (D-035): no `try`/`except` decides a view; every "not available" comes
  from the view table or `meta["unavailable"]`, with items 11 and 12 as the exceptions.
- **The countable rules**: no function body over 50 lines, no TODO, commented-out code, `noqa`,
  bare `except`, mutable default or import inside a function, no runtime import cycle, and a
  module docstring everywhere. No internet access and no file left in the working directory.

## 11. Against the review guides

What the two guides already declare, and where this audit adds to it.

| Declared | This audit |
|---|---|
| A103: binary 380 score bins, regression 50 | Item 1: regression's top bins are too wide for a narrow slice |
| A105: regression's train concordance on rows, test's on cells, about 0.01 higher | Item 5: up to 0.016 |
| A115: score edges cut over test and validation together | Item 14: one change with view 14 |
| A107: permutation importance is not available when the sample's target has one value | Item 12: one positive row is not enough either |
| A108: Training's warnings stay free text, off the card | Item 8: they are off the report too |
| A131: the drift reference is three tables in `evaluation/tables/`, not an artifact of its own | Item 23: a re-evaluation can then move it |
| A86: FLAML's refit on every row left on | Item 39: confirmed, the model is discarded |
| A87: threads are the machine's cores | Item 35: `os.cpu_count()` ignores a container's limit |
| A135: nine Evaluation modules above about 300 lines | Items 45 to 50: where each could be cut |
| The judged-model check runs at one dealing only | Item 6: it is computable at more |
| Open risk: cells collected to the driver, `frames.rows` recomputed | Item 39: the counts, with lines |
| Open risk: the drift reference's scores are test clients only | Item 13: and known-target rows only |
| Open risk: the model libraries on a Spark executor | Item 33: `core_modelling` too, and all three libraries |
| Local paths only until M2.4 | Item 32: the scores write is the one place Spark and Python share a path |

Not declared anywhere: items 2, 3, 4, 7, 9, 10, 11, 15 to 22 and 34. Item 83 shows a risk the
guide lists as unconfirmed.

## 12. How the audit was run

Thirteen read-only agents, one per lens, each briefed to form its own view from the code, the
tests and `docs/` without reading `worknotes/`. The main thread kept the architecture pass
(items 34, 40, 58), read or reran every item marked so above, and wrote this file.

| Lens | Model | Result |
|---|---|---|
| ML correctness, Training | Fable | Items 3, 4, 6, 31 |
| ML correctness, Evaluation | Opus | Items 1, 5, 12, 13, 14 |
| Code review, Training | Opus | Items 7, 42 to 47 |
| Code review, Evaluation's computing half | Opus | Items 2, 11, 48 to 50, 54 |
| Code review, reports, views and charts | Sonnet | Items 15 to 20, 51 to 53, 55 |
| Silent failures | Opus | Items 8, 9, 10 |
| Formats, config and Public API | Opus | Items 21 to 30 |
| Docs against code | Sonnet | Items 69 to 81 |
| Tests | Sonnet | Items 59 to 68 |
| Scripted inventory | Sonnet | Items 56, 57 |
| Bank parity | Sonnet | Items 32, 33, 35 to 38 |
| Spark actions and memory | Sonnet | Item 39 |
| Notebooks and the CLI | Haiku | Item 82 |
| The Spark checks' module (written, never run, by the agent) | Sonnet | §13, item 83 |

**Not covered**
- Spark beyond the eight checks of §13: the fold dealing, the sampling and the explanation
  sample were read, never run on their own, and nothing ran at canonical size.
- Inside the bank: executors, the default filesystem, the cluster master, plotly in JupyterLab.
- The time-budget path and Training's regression path were read only.
- Reproducibility across machines.
- The sign-off gate at register, which is not built.

**Suggested order.** Items 1 to 4, then 7, 5 and 6, then 8 to 14 with the six defects of §3 in
one batch. Items 21 to 23 and 40 before M2.4 starts, since register reads the run folder
through them. The rest of §4 with the 1.0 hardening.

## 13. Spark checks

A second pass on 2026-11-22 ran what the first pass had only read. Eight checks on local Spark
with the tests' fixtures and quick card config: all ran, in 152 seconds. A Sonnet agent wrote
the module without running Spark and the main thread ran it once. The module is kept outside
the repo; P1 and P2 are ready-made seeds for the tests of items 1 and 2.

| Check | What ran | Result |
|---|---|---|
| P1 | Regression slices through the real `score_edges` and `score_cells`, against row-level top-k | Confirms item 1: 30%, 28%, 13% and 9% low at 0.05% to 0.3% |
| P2 | A stratum with levels `low`, `mean`, `pooled`, `high` through the real stratum path | Confirms item 2: `mean` reports 20,000 rows for 5,000, `pooled` the whole part |
| P3 | `score_edges` on the same rows in 2, 16 and 1 partitions | New, item 83 |
| P4 | Test's metrics with edges cut over every row and over test rows only | AUC moves by 5e-6, average precision by 5e-5: item 14's second half is a matter of rule |
| P5 | Spark jobs of one Training run and one Evaluation run | Training 74 jobs by job group and 106 by the scheduler's counter, in 14 s; Evaluation 83 and 114, in 18 s (item 39) |
| P6 | That run's artifacts | No null target among the scored rows, 2.8 to 3.4% of eligible rows per period dropped (item 13); best noise share 0.0078 on 19 features, so item 3 does not show at this size; 7 of 46 floor drops have more than 20% nulls (item 4); no Training warning to lose (item 8) |
| P7 | A run with `training.fold_repeats: 2` | Confirms item 6: no warning and no key about the judged-model check |
| P8 | A run with all 171 candidates excluded | Refused before the run number: one bullet of item 7 withdrawn |

**83. Evaluation's tables depend on the partition layout, inside the binning's tolerance**
(P3).
- **What happens.** The same scored rows cut in 2, 16 or 1 partitions give different score
  edges: almost all of regression's 49 (by up to 0.07 in score) and about half of binary's 379
  (by up to 0.003). The AUC and the average precision from the cells agree to four digits
  under all three.
- **Why.** `approxQuantile` merges one sketch per partition, so its answer inside the rank
  error of 1e-4 depends on how the rows are laid out.
- **What it means.** "One run evaluated twice gives identical tables" (`review_guide_3.md` §3)
  holds on one machine reading the same parquet files. On a cluster, where the layout changes
  from run to run, the cells, the curves and the slices can differ in their low digits while
  the headline metrics hold. The guide lists this as an unconfirmed risk; it is now shown.
- **Fix.** State the promise as "to the binning's tolerance" in `evaluation.md`, or store the
  edges with the run and reuse them on a rerun.

**Still not run in Spark:** the fold dealing and the sampling on their own, a canonical-size
run (which would settle item 3 for the shipped example), and anything inside the bank.
