# Log
Verbose trail behind `worknotes/sync.md`, newest first. Updates on the same topic from the same or
neighbouring days share one entry, each keeping its date. Template and rules: `worknotes/README.md`.

### 2026-10-25 — Synthetic data: the LDS's to-dos reviewed and planned
- 2026-10-25: the SDS asked for a review of the synthetic build and a plan for the LDS's
  three to-dos (noise columns of several kinds, very low fill rates, every such column named like
  the traps), given that the first target build and run-through is credit-card acquisition.
  Findings: the to-dos were recorded for M4; on the card use case no column today tests
  missingness, cardinality, the missingness-pattern leak, the time-alignment check or the process
  leak (the last two sit on the personal loan, whose count-rise target is M4). Proposal: pull the
  to-dos into Stage 1's major step 2 as a new minor step 2b (eight trap columns on in every
  preset: a random flag, a 300-level categorical, a noisy copy of `casa_bal`, two low-fill
  columns, a leak through missingness, card twins of the shifted and process-leak kinds; version
  0.5.0; one regeneration with the holdings table and the `dev` preset; existing columns
  byte-identical through a new `noise` stream), a 2c regenerate-and-document step, the trap
  summary as the acceptance list for "the traps are flagged" (kind → Feature Checks step, kept
  in the tests), and the `unstable` kind deferred to M4. Q379–Q386 with defaults.
- The questions first landed at the end of the Stage 1 file, which another chat is working in;
  the SDS objected, and they moved to their own file, `worknotes/synthetic_questions.md`, with
  the Stage 1 file pointing at it.
