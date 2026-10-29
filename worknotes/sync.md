# Sync page
_For the SDS and the LDS · last updated: 2026-10-28 (the Stage 1 addendum built and reviewed; one continuous review guide) · last sync: 2026-10-26_

**In short (10-27 to 10-28):** Stage 1 is built end to end and the SDS has reviewed all of it;
the remarks are applied, so Target Factory and the dataset are now yours to read in full. The
review settled three things worth knowing: the framework keeps every label it can build and does
not police a data scientist (leakage protection is the screens, not hidden data); data quality
is fixed upstream, not by config knobs (two such knobs were removed); and eligibility is two
lists, who the analysis sees and who the model sees, the second applied before Feature Checks.
The SDS's second and third rounds then settled and approved the addendum, built the same day
by five agents from one spec and reviewed by four more: the unit of analysis (month, week or
day) is a parameter; the saved model input is the sources joined plus one target column per
use case, so one table serves several use cases and everything from eligibility on is derived
at read time from each use case's own config, which means a changed eligibility no longer
forces a rebuild; and the audit log can revert to an earlier state. A follow-up on the client
split was checked with numbers: hashing structured client ids gives a split as random as a
random number would. The reviews found no invariant broken and tightened a handful of
refusals. The review guide is now one continuous document for Stage 1 as it stands.

Detail behind each item: `worknotes/log.md`. How this page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
**Decisions needed from you: the short-term open decisions** in `docs/roadmap.md` → Open decisions:
OD-01 first (the Phase 2 plan, `worknotes/timeline_proposal.md`, before this week's stakeholder
buy-in), then OD-06, OD-08, OD-11, OD-12, OD-18, OD-23. Everything below is for review and feedback.
- [ ] **Stage 1's design** — D-129–D-133 in `docs/decisions.md`, the full YAML in
      `docs/components/config.md` — feedback wanted: the config layout (D-129), the saved model
      input (D-131) and what the two automation levels change (D-132).
- [ ] **Stage 1 as built, after the addendum** — `worknotes/m2_1_foundation/review_guide.md`
      (one continuous guide: read in order; the data code in full, it builds every model's
      label and frames) — feedback wanted: do the rule, the two eligibility lists (analysis /
      modelling, the second applied before Feature Checks), the frames and the one model input
      for several use cases match how you'd define and model card acquisition; does
      `conf/base/TEMPLATE.yml` read well as a DS's first contact with the framework?
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

## Last 2 working days (10-27 to 10-28)
- **The Stage 1 addendum, built and reviewed (10-28).** From the SDS's second and third
  rounds: the unit of analysis is `time.period` (month, week or day; the key column `period`,
  the `time` fields `observation_window`, `target_window`, `validation_period`; one dict of
  period arithmetic in `periods.py`, never a bare `add_months`); the model input is the sources
  joined plus one target column per use case (`target_<use_case>`), saved for one config or a
  list, with eligibility, candidates, contract and split derived on read from the reader's
  config (a changed eligibility no longer forces a rebuild; sidecar schema 3; the freeze point
  narrows to the data part); `revert` in the audit log; the id cast to string at load so the
  split's draw survives an upstream type change (T22). Built by five agents on disjoint files
  from one spec; four reviews (code, silent failures, compatibility, ML audit) found no
  invariant broken and tightened refusals: `task` in the hashes, a feature source matching
  nothing, a reserved column name, a validation period outrunning the saved target source, a
  `revert` laundering a rule's exclude. Full suite 252 passed, 9 deselected, 4 min 56 s; the notebook runs on the dev
  data in 30 s; two configs save one table with two target columns. — look at:
  `worknotes/m2_1_foundation/review_guide.md` (continuous), `addendum_spec.md`,
  `review_answers.md`; D-088, D-125, D-129, D-131
- **The SDS's review of steps 2 and 3, applied (10-28).** Labels kept in every period Target
  Factory can build (an upstream target would look the same; the framework does not police a
  DS); the two config knobs for source data quality went (`null_as`, `leavers`): a null never
  counts as an event and the contract's callout points upstream; eligibility is two ordered
  lists, `analysis` filters dropping rows before EDA and `modelling` filters tagging them until
  Feature Checks, which runs on the eligible rows; the split and the sampling as one salted hash
  draw in [0, 1); one coverage check for the spine and the target source; the template's comment
  rule. — look at: `review_answers.md`; D-029, D-030, D-129, D-131
- **Stage 1 (M2.1 Foundation) built end to end, version 0.2.0 (10-26 → 10-27).** The config
  schema and template with the level defaults, the hashes, the decision audit log and the
  environment adapter; Target Factory (`flag_goes_up`, nulls under SQL semantics with their
  share shown); the dataset (every source read the same way and joined to the governing spine,
  eligibility applied to every period alike, the client split and the two declared sampling
  options, contract checks on the eligible window before any sampling, the frames collected with
  a size printout against a budget, the model input saved with its hashes and refused when
  stale); `run` with its CLI and the first guided notebook; two traps ruled (T20, T21). — look
  at: D-129–D-133, `docs/components/dataset.md`

## Demo next
- Stage 1 end to end on the synthetic dev data: `notebooks/01_target_factory.ipynb` (the target
  summary, the join and the two eligibility lines, the model input saved, the window frame), or
  from the command line `python -m core_modelling run conf/base/cc_acquisition.yml --env conf/local/environment.yml`.
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
