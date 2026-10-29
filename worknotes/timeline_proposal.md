# Timeline proposal
_Written 2026-10-20; reshaped 2026-10-21 and 10-22. The working assumption (D-022): we build on
it now, while the LDS still reviews it and stakeholder buy-in comes in the week of 10-26. Once agreed, the
dates and the depth per component move to `docs/roadmap.md` (OD-01), and the plan goes to the CDS
(D-022). Settled with it: milestones with dates per stage, not a task board, and December as a
pre-release with two purposes (D-022); release 1.0 as the first change request, framework only
(D-021). Milestone IDs: round 1 is M2 + M3, run-through 1 is M5a, round 2 is M4, and run-through
2 is M5b._

## Verdict
- **Two build rounds, each followed by a short run-through:**
  1. Round 1 (10-26 – 12-08, about 28 working days): every component end to end, then the exit
     points close to final and calibration right.
  2. Run-through 1 (12-09 – 12-18, 8 days): a real run as a user would make it, fixes only, then
     the code moves into the bank's internal repo, committed and demonstrated. This is **the
     December pre-release**. It doesn't reach production: the year-end change freeze (D-021).
  3. Round 2 (01-04 – 02-05, 25 days): depth where the pre-release showed it matters, both
     integrations, regression end to end, tests to every function.
  4. Run-through 2 (02-08 – 02-19, up to 10 days): the same procedure, ending in **release 1.0**,
     submitted as the first change request. Production follows once that change request clears;
     the first one is slow.
- **December's two purposes (D-022)** need a working run and stable exit points, not depth
  everywhere. The year-end result is a run inside the bank with its reports. The downstream teams
  get exit points that change little afterwards, so they can plan their work on them.

## Why this shape
1. **The skeleton still comes first inside round 1.** Every stage is built thin before anything
   deepens, so problems between stages surface in November, not in the run-through.
2. **Shapes final, contents thin.** Round 1's last block brings the exit points (`glossary.md`)
   close to final: the scores table and manifest, the model bundle, registry records, monitoring
   tables and the model card. They are what the downstream teams plan on, and from release 1.0
   they only grow (D-007).
3. **The run-through is mirrored before release 1.0.** The same procedure tests the release
   checklist once in December. Round 2 is shorter than round 1 (25 days against 28): the
   run-throughs absorb the stabilisation, and the pre-release shows which depth matters.

## The plan
The week of 11-30 counts as mostly lost (public holidays), and 12-21 – 01-01 as a slowdown
for fixes and the integration designs.

| # | Dates | Milestone | Goal | Done when |
|---|---|---|---|---|
| M0 | to 10-12 | Design baseline | Docs rebuilt from three review rounds and the LDS's notes | Done 2026-10-12 |
| M1 | 10-13 – 10-21 | Synthetic data + local Spark harness | `synthetic/` (~100k × 24 months, traps, oracle), generated into `data/01_raw/`; Spark fixtures; the second task chosen | Done: accepted by the LDS 2026-10-21, three future to-dos (backlog); regression chosen (D-020), its per-task spec still to design (D-050) |
| M2 | 10-26 – 11-20 | Round 1a: walking skeleton, in stages M2.1–M2.4 below | Every stage thin, end to end on synthetic data, binary task | `run` end to end; `deploy` to a production-tier path and inference from it; nothing the crunch did is missing (D-037) |
| M3 | 11-23 – 12-08 | Round 1b: exit points and calibration | Exit-point shapes close to final; calibration right (D-049); the EDA + Feature Checks report presentable. Priorities re-evaluated as we go | The LDS has reviewed the exit-point shapes; calibrated scores match the oracle's probabilities on synthetic data |
| M5a | 12-09 – 12-18 | Run-through 1 → **pre-release** | A user's run end to end, fixes only; then into the internal repo, a smoke run on a real mart, a demo. Not production: the year-end freeze (D-021) | The code runs inside the bank to a local model; the reports to show |
| M4 | 01-04 – 02-05 | Round 2: depth and integrations | Depth the pre-release showed matters; both integrations thin; regression end to end; tests to every function | Each item reviewed by the LDS |
| M5b | 02-08 – 02-19 | Run-through 2 → **release 1.0** | The same procedure, plus CI / Sonar; aimed at 02-12 | The definition of done (D-021); submitted as the first change request (D-021); shared formats freeze from its first row in the bank (D-007) |

**M2's stages,** sized by weight:

| Stage | Dates | Days | Goal |
|---|---|---|---|
| M2.1 Foundation | 10-26 – 11-02 | 6 | One config gives the train, test and validation frames, with eligibility and split logs |
| M2.2 Understanding | 11-03 – 11-06 | 4 | The traps are flagged, the EDA + Feature Checks report opens offline, the ledger shows each feature's trail |
| M2.3 Modelling | 11-09 – 11-16 | 6 | A calibrated model beats the baselines and never the oracle; three families round-trip without pickle; no CV fold mixes a client's rows (D-106) |
| M2.4 Operations | 11-17 – 11-20 | 4 | Register, promote, deploy, score and monitor from the CLI and the notebooks |

M3 and M4 deepen across stages rather than stage by stage. Two deepening rounds are planned; don't
plan for more.

### Depth per component
Levels as in `docs/roadmap.md` (full · deep · thin · stub). "Shape final" means the output's schema is close to final (an exit point) while
its content is thin. "Nice to have" lists optimistic additions, done only if the round has room;
they are the first cut. Stage 5 (integrations and release) runs in M4 and both run-throughs.

