# Log
Verbose trail behind `worknotes/sync.md`, newest first. Updates on the same topic from the same or
neighbouring days share one entry, each keeping its date. Template and rules: `worknotes/README.md`.

### 2026-11-06 — Reviews 3 and 4 of major step 2, the EDA gaps spec built; EDA to the LDS
- Review 4 (R38–R41, Q531, verbatim in `answers.md`): a line chart's top is min(every point,
  twice the highest supported point), so many grey points no longer flatten or escape the chart;
  the slices' decision paragraph is its own view (`decision_note`), shown by the report and said in
  notebook 02's markdown; the notebook's per-feature and per-stratum headings are Markdown, not
  raw HTML; no copy of a notebook's old outputs is kept; `eda/report.py` stays one module
  (Q531, maybe revisited after the LDS's feedback). The touched modules' tests 79 passed.
- `review_guide.md` rewritten for the LDS (the notebooks first, six key points, about 1.5 h);
  handover `worknotes/handovers/m2-2-major-step-3.md` written for Feature Checks in a new chat,
  with every formatting rule of EDA's reviews.
- The SDS's review-3 remarks (R29–R37, Q523–Q524, verbatim in `m2_2_understanding/answers.md`)
  merged with `eda_gaps_spec.md`; built on Opus in waves on disjoint files (slices + profile ∥
  sources ∥ chart changes → Target Factory → the EDA wiring → notebook 02), each step reviewed.
- Findings that changed the design: the ML audit showed the decision view's categorical order
  ("other window periods") not out of sample on a panel (a null code read lift 1.3–1.6 on small
  populations): now cross-fitted by client fold, prior included; the occurrences per period
  showed the validation period's outcomes: now cut at the window's last + w; the view reads in
  sample and never as a baseline (the spec's "the number a model has to beat" dropped, §4.3).
- R31 answered: the summary hid the labels outside the window by design (M2.1); now filled up to
  the window's last, earlier periods included; after it they stay blank (a gap period's target
  window reaches the validation period's outcomes).
- Results: the touched modules green after each step; full suite 533 passed (9 slow deselected, 8:49);
  notebooks 01 and 02 on the 100k data with no cell error (`run_eda` 200 s, report 5.8 MB).
- Open for the SDS: V55–V73 (`plan.md` §9). Nothing committed.

### 2026-11-06 — An independent look at EDA: what key element might be missing (brainstorm, nothing built)
- Asked by the SDS as a brainstorm. Inputs: the spec, the code, notebook 02, a legacy comparison
  and an outside survey (EBA GL/2017/16, the ECB internal-models guide, scorecard practice, the
  profilers), both by subagents and checked on the main thread.
- Ranked first: EDA never uses the declared decision (`decision.type`, `n`) beyond listing it in
  the choices block; nothing says what one feature achieves at the operating point (capture,
  lift, precision at the top n or at fixed shares) or what a model must beat. Computable from the
  cells, snapshot period, in the ranking's order; a per-task spec entry for amounts.
- Also absent and cheap: a value profile per candidate (min, p1, median, p99, max, the top mass
  points, ±inf), the legacy `univariate_summary` dropped without a record; the population's time
  dimension (stratum composition per compared period, the gap and latest periods' counts, which
  `eda.json` stores and the report never shows, panel entries and exits, the unlabelled eligible
  rows per period); each candidate's source in the ledger and the sources' matched share per
  period (in the join log, never in the report).
- A stale sentence: `reporting.md` chart rule 4 and `eda.md` "The statistics" describe a
  twenty-group histogram from the cells; nothing draws one.
- Adjacent, not EDA's: where in the forward window the events fall (Target Factory's summary);
  null-indicator clusters (Feature Checks); an exposure stratum (guidance, needs campaign data).
  Not raised: WoE/IV and a quick multivariate model, settled or against `CLAUDE.md` §4.4.
- The SDS answered Q525–Q530 the same day: the decision view, on the evaluation slices (the top
  decile the reading that matters); the value profile in Extended, lean; the time dimension
  skipped; the source column and the sources table; the histogram sentences deleted; the target
  view in Target Factory. On the way the proposed offset distribution turned out flat by
  construction under a forward-window label (every conversion puts one positive row at every
  offset), so the spec replaces it with the conversions per period of occurrence. Build spec
  with the Q&A verbatim, V55–V65 and the steps A–F: `m2_2_understanding/eda_gaps_spec.md`, to
  be merged with review 3 in the other chat; this chat closes.

### 2026-11-05 — Review 2 of major step 2: remarks, Q501–Q522, the build and the stage-3 review
- Built from `review2_spec.md` the same day, on Opus throughout (main thread and every agent):
  A+B (data layer, range labels) ∥ C (primitives) → D (views, `eda/explore.py`) → E (notebooks
  on the 100k data) ∥ F (component docs) → the D fix round and two simplicity passes; one
  code review per step, every finding fixed or ruled on.
- Main-thread rulings on the way: one figure has one legend, so a deep dive pairs the group
  chart with the first strata chart only (V34); label numbers lose the thousands separator (V30);
  a key feature that is a stratum gets no chart against itself (V41, found on the 100k report by
  headless-Chrome screenshots, the way the report was checked here); the deep-dive views read
  the stored tables (V45); a numeric's groups stay cut from the cells (D-135).
- Stage 3: seven reviewers (code ×4, ML audit: safe, silent failures, compatibility), every
  finding checked by a second reader (none refuted; two partly), one fix round on disjoint files,
  a review of the fixes, a last small round. The weightiest: the regression concordance's SE
  ignored the target's ties, 1.3–2.7× too small on a zero-inflated target, so a null feature got
  a direction up to 44% of the time (V47, D-082 amended); the report rendered after the commit
  marker (V49); negative estimates clipped (V50); `pivot_target` sorting labels as text.
- Results: full suite 510 passed (9 slow deselected, 8:49) after the fix round, the touched
  modules green after the last small round; `ruff check .` clean; notebook 02 on the 100k data:
  `run_eda` 132 s, 1.2 GB peak, report 5.6 MB; notebook words 02 4,009 → 2,046, 01 796 → 581.
- Open for the SDS: V29–V54 (`plan.md` §9), Q523 (percent rate axes), Q524 (thin strata levels
  setting the strata chart's axis); the review guide is rewritten for review 3. Nothing committed.
- Earlier the same day: the SDS reviewed through notebook 02 and set a three-stage review
  (remarks and brainstorming questions, an exact build plan, then the build and a comprehensive
  review); remarks R10–R28 and the answers Q494–Q522 are in `m2_2_understanding/answers.md`.

### 2026-11-04 — Major step 2 built: EDA, its report, notebook 02
- Built in three workflows on the main thread's briefs and one contract file (the interfaces
  between the reporting primitives, the EDA modules and the stage, fixed up front): m2.1
  (Sonnet) ∥ m2.2 (Opus), then m2.3 (Opus·xhigh), then its review ∥ the ML audit of m2.2+m2.3 ∥
  m2.4 → its review; one fix round by three fixers on disjoint files; no Fable.
- Fixed before m2.3 (main thread): the reporting reviewer's chart bugs (a greyed bar kept its
  height, the support axis title, a null line or box dropped or mislabelled, lift 0 uncoloured,
  numpy ints); the pooled window's interval, √periods too narrow, now on effective clients
  (`window_clients` gains `event_clients`).
- The ML audit (no §4 invariant broken) found: the settings digest lacked
  `time.validation_period` (V21), a collect's row order made the association cap
  non-deterministic (T34, V22), a strictly positive regression target over few rows crashed the
  Kendall SE, Hanley–McNeil is not symmetric below 0.5 (V24), an empty client fold raised; all
  fixed with tests.
- Decisions to veto: V18–V28 (`plan.md` §9); questions Q494–Q500 (`review_guide.md`). Size: about
  2,750 lines of `src/` and 890 of tests against the plan's 1,000 and 500 (Q494 proposes a
  simplicity pass).
- Measured: `run_eda` 50–54 s on the unit preset, 60 s on the `dev` preset (20,000 clients, 161
  candidates); the report 5.6 MB (plotly.js 4.83 MB of it). Full suite 491 passed (9 slow
  deselected) in 9 min; `ruff check .` clean; notebook 02 ran end to end on `dev` with no error.
- On `dev` the traps rank on top, the null controls read 0.50–0.52 and are never key features.

### 2026-11-04 — Handover for major step 2
- `worknotes/handovers/m2-2-major-step-2.md`: state, routing, the EDA call sequence and the statistics callers' guards (moved out of the session scratchpad), the builders' common brief; resume with `/resume m2-2-major-step-2`.

### 2026-11-04 — Review 1 fixes: the level encoding cross-fitted by client fold, the window SE on clients
- The counts table gains `fold` (a categorical's client fold, `pmod(xxhash64(unit_id), 5)`; null
  for a numeric); `estimate_cells` counts a categorical's cells five times; `window_clients`
  gives the window's labelled rows and distinct clients by class.
