# Stage 3 audit of steps 2 and 3: the answers record

_The EDS's answers of 2026-11-23 to the items of [`audit_steps_2_3.md`](audit_steps_2_3.md),
verbatim, with the outcome for the fix plan. Each item as asked is in that file under its
number. Q676 to Q686 were answered the same day (§3), with the word to build: "Now after
recording the answers, orchestrate the workflow and apply all the fixes; utilize the proper
model levels for each individual tasks, only run small tests during the process but do run a
full suite test afterwards. When finished, make sure all docs are up to date and rework the two
outstanding review_guides so that it reflects the current state."_

**Status: built 2026-11-23.** Every approved item is applied; what the build decided on its own
(A136 to A164) and what stays open (Q687 to Q693) lead the two review guides,
[`review_guide.md`](review_guide.md) and [`review_guide_3.md`](review_guide_3.md).

## 1. The answers

| Item | The EDS's answer | Outcome for the plan |
|---|---|---|
| 1 | "Apply the fixes, but explain how you measure “capture, rate and lift ” on the regression target" | Both parts are built: finer top score bins for regression with a tail pass, and "not available" below the finest bin. Only the top is made finer, so the cells per replicate stay within about twice today's (regression's cells also carry 20 target bins), and the tolerance is measured as A103 did for binary. The explanation: §2 |
| 2 | "Shouldn’t the fix simply be that we are refusing input columns named mean, pooled and all? Honestly no column should be named like that anyways" | Settled in §3: Q676 |
| 3 | "best_noise_share being 0 is the lowest threshold possible and it means that the feature being pruned also had exactly zero contribution, no? I agree that if you run pruning, every column should get at least one (if not two) turns - if this doesn’t use up too much time - but I don’t really understand this exact edge case. Also, in the evidence, I don’t really see a huge drop in performance" | Settled in §3: Q677 |
| 4 | "Which of the model families would actually use this information, what does “each library sends nulls down their own side of a split” exactly mean? Does It mean that this doesn’t have to be spun off into a new “feature_filled” binary column because all families do it by default? If you apply this fix, wouldn’t pruning get overly complicated?" | Settled in §3: Q678 |
| 5 | "Fix as proposed" | Built as the item's third option: Evaluation computes train's in-sample concordance on the same cells from `oof.parquet`, so the gap compares like with like and the "about 0.01" clause goes |
| 6 | "Fix as proposed" | The winning configuration is fitted on every dealing and the means compared |
| 7 | "What’s the fix here?" | Settled in §3: Q679 |
| 8 to 10 | "Fix as proposed" | As proposed |
| 11 | "Just silently drop the feature, this is such an edgewise" | Dropped from the partial dependence with no error and no warning. Settled in §3: Q680 (one `unavailable` line or none) |
| 12 | "I’m okay with the fix, but why is permutation table only presented on the sample? It’s not a dotplot" | The guard is built. Settled in §3: Q681 (which rows it runs on) |
| 13 | "Keep the null-target test rows for reference then" | The test part's null-target rows are scored and kept for the drift reference; the metrics leave them out |
| 14 | "Skip negligible points" | Skipped whole: the edges stay cut over both parts (A115 stands) and view 14 stays |
| 15 to 23 | "Fix all as proposed" | As proposed |
| 24 | "I don’t understand what’s the problem here" | Settled in §3: Q682 |
| 25 | "Fix as proposed" | Built, then deferred to 1.0 on 2026-11-24 ("Since we are at pre-release, do we need it?"): the contract is tested on the run the suite writes; a frozen run folder per format version from 1.0 (roadmap backlog) |
| 26 | "What is T44?" | Settled in §3: Q683 |
| 27 to 29 | "Fix all as proposed" | As proposed |
| 30 | "What’s the problem and the fix here?" | Settled in §3: Q684 |
| 31 | "Fix as proposed" | As proposed |
| 32 to 39 | "Is and of these real warnings that would go bad?" | Settled in §3: Q685 |
| 40 to 58 | "Do all refactors" | All, after the answers below |
| 59 to 68 | "Update all tests" | All |
| 69 to 82 | "Update all docs, but after the refactoring only" | All, after the refactors. Item 82 is settled in §3: Q686 |
| Small things (§9) | "In the small things, try to fix all duplicates and edge cases where it’s reasonable that an error could happen; don’t worry about artifacts changes, we are still in pre-release mode." | The duplicates and the reasonable edge cases are fixed; artifact shapes may change |
| 83 | "Yes, change promise." | `evaluation.md` states the rerun promise to the binning's tolerance |

## 2. Explanations asked for

**Capture, rate and lift on a regression target (item 1).** A list is the top share of a part's
rows by score, per period (`statistics/metrics.py:294-299`):
- capture: the list's summed amount over the part's total amount;
- rate: the list's summed amount over its rows, the mean amount per listed row (binary's
  precision);
- lift: the rate over the part's mean amount.

Both sums come from the score bins, added up from the top bin down, with the last bin split in
proportion to its rows. That split is item 1.

