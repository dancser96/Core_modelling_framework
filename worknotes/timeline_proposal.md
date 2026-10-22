# Timeline proposal
_Written 2026-10-20; reshaped 2026-10-21 and 10-22 after the SDS's planning notes. A proposal to
agree with the LDS (Q218), then to share with the CDS as the exact plan (D-097). Settled already:
the plan is milestones with dates per stage, not a task board, and December is a pre-release with
two purposes (D-109); the first change request is release 1.0, carrying the framework only
(D-115). Once agreed, the dates move to `docs/roadmap.md`. Findings behind it:
`holistic_review.md`; open questions: `holistic_review_questions.md`._

## Verdict
- **Two build rounds, each followed by a short run-through:**
  1. Round 1 (10-26 – 12-08, about 28 working days): every component end to end, then the exit
     points close to final and calibration right.
  2. Run-through 1 (12-09 – 12-18, 8 days): a real run as a user would make it, fixes only, then
     the code moves into the bank's internal repo, committed and demonstrated. This is **the
     December pre-release**. It doesn't reach production: the year-end change freeze (D-115).
  3. Round 2 (01-04 – 02-05, 25 days): depth where the pre-release showed it matters, both
     integrations, regression end to end, tests to every function.
  4. Run-through 2 (02-08 – 02-19, up to 10 days): the same procedure, ending in **release 1.0**,
     submitted as the first change request. Production follows once that change request clears;
     the first one is slow.
- **December's two purposes (D-109)** need a working run and stable exit points, not depth
  everywhere. The year-end result is a run inside the bank with its reports. The downstream teams
  get exit points that change little afterwards, so they can plan their work on them.

## Why this shape
1. **The skeleton still comes first inside round 1.** Every stage is built thin before anything
   deepens, so problems between stages surface in November, not in the run-through.
2. **Shapes final, contents thin.** Round 1's last block brings the exit points (`glossary.md`)
   close to final: the scores table and manifest, the model bundle, registry records, monitoring
   tables and the model card. They are what the downstream teams plan on, and from release 1.0
   they only grow (D-107).
3. **The run-through is mirrored before release 1.0.** The same procedure tests the release
   checklist once in December. Round 2 is shorter than round 1 (25 days against 28): the
   run-throughs absorb the stabilisation, and the pre-release shows which depth matters.

## Dates

| Dates | Block | Days | Goal | Done when |
|---|---|---|---|---|
| 10-22 – 10-23 | Planning | 2 | This plan agreed with the LDS; the spikes started (the SDS) | Q218 answered |
| 10-26 – 11-20 | Round 1a: walking skeleton (S1–S4) | 20 | Every stage thin, end to end on synthetic data | `run` end to end; `deploy` to a production-tier path and inference from it; nothing the crunch did is missing (D-093) |
| 11-23 – 12-08 | Round 1b: exit points and calibration | ~8 of 12 | Exit-point shapes close to final; calibration right (D-104); the EDA + Feature Checks report presentable | The LDS has reviewed the exit-point shapes; calibrated scores match the oracle's probabilities on synthetic data |
| 12-09 – 12-18 | Run-through 1 → **pre-release** | 8 | 12-09 – 12-14: a user's run end to end, fixes only. 12-15 – 12-18: into the internal repo, a smoke run on a real mart, a demo | The code runs inside the bank to a local model; the reports to show |
| 12-21 – 01-01 | Slowdown | ~6 of 10 | Fixes from the move-in; the two integration designs; round 2's priorities | — |
| 01-04 – 02-05 | Round 2: depth and integrations | 25 | Depth the pre-release showed matters; both integrations thin; regression end to end; tests to every function | Each item reviewed by the LDS |
| 02-08 – 02-19 | Run-through 2 → **release 1.0** | ≤ 10 | The same procedure, plus CI / Sonar; aimed at 02-12 | The Phase 2 definition of done (D-021, D-075); release 1.0 submitted as the first change request (D-115); shared formats freeze from its first row in the bank (D-107) |

## The plan table

### Stages
Round 1a's 20 days are split by weight, not evenly. S1 carries the most new design (the config
spine, with the audit log if Q241 is adopted, the identities and migrations, plus the dataset and
Target Factory). S3 carries the ML-critical code the LDS reads in full, and three families' round
trips. S2 and S4 are thinner code on top of S1's shapes.