- `concordance.cross_fitted_concordance` replaces `cross_fitted_table`: each fold ordered by the
  other folds' encoding, Somers' D over the pairs inside each fold only (pooling the folds into
  one table leaned 0.49, since two folds' orders come from fits that share data);
  `client_support` scales a window's events and non-events to distinct clients.
- Measured (40 seeds, a panel null 50-level code, ~500 event clients): by client fold 0.502 on
  average, SD 0.019, so single values of 0.53–0.55 are noise the client SE covers; by period
  0.57; in sample 0.60. A panel null numeric marked `non_monotone` in 0 of 20 seeds on the
  clients' SE, more than one on the rows'.
- The combined review (ML audit, Opus): the within-fold value is exactly unbiased and no path
  lets a client inform its own order. Fixed from it: a regression target without zeros crashed
  the support (now per task, `TASK_SPECS[task]["client_support"]`, regression by one ratio);
  distinct clients overstated the size with unequal rows per client (now Kish's `(Σ m)² / Σ m²`
  in `window_clients`); a sparse feature's scaled support fell below one row (floored at one);
  the fold only on the window's cells (the table grows on the window only); clear refusals for
  an empty `read` and one fold; the run-wide ratio's error directions documented. Open, for the
  SDS (question 14): the cross-fitted value spreads about 1.4× its SE (the folds' orders share
  fitted noise), so a null code cleared `direction`'s 0.5 + 2 SE in about 12% of runs. The SDS
  chose a fixed factor: `CROSS_FIT_SE_INFLATION = 1.5` (the measured upper end), with a Phase 3
  wishlist item to check it and possibly replace it with a permutation null.
- Tests run: `test_statistics.py` (33), `test_counts.py` (19), `test_code_rules.py`. Docs:
  eda.md, dataset.md, D-135, T33, reporting.md's ranking row, plan V16.

### 2026-11-04 — The SDS's review 1 remarks: answers in chat, routing reset
- Answered the review-1 questions in chat (margin and SE, the encoding's bias, cells, edges, the
  pairwise cap, clustering, the level ceiling, binning, client-constant, overlapping flags); the
  fixes wait for the SDS's go, in one batch.
- PySpark 3.4.3's own deprecation warnings (typing.io, distutils) filtered in `pyproject.toml`.
- Routing for major steps 2–3 reset (`plan.md` §3): Opus main thread, no Fable builders, one
  combined review per minor step, one fix round per major step, Fable only for the final audit;
  D-072 (l) and `CLAUDE.md` §1: Fable at most 25–30%.
- The SDS's answers (Q6 default, Q8–Q11 yes) applied: `PAIRWISE_ROWS` 50,000 and
  `MIN_SHARED_ROWS` 500 (`spearman_matrix` 6.1 s → 3.3 s with 8 null masks, 22.7 s with 76 at
  50,000 rows); `client_constant`'s flagged features shown as one table in notebook 03, the
  feature store's static metadata on the backlog; the log keeps 7 working days (pruned: 2,209 →
  822 lines) and is appended only when a turn settles something; the small-prompt rule in
  `CLAUDE.md` §8 and D-072 (h).
- Q7 measured before building the test: with the same clients in every period and a 3-month
  target window, a null 50-level code at ~200 events a period reads 0.597 in-sample, **0.570
  cross-fitted by period** (max 0.588) and 0.492 cross-fitted by client fold (10 seeds); capped
  300- to 5,000-level codes read 0.50–0.51 by period. The same panel effect hits the numerics'
  margin: the window SE counts a client's persisting label once per period, so a null numeric is
  marked `non_monotone` 12–18% of the time (0% with the SE on distinct clients). Both fixes wait
  for the SDS (questions 12–13).