**T44 (item 26).** Trap 44 in `docs/context/lessons.md`: pandas writes a column whose values are
all null as parquet type `null`, so a table's schema changes with its data and Spark may not
read the column. Q670 settled the fix: once in `write_parquet` for every stage, in M2.4. Item 26
only adds that Evaluation's tables are hit too.

## 3. The second round's questions, answered 2026-11-23

The EDS's answers, verbatim. Every default below is taken.

| Question | The EDS's answer | Added to the default |
|---|---|---|
| Q676 | "Default" | |
| Q677 | "For now, go with the default, but in addition, create a short worknotes report where you analyze how likely this behavior happens given the data size, number of columns and feature concordance strength and how to mitigate this in the future, because I don’t love this default option but only want to tamper with it if it actually matters" | The report: `pruning_noise_share.md` |
| Q678 to Q683 | "Default" | |
| Q684 | "Default, but in addition please create a worknotes report on all the washings you do, the potential issues and how you are solving backward/forward compatibility with non-major releases" | Read as "hashings". The report: `hashes_and_compatibility.md` |
| Q685 | "Default" | |
| Q686 | "Default" | |

**Q676 (item 2). Refuse the names, or fix the code?** `all` would be a column name; `mean` and
`pooled` are values inside a stratum column (`segment = "pooled"`), so refusing column names
covers `all` only, and a value is data nobody chooses. *Default:* fix in code (two flags, the
pooled cells passed apart) and refuse nothing, as a source name is never refused elsewhere.

**Q677 (item 3). Pruning.** At a threshold of 0 the pruned features are those with no
contribution in the pruning model, which has 150 splits per fold. On a wide frame the noise
columns get no split either, so nothing was compared with noise, and "unused by 150 splits" is
not "useless to the model the search fits". The loss in the simulation is modest (AUC 0.8187 to
0.8118). *Default:* a noise share of 0 prunes nothing and warns; the pruning model offers every
column about twice (trees scaled to the columns, a column share per tree), its numbers fixed
after measuring two or three sizings on the simulated frame and on `dev`.

**Q678 (item 4). The floor and nulls.** All four families take nulls natively and the encoder
imputes nothing, so no `feature_filled` column is needed: LightGBM and both XGBoost families
send null rows to the better side of each split, CatBoost orders nulls below every value.
LightGBM is shown by the run; the others by their documented behaviour. Pruning is untouched.
*Default:* the floor passes a feature when its value concordance or its null-indicator
concordance on train clears the threshold; one test runs all four families.

**Q679 (item 7). The three fixes.**
- A negative target under `tweedie` or `poisson`: refused in `_open_run` from the train
  target's minimum, naming the objective.
- Selection leaving no feature, and a noise-column name: the model-free rules run before
  `create_run` (refactor 42).
- A regression fold with one target value: refused in `check_folds`, before the collect.

*Default:* build all three.

**Q680 (item 11).** *Default:* the feature leaves the partial dependence with one line under
`unavailable` ("null on every sample row"), which the view shows; no warning.

**Q681 (item 12). Which rows permutation importance runs on.** The limit is compute, not
display: each cluster is re-scored five times on the driver. Options: (a) the 5,000-row sample
with the guard; (b) its own larger hashed test sample, such as 50,000 rows of the features and
the target; (c) every test row inside Spark, clusters × 5 scoring jobs. *Default:* (b).

**Q682 (item 24). FLAML's names.** The config says `estimator_list`, `max_iter`, `lgbm`,
`xgb_limitdepth` and `ap`, and stored keys follow (`oof_ap`). They freeze at 1.0 and Phase 3's
Optuna path would have to use them. D-037 chose FLAML's names knowingly. *Default:* no change;
the item is dropped.

**Q683 (item 26).** *Default:* nothing now; Evaluation's tables join the backlog line of the
`write_parquet` fix (Q670).

**Q684 (item 30). Six weak spots in step 1's foundations.**
- (a) The identity hashes cover defaulted fields, so a new field with a default moves every
  data-definition hash and orphans the audit log and the earlier runs.
- (b) `load_bundle` refuses another `hash_version`, although the model hash is over file bytes.
- (c) One unreadable `run.json` stops `list_runs` and `find_run` for the use case.
- (d) `create_run` reads every audit log strictly to collect run numbers.
- (e) A `run` entry that loses a race raises after the stage is committed.
- (f) The run number and the folder swap rest on local-filesystem behaviour.

*Default:* (c), (d) and (e) now; (a) and (b) as one open decision before 1.0; (f) with M2.4's
transport.

**Q685 (items 32 to 39). What to act on.** Likely to go bad: 32 and 33 on a cluster, 35 on a
shared node, and the driver's memory at bank size (39). *Default:*
- now: a `threads` setting in the environment file (35), a random token in the temporary names
  (37), and the cheap passes of 39 (the explanation sample's three scans, the count before the
  train collect, the repeated loads);
- M2.4: 32, with the transport;
- the bank trip: 33 and 36;
- nothing: 34 (gone with refactor 40) and 38.

**Q686 (item 82). The notebooks.** *Default:* `notebooks/README.md` allows a package-built line
of run facts (the opening, a summary, the warnings) as HTML output, and the optional `shap`
cell of notebook 05 stays.
