# Log
Verbose trail behind `worknotes/sync.md`, newest first. Updates on the same topic from the same or
neighbouring days share one entry, each keeping its date. Template and rules: `worknotes/README.md`.

### 2026-10-14 — Worknotes: sync page and log rules for the LDS
- 2026-10-14, sync page rules: new SDS rules for `worknotes/sync.md`, recorded in
  `worknotes/README.md` ("Writing `sync.md` for the LDS") and referenced from the doc-sync skill,
  `/brief` and `CLAUDE.md` §8:
  - new decisions by reference at the top;
  - review list most important first, then newest;
  - "since the last sync" only for what changes the LDS's picture (one bullet per topic; no
    tooling, versions, machine setup or "notes recorded" items).

  The LDS spends 30–60 minutes a day and only reads and reviews. The page was rewritten to match:
  - the "what the design baseline contains" digest and the history already covered by the
    2026-10-13 sync were removed (they repeated `docs/decisions.md`; the history stays here);
  - the open-questions table collapsed into the CDS meeting row;
  - the production-paths question moved to the CDS questions (e5);
  - all review items kept, reordered.
- 2026-10-14, recap and merged log: the sync page gains a terse "Last 7 days" section (one line
  per topic, kept for seven days, for circling back). Log entries on the same topic from the same
  or neighbouring days are merged, each update keeping its date; this log was restructured that way
  (14 entries → 5). Rules in `worknotes/README.md` and the doc-sync skill.
- Why: the page had grown long and noisy for a reader with 30–60 minutes a day; the compact page
  still needs a short memory of the week.
- Files: `worknotes/{README,sync,log}.md`, `.claude/skills/doc-sync/SKILL.md`,
  `.claude/commands/brief.md`, `CLAUDE.md` §8.
- Decisions / open decisions: none.

### 2026-10-14 — CDS meeting preparation: LDS sync follow-ups, D-058–D-061, meeting drafts
- 2026-10-14, LDS sync notes (from 2026-10-13) routed to their owner docs:
  - OD-06 reframed as a CDS question: keep the current folder structure that emulates the
    permission barriers? Added to CDS topic (d);
  - OD-07–OD-09: the SDS won't design the registry and deployment alone, especially if they are to
    become the unit's new registry type; the `lifecycle.md` proposals are now straw men. New
    OD-23: who builds them (an MLE/MLOps colleague?) and when that person joins; topic (e);
  - OD-13: MLflow is seen as a registry / experiment-tracking tool, not one for tracking decay over
    time, and the CDS is expected to agree; monitoring and the downstream stages need much more
    design. Phase 3 backlog item reworded to "MLflow for the registry and experiment tracking";
  - OD-10 leaning: record as much as possible; automated filters as rules in the config, human
    filters as lists, possibly with an explanation;
  - OD-15 widened to "Phase 2 modelling scope". The LDS is comfortable with FLAML only and binary
    only (a pinned package can add more later) and doubts anything gets built between a first and
    second release 2–3 months apart; the SDS's idea is FLAML only with binary + regression. Decided
    at the CDS meeting (a). D-020, D-037 and D-050 marked under review;
  - sync page review items kept (walked through on 2026-10-13, the LDS hasn't finished them).
- 2026-10-14, critique (Claude): pinning protects users' code, not the shared tables (scores,
  registry, monitoring, model card) that many pinned versions write to (`CLAUDE.md` §2), so
  regression's per-task spec should be designed in M1 even if only binary is built. FLAML can
  probably restrict the search to one model family (verified later the same day, below).
- 2026-10-14, answers to Q111–Q118:
  - Q112 → D-058: automated feature filters live in the config as rules; a frozen config on
    unchanged data reproduces their outcome; restated past months may change it, which is
    accepted; the model bundle freezes the features. OD-10 narrowed to human decisions and the
    flag case;
  - Q111: "mandatory" would have meant config validation rejecting an entry without a reason. New
    proposal after the SDS pointed out that 20 exclusions shouldn't need 20 comments: human lists
    are grouped with one note per group; only a `keep` group that resolves a flag must carry a note
    (it unblocks registration, D-031). SDS leaning to accept; confirm once built;
  - Q113 → D-059: register / promote / deploy thin but real until the registry has an owner;
  - Q114 → D-060: regression's per-task spec designed in M1 whatever OD-15 decides;
  - Q115: verified on FLAML 2.7.0 that `estimator_list` + `custom_hp` search one model family
    inside our own ranges; `config_history` keeps only improving trials (`docs/context/environment.md`);
  - Q116: the CDS meeting is on 2026-10-15, 2 × 30 min. Session 1: the crunch walkthrough (SDS)
    plus the direction overview; session 2: feedback plus questions;
  - Q117 (default accepted): per-month row and positive counts saved in the EDA artifacts so a
    restated source month shows up (`docs/components/eda.md`);
  - Q118: rename "builder" → SDS across the docs later, once no parallel session is writing;
  - role short forms SDS / LDS / CDS recorded in `docs/context/project.md`;
  - a parallel session had taken D-056 and D-057, so these decisions start at D-058.