### 2026-11-03 — Major step 1 done: m1.3 and m1.4b built, reviewed and fixed; full suite 443 passed
- **m1.4b (Opus, 59 tests at build):** `statistics/cells.py`, `concordance.py`, `intervals.py`,
  `association.py` and the per-task entries in `tasks.py`. The ML audit (Fable) measured two
  statistics failing at the bank's event counts and both were changed in the fix round (30 tests):
  the fixed 0.03 non-monotone margin marked 42% of null numerics at 500 events (63% at 250), the
  SE-scaled `max(0.03, 4 · SE)` marks 0–2% at every size while the inverted U stays marked; the
  window-fitted level encoding read 0.53–0.57 on a null 20–50-level code at ~190 events per period
  (above Training's 0.515 floor), the cross-fitted encoding (`cross_fitted_table`, each period's
  levels ordered by the other periods' encoding) reads 0.49–0.52 and a predictive code loses under
  0.01 (V16, D-135 changed in place; T33). Also from the reviews: `explained_by_others` over the
  Spearman members only, "not available" for a not-compared pair, mixed kinds or inconsistent
  correlations (V17); `cramers_v` plain; `shares()["bins"]`; `pool_periods` keeps unlabelled
  `sum_y` null; `rare_effect` refuses a non-positive rest. Exact Spearman timing: 11 s at
  139 × 200,000 with the realistic mask structure, 253 s with 76 distinct masks (recorded for the bank).
- **m1.3 (Fable, 33 tests at build; resumed after the model's 5-hour limit):** `Frames(snapshot,
  rows, …)`, `detect_kinds`, `dataset/counts.py` (compared periods, the edges, the levels, the two
  passes, the client-constant shares in 50-column chunks, the population counts, the cell
  estimate). The reviews (code, silent failures, ML: accept) led to the fix round (37 tests): the
  edges cut on the snapshot's ELIGIBLE rows; a 10,000-level ceiling above which `new_levels` is
  "not available" up front (`window_levels` returns the levels and the `over_ceiling` list, a
  required argument of both passes); a literal `"null"` level quoted so it never shares the null
  bin's label; NaN in a categorical as null; loud refusals (no supported candidate, empty window
  periods, a missing snapshot period); NaN as null in the constant shares; plain counts in the
  population table; binary target bins checked; the cell estimate covers both passes. Measured:
  an unnormalised `-0.0` lands below the `= 0` singleton on PySpark 3.4.3 (T26).
- **Notebook 01** reads `frames.snapshot` and `meta["population"]` (the frame rename).
- **Docs:** `eda.md` (Pass 1 and 2 wording, the edges rule, the categorical ceiling, the statistics
  section rewritten by m1.4b, the checks, the artifacts and write order), `dataset.md` (by m1.3),
  `feature_checks.md` (redundancy wording, `new_levels`), `feature_ledger.md`, the glossary, D-135,
  `plan.md` (§2 signatures as built, V2 margin, V16–V17), `lessons.md` T33 and T26's measurement,
  `training.md` (notes for Training's D-088 and kinds checks), `review_guide.md` (ready).
- **Verification:** `ruff check .` and `ruff format --check .` clean; the full suite 443 passed
  (9 slow deselected) in 6 min 16 s. Nothing committed. Major step 1 goes to the SDS's review.

### 2026-11-03 — Major step 1, build round 2: the fix rounds landed; m1.3 and m1.4b restarted
- **Fix rounds (Opus `xhigh`, every one green and ruff clean):** m1.1 (127 tests: `feature_checks:
  {}` refused; `nulls_informative_min` checked against the leak bound in use; `set
  time.validation_period` to null refused; `_accepted_period_end`; `__version__ = 0.3.0.dev0`);
  m1.4a (14 tests: `merge_bins` sums only `n` and `sum_y` and refuses other numeric columns;
  `new_level_share` reads current cells only and never returns NaN; `psi` refuses shares outside
  [0, 1]); m1.5 (29 tests: `save_ledger(ledger, folder, meta)` with the data-definition hash and the
  stage digest in `_ledger.json`, `read_ledger(folder, ddh)`, the ledger saved first and the stage
  json last as the commit marker, `tables` stamped and checked, `datetime64` and NaN handled in
  JSON, unknown excluded/held/kept names refused, the failed-swap restore); the null validation
  period (102 tests: `target_factory.last_labelled_period(cfg)` owns "v, or the window's last period
  when null" for Target Factory, the panel, the contract and the model input; `held` checked like
  `excluded`; the spine's reach without `+ w`, dataset.md's rule).
- **m1.2's reviews** (compat: accept; code and silent-failure: fix first) found two real holes,
  both confirmed by probe and closed in its fix round (155 tests): a `keep` on several features
  settled findings in advance on features that never had them (every stored (feature, finding)
  pair must now be open at write time: a keep with differing open sets is split), and a `revert`
  restored a validation period a run had compared (the revert is checked like a `set`, and
  `resolve_config` refuses a stale resolved period). Also: run `periods` must be the config's
  period labels; `OPS_BY_OPERAND` refuses operands on the wrong op; a writer starting a new log
  says where; `data_path` lower-cases the use case; a corrupt entry file is named.
- **The two Fable builders (m1.3, m1.4b) hit the model's 5-hour limit before writing a file;**
  resumed at 17:33: m1.3 on Fable (its context kept), m1.4b restarted on Opus `xhigh` so a second
  outage cannot stall both. Their reviewers follow when they land.
- **Docs propagated on the main thread** (the files no agent holds): `feature_checks.md` (the
  empty-mapping refusal, the entry writer and paths, the null-informative bound, the PSI groups
  and `psi`'s contract, the per-feature keep rule, the run entry's labels and the revert check),
  `target_factory.md` (the last labelled period), the glossary (last labelled period), D-134 (the
  keep rule), `training.md` (the run marker's `periods`), `architecture.md` (the inventory's
  sidecar and stage-json fields), `sources.py`'s docstring. `eda.md` and `dataset.md` wait for
  m1.3 and m1.4b, which own parts of them.

### 2026-11-03 — Major step 1, build round 1: the spike and four of six pieces built and reviewed
- **The facts spike (Sonnet, 17 items, every number measured on PySpark 3.4.3):** the explode
  counts pass takes 15–18 s on the canonical six-month window (625,074 rows × 139 numerics →
  115,695 cells, 2.8 MB shuffle, 0.9 GB heap) against 75 s for the per-feature loop at the heap
  cap; the lag pass 19 s; the wide per-client `groupBy` spills 2.2 GB (chunk it, T27). `Bucketizer`
  accepts `nextafter` singleton splits and needs no casts; a null input gives a null bucket, NaN
  the extra one (T26). The edges rule leaves no canonical numeric collapsed (plain quantiles
  collapse 33 of 139 columns to ≤ 5 bins). The table concordance equals the binned AUC to 1e-16
  and the raw AUC within 0.0001; the regression τ-b is exact against binned rows, about 0.01 off
  raw (T32). Rank-once is not the pairwise-complete Spearman when null masks differ (0.23 off;
  T28). scipy's `association` fails on empty marginals (T29); plotly keeps a repeated `div_id`
  and clamps a zero quartile on a log axis; jinja2 is not in the venv (T30); parquet list columns
  come back as arrays (T31). Decisions and traps: D-135–D-137 extended, T26–T32, plan §7a.
- **Built (tests pass, ruff clean):** m1.1 the schema (Opus; 113 tests): `Eda(snapshot, bins,
  key_features)`, `Features.kinds/kept/held`, `Time.validation_period: date | None`, the typed
  `FeatureChecks` with bounds on every threshold, `snapshot_period`, the `keep` rename across
  the codebase, the template and both example configs. m1.4a `statistics/distributions.py`
  (Fable; 12 tests): `quantile_edges`, `bin_labels`, `merge_bins`, `psi`, `new_level_share`,
  `standardised_difference`. m1.2 the audit log (Opus; 134 tests): `Entry.finding/findings/
  periods`, strict validation, `open_flags`, `held_features`, `features.held` in the resolved
  config (the hash moves with it, measured), `record_stage_entry`, the 18 feature-check leaves
  loggable, `check_settable`, the validation-period refusal, CLI `--keep --findings`,
  `data_path(env, use_case, layer, *parts)`, `feature_dir`, `audit_log_dir(env, cfg, entity)`
  (the planned `stage_dir` folded into `feature_dir`). m1.5 artifacts and ledger (Opus; 22
  tests): `StageResult`, `write_stage`/`read_stage`, `settings_digest`/`settings_meta`,
  `check_upstream`, `remove_stage`, `create_ledger`, `add_columns`, `save_ledger`, `read_ledger`,
  `render_decisions`, `resolve_features`.
- **Reviewed:** m1.1 (code-reviewer, compat-guardian: accept; `feature_checks: {}` would run no
  check; the `nulls_informative_min` vs `null_concordance_max` bound; six readers still assume a
  date for `v`), m1.4a (code-reviewer, ML auditor: accept; `merge_bins` sums any numeric column;
  `new_level_share` double counts lagged cells and returns NaN at `n = 0`), m1.5 (code-reviewer,
  silent-failure-hunter: fix first; compat-guardian: accept): `datetime64` written as nanoseconds,
  NaN as a bare JSON token, unknown excluded/held names silently ignored, the ledger sidecar
  without the data-definition hash, no write-order rule, list cells NaN in memory vs None on
  disk. The usage limit stopped m1.3, m1.4b and m1.2's reviewers (7 of 19 agents).
- **Decisions taken on the main thread (open to the SDS's veto, listed in the review guide):**
  `feature_checks: {}` refused; the `nulls_informative_min < null_concordance_max` validator;
  `set time.validation_period` to null refused; a `keep` naming a finding open on none of its
  features refused; `quantile_edges` cuts the rest into `bins − n_mass` bins (exactly `bins` for a
  continuous column); `merge_bins` gives "about `groups`" groups; the ledger is saved first and the
  stage json last; `_ledger.json` carries the data-definition hash and the stage digest;
  `resolve_features` refuses unknown names; `__version__ = 0.3.0.dev0` during the build; the
  exact pairwise-complete Spearman grouped by null mask (T28). jinja2's pin is asked of the SDS.
- **Round 2 launched (background):** m1.3 and m1.4b (Fable `xhigh`), the m1.2 reviewers (Opus),
  and four fix agents (Opus `xhigh`): m1.1's findings, m1.4a's findings, m1.5's findings, and the
  null-`v` readers (`target_factory.py`, `panel.py`, `contract.py`, `model_input.py`, with
  `held` in the named-feature check). Docs updated on the main thread meanwhile: `lessons.md`
  T26–T32, D-135–D-137, `architecture.md` (Public API rows built, `record_stage_entry`, the open
  flags' home), `reporting.md` chart rule 4 (`1 / groups`, the label grammar, log axes),
  `plan.md` (m1.2 paths, m1.4 halves, §7a).

### 2026-11-03 — Briefing for the LDS sync
- `/brief`: `sync.md` refreshed (windows 11-02 to 11-03 and 10-26 to 10-30; last sync 11-03).
  Every commit since the last briefing is covered by this log; uncommitted: the plan and record
  revisions after R1–R9 and the doc edits staged with them.
- Review list: a new first item, the Stage 2 design's summary levels (input before the build is
  cheapest); Stage 1 kept (not reported finished). A new open question: whether OD-01's
  stakeholder buy-in, planned for the week of 10-26, happened (nothing records it).
- Flagged for the SDS: Q464 puts version 0.3.0 at Stage 1's sign-off, `plan.md` §1 at Stage 2's
  end; M2 (to 11-20) is tight with Stage 2 ending about 11-12.
- Then the SDS's remarks on the page: summarise the essence of the updates and the SDS's key
  decisions, not the rounds; give the key decisions as much room as the open ones; no timelines.
  `sync.md` rewritten around the decisions (flags act at both levels, notes inform; no sampling,
  one counts table and one engine; the lag check and the look-ahead flag; the layout and no bumps
  in 0.x), each a "Decision: …" review item; dates removed. Rules extended in
  `worknotes/README.md` and `.claude/commands/brief.md`.
- Then (the SDS): each review item names the doc's Level 1 plus the sections and tables that
  carry the decision, by heading (as the SDS reviewed EDA and Feature Checks); the four decision
  items and the Stage 1 item rewritten so; the rule added to `worknotes/README.md`.
- The LDS's answers: no other example modes needed for now (`run_modes.md`, item 5); the model
  documentation question dropped (`roadmap.md`, Phase 3 wishlist).

### 2026-11-03 — Stage 2 plan revised after the SDS's remarks (R1–R9); the build waits
- The SDS read the plan and the spec and sent nine remarks (recorded verbatim with what was done at
  the end of `worknotes/m2_2_understanding/answers.md`); the build does not start yet. Their 09:24
  commit ("Stage 2 initial plan") took the doc edits below with it; the plan and record revisions
  are uncommitted.
- **Routing budget (R2):** Fable may take a third to half of the stage's tokens and the hardest
  code pieces; `xhigh` effort on every model where a wrong answer is costly; architecture over
  rewrites. `plan.md` §3 rewritten: Fable takes m1.3 (frames and counts), m1.4 (statistics), m2.3
  (EDA stage) and m3.2 (decisions and Feature Checks stage); every §4 Opus piece and its reviews at
  `xhigh`; the notebooks to Opus `xhigh`. D-072 (l) and `CLAUDE.md` §1 extended.
- **Notebook guides (R8):** the guide text is the notebooks' main deliverable; rule extended in
  `notebooks/README.md`; m2.4/m3.4 content and the done criteria name it.
- **Tests (R7):** the SDS reads code, not tests; the review guide marks at most two "read this
  test" per major step (`plan.md` §4 item 6).
- **`lag_drop` → `lagged_signal_drop` (R3)** in `feature_checks.md` and `test_harness.md`.
- **`psi_latest` (R4, V13):** pinned to the window's last period against the latest period,
  whatever `eda.snapshot` says (`feature_checks.md`, `feature_ledger.md`, D-135).
- **The one-bucket symptom (R5, V14, T25):** quantile edges collapse on zero-inflated or discrete
  columns. The edges rule: mass points (share ≥ `1 / bins`) as singleton bins, quantile edges over
  the rest; charts merge cells by cumulative share, a mass point its own bar. Unit tests on three
  constructed columns, the m1.0 bin-count measurement and an acceptance-test assertion
  (`eda.md`, `dataset.md`, `reporting.md`, the glossary, `test_harness.md`, `lessons.md` T25, D-135,
  `plan.md` m1.0, m1.3, m1.4, m3.3, §7).
- **Chart sampling (R6, V15):** no chart draws clients (cells and quartiles only), so nothing is
  sampled; a rule for any future row-level chart in `reporting.md` requirement 5.
- **Null register (R1):** moved to the owner docs in the spec step; N10 added to `dataset.md`, N17
  to `training.md`; the register's intro lists every owner.
- **V1 confirmed (R9)** with the wording "for Training, a held feature acts as an excluded feature
  without a final decision" in `feature_checks.md`, `feature_ledger.md`, `training.md`, the glossary,
  `notebooks/README.md`, D-134 and the plan's notebook 03 step.
- Timeline shifted one day (`plan.md` §8); SDS reviews 11-06, 11-10, 11-12. Nothing coded.
- **The SDS approved the plan ("let's go, start working on major step 1")** and committed the
  revisions (`b694961`). The build of major step 1 started as one background workflow: the facts
  spike (Sonnet), m1.1 the schema (Opus `xhigh`) and m1.4a the distribution statistics (Fable
  `xhigh`; split off m1.4 because the counts passes need `quantile_edges` first) run first; m1.2
  (Opus), m1.5 (Opus), m1.4b (Fable) and m1.3 (Fable, after the spike) follow as their inputs
  land; each step's reviewers (code-reviewer, silent-failure-hunter, compat-guardian on Opus;
  the ML auditor on Fable) run as soon as it returns. Briefs: one file per step in the session
  scratchpad (`briefs/common.md` + `m1_*.md`), the main thread reads every diff and the
  findings next. Status rows moved to "building" in `docs/UPDATES.md` and `docs/README.md`.

### 2026-11-02 — Stage 2 design settled: round 4 answered, the spec written, the plan drafted
- The SDS answered round 4 (Q490 at the default with 100 bins and an `eda.bins` switch that turns
  the binning off for small populations; Q491–Q493 at the defaults; Q477 confirmed by silence) and
  asked for the spec, the holistic review and the plan with a routing table that keeps the main
  thread on Fable. Recorded at the end of `worknotes/m2_2_understanding/answers.md`;
  `questions.md` is a stub (new questions start at Q494).
- **The spec, written into the component docs** by five Opus doc writers and one Sonnet
  propagator from one design brief, every result read and corrected on the main thread:
  `eda.md` (446 lines, three levels), `feature_checks.md` (493), `feature_ledger.md` (244),
  `reporting.md` (215), `config.md` (the Stage 2 fields, the `keep` / `flag` / `run` entries, the
  worked example, the folder order), `dataset.md` (the snapshot and `rows` frames, the counts
  passes), `test_harness.md` (the acceptance test), `data/README.md`, the glossary (concordance,
  best-order concordance, counts table, snapshot, compared periods, flag / note / held, kinds,
  bins), `lessons.md` (the SE lesson corrected; T23 a screen that flags without acting; T24
  sampling the analysis population), `notebooks/README.md`, `run_modes.md`, `training.md`,
  `lifecycle.md`, `architecture.md` (§2, §3, §11, the Public API, the artifact inventory, the
  data folders), `docs/README.md`, `CLAUDE.md` §4.6 (D-134's wording).
- **Decisions:** D-134 (flags hold features out at both levels; `keep` with `findings`; replay
  writes `features.held` into the resolved config so the run hash sees it), D-135 (the window
  stays in Spark as one counts table, the snapshot collected whole, `eda.bins`, one statistics
  engine, `concordance_best_order`, the two PSI notes between named periods), D-136 (root → use
  case → layer, the artifact files, local paths until M2.4, no schema bumps in 0.x), D-137 (the
  Stage 2 engineering shape); D-007, D-029, D-030, D-031, D-050, D-064, D-082, D-088, D-125,
  D-132, D-133 extended in place. OD-11 settled and removed; OD-12 narrowed to Evaluation.
- **Decided while integrating the writers' findings:** the open flags' features enter the
  resolved config as `features.held` (a config agent's catch: trail-only flags would have left
  two runs with different held sets on one hash); `resolve_features(ledger, resolved)` reads it;
  the clusters are Feature Checks' table, cut from EDA's correlation table, with
  `explained_by_others` as the multiple correlation from the correlation submatrix (no rows
  needed); `pivot_target(result, rows, columns, where)` reads the task and strata from the
  stage result; the lag is by period index and the window's first period has no lagged value;
  `SE_FLOOR = 0.005`; the five steps run in a fixed order (a deviation from Q488's "YAML order",
  stated in the record); the replayed list `features.kept_despite_flags` becomes `features.kept`.
- **The plan:** `worknotes/m2_2_understanding/plan.md`: three major steps (foundations; EDA;
  Feature Checks), sixteen minor steps with files, signatures, tests and what is left out, the
  routing table (Opus for every §4 path, Sonnet for reporting, notebooks, the facts spike and the
  doc propagation, Fable only for the plan, the briefs, the diffs, the integration and the ML
  audit), the order and parallelism, the done criteria, the risks, a timeline estimate
  (SDS reviews 11-05, 11-09, 11-11). Waiting for the SDS's approval.
- **The holistic review** (Opus, fresh context, read-only; verdict "proceed with changes") found
  ten contradictions between the freshly written docs, four knock-on effects on docs not updated
  (`environment.md`'s paths, `architecture.md` §4/§9/§10, `evaluation.md`'s support rule,
  `monitoring.md`'s PSI), four shape risks and four gaps. All applied (a Sonnet propagation pass,
  verified on the main thread). The ones that needed a decision are the plan's veto list
  V1–V12: the held set in the resolved config; the ranking value is the plain concordance unless
  the feature is `non_monotone` (the review showed "the larger" would boost every noise
  feature); a cell-count guard for `eda.bins: null`; the clusters as Feature Checks' table; the
  reserved `__other__` / `__new__` bins; the fixed step order; `concordance_unstable` kept a flag
  with a false-positive bound in the acceptance test; the regression lift only for a positive
  mean; the latest period only after the validation period; one environment file per entity
  inside the bank. Routed to the build's reviews: the best-order optimism and the train-only
  ranking inside a cluster (ML auditor), the in-place schema and path changes (compat-guardian).
- Quick check after the doc work: `pytest tests/test_environment.py tests/test_config_schema.py
  tests/test_code_rules.py` → 64 passed (the configs and the code are unchanged until the build).

### 2026-11-02 — Stage 2 round 3 answered; no sampled EDA: the window stays in Spark; round 4 opened
- The SDS answered Q478–Q489 (Q477 not listed: taken as its default (A), confirmation asked),
  mostly at the defaults: the finding table, the folder order, guidance only for forward-looking
  names, mixed pairs now, the `dev`-preset trap test, local paths until M2.4, `feature_checks` as
  a typed mapping. Two departures: **no schema bumps in 0.x** (Q483: the `feature_checks` shape,
  the `keep` rename and the new entry fields change in place; the first bump when user testing is
  under way) and **no sampled EDA** (Q482 rejected: "that defeats the purpose of some reports").
  Recorded verbatim with the outcomes at the end of `worknotes/m2_2_understanding/answers.md`.
- The SDS's rule replaces Q482: the window's statistics are computed in Spark and only aggregated
  tables come to pandas; the snapshot analysis runs on every client in pandas; the Mac's
  100,000-client snapshot stands for the bank's full retail snapshot. Round 4's Q490 is the design:
  one counts table (feature, period, bin, target bin, lagged, n, sum of target) from a
  `Bucketizer` + explode + `groupBy` pass over the window, gap and latest periods, a second
  client-sorted pass for the lag check and `client_constant`, every window statistic read from the
  table; the snapshot collected whole for the pairwise matrix, kinds, edges, pivots and the
  row-level views. `eda.sample_share`, `eda.snapshot: window` and `Frames.drift` go. Q491 asks
  whether the snapshot's statistics come from the same table (one engine, default yes); Q493
  answers "shouldn't drift be measured between specific months": two PSI notes between named
  periods, `psi_gap` dropped, `concordance_unstable` keeps every window period.
- Q489 was not understood; Q492 explains it in plain words (the inverted-U age; the concordance a
  ten-leaf tree would reach) and renames it `concordance_best_order`.
- On A31 the SDS asked to keep track of every null-value assumption: a numbered register (N1–N18)
  now closes `answers.md` and moves into the spec's "Nulls" sections later. The facts to check are
  mine (the plan's first spike); the list in `questions.md` carries their status, with the Q490
  items added.

### 2026-11-02 — Stage 2 round 2 answered; the flags must act; round 3 opened
- The SDS answered Q466–Q476, mostly at the defaults: EDA on one snapshot by default
  (`eda.snapshot: last`), N = 10 key features with the correlation skip, the loggable
  `features.kinds`, the notebooks shipped in the wheel with an `init` command (M2.4), the
  redundancy clusters with `explained_by_others`, the `client_constant` finding for the 0.5.3
  look-ahead trap, `time.validation_period: null` for EDA-only configs. Recorded verbatim with the
  outcomes at the end of `worknotes/m2_2_understanding/answers.md`, which now holds both rounds.
- One design change: "what's the point of flagging if for an autonomous run they are not getting
  excluded?" Round 3's Q477 proposes that an open flag holds the feature out of training at both
  levels until a person keeps or excludes it (visible everywhere, reversible by one entry); Q478
  sorts every finding into flag or note and splits the null-indicator statistic into a leak flag
  (0.70) and a `nulls_informative` note (0.55). Q468 becomes two quality notes (`nulls_may_be_zeros`,
  `nulls_informative`) and no doctrine beyond D-029 (c).
- Two restatements: the folder order (Q479: the root is already the entity's area, so
  `<root>/<use_case>/<layer>/…` with no entity segment) and the other use case's label (Q480: a
  backward-looking event flag is an ordinary candidate; the name nudge is optional).
- Gaps found before the plan, asked in round 3: mixed-kind pairs now (Q481, A14 withdrawn), a
  client sample for EDA and Feature Checks at a real size (Q482), config and log schema bumps
  with migrations (Q483). A fresh-context gap analysis (Opus, read-only, 34 minutes) then
  corrected two draft questions (Q484 withdrawn: `forward_sum` already is the regression
  variant, Q420; Q483 re-aimed at the real break, the `feature_checks` shape) and added five
  (Q485 snapshot and window statistics both computed in EDA; Q486 the trap test on the `dev`
  preset with window assertions and an explicit scope dict; Q487 local artifact paths until
  M2.4; Q488 `feature_checks` as a mapping with typed, loggable thresholds; Q489 a binned
  concordance for non-monotone signal). Its settled plan defaults are listed for veto (A19–A36:
  flag entries per finding with an empty entry closing one, no lineage entry, verdicts derived
  at render, staleness digests, compared periods as run entries, the artifact files, report
  order, `StageResult.views`, regression specifics, pseudo-event shrinkage, nulls per
  statistic) and its library checks join the facts list. Two corrections to the record:
  `roc_auc_score` on a constant score returns 0.5 (sklearn 1.8), and `eda.snapshot` is a window
  period. `docs/context/environment.md` no longer says the collect fails loud (D-133: callout,
  then proceeds).

### 2026-11-02 — Stage 2 round 1 answered; the record file; round 2 opened
- The SDS answered Q418–Q462: mostly the defaults. Settled: the in-between depth and the longer
  stage (Q418, Q419: M2.3 from about 11-12); real regression functions on a variant config;
  `statistics/` and `reporting/` as subfolders of reusable functions that every stage imports,
  the stage modules orchestrating only (Q421); the stage function resolves the config itself; one
  `StageResult`; concordance as the one scale (pending the explanation); shrunk level encoding;
  no imputation; Wilson intervals, 20 events per bin; the lag check for time alignment; PSI 0.10
  and Cochran's Q; Feature Checks requiring EDA's artifact; the SE lesson corrected; the wide
  ledger; two reports; two notebooks; the trap acceptance test.
- Changed by the SDS: N = 10 key features at both levels with a correlation skip (Q436); the
  proposed-decisions table without a suggested operation and a simpler decision model (Q448,
  Q449); every default explained in the template (Q446); the folder order root (entity) → use
  case → layer (Q424); column kinds displayed, validated and overridable (Q426).
- Open from the generic remarks: EDA on one snapshot by default and EDA-only configs; a
  correlation view weighing redundancy against predictiveness with second-order effects; how
  users get the notebooks from a Nexus package; the 0.5.3 look-ahead trap (constant per client,
  below the oracle's AUC) needs a finding of its own; "nulls that mean zero" as a quality
  finding; another use case's label as a candidate (a §4.1 caveat raised).
- The record: `worknotes/m2_2_understanding/answers.md` holds every round-1 question verbatim
  with the SDS's answer verbatim and the outcome for the plan (the SDS asked for it before
  compacting the chat); `questions.md` is rewritten for round 2 (Q466–Q476; Q463–Q465 were the
  other chat's) with the explanations asked for (the ledger, concordance as Somers' D, the
  flag / exclude / keep model, the drift frame, `missingness_leak`).
- Files: `worknotes/m2_2_understanding/answers.md` (new), `questions.md` (round 2),
  `worknotes/log.md`, `docs/UPDATES.md` (status rows).
- Decisions / open decisions: none written yet; D-134 onward with the plan (D-029 (d), D-030's
  EDA scope, D-082's SE, D-132's N, the template defaults, the folder layout).
- Still open: round 2; then the spec into the component docs, the holistic review and the plan
  with the routing table.

### 2026-10-30 — Stage 2 (M2.2 Understanding) design opened: four surveys and Q418–Q462
- The SDS asked to start Stage 2 (EDA, Feature Checks, the feature ledger, Reporting) between
  thin and deep with every key component in, and to name every check and view explicitly. The
  brainstorming path is architectural (four new components); step 0 (research, critique) ran
  before the questions; the holistic review runs with the plan once the questions are answered.
- Delegated (D-072 (l)): the crunch's EDA / checks / charts catalogue (Opus, high); best practice
  with web sources (Opus, xhigh); the synthetic traps measured on the dev data and the oracle's
  shape (Sonnet, high); the package's interface sheet after Stage 1 (Sonnet, high). The main
  thread read every report in full; the design and the questions stayed on it.
- **Legacy survey** (`legacy/propensity_crunch/`): VIF, MI, univariate AUC, PSI and the
  summary all skipped categoricals (T10); every statistic ran after median imputation; the AUC
  existed twice (`feature_stats.py:65`, `leakage.py:21`); no cardinality statistic; lineage was
  a hand-typed list (T12); VIF silently dropped zero-variance columns, hiding T11; signal
  persistence used the OOT month's labels; every threshold a literal (0.95 leak, 0.03 AUC drop,
  0.25 PSI, 0.98 dominance, 0.5 missing, 0.9 correlation); charts with fixed 0–1 ranges and
  raw-count overlays (T16); bare `except` fallbacks in three chart functions; the card held a
  feature count only.
- **Trap survey** (measured on `data/01_raw/synthetic_dev`, 20k clients, cc-eligible rows):
  `leak` AUC 0.968 and 0.872 (oracle ceiling 0.844); `missing_leak` fill indicator 0.894;
  `shifted` 1.00 at `w = 1` but **0.70 at `w = 3`**; `process_leak` 0.90 at `w = 1`, **0.67 at
  `w = 3`** (98.7% zeros); `upstream_target` equals the target; `redundant` Spearman 0.99997
  with `relationship_days`; `high_cardinality` 300 levels; null controls 0.495–0.502;
  `near_constant` 99.9% zeros; `low_fill` 1.05% and 0.3%. Under `cc_flag = 0` eleven card
  columns are exactly constant and `cc_utilisation_ratio` all null (T11); `repayment_cc_vol`
  99.4% zero. The login drift starts 2026-01 (the latest synthetic period is 2026-09). The
  `unit` preset: 5k × 24 months, 125,709 rows, 16.8 s to generate. `truth.json` has no
  relevance ranking: the trap list (`spec.traps`, 33 entries; 20 trap columns) and the oracle's
  AUC per target and window are the acceptance material. An observation: `cc_acquisition`'s
  second analysis filter is a no-op after the first (`income IS NOT NULL` drops the exempt
  null-income clients), to look at with the config.
- **Interface survey**: nothing tells numeric from categorical; `run` passes raw configs, writes
  no resolved config and no stage artifacts; `period` reaches pandas as `datetime.date`; no
  gap / latest-period helper; `features.excluded` validated, not applied (by design: EDA and
  Feature Checks see the candidates); `flag`, `dropped`, `run`, `sign_off` exist in `Op` with
  no writer; the audit log and the model input are local only (`://` refused).
- **Best-practice survey** (web, verified where stated). Ranking: AUC's null SE is
  √((n₊+n₋+1)/(12 n₊ n₋)) ≈ 1/√(12·n₊) (Hanley–McNeil 1982; simulation at 800 events: 0.0105 vs
  the lesson's 0.0177), **so `lessons.md`'s 0.5/√events is 1.7× too conservative**; IV bands
  (Siddiqi) depend on the binning; MI's failure in the crunch was probably the kNN estimator.
  Regression: Kendall τ-b / Harrell's C generalise AUC; scipy's τ is O(n log n). Leakage: no
  numeric thresholds in the primary sources (Kaufman et al. 2012; Kapoor & Narayanan 2023);
  DataRobot flags at 0.85 and removes at 0.975; no published backward check (the nearest
  analogue: negative-control outcomes, Lipsitch 2010). Drift: the PSI bands are Lewis's 1994
  constants, blind to n and bins (n·PSI ~ χ²; Yurdakul 2018, du Pisanie 2023); JS distance is
  the bounded alternative; at 50 events a per-period AUC range of ≈ 0.10 arises from noise
  alone. Redundancy: |ρ| ≥ 0.9 (ydata, caret); VIF 5/10 don't justify dropping (O'Brien 2007).
  Quality: drop above 95% missing (scorecardpy); near-constant rules are scale-free (caret
  95/5); ydata warns above 50 levels. Low prevalence: Wilson via `binomtest(...).proportion_ci`
  (verified, scipy 1.16.2); no standard minimum per bin (half-width ≈ 1.96/√k); SMD 0.1 / 0.25
  (Austin 2009). Report: plotly.js 3.1.1 is 4.83 MB; fragments 7.6 KB (20 bars) to 1.37 MB
  (100k raw points), so charts are pre-aggregated; 8–16 WebGL contexts per page; Styler needs
  jinja2, **absent from the local venv** (to pin, D-012); kaleido needs a browser. Ledger: no
  per-feature audit schema exists; SR 11-7 asks for evidence and traceability.
- **The questions**, `worknotes/m2_2_understanding/questions.md` (959 lines): section 0 is the
  explicit catalogue (what Stage 2 builds per component, what waits, what is deliberately not
  built); A scope and time (7–8 days instead of 4; regression real on a variant config); B the
  shape (`statistics.py`, `eda/`, `feature_checks/`, `ledger.py`, `reporting/`,
  `artifacts.py`; stage functions resolve the config themselves; one `StageResult`; artifacts
  under `04_feature/<uc>/<entity>/<ddh>/{eda,feature_checks}/` with the ledger at the hash
  level; column kinds from the Spark schema); C the statistics (one **concordance** scale for
  both tasks: AUC / Kendall; shrunk level encoding for categoricals; missingness never imputed;
  Wilson intervals; `strata.min_events` for strata and periods, 20 events for bins; PSI with a
  null bin); D EDA's views one by one (choices block and warnings, headline, funnel, target per
  period / stratum, label-free reference groups with SMDs, the ranking table, deep dives, strata
  pivots, chart sampling, `pivot_target`); E Feature Checks' steps and findings one by one with
  low defaults (`quality`: all_null, constant, near_constant 0.99, high_missing 0.95,
  high_cardinality 50, unsupported_type; `leakage`: too_strong 0.80, missingness_leak 0.60,
  rare_value_leak lift 5; `time_alignment`: a **lag check** instead of D-029 (d)'s backward
  label, which is degenerate under a precondition eligibility; `stability`: Cochran's Q on the
  per-period concordances, PSI 0.10 within the window, against the gap periods and the latest
  period, new levels; `redundancy`: Spearman 0.90, Cramér's V 0.90; `eligibility_constant`
  folds into quality); every finding a flag, only lineage a rule exclude, idempotent rule
  entries, `open_flags`, proposed decisions, Feature Checks requiring EDA's artifact; F the
  ledger (wide, per data definition, `ledger_schema_version` 1, decisions joined at render); G
  reporting (the writer, chart primitives, no cap with pre-aggregated figures, neutral theme,
  two reports); H notebooks, the trap acceptance mapping, period labels, strata validation, no
  `exclude_labels` field. Twelve assumptions and the facts still to check close it.