| Stage | When | Days | Goal |
|---|---|---|---|
| S1 Foundation | 10-26 – 11-02 | 6 | One config gives the train, test and validation frames, with eligibility and split logs |
| S2 Understanding | 11-03 – 11-06 | 4 | The traps are flagged, the EDA + Feature Checks report opens offline, the ledger shows each feature's trail |
| S3 Modelling | 11-09 – 11-16 | 6 | A calibrated model beats the baselines and never the oracle; three families round-trip without pickle; no CV fold mixes a client's rows (D-120) |
| S4 Operations | 11-17 – 11-20 | 4 | Register, promote, deploy, score and monitor from the CLI and the notebooks |
| S5 Integrations and release | Round 2 and both run-throughs | — | Feature store and data observability thin; regression end to end; tests and CI / Sonar |

Round 1b and round 2 deepen across stages rather than stage by stage.

### Depth per component (OD-01)
Depth levels as in `docs/roadmap.md` (full · deep · thin · stub). "Shape final" means the output's
schema is close to final (an exit point) while its content is thin. "Nice to have" lists optimistic
additions, done only if the round has room; they are the first cut.

| Stage | Component | Pre-release (Dec) | Release 1.0 (Feb) | Nice to have |
|---|---|---|---|---|
| S1 | Config spine (YAML, levels, identities, audit log if Q241 is adopted) | deep | deep | A command showing where each resolved value came from |
| S1 | Environment adapter | deep (bank-verified) | deep | — |
| S1 | Dataset (window, split, sampling) | thin (uniform negative downsampling, D-117) | deep (simple sampling: options 1, 2 or none, D-123) | — |
| S1 | Target Factory | thin (one binary rule family, lineage) | deep (other rule families, labels for scored months) | Incremental builds |
| S2 | EDA | thin; report presentable | deep (key-feature deep dives, low-prevalence charts) | Pivot functions |
| S2 | Feature Checks | thin (quality, leakage, time alignment, lineage) | deep (stability) | — |
| S2 | Feature ledger | thin | deep (joined with the audit log) | — |
| S2 | Reporting | thin (HTML, embedded plotly, styled tables) | deep (theme file) | — |
| S2 | Synthetic data | as accepted (M1) | plus noise and very-low-fill columns (the LDS's to-dos) | — |
| S3 | Training (FLAML) | thin; client groups (D-120); calibration chain right (D-104); bundle shape final | deep (categoricals, refit with checks, automated selection) | — |
| S3 | Evaluation | thin (core views, reliability among them) | deep (comparison, stratified) | Window ablation and the sweep function |
| S3 | Model card | shape final | deep | — |
| S4 | Lifecycle (register / promote / deploy) | thin; records shape final (D-111) | deep (registry tables, inventory) | — |
| S4 | Inference | thin; scores table and manifest shape final | deep (reinference) | — |
| S4 | Monitoring | frame in place: four layers, tables with flags, shape final | frame deep, content light (D-112) | — |
| S4 | CLI and Python API | thin | deep | — |
| S4 | Guided notebooks | thin | deep (guidance reviewed by the LDS) | — |
| S5 | Feature store integration | — (learn session; design in the slowdown) | thin | — |
| S5 | Data observability integration | — (learn session; design in the slowdown) | thin | — |
| S5 | Regression | shapes (per-task spec entries) | end to end | — |
| S5 | Tests | invariants, migrations, bundle round trip, e2e on `unit` | every function; CI / Sonar | — |
| — | LLM-assisted modelling | — | — (Phase 3) | — |

Changes from the first draft: training's categoricals and refit, and the deep EDA, Feature Checks
and Evaluation, move from December to round 2; the window ablation and sweep function become a
nice to have; monitoring's content stays light at release 1.0 (D-112); sampling stays simple,
and advanced sampling moves to the Phase 3 wishlist (D-123).

## Work streams beside the critical path
- **Spikes (the SDS runs them, Claude reminds; due before S3, 11-09):** (1) FLAML 2.7's group
  split on the synthetic data (D-120 needs it, or its fallback; no sample weights in Phase 2,
  D-123); (2) non-pickle round trips for
  `lgbm`, `xgboost`, `catboost`; (3) Arrow `toPandas` with date columns; (5) plotly in the bank's
  JupyterLab, opening time included (the SDS, inside, later). Spike 4 is dropped (D-105).
- **Learn sessions, booked by the LDS, by 11-06:** platform / MLOps (change-request steps and the
  freeze, registry owner OD-23 (who builds the registry and deployment), Sonar quality gate,
  scheduling); the feature store team (OD-26: how a use case reads from the feature store); the
  data observability team (OD-13: how monitoring feeds that framework). The data observability
  session matters before round 1b, since its needs shape the monitoring tables. Both integration
  designs are written in the slowdown.
- **The first change request (D-115):** release 1.0, the framework only. If the bank allows it,
  start its first-time steps (security review of the saved formats, the deployment path) when the
  freeze lifts in January, using the pre-release as material, so only the final submission waits
  for 1.0 (unverified: the freeze's dates and the process are unknown).

## Assumptions
- The SDS works on the framework about 6 hours a day with Claude and reviews every line; the LDS
  reads 30–60 minutes a day. Review time, about 40% of build time, is inside each block.
- The week of 11-30 is mostly lost (National Day's two public holidays, plus leave): counted as one
  working day. 12-21 – 01-01 is a slowdown, not a stop: 2–3 days of leave plus 01-01, so about six
  slower days, used for fixes and designs rather than new build.
- The year-end change freeze is long; its dates are unknown. Nothing in the plan needs a change
  request before release 1.0.
- External teams are unavailable until a session is booked. Nothing on the critical path depends
  on them before round 2, except that the data observability session should shape the monitoring
  tables.
- One memory-heavy job at a time on the 8 GB Mac; the WSL2 PC takes round 2's heavy comparisons.

## How each block ends (D-084)
- Each stage S1–S4 and round 1b ends in the SDS's review and the LDS's review with a review guide
  (D-067). At most five "needs decision" items on the sync page.
- The LDS reviews design docs and the ML-critical code in full (dataset, Target Factory, training,
  calibration, evaluation) and samples the rest.
- A fresh-context holistic review closes each round, before its run-through.
- A run-through: the SDS takes one use case from config to scores through the guided notebooks
  and the CLI, on the canonical synthetic data, as a user would. The LDS reads the reports and the
  exit points. Findings become a fix list; nothing new is built.

## Risks to these dates

| Risk | Trigger | Response |
|---|---|---|
| Review backlog grows | More than five "needs decision" items for a week | The LDS reviews designs and ML-critical code only; the SDS reviews with review guides |
| Round 1a slips | S4 not done by 11-20 | Round 1b keeps the exit points; calibration depth and the presentable report move to round 2 |
| Round 1b is short | The lost week of 11-30 | The exit points come first; the presentable report is the first item to move to round 2 |
| An exit point's shape changes after the pre-release | A downstream team or the data observability session needs a different shape | Cheap until release 1.0's first shared row (D-107); collect the changes in run-through 1 |
| Round 2 is too full | Behind plan in its third week | Cut the nice to haves, then depth in EDA and Evaluation. The integrations, regression and tests stay (D-075, D-097) unless the CDS agrees otherwise |
| A spike fails | Any spike result before 11-09 | A family whose round trip fails is fixed in S3 rather than dropped (D-093); a failed group split falls back to a client-grouped holdout (D-120) |
| External teams not available | No session booked by 11-06 | Stand-ins (the synthetic mart split into a "feature store" table; a flat monitoring export); the integrations stay in round 2 |
| Memory on the 8 GB Mac | An out-of-memory error in S3 or round 2 | The `dev` preset of about 20k clients for daily work; the WSL2 PC for comparisons |
| Config questions reopen the spine | OD-10 (Q241) or OD-25 still open on 10-26 | Settled in S1 with reversible defaults; no revisit before round 2 |
| The first change request is slow | Its first-time steps can't start before 1.0 is final | Release 1.0 is ready by 02-19 but reaches production later (March or after); tell the CDS early |

## Mapping to the roadmap's milestones
M2 is round 1a, M3 round 1b, M4 round 2, and M5 the two run-throughs. Once agreed, the roadmap's
milestones table is renamed to these blocks.
