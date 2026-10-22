# Questions for the planning session, round 5
_Updated 2026-10-22 after the fourth round of answers. Only open questions are listed; answered
ones are recorded in `docs/decisions.md` (D-082–D-122) and the owner docs. Each question carries
Claude's proposed default, so "default" is enough as an answer, and every decision it cites is
summarised in brackets (D-122). Findings behind the questions: `holistic_review.md`. Dates:
`timeline_proposal.md`. New numbers continue from Q301; Q297–Q299 belong to `pickle_summary.md`._

**Who:** SDS, LDS, or both.

## A. For the SDS and the LDS

| # | Question | Default | Who |
|---|---|---|---|
| Q218 | Accept the reshaped plan in `timeline_proposal.md`? Round 1 to 12-08 (stages of 4–6 days; the week of 11-30 counted as lost); run-through 1 and the pre-release by 12-18 (code into the internal repo, not production); a slowdown to 01-01; round 2 to 02-05; release 1.0 by 02-19, submitted as the first change request (D-115: the year-end freeze makes the first change request release 1.0, framework only). Also the depth per component with nice to haves (OD-01: depth per component per phase). It moves categoricals, refit and the deep EDA, Feature Checks and Evaluation to round 2, makes the window ablation a nice to have, and keeps monitoring's content light (D-112: monitoring's frame built properly, its content light) | Yes | both |
| Q223 | Round 1b (11-23 – 12-08, about 8 working days): exit-point shapes close to final, calibration right (D-104: scores are compared across products, so calibration is a release requirement), a presentable EDA + Feature Checks report. Must anything else be in the pre-release, e.g. for the year-end showcase? | These three; the report is the first to move to round 2 if time runs short | both |

### Q241. The config and the audit log
_OD-10: how the config can stay unchanged while every downstream decision, by a rule or a person,
is recorded._

**The proposal in five points:**
- **The config is the intent, frozen once Target Factory has built the target.** Nobody edits it
  afterwards.
- **Every later decision is an entry in an append-only log:** who (a person or a rule), what, why
  and the evidence. Entries are never edited; a reversal is a new entry. Decisions inside a
  training run (selection drops, the winning family) are logged as run outputs, not inputs.
- **Replay gives a run's one input:** the config plus entries 1 to n, applied in order and
  validated by the schema, is the resolved config a run trains on. Each run records the entry it
  replayed up to.
- **The log can't change the data definition** (entity, sources, eligibility, target, window,
  candidates). Changing those means a new config, with fresh EDA and Feature Checks.
- **What it replaces:** human keep / exclude lists move from the config to the log (amends D-043:
  human feature decisions live in the config as keep / exclude lists with one reason per group).

**The verbose table.** Card acquisition within 3 months on the synthetic mart, entity A.
`show_decisions(config, entity)` prints it in a notebook; each report's choices block shows the
entries up to its run, and the model card the slice up to the registered run.

| # | Date | By | Stage | Decision | What | Reason | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | 10-27 | rule `target_lineage` | Target Factory | exclude | `cc_flag` | Builds the target | lineage file |
| 2 | 10-27 | rule `quality.all_null` | Feature Checks | exclude | 1 feature | No values in the window | checks log, step 1 |
| 3 | 10-27 | rule `quality.near_constant` | Feature Checks | exclude | 1 feature | 99.9% one value | checks log, step 2 |
| 4 | 10-27 | rule `leakage.too_strong` | Feature Checks | flag | 2 features | Univariate AUC 0.97 and 0.88 | report → Leakage |
| 5 | 10-27 | rule `stability.psi` | Feature Checks | flag | 5 features | PSI above 0.25 across the window | report → Stability |
| 6 | 10-27 | person (DS) | Feature Checks | exclude | the 2 flagged in #4 | Set after the offer, so not known at scoring time | #4; report → Leakage |
| 7 | 10-27 | person (DS) | Feature Checks | keep despite flag | the 5 flagged in #5 | Digital adoption trend; monitoring watches it | #5; report → Stability |
| 8 | 10-28 | stage | Training | run `r1` | input = config + #1–7 | — | training report |
| 9 | 10-28 | rule `selection.importance` | Training | dropped (run output) | 71 features | Below the importance floor | ledger, run `r1` |
| 10 | 10-28 | person (DS) | Settings | change | `training.max_iter` 100 → 300 | AUC still rising at the last trials | training report, `r1` |
| 11 | 10-29 | stage | Training | run `r2` | input = config + #1–10 | — | training report |
| 12 | 10-29 | person (DS) | Sign-off | exclude | `nationality` | Not used for product targeting | sign-off view, `r2` |
| 13 | 10-29 | stage | Training | run `r3` | input = config + #1–12 | — | training report |
| 14 | 10-30 | person (DS) | Sign-off | approve | the 61 features of `r3` | Each defensible; flags reviewed | sign-off view, `r3` |
| 15 | 10-30 | person (DS) | register | register | `r3` as version 1 | Candidate for production | model card |
| 16 | 11-02 | person (reviewer) | promote | promote | version 1 | Approved pull request | registry record |

