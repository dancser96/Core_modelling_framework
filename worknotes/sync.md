# Sync page
_For the SDS and the LDS · last updated: 2026-10-21 (planning set, round 3) · last sync: 2026-10-13 (2026-10-14: CDS prep only)_

**New decisions since the last sync:** D-056–D-102 (`docs/decisions.md`); D-082–D-102 are the SDS's answers to the holistic review (2026-10-20 and 10-21)

Detail behind each item: `worknotes/log.md`. Open decisions (OD-nn): `docs/roadmap.md`. How this
page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
Tags per D-084: **needs decision** (at most five) or **for information**. The list was drained on
10-20 at the SDS's request: everything except the synthetic data and the current planning is
covered by the planning set below or by D-073–D-102.
- [ ] **Planning-session set, round 3** (needs decision) — `worknotes/holistic_review.md` (§1
      verdict and §3 top risks first), `worknotes/timeline_proposal.md` (scenario A vs B, the
      dates, the OD-01 depth table), then `worknotes/holistic_review_questions.md` section A (for
      both of us) and B (facts) — feedback wanted: what December means (Q217), the depth table
      (Q218), the M3 priorities (Q223); three proposals that shape M2: the config + audit log as
      the SDS frames it (Q241), client-grouped validation inside training (Q254), how long old
      versions must keep working (Q286); and the facts only you have (Q232, Q235, Q237, Q238).
- [ ] **The SDS's answers as decisions** (needs decision) — `docs/decisions.md` D-082–D-102 —
      feedback wanted: D-082 (positive events), D-083 (train and test choose, never validation;
      `CLAUDE.md` §4.4 reworded), D-093 (M2 never lesser than the crunch), D-094 (training under
      FLAML, the calibration chain), D-098 (per-month test metrics; denominators), D-101 (pickle
      only matters for saved and moved artifacts).
- [ ] **Synthetic data generator (M1)** (for information) — `synthetic/REVIEW.md`, then
      `notebooks/00_synthetic_data.ipynb` and `docs/components/test_harness.md` (Levels 1
      and 2) — feedback wanted: is the book realistic enough to develop against, and are the
      traps the ones the framework must catch? The SDS approved it on 10-19. In short:
      - 100k clients × 24 months, written as a 147-column feature mart that Spark reads like the
        real one;
      - a steady-state book: 8–12% of clients leave a year and as many join, while shares, ages
        and tenure stay flat;
      - 12 standard targets, each with a known ceiling (the oracle: AUC 0.70–0.95);
      - traps the framework must catch: two leaks, an upstream target, a process leak, a column
        shifted a month ahead, a Simpson effect, drift and a rare level;
      - 1,263 independent check rows, all passing; the code is in role folders (rules, functions,
        truth, checks).
- [ ] **Synthetic data spec** (for information) — `docs/components/test_harness.md` — feedback
      wanted: is the synthetic retail book realistic enough to develop against? Especially the
      mixes per profile and the product rates taken from public UAE figures (D-064).

## Questions for the LDS
- **The planning set** (above): section A of `worknotes/holistic_review_questions.md` (Q217,
  Q218, Q223, Q241, Q254, Q260, Q262, Q263, Q286) and the facts in section B.
- **Monitoring in Phase 2 (OD-01):** you suggested Phase 3; the SDS wants every major component at
  least thin by December, with health and drift monitoring deep by release 1.0 (D-040, D-097).
  Agree?
- **Example notebooks:** beyond running as a pipeline and through notebooks, anything more you want
  from the release examples? (`docs/components/run_modes.md`)
- **Model documentation (Phase 3):** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| What December means, and the dates to M2–M5 (Q217, Q218, Q223) | D-097 puts the definition of done at release 1.0 and makes December a pre-release; content and dates still to agree | Scenario A: pre-release in December, release 1.0 mid-February 2027 (`worknotes/timeline_proposal.md`) | SDS + LDS, then the CDS |
| The config + audit log (OD-10, Q241) and the automation-level mapping (OD-25) | The SDS's framing: the config is set after Target Factory, every later decision is logged, config + log replay to one final modelling input | Proposal in Q241: append-only log per instance, replay to the frozen config, data definition locked, `run_id` on the replayed input | SDS + LDS |
| Depth per component (OD-01) | full / deep / thin / stub, in three columns | Draft in `worknotes/timeline_proposal.md` | SDS + LDS |

## Since the last sync
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
- The planning set: the verdict and top risks (`worknotes/holistic_review.md` §1, §3), then the
  two December scenarios and the depth table (`worknotes/timeline_proposal.md`); the CDS outcomes
  and the synthetic data generator after that.

## Last 7 days
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
