# Sync page
_For the SDS and the LDS · last updated: 2026-10-22 (decision log compacted) · last sync: 2026-10-22_

**New or extended decisions in the last 2 days:** D-072 (g) extended (two tables; a superseding decision replaces its row in place). The log was compacted today from 128 to 58 rows; IDs you knew may have moved (mapping in `worknotes/log.md`, entry of 2026-10-22)

Detail behind each item: `worknotes/log.md`. Open decisions (OD-nn): `docs/roadmap.md`. How this
page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
Tags per D-072 (h): **needs decision** (at most five) or **for information**.
- [ ] **The decision audit log, built into the config doc** (needs decision) —
      `docs/components/config.md` → Decision audit log — feedback wanted: do the closed list of
      operations, the maintained list of settings a decision may change, the replay rules and the
      verbosity controls answer your concern about verbosity and the step from entries to code?
- [ ] **The twenty decisions that shape the framework** (needs decision) —
      `worknotes/decisions_LDS_review.md`, in reading order, each with why it matters and what
      feedback is wanted; the rows themselves are in `docs/decisions.md` (high-impact table) —
      feedback wanted: per row, as listed there. Start with the frame (rows 1–7), then the ML rules.
- [ ] **The inconsistency questions, block A** (for information, until the SDS has answered) —
      `worknotes/inconsistency_questions.md` Q302–Q318: decisions that disagree with each other
      (retraining in Phase 2, where pickle stops, one or two sign-off gates, the model interface,
      the sampling trigger, tests before the pre-release). The SDS answers; your view on any of
      them is welcome in the sync.
- [ ] **The Phase 2 plan** (needs decision) — `worknotes/timeline_proposal.md` — the working
      assumption we build on (D-022): dates, M2's stages, depth per component. Feedback wanted:
      your review before the stakeholder buy-in next week (OD-01).

## Questions for the LDS
- **Example notebooks:** beyond running as a pipeline and through notebooks, anything more you want
  from the release examples? (`docs/components/run_modes.md`)
- **Model documentation (Phase 3):** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| Automation levels: what `autonomous` and `assisted` each decide by rule and by a person at each decision point (OD-25) | Needed in M2.1; it uses the same inventory of decision points as the audit log's list of settings a decision may change (D-125) | Written when the config spine is built, with reversible defaults | SDS + LDS |
| Whether the field is renamed from `profile` now or at M4, and where the Phase 2 sign-off gate sits (Q317, Q305 in `worknotes/inconsistency_questions.md`) | Both surfaced by the sweep as decisions disagreeing with each other | Q317: rename at M2.1, no migration; Q305: one gate after training | SDS, with the LDS's view |

## Last 2 days
- **Decision log compacted and reviewed (10-22):** 128 rows → 58, split into a high-impact table
  (42 rows, read in full) and a low-impact one (16, sample); merged rows name the IDs they absorbed;
  a superseding decision now replaces its row in place (D-072 (g)). Four reviewers then swept every
  doc for inconsistencies: 40 questions, each with a default, in `worknotes/inconsistency_questions.md`
  (block A = decisions disagreeing with each other, block B = doc vs decision design points, block
  C = docs lagging settled decisions). Your reading list: `worknotes/decisions_LDS_review.md`. — look
  at: `docs/decisions.md`, the two worknotes files
- **The planning thread is closed** (10-22). The plan is the working assumption, still under
  review: M2 in four stages (M2.1–M2.4) to 11-20, M3 to 12-08, the pre-release by 12-18, M4 to
  02-05, release 1.0 by 02-19 (D-022; stakeholder buy-in next week). The decision audit log is built into `config.md` from the accepted
  structure, including the resolved config saved as one file and a registered bundle that carries
  its run's slice of the log as one file (D-125). Phase 2 retraining keeps the clients and the
  window (D-052); the Public API is the short list (D-024); product and activity come from the use
  case's name, as in the crunch (D-128). `worknotes/holistic_review.md` is deleted; the questions
  file is closed. — look at: `worknotes/timeline_proposal.md`, `docs/components/config.md`
- **No pickle only at promotion** (10-21, D-051): the sandpit may save pickle; only what moves
  to production may not. The main disadvantage: the promoted model is a plain-data rebuild, so
  Evaluation must score that rebuild or its evidence doesn't carry over. Fewer families reach
  production (CatBoost only as `.cbm`; no scikit-learn forests), and MLflow's default flavors
  pickle (Q297–Q299). — look at: `worknotes/pickle_summary.md`

## Demo next
- The compacted decision log's two tables and the reading list (`worknotes/decisions_LDS_review.md`),
  then the Phase 2 plan (`worknotes/timeline_proposal.md`) and the decision audit log's worked
  example (`docs/components/config.md`).

## Last 7 days
- 10-22 — **Decision log compacted; inconsistency sweep; LDS reading list** — `docs/decisions.md`,
  `worknotes/inconsistency_questions.md`, `worknotes/decisions_LDS_review.md`
- 10-22 — **Planning thread closed**: plan as working assumption, audit log in `config.md`;
  D-022, D-024, D-052, D-125, D-128 — `worknotes/timeline_proposal.md`, `docs/components/config.md`
- 10-22 — **Fourth answers; plan adjusted**: registry records (D-111), monitoring frame (D-040),
  sampling kept simple (D-117), the Phase 3 wishlist — `docs/roadmap.md`
- 10-21 — **Third answers; plan reshaped; synthetic data accepted by the LDS**: the master layer
  (D-016), calibration a release requirement (D-049), outputs-only compatibility (D-007); two
  build rounds with a run-through after each — `worknotes/timeline_proposal.md`
- 10-21 — **No pickle only at promotion**: D-051 — `worknotes/pickle_summary.md`
- 10-21 — **Holistic review, second answers**: per-month evaluation (D-098), trial budgets (D-094),
  M2 engineering shape (D-100); doc-hygiene pass — `docs/decisions.md`
- 10-20 — **Holistic review answered**: positive events (D-082), choices on train and test (D-083),
  YAML and the config spine (D-043, D-088), identities, the sign-off view (D-031); `CLAUDE.md`
  §4.4 and the speed claim (D-023) reworded — `docs/decisions.md`
- 10-20 — **Holistic review and planning set**: verdict, top risks, 49 questions with defaults, a
  timeline (the review was deleted on 10-22; its outcomes are in `docs/decisions.md`)
- 10-20 — **CDS meeting outcomes**: design left to us; feature store and data observability in
  the first release; feature sign-off; no pickle; binary + regression, FLAML only — D-020, D-021,
  D-023, D-031, D-051, D-073, D-079, D-081; OD-25–OD-27
- 10-19 — **Working rules and doc structure**: plans in major/minor steps, commits only on
  request, three-level docs without flowcharts, open decisions split by horizon — D-072
- 10-17–19 — **Synthetic data generator (M1)**: built, reviewed by the SDS, approved; accepted by
  the LDS on 10-21 — `synthetic/REVIEW.md`
- 10-13–15 — **Synthetic data (M1) design**: feature-mart spec settled, local Spark harness running,
  population and holdings built — D-011, D-029, D-041, D-064, D-083, `docs/components/test_harness.md`