**Replay: how the table rebuilds the state.** Entries apply in order. Each row below is the state
after that entry, which is exactly what a run started at that point would train on.

| After | Excluded | Kept despite a flag | Open flags | `max_iter` | Input hash |
|---|---|---|---|---|---|
| config only | — | — | — | 100 | `h0` |
| #3 | 3 (#1 lineage, #2–3 quality) | — | — | 100 | `h3` |
| #5 | 3 | — | 7 (#4 leakage 2, #5 stability 5) | 100 | `h5` |
| #6 | 5 (+2 leaks) | — | 5 | 100 | `h6` |
| #7 → run `r1` | 5 | 5 | 0 | 100 | `h7` |
| #9 | unchanged: a run output, not an input | | | | `h7` |
| #10 → run `r2` | 5 | 5 | 0 | 300 | `h10` |
| #12 → run `r3` | 6 (+`nationality`) | 5 | 0 | 300 | `h12` |
| #14–16 | unchanged: the sign-off, register and promote are the trail | | | | `h12` |

`resolve_config(config, entity, upto=12)` returns the state run `r3` trained on, each value
pointing at the entry that set it:

```yaml
# resolved: cc_acquisition.yml + entries 1–12 (input hash h12)
features:
  exclude:
    - cc_flag                                  # 1, rule target_lineage
    - legacy_risk_grade_trap_all_null          # 2, rule quality.all_null
    - paper_statement_flag_trap_near_constant  # 3, rule quality.near_constant
    - cc_preapproval_score_trap_leak           # 6, person: set after the offer
    - cc_campaign_response_score_trap_leak     # 6
    - nationality                              # 12, person: not used for targeting
  keep_despite_flags:
    - login_digital_mobile_cnt                 # 7, person: digital adoption trend
    - login_digital_mobile_cnt_0_2_months_avg  # 7 (and three more rollups)
training:
  max_iter: 300                                # 10, person: AUC still rising
```

What makes the rebuilt state trustworthy:
1. **Order decides.** A later entry on the same feature or setting wins: an "include back" after
   an "exclude" restores the feature.
2. **Replaying to any point reproduces any run.** `upto=7` gives `r1`'s input, so an old run can be
   rerun or compared without guessing what was decided at the time.
