# EDA and Feature Checks: questions and answers

**What this is:** short answers to the questions that came up while EDA and Feature Checks were
designed, reviewed and tried (M2.2, closed 2026-11-11). Each answer names the doc or the function
that owns the detail; when the two disagree, the owner is right.

**Related:** [eda](../components/eda.md) · [feature checks](../components/feature_checks.md) ·
[dataset](../components/dataset.md) (the counts table) · [feature ledger](../components/feature_ledger.md) ·
[config](../components/config.md) · [environment](../components/environment.md) ·
`notebooks/00_eda_fc_helper.ipynb` (where each number comes from, step by step)

## Folders, configs and reruns

**Which folder do the notebooks read and write?**
The folder is computed from the config, never chosen:
`<roots.data>/<use_case>/04_feature/<data-definition hash>/`. Step 1 of notebooks 02 and 03 lists
the use case's folders with the one in use first and when each stage last ran
(`list_data_definitions`).

**I changed the config and no new folder appeared. Why?**
The hash covers what defines the data: the entity, the task, the sources' logical names, the keys,
the eligibility steps, the target, the period, the observation window, the target window and the
candidates. Key features, thresholds and other EDA or Feature Checks settings are not data: the
folder stays and the stage is rerun in it. A changed filter is new data, so the folder is new.

**What happens to my decisions when the folder changes?**
The new folder starts with an empty decision audit log: decisions belong to one data definition.
The old folder stays on disk and nothing reads it.

**When must a stage be rerun?**
- An EDA setting changed: rerun EDA. The stored Feature Checks is then refused as stale, so rerun
  it too. Any EDA rerun clears Feature Checks' output.
- A source was pointed at another path or table in the environment file: that is other data under
  the same folder. The next stage refuses, names the source and both locations, and asks for a
  rerun (after Target Factory when the config reads a model input built from the moved source).
  The folder and the decisions carry over.
- The framework was upgraded and the stage json's `schema_version` moved: rerun.
- Not caught: data that changes under the same path. A loaded source period is assumed never to
  change (`CLAUDE.md` §4, invariant 10).

**Does a file in `conf/local/` override the one in `conf/base/`?**
No. A notebook or the CLI loads the file it is given. To try settings, copy the example into
`conf/local/` and point `CONFIG` at the copy. The tests read their own frozen copies in
`tests/conf/`, so editing an example breaks no test.

**Why is the model input not under the use case's folder?**
Because it is not per use case. It is a source in the environment file with a logical name, and
several use cases may share one table: both examples read `retail_acquisition_input`.

**Can a `revert` undo the flags Feature Checks wrote?**
Yes, on purpose: a revert is a person's explicit act. Training will open with the held, excluded
and kept features in force and warn when fewer are held than Feature Checks' run held
([training](../components/training.md), requirement 1).

## The counts table

**Zero gets its own bin. What does that do to a feature with values on both sides of zero?**
When 0 occurs, two edges are added (0 and the next float above it), so the quantile bin that held
0 becomes three: the values below 0, `= 0`, and the values above. The two side bins hold fewer
rows than the others. The statistics lose nothing: the concordance and the PSI are sums over
cells, and the PSI and the charts merge the bins into about ten groups first.

**What is a lagged cell, and why is it not a column of the current cells?**
A lagged cell counts a feature's value one period earlier against the current period's target.
One check reads them: Feature Checks' time alignment, which catches a feature that knows the
target only through its latest value. A row's lagged value falls in another bin than its current
value, so one table would need current bin × lagged bin × target bin per feature: up to a hundred
times the cells. Two sets of rows with a `lagged` flag is the small form. The window's first
period has no lagged cells (there is no earlier period in the rows), and a one-period window has
none at all.

**How do a hundred fine bins become the ten groups a chart or the PSI shows?**
`merge_bins` joins neighbouring fine bins into about ten groups, a mass point keeping a group of
its own. `group_of_bins` then gives each fine bin its group. A bin below the first group (another
period's values may lie below the snapshot's) joins the first group where the caller allows it,
and is refused otherwise.

**Why is a count of positive labels called `support`?**
`support` is the count an estimate's precision rests on, named once for both tasks: events for a
binary target, units with a non-zero target for an amount. In a window it differs from
`positive_rows`: the same client is labelled in every period, so the pooled support counts
distinct clients with an event ([glossary](../glossary.md)).

## Why the method is what it is

**What is the concordance, and why one number for both tasks?**
It counts pairs of rows: the share the feature orders the same way as the target. For a 0/1 target
that is the AUC; for an amount it is the share of correctly ordered pairs. 0.5 means no ordering
information and 1 perfect ordering, whatever the task, so both tasks share the scale and the
thresholds ([glossary](../glossary.md), [eda](../components/eda.md) → The statistics).

**What does the best-order concordance add?**
For an inverted-U feature (age) the plain concordance is about 0.5. Ordering the bins by their
shrunk rate gives roughly what a small tree would reach, so the feature ranks where its
information puts it and is marked `non_monotone`. A scorecard or a monotone constraint would lose
that shape.

**Why no mutual information, VIF or Information Value?**
Mutual information is useless at low prevalence. VIF needs imputation, hides constant columns
and costs O(p³). Information Value and WoE would be a second scale beside the concordance with a
binning of their own.

