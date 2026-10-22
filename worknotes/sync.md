# Sync page
_For the SDS and the LDS · last updated: 2026-10-22 (planning set, round 5) · last sync: 2026-10-13 (2026-10-14: CDS prep only)_

**New decisions since the last sync:** D-056–D-123 (`docs/decisions.md`); D-082–D-123 are the answers to the holistic review (2026-10-20 to 10-22), except D-110 (pickle scope)

Detail behind each item: `worknotes/log.md`. Open decisions (OD-nn): `docs/roadmap.md`. How this
page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
Tags per D-084: **needs decision** (at most five) or **for information**. The list was drained on
10-20 at the SDS's request; the synthetic data left it on 10-21, reviewed and accepted by you.
Everything else is covered by the planning set below or by D-073–D-123.
- [ ] **Planning-session set, round 5** (needs decision) — `worknotes/timeline_proposal.md` (the
      plan: two build rounds, each followed by a run-through; stages sized in days; the lost week
      of 11-30 and the year-end slowdown), then `worknotes/holistic_review_questions.md` section A
      — feedback wanted: the plan (Q218) and round 1b's content (Q223); the audit log (Q241),
      reframed with replay rebuilding the state and seven sub-questions with alternatives; the
      refit (Q276): what we refit on, and which checks stay possible.
- [ ] **The answers as decisions** (needs decision) — `docs/decisions.md` D-082–D-123 —
      feedback wanted: D-082 (positive events), D-083 (train and test choose, never validation;
      `CLAUDE.md` §4.4 reworded), D-093 (M2 never lesser than the crunch), D-094 (training under
      FLAML, the calibration chain), D-098 (per-month test metrics; denominators). D-103–D-123
      record our answers of 10-21 and 10-22: check the wording, especially D-112 (monitoring: the
      frame built properly, the content light) and D-115 (the first change request is release
      1.0, framework only; a model's first deploy comes after it).

## Questions for the LDS
- **The planning set** (above): section A of `worknotes/holistic_review_questions.md` (Q218,
  Q223, Q241, Q276).
- **Example notebooks:** beyond running as a pipeline and through notebooks, anything more you want
  from the release examples? (`docs/components/run_modes.md`)
- **Model documentation (Phase 3):** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| The plan: rounds, dates and depth per component (Q218, Q223, OD-01) | December is a pre-release with two purposes: a working result to show at year end, and exit points close to final for the downstream teams (D-109) | Round 1 to 12-08, run-through and pre-release (into the internal repo, not production) by 12-18, round 2 to 02-05, release 1.0 by 02-19 as the first change request (D-115) (`worknotes/timeline_proposal.md`) | SDS + LDS, then the CDS |
| The config + audit log (OD-10, Q241) and the automation-level mapping (OD-25) | The SDS's framing: the config is set after Target Factory, every later decision is logged, config + log replay to one final modelling input | Q241 reframed: five points, the 16-entry table, replay rebuilding the state, and seven sub-questions with alternatives (where people's decisions live, what the log may change, rule entries, run identity, storage, who writes, usability) | SDS + LDS |

## Since the last sync
- **Fourth round of answers; plan adjusted** (10-22): D-111–D-123. Phase 2 registry records
  (D-111, soft); monitoring's frame built properly, its content light (D-112); scores written per
  entity × domain where possible (D-113); a newer framework version within an image's year
  (D-114, soft); the first change request is release 1.0, framework only, after the year-end
  freeze (D-115); reserved columns for later tasks (D-116); sampling kept simple (one keep
  fraction, no month stratification), with advanced sampling, low-value downsampling included,
  and recency weighting moved to Phase 3 (D-117, D-123); no
  lineage list for upstream targets (D-118); an artifact inventory at S1 (D-119); FLAML gets the
  client groups (D-120); a Phase 3 wishlist in the roadmap (D-121); decisions summarised in
  brackets inside questions (D-122). The timeline now sizes stages in days and counts the week of
  11-30 as lost. — look at: `worknotes/timeline_proposal.md`,
  `worknotes/holistic_review_questions.md`, `docs/roadmap.md` → Phase 3 wishlist
- **Third round of answers; the plan reshaped** (10-21): D-103–D-109. The framework's scores end
  at its own traceable table, the master layer; consumable tables are built outside it (D-103).
  Scores are compared across products, so calibration is a release requirement (D-104; a rank
  score later is OD-28). Reports stay self-contained, size not optimised (D-105). Phase 2 relies
  on the train/test client split, nothing more around FLAML's trial selection (D-106; whether to
  pass FLAML the client groups, as `CLAUDE.md` §4.11 asks, is Q296). Compatibility is about
  outputs (D-107; `CLAUDE.md` §2). Upstream data facts aren't ours (D-108). The plan is
  milestones with dates per stage; December is a pre-release with two purposes (D-109), and the
  timeline is reshaped into two build rounds with a run-through after each. The synthetic data is
  accepted, with three future to-dos. Q241 now shows the audit log in use. — look at:
  `worknotes/timeline_proposal.md`, `docs/decisions.md` D-103–D-109,
  `worknotes/holistic_review_questions.md` Q241