3. **Rule entries can be checked.** Rerunning Feature Checks on unchanged data reproduces #1–5. If
   the data was restated and a rule now decides differently, replay shows the difference, and the
   person entries that cited the old rule entry (#6 cites #4) are flagged for a look rather than
   applied silently.
4. **Stale entries fail loud.** An entry naming a feature that is no longer a candidate stops the
   replay with the entry number.
5. **The trail never changes the input.** Run outputs (#9) and the sign-off, register and promote
   entries (#14–16) are recorded but leave the resolved config alone.

**Writing an entry** is one call in a notebook, or the same through the CLI (`python -m
core_modelling decide`):

```python
record_decision(
    "conf/base/cc_acquisition.yml", entity="entity_a",
    exclude=["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"],
    reason="Set after the offer, so not known at scoring time",
    evidence="feature_checks#leakage",
)
```

It is refused at once when a feature isn't a candidate, the reason is missing, the change touches
the data definition, or a setting fails the schema.

**The cost.** The current state can't be read from the config file alone: a person needs
`show_decisions` or `resolve_config`. The framework gains three public functions (record, show,
resolve) and one CLI command.

**Questions** (each with options; the recommendation first):
- (a) **Where do people's feature decisions live?** **Who:** both.
  - A. In the log, as above: the full trail (who, when, why, in what order); the config file never
    changes. Recommended.
  - B. In the config, as keep / exclude lists (today's D-043: human decisions as lists in the
    config, one reason per group): the current state readable in one file; the trail only in git
    history; every edit changes the config hash.
  - C. Both: lists in the config, with a log entry written automatically from each change: a
    readable file and a trail, but two sources of truth that can disagree.
- (b) **What may the log change after Target Factory?** **Who:** both.
  - A. Feature decisions, settings (budgets, thresholds, sampling) and sign-offs, each with a
    reason; only the data definition needs a new config. Recommended: the config file truly never
    changes.
  - B. Feature decisions and sign-offs only; a settings change is a new config version.
  - C. Everything, including the data definition, with EDA and Feature Checks rerun automatically.
    Not recommended: EDA's findings would no longer describe the data being modelled.
- (c) **Are rule outcomes entries in the log?** **Who:** LDS.
  - A. Yes, as #1–5 above: one table holds the whole trail, and a rerun on restated data shows up
    as a difference. Recommended.
  - B. No: the log holds people's decisions only; rule outcomes stay in the Feature Checks log and
    the feature ledger. A shorter table, but the trail is split across places.
- (d) **What identifies a run?** **Who:** SDS.
  - A. The hash of the resolved input: two runs on the same state share it, however that state was
    reached (amends D-088: `run_id` = config hash + entity + timestamp). Recommended.
  - B. The config hash plus the last entry number replayed: readable, but the same state reached
    by different entries gets different identities.
- (e) **Where are entries stored?** **Who:** SDS.
  - A. One small file per entry (`decisions/0006.json`): no appending, which may be switched off on
    the bank's HDFS (unverified); two people writing at once can't interleave. Recommended for now.
  - B. One appended file per instance: one file to copy, but needs append on HDFS.
  - C. A shared table: queryable across use cases, but every pinned version must write the same
    schema (D-089: shared tables only grow within a major version). Recommended later, for
    registered slices, with the registry tables in round 2.
- (f) **Who may write a person's entry?** **Who:** LDS.
  - A. Any DS on the use case; the entry names the person. Recommended.
  - B. Only the use case's owner.
  - C. Any DS, but the sign-off (D-076: a person signs off every feature before register) only by
    the owner.
- (g) **Usability:** is the verbose table what you'd want to read, and the replay view enough to
  see what a run used? **Default:** yes. **Who:** both.

### Q276. Refit: what we refit on, and which checks stay possible
**What a refit is.** After a model is evaluated and accepted, it can be retrained with the same
features and hyperparameters on more data (D-052: an optional refit on more data after
evaluation). The result is one more fit of the same recipe (D-096: a fitted model is one fit of a
recipe, and production retraining is such a refit, checked against its parent).

**(a) What do we refit on?** **Who:** both.
- A. **No refit:** the evaluated model is registered as is. Every metric belongs to the model that
  scores; the test clients' rows are never trained on.
- B. **All clients, same window:** train and test clients over the observation window. The
  validation month is still later and unseen, so the refit gets its own honest number.
- C. **Extended window ("all data"):** the window moves forward to the latest months whose labels
  have matured, usually including the validation month. The most recent data, but no month is
  left to validate on.

**Recommendation:** A by default (the refit stays optional); B when a refit is wanted in the
sandpit; C only as retraining in production (OD-27: whether production has the data and compute
to retrain), with the checks in (b).

**(b) Which checks stay possible?** **Who:** both.

| Check | A. No refit | B. All clients | C. Extended window |
|---|---|---|---|
| Metrics on the card | the model's own | the parent's, plus the refit's own validation score | the parent's only, labelled "not this model" |
| Validation month | scored | scored | none left |
| Agreement with the parent on the latest month (rank correlation, top-N overlap, score PSI) | not needed | useful | the only check; a large difference stops it until a person looks |
| Encoder levels | its own | inherited; new levels go to `__other__` and are counted | inherited, as in B |
| Calibration | checked on validation | refitted, checked on validation | refitted; checked only once labels arrive (monitoring) |

**Question:** adopt the recommendation in (a) and the checks per column in (b)? **Default:** yes.

## B. For the SDS

### Q281. Which functions are "public"?
**Your question:** with several active versions, each tied to its base image, why is this a
problem? **It isn't, while a use case stays on its version.** It matters when a use case moves up.
Its own code calls framework functions by name: the copied notebooks, the extension functions in
its repo (D-090: custom builders live in the use case's repo, never in the framework) and the CLI
calls in its schedule. If the newer version renamed or removed one of them, the move breaks right
there. A "public API" is just the list of functions we promise to keep working across versions, so
moving up stays painless; everything else may change freely. D-107 (compatibility is about
outputs; wrappers for renamed functions matter little) already lowers the stakes, so the list can
be short.

**Options:**
- A. **A short public list:** the stage functions, `run`, the CLI commands and the config schema.
  The shipped notebooks call only those, which a small test checks. Recommended.
- B. **No list:** every function may change; a use case re-tests its notebooks and extension code
  whenever it moves up. Least work for us, most for each use case.
- C. **Everything public:** nothing is renamed without a deprecation. Safe, but it freezes the code.

**Default:** A.

### Q292. Where a score's product and activity come from
**What it's about.** Each row of the master layer (D-103: the framework's own traceable scores
table; consumable tables are built outside it) has to say which product (e.g. Credit Cards) and
which activity (e.g. Activation) the score is for. Consumers select scores by these two, and the
retail platform's table has both as columns. The question is where the framework gets the two
values.

**Options:**
- A. **Two fields in the use case's config** (`product: Credit Cards`, `activity: Activation`),
  checked at load against a list of allowed values in `conf/local/`, so "Credit Card" and "Credit
  Cards" can't become two products. Recommended.
- B. **Parsed from the use case's name** (`cc_acquisition` → Credit Cards, Activation): no new
  fields, but a naming convention becomes data, and renaming a use case changes its product.
- C. **Left out:** consumers map use cases to products themselves. Least for us; every consumer
  keeps its own mapping.

**Default:** A.