- Files: `worknotes/m2_2_understanding/questions.md` (new), `worknotes/README.md` (two stage
  folders for now), `docs/UPDATES.md` (status rows, a log line).
- Decisions / open decisions: none settled; D-134 onward once answered. Touches OD-11, OD-12.
- Still open: every question; the plan follows the answers, with the routing plan and the
  holistic review. Sequencing: the other chat scheduled the synthetic to-do (extra feature
  tables, mistake tests) and per-source key names before EDA's build; both are dataset and
  synthetic files, disjoint from Stage 2's, so they can run beside it (Q419).

### 2026-10-30 — Integration news: data observability narrowed, feature store leaning, synthetic to-do
- The SDS's news, routed by firmness:
  - **Data observability (firm, "pretty much sure"):** it is a Great Expectations-style suite of
    data checks on production (maybe sandpit) tables. The framework's only contact: every deploy
    points the model's source tables at it. Recorded: D-021 (b) replaced in place; D-040 and
    D-079 lose the monitoring feed; OD-13 narrowed to tooling; the Chief DS topic became an
    information item; the learn session is no longer needed before M3.
  - **Feature store (a leaning, an update may follow):** little build outside the bank; the SDS
    adds an example notebook inside the bank that loads features, applies the format fixes and
    saves a dataset that Target Factory joins like any other source. Recorded in OD-26; D-021 (a)
    marked under review. The config comments and the refused `feature_store` format stay until
    the update.
  - **Synthetic to-do:** small feature tables so the primary example merges two feature sources,
    and mistake tests for the guardrails (`test_harness.md` → To-do).