- 2026-10-25, answers: defaults throughout. Q380: the LDS meant a constant column ("one value");
  the second reading, informative on its own but redundant given others, is kept. The catalogue
  loses the noisy copy and gains two constant columns (string, numeric) and `relationship_months`
  beside `relationship_days`: ten columns, 147 → 157. Q386: the SDS asked how a trap-name mapping
  translates to real data; answer in the file: it is a test over synthetic data, the framework
  flags name-blind (a code-rule guard asserts `_trap_` never appears in `src/core_modelling/`);
  where the test runs inside the bank depends on whether `synthetic/` travels with the light
  suite, unsettled (the package calls itself dev-only while the tests import it). Q387 added:
  which chat builds 2b (default: this one, now; 2c once, after the Stage 1 chat's 2a).
- Files: `worknotes/synthetic_questions.md` (new), `worknotes/README.md` (registered),
  `worknotes/sync.md`, this log.
- Still open: Q387; whether `synthetic/` goes into the bank with the light suite (D-014).

### 2026-10-25 — Inconsistency questions closed
- 2026-10-25: the SDS answered Q374 with the alternative: in Phase 2, `register` relies on the
  per-family round-trip check of the plain-data model; re-scoring the stored test split with each
  model's copy and failing loud on a difference is a Phase 3 wishlist question. With every
  question answered, the SDS asked to delete `worknotes/inconsistency_questions.md`.
- Files: `docs/decisions.md` (D-051 and its status), `docs/roadmap.md` (Phase 3 wishlist),
  `docs/components/lifecycle.md` (register), `docs/UPDATES.md` (the log lines that pointed at the
  file), `worknotes/README.md` (its row removed), `worknotes/sync.md`, this log;
  `worknotes/inconsistency_questions.md` deleted.
- Decisions / open decisions: D-051 extended.
- Still open: MLflow's availability (OD-08).

### 2026-10-25 — Stage 1 questions, round 2
- 2026-10-25: the SDS answered round 1: defaults throughout, with a super slim synthetic holdings
  table (Q352), Phase 3 references removed unless a Phase 3 requirement shapes how something is
  built (Q353), combined and reusable eligibility expressions (Q355), `conf/local` only needs to
  work on the laptop (Q362), and both source joins as left joins from a governing spine with
  duplicate-key checks and match counts (Q373). Asked for explanations of Q358, Q364, Q365, Q367,
  Q371, the training fields and the stage sections (Q354), and what top-N means (Q360).
- Round 2, first draft: explanations in chat and an appendix, plus Q375–Q378; Q354's layout was
  left unchanged. The SDS asked for a redo: unanswered questions are accepted defaults, and the
  questions asked about are reframed in the file with context, with the SDS's points worked in.
- Round 2, redo: the questions file is rewritten. Settled items are listed as settled with the
  SDS's changes; Q375–Q378 are folded back into the questions they came from; six questions are
  rewritten in place with context, an example, options and a default. Q354's YAML carries the
  ordered sources with the governing spine, `define` / `filter` eligibility steps,
  `data.model_input`, one `decision` block for everything declared before results, a shared
  `strata` section and every stage section in full (the training section with families,
  budgets, seeds, search ranges, selection, categoricals, calibration, sampling). Q365 maps the
  crunch's saved model input onto the design, checked by the data-definition hash. Q371 sizes a
  collect from a row count and bytes per row measured on a sample, against a budget in GB.
- The full rewrite overwrote round 3 (written by a parallel session minutes earlier); it was
  restored from that session's transcript, then moved by that session to
  `worknotes/synthetic_questions.md`.
- 2026-10-25, check after the move: the Stage 1 file matches the rewrite, and the synthetic
  file matches round 3 (references fixed, "this stage" → "Stage 1"). The check against the
  SDS's round-1 answers found details of accepted defaults dropped in the condensed settled
  section; restored: the approved OD-25 mapping table and the level-move rule (Q360), the three
  source settings and the refused `feature_store` format (Q352), the SDS's `== True` form (Q355),
  one key naming across sources (Q357), the per-task contract checks (Q372), the target source's
  role and the column-collision rule (Q373).
- Files: `worknotes/m2_1_foundation/questions.md`, this log, `worknotes/sync.md`.
- Still open: Q354 (a)–(c), Q358, Q364, Q365, Q367, Q371; then the plan.

### 2026-10-23 — Stage 1 (M2.1 Foundation) kick-off: design questions
- 2026-10-23: the SDS opened the Stage 1 build (config spine, environment adapter, Target Factory,
  dataset): first the design questions, then a plan in major and minor steps (D-072 (a)). Three
  first comments on Target Factory: optional but designed together with the dataset, so the
  several-sources demonstration matters; Phase 2 has no feedback into the feature store (OD-26);
  Phase 3 references leave the build docs and live only in the roadmap. New working rule: a
  `worknotes/<stage>/` folder holds the stage's questions, plan and review guide and is deleted
  when the stage is done.
- Written: `worknotes/m2_1_foundation/questions.md`, Q349–Q373 in five sections (scope; config
  spine; adapter; Target Factory; dataset) with defaults, a concrete YAML layout, a `conf/local`
  environment file, the OD-25 level mapping as a table, and eleven assumptions (hash-enforced
  immutability, migrations machinery, the target table, the `Frames` dataclass, tests). Numbering
  continues after Q346–Q348, which another session added to the inconsistency file the same day.
- Applied now: `docs/components/target_factory.md` (Purpose, requirement 2, design constraints,
  Related and Open questions; status `designing` as in `UPDATES.md`); the OD-19 row in
  `docs/roadmap.md` now holds the aggregation list that was in the doc; `worknotes/README.md`
  registers the stage folder.
- Files: `worknotes/m2_1_foundation/questions.md`, `docs/components/target_factory.md`,
  `docs/roadmap.md`, `worknotes/README.md`, `worknotes/sync.md`, this log.
- Decisions / open decisions: none yet; OD-25's proposed mapping is Q360.
- Still open: Q349–Q373; the plan.

### 2026-10-23 — Inconsistency answers applied
- 2026-10-23, round 2 (closes the questions): Q306 no log of who signs off or approves in Phase 2,
  a Phase 3 wishlist question instead (D-033); Q313 EDA and Feature Checks use all clients, the
  client split comes after Feature Checks, from Training on everything is train-only, the cost
  stated in the model results report (D-030 changed, `CLAUDE.md` §4.4 and the auditor agent
  reworded); Q320 validation shown everywhere in Phase 2, people trusted, gating data a Phase 3
  wishlist question (D-083); Q343 a Phase 2 production retrain keeps window and clients, only the
  inference month moves (D-052, D-088; my reading of "all three changeable" was wrong); Q344
  "limited to Target Factory" means limited to Stage 1, the M2.1 Foundation components where data
  comes in (D-021); Q346 register always writes the plain-data model (D-051); Q347 the validation
  month changes only through an audit-log entry, refused when Feature Checks compared that month
  (D-088, `config.md`). Defaults taken: Q328 (pruning on the calibration folds; the gap's train side
  unsampled; D-106), Q332 (OD-12 covers EDA, Feature Checks and Evaluation), Q342 (fail loud over
  the budget; D-117), Q345 (MLflow's shape; D-111, OD-08), Q348 (the production retrain's check;
  D-052). `worknotes/inconsistency_questions.md` closed, kept until the SDS says to delete it. MLflow
  added to the plan's integration stage; the plan's feature-store stand-in replaced by the
  commented-out settings.
- 2026-10-23: the SDS answered Q302–Q332 of the inconsistency sweep; questions left unanswered took
  their proposed default.
- Answers: Q302 production retrains the recipe on the same data definition by default, not
  retraining is allowed, extended data is Phase 3; Q303 the sandpit (local and registered on HDFS)
  may hold any format, pickle only matters for the move to production; Q304 all three FLAML families
  in M2, fewer would be less than the crunch; Q308 no sample weights in Phase 2; Q309 sampling only
  when the config declares it, for a rare target or the budget; Q310 the feature store example in
  three source settings, two commented out until inside the bank; Q312 withdrawn (D-128 doesn't
  bake a retail rule in: the use case name is copied); Q316 a use case = config + audit log, several
  per repo; Q319 train and validation months in the config, the inference month a run argument, all
  three settable in a production retrain; Q327 MLflow in Phase 2 is the goal and shapes the build if
  integrated, the feature store is limited to Target Factory, the data observability framework
  shapes the build once seen in use; Q331 reports from EDA, Feature Checks, the model results
  (Evaluation after FLAML training) and Monitoring.
- Defaults taken: Q305 one sign-off gate after training; Q307 the interface is the function triple;
  Q311 full tests by release 1.0; Q314 `CLAUDE.md` §4.12 reworded (prior shift or weights); Q315
  docs stay live, D-072 (j) "design docs frozen until M4" dropped and (k), (l) re-lettered (j), (k);
  Q317 `automation_level` from M2.1; Q318 the retail default as an example comment; Q321 no CLI level
  override; Q322 the Public API adds the audit-log functions and the session function (public at
  M2.1); Q323 "resolved config" replaces "frozen config"; Q324–Q326 backlog retagged, Target Factory
  and Inference rows added; Q329 "interactive" run mode and level names; Q330 no sandpit refit;
  Q333 the gap caveat; Q334 OD-12 to short-term (OD-08 stays short-term, given MLflow), statuses
  "designing" where a design doc exists; Q335–Q341 docs aligned.
- Restated, as the SDS asked: Q306, Q313, Q320, Q328, Q332. New follow-ups: Q342 (rows over the
  budget with no sampling declared), Q343 (a production retrain on moved months vs the
  data-definition hash and the EDA gate), Q344 (what "limited to Target Factory" covers), Q345 (how
  MLflow shapes the build before it is confirmed).
- Not in the plan yet: MLflow integration has no milestone in `worknotes/timeline_proposal.md`
  (OD-01, OD-08).
- Reviews of the applied answers: the ml-correctness-auditor (xhigh) and compat-guardian (high) ran
  on the whole diff. Fixed directly: `CLAUDE.md` §4.12 tightened to "outcomes only through the row's
  own label, one keep fraction for the whole train split, undone by the prior shift; anything else
  needs weights" (the defaulted Q314 wording admitted per-month fractions), and the auditor agent's
  paraphrase with it; `architecture.md` states that the Public API freezes from release 1.0;
  `config.md` says unknown config keys fail loud (a leftover `profile:` can't fall back silently).
  Turned into questions: production-retrain months and identities (Q343 sharpened), validation
  looks before the sign-off and on moved validation months (Q320 widened), the train–test gap under
  downsampling (Q328 (3)), `production.json` across major version 1 (Q345 sharpened), promoting
  without a retrain (Q346), moving the validation month after Feature Checks (Q347), the production
  retrain's check (Q348).
- Work split: the decision rows, `CLAUDE.md`, the roadmap, `docs/UPDATES.md` and the worknotes on the
  main thread; three subagents on the session model at high effort aligned the docs (glossary,
  architecture and context docs; the config, lifecycle and operations docs; the modelling docs)
  from one brief of the answers.
- Files: `docs/decisions.md`, `CLAUDE.md` (§2, §3, §4.10, §4.12, §4.13, §5, §7), `docs/roadmap.md`,
  `docs/UPDATES.md`, `docs/glossary.md`, `docs/architecture.md`, `docs/context/*`, `docs/components/*`,
  `conf/base/README.md`, `notebooks/README.md`, `tests/README.md`, `README.md`, the worknotes.
- Decisions / open decisions: D-006, D-014, D-021, D-023, D-024, D-031, D-033, D-036, D-037, D-040,
  D-043, D-049, D-051, D-052, D-072, D-088, D-091, D-106, D-111, D-117, D-125 extended; OD-02, OD-06,
  OD-08, OD-11, OD-12, OD-13, OD-17, OD-18, OD-25, OD-26, OD-27 updated.
- 2026-10-23, review of round 2 (ml-correctness-auditor, xhigh): wording fixed so the docs match
  the decisions: automated selection reads train-split statistics only, never EDA's all-client
  ranking (a separate ledger statistic); the prior shift's true rate from the unsampled train split
  (D-098); Training's count check on every client before the split; Feature Checks reads the
  validation month only to leave it out; `CLAUDE.md` §4.4 "label-using automated selection";
  pruning before calibration on the same folds; the bundle's audit-log slice includes a later
  validation-month entry. Folded in: the production check also compares per-month rows and
  positive events with the parent's EDA artifact, within tolerances, and names its months (D-052);
  the validation-month check covers every Feature Checks run (D-088). Corrected my own Q328 default:
  the gap's train side is the fitted rows, as AUC, since most rows of the unsampled split were never
  fitted under sampling (D-106). Moving the validation month after it was shown went into the
  Phase 3 gating question, per the Q320 answer. Asked: Q374 (register checks each model's
  plain-data copy).
- Still open: Q374; MLflow's availability (OD-08).

### 2026-10-22 — Decision log compacted; inconsistency sweep; LDS review list
- 2026-10-22: the SDS asked for a holistic pass now that the key designs are in place: compact
  `docs/decisions.md` by merging very similar rows, sweep every doc for inconsistencies between
  decisions, open decisions and descriptions, and list the twenty decisions the LDS should read first.
- The log went from 128 rows to 58, in two tables: high-impact (42 rows: scope, outputs, ML
  correctness, lifecycle, compatibility, responsibilities) and low-impact (16 rows: working rules,
  tooling, docs, dev-only data, defaults, naming). Every merge went into the lowest ID of its cluster;
  the surviving row's status names the IDs it absorbed. New rule in the file header and D-072 (g): a
  superseding decision replaces the original row in place (same ID), no superseded rows are kept.
  Four subagents remapped about 1,000 references in the current-state docs; this log and the `## Log`
  section of `docs/UPDATES.md` keep their old numbers as history, resolved through the mapping below.
- Old → new mapping (retired → surviving): D-002→D-001; D-005, D-080→D-020; D-008, D-059, D-095→D-033;
  D-010, D-018, D-074, D-127→D-024; D-015→D-039; D-019→D-013; D-025, D-063, D-067, D-070 (code
  layout)→D-003; D-027, D-045→D-044; D-042→D-012; D-048→D-030; D-053, D-062→D-083; D-055, D-075,
  D-115→D-021; D-056→D-041; D-057→D-011; D-058, D-086→D-043; D-060→D-050; D-061, D-066, D-118→D-029;
  D-065, D-068, D-069, D-070 (synthetic mechanics)→D-064; D-071, D-084, D-102, D-121, D-122→D-072;
  D-076, D-092→D-031; D-077, D-085, D-087→D-023; D-078, D-101, D-110→D-051; D-089, D-107, D-119→D-007;
  D-090→D-006; D-093→D-037; D-096, D-126→D-052; D-097, D-109, D-124→D-022; D-099→D-094; D-103, D-113,
  D-116→D-016; D-104→D-049; D-105→D-036; D-108→D-079; D-112→D-040; D-114→D-047; D-120→D-106;
  D-123→D-117. Lettered items were re-lettered: D-084 (a)–(g) are now D-072 (h), (i), (i), (j), (k),
  (h), (g); the old D-072 (b)–(e) are now (c)–(f).
- Four more subagents swept the docs for inconsistencies; the findings became the question list
  `worknotes/inconsistency_questions.md`. The LDS reading list is `worknotes/decisions_LDS_review.md`.
- Files: `docs/decisions.md` (rewritten), `CLAUDE.md` §8 (decision trigger), `.claude/skills/doc-sync/SKILL.md`,
  `worknotes/README.md` (two new files registered), `worknotes/decisions_LDS_review.md`,
  `worknotes/inconsistency_questions.md`, and D-number references across `docs/`, `worknotes/`,
  `notebooks/`, `synthetic/`, `tests/README.md` and `.claude/`.
- Decisions / open decisions: D-072 (g) extended (two tables; replace in place).
- Still open: the SDS's answers to the inconsistency questions; the LDS's pass over the review list.

### 2026-10-22 — Working rules: sync windows and the decision log
- 2026-10-22: the SDS changed two working rules, built in without rework of existing content.
  (1) The sync page's "since the last sync" becomes "last 2 days"; it and "last 7 days" are each at
  most one page, important changes and updates only, no info dump; the 7-day recap covers days
  3–7. (2) The decision log holds every active decision in as few rows as reasonable: new
  information heavily adjacent to a set decision extends its row; a superseding decision replaces
  it with a new row, the old one marked superseded.
- Applied to itself: both rules extend D-084 as (f)–(g) rather than adding a row.
- Files: `worknotes/README.md` (rules, template), `docs/decisions.md` (header, D-084),
  `CLAUDE.md` §8 (decision trigger), `.claude/skills/doc-sync/SKILL.md`, `.claude/commands/brief.md`.
- Still open: `sync.md` is reshaped at its next refresh; existing decision rows are not merged
  (no rework asked).

### 2026-10-22 — The planning thread closed
- 2026-10-22, later: the SDS corrected the reading of Q218: the plan is a working assumption, not
  agreed; the LDS still reviews it and stakeholder buy-in comes next week. The plan (dates, M2's
  stages, depth per component) moved back into `worknotes/timeline_proposal.md`; the roadmap keeps
  a short milestone table marked as the working assumption; OD-01 restored; D-124 now soft.
- 2026-10-22, after the daily LDS sync: the last answers (Q223, Q241 (a)–(g), Q276, Q281, Q292)
  and "barring any change in the timelines, all is answered", so Q218 counts as accepted.
- Decisions: D-124 (the plan agreed; milestone IDs kept: M2 = round 1a in stages M2.1–M2.4, M3 =
  round 1b, M4 = round 2, M5a/M5b = the run-throughs; OD-01 closed); D-125 (the decision audit log;
  OD-10 closed; amends D-043 and D-088); D-126 (retraining keeps clients and window; all-clients
  and extended-window refits to the Phase 3 wishlist; narrows D-052, D-096); D-127 (Public API,
  option A); D-128 (product and activity parsed from `<product>_<activity>`, as in the crunch's
  `fx_activation`).
- Q241's concern (verbosity, entries → code, which decisions are allowed, how that list is kept)
  is answered in `config.md`: a closed list of operations in one dict, a maintained list of
  settings a `set` may touch with a test against the schema, replay rules, verbosity controls,
  the resolved config saved as one file, and a registered bundle that carries its run's slice as
  one file.
- Roadmap: the agreed blocks, M2's stages and the depth per component moved in from the timeline
  note; backlog retagged (most former M3 depth is now M4); two to-dos added (the learn sessions;
  the first change request's first-time steps); OD-01 and OD-10 deleted; the CDS topic "Phase 2
  plan" is now due.
- Worknotes: `holistic_review.md` deleted (its "do before M2.1" items were all settled or held
  elsewhere); the questions file closed; `timeline_proposal.md` trimmed to reasoning, work
  streams, assumptions and risks; the sync page's last sync set to 10-22 and the bullets it
  covered removed.
- Delegated: the audit-log design into `config.md`, plus the ledger, architecture, lifecycle,
  training, dataset, inference, run modes and notebooks README, to an Opus agent at high effort.
  Its own choices, read and kept on the main thread: `include` reverses only a person's exclude;
  the decision, metric and baselines are never loggable (§4.3); evidence cites train and test only
  (§4.4); the registered slice includes the run's sign-off. New open point in `config.md`: does a
  person entry citing a superseded rule entry block register?

### 2026-10-22 — Fourth round of answers, the plan adjusted, questions round 5
- 2026-10-22: the SDS answered Q260, Q262, Q267, Q268 (asked back), Q269, Q272, Q275, Q281 (asked
  back), Q284, Q285, Q290, Q292 (didn't understand), Q296, Q301 and all of section B, and gave
  timeline notes: stages may differ in length, the year-end change freeze, the week of 11-30
  mostly lost, a year-end slowdown rather than a stop.
- Decisions D-111–D-122 (registry records, soft; monitoring frame vs content; where scores are
  written; a newer version within an image's year, soft; the first change request is release 1.0,
  framework only; reserved later-task columns; sampling; lineage; artifact inventory; FLAML client
  groups; Phase 3 wishlist; bracket summaries in questions). Status notes on D-040, D-055, D-106.
- Numbering clash: a parallel session had added its own D-110 (pickle scope) after D-109; this
  session's rows first went in as a second D-110–D-121 and were shifted to D-111–D-122 everywhere
  (decisions, roadmap, timeline, questions, `CLAUDE.md`, memory, eleven owner docs). The other
  session's D-110 references were left as they were.
- Answers given back in chat: month stratification adds nothing when months are large, similar
  slices and one keep fraction is used (the SDS was right); downsampling low-value rows can
  calibrate back if each kept row carries 1 / its keep probability, and local case-control
  sampling (Fithian and Hastie, 2014) is the closest known method; this goes to the literature
  round. Public API: several active versions are no problem while a use case stays pinned; the
  list matters when it moves up.
- Questions round 5: section B (facts) deleted (to-dos already, or answered); Q241 reframed (five
  points, verbose table, replay table and resolved YAML, seven sub-questions with alternatives);
  Q276 moved to section A as refit options plus a checks table; Q281 and Q292 restated with
  options. Open: Q218, Q223, Q241, Q276, Q281, Q292.
- Timeline: stages S1 6, S2 4, S3 6, S4 4 days; round 1b 11-23 – 12-08 (about 8 days); run-through
  1 12-09 – 12-18 (into the internal repo, a demo, no production); slowdown 12-21 – 01-01 for fixes
  and the integration designs; round 2 01-04 – 02-05; release 1.0 by 02-19 as the first change
  request.
- `CLAUDE.md` §9: the bracket rule (D-122); the doc map lists the Phase 3 wishlist. Roadmap: OD-07
  closed, OD-04 and OD-08 narrowed, OD-17 updated, milestone dates, the wishlist.
- Delegated: owner docs (dataset, training, inference, lifecycle, monitoring, feature checks,
  Target Factory, run modes, environment, project) to an Opus agent at high effort; read on the
  main thread, which also fixed the monitoring wording in `architecture.md` and `UPDATES.md`.
- Later the same day: "keep sampling simple for Phase 2; low-value downsampling and anything else
  advanced to Phase 3" became D-123. Phase 2 keeps uniform negative downsampling, a random sample
  of clients, or no sampling, all without sample weights. Option 3 with its weight-aware
  statistics, low-value downsampling, the smart-downsampling research and the comparison against
  the oracle moved to the Phase 3 wishlist. OD-17 narrowed to the window ablation; the literature
  round and its reminder dropped; spike 1 no longer needs sample weights. Edited: decisions,
  roadmap, dataset, training, environment, glossary, test harness, timeline, UPDATES, memory.
- Open: the six questions; spike 1 decides FLAML's group split or the holdout fallback.

### 2026-10-21 — Third round of answers, the plan reshaped, synthetic data accepted
- 2026-10-21, evening: the SDS passed on the LDS's review of the synthetic data and answers to
  Q237, Q238, Q241, Q254, Q263, Q286, Q291, Q293, Q295, plus planning notes.
- Decisions D-103–D-109: the master layer is where the framework's scores end, consumable tables
  are others' (D-103); scores are compared across products, so calibration is a release
  requirement (D-104); reports self-contained, size not optimised, spike 4 dropped (D-105); the
  train/test client split is Phase 2's only requirement for validation inside training, an own CV
  loop a later wishlist item (D-106); compatibility is about outputs, `CLAUDE.md` §2 reworded
  (D-107); upstream data facts aren't the framework's (D-108); the plan is milestones with dates
  per stage, December a pre-release with two purposes, scenario A (D-109).
- Plan: `worknotes/timeline_proposal.md` rewritten as one plan table (five stages, depth at the
  pre-release and release 1.0, nice to haves, dates). Answer to the SDS's "2.5 rounds" question:
  yes, with the skeleton first inside round 1, exit-point shapes close to final by 12-04, and a
  second run-through mirrored before release 1.0. Round 1 10-26 – 12-04, run-through 1 and the
  pre-release 12-07 – 12-18, round 2 01-04 – 02-05, release 1.0 by 02-19.
- Q241: a worked example of the audit log in use (16 entries from Feature Checks to promote, the
  write call and CLI command, the stored entry, replay, the cost); storage moves to one file per
  entry, because HDFS append may be off in the bank (unverified).
- Verified in FLAML 2.7.0 (`flaml/automl/task/generic_task.py`, `decide_split_type`): for
  classification, passing `groups` turns the automatic split into a group split; for regression it
  stays by rows unless `split_type="group"` is passed. Basis of Q296.
- Found: D-106 relaxes `CLAUDE.md` §4.11 ("any CV inside train is grouped by client") unless FLAML
  gets the groups (Q296). D-103's one master table may clash with D-034, entities never merged
  (Q301, raised by the propagation agent).
- New: Q296, Q300 (first change request), Q301 (scores table per entity), Q286b (left from Q286),
  OD-28 (rank score). Q297–Q299 are `pickle_summary.md`'s, from a parallel session.
- Delegated: the owner-doc propagation (inference, training, evaluation, reporting, dataset,
  lifecycle, test_harness, environment, architecture) to an Opus agent at high effort; read and
  rewrapped on the main thread.
- Files: `docs/decisions.md`, `docs/roadmap.md` (M1 accepted, milestone mapping, OD-01, OD-06,
  OD-10, OD-17, OD-18 narrowed, OD-28), `docs/glossary.md` (master layer, exit point),
  `CLAUDE.md` §2, the nine owner docs above, `worknotes/holistic_review_questions.md` (round 4),
  `worknotes/timeline_proposal.md`, `worknotes/sync.md`.
- Open: Q218, Q223, Q241, Q296, Q300, Q301 and the rest of round 4.

### 2026-10-21 — MLflow teaching summary and the no-pickle difficulties
- 2026-10-21: the SDS asked for an MLflow explanation (the CDS chose MLflow) and for the
  difficulties of a no-pickle bundle; both saved in `worknotes/mlflow_summary.md`. Checked on the
  pinned versions: LightGBM text and XGBoost JSON round-trip identically; CatBoost JSON does not
  (up to 1.3e-15, drifts on re-save), CatBoost `.cbm` does. FLAML 2.7.0 logs to MLflow by itself
  once a run is open (`mlflow_logging=False` needed).
- 2026-10-21, later: the SDS asked for a compact summary of every difficulty of a no-pickle,
  JSON-only bundle, not just MLflow's: model families, our own code around the booster, JSON
  itself, tests and lint, MLflow, habits. Newly verified: in ruff 0.17, `S301` misses
  `joblib.load` and `S403` is preview-only, so a `banned-api` list (`TID251`) is needed.
  `worknotes/mlflow_summary.md` is no longer in the repo.
- 2026-10-21, rework: the SDS found the summary too long and not focused on disadvantages, and
  set the scope: no pickle only for what is promoted from the sandpit to production; HDFS saves
  in the sandpit may pickle (D-110, superseding D-101's "local runs included"). The summary was
  rewritten as six disadvantages; the lint and JSON-detail points were dropped, since the
  sandpit may now pickle.
- Why: the SDS had not used MLflow; the pickle result affects D-078 and the CatBoost plan.
- Files: `worknotes/mlflow_summary.md` (new, since removed); `worknotes/pickle_summary.md` (new,
  rewritten); `docs/decisions.md` (D-110; status notes on D-078, D-101);
  `docs/components/inference.md`; `.claude/skills/bank-parity-check/SKILL.md`.
- Open: Q297–Q299 (the promote gate; strict JSON vs plain data, first raised as Q296, a number
  D-106 has since reused; security sign-off on the formats); the CDS's MLflow decision as a D-row
  (OD-08, OD-13).

### 2026-10-21 — `delegation` skill (D-071 as a procedure)
- 2026-10-21, after the SDS's subscription upgrade: a `delegation` skill so parallel subagent
  work and model routing happen by procedure, not by wish. It covers the split (disjoint files,
  one deliverable each), the routing table (haiku for searches, sonnet for implementation,
  tests, research and doc edits; the four review agents and all design or §4 judgement stay on
  the session model), a seven-part brief template with a capped report format, spawning rules
  (one message, background, one memory-heavy job at a time), integration and verification, and
  the anti-patterns.
- Why: with usage limits relaxed, the bottleneck is whether Claude actually delegates and briefs
  well; a skill with a trigger-rich description is the only mechanism short of CLAUDE.md that
  loads on demand. CLAUDE.md §1 now points at it; worker agent files were deliberately not added
  (per-call `model` on the Agent tool does the routing without new files).
- Files: `.claude/skills/delegation/SKILL.md` (new); `CLAUDE.md` §1 and §10;
  `docs/guides/skills_and_agents.md`; `docs/guides/claude_code_workflow.md`.
- Decisions / open decisions: D-071 (unchanged).
- 2026-10-21, routing revised after the SDS's review: research is split from design (research
  gathers evidence, design decides and never leaves the main thread) and into three tiers
  (locate on haiku; fact checks on sonnet high with `file:line` quotes, or a strong model when
  tracing several code paths; best-practice research on a strong model, xhigh for a major
  step). Docs: sonnet only propagates settled text; component doc content goes to a strong
  model; the sync page, log, decisions, OD rows, UPDATES and review guides stay on the main
  thread, and every doc diff is read in full before the SDS sees it. ML-critical code and §4 or
  §2 tests go to a strong model; ordinary implementation and tests to sonnet high. Every Agent
  call passes `effort`, because the fallback when none is set isn't documented and the 5.5
  models default to `medium`; reviewers run at high, `ml-correctness-auditor` at xhigh.
- Still open: trigger test in a fresh session; check after the first real build which delegated
  pieces needed rework, and adjust the tiers; dedicated worker agents and a nested orchestrator
  agent if the main thread still does the pieces itself.

### 2026-10-21 — The SDS's second answers to the holistic review (D-098–D-102; questions round 3)
- The SDS answered part of round 2 and asked that unanswered questions never be deleted, and
  that the answer mapping go in the chat reply rather than a section of the questions file.
- Decided: D-098 (test metrics per month first; denominators), D-099 (trial budget plus seeds,
  time recorded), D-100 (M2 engineering shape: Protocol-ready plain-function model interface,
  compatibility table as a dict, Spark session fails loud, test runtimes with reminders, oracle
  tolerance), D-101 (pickle only matters for saved and moved artifacts), D-102 (doc upkeep:
  three-level template on rebuild; one hygiene pass). D-078 status noted.
- Routed without a decision row: Q233 (start from the retail platform team's current output
  format as a guide; other entities and domains may differ) → OD-18 leaning; the screenshot the
  SDS mentioned didn't reach the chat, so Q233 stays open for it. Q234 deleted (the SDS tests
  plotly in the bank later). Q257 → a to-do in `evaluation.md` (OD-12). Q266 → roadmap backlog
  (integration seams designed when code moves toward the bank). Q273 declined (local counts can
  be deleted anyway). Q287 accepted (sampling literature round after M2.1) → OD-17.
- Reminders the SDS asked for, kept in Claude's memory (`project_reminders.md`) and raised at
  session start: the five spikes before M2.3 (the SDS runs them), the full test suite after 7
  days without a run (last: 2026-10-19), the sampling literature round after M2.1.
- Questions round 3: section A for both (Q217, Q218, Q223, Q260, Q262, Q263; detailed proposals
  Q241 on the config + audit log as the SDS frames it, Q254 on client-grouped validation inside
  training, Q286 on how long old versions keep working); B facts (Q232, Q233, Q235, Q237, Q238);
  C for the SDS (Q267, Q290 new on "PSB"; elaborated Q268 with what "offset" means, Q269 with
  Claude's answer on recency weighting, Q272, Q275 with the three sampling options, Q276 on
  refits, Q281, Q284, Q285).
- Doc-hygiene pass (Q288) delegated to a separate agent after Claude's own edits, so the two
  never edited the same file at once. All 15 items fixed: two-paths wording marked Phase 3 across
  six docs; settled-OD references pointed at their decisions (status columns only); M2 monitoring
  a stub; human-decision wording hedged with OD-10; the three sign-offs kept apart (feature,
  promotion, CR) with a new glossary entry; CLI list and role-subfolder rule in `architecture.md`;
  Phase 3 list and theme wording; stale paths; template status values; 13 glossary entries; the
  synthetic "profile" clash noted. Verified by Claude: decision texts unchanged except D-065's
  path, every table's cell counts consistent, no live reference to a closed OD left. Five
  leftovers the agent reported were then fixed by Claude: the learning-curve check now scores
  test (D-083), the UPDATES training row, `architecture.md`'s OD-27 line cites D-096, the theme
  wording in both environment docs, and the `doc-sync` skill's "local sync notes".
- Files: `docs/{decisions,roadmap,glossary}.md`;
  `docs/components/{training,evaluation,dataset,inference,environment}.md`; `tests/README.md`;
  `worknotes/{holistic_review,holistic_review_questions,timeline_proposal,sync,log}.md`; plus the
  hygiene pass's files.
- Later the same day, Q233: the SDS shared a screenshot of the retail platform team's expected
  propensity output (customer id, product, activity, score 0–1, source, refresh date). Recorded in
  `inference.md` requirement 4 and OD-18, with the bank-specific example values (the source code,
  the id prefix) left out of the repo. Q233 closed; new questions Q291–Q295: two layers (the
  framework's traceable scores table plus a per-consumer column mapping), product and activity as
  config fields, writing only one's own partitions of the shared table, column meanings, and
  whether scores must be comparable across products (calibrated probabilities). Q267 restated.
- Decisions / open decisions: D-098–D-102; OD-10, OD-12, OD-17, OD-18 updated.
- Still open: questions round 3.

### 2026-10-20 — The SDS's answers to the holistic review (D-082–D-097; questions round 2)
- The SDS answered Q217–Q265 the same day, with notes on the review itself. Recorded:
  - review corrections: "every stage writes an HTML report" was Claude's drift; the intent is EDA
    and Feature Checks as a product within the product (a data-analysis report); the speed /
    automation wording; `v + w ≤` the last month as a config requirement; what to do about
    correlated rows (count events, change nothing in the fit); leavers are null only inside the
    target window; D-062 vs OD-22 settled on train and test only; the sync-page rule;
  - decisions D-082–D-097 (`docs/decisions.md`), with status notes on D-023, D-052, D-053
    (superseded), D-062 (amended), D-076, D-077, D-080;
  - `CLAUDE.md`: the speed claim, the outputs bullet, §4.4 reworded (tuning choices may weigh
    test; validation never). Flagged to the SDS as the one invariant change;
  - OD-05, OD-09, OD-22, OD-24 deleted; OD-01, OD-10 (restated proposal), OD-11 (not urgent),
    OD-17 (sampling research), OD-25 (narrowed), OD-27 (shape settled) updated; Chief DS topics:
    the plan with dates, YAML as an information item;
  - owner docs: `architecture.md` (reports, YAML, shared-table rule, identities, sweeps),
    `project.md` (speed, goal 1, automation row, definition of done at release 1.0, extension
    code), `glossary.md` (profile, automation level, positive events, sign-off, sweep, register,
    run id, model hash, recipe), `config.md` (YAML, levels, `v + w` validation, the identities
    section with a worked example, open questions), `dataset.md`, `target_factory.md`,
    `feature_checks.md`, `feature_ledger.md`, `training.md`, `evaluation.md`, `reporting.md`,
    `run_modes.md`, `llm_assist.md`, `lifecycle.md`, `context/lessons.md` (SE on events),
    `context/environment.md` (24 months; 100–300 candidates from thousands);
  - `worknotes/README.md`: review items tagged needs decision / for information, cap of five,
    the LDS's review scope; the sync page drained to the planning set and the synthetic data;
  - `docs/guides/setup_windows_wsl2.md`: the machine-switch checklist now lists every laptop-level
    Claude item (the memory folder, user settings, the synced user-level skill, the plugin list);
    the answer to the SDS's Q229.
- The questions file is now round 2: section A (still open: Q217, Q218, Q223, Q232–Q235, Q237
  part, Q238, Q257, Q260, Q262, Q263), section B (restated: spikes Q230, the audit log Q241, the
  grouped-CV fallback Q254), section C (new Q266–Q289 from the review's open-ended pointers,
  especially §4–§7), section D (where each answer went).
- Not done on purpose: the doc-hygiene pass (Q288) and the sampling literature round (Q287) wait
  for the answers; nothing committed.
- Files: `CLAUDE.md`; `docs/{decisions,roadmap,UPDATES,architecture,glossary}.md`;
  `docs/context/{project,lessons,environment}.md`; `docs/guides/setup_windows_wsl2.md`;
  `docs/components/{config,dataset,target_factory,feature_checks,feature_ledger,training,evaluation,reporting,run_modes,llm_assist,lifecycle}.md`;
  `worknotes/{README,sync,log,holistic_review,holistic_review_questions,timeline_proposal}.md`.
- Decisions / open decisions: D-082–D-097; OD-05, OD-09, OD-22, OD-24 deleted; OD-01, OD-10,
  OD-11, OD-17, OD-25, OD-27 updated.
- Still open: round 2 of the questions (sections A–C); the planning session with the LDS.

### 2026-10-20 — Holistic review of the design and plan; the planning-session set
- The SDS asked for a critical review of everything designed so far, before the planning session
  with the LDS that will attach deadlines to the milestones: risks, weaknesses, suggestions and
  questions for both of them, in two worknotes files, plus a small timeline suggestion.
- Done, as three files in `worknotes/`:
  - `holistic_review.md` (deleted 2026-10-22): verdict (proceed with changes), what to keep, ten
    ranked risks, scope and goals, stage-by-stage findings, forward compatibility, process, a
    doc-hygiene list, and a "do before M2.1" list;
  - `holistic_review_questions.md`: Q217–Q265 in nine groups (target and scope; process; facts
    from outside the team; config spine; dataset to ledger; training and evaluation; lifecycle
    to monitoring; reporting, notebooks, tests; the CDS), each with a default and an owner;
  - `timeline_proposal.md`: scenario A (December = pre-release of the skeleton plus one deepening
    round inside the bank; release 1.0 mid-February 2027 with the integrations) against
    scenario B (release 1.0 in December, not recommended); dated milestones M2.1–M2.4, M3,
    M5-lite, M4; spikes and learn sessions beside the critical path; the OD-01 depth table in
    three columns; review cadence; risks to the dates.
- How: every doc in `docs/`, the decision log to D-081 and the worknotes read on the main thread;
  three subagents in parallel (D-071): an ML-correctness audit of the design, a
  forward-compatibility audit, and a cross-doc consistency sweep. Their findings were integrated
  and the ones the review leans on were checked in the pinned sources:
  - FLAML 2.7.0 `DataTransformer` drops constant columns and fills `__NAN__`
    (`flaml/automl/data.py` 313–324) and the estimator wrapper recodes categoricals
    (`model.py` 1475–1486); `AutoML.predict` re-applies both. No out-of-fold prediction API. `fit`
    accepts `sample_weight`, `groups` and `split_type` (honouring the weights in grouped CV is
    unverified);
  - `test_harness.md` promises a time-alignment check for the shifted column that
    `feature_checks.md` never lists.
- Main findings (detail in the review): December means two things; review bandwidth is the
  binding constraint; no rule for old versions reading rows newer versions wrote; identities and
  hashes undefined; the model bundle under FLAML loses a preprocessing layer; the calibration
  chain unspecified; the refit registers an unevaluated model; "positives" should mean events in
  every support rule; leavers make the rates survivor-conditioned; the post-training sign-off sees
  validation results; D-062 and OD-22 disagree; regression hooks missing; about 25 doc
  inconsistencies and 15 glossary gaps.
- Not done on purpose: the doc-hygiene fixes (§8 of the review) and the conversion of questions
  into OD rows; both wait for the SDS's answers so the docs change once.
- Files: `worknotes/{holistic_review,holistic_review_questions,timeline_proposal}.md` (new);
  `worknotes/{README,sync,log}.md`; `docs/UPDATES.md` (log line).
- Decisions / open decisions: none yet; Q217–Q265 feed D rows and OD-01, OD-10, OD-17, OD-18,
  OD-24, OD-25 and the roadmap dates.
- Still open: the planning session; the spike week; the three external sessions.

### 2026-10-20 — CDS outcomes: the SDS's answers to Q209–Q216 (D-080, D-081)
- Q209 (default) → D-080: binary and regression end to end, FLAML only; the predefined path + Optuna
  and its trade-off chart move to Phase 3. OD-15 deleted; M1 still needs regression's per-task spec
  (D-060).
- Q210 (default) → D-081 (soft): the proposed task order; regulated models only when a use case
  asks. OD-21 deleted.
- Q211: "documentation written by an LLM" means the framework's own repo docs (a future Claude
  prompt), not a Phase 2 work stream. D-075 (c) removed: no LLM in the first release; the model
  documentation generator is back in the Phase 3 backlog; `llm_assist.md`, `reporting.md`, the
  adapter docs, architecture, glossary, project and roadmap reverted to match.
- Q212 (default): sign-off placement as in D-076 (end of Feature Checks in manual runs, after
  training in hands-off runs, always before register).
- Q213 (default): any non-executable plain-data format counts, JSON preferred; no pickle anywhere
  (D-078 status).
- Q214 (default): both integrations thin, one worked example each; December target kept, revisited
  after the work streams (D-075).
- Q215 (default): the compatibility window stays noted in OD-04, decided at M5. The SDS expects the
  shared tables to be less of a problem than Claude suggested.
- Q216 (default): the housekeeping block stays a requirement in `config.md`.
- Before that, same day: a fresh-context review of the integration found 11 must-fix and 13
  consider items. Fixed: data observability integration is ours (only tooling and dashboards are
  the platform team's), which feature list is signed off, thresholds the same at every level, the
  config hash excluding the housekeeping block, stale environment and workflow notes, several
  sources per entity in the config from v1 (feature store), inference and the in-memory pickling
  of broadcast models, the no-pickle rule mirrored in the auditor, tests README and bank-parity
  skill.
- Files: as in the entry below, plus `docs/components/{eda,inference,test_harness}.md`,
  `docs/context/environment.md`, `docs/guides/claude_code_workflow.md`, `conf/local/README.md`,
  `notebooks/README.md`, `tests/README.md`, `synthetic/REVIEW.md`,
  `.claude/agents/ml-correctness-auditor.md`, `.claude/skills/bank-parity-check/SKILL.md`.
- Decisions / open decisions: D-080, D-081; D-075, D-076, D-078 statuses; OD-15, OD-21 deleted;
  OD-01, OD-04, OD-20, OD-22 updated.
- Still open: nothing from this round.

### 2026-10-20 — CDS design meeting outcomes integrated (D-073–D-079, OD-24–OD-27)
- The SDS's notes from the two CDS sessions (2026-10-15) were routed to their owner docs, and the
  meeting material (`worknotes/chief_ds_meeting/`) was deleted.
- Already settled in session 1, now recorded: the library is the consumption model (D-024
  confirmed); the package ships in the base image through Nexus, and images are supported for a
  year (D-074; OD-04 narrowed to the release mechanics); an LLM writes the model documentation in
  the current documentation structure (D-075).
- Where each note went:
  - the main message (the CDS trusts us; downstream effects are worked out when we get there)
    → D-073. Open decisions now start with an area tag and are owned by SDS + LDS instead of "Chief
    DS meeting"; the meeting table became "Chief DS topics"; the blank-slate lifecycle session is
    dropped;
  - config: Python files preferred (research) → OD-24. "The config never changes; downstream
    decisions go to an audit log", with the SDS's pathway idea → OD-10 widened, with a draft
    inventory of decision points in `config.md`. Housekeeping block → `config.md` requirement 2;
  - first release: the feature store → D-075, OD-26, a learning work stream in the backlog; the
    data observability framework → D-075, OD-13; LLM → D-075 (documentation now, the modelling
    loop in Phase 3), and `llm_assist.md` is rewritten around the two uses;
  - human in the loop → D-076, `CLAUDE.md` §4.13, feature checks and the ledger;
  - model tiers → D-077 (soft) and OD-25, named "automation levels" because "tier" is the
    lifecycle's word (local → registered → production);
  - JSON rather than pickle → D-078 (amends D-051); per-family research in `training.md`;
  - retraining in production → OD-27;
  - f1 and f4 → D-079 (the platform / MLOps team), and OD-23's leaning;
  - hints: a1 and a3 → OD-21 and OD-15, now owned by SDS + LDS; b1 → OD-02's leaning (a hybrid:
    entity × domain repos, use cases branching off), moved to medium-term because it doesn't
    block M2; no blank-slate lifecycle → D-073.
  - Not in the notes: d2 (OD-06 stays open, now ours), d5 (stage structure: D-028 marked decided
    under D-073), f2 (OD-14), f3 (a confirm item: D-040 marked confirmed).
- Critique (Claude):
  - **Python configs:** a Python config runs code when it is loaded, the same class of risk as the
    pickle the CDS bans. Migrations (`dict → dict`) and hashing also assume plain data. Whatever
    the authoring format, the frozen config must stay plain data.
  - **Audit log:** it solves OD-10's flag case, since a `keep` no longer edits the config.
    Reproducibility then means "frozen config + the decisions used", and the run's hash must cover
    both. Keep it an append-only table, not a graph engine.
  - **Autonomous vs the feature sign-off:** by D-076, "fully autonomous" still stops at the human
    sign-off before register. The two directions fit only if "autonomous" means autonomous up to
    registration.
  - **Retraining in production:** the model that scores is no longer the one evaluated, as with a
    refit (D-052), so production needs a check before it scores.
  - **No pickle:** this limits FLAML's estimator list. Scikit-learn's forests have no non-pickle
    format without a new dependency or our own exporter (unverified for the pinned versions).
  - **Scope:** two integrations with systems we don't know yet, plus a documentation writer, on a
    December target. Leaning: thin integrations; revisit the target after the work streams.
- Questions to the SDS: Q209–Q216, answered in the entry above.
- Files: `CLAUDE.md`; `docs/{decisions,roadmap,UPDATES,README,glossary,architecture}.md`;
  `docs/context/project.md`;
  `docs/components/{config,feature_checks,feature_ledger,training,lifecycle,monitoring,reporting,target_factory,environment,run_modes,llm_assist}.md`;
  `worknotes/{README,sync,log}.md`; `worknotes/chief_ds_meeting/` deleted.
- Decisions / open decisions: D-073–D-079. Status notes on D-017, D-021, D-023, D-024, D-028,
  D-031, D-033, D-040, D-043, D-051 and D-055. OD-24–OD-27 opened; OD-02, OD-04, OD-09, OD-10,
  OD-13, OD-15, OD-19–OD-21 and OD-23 updated.
- Still open: see the entry above.

### 2026-10-19 — Synthetic data notebook: a visual tour
- The SDS chose 5 of 9 proposed charts:
  - the leakage screen preview (2);
  - the gains curve of perfect knowledge (4);
  - heavy tails on log–log axes (5);
  - collinear clusters (7);
  - the regression fan (9).

  They asked for the notebook to become a visual entry, with the checks less prominent.
- Done:
  - sections 1–8 follow Level 2 of the spec: the book, holdings, amounts, time, the mart, traps,
    the ceiling, client stories;
  - the appendix A1–A7 holds every check table and the tables behind the charts;
  - the first cell prints the check status (1,263 of 1,263 rows pass);
  - population and spend-mix tables became charts; a joiner's rollups show how windows fill;
  - the notebook loads the 20% sample once, instead of six partial reads, and runs in about 20 s.
- Results:
  - **Leakage screen:** the oracle's AUC is 0.842 for card acquisition (w = 3); trap columns 1.00,
    0.97 and 0.87; the best real column (income) 0.68. For personal-loan opening next month, the
    oracle's AUC is 0.763; the shifted column scores 0.94 and applications 0.90.
  - **Gains:** in the top 10% of non-holders, the oracle catches 54% of card acquirers, income
    25%, a salary-transfer-and-income rule 16%, and the leak 89%.
  - **Regression:** realised spend falls inside the oracle's 10–90% band in 67–95% of the months,
    per client.
- Found: the first tail chart (per profile, 20% sample) showed slopes of −1.2 to −2.0 against the
  spec's −2. Per subsegment on every client, the Hill estimate is ≈ 2.0 and the slope beyond 3× the
  median is −1.8 to −1.95. Mixing subsegments' medians within a profile flattens the visible range,
  so the chart is now per subsegment on the full month. Traditional wealth has too few holders per
  subsegment for a clean tail and was dropped from the chart.
- Code review of the notebook found 5 blocking issues and 7 suggestions, all fixed:
  - the leakage bars were ordered by kind, not strength;
  - each screen showed the other target's traps below the line;
  - two full copies of the mart;
  - limit-tier shares came from declared-income card holders only;
  - smaller items: chart wording against the spec, the regression rows cut short, axis labels.

### 2026-10-19 — Working rules and doc structure (D-072)
- The SDS's feedback for the whole project:
  - a plan for building a section has major steps (the SDS reviews) made of minor steps (Claude's
    review skills and subagents run);
  - commits only when the SDS asks, even locally, always with a message;
  - the open decisions split into short-term and medium-term tables;
  - no flowcharts: they don't work on smaller screens;
  - docs in three depth levels, following the 80-20 rule. Level 1 is ≈ 4% of the doc and gives
    ≈ 64% of the information. Level 2 covers the main relationships, e.g. who is likely to pick up
    which product, and with Level 1 is ≈ 20% of the doc for ≈ 80%. Level 3 holds every detail.
- Done:
  - `test_harness.md` restructured into Level 1 (summary, 3.2% of the words), Level 2 (how it fits
    together; 18.6% with Level 1) and Level 3 (the details, in Level 2's order). Level 2 is new:
    who the clients are, a table of who holds and who picks up each product, how amounts follow,
    the mart, traps and the oracle, the month loop and the code in brief, the checks. The month
    flowchart became a numbered list and the code-map tree nested bullets;
  - the component template, the new-component skill, `CLAUDE.md` §1 workflow, §8 (doc map,
    style, open-decision trigger) and §9 (git), the workflow guide and the worknotes README;
  - the other diagrams (architecture: framework vs use case, the time model, the package layout;
    lifecycle tiers; the dataset time model) replaced with lists. Architecture's time model now
    links to dataset's, its owner;
  - open decisions split: short-term OD-01, 02, 05–11, 13, 15, 18, 23; medium-term OD-04, 12, 14,
    17, 19–22. CDS-agenda rows with a later build need (release path, inventory, long-term feature
    sources, eventual task scope) sit in medium-term.
- Found: `worknotes/chief_ds_meeting/questions.md` lists OD-04 (Nexus distribution) as settled in
  session 1, but its roadmap row is still open. The CDS meeting outcomes still need converting into
  D-rows.
- Nothing committed (new rule).

### 2026-10-19 — Synthetic data (M1): the SDS's review round 1, approved
- 2026-10-19, approved: the SDS gave their OK on the round. `synthetic/REVIEW.md` now describes
  only the current state (what it is, how to regenerate, the review order, targets, settled
  choices, limitations). The LDS summary is on the sync page's review list. M1's generator is done;
  OD-15 (second task type) is still open, so the handover `handovers/synthetic_build.md` stays
  until M1 closes. Committed and pushed as "Synthetic Data build".
- The SDS reviewed the finished generator (notebook, spec, code) and asked for:
  - the code in role subfolders: rules as plain data, functions, checks;
  - merged tied modules, measuring code amount against effect;
  - a smaller `truth.json`, a top-down spec with a function summary (and the same for every
    future component doc);
  - higher exit rates with smaller gaps between profiles;
  - notebook fixes: tables saying what their values are, an income chart, proof that `<NA>` is a
    null, single-column AUCs for activation targets;
  - an explanation of "unplanted" traps.

  Open points: exits stay random; the moderate leak and the shifted column are built; dirty
  rollups are stated, not built; loan rates and login levels accepted.
- Debatable cuts went to the SDS with numbers. The regression oracle (57% of generation time) is
  kept; the relevance rankings (half of `truth.json`) and the `separation` knob (no effect at 1.0)
  are cut; traps in real columns keep their names, labelled `trap_column` false.
- Done:
  - 46 modules → 32 in `spec/`, `mechanisms/`, `truth/`, `checks/`; mart and oracle bit-identical
    before the behaviour changes;
  - `truth.json` 234 → 55 KB (only what can't be recomputed; sizing once per target); 10 check
    families → 8;
  - exits 0.7 / 0.8 / 0.9 / 1.1% a month, with traditional wealth at 42 adoptions a month to keep
    its holding length;
  - the moderate leak (AUC 0.877 vs oracle 0.842) and the shifted personal-loan balance (0.945 vs
    0.766);
  - version 0.4.0, canonical regenerated (337 s, after the review fixes below), all 1,263 check
    rows pass;
  - the notebook rebuilt: labelled tables, exits from the mart, holdings by income with
    thresholds, card limit vs income, null proof, single-column AUCs;
  - `test_harness.md` rewritten top-down with a code map; component template and `CLAUDE.md` §1
    rule 5 updated (D-070).
- Found on the way: a notebook exit-rate table read high for small profiles. Months without
  leavers dropped out of the mean, and the 20% sample ran high; the table now counts zero months
  and reads every client.
- Reviews of the round. Code review: no blocker; fixed the doc claims, merge leftovers and
  duplicated rows. ML-correctness audit: safe, with three should-fix items:
  - **The starting book's tenure** (a Beta share of adult life) wasn't the turnover's steady
    state, so with the higher exits the shares of products built up over tenure drifted down
    (traditional wealth, Private: 0.60 → 0.49 by month 24; one check passed by 0.001). A first fix
    (tenure truncated to adult life) still let tenure grow and Mass shares rise. Now tenure is
    exponential at the entry rate and clients join younger than the book's mean age by its mean
    tenure: age and tenure are jointly stationary, with 9 parameters fewer. Shares are checked at
    the last month too.
  - **Leaks beat the oracle on their own window only**; documented.
  - **The sizing is now recomputed by the checks.**
- The SDS asked for parallel work with subagents as much as possible from now on: `CLAUDE.md` §1
  workflow, D-071.

### 2026-10-13 → 2026-10-17 — Synthetic data (M1): design round, spec, steps 0–7
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
- 2026-10-14, step 1 built (population), spec extended:
  - the SDS reviewed the spec ("okay to move forward"); build plan and proof merged into one
    table; Claude's proposals written in at the SDS's request: product rates and income thresholds
    (OD-16, confirmed at the step-2 gate), the nationality / employment mix per profile, and a
    second entity for M3. Regression is supported whatever OD-15 settles (D-060): card spend over
    the next 3 months, with its true mean and quantiles in the oracle (step 6);
  - second validation month (SDS question): only the window ablation needs it, to show a gain is
    not one month's luck; burn-in makes all 24 synthetic months usable, so it fits;
  - code: `synthetic/src/synthetic/{presets,population,latents,generate,checks}.py`,
    `tests/test_synthetic_population.py`, `notebooks/00_synthetic_data.ipynb` (dev-only checking
    notebook). 100k clients generate in ~4 s (peak ~1.5 GB); 107 checks pass; no failing seed in 60;
  - first check run: one seed tripped a salary-transfer row at 4.5 standard errors. A 1,500-seed
    sweep showed unbiased draws, so it was chance, but the code review counted ~170 tests (not
    107) and ~1 failing seed in 40 at 4 standard errors. Tolerance set to 4.5 (family-wise ≈ 0.1%);
  - code review (3 blocking, 15 suggestions): the notebook failed `ruff check`; the entry-rate
    check used the wrong denominator; any month without new clients crashed small presets. All
    fixed, plus: one random stream per mechanism, so later steps never re-draw earlier columns;
    expected values restated from the spec rather than the generator's functions; a sharper
    income-vs-wealth check (slope on new clients); spec typos now fail loud; an `n` column in the
    check table; long check functions split;
  - simplicity review: the same two long functions and a repeated subsegment → profile mapping.
- 2026-10-15, step 1 revised after the SDS's review:
  - general rule: every function (public, private, test) has type hints and a docstring, and every
    module an explanatory docstring. `CLAUDE.md` §1 rules 9–10, enforced by ruff `ANN` + `D1` and
    `tests/test_code_rules.py` (ruff skips private functions); simplicity-review and code-reviewer
    check it too (D-063);
  - population: UAE and GCC split; more extreme nationality mixes (ARAB = non-UAE, non-GCC Arab,
    barely wealthier than ASIA; WESTERN peaks in Priority); Retired added (heavy in Private);
    fewer unemployed in PSB, more in Private; emirate mix per profile, Dubai-heavy, with "Others"
    at 25% / 7% / 11% (Private / Priority / PSB); hidden-trait correlations within [0, 0.2];
    turnover per profile (≈ 2.4% to 12% leave a year); residence gap a mix of recent arrivals and
    settled residents (median ≈ 0.4 years) instead of a mean-2-year exponential;
  - checks: 150 rows (emirate and turnover per profile, residence gap); 0 failing seeds in 40;
  - notebook: charts failed with "Mime type rendering requires nbformat"; `nbformat` added to the
    dev requirements (Jupyter has it inside the bank). Turnover chart per profile, residence-gap
    histogram;
  - spec: product rates now from public UAE figures (sources in the spec); no early settlement for
    loans; month-1 holdings drawn from the same hazards as adoption, so loan holders agree with
    income; second entity optional (D-064, OD-16 settled);
  - second validation month dropped: the window choice weighs train, test and validation (D-062);
    Claude flagged that weighting train rewards overfitting (Q119).
  - code review of the revision (2 blocking, 11 suggestions; all applied except a design note): the
    residence-gap check skipped ~95% of residents; the check test ran on the 5k preset, where many
    Private rows pass with zero hits and the false-failure rate was ~1%, not ~0.1%. Now: the check
    test runs at 100k (~7 s), new checks for month-to-month persistence of the hidden traits and for
    turnover read from the mart, no silent skip of empty strata, the zero-entrant test asserts the
    path ran, `median_income` renamed, one emirate table, `tests/` scanned for docstrings. Each new
    check was shown to fail on a deliberately broken generator. 154 rows; seeds 0–5 at 100k pass;
  - design note from the review (Q121): new clients draw ages like the starting book, so the book
    ages ≈ 1.4 years over the panel.
- 2026-10-15, step 1 closed and step 2 (holdings and states) built:
  - SDS answers: Q119 window choice weighs test and validation equally, train only shows the gap;
    Q120 emirate stays independent of residence and nationality; Q121 new clients 5 years
    younger; Q122 as few parameters as possible: credit cards with an onboarding wave then ~500
    adoptions a month, digital wealth ~400, auto loans ~150, traditional wealth and home loans ~30;
    Q123–Q127 defaults;
  - design (D-065): per product the share per profile plus adoptions a month (0/1 products) or the
    term (loans); leaving chances derived (refills of clients who left the bank included); chances
    logistic in traits, age, descriptors, the half-strict income threshold and churned status;
    credit card and e-banking have a 3-month onboarding wave, the others build up over tenure from
    "never held", which is also how the starting book is drawn (exact closed form of the stepped
    chain), so holdings agree with income, traits and tenure from month 1;
  - built with agents: a research agent drafted the step 3 questions; an independent agent wrote
    the step-2 checks from the spec (it hit a session limit at the end; Claude finished and split
    them); code-reviewer and ml-correctness-auditor ran in parallel;
  - review and audit findings fixed: digital activity read this month's e-banking state (lapses
    without a chance, wake-ups in the registration month, an oracle that could see a future
    registration); loan shares low by Jensen (now calibrated on P(≥ 1)); digital share off and
    drifting; lapse chance not centred; starting book one month behind; bisection replaced by
    brentq (fails loud). Loans now set by term (UAE maxima 48 / 60 / 300 months) because event
    counts gave absurd terms;
  - audit doc items: the oracle's window probability must freeze the state at the observation
    month (the naive product scored card AUC 0.71 instead of 0.81), events defined as "any month
    in the window", leavers' targets null by default (D-066); eligibility-defining state columns
    and exact identities added to the trap table; Target Factory's rule wording and panel-edge
    guard updated;
  - checks: 290 rows pass (rules, oracle vs realised events overall and per chance decile, shares,
    flat shares, steady-state volumes net of the book's growth, income threshold and exemptions,
    churned odds, onboarding); 8 deliberately broken generators each caught by the intended rows;
    pytest 9 passed in ~30 s (2.2 GB); notebook extended with a step-2 section;
  - flagged for the SDS: personal loans ≈ 680 new a month at the 48-month term (above ~400);
    traditional wealth at ~30 a month implies holdings that last ≈ 33 years.
- 2026-10-15, step 2 closed; the rest of M1 in one go:
  - SDS answers: Q128–Q129 defaults (personal loans ≈ 680 a month and traditional wealth held
    ≈ 33 years both accepted). Q130–Q139 (step 3 inputs) set aside, their content folded into the
    next round;
  - new approach (SDS): no more step-by-step gates. One long question round settles everything
    the rest of the synthetic data needs (Q140–Q208: process, amounts, current/savings, card,
    loans and wealth, subcategories, logins, time effects, the mart's columns, traps, oracle,
    output); then `test_harness.md` and a detailed build plan with instructions for subagents;
    then steps 3–7 are built in one go, with one thorough review at the end, so the framework
    itself can start the week of 2026-10-19;
  - measured for the plan: the canonical preset now generates in 9 s with 31 columns, 1.3 GB in
    memory (2.1 GB peak); at ~150 columns the mart must be written month by month and the
    canonical checks must read column subsets.
- 2026-10-16, question round answered, spec completed, plan written:
  - committed steps 0–2 together with the CDS meeting material (`2e50bc4`, SDS: fine to keep them
    in one commit);
  - SDS answers (defaults otherwise): Q141 size rules relaxed for good (functions ~50 lines,
    steps ~300–400 lines, D-067); Q147 the review guide lives in `synthetic/REVIEW.md`, the SDS
    reviews first and then a summary goes to the sync page for the LDS; the notebook is pushed
    with outputs, so no HTML export; Q149 no cuts, only the iteration steps go; Q151 levels:
    current/savings 40 / 4 / 1.5 / 0.5, card spend 0.4 / 0.3 / 0.3 / 0.35, card limit
    3 / 2.5 / 2 / 1.5 (× income), the rest as proposed; Q154 amounts as doubles, one decimal
    column that must work (`cc_limit`); Q163 card limits from a few product tiers, rarely adjusted;
    Q171 subcategory shares more extreme per profile; Q174 "never logged in" is null; Q175
    seasonality per profile (Mass travels little; school fees vary less than income, so they weigh
    most on lower Affluent); Q177 Private clearly apart, the rest overlapping; Q179 the generator
    assumes no observation window (the `dataset.md` example is closer to reality); Q182 one
    logical lowercase grammar (the real mart's naming is poor); Q186–Q190 traps on two products
    only (card acquisition, personal-loan opening), several kinds each, planted columns with a
    `_trap_<kind>` suffix and one trap summary (D-069); Q203 the CLI goes in the review guide;
  - `test_harness.md` rewritten as the full spec: amounts (levels, variation, current/savings
    booking identity, subcategories, card tiers and revolvers, loans, deposits, wealth with a
    market index, FX, logins, time effects per profile, overlap), the column list (≈ 145),
    nulls and types, the trap summary, the oracle (window probabilities on demand, standard
    targets, regression oracle), interface and budgets. Numerically checked first: the Hill
    estimator recovers the tail index within ≈ 5% through the lognormal body, and `exponnorm`
    gives the exact median offset;
  - build plan with agent instructions: `worknotes/handovers/synthetic_build.md` (stages A–F,
    module map, month loop, streams, signatures, independent checks per family, mutation tests,
    integration protocol, review package);
  - `CLAUDE.md` §1 rules 3 and 13, the simplicity-review skill and the code-reviewer agent updated
    (D-067); `notebooks/README.md` exception for the synthetic notebook; `dataset.md` example
    marked as an illustration.
- 2026-10-16, build stages A and B (agents: a builder per stage, independent checks authors from
  the spec alone, code-reviewer per stage; four agents stopped at an account session limit at
  midday and were resumed or relaunched):
  - stage A (`2cdf746`, review fixes `bdf0f16`): month loop split into start/advance/finish, ten
    random streams, true income and wealth base, hidden client attributes, card activity,
    current/savings activity and the hidden revolver chain, calendar terms (FX summer, digital
    drift, bonus trigger), 0/1 integer flags, a month-by-month parquet writer and `truth.json`,
    fast and slow test suites. Step-1 columns identical to before; steps 1–2 rows pass. Review:
    flags now fail loud on anything but 0/1; an explicit `rule` column picks the fast-suite rows;
    calendar terms act only on adoption and wake-up odds (not lapses);
  - stage B (`6335a3d`): balances, flows with the booking identity (max error 2e-8), subcategories,
    card tiers and revolvers, loans, deposits, wealth with a market index, FX, logins, seasonality
    per profile. All 173 step-3 rows pass at 100k; 12 deliberately broken generators each tripped
    their intended rows. Changes made while integrating: hidden attributes get their own stream
    (amounts' draws no longer move holdings); `separation` also scales subsegment median incomes
    (otherwise it had no effect on amounts); revolvers spend less as the card fills up (45% of
    revolver months sat at the limit, now 0.5%); the app relaunch is × 1.8 (× 1.3 gave PSI 0.07);
    FX trait loading 0.25 (0.4 put lag-1 on the band's edge). Canonical write ≈ 25 s, ≤ 1.4 GB;
  - checks for later stages already written from the spec (traps, mart, oracle), with their
    contracts (truth key layout, AUC definition, tenure convention) fixed in the plan.
- 2026-10-16 → 2026-10-17, stages C–F (the account session limit stopped agents four more times;
  each was resumed; from then on one agent ran at a time):
  - stage C (`c9ded4f`): name grammar, history buffer, rollups, recency and ratios with the null
    rule, explicit parquet schema; Spark recomputes every derived column; prefix stability holds;
  - stage B review fixes (`b1cce83`): fail-loud fallbacks, spec constants out of mechanism code,
    shared helpers; generated data byte-identical;
  - stage D (`f8c0fd0`): look-ahead leak columns, null controls, quality, dirty switches, extra
    columns. Simpson's reversal could not appear by subsegment (Mass is 94% of eligible rows);
    regrouped by a new `onboarding_channel` descriptor (`eb4fa2c`): within +0.12 / +0.13, pooled
    −0.17;
  - stage E (`2f61135`): window probabilities with the state frozen at t (equal to the recorded
    chance at w = 1), oracle AUCs 0.71–0.92 for 12 standard targets, relevance rankings, a Monte
    Carlo oracle for next-3-month card spend; null controls checked in the bottom fifth;
  - stage F (`bbde9af`, `e5abb2e`): CLI with `--checks`, source mapping through two private
    adapter functions, budgets (≈ 345 s, 1.8 GB RSS at 100k), check families in separate
    processes (one family needs several GB), the checking notebook with outputs;
  - canonical dataset in `data/01_raw/synthetic_canonical/` (100k, 2.5M rows, 145 columns): all
    1,197 check rows pass (after the final round);
  - final code review (0 blocking, 12 suggestions) and ML-correctness audit (safe; boosting every
    mart column on top of the oracle never beat it): fixes applied in one round, incl. sizing
    `truth.json`'s low-confidence flag on events rather than positive rows; four audit suggestions
    left for the SDS (behaviour-driven exits, a moderate leak, the shifted-column trap, dirty
    rollups) in `synthetic/REVIEW.md` §6;
  - memory note: other apps held most of the Mac's 8 GB (TextEdit 3.7 GB); runs were 5–10× slower.
- Files: `docs/components/{test_harness,environment,target_factory}.md`,
  `docs/{UPDATES,architecture,decisions,glossary,roadmap}.md`,
  `docs/context/{lessons,environment}.md`, `docs/guides/setup_{macos,windows_wsl2}.md`,
  `requirements.txt`, `requirements-dev.txt`, `synthetic/`, `src/core_modelling/{_compat,environment}.py`,
  `tests/{conftest,test_spark_roundtrip,test_synthetic_population}.py`,
  `notebooks/{00_synthetic_data.ipynb,README.md}`, `pyproject.toml` (ruff).
- Decisions / open decisions: D-056, D-057, D-062–D-069; D-042 status; OD-16 settled.
- Still open: the SDS's review of the synthetic data (`synthetic/REVIEW.md`), then the LDS
  summary; which Spark session arguments the
  bank needs (M2).

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
- 2026-10-14, round 4 (SDS + LDS prep sync; no comments on the overview): the questions now carry
  our joint proposals, "(new)" markers removed, renumbered:
  - a1 proposal: binary, possibly with regression; a2 proposal: FLAML only; the old a3 (release
    rhythm) dropped to stay on the short-to-medium term; a3 (was a4) is now a prioritisation
    question with the proposed order binary → regression → multiclass → time-to-event →
    forecasting → nearby problems, the regulated-models part unchanged;
  - b2 proposal: package distribution through Nexus; b3 starred, proposal: one repo per entity ×
    domain (2 × 3), caveat: needs standardised upstream data; the feature-source question (old d3)
    folded into it;
  - the lifecycle questions (old e2–e5) moved to a separate box, "to be covered in a separate
    session", where the CDS ideates from a blank slate (s1–s4); (e) keeps e1 (ML engineering
    capacity) and the definition-of-done confirm (e2);
  - f1 also asks whether the existing data observability framework can be reused; f2 proposal: a
    central team monitors the live models; c2 proposal: the current group model validation
    framework (already in the Kedro project template), is it sufficient?
  - proposals recorded as leanings on OD-02, OD-04, OD-15, OD-21, plus OD-13, OD-07–OD-09 (separate
    session), `monitoring.md` and the Phase 3 backlog.
- 2026-10-14, e2 refocused: milestones are not anchored to outside-the-bank steps, so the
  definition-of-done confirm only asks about internal systems (the first change request runs
  `deploy` and the production model scores). D-055 status noted; its wording changes after the
  CDS confirms.
- Why: the CDS meeting is on 2026-10-15.
- Files: `docs/roadmap.md`, `docs/decisions.md`, `docs/UPDATES.md`,
  `docs/context/{project,environment}.md`,
  `docs/components/{lifecycle,monitoring,config,feature_ledger,eda}.md`,
  `worknotes/chief_ds_meeting/{overview,questions}.md`, `worknotes/README.md`, `worknotes/sync.md`.
- Decisions / open decisions: D-058–D-061; OD-06–OD-10, OD-13, OD-15 updated; OD-23 opened.
- Still open: Q111 (confirm once built); the rename (Q118); the meeting itself.

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