- 2026-10-14, drafts round 1: `worknotes/chief_ds_meeting/overview.md` and `questions.md`. Goal
  agreed with the LDS: the CDS accepts the modelling half and is involved in designing everything
  downstream; unanswered questions are still raised for visibility. New topics (g) modelling half
  and (h) people, involvement and timeline.
- 2026-10-14, round 2: overview without fillers or estate size, built on the original plan the CDS
  reviewed around August, no wide ASCII boxes, only high-level principles, first release "before
  the end of the year", check-ins rather than demos. Questions: (g) dropped (the modelling half is
  agreed through d1, the stage structure), (h) folded into other topics, library vs service (b1)
  is the star, the release path no longer covers how code reaches the bank, e1 framed from the
  original plan's part-time ML engineering lane, regulated models added to a4.
- 2026-10-14, round 3: overview back to the first draft's structure, written as a design update
  rather than a pitch, timers removed. Questions: d3 (shared targets) answered "no" → D-061; e2
  (who else joins), e4 (outside models in the registry) and f3 (campaign link) dropped;
  "registered" merged with the lifecycle steps into one starred question. 23 questions, 8 starred.
- Why: the CDS meeting is on 2026-10-15.
- Files: `docs/roadmap.md`, `docs/decisions.md`, `docs/UPDATES.md`,
  `docs/context/{project,environment}.md`,
  `docs/components/{lifecycle,monitoring,config,feature_ledger,eda}.md`,
  `worknotes/chief_ds_meeting/{overview,questions}.md`, `worknotes/README.md`, `worknotes/sync.md`.
- Decisions / open decisions: D-058–D-061; OD-06–OD-10, OD-13, OD-15 updated; OD-23 opened.
- Still open: Q111 (confirm once built); the rename (Q118); the meeting itself.

### 2026-10-13 → 2026-10-14 — Synthetic data (M1): design round, spec, step 0 (Spark harness)
- 2026-10-13, design round 1 opened (Q76–Q105): the SDS described the feature groups (client
  description, flows and cash, digital, loans, wealth) and asked for proactive feature suggestions
  plus a proof plan per build step. Main points of Claude's review of `test_harness.md`:
  - the output becomes an upstream-style feature mart (current-month values plus backward rollups,
    one wide table per entity), no longer only a raw monthly panel;
  - the planted collinear-cluster and eligibility-defining traps would arise organically (rollups,
    product-specific flows);
  - new realistic mechanisms (loan top-ups, maturity closures, three-state wealth history) must
    also be expressed in the oracle, or it stops being the ceiling;
  - knock-on for Target Factory: the target spec must express counter increases and state
    transitions, not only thresholds on forward sums;
  - proof per step: check tables shared by tests and a dev notebook, a prefix-stability test as
    the no-leak proof, human gates after the population, flows and mart steps.
- 2026-10-13, round 1 answered, Q106–Q110 opened (defaults accepted unless listed):
  - holdings as 0/1 flags; "churned" from clients who held the product before the window plus
    1 → 0 transitions. Acquisition is one target (0 → 1), whether never or churned before, so
    Target Factory needs no separate state-change rule;
  - eligibility mostly income thresholds, half-strict (adoption low below the threshold, jumping
    at it). F9 (consent, KYC) dropped; of F10–F14 only term deposits kept; F15 dropped; the other
    suggestions accepted (F25, F26 later);
  - Q78: a rollup is null when its window reaches before relationship start; Q80: about 150
    columns; Q81: Private 1k, MM = 3 × UM; Q89: add FX; Q90: no top-ups, no opening dates; Q102: a
    size parameter to drop to 50k (the Mac has 8 GB);
  - build steps and checks approved, plus a temporary notebook with simplified EDA and
    aggregations to speed up the SDS's checks;
  - found: the Mac had no Java runtime and an empty `.venv`, both needed for step 0.
