# Sync page
_For the SDS and the LDS · last updated: 2026-10-20 · last sync: 2026-10-13 (2026-10-14: CDS prep only)_

**New decisions since the last sync:** D-056–D-081 (`docs/decisions.md`)

Detail behind each item: `worknotes/log.md`. Open decisions (OD-nn): `docs/roadmap.md`. How this
page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
- [ ] **CDS meeting outcomes** — `docs/decisions.md` D-073–D-079, then `docs/roadmap.md` (open
      decisions and the new Chief DS topics) — feedback wanted: does this match your notes from
      the two sessions? Especially the feature sign-off before register (D-076), automation
      levels (D-077) and no pickle (D-078).
- [ ] **Synthetic data generator (M1)** — `synthetic/REVIEW.md`, then
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
- [ ] **Synthetic data spec** — `docs/components/test_harness.md` — feedback wanted: is the
      synthetic retail book realistic enough to develop against? Especially the mixes per
      profile and the product rates taken from public UAE figures (D-064).
- [ ] **Rule changes from the holistic review** — `CLAUDE.md` §2, §4.4, §4.7, §4.10;
      D-047–D-055 — feedback wanted: do the reworded invariants (label checks on train-split
      clients; calibration) match how you'd audit a model?
- [ ] **Roadmap** — `docs/roadmap.md` milestones and open decisions — feedback wanted: milestone
      order, and which open decisions you want to own.
- [ ] **Observation windows and splits** — `docs/components/dataset.md` — feedback wanted: the
      default sampling option (OD-17).
- [ ] **Inference output** — `docs/components/inference.md` (OD-18) — needed from you: the extra
      columns for the campaign system and the score/manifest path layout.
- [ ] **Feature ledger sketch** — `docs/components/feature_ledger.md` (OD-11) — feedback wanted:
      enough oversight of initial vs selected features?
- [ ] **Lifecycle** — `docs/components/lifecycle.md` — feedback wanted: do the straw men match how
      production changes actually run? (The design itself now goes through the CDS.)
- [ ] **Goals and scope** — `docs/context/project.md` — feedback wanted: anything missing?
- [ ] **Reading order** — `docs/README.md` — feedback wanted: the right way in for a newcomer?

## Questions for the LDS
- **Trade-off chart (OD-22):** may the overfitting chart pick a trial on the test metric, or only on
  client-grouped CV inside train? Leaning: CV only; test is reported, never chosen on.
- **Monitoring in Phase 2 (OD-01):** you suggested Phase 3; the SDS wants a stub of every major
  component in Phase 2, with health and drift monitoring deep (D-040). Agree?
- **Example notebooks:** beyond running as a pipeline and through notebooks, anything more you want
  from the release examples? (`docs/components/run_modes.md`)
- **Model documentation (Phase 3):** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| Config research before M2 (OD-24, OD-25) | YAML or Python configs; automation levels | — | SDS + LDS |
| Depth per component (OD-01) | full / deep / thin / stub | — | SDS + LDS |
| Decision audit log (OD-10) | CDS direction: the config never changes; later decisions go to a log. Fixes the flag case (a `keep` in the config changed its hash) | Append-only records per decision point; draft inventory in `config.md` | SDS |

## Since the last sync
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

  New research questions: YAML or Python configs (OD-24), a decision audit log with the config
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
- The CDS outcomes and the new research questions (`docs/roadmap.md`), then where the synthetic
  data generator stands.

## Last 7 days
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
