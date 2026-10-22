# Decisions for the LDS's review
_Written 2026-10-22 for the LDS · the 20 decisions that most shape the framework, chosen as if none
had been read yet · the decisions themselves are in `docs/decisions.md` (high-impact table); this
page only says why each matters and what feedback is wanted_

**How to use.** Read in the order below: the frame first (what is built, how it ships, how versions
coexist), then the ML rules, then the artifacts and the use-case contract. Tick a row when it is
reviewed; objections go into the daily sync or as a comment on the row. The SDS removes a row once
the LDS has reviewed it and adds a new high-impact decision when one lands, so the list stays short.

## The frame

| # | ID | What it decides | Why it matters to the LDS | Feedback wanted |
|---|---|---|---|---|
| 1 | D-021 | Definition of done = release 1.0: a config and the guided notebooks take a new use case to production scores; the feature-store and data-observability integrations are in, thin; no LLM; release 1.0 is the first change request and carries the framework only | Sets what "done" means, and what December delivers versus February | Is "framework only" in the first change request right, and do two thin integrations count as done? |
| 2 | D-020 | Phase 2 scope: binary and regression end to end; FLAML is the only modelling path (a use case may restrict it to one family); the predefined path and Optuna move to Phase 3; the proof of extensibility is the per-task spec | Fixes what is built and what counts as proof that a third task is cheap | Regression as the second task, and FLAML only for the first release |
| 3 | D-022 | The plan: walking skeleton, then two rounds each followed by a run-through; depth levels; M2 in four stages; the dates; the tests expected at the pre-release and at release 1.0 | The dates and the depth per component are what the LDS is reviewing now (OD-01) | The dates, the depth table in `timeline_proposal.md`, the M3 priorities |
| 4 | D-047 | Each use case pins its framework version and upgrades at its own pace; many versions run at once; a use case may take a newer version within its image's year | Every compatibility rule and the shared-table design follow from it | Is per-use-case pinning how teams will actually work inside the bank? |
| 5 | D-007 | Forward compatibility is about outputs: `schema_version` and migrations everywhere; shared tables only grow within a major version; formats freeze from release 1.0's first row; an artifact inventory | The promise every later version must keep | The freeze point, and the "columns only added, never renamed" rule for shared tables |
| 6 | D-024 | A versioned library with a CLI and a Python API, no service layer; shipped in the base image through Nexus; the Public API is the stage functions, `run`, the CLI and the config schema | How every DS consumes the framework, and what may never change silently | Anything missing from the Public API; the base-image channel |
| 7 | D-033 | Lifecycle vocabulary: register (a defended model the DS wants to keep), promote (the approved PR is the sign-off; a verified bundle), deploy (the change request); the model key; the steps are thin but real in M2 | Governance of every live model | Is "registered = defended and kept" the right bar; the model key's fields |

## The ML rules

| # | ID | What it decides | Why it matters to the LDS | Feedback wanted |
|---|---|---|---|---|
| 8 | D-030 | A multi-month observation window; train and test split by client; one out-of-time validation month; label-using checks see train-split clients only; label-free checks may use later months, never the validation month | The core data discipline (`CLAUDE.md` §4) | The train-split-only scope of label checks, which is marked soft |
| 9 | D-083 | Every choice among variants or trials weighs train and test only; validation never informs a choice; no second validation month | Keeps validation honest at the cost of a test-vs-validation gap that mixes overfitting with selection | Agree that test may choose, with that cost stated in reports? |
| 10 | D-117 | Sampling in Phase 2: uniform negative downsampling for rare binary targets, a random client sample for common targets and regression, none when the rows fit; no sample weights; advanced sampling in Phase 3 | The LDS dislikes sampling; this fixes what Phase 2 does about it | Is uniform downsampling plus the prior shift acceptable for rare targets in Phase 2? |
| 11 | D-049 | A prior-shift offset whenever sampling happened; a general calibration step (Platt in M2, isotonic in M3) on by default for `probability` decisions; calibration is a release requirement; retail propensity defaults to `probability` | Scores are compared across products, so calibration has to be right | The default to `probability`; Platt before isotonic |
| 12 | D-031 | No model without EDA and Feature Checks for the same data definition; a person signs off the final feature list before register, at every automation level; an LLM never passes the gate; low thresholds; the sign-off view shows train-only evidence | The human gate the CDS asked for, and its placement | Is a sign-off over the final list, not every candidate, enough? |
| 13 | D-029 | Target Factory builds targets only, from a declarative spec; targets are per use case; what an event is (a flag 0 → 1 in any window month; leavers null by default); automatic lineage exclusion; no lineage list for upstream targets | Target leakage and target semantics for every use case | Leavers as null by default; no lineage list required for upstream targets |
| 14 | D-094 | Training under FLAML: the framework encodes categoricals; inference calls the booster directly; the calibration chain (general calibration, then the prior shift in logit space); `model_hash` over parts; a trial budget plus seeds by default | ML-critical mechanics the LDS reviews in full | The order of the chain; the trial budget as the default |

## The artifacts and the use-case contract

| # | ID | What it decides | Why it matters to the LDS | Feedback wanted |
|---|---|---|---|---|
| 15 | D-051 | A versioned model bundle with plain-data parts; a family is offered only once a lossless non-pickle round trip is verified; no pickle for anything promoted (the sandpit may pickle) | The security blocker, and the main constraint on model families | The sandpit exception; the M2 families `lgbm`, `xgboost`, `catboost` (D-037) |
| 16 | D-052 | A `recipe_hash`; a refit is a new run linked to its parent; the refit is how retraining in production works, with a label-free agreement check; Phase 2 keeps the data definition | How the CDS's preference for retraining in production is met | The agreement check; what "deployed" then records (OD-27) |
| 17 | D-016 | Scores end at the master layer (long, traceable, one schema everywhere); consumable tables are built outside; batch-scoped and write-once; reserved columns for later tasks | The one output every consumer reads | The master-layer columns (`inference.md` requirement 4); manifests beside or inside the scores (OD-18) |
| 18 | D-043 | Config: YAML, plain data, one file per use case; automated filters as ordered rules, never outcome lists; human decisions live in the audit log | The use-case contract | Rules instead of lists for filters; one file per use case |
| 19 | D-125 | The decision audit log: the config is the intent, frozen after the target; every later decision is an append-only entry; replay gives the run's input; a maintained list of settings a decision may change; packed into the bundle at register | Answers the LDS's verbosity concern and defines how human decisions reproduce | The closed list of operations, the settings list, the replay rules (`config.md`) |
| 20 | D-023 | Two automation levels, `autonomous` and `assisted`, running the same checks, differing in human time; the `profile` field is renamed at M4; the speed claim is "a registered candidate in days to a few weeks" | The product promise and how teams will use the framework | The two-level cut and the speed claim's wording; the level mapping (OD-25) |

## Next in line
Not in the twenty, worth reading after them: D-088 (identities and hashes), D-106 (validation
inside training; FLAML gets the client groups), D-098 (evaluation per month; denominators), D-082
(positive events, not rows), D-040 (monitoring: frame deep, content light), D-054 (the drift
reference).