- 2026-10-14, spec written and step 0 built:
  - `docs/components/test_harness.md` rewritten as the spec, with the build plan and its statuses
    pinned at the top: feature mart shape, segment mix (Private 1k with Upper : Lower = 1 : 3,
    Priority 4k likewise, MM = 3 × UM), client description, income thresholds, products, maths,
    names, null rule, traps, ground truth, proof per step, temporary notebook;
  - final answers: Q107 the never / churned / active flag for term deposit and both wealth products
    only (churned clients re-adopt more often, so the flag carries signal); Q110 the Upper : Lower
    ratio swapped to 1 : 3; Q106, Q108, Q109 defaults. Q78: the null rule mirrors the retail
    dataset and is not something the framework enforces;
  - D-056 (feature mart), D-057 (environment adapter starts in M1); OD-16 narrowed to rates,
    thresholds and the second entity; glossary "feature mart"; Target Factory's binary rule kinds;
  - step 0 code: `synthetic/` package skeleton (own editable install), `core_modelling/_compat.py`
    (shim imported first), `core_modelling/environment.py` (`_get_spark_session`, local defaults,
    Arrow fallback off), `tests/conftest.py` (real Spark fixture), `tests/test_spark_roundtrip.py`.
    `pytest`: 2 passed in ~7 s; `ruff` clean;
  - found on the pinned versions: T1 still live (without the shim, `import pyspark.pandas` and
    `import flaml` fail); new trap T18 (Spark 3.4 can't read nanosecond timestamps that pandas
    writes to parquet, so month columns are dates); `libomp` missing on the Mac, so xgboost and
    `import flaml` failed to load; scipy 1.17.1 and plotly 7.1.0 pulled in transitively;
  - simplicity review: removed the unused `settings` parameter (comes back with `conf/local/` in M2);
  - code review (1 blocking, 4 suggestions, all applied): the month is a partition column, so it
    never went through parquet and the test didn't prove T18 (added a date column inside the file,
    with a null, and a boolean null); one library call (`builder.config(map=…)`) instead of a
    loop; why-comments on UTC and UI off; an unverified version claim dropped from the shim
    docstring; new M2 requirement: `getOrCreate()` silently reuses a kernel's session, so the bank
    path must not push local settings onto it and must fail loud on a wrong master.