**Why are nulls never filled, and what do the null findings mean?**
A null is a state of its own in every statistic; a null that means a value is filled upstream.
`missingness_leak` (a flag): being filled predicts the target strongly, so ask how the field gets
filled. `nulls_informative` (a note): a weaker signal; keep nulls as their own group.
`nulls_may_be_zeros` (a note): fill the zeros upstream. Many columns sharing one
`nulls_informative` value usually share one null set: roll-ups are null while a client is newer
than the months they span, which often marks a population worth a filter of its own.

**Why does EDA analyse one snapshot period by default?**
One conversion is positive in several window rows of the same client, so pooled rows overstate
the evidence. A snapshot has one row per client and the latest matured labels. The window
statistics come from Spark counts beside it.

**Why is nothing sampled?**
A client sample would make every number in the report approximate. The window is never
collected: its statistics are Spark aggregates over every row, and one period fits in pandas
even at the bank's size.

**What does a flag do, and how does it differ from a note?**
A flag says "this should not enter a model as it is": it holds the feature out of training at
both automation levels until a person keeps or excludes it. A note says "look at this" and never
affects training. A `keep` names the findings it settles, so a later, different flag holds the
feature again; an `exclude` removes the feature whatever its flags.

**A feature with little support was flagged. Why was the check not skipped?**
No check skips for low support. Each finding states its support and whether the value is more
than two standard errors past the threshold, and errs towards a hold.

**Why does time alignment lag the feature instead of comparing forward and backward labels?**
On an acquisition target the backward label is almost always 0 on the eligible rows, and with
holders included a legitimate holding feature and its shifted twin both predict the past event
perfectly. What gives a look-ahead away is the signal collapsing when the value is one period
older. The lagged value is read in the window's direction, so a flip (0.65 to 0.35) is caught too.

**Why is concordance stability a test and not the range across periods?**
At 50 events per period a concordance's null standard error is about 0.04, so six periods show a
range near 0.10 from noise alone. Cochran's Q weighs each period by its precision; a floor on the
range relative to the feature's signal keeps a large population's tiny wobble from flagging.

**Which periods do the drift findings compare?**
`psi_window`: the window's first period against its last. `psi_latest`: the window's last period
against the latest period. `concordance_unstable`: every window period. Periods after the window
are compared without labels, because their target windows reach into the validation period's;
the validation period itself is never read.

**Why 20 events for a bin but `strata.min_events` for a stratum or a period?**
A 95% interval's half-width is about 1.96/√k of the rate: ±44% at 20 events, ±28% at 50. The
stricter rule would grey out every decile of a rare target, and the interval already shows the
uncertainty.

**Where do the default thresholds come from?**
From practice, not from literature, and they start sensitive; they are to be reviewed on real
data. The PSI bands 0.10 and 0.25 are Lewis's (1994, via Siddiqi): they ignore the sample size
and the number of bins (Yurdakul 2018), so they are labels, not tests. `too_strong` at 0.80 sits
below the synthetic oracle's ceiling of 0.84 with every feature: one feature above it is the
outcome or a leak. Strength is not legitimacy (Kaufman et al. 2012): a leak is a value known
only after the period, which is why time alignment exists beside it. Common practice elsewhere:
95% missing (`scorecardpy`), near-constant at 95/5 (caret), 50 levels (ydata-profiling),
|ρ| ≥ 0.9 (caret, ydata-profiling). Intervals are Wilson's (Brown, Cai and DasGupta 2001), and a
standardised difference of 0.25 reads as "differs" (Austin 2009).

## Reading the tables and the reports

**In which order are the key features shown?**
The ones the config lists first, then the ranking's top N, each by rank. Listed features never
count towards `top_n`. A candidate correlated above `max_correlation` with a key feature already
chosen, listed ones included, is skipped and names it in `represented_by`, so the report does
not show three prints of inflow, outflow and their total. The ranking table itself stays in rank
order.

**What does EDA's sources table show?**
Per compared period: the spine's rows, then for each joined feature source the share of those
rows that found a row in it. 0.85 for the synthetic extract means 85% of the clients have a row
there and the others have nulls in all of its features. A share that drops in one period means
the source was loaded late or in part.

**A finding's value reads `< 0.0001`. What is it?**
A p-value. `stability.concordance_unstable` tests whether a feature's concordance is the same in
every window period (Cochran's Q); its value is the test's p, practically zero for a feature
whose signal moves.

**How many groups does a numeric deep dive show?**
A numeric with at most `strata.max_levels` distinct values is shown value by value; above that it
is merged into `strata.max_levels` groups (10 by default).

**Why does the ledger have a row for `cc_flag`?**
It is the column the config's target is built from (`data.target.column`), not a part of the use
case's name. It is excluded from the candidates as lineage, and the ledger keeps its row to say
so. The use case's name is used whole wherever it is used: the folder and `target_<use_case>`.

**What is `external_assets_band` in the helper notebook?**
A synthetic categorical from the second feature source: the band of a client's assets held
elsewhere. The helper follows it because it comes from the joined source, so about 15% of its
values are null.

## Code conventions

**What does `# fmt: skip` mean?**
It tells `ruff format` to leave that one statement as written. It sits on hand-laid lists and
calls that read better in logical groups than one item per line.

**How long should a docstring be?**
As long as the function is hard to read. A textbook statistic gets one line with its formula. A
function that reshapes frames states the grain it receives, the grain it returns and the columns
(`CLAUDE.md` §1, rule 9).

**The docs and the code cite Q-, R-, A- and V-numbers. Where are they?**
In git history. They number the questions, remarks and plan defaults of the design rounds, whose
records are deleted when a stage closes. The sentence that cites one states the outcome. N-numbers
are the null-value assumptions in [eda](../components/eda.md) → Nulls.
