# Sync page
_For the SDS and the LDS · last updated: 2026-10-27 (Stage 1 built end to end; steps 2 and 3 with the SDS for review) · last sync: 2026-10-26_

**In short (10-26 to 10-27):** Stage 1 is built end to end, two days ahead of its plan. The
config spine was reviewed by the SDS and its remarks applied. Target Factory was reviewed too and
reworked: the rule now catches any rise of the holding flag after the observation month, nulls in
the data are handled leniently and shown, and whether a client already holds the product is an
eligibility matter, split into filters applied before the analysis (rows dropped) and before
modelling (rows kept and tagged, so holders and non-holders can be compared). The dataset is
built on top: the sources joined, eligibility, the client split, the contract checks, a saved
model input every later stage reads, and the first guided notebook. The SDS reviews Target
Factory and the dataset together now; then they are yours to read in full.

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
- [ ] **Stage 1, major steps 2 and 3 as built: Target Factory and the dataset** (after the SDS's
      review) — `worknotes/m2_1_foundation/review_guide.md` → Major steps 2 and 3, read in full
      (they build every model's label and frames) — feedback wanted: do the rule, the two kinds
      of eligibility and the frames match how you'd define and model card acquisition?
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

## Last 2 working days (10-26 to 10-27)
- **Stage 1 (M2.1 Foundation) built end to end, version 0.2.0 (10-26 → 10-27).** Three major
  steps, each reviewed by four fresh-context reviewers before the SDS. **Step 1** (the config
  schema and template, level defaults, the hashes, the decision audit log, the environment
  adapter) was reviewed by the SDS on 10-26: the template now shows every default, more settings
  may change through the log, and a month is held as its last day whichever day a source tags.
  **Step 2** (Target Factory) was reviewed on 10-27 and reworked on three points: the rule
  compares the observation month with any later month of the window (`flag_goes_up`); nulls
  follow SQL semantics and their share is shown, with an optional value a null stands for; and
  a client already holding the product is an eligibility matter, not the rule's, so eligibility
  filters now come in two kinds: before EDA (rows dropped) and before modelling (rows kept,
  tagged, usable as strata). **Step 3** (the dataset, 10-27): every source read the same way and
  joined to the governing spine, eligibility of both kinds applied to every month alike, the
  client split and the two declared sampling options, contract checks on the eligible window
  before any sampling (with a callout when nulls may hide negatives), the frames collected with a
  size printout against a budget, and the model input saved with its hashes and read back by
  every later stage, refused when stale. Also `run` with its CLI and the first guided notebook.
  Two traps found on the way and ruled: a sampling hash must not share the split's input, and a
  sidecar file in a parquet folder must not be named `_metadata…`. The full suite passes (203
  tests, 4 minutes). The SDS reviews steps 2 and 3 together next. — look at: D-129–D-133,
  `worknotes/m2_1_foundation/review_guide.md` → Major steps 2 and 3; `docs/components/dataset.md`

## Demo next
- Stage 1 end to end on the synthetic dev data: `notebooks/01_target_factory.ipynb` (the target
  summary, the join and eligibility lines, the model input saved, the window frame), or from the
  command line `python -m core_modelling run conf/base/cc_acquisition.yml --env conf/local/environment.yml`.
- The config spine: the template's reading key (`conf/base/TEMPLATE.yml:1`) and the audit log's
  worked example replayed, `pytest tests/test_audit_log.py -q`.
- The Phase 2 plan (`worknotes/timeline_proposal.md`) if not shown yet.

## Last 7 working days (10-19 to 10-23)
- 10-23 → 10-25 — **Inconsistency sweep answered and closed**: 21 decision rows extended; EDA and
  Feature Checks use all clients and the client split comes after them (D-030, `CLAUDE.md` §4.4);
  production retrains the recipe by default, checked against its parent (D-033, D-052); one
  sign-off gate (D-031); sampling only when declared (D-117); the validation month in the config
  (D-088) — the rows changed on 10-23 in `docs/decisions.md`
- 10-25 — **Your synthetic to-dos built as ten trap columns** (0.5.0), on in every preset; the
  package goes into the bank as code, tests generate their data from a seed (D-041, D-064) —
  `docs/components/test_harness.md` → Trap summary
- 10-23 → 10-26 — **Stage 1 designed and planned**: the config layout, the environment file, the
  model input, the automation-level mapping, the collect printout (D-129–D-133; OD-25 closed) —
  `worknotes/m2_1_foundation/plan.md`
- 10-22 — **Decision log compacted; inconsistency sweep; LDS reading list**: 128 rows → 58 in a
  high-impact and a low-impact table, so IDs may have moved (mapping in `worknotes/log.md`) —
  `docs/decisions.md`, `worknotes/decisions_LDS_review.md`
- 10-22 — **Planning thread closed**: plan as working assumption, audit log in `config.md`;
  D-022, D-024, D-052, D-125, D-128 — `worknotes/timeline_proposal.md`, `docs/components/config.md`
- 10-22 — **Fourth answers; plan adjusted**: registry records (D-111), monitoring frame (D-040),
  sampling kept simple (D-117), the Phase 3 wishlist — `docs/roadmap.md`
- 10-21 — **Third answers; plan reshaped; synthetic data accepted by the LDS**: the master layer
  (D-016), calibration a release requirement (D-049), outputs-only compatibility (D-007) —
  `worknotes/timeline_proposal.md`
- 10-21 — **No pickle only at promotion**: D-051 — `worknotes/pickle_summary.md`
- 10-21 — **Holistic review, second answers**: per-month evaluation (D-098), trial budgets (D-094),
  M2 engineering shape (D-100); doc-hygiene pass — `docs/decisions.md`
- 10-20 — **Holistic review answered**: positive events (D-082), choices on train and test (D-083),
  YAML and the config spine (D-043, D-088), identities, the sign-off view (D-031) —
  `docs/decisions.md`
- 10-20 — **CDS meeting outcomes**: design left to us; feature store and data observability in
  the first release; feature sign-off; no pickle; binary + regression, FLAML only — D-020, D-021,
  D-023, D-031, D-051, D-073, D-079, D-081; OD-25–OD-27
- 10-19 — **Working rules and doc structure**: plans in major/minor steps, commits only on
  request, three-level docs without flowcharts, open decisions split by horizon — D-072