| Stage | Component | Pre-release (Dec) | Release 1.0 (Feb) | Nice to have |
|---|---|---|---|---|
| 1 | Config spine (YAML, levels, identities, decision audit log) | deep | deep | A command showing where each resolved value came from |
| 1 | Environment adapter | deep (bank-verified) | deep | — |
| 1 | Dataset (window, split, sampling) | thin (uniform negative downsampling, D-117) | deep (simple sampling: options 1, 2 or none, D-117) | — |
| 1 | Target Factory | thin (one binary rule family, lineage) | deep (other rule families, labels for scored months) | Incremental builds |
| 2 | EDA | thin; report presentable | deep (key-feature deep dives, low-prevalence charts) | Pivot functions |
| 2 | Feature Checks | thin (quality, leakage, time alignment, lineage) | deep (stability) | — |
| 2 | Feature ledger | thin | deep (joined with the audit log) | — |
| 2 | Reporting | thin (HTML, embedded plotly, styled tables) | deep (theme file) | — |
| 2 | Synthetic data | as accepted (M1) plus the LDS's noise, constant, redundant and very-low-fill columns (0.5.0) | plus the `unstable` kind | — |
| 3 | Training (FLAML) | thin; client groups (D-106); calibration chain right (D-049); bundle shape final | deep (categoricals, automated selection; retraining keeps the data definition, D-052) | — |
| 3 | Evaluation | thin (core views, reliability among them) | deep (comparison, stratified) | Window ablation and the sweep function |
| 3 | Model card | shape final | deep | — |
| 4 | Lifecycle (register / promote / deploy) | thin; records shape final (D-111) | deep (registry tables, inventory) | — |
| 4 | Inference | thin; scores table and manifest shape final | deep (reinference) | — |
| 4 | Monitoring | frame in place: four layers, tables with flags, shape final | frame deep, content light (D-040) | — |
| 4 | CLI and Python API | thin | deep | — |
| 4 | Guided notebooks | thin | deep (guidance reviewed by the LDS) | — |
| 5 | Feature store integration | — (learn session; design in the slowdown) | thin | — |
| 5 | Data observability integration | — (learn session; design in the slowdown) | thin | — |
| 5 | MLflow (registry, experiment tracking; if confirmed available, D-111) | — (M2.4's records map onto it) | thin | — |
| 5 | Regression | shapes (per-task spec entries) | end to end | — |
| 5 | Tests | invariants, migrations, bundle round trip, e2e on `unit` | every function; CI / Sonar | — |
| — | LLM-assisted modelling | — | — (Phase 3) | — |

## Work streams beside the critical path
- **Spikes (the SDS runs them, Claude reminds; due before M2.3, 11-09):** (1) FLAML 2.7's group
  split on the synthetic data (D-106 needs it, or its fallback; no sample weights in Phase 2,
  D-117); (2) non-pickle round trips for
  `lgbm`, `xgboost`, `catboost`; (3) Arrow `toPandas` with date columns; (5) plotly in the bank's
  JupyterLab, opening time included (the SDS, inside, later). Spike 4 is dropped (D-036).
- **Learn sessions, booked by the LDS, by 11-06:** platform / MLOps (change-request steps and the
  freeze, registry owner OD-23 (who builds the registry and deployment), Sonar quality gate,
  scheduling); the feature store team (OD-26: how a use case reads from the feature store); the
  data observability team (OD-13: how monitoring feeds that framework). The data observability
  session matters before round 1b, since its needs shape the monitoring tables. Both integration
  designs are written in the slowdown.
- **The first change request (D-021):** release 1.0, the framework only. If the bank allows it,
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

## How each block ends (D-072)
- Each stage M2.1–M2.4 and round 1b ends in the SDS's review with a review guide (D-003) and the
  LDS's review. The decisions the LDS must take are the short-term open decisions in the roadmap.
- The LDS reads the design docs and the important parts of the ML-critical code (dataset, Target
  Factory, training, calibration, evaluation), and tries the functionality and the notebooks
  (D-072 (i)).
- A fresh-context holistic review closes each round, before its run-through.
- A run-through: the SDS takes one use case from config to scores through the guided notebooks
  and the CLI, on the canonical synthetic data, as a user would. The LDS reads the reports and the
  exit points. Findings become a fix list; nothing new is built.

## Risks to these dates

| Risk | Trigger | Response |
|---|---|---|
| Review backlog grows | More than five items on the sync page's review list for a week | The LDS reviews designs and ML-critical code only; the SDS reviews with review guides |
| Round 1a slips | M2.4 not done by 11-20 | Round 1b keeps the exit points; calibration depth and the presentable report move to round 2 |
| Round 1b is short | The lost week of 11-30 | The exit points come first; the presentable report is the first item to move to round 2 |
| An exit point's shape changes after the pre-release | A downstream team or the data observability session needs a different shape | Cheap until release 1.0's first shared row (D-007); collect the changes in run-through 1 |
| Round 2 is too full | Behind plan in its third week | Cut the nice to haves, then depth in EDA and Evaluation. The integrations, regression and tests stay (D-021, D-022) unless the CDS agrees otherwise |
| A spike fails | Any spike result before 11-09 | A family whose round trip fails is fixed in M2.3 rather than dropped (D-037); a failed group split falls back to a client-grouped holdout (D-106) |
| External teams not available | No session booked by 11-06 | The feature-store settings of the release example stay commented out (D-021); a flat monitoring export stands in; the integrations stay in round 2 |
| Memory on the 8 GB Mac | An out-of-memory error in M2.3 or round 2 | The `dev` preset of about 20k clients for daily work; the WSL2 PC for comparisons |
| Config questions reopen the spine | OD-25 (the automation-level mapping) still open on 10-26 | Settled in M2.1 with reversible defaults; no revisit before round 2 |
| The first change request is slow | Its first-time steps can't start before 1.0 is final | Release 1.0 is ready by 02-19 but reaches production later (March or after); tell the CDS early |