- Critique (also in the reply):
  - Data observability: a real saving (no work stream, no monitoring-table dependency before
    M3). It doesn't replace monitoring's drift layer: its checks see source tables, not the
    model's inputs against the training reference.
  - Feature store notebook: three risks. (i) Point in time: it must write one row per unit per
    period holding the values as of that period; today's values stamped on history are
    look-ahead that no Stage 1 check can see (§4.1). (ii) Production: inference reads the
    sources each scored period, so the extract needs a refresh job with the same fixes; a
    notebook can't be in the production path (§3, §4.9). (iii) Reproducibility: the hashes see
    logical names, not contents, so an extract overwritten under the same name changes a model
    silently (§4.10).
- Guardrail inventory for the to-do (a subagent read the code, the main thread checked the key
  lines). A joined feature source gets no period-coverage check: only the spine
  (`dataset/panel.py:146`) and the target source (`target_factory.py:112`) do, so a source that
  ends before the validation period leaves its features null there without a message. The
  column-clash check (`panel.py:205`) is case-sensitive, while Spark isn't. Padded ids only lower
  the matched share. A weekly table on a monthly spine fails as "duplicate keys" without naming
  the period. `dataset.md` claimed that the join log prints distinct units per period; it prints
  the matched share and logs matched rows per period (fixed).
