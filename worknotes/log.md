# Log
Verbose trail behind `worknotes/sync.md`, newest first. Updates on the same topic from the same or
neighbouring days share one entry, each keeping its date. Template and rules: `worknotes/README.md`.

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