- **No pickle only at promotion** (10-21, D-110): the sandpit may save pickle; only what moves
  to production may not. The main disadvantage: the promoted model is a plain-data rebuild, so
  Evaluation must score that rebuild or its evidence doesn't carry over. Fewer families reach
  production (CatBoost only as `.cbm`; no scikit-learn forests), and MLflow's default flavors
  pickle (Q297–Q299). — look at: `worknotes/pickle_summary.md`
- **The SDS's second round of answers** (10-21): D-098–D-102: test metrics per month first and
  named denominators (D-098); reproducible runs on a trial budget with time recorded (D-099); M2
  engineering shape, including a Protocol-ready model interface and test runtimes (D-100);
  pickle only matters for saved and moved artifacts (D-101); doc upkeep (D-102). A doc-hygiene
  pass fixed the inconsistencies the review found. The questions file is round 3, open questions
  only; three proposals for both of us in section A (Q241, Q254, Q286). The retail platform's
  expected score format arrived (`inference.md` requirement 4); its fit with the framework's own
  scores table is Q291–Q295. — look at:
  `worknotes/holistic_review_questions.md`, `docs/decisions.md` D-098–D-102
- **The SDS answered the holistic review** (10-20, same day): D-082–D-097. The main ones: counts of
  positives mean events (D-082); choices among variants weigh train and test only, validation
  never chooses, `CLAUDE.md` §4.4 reworded (D-083); review-list tags and a cap of five, the LDS's
  review scope, frozen design docs (D-084); the speed claim is "a registered candidate in days to
  a few weeks" (D-085); YAML (D-086); two automation levels (D-087); identities with a worked
  example (D-088); the shared-table rule (D-089); extension code in use-case repos (D-090); M2
  defaults (D-091); the sign-off over the final list (D-092); M2 never lesser than the crunch, all
  three FLAML families (D-093); training under FLAML and the calibration chain (D-094);
  "registered" (D-095); `recipe_hash` and the refit as production retraining (D-096); the plan
  shape: release 1.0 is the definition of done, December a pre-release, regression stays (D-097).
  The questions file is now round 2: what is still open, three restated, 24 new from the review's
  pointers. — look at: `docs/decisions.md` D-082–D-097, `worknotes/holistic_review_questions.md`
- **Holistic review before planning** (10-20). Everything designed so far was reviewed against the
  goals, every component doc and the decision log, with three fresh-context audits (ML
  correctness, forward compatibility, cross-doc consistency). Verdict: proceed with changes. The
  main findings: December is ambiguous and not reachable as release 1.0; review bandwidth is the
  bottleneck; five design holes to close before M2 writes a shared row (shared-table rule,
  identities and hashes, the model bundle under FLAML, the calibration chain, the refit); three
  research questions gating the config spine; external dependencies without names or dates. Two
  claims were verified in the pinned FLAML source: it drops and recodes columns before the
  booster, and it exposes no out-of-fold predictions. 49 questions with defaults, and a timeline
  with a depth-per-component draft. — look at: `worknotes/holistic_review.md`,
  `worknotes/timeline_proposal.md`, `worknotes/holistic_review_questions.md`