- Files: `docs/decisions.md` (D-021, D-040, D-079), `docs/roadmap.md` (verdict, backlog, OD-13,
  OD-26, CDS topics), `docs/components/monitoring.md`, `lifecycle.md`, `test_harness.md` (To-do),
  `dataset.md` (join print), `docs/architecture.md`, `docs/context/project.md`,
  `docs/glossary.md`, `docs/UPDATES.md`, `CLAUDE.md` (integrations line),
  `worknotes/timeline_proposal.md`.
- Then (the SDS's answers, 2026-10-30): Q411, Q413 kept; Q412 `deploy` prints and records the
  physical source tables (D-021 (b), `lifecycle.md`); Q414 the extract written by an upstream
  job, else a framework function (OD-26 (ii)); Q417 the to-do's table and timing (after Stage
  1's sign-off, before EDA). Q416: close the gaps after Q415, but no coverage check on joined
  sources: missing clients or periods are fine, the left join leaves nulls (`dataset.md`); left
  to fix: the case-insensitive clash check, the weekly-on-monthly hint. Q415 became a question
  back: what per-source key names cost (the spine keeps `data.keys`, another source may name
  its own, the list taking `{source, keys}`); estimated in the chat (`dataset.md` → Open
  questions).
- Then built (the SDS accepted Q415: "build all above as needed"), in parallel:
  - per-source key names (`SourceKeys`, `SourceEntry`; `sources.source_name`, `source_keys`,
    `feature_source_names`, `feature_sources_dump`; `read_keyed_source` takes the entry); a
    plain-name config's hashes and sidecar unchanged (the old example digest is reproduced by
    its plain-name variant, pinned in `test_identities.py`); the column-clash check ignoring
    case; the finer-period hint, with a new tag `first and last days` so `other days` means a
    day that is neither (code review);
  - synthetic 0.5.3: `fs_extract` (keys `customer_no` as a string, `as_of_date`; 85% of the
    clients; six trait proxies; `holding_cnt_trap_lookahead`, kind `lookahead`) with its own
    check family (all rows pass at 5k and 20k); the mart, oracle and holdings byte-identical to
    0.5.2 at seed 0 (hashed before and after);
  - `tests/test_source_mistakes.py`: 12 tests, one per planted mistake; every guardrail behaved
    as documented;
  - wiring: both example configs join the extract; the environment example, `conf/local` and
    the test fixtures map it; the dev dataset regenerated at 0.5.3 (72 s, 1.2 GB peak); notebook
    01's cells run on it (41 s; `cc_acquisition` 116,998 window rows, 64% eligible, 161
    candidates, the extract's columns among them).
- Reviews: code (two blockers fixed: the mixed-tag hint, a long line; simplifications taken),
  compatibility (safe; two stale signature lines and three doc notes fixed), silent failures
  (empty names refused at load, the keys read logged and printed, `targets: ""` no longer falls
  back to the spine, a level-values rule row, case-insensitive duplicate sources), ML audit
  (safe; taken: a joined source's missing periods printed by name, a target source keyed as its
  feature entry, the spine's key names read as `source_<name>` in an own-keyed source; parked:
  inference on a lagging extract → `inference.md`, a target lag check → `target_factory.md`;
  for M2.2: the look-ahead trap needs a tell in Feature Checks; a survival-coded coverage trap
  deferred).
- Then (the SDS, 2026-11-02): Q463 notebook 00 is not re-run (the EDA notebook replaces it in
  M2.2); Q464 the version goes to 0.3.0 at Stage 1's sign-off; Q465 (a): the SDS carries the
  look-ahead finding to the Stage 2 chat.
- A slip of mine: the mistake-test brief's wait loop (`pgrep -f pytest`) matched its own shell,
  so the agent waited about an hour; stopped and re-briefed.
- Decisions / open decisions: D-021 (b) replaced and extended, (a) under review; D-040, D-079
  extended; D-129 extended (per-source keys); OD-13 narrowed; OD-26 leaning.

### 2026-10-29 — New working rules: Fable routing, the LDS's reading, stage folders, targeted tests
- The SDS set four generic rules: (1) on a Fable session, a major task starts with a routing plan
  (each subagent piece's agent, model, effort and why) so the tokens don't all go to Fable; strong
  subagent pieces now run on Opus, Fable keeps the main thread and the ML-correctness auditor
  (the SDS, Q409); (2) the LDS reads the important
  parts of the code, not all of it, and tries the functionality and the notebooks; (3) a stage's
  worknotes folder is written for the SDS, an LDS review only on request; (4) small, targeted
  fixes run the touched modules' tests only; the full suite runs once, on the main thread, when a
  major step or a multi-module build is finished, and never per agent.
- Why: Fable sessions spent nearly every token on Fable; the LDS's 30–60 minutes are better spent
  on the logic that matters and on trying things; the full suite (about 5 minutes) on every small
  fix cost more time than it caught.
- Files: `CLAUDE.md` §1 (parallel bullets, rule 13, workflow step 2) and §9 (roles);
  `.claude/skills/delegation/SKILL.md` (§3 strong = Opus, the routing plan; §4–§6 tests;
  anti-patterns); `.claude/agents/code-reviewer.md` (own tests only);
  `.claude/skills/verification-before-completion/SKILL.md`; `.claude/commands/brief.md` and the
  sync template ("Demo next" becomes "To try"); `worknotes/README.md`;
  `docs/guides/claude_code_workflow.md`; `worknotes/timeline_proposal.md`. The live sync page
  was left as it was.
- Then (Q410, the SDS): `sync.md` is refreshed only by `/brief` or on request; `log.md`
  keeps the every-turn trigger (`CLAUDE.md` §1 step 4 and §8, `doc-sync`, `worknotes/README.md`).
- Decisions / open decisions: D-072 (i) replaced, (l) and (m) added, (h) extended.

### 2026-10-29 — Questions answered; source column names; the name rule; two example use cases
- 2026-10-29, the SDS's second message: Q407 relax the name rule; the Target Factory notebook
  must show several targets ("that was the main point"): a second config for another product;
  then clean the worknotes folder of stale notes and drain the sync page's review list to the
  one real to-do, starting the Stage 1 review.
- Code: `config/schema.py` (`USE_CASE_PATTERN` letters, digits, `_`, `-`, any case; the
  `product` / `activity` properties removed, D-128 replaced), `dataset/panel.py` (use cases
  sharing a model input differ ignoring case; a target join line names its use case),
  `dataset/contract.py` (the eligible-rows line prints its period count), `conf/base/
  td_acquisition.yml` (new: term deposit, `analysis: []`, `non_holders` on `td_flag`), the
  shared model input renamed `retail_acquisition_input` (both configs, the environment files,
  the test fixtures), the notebook (two configs: summaries, one save, the target columns, a
  per-use-case frame comparison). Notebook on the dev data: one table with
  `target_cc_acquisition` and `target_td_acquisition`; `cc_acquisition` 116,998 window rows,
  64% eligible, target mean 0.028; `td_acquisition` 124,484 rows, 94% eligible, 0.009.
- Worknotes cleaned: deleted `decisions_LDS_review.md`, `pickle_summary.md` (its six costs and
  the open Q297–Q299 moved to `lifecycle.md` → Open questions first), `handovers/
  synthetic_build.md` (its trap-to-step mapping moved to `test_harness.md`), and the stage
  folder's `questions.md`, `plan.md`, `addendum_spec.md`, `review_answers.md` (all answered
  or built; the split explanations folded into `review_guide.md`, which now stands alone).
  Kept `timeline_proposal.md`: the only home of the Phase 2 plan's detail (OD-01). References
  fixed in `README.md`, `roadmap.md`, `UPDATES.md`, `decisions.md` (D-051), `sync.md`. The
  sync page's review list drained to the Stage 1 item, which names the functions carrying the
  ML logic (the peer session's new D-072 (i)).
- Reviews of the afternoon's change: code review (approve; the notebook's income wording, a
  memory note for several large use cases, a per-config `time` print, the contract line's
  number, a hyphenated mixed-case name through Spark, the validator's docstring) and
  compatibility review (no break, no version bump; but "any case" reached case-insensitive
  places: the audit log folder on macOS and the target-column collision check). Fixed by
  treating the name case-insensitively, as written in configs but lower-cased wherever it
  becomes a folder or a column, starting with a letter or digit (D-128); reserved source
  column names matched ignoring case (`Target` read as `source_Target`); the contract line's
  `min_rows`. Full suite before the fix pass: 280 passed, 5 min 45 s; after it: 286 passed,
  5 min 13 s; ruff clean. A hyphenated target column round-trips through partitioned parquet
  (checked by hand). The notebook on the dev data: 34 s; one earlier run failed on the first
  frame collect with a Spark execution error right after another local Spark session, and
  passed alone; the cause is not pinned.
- The SDS's seven points: the sidecar sentence (explained: the schema number stayed 3 after two
  keys were added on 10-28, since no earlier schema-3 file survives), the window written
  `2025-03-01 … 2025-08-31` (fine; checked by loading it), `task` in the hashes (binary or
  regression, not the use case), `revert` 14 → 8 then 15, 16 (effective 1–8, 15, 16; checked in
  code), source columns named `target`, `split`, `eligible` (the reader served every source, so
  "the latter": handle it), missing periods (a Phase 3 wish), the use case's naming rule (no
  programmatic reason today; Q407 opened, default relax). Recorded in `review_answers.md`, now
  holding this round plus the earlier explanations the review guide points to.
