# Sync page
_For the SDS and the LDS · last updated: 2026-10-15 · last sync: 2026-10-13 (2026-10-14: CDS prep only)_

**New decisions since the last sync:** D-056–D-066 (`docs/decisions.md`)

Detail behind each item: `worknotes/log.md`. Open decisions (OD-nn): `docs/roadmap.md`. How this
page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
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
- **Model documentation:** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| CDS meeting, 2026-10-15 (2 × 30 min) | Covers OD-06–OD-09, OD-13, OD-15, OD-23 and D-055 | Material reviewed together on 10-14; questions carry our joint proposals; the lifecycle design gets a separate blank-slate session | SDS + LDS, then the CDS |
| Depth per component (OD-01) | full / deep / thin / stub | — | SDS + LDS |
| Human feature decisions (OD-10) | Resolving a flag after training would force an identical retrain | Grouped lists, one note per group; only a `keep` that resolves a flag needs one | SDS |

## Since the last sync
- **Synthetic data: population and holdings exist.** Steps 0–2 built: Spark harness, the client
  population (24 months, 100k clients) and their products: credit card, term deposit, digital and
  traditional wealth, three loan types, e-banking, FX and digital activity. Each product is set by
  its share per profile and one rate; the chance behind every event is recorded as hidden truth.
  An audit fixed how the "true probability" of a target must be computed (D-066). Step 2 is
  closed; the rest (amounts, the mart's columns, traps, oracle, the written dataset) is built in
  one go after one question round, with one review at the end. — look at:
  `docs/components/test_harness.md` (product rates, maths §3), `notebooks/00_synthetic_data.ipynb`
- **Window ablation without a second validation month** (D-062): the window is chosen on test and
  validation equally; train only shows the overfitting gap. — look at: `docs/components/dataset.md`
- **New code rule** (D-063): every function has type hints and a docstring, checked automatically.

## Demo next
- The CDS meeting outcomes (2026-10-15), then where the synthetic data generator stands.

## Last 7 days
- 10-14 — **CDS meeting material**: three rounds with the SDS, then a review with the LDS that added
  our joint proposals (OD-02, OD-04, OD-15, OD-21) and split off a blank-slate lifecycle session —
  `worknotes/chief_ds_meeting/`
- 10-14 — **Follow-ups to the 10-13 sync**: feature decisions, lifecycle depth, regression shapes,
  targets — D-058–D-061
- 10-13–15 — **Synthetic data (M1)**: feature-mart spec settled, local Spark harness running,
  population and holdings built — D-056, D-057, D-062–D-066, `docs/components/test_harness.md`
- 10-13 — **LDS sync**: Phase 2 scope reopened (FLAML only / binary only, OD-15); the registry and
  deployment need an owner (OD-23); MLflow for the registry rather than monitoring (OD-13)
- 10-12–13 — **Holistic review of the baseline**: where test or validation data could choose
  something, and shape risks — D-047–D-055
- 10-12 — **Design baseline (M0)**: docs rebuilt from three review rounds and the LDS notes;
  roadmap with milestones and open decisions; worknotes shared — D-020–D-046
