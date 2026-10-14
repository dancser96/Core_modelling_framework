# Sync page
_For the SDS and the LDS · last updated: 2026-10-14 · last sync: 2026-10-13_

**New decisions since the last sync:** D-056–D-061 (`docs/decisions.md`)

Detail behind each item: `worknotes/log.md`. Open decisions (OD-nn): `docs/roadmap.md`. How this
page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
- [ ] **CDS meeting material** — `worknotes/chief_ds_meeting/overview.md` and `questions.md` —
      feedback wanted before tomorrow: anything to cut, add or reframe?
- [ ] **Synthetic data spec** — `docs/components/test_harness.md` — feedback wanted: is the
      synthetic retail book (segment mix, products, eligibility thresholds) realistic enough to
      develop against?
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
- **Model documentation:** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| CDS meeting, 2026-10-15 (2 × 30 min) | Covers OD-06–OD-09, OD-13, OD-15, OD-23 and D-055 | Drafts ready; modelling half as our proposal, downstream designed with the CDS | SDS + LDS, then the CDS |
| Depth per component (OD-01) | full / deep / thin / stub | — | SDS + LDS |
| Human feature decisions (OD-10) | Resolving a flag after training would force an identical retrain | Grouped lists, one note per group; only a `keep` that resolves a flag needs one | SDS |

## Since the last sync
- **CDS meeting material is ready for our discussion.** The overview is a ~15-minute design update;
  the questions are 23 over topics a–f, 8 starred. On your OD-15 position: FLAML can be limited to
  one model family, so "FLAML only" can still offer a predefined family. — look at:
  `worknotes/chief_ds_meeting/`
- **Synthetic data: spec settled, first code running.** The synthetic retail book is specified, and
  a local Spark harness (the first framework code) passes its tests; the generator is next, built
  in reviewed steps. — look at: `docs/components/test_harness.md`

## Demo next
- Walk through the CDS meeting drafts: `worknotes/chief_ds_meeting/overview.md`, then
  `questions.md`.

## Last 7 days
- 10-14 — **CDS meeting drafts**, three rounds with the SDS — `worknotes/chief_ds_meeting/`
- 10-14 — **Follow-ups to the 10-13 sync**: feature decisions, lifecycle depth, regression shapes,
  targets — D-058–D-061
- 10-13–14 — **Synthetic data (M1)**: feature-mart spec settled, local Spark harness running —
  D-056, D-057, `docs/components/test_harness.md`
- 10-13 — **LDS sync**: Phase 2 scope reopened (FLAML only / binary only, OD-15); the registry and
  deployment need an owner (OD-23); MLflow for the registry rather than monitoring (OD-13)
- 10-12–13 — **Holistic review of the baseline**: where test or validation data could choose
  something, and shape risks — D-047–D-055
- 10-12 — **Design baseline (M0)**: docs rebuilt from three review rounds and the LDS notes;
  roadmap with milestones and open decisions; worknotes shared — D-020–D-046