- Code (one builder, then three reviewers, then a fix pass by the same builder):
  `sources.py` (`rename_reserved`; a non-key `unit_id`/`period` read as `source_<name>`, checked
  against every column, keys included; no refusal for `target`, `split`, `eligible`; the source
  log's `renamed`), `dataset/panel.py` (`read_side_columns(columns, targets, use_case,
  features)`: an upstream label, own or another use case's, dropped only when its target source
  is a feature source; a remaining `target`, `split`, `eligible` read as `source_<name>`; the
  lineage under its read names; one `drop` and one `rename` log entry, printed; the join entry
  carries `renamed`; decision names that are framework names refused), `model_input.py`
  (`saved_candidates` and `save_model_input` run the same plan; a clash fails at save),
  `target_factory.py` (a key name in `data.target.column` or `lineage` refused with the hint),
  `eligibility.py` (the error names the `source_<name>` convention).
- Reviews: code review (approve; the renames' two kinds separated in the log, the lineage's read
  names in the meta, the save-side check, tests), silent-failure audit (a label dropped by name
  when it came from a separate target source; key renames missing the lineage; decision names
  that silently missed; a key collision; the join log), ML audit (one §4.6 gap: a lineage entry
  `period` reserving the key while `source_period` stayed a candidate; the rest verified). All
  fixed. Not taken: storing the read-side plan in the meta for inference (the bundle's feature
  list suffices; inference is built in M2.4); the candidate list depending on which use cases
  share a table (an open question in `dataset.md`, decided with Feature Checks); `strata`
  naming a framework column (an open question in `eda.md`).
- Tests: a pure parametrised `read_side_columns` test (ten cases), the printouts, the refusals,
  the built target over `target`, the own upstream `target`, `saved_candidates` on both.
  Full suite: 273 passed, 1 failed (the template test read `source_<name>` in a new comment as
  an unfilled placeholder; the comment reworded, `test_config_schema.py` rerun: 38 passed);
  ruff clean; the notebook on the dev data in 27 s.
- Docs: D-129 extended; `dataset.md`, `target_factory.md`, `config.md`, `architecture.md`, the
  template; `roadmap.md` Phase 3 wishlist (missing periods); `eda.md` and `dataset.md` open
  questions; `UPDATES.md` dataset row; `review_guide.md` (status, reading order, what "right"
  looks like, the 10-29 round).

### 2026-10-28 — The Stage 1 addendum: periods, one model input for several use cases, revert
- The SDS's third round accepted everything (the hash answer; Q400 as reworked; Q405
  `target_<use_case>`; Q406 one shape) and asked for the build with subagents and one continuous
  review guide, noting that the Q401/Q403 proposals had been shortened out of the worknotes
  (lesson recorded: a to-do keeps its full proposal). `addendum_spec.md` written as the one spec
  (A periods, B the shared model input, C revert, the id cast); five builders on disjoint files
  in two waves, then four reviewers on the merged state, then four fixers.
- Code: `periods.py` (new: `Period`, `PERIODS` for month, week, day: index, inverse, start, end,
  in Python and Spark, label, typo rule; `label_by_period`, `period_labels`); `sources.py`
  (`unit_id`, `period` at the period's end, `unit_id` cast to string, `KEYS` and
  `HELPER_COLUMNS` owned here, a reserved column name refused, the log's `periods`,
  `period_tag`, `id_type`; `missing_periods`, `check_periods_covered`); `schema.py` (`Keys.period`,
  `Time.period`, `observation_window`, `target_window`, `validation_period`; the typo rule and
  the end move per period; `v ≥ tk + w` by index); `identities.py` (`task`, `period`,
  `observation_window`, `target_window` in the hashes; digests re-pinned); `target_factory.py`
  and `tasks.py` (the forward window over the period index; `null_in_window` null where the
  window is incomplete; summaries per period); `dataset/panel.py` (`load_panel(cfgs)`: the
  shared-definition check, the sources joined once, each target as `target_<use_case>`, one
  rollup for the join log and the null shares, a feature source matching nothing refused;
  `prepare_panel`: the own target kept, the other use cases' targets and upstream columns
  dropped, eligibility, candidates, contract, split; `build_panel` = both; `JoinedSource`);
  `dataset/eligibility.py` (new: the two lists, the SQL guard, the candidates);
  `dataset/contract.py` (the null callout fed by the saved share, its population named);
  `dataset/model_input.py` (schema 3; `save_model_input(cfgs | cfg)`; the refusal order: schema,
  hash version, sources/keys/period, the use case, its target spec, the periods, the target
  source's reach; `saved_candidates` without Spark); `dataset/frames.py`, `split.py` (period);
  `run.py` and `__main__.py` (several config paths, one save; entity lists must agree;
  `decide --revert-to`); `replay.py` and `audit_log.py` (`revert`: `to_seq`, the replay and the
  origins restart from the slice, the header line, `record_decision(revert_to=)`; `include`
  judged over the effective entries).
- Tests: the week and day moves and index round trips, the id cast, the reserved column, the
  old field names refused; the weekly and daily forward windows; two configs → two target
  columns, the other target and upstream column never a candidate, the shared-field refusals,
  the collision, a feature source matching nothing; read-side: a changed eligibility not
  refused, a changed target spec, a missing use case, schema 2, uncovered periods and an
  outrun target source refused; the weekly end-to-end frames; `run([a, b])`; the revert example
  and its refusals; `task` moving both hashes. Full suite 252 passed, 9 deselected, 4 min 56 s; ruff clean; the notebook
  on the dev data in 30 s (sidecar schema 3); the two-config CLI save and read-back checked.
- Docs: D-088, D-125, D-129, D-131 extended; `config.md`, `dataset.md`, `target_factory.md`,
  `architecture.md`, `glossary.md`, `lessons.md` (T19 reworded, T22), the template and the
  example config, the notebook's text, CLAUDE.md §4 in periods; "period" through every
  component doc; `UPDATES.md`; `roadmap.md`'s addendum item removed; `review_guide.md` rewritten
  as one continuous guide; `review_answers.md` third round.

### 2026-10-28 — The SDS's review of Stage 1's steps 2 and 3, applied
- 2026-10-28, the SDS's remarks (`worknotes/m2_1_foundation/review_answers.md`, one row per
  remark): Q395–Q398 at their defaults; Q399 refused ("the Target Factory must produce the labels
  for the whole time window"; the framework doesn't police a DS); `null_as` and `leavers`
  questioned; the two month-coverage functions questioned; `split.py` to be explained;
  eligibility as two lists with the second before Feature Checks; the month anchoring to become
  a parameter; the template's comments to follow one rule; a list of configs for Target Factory;
  the univariate ranking's population; two audit-log usability questions.
- Code: `schema.py` (`Eligibility` with `analysis` and `modelling` lists, names unique across
  both; `EligibilityStep` without `before`; `Target` without `null_as` and `leavers`),
  `panel.py` (`apply_eligibility(panel, eligibility)` runs the two lists as one order, the log
  entry's `kind`; `modelling_tags`; `build_panel` keeps every label), `sources.py`
  (`check_months_covered(log, first, last, role, until)`, the one check behind the spine's
  `first … v` and the target source's `first … v + w`; `month_from_number`),
  `target_factory.py` (no null or leaver handling; the coverage check shared),
  `tasks.py` and `contract.py` (the column checks without `null_as`; the callout fires above 0
  and points upstream), `split.py` (rewritten around `_hash_uniform(columns, salt, seed)`, one
  draw in [0, 1) compared with the share; one `RESOLUTION` constant), `frames.py`
  (`feature_checks` gets the window's eligible rows), the template (the comment rule in the
  reading key: short inline, long above the key, level lines inline; the ordered-sources and
  duplicate-key note; every line under 100 characters) and the example config.
- Tests: the schema's eligibility tests (two lists, names unique across both, the defaults), the
  Target Factory series without the `null_as` cases (six), `test_dataset.py` (the two lists, a
  define in `analysis` serving a `modelling` filter), the contract's callout, `test_frames.py`
  (the analysis step logged first; Feature Checks' frame is the eligible window; the model input
  labelled in every month but the last w), the golden digests re-pinned (`HASH_VERSION` 1).
- Docs: `config.md`, `dataset.md`, `target_factory.md`, `eda.md` (the ranking on the eligible
  rows of the one frame), `feature_checks.md` (the eligible population; `eligibility_constant`
  may fold into `quality`), `glossary.md`, D-029, D-030, D-129, D-131, `CLAUDE.md` §4.4, the
  notebook's guide cell, `UPDATES.md`, the roadmap backlog (the Stage 1 addendum), the plan's
  status; `review_guide.md` → Major steps 2 and 3 rewritten for the LDS (the reviewers' findings
  condensed); `review_answers.md` holds this round only.
- Open with the SDS (`review_answers.md`): Q400 one model input for several use cases (the list
  form of the two public functions, one block of columns per use case), Q401 the unit of
  analysis as a parameter (`time.period`, the key column `period`, the `time` fields renamed),
  Q402 the list names, Q403 a `revert` operation in the audit log, Q404 the summary's display
  rule. Q400 and Q401 are proposed as a Stage 1 addendum before M2.2.
- Reviews (three in parallel on the diff, read-only, while a doc agent synced the owner docs):
  code review 2 blocking (the docs, which the agent was syncing; one order test), 6
  suggestions; ML audit safe, 2 should-fix, 2 hardening; compat review: every 0.x break named,
  the sidecar's `schema_version` to 2. Taken on the main thread: `MODEL_INPUT_SCHEMA_VERSION`
  2 with the refusal naming the framework version; `_modelling_rows` restricts its months
  itself; a non-deterministic function refused in eligibility SQL (`UNSAFE_SQL`); the upstream
  tail's `before_tail` by month number; the `KINDS` indirection dropped; the coverage message
  with both dates; the Feature Checks collect entry named `eligible_window`, its own fixture and
  test; the template's `gate_metric` comment restored; tests added: an analysis step cannot use
  a modelling define, a define is never a tag, non-deterministic SQL, the modelling months
  inside the window, a labelled gap-month row never counted by the contract, the pinned hash
  draw with the boundary agreement over 200k ids, `month_from_number` round trips and a
  year-end crossing. Deferred: `label_free_months` for Feature Checks (M2.2, F3);
  `negative_downsampling`'s per-row check (a test idea, not a bug). Version kept at 0.2.0.
- Verified: `ruff check .` clean, every file formatted; the full suite 202 passed, 9 slow
  deselected, in 4 min 21 s before the reviews' fixes and 208 passed in 5 min 33 s after them
  (one run in between failed on a stale test regex for the reworded refusal, fixed); the
  notebook's code cells as a script on the `dev` dataset in 32 s, and again
  in 27 s after the sidecar bump (the analysis filter drops 6% before EDA, 64% tagged
  non-holders, the model input saved at `schema_version` 2, the window frame 116,998 rows ×
  160 columns, ≈ 0.47 GB at the peak).

- 2026-10-28, the SDS's second round (no code changed, as asked): Q401 approved as proposed,
  Q402 and Q404 at their defaults, Q403's `revert` approved for M2.2; Q400 pushed back ("one
  loop through the configs, add every target to the merged frame, filter nothing, save one
  table every config refers to") and reworked to that shape: Target Factory builds the sources
  joined plus one target column per use case; eligibility, candidates, contract and split move
  to the read side (`build_frames`), the data-definition hash leaves the sidecar (schema 3
  proposed), D-125's freeze point narrows to the data part; Q405 (the target column's name) and
  Q406 (one shape for a single config too) open. The follow-up on the split's hash answered
  with a scratchpad check on 100,000 structured ids (segment, age block, counter): the test
  share per segment and per age block within binomial noise, lag-1 autocorrelation about 0,
  chi-square over 100 bins 94 and 102 (expected 99 ± 14); found on the way: the id's type
  changes the draw (string vs long), so `unit_id` is to be cast to string at load. Recorded in
  `review_answers.md` (the hash check, Q400 reworked, the to-do list), `sync.md` and the
  roadmap's addendum item.
### 2026-10-27 — Stage 1, major step 3 built: the dataset, `run`, the notebook (version 0.2.0)
- 2026-10-27, the SDS: build step 3 now and review steps 2 and 3 together; the review guide
  combines both. Built on the main thread (the pieces depend on each other; one Spark job at a
  time on the 8 GB machine), the four reviews delegated in parallel.
- Code: `dataset/panel.py` (`load_panel`: every source through `read_keyed_source`, the spine
  checked for `first … v`, the other feature sources and the targets left-joined with a marker
  each, months from the window's first to the spine's last, one rollup for the join log and the
  window-month-without-target refusal; `apply_eligibility`: a define reused and dropped, a
  `before: eda` filter dropping with rows per month, a `before: model` filter tagging 0/1,
  `eligible`, a condition resolved against the sources' columns and earlier defines only, boolean
  required; `resolve_candidates`), `dataset/split.py` (`assign_split`, `sample_train` with the
  two options, the hashes salted `'split'` / `'sample'`, T20), `dataset/contract.py`
  (`check_contract`: unique keys, the task's checks, the null callout), `tasks.py`
  (`contract_checks` per task: both classes and the rate band; a finite, non-constant amount),
  `dataset/frames.py` (`Frames`, `build_frames` for the four stages, `_modelling_rows` with the
  null-target share per month, `estimate_collect`, `collect_frame` with the printout and the
  callout, `save_model_input` partitioned by month with `_model_input.json`, T21;
  `read_model_input_metadata` refusing another definition, split, schema or hash version;
  `saved_candidates` for the audit log), `run.py` (`STAGES`, `run`), `__main__.py` (`run`),
  `schema.py` (`negative_downsampling` needs a binary task), `audit_log.py` (a feature decision
  checked against the saved model input's candidates, else the patterns, saying so),
  `sources.py` (`month_number` shared), `notebooks/01_target_factory.ipynb`, version 0.2.0.
- Tests: `test_dataset.py` (the join and its log, a shared column, a spine gap, a target source
  matching nothing, replayed names, every eligibility rule, the candidates), `test_split.py`
  (by client, stable, near the share; the positives kept; whole clients at the share with equal
  seeds; the identity), `test_contract.py` (each refusal with its numbers, ineligible rows never
  counted, the callout), `test_frames.py` (end to end on the unit preset: the window, the
  modelling frames, the model input round trip equal to the in-memory frames, the stale-input
  refusals, the callout, regression with client sampling), `test_run.py` (the CLI run, the
  notebook's imports), a schema test; `conftest.py` gained `variant` and `write_sources`.
- Timings on the unit preset: the window frame 12 s, the modelling frames 7 s, the model input
  saved 5 s, read back 2 s; the new tests 60 passed in 86 s.
- Docs: `dataset.md` (status, requirements 1, 3, 9, the model input, the frames' meta, the
  Interface, two open questions), `target_factory.md`, `run_modes.md` (status, Interface),
  `environment.md` (`load_environment` public; the model input's path local until M2.4),
  `config.md` (status; the feature decisions' check), `architecture.md` (Public API rows),
  `glossary.md`, D-131, `data/README.md`, `lessons.md` (T20, T21), `notebooks/README.md`,
  `docs/README.md`, `UPDATES.md`, the roadmap's M2 row; `review_guide.md` (one reading order
  for steps 2 and 3, the deviations), `review_answers.md` (step 2's table kept; Q395–Q398), the
  plan's status and timeline.
- Reviews (four in parallel, read-only while the suite ran): code review (strong, high)
  approved, 11 suggestions; silent-failure audit (strong, high) 2 high, 5 medium; compat review
  (strong, high) non-breaking, 7 items; ML audit (strong, xhigh) safe, 1 medium, hardening. The
  fix pass on the main thread, every item re-tested (`review_guide.md` → Reviewers' findings,
  step 3): the model input's folder rewritten whole instead of a dynamic partition overwrite
  that left stale months; a missing model-input mapping fails loud and the pattern-check
  fallback says why; `split` / `eligible` refused as step names; a star in a call, a subquery
  and a window function refused in eligibility SQL; labels nulled outside the window and the
  validation month (Q399); months without eligible rows refused by the contract; null
  conditions counted per month; `step: eligibility` + `name` in the log; the split compared in
  JSON mode and `month` cast on read; the artifact inventory (D-007 (d)) in `architecture.md`;
  `dataset/model_input.py` split out of `frames.py`; `missing_months` shared; the smaller items.
  Justified: the notebook's repo-derived path (an editable install; a use case writes its own);
  the contract not re-run on the read path (`dataset.md` → Open questions). Deferred: a sidecar
  migration hook (roadmap backlog).
- Verified before the reviews: `ruff check .` clean, every file formatted; the full suite 203
  passed, 9 slow deselected, in 4 min 4 s (one Spark job, nothing else running). After the fix
  pass: the affected files 99 passed, the panel tests 19 passed, then the full suite 207
  passed, 9 slow deselected, in 4 min 5 s. The notebook's code cells run
  as a script on the `dev` dataset through `conf/local/environment.yml` in 32 s: the summary,
  the join and eligibility lines (64% non-holders tagged, 6% dropped before EDA), the model
  input saved under `data/05_model_input/`, the window frame 116,998 rows × 160 columns
  (≈ 0.47 GB at the peak against the 1.5 GB budget).

### 2026-10-27 — Stage 1, major step 2 reworked after the SDS's review: the rule, nulls, two kinds of eligibility
- 2026-10-27, the SDS's answers: eligibility filters split into pre-EDA (rows dropped) and
  pre-model (rows tagged; the tag columns serve as strata, e.g. holders vs non-holders), which
  answers Q394; the rule compares the current month with any forward month, so `[0, null, 1, 1]`
  is 1 and `[1, 0, 1, 1]` is 0; Q392 yes, named `flag_goes_up`, with count and amount rules kept
  separate; Q393 (A); `review_answers.md` holds the current review only, never a growing history
  (saved as a memory rule).
- Code (one agent, strong, high; the main thread read the diff): `flag_goes_up` =
  `max(forward) > value at t` cast to int (SQL null semantics; a holder at t gets 0);
  `forward_sum` = the sum of the known values; `data.target.null_as` (coalesced in the column's
  type, so a boolean flag works too; refused without a rule, and for a flag unless 0 or 1);
  `build_targets` returns `null_in_window` as a fourth column and the summary shows
  `null_value_share`; `EligibilityStep.before: eda | model` (a filter needs it, a define takes
  none); `cc_acquisition.yml` shows one filter of each kind; the template explains both and
  `null_as`; golden digests re-pinned (both change: eligibility and target gained fields). Tests:
  one parametrized test over the SDS's series, forward_sum with nulls, the refusals, a hand-made
  summary with `null_value_share` ≠ `null_share`, three schema tests; the precondition and
  strict-null tests removed. The oracle comparison holds on the non-holders (`cc_flag == 0`).
- Docs on the main thread: `config.md` (layout, requirement 6: the two kinds), `dataset.md`
  (purpose, frames, model input, requirement 1), `eda.md` (funnel, reference groups), the
  glossary, `target_factory.md` (requirements 3 and 5, Interface), D-029 (c), D-129, D-131,
  `UPDATES.md`, the plan (3.1 `apply_eligibility` tags or drops; 3.3 on `eligible = 1`; 3.4
  frames; the precondition items removed), `review_guide.md` (reverted findings, the SDS's
  review), `review_answers.md` rewritten to the current review.
- Verified: full suite 163 passed, 9 deselected (3 min 14 s), `ruff check .` clean. Code review
  (strong, high): approved; four suggestions taken (the unused `w` dropped from the rule
  signature; `null_as` cast only for a boolean column, numerics widen, with a test; the window
  count named; the `null_as` wording and the printed caption). After them: Target Factory, schema
  and code-rule tests 67 passed.
- ML audit of the rework (strong, high): safe, nothing blocking; every invariant traced through
  the eight series and the oracle. Taken: an upstream target built with a longer window than `w`
  passed the tail check (the month before the tail must now hold a value, with a test); the
  `null_in_window` docstring (false for incomplete windows). Into the plan (step 3): eligibility
  SQL may reference source columns and define names only; both kinds applied to the validation
  month; tags and helper columns out of the candidates; join misses logged; a contract callout
  when `null_value_share` > 0 without `null_as` (would-be negatives dropped as nulls). For M2.2:
  the time-alignment screen on define and tag columns (`feature_checks.md`), a label-free
  comparison for a tag that is the rule's precondition (`eda.md`). The SDS committed the rework
  as `81df5dd` before these last edits.
- Verified after the ML audit's guard: Target Factory and code-rule tests 37 passed, `ruff check .`
  clean, every file formatted.
