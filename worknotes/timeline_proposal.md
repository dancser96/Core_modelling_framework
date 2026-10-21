# Timeline proposal (initial)
_Written 2026-10-20 for the planning session with the LDS. A proposal to argue with, not a
commitment. Companion files: `holistic_review.md` (findings) and `holistic_review_questions.md`
(round 3). Milestones and depth levels: `docs/roadmap.md`; the dates below go there once agreed.
Status: the SDS's answers of 2026-10-20 settled the plan shape (D-097: release 1.0 is the
definition of done, December a pre-release, regression stays) and M2's floor (D-093: never lesser
than the crunch). Scenario A vs B (Q217) and the depth table (Q218) await the LDS._

## Verdict
- **Recommended (scenario A):** December = the walking skeleton plus one deepening round, moved
  into the bank as an internal **pre-release** (0.x). The two integrations, the second deepening
  round and full test coverage follow as **release 1.0 around mid-February 2027**.
- **Why:** 43 working days remain to 2026-12-18, minus leave and public holidays. The crunch took
  2–3 weeks for one stage of this scope (single-month FLAML in notebooks). Phase 2 has ten stages,
  a config spine, a ledger, reporting, a CLI, eight guided notebooks, two integrations with
  systems nobody on the team has used yet, and a "every line is read by a human" rule that caps
  throughput at reading speed, not at Claude's writing speed.
- **Scenario B** (December = release 1.0 with both integrations) needs the feature store and data
  observability teams available in November and leaves EDA, evaluation and monitoring thin at
  release. Not recommended; kept here so the choice is explicit (Q217).

## Assumptions
- The SDS works on the framework about 6 hours a day with Claude; the LDS reads 30–60 minutes a
  day and reviews, never runs. Build pace reference: M1's generator (32 modules, 1,263 checks)
  took about five working days including the SDS's review, after a week of design.
- Review time is about 40% of build time and is budgeted below, not hidden.
- External teams are unavailable until a session is booked (Q232). Nothing on the critical path
  depends on them before January.
- One memory-heavy job at a time on the 8 GB Mac; the heavy M3 comparisons may need the WSL2 PC
  (agreed 2026-10-20: prepare it in a background slot).

## Milestones with dates (scenario A)

| Milestone | Dates | Content | Exit criterion |
|---|---|---|---|
| Planning + M1 close | Wed 10-21 – Fri 10-23 | Planning session(s) with the LDS; regression per-task spec shapes (D-060); the spikes started (the SDS); the review list drained to the planning set and the synthetic data | Dates and OD-01 agreed; the LDS has the synthetic data "accepted" or "accepted on trust" |
| M2.1 Spine | Mon 10-26 – Fri 10-30 | Config spine (YAML, Pydantic, profiles, frozen config, hashes, migrations); environment adapter (session arguments, transport, paths, sources); dataset (window, client split, sampling option 1, row budget, contract checks); Target Factory thin (one binary rule, lineage, panel edge) | Train / test / validation frames from the synthetic mart through one config, with the eligibility and split logs |
| M2.2 Understanding | Mon 11-02 – Fri 11-06 | EDA thin; Feature Checks thin (quality, leakage, lineage, eligibility-constant); ledger in two parts; reporting writer thin (HTML, embedded plotly, styled tables); the sign-off entry point | The trap columns are flagged; two reports open offline; the ledger shows the trail |
| M2.3 Modelling | Mon 11-09 – Fri 11-13 | Training (FLAML with `lgbm`, `xgboost` and `catboost`, D-093; own encoding before FLAML and booster-direct inference, D-094; grouped CV; the calibration chain with Platt; bundle without pickle; drift reference); Evaluation thin (test vs validation, stratified table, gains, reliability); model card | A model beats the simple baselines and never beats the oracle; all three families round-trip with identical predictions |
| M2.4 Lifecycle and operations | Mon 11-16 – Fri 11-20 | register / promote / deploy thin (append-only records); Inference (Spark scoring, batch output, manifest, reinference); Monitoring stub (health and PSI tables, flags); CLI and Python API; eight guided notebooks thin; the e2e test on the `unit` preset | `run` end to end on synthetic data; `deploy` to a production-tier path; inference from it; a monitoring table; `pytest` green; **nothing the crunch did is missing** (D-093) |
| Buffer | Mon 11-23 – Tue 11-24 | Slippage from M2; the M3 priorities agreed with the LDS | — |
| M3 Deepening round 1 | Wed 11-25 – Fri 12-11 | Priorities to agree (Q223). Candidates in order: sampling comparison against the oracle (settles OD-17); EDA key-feature deep dives and low-prevalence charts; Feature Checks stability; Training calibration step, categorical handling, refit; Evaluation core views and comparison; Monitoring drift deep; regression thin if its spec proves cheap | Each item has a review guide and the LDS's review |
| M5-lite Pre-release into the bank | Mon 12-14 – Fri 12-18 | Bank-parity check; release checklist; the zip; first move into the internal repo; a smoke run on a real mart with findings reported back in words | The skeleton runs inside the bank on one real use case to a local model. `deploy` inside the bank waits for the change-request calendar (D-055), a January item |
| Holiday slowdown | 12-21 – 01-03 | Fixes from the smoke run; nothing new | — |
| M4 Deepening round 2 + integrations | Mon 01-04 – Fri 02-12 | Feature store integration (after the learn session); data observability integration; registry tables and inventory; monitoring deep; regression end to end; tests to "every function"; CI / Sonar readiness | Release 1.0: the Phase 2 definition of done (D-021, D-075) |

