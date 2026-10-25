# Sync page
_For the SDS and the LDS · last updated: 2026-10-25 (the synthetic to-dos answered, Q379–Q386; Stage 1 round 2) · last sync: 2026-10-22_

**New or extended decisions in the last 2 days:** 10-25, extended: D-051 (Phase 2 relies on the per-family check of the plain-data model). 10-23, changed: D-030 (EDA and Feature Checks use all clients; `CLAUDE.md` §4.4 reworded). 10-23, extended by the SDS's answers: D-006, D-014, D-021, D-023, D-024, D-031, D-033, D-036, D-037, D-040, D-043, D-049, D-051, D-052, D-072, D-083, D-088, D-091, D-106, D-111, D-117, D-125 (each status names what changed). 10-22: D-072 (g) (two tables; a superseding decision replaces its row in place); the log was compacted from 128 to 58 rows, so IDs you knew may have moved (mapping in `worknotes/log.md`, entry of 2026-10-22)

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
- [ ] **The SDS's answers to the inconsistency sweep** (needs decision) — `docs/decisions.md`, the
      rows changed or extended on 10-23 — feedback wanted, most important first: EDA and Feature
      Checks on all clients, so people's feature decisions see test labels (D-030, `CLAUDE.md`
      §4.4); production retraining on the same window and clients as the default deploy path, with
      a check against the parent (D-033, D-052); one sign-off gate after training (D-031);
      validation shown everywhere in Phase 2, people trusted (D-083); sampling only when the config
      declares it (D-117); MLflow's shape (D-111, OD-08).
- [ ] **Your synthetic to-dos, as planned** (for information) — `worknotes/synthetic_questions.md`
      → The catalogue — ten trap columns, built in Stage 1 — feedback wanted: "univariate" is read
      as a column with a single value (a constant); is that right, and is a kind missing?
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
| Is MLflow available inside the bank (OD-08)? | MLflow in Phase 2 is the goal; its shape is settled (D-111): M2.4's records map onto it, it goes in with the integrations in M4 | Ask at the platform learn session, by 11-06 | SDS + LDS, with the platform / MLOps team |

## Last 2 days
- **Inconsistency questions closed (10-25):** the last one, Q374, is answered: in Phase 2 a
  model's plain-data copy is trusted on its family's verified round trip, and whether `register`
  should re-score each model's copy on the stored test split is a Phase 3 wishlist question
  (D-051). The questions file is deleted; every outcome is in `docs/decisions.md`, the roadmap
  and the docs. — look at: D-051 in `docs/decisions.md`
- **Your synthetic to-dos, planned and answered (10-25):** noise columns of several kinds, very
  low fill rates, named like the traps. Built now, in Stage 1's synthetic step rather than M4, as
  ten trap columns on in every preset: a random flag, a 300-level categorical, two constant
  columns (your "univariate", read as one value), a redundant column (informative alone, nothing
  given its source), two low-fill columns, a leak through missingness, and card twins of the
  loan-only shifted and process-leak kinds, so the credit-card run-through meets every
  trap-column kind; the `unstable` kind waits for M4. The trap list also becomes the acceptance
  test for "the traps are flagged": a test over synthetic data, the framework stays name-blind
  (Q386). Open: which chat builds it (Q387). — look at: `worknotes/synthetic_questions.md`
- **Stage 1 questions, round 2 (10-25):** round 1 is answered (defaults, a slim synthetic
  holdings table, left joins from a governing spine); six questions stay open, rewritten with
  context: the full config layout (Q354), the environment file (Q358), where `w` lives (Q364),
  the crunch's saved model input in this design (Q365), degenerate targets (Q367) and the
  collect budget (Q371). The plan follows the answers. — look at:
  `worknotes/m2_1_foundation/questions.md`
- **Stage 1 (M2.1 Foundation) kicked off (10-23):** the design questions for the config spine,
  environment adapter, Target Factory and dataset are in `worknotes/m2_1_foundation/questions.md`
  (Q349–Q373, each with a default, plus the assumptions the build rests on); the build plan in
  major and minor steps follows the SDS's answers. Already applied: `target_factory.md` is designed
  together with the dataset, shows several sources (targets from one, features from others, joined
  on unit and month), says Phase 2 only reads from the feature store, and has no Phase 3
  references. The stage folder rule: one `worknotes/<stage>/` at a time, deleted when the stage is
  done. — look at: `worknotes/m2_1_foundation/questions.md`, `docs/components/target_factory.md`
- **Inconsistency answers applied (10-23):** the SDS answered the sweep and the rest took their
  defaults; 21 decision rows extended, and `CLAUDE.md`, the roadmap and the docs brought in line.
  What changes for you: production retrains the recipe by default (deploying the fitted model stays
  possible); the sandpit may hold any format, only the move to production must avoid pickle; all
  three FLAML families in M2; one sign-off gate after training; sampling only when the config
  declares it; MLflow in Phase 2 is the goal; the validation month moves into the config;
  `automation_level` from M2.1; "resolved config" replaces "frozen config"; docs stay live. An
  ML-correctness and a compatibility review of the answers found gaps, which a second round of
  answers closed the same day. The rule change: EDA and Feature Checks use all clients, and the
  client split comes after them, so people's feature decisions see test labels; the validation
  month stays the honest number (D-030, `CLAUDE.md` §4.4). Also: a Phase 2 production retrain keeps
  the window and clients and passes a check against its parent; no sign-off log in Phase 2;
  validation shown everywhere, people trusted; register always writes the plain-data model. A
  review of round 2 fixed wording (automated selection and the prior shift read train-split
  numbers only) and left one question (Q374, answered 10-25). — look at: `docs/decisions.md`
- **Decision log compacted and reviewed (10-22):** 128 rows → 58, split into a high-impact table
  (42 rows, read in full) and a low-impact one (16, sample); merged rows name the IDs they absorbed;
  a superseding decision now replaces its row in place (D-072 (g)). Four reviewers then swept every
  doc for inconsistencies: 40 questions, each with a default, now all answered
  (block A = decisions disagreeing with each other, block B = doc vs decision design points, block
  C = docs lagging settled decisions). Your reading list: `worknotes/decisions_LDS_review.md`. — look
  at: `docs/decisions.md`, `worknotes/decisions_LDS_review.md`
- **The planning thread is closed** (10-22). The plan is the working assumption, still under
  review: M2 in four stages (M2.1–M2.4) to 11-20, M3 to 12-08, the pre-release by 12-18, M4 to
  02-05, release 1.0 by 02-19 (D-022; stakeholder buy-in next week). The decision audit log is built into `config.md` from the accepted
  structure, including the resolved config saved as one file and a registered bundle that carries
  its run's slice of the log as one file (D-125). Phase 2 retraining keeps the clients and the
  window (D-052); the Public API is the short list (D-024); product and activity come from the use
  case's name, as in the crunch (D-128). `worknotes/holistic_review.md` is deleted; the questions
  file is closed. — look at: `worknotes/timeline_proposal.md`, `docs/components/config.md`

## Demo next
- The compacted decision log's two tables and the reading list (`worknotes/decisions_LDS_review.md`),
  then the Phase 2 plan (`worknotes/timeline_proposal.md`) and the decision audit log's worked
  example (`docs/components/config.md`).

## Last 7 days
- 10-22 — **Decision log compacted; inconsistency sweep; LDS reading list** — `docs/decisions.md`,
  `worknotes/decisions_LDS_review.md`
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