- 2026-10-14, step 0 follow-ups:
  - scipy 1.16.2 and plotly 6.3.1 pinned in `requirements.txt` (other packages had pulled in newer
    versions: scipy via scikit-learn, LightGBM, XGBoost, CatBoost and SHAP; plotly via CatBoost). Verified: `pip check` clean, the
    ML stack imports, pytest green, report HTML embeds plotly.js 3.1.1 like the bank. plotly 7
    would bundle plotly.js 4; code written locally on 7 could fail inside the bank. D-042 status
    noted;
  - `libomp` installed by the SDS; the shim test imports `flaml` again, as planned;
  - the SDS works on the Mac only; the WSL2 PC is deferred, with a "Switching from the Mac"
    checklist in `docs/guides/setup_windows_wsl2.md`; step 0's proof is "green on the Mac";
  - notebooks will define their Spark session through the adapter with arguments (more than the
    crunch's bare `getOrCreate()`); an M2 requirement in `environment.md`.
- Files: `docs/components/{test_harness,environment,target_factory}.md`,
  `docs/{UPDATES,architecture,decisions,glossary,roadmap}.md`,
  `docs/context/{lessons,environment}.md`, `docs/guides/setup_{macos,windows_wsl2}.md`,
  `requirements.txt`, `requirements-dev.txt`, `synthetic/`, `src/core_modelling/{_compat,environment}.py`,
  `tests/{conftest,test_spark_roundtrip}.py`.
- Decisions / open decisions: D-056, D-057; D-042 status; OD-16 updated.
- Still open: the SDS's review of step 0; which Spark session arguments the bank needs (M2).

### 2026-10-12 → 2026-10-13 — Holistic review of the design baseline: findings and outcomes
- 2026-10-12, findings (Q56–Q65): a cross-component review of the whole uncommitted baseline. The
  mechanical checks were clean (no broken links, no dangling D/OD/T ids, renames complete).
  Findings:
  - §4.4 conflicts: the trade-off chart could choose on the test metric (D-037); EDA and Feature
    Checks label views ran on the window, which includes test clients; label-free PSI against the
    validation month; sweeps and the LLM loop chose variants on the validation month;
  - shapes: the model bundle was not a versioned artifact; binary-only hooks outside D-020's five
    dicts; the scores schema had no domain, split or batch id; config and data-definition hashes
    under-specified; the run id not unique per entity; the ledger keyed by `run_id` before a run
    exists;
  - D-031 × OD-10: resolving a flag after training changes the config hash, which forces a retrain
    before registration; D-031 also partly pre-decided OD-09;
  - gaps: final-fit policy; calibration without downsampling; drift reference on the true
    population; labels for monitoring; lifecycle CLI commands; the definition of done depends on
    the bank's change-request process;
  - simpler: a v0 synthetic generator for M1; registry tables serve as the Phase 2 inventory.
- 2026-10-13, outcomes (the SDS's answers, Q56–Q75):
  - D-047 (framework pinned per use case; settles OD-03), D-048 (§4.4: label checks on train-split
    clients, label-free checks never on the validation month), D-049 (§4.7: prior shift from the
    weighted rate + a general calibration step), D-050 (per-task spec; OD-15 by end of M1), D-051
    (versioned model bundle), D-052 (optional refit), D-053 (sweeps that pick are labelled
    optimistic; selection month with the LLM branch), D-054 (drift reference + labels for
    monitoring), D-055 (definition-of-done production step, soft); status notes on D-020, D-021,
    D-030, D-037;
  - roadmap: OD-03 deleted, OD-22 added (trade-off chart: test metric vs CV), OD-10/11/15/18
    extended, backlog and CDS topics (b), (e) updated;
  - `CLAUDE.md` §2 (pinning, bundle + drift reference versioned), §3 (per-task spec), §4.4, §4.7,
    §4.10 (source months assumed immutable); compat-guardian and ml-correctness-auditor aligned;
  - component docs: config (identity issues as open questions), dataset (calibration wording,
    refit frames, contract checks, ablation design), training (calibration, bundle, drift
    reference, refit, OD-22), target factory (labels for scored months), EDA and Feature Checks
    (train-split clients, comparison months), ledger (two keying issues), evaluation (optional
    validation on test clients), reporting, lifecycle, inference (pinned version), monitoring, run
    modes (lifecycle commands, entity selector), LLM assist (selection-month gate); architecture,
    project, glossary, environment, tests README, UPDATES;
  - deviation to check: EDA's population base rate per month stops at the window's end, because
    the gap months' target windows overlap the validation month's.
- Decisions / open decisions: D-047–D-055; OD-03 (settled), OD-10, OD-11, OD-15, OD-18, OD-22.
- Still open: OD-22 with the LDS; D-055 at the CDS meeting (e); hashes, ledger keying and scores
  format to specify later.

### 2026-10-12 — Design baseline (M0): review rounds, shared worknotes, review pass
- 2026-10-12, baseline after review rounds 1–3 (Q1–Q52) and the LDS notes:
  - rewrote CLAUDE.md (summary, classes rule, "major steps start wide", invariants §4.11–13, doc map
    + update triggers + creation rules), project.md (from → to table, goals, scope, Phase 2
    definition, entities/domains, roles), architecture.md, UPDATES.md;
  - decisions D-020–D-043; new roadmap.md (milestones, depth levels, backlog, OD-01–OD-21, CDS
    topics), glossary.md, components/dataset.md, components/feature_ledger.md;
  - rewrote every component doc; renamed data_creation → target_factory and tracking → monitoring;
  - lessons (T16, T17), environment (devcontainer libraries, Optuna, offline plotly), READMEs,
    guides, skills and agents; added `holistic-review` and `/brief`, `/handover`, `/resume`.
- 2026-10-12, shared worknotes and reading guide (round-4 Q53–Q55, confirmations 1–3):
  - worknotes committed for the SDS and the LDS: `sync.md`, `log.md`, `handovers/` (D-044);
  - new `docs/README.md` with the reading order and the stage → component map (D-045);
  - sampling (Q12b) and window ablation (Q12c) answers added to the dataset, training, evaluation,
    run-modes and synthetic-data docs, OD-17 and the backlog;
  - D-033 lifecycle vocabulary and D-037 (trade-off chart on in-time data only) confirmed; the
    depth-level wording stays proposed (OD-01).
- 2026-10-12, review pass before compacting: questions for the LDS (example notebooks, "necessary
  inputs" for model docs, monitoring in Phase 2 vs 3, sandpit vs production paths); lifecycle
  urgency and sandpit-path note; OD-01, OD-04 (Nexus with version pins), OD-13 (MLflow lead time),
  OD-15 (quantile-loss idea); target factory's aggregation starting list; D-046 (no per-source
  column catalogue).
- Decisions / open decisions: D-020–D-046; OD-01–OD-21.

### Earlier
- 2026-10-05 — Vendored and adapted review/debugging skills and agents (D-019).
- 2026-09-30 — Repo bootstrapped for Phase 2.