## Work streams beside the critical path
- **Spikes (the SDS runs them, Claude reminds at session start; due before M2.3, 11-09):** each a
  throwaway script of an hour or two, only the answer kept in `docs/context/environment.md`.
  (1) FLAML 2.7 grouped CV with sample weights, and whether `sample=True` subsamples rows or
  clients; (2) non-pickle round trips for `lgbm`, `xgboost`, `catboost`; (3) Arrow `toPandas`
  with date columns; (4) report size with embedded plotly.js; (5) plotly in the bank's JupyterLab,
  which the SDS tests inside later.
- **Learn sessions to book by 11-06 (Q232):** platform / MLOps (change-request steps, registry
  owner OD-23, permissions OD-06, Sonar quality gate, scheduling); feature store team (OD-26);
  data observability team (OD-13). The two integration designs are written after those sessions,
  in M3's weeks, and built in M4.
- **Facts by 10-30:** the retail platform team's output format arrived on 10-21; its column
  meanings (Q294) and the two-layer design (Q291–Q295) settle the scores schema for M2.4;
  real-data facts (Q237, from the LDS).

## OD-01 draft: depth per component
Depth levels as in `docs/roadmap.md` (full · deep · thin · stub). "Shapes" = the config section,
artifact schema and per-task spec entry exist without a working body.

| Component | M2 (11-20) | December pre-release | Release 1.0 (mid-Feb) |
|---|---|---|---|
| Config spine | thin | deep | deep |
| Environment adapter | thin | deep (bank-verified) | deep |
| Dataset (window, split, sampling) | thin | deep (sampling default settled) | deep |
| Target Factory | thin | thin + labels for scored months | deep (incremental builds) |
| EDA | thin | deep | deep |
| Feature Checks | thin | deep | deep |
| Feature ledger | thin | thin | deep (with the decision log) |
| Training (FLAML) | thin | deep (calibration, categoricals, refit) | deep |
| Evaluation | thin | deep (core views, comparison) | deep |
| Reporting + model card | thin | thin | deep (theme) |
| Lifecycle (register / promote / deploy) | thin | thin | deep (registry tables, inventory) |
| Inference | thin | deep | deep |
| Monitoring | stub | thin (health + drift tables, flags) | deep (health, drift); thin (performance); stub (impact) |
| Feature store integration | — | — | thin |
| Data observability integration | — | — | thin |
| Regression | shapes | thin, if cheap | deep (end to end) |
| Guided notebooks | thin | thin | deep (guidance reviewed by the LDS) |
| Experiment sweeps / window ablation | — | — | thin (the sweep function) |
| Tests | invariants + e2e | + migrations, bundle round trip | every function; CI / Sonar |
| LLM-assisted modelling | — | — | — (Phase 3) |

## Review cadence (D-084)
- Every major step (each M2 row, each M3 item) ends in an LDS review with a review guide (D-067).
  At most five "needs decision" items on the sync page; the rest is "for information".
- The LDS reviews design docs and the ML-critical code in full (dataset, Target Factory, training,
  calibration, evaluation) and samples the rest. No scheduled demos between the two.
- A fresh-context holistic review of the whole run at the end of each major step.

## Risks to these dates
| Risk | Trigger | Response |
|---|---|---|
| Review backlog grows | More than five "needs decision" items for a week | The LDS reviews designs and ML-critical code only; the SDS reviews with review guides |
| A spike fails (grouped CV, model formats) | Any spike result before 10-30 | Own client-grouped CV loop around FLAML (Q254); a family whose round trip fails is fixed in M2.3 rather than dropped, since M2 may not fall below the crunch (D-093) |
| External teams not available | No session booked by 11-06 | Stand-ins (the synthetic mart split into a "feature store" table; a flat monitoring export); integrations stay in M4 |
| Memory on the 8 GB Mac | An OOM in M2.3 or the M3 comparison | A `dev` preset of about 20k clients for daily work; the WSL2 PC for the comparison |
| Config questions reopen the spine (OD-10, OD-25) | Either still open on 10-26 | YAML, two levels and the identities are decided (D-086–D-088); the audit log's scope (Q241) and the level mapping are settled in M2.1 with reversible defaults; no revisit before M4 |
| The CDS reads December as release 1.0 | — | The exact plan goes to him once agreed with the LDS (D-097) |