- **CDS meeting outcomes** (D-073–D-079). The CDS leaves the design to us and wants the lifecycle
  to evolve as we build, not a blank-slate redesign. Settled:
  - the package ships in the base image through Nexus; the image pins the version;
  - the first release adds feature store integration (on the feature store, other sources, or
    both) and data observability integration for monitoring, both thin; no LLM until Phase 3
    (the CDS's "LLM-written documentation" means our own repo docs);
  - a person signs off every feature before a model is registered, at every automation level;
  - profiles become automation levels, from fully autonomous to fully manual (soft);
  - no pickle for models;
  - downstream operations (flags, live-model ownership, monitoring tooling) go to the platform /
    MLOps team.

  New research questions: YAML or Python configs (OD-24, since settled as YAML, D-086), a decision audit log with the config
  never changing (OD-10), automation levels (OD-25), the feature store (OD-26), retraining in
  production (OD-27). The SDS then settled the Phase 2 modelling scope: binary and regression, FLAML only, the predefined
  path + Optuna in Phase 3 (D-080); and the task order after the first release (D-081). — look at: `docs/roadmap.md` → Open
  decisions, Chief DS topics
- **Synthetic data generator done and approved by the SDS** (M1; D-064–D-071). Population,
  holdings, amounts, the feature mart, traps, oracle and CLI were built in one go (10-17). The SDS's
  review (10-19) reorganised the code into role folders, cut what did little (`truth.json`
  234 → 55 KB), added a moderate leak and a shifted column, raised exits and made the book a steady
  state. The notebook is now a visual tour, with the checks in an appendix. It shows a leakage
  screen, the gains a perfect model would reach, heavy tails, collinear clusters and the regression
  oracle's band. It is now on your review list. Still open in M1: regression's per-task spec (D-060). —
  look at: `synthetic/REVIEW.md`
- **Window ablation without a second validation month** (D-062): the window is chosen on test and
  validation equally; train only shows the overfitting gap. — look at: `docs/components/dataset.md`
- **Working rules** (D-071, D-072):
  - Claude works in parallel by default: subagents take the independent pieces, long jobs run in
    the background, and Claude integrates and verifies the results.
  - Build plans have major steps, each ending in the SDS's review, made of minor steps, each ending
    in Claude's review skills.
  - Commits happen only when the SDS asks.
  - Docs have no flowcharts, since they break on small screens.
  - Component docs read in three levels: a summary (≈ 4% of the doc), how it fits together (with
    the summary ≈ 20%), then the details. `test_harness.md` is the first one written this way.

  — look at: `CLAUDE.md` §1 workflow, `docs/components/README.md`
- **Open decisions split** into short-term (needed to finish M1 or build M2) and medium-term (M3
  on, or parked). — look at: `docs/roadmap.md` → Open decisions
- **Code rules** (D-063, D-067): every function has type hints and a docstring, checked
  automatically; functions up to ~50 lines and steps up to ~300–400 changed lines, with a review
  guide for larger agreed builds.

## Demo next
- The planning set: the reshaped plan (`worknotes/timeline_proposal.md`: verdict, dates, the plan
  table), then the audit log in practice (Q241's worked example); the CDS outcomes after that.

## Last 7 days
- 10-22 — **Fourth answers; plan adjusted**: D-111–D-123; questions round 5; Phase 3 wishlist —
  `worknotes/timeline_proposal.md`, `docs/roadmap.md`
- 10-21 — **Third answers; plan reshaped; synthetic data accepted by the LDS**: D-103–D-109;
  questions round 4; two build rounds with a run-through after each —
  `worknotes/timeline_proposal.md`
- 10-21 — **Holistic review, second answers**: D-098–D-102; questions round 3; doc-hygiene pass —
  `worknotes/holistic_review_questions.md`
- 10-20 — **Holistic review answered**: D-082–D-097; questions round 2; `CLAUDE.md` §4.4 and the
  speed claim reworded — `docs/decisions.md`, `worknotes/holistic_review_questions.md`
- 10-20 — **Holistic review and planning set**: verdict, top risks, 49 questions with defaults,
  timeline with scenario A (pre-release December, release 1.0 mid-February) — `worknotes/holistic_review.md`,
  `worknotes/timeline_proposal.md`, `worknotes/holistic_review_questions.md`
- 10-20 — **CDS meeting outcomes**: design left to us; feature store and data observability in
  the first release; feature sign-off; no pickle; binary + regression, FLAML only — D-073–D-081,
  OD-24–OD-27
- 10-19 — **Working rules and doc structure**: plans in major/minor steps, commits only on
  request, three-level docs without flowcharts, open decisions split by horizon — D-072
- 10-17–19 — **Synthetic data generator (M1)**: built, reviewed by the SDS, approved; ready for
  the LDS — `synthetic/REVIEW.md`
- 10-14 — **CDS meeting material**: three rounds with the SDS, then a review with the LDS that added
  our joint proposals (repos, release path, task scope and order); the material was removed once its outcomes were
  in the docs (10-20)
- 10-14 — **Follow-ups to the 10-13 sync**: feature decisions, lifecycle depth, regression shapes,
  targets — D-058–D-061
- 10-13–15 — **Synthetic data (M1) design**: feature-mart spec settled, local Spark harness running,
  population and holdings built — D-056, D-057, D-062–D-066, `docs/components/test_harness.md`
- 10-13 — **LDS sync**: Phase 2 scope reopened (FLAML only / binary only; settled by D-080); the registry and
  deployment need an owner (OD-23); MLflow for the registry rather than monitoring (OD-13)
- 10-12–13 — **Holistic review of the baseline**: where test or validation data could choose
  something, and shape risks — D-047–D-055
