# Sync page
_For the SDS and the LDS · last updated: 2026-10-26 (briefing for the sync) · last sync: 2026-10-26_

**In short (10-23 to 10-26):** The inconsistency sweep and the Stage 1 design questions are all
answered, and Stage 1 is being built. The biggest rule change: EDA and Feature Checks now look at
all clients, so people's feature choices have seen test labels, and the validation month is the
honest number. Stage 1's design is settled: the config's layout, a separate file for environment
facts, one saved model input that every later stage reads, what the two automation levels change,
and a size check before data leaves Spark. Its first build step, the config and the environment
adapter, is built and reviewed, the SDS's remarks are applied, and Target Factory is being built.
Your synthetic to-dos are built as ten new trap columns. The Phase 2 plan needs your review this
week, before the stakeholder buy-in.

Detail behind each item: `worknotes/log.md`. How this page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
**Decisions needed from you: the short-term open decisions** in `docs/roadmap.md` → Open decisions:
OD-01 first (the Phase 2 plan, `worknotes/timeline_proposal.md`, before this week's stakeholder
buy-in), then OD-06, OD-08, OD-11, OD-12, OD-18, OD-23. Everything below is for review and feedback.
- [ ] **Stage 1's design** — D-129–D-133 in `docs/decisions.md`, the full YAML in
      `docs/components/config.md` — feedback wanted: the config layout (D-129), the saved model
      input (D-131) and what the two automation levels change (D-132).
- [ ] **Stage 1, major step 1 as built** — `conf/base/TEMPLATE.yml`, `conf/base/cc_acquisition.yml`,
      then `worknotes/m2_1_foundation/review_guide.md` → Major step 1 (not ML-critical: sample it)
      — feedback wanted: does the template read well as a DS's first contact with the framework?
- [ ] **The decision audit log** — `docs/components/config.md` → Decision audit log — feedback
      wanted: do the closed list of operations, the settings a decision may change, the replay
      rules and the verbosity controls answer your concern about verbosity and the step from
      entries to code?
- [ ] **The twenty decisions that shape the framework** — `worknotes/decisions_LDS_review.md`, in
      reading order, with the feedback wanted per row; start with the frame (rows 1–7).
- [ ] **The SDS's answers to the inconsistency sweep** — the rows changed on 10-23 in
      `docs/decisions.md` — feedback wanted, most important first: EDA and Feature Checks on all
      clients (D-030); production retrains by default, checked against its parent (D-033, D-052);
      one sign-off gate (D-031); validation shown everywhere (D-083); sampling only when declared
      (D-117).
- [ ] **Your synthetic to-dos, built** — `docs/components/test_harness.md` → Trap summary,
      `synthetic/REVIEW.md` §1 — feedback wanted: is "univariate" right as a constant column, and
      is a kind missing? The notebook's section 6 shows them against the oracle.

## Questions for the LDS
- **Example notebooks:** beyond running as a pipeline and through notebooks, anything more you want
  from the release examples? (`docs/components/run_modes.md`)
- **Model documentation (Phase 3):** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| Is MLflow available inside the bank (OD-08)? | MLflow in Phase 2 is the goal; its shape is settled (D-111): M2.4's records map onto it, it goes in with the integrations in M4 | Ask at the platform learn session, by 11-06 | SDS + LDS, with the platform / MLOps team |

## Last 2 working days (10-23 to 10-26)
- **Stage 1 (M2.1 Foundation): designed, planned, step 1 built (10-23 → 10-26).** Stage 1
  builds the config spine, the environment adapter, Target Factory and the dataset, in three
  major steps, each ending in the SDS's review. Its design questions (10-23, round 2 on 10-25)
  are all answered: the config layout, the environment file, the model input, the level mapping
  and the collect printout. Step 1 is built: the schema and template, level defaults,
  migrations, the hashes, the decision audit log with its `decide` command, and the environment
  adapter. Three reviewers found two real traps (an `hdfs://` root reaching `pathlib`; a level
  move not moving the level defaults), both fixed. From the SDS's review: the template shows
  every default, a level move no longer overwrites a person's setting, more settings may change
  through the log, and a month is held as its last day, whichever day a source tags. The synthetic data
  gained a slim second table, so the skeleton reads two sources. Target Factory (major step 2)
  is being built. — look at: D-129–D-133, `worknotes/m2_1_foundation/plan.md`, `review_guide.md`,
  `review_answers.md`
- **Inconsistency sweep answered and closed (10-23 → 10-25).** 21 decision rows extended, and
  `CLAUDE.md`, the roadmap and the docs brought in line. The rule change: EDA and Feature Checks
  use all clients and the client split comes after them, so people's feature decisions see test
  labels; the validation month stays the honest number (D-030, `CLAUDE.md` §4.4). Also:
  production retrains the recipe by default on the same window and clients, checked against its
  parent; only the move to production must avoid pickle; all three FLAML families in M2; one
  sign-off gate after training; sampling only when the config declares it; the validation month
  moves into the config; in Phase 2 a model's plain-data copy is trusted on its family's
  verified round trip (D-051). — look at: the rows changed on 10-23 in `docs/decisions.md`
- **Your synthetic to-dos, built (10-25).** Ten trap columns, on in every preset: a random flag, a
  300-level categorical, two constants (your "univariate"), a redundant column, two low-fill
  columns, a leak through missingness, and card twins of the shifted and process-leak kinds, so
  the credit-card run-through meets every kind; `unstable` waits for M4. The trap list is the
  acceptance test for "the traps are flagged", and the framework stays blind to the names. Every
  existing column is unchanged at the same seed, and every check passes. The package goes into
  the bank as code; tests generate their data from a seed. — look at:
  `docs/components/test_harness.md` → Trap summary; D-064, D-041

## Demo next
- Stage 1's config spine: the template's reading key (`conf/base/TEMPLATE.yml:1`) and the worked
  example `conf/base/cc_acquisition.yml`; then the audit log's worked example replayed,
  `pytest tests/test_audit_log.py -q` (20 tests, under a second; `tests/test_audit_log.py:134`),
  and a decision from the command line, `python -m core_modelling decide --help`.
- The Phase 2 plan (`worknotes/timeline_proposal.md`) if not shown yet.

## Last 7 working days (10-16 to 10-22)
- 10-22 — **Decision log compacted; inconsistency sweep; LDS reading list**: 128 rows → 58 in a
  high-impact and a low-impact table, so IDs may have moved (mapping in `worknotes/log.md`) —
  `docs/decisions.md`, `worknotes/decisions_LDS_review.md`
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
