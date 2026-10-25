# Synthetic data: the LDS's to-dos and the credit-card run-through
_Written 2026-10-25 for the SDS · Q379–Q386, each with a proposed default; cited decisions are
summarised in brackets (D-072 (k)) · its own file, apart from the Stage 1 questions
(`m2_1_foundation/questions.md`), whose major step 2 it amends · outcomes go to `docs/` and the
Stage 1 plan; the file is deleted once they have landed_

**Trigger.** The LDS's notes on the synthetic data (noise columns of several kinds; very low fill
rates; every such column named like the traps), and the fact that the first target build and
run-through is credit-card acquisition (Stage 1, Q351).

**How to answer.** By number; "default" accepts the proposal; "all defaults except …" works.

**Status (2026-10-25).** Q379–Q386 answered by the SDS: defaults throughout, except Q380 (the LDS
meant a *constant* column; "informative on its own but redundant given others" stays as a second
definition, so the catalogue below changed: the noisy copy went, two constant columns and one
redundant column came in; ten columns in all) and Q386 (clarified in place: the mapping is a
test, the framework stays name-blind). Open: Q387, who builds minor step 2b and when; the build
starts on the SDS's go.

### Where the synthetic build stands
- `synthetic` 0.4.0, accepted by the LDS on 10-21 (M1 done): 147 columns, 100k × 24 months, 8
  check families (1,263 rows pass), the `unit` (5k) and `canonical` (100k) presets. The `dev`
  preset (20k, Q363) and the slim `holdings` table (Q352) are planned for this stage's
  major step 2.
- Trap columns on by default (10): two card leaks, the upstream card target, the loan process
  leak, the loan shifted column, three null controls (a lognormal amount, a zero-inflated count,
  a Zipf categorical), a near-constant flag and an all-null string. Off by default:
  `extra_{nnnn}_trap_weak` / `_trap_noise` (`--extra-columns N`) and the dirty switches.
- The LDS's to-dos are recorded already (`test_harness.md` → Future to-dos; the roadmap's
  backlog; the depth table puts them at release 1.0, "before Feature Checks goes deep").
- Against Feature Checks' Phase 2 requirements, what no column tests today **on the card use
  case**: missingness (no low-fill column), cardinality (no high-cardinality categorical), the
  missingness-pattern leak (req. 3), the time-alignment check and the process leak (both sit on
  the personal loan only, whose count-rise target is M4), and within-window stability (req. 6,
  Feature Checks deep, M4). Redundancy is covered by the collinear rollups and the identities;
  the ranking has null controls at 0.5 but no graded set in the default dataset.

### What changes (the proposal)
1. **Pull the to-dos forward** from M4 into Stage 1's major step 2, where the synthetic package
   is touched anyway (holdings table, `dev` preset): one version bump (0.4.0 → 0.5.0), one
   regeneration of `dev` and `canonical`, and M2.2's "the traps are flagged" covers them from the
   start.
2. The new columns are **on in every preset**: they exist to test the checks, so they must be in
   the dataset EDA and Feature Checks run on. The extras stay the scale switch.
3. **Every new column is a trap column**, `_trap_<kind>` (D-064 (planted columns carry a
   `_trap_<kind>` suffix; one trap summary lists every trap)). New kinds: `high_cardinality`,
   `constant`, `redundant`, `low_fill`, `missing_leak`; the random flag reuses `null_control`. The trap
   summary and `truth.json` list them.
4. **Card twins for the loan-only kinds.** The first run-through is the card only, so the two
   trap-column kinds that sit on the loan alone (shifted, process leak) get a card twin, and
   `cc_acquisition` meets every trap-column kind (D-064's intent: a test of either target meets
   every kind; the loan target needs M4's count-rise family).
5. **Existing columns stay byte-identical at the same seed:** the new persistent and monthly
   columns draw from a new `noise` stream appended to `STREAMS`, and the new look-ahead draws
   come after the existing ones in the `leaks` stream. Verified once in 2c by diffing the shared
   columns of the 0.4.0 and 0.5.0 canonical datasets.

### The catalogue
All trap columns (`trap_column` true), on in every preset. "Tests" names the framework check the
column is for (Feature Checks' Phase 2 requirements; EDA's ranking).

| # | Column | Kind | Construction | Tests | Expected |
|---|---|---|---|---|---|
| N1 | `marketing_consent_flag_trap_null_control` | null_control | persistent 0/1 per client, p = 0.4, independent of everything | the ranking on a binary feature | AUC ≈ 0.5 on every target |
| N2 | `referral_branch_code_trap_high_cardinality` | high_cardinality | persistent categorical, 300 Zipf levels (`BR001`…), independent of everything | cardinality (req. 2); the categorical encoder's rare and unseen levels → `__other__` (D-037); a target encoding fitted on train looks predictive on train | flagged for cardinality; held-out AUC ≈ 0.5 |
| C1 | `booking_country_trap_constant` | constant | the string `UAE` in every row (the LDS's "univariate": one value) | the quality check's constant case (req. 2); a one-level categorical through the encoder | flagged constant; kept out of every correlation view |
| C2 | `statement_cycle_days_trap_constant` | constant | the integer 30 in every row | the same for a numeric: zero variance in standardisation, correlation and VIF | flagged constant; no NaN or crash downstream |
| R1 | `relationship_months_trap_redundant` | redundant | `floor(relationship_days / 30.44)`: informative on its own, nothing given its source (the SDS's second definition) | redundancy (req. 7) with both AUCs side by side; the ranking | AUC for `cc_acquire` within 0.01 of `relationship_days`' (the onboarding wave); rank correlation above 0.99; flagged as a pair |
| L1 | `loyalty_points_bal_trap_low_fill` | low_fill | 1% of clients have it (persistent), a lognormal amount each month; null for the rest | missingness (req. 2) | fill 1%; flagged; AUC ≈ 0.5 among the filled rows |
| L2 | `complaint_category_trap_low_fill` | low_fill | 0.3% of rows a month, one of six levels; null otherwise | missingness; EDA's level tables with tiny counts | fill 0.3%; flagged; small cells suppressed |
| M1 | `cc_offer_code_trap_missing_leak` | missing_leak | look-ahead (w = 3): a random code for 80% of the non-holders who take the card within 3 months and 1% of the other non-holders; null for holders | the missingness-pattern leak (req. 3): the value says nothing, being filled says almost everything | AUC of "is filled" ≈ 0.90 for `cc_acquire` at w = 3, above the oracle's 0.84; the codes' levels carry no signal |
| S1 | `cc_limit_trap_shifted` | shifted | next month's `cc_limit` (an as-of misalignment); null without a next month; float | the time-alignment check, on the card | beats the oracle at w = 1; ≈ 0.67 at w = 3 (one acquirer in three has next month's limit), below the oracle |
| P1 | `application_cc_cnt_trap_process_leak` | process_leak | a card taken at t+1 is preceded by an application at t with chance 0.8; declined applications are 30% of all, among non-holders | the leakage screen plus human review, on the card | beats the oracle for `cc_acquire` at w = 1, not at w = 3 |

Not built now: an `unstable` kind (a one-month campaign flag whose link to acquisition exists in
one window month only; tests req. 6, Feature Checks deep, M4; Q385), drift noise (the login drift
already covers drift) and the noisy copy of a real column first proposed as N3 (dropped on the
SDS's answer to Q380; R1 covers redundancy).

### Questions
- **Q379. Timing: build the LDS's to-dos now, in Stage 1's major step 2?** *Options:* (a) now,
  as minor step 2b below: one regeneration together with the holdings table and the `dev` preset;
  M2.2 tests the checks on them from the start. (b) At M4, as the roadmap says: Stage 1 stays as
  planned, but the dataset is regenerated twice and M2.2 and the run-through see no noise or
  low-fill columns. *Default:* (a); about half a day with subagents.
- **Q380. The noise catalogue, and what "univariate" means.** The LDS's note says "noisy
  (univariate, random etc)". My reading was *random* = independent of everything (N1, N2) and
  *univariate* = noise on one real variable (a noisy copy). *Answered (SDS, 10-25):* the LDS
  meant a column with only one value, a **constant column**; and the other reading, a column
  **informative on its own but redundant given others**, is kept as a second definition. So the
  catalogue has C1 and C2 (a string and a numeric constant: they hit different code paths) and
  R1 (tenure in months beside tenure in days: as informative as its source for card acquisition,
  worthless given it); the noisy copy is dropped.
- **Q381. Low fill: two columns?** L1 numeric, 1% of clients, persistent (a client has it or not);
  L2 categorical, 0.3% of rows a month. The recorded to-do says 0.1–2% filled. *Default:* both;
  the alternative is L1 alone.
- **Q382. The missingness leak M1 (my addition).** Feature Checks req. 3 names "dominance and
  missingness patterns", and no trap tests it: today's leaks leak through their values. M1 is a
  third card leak that leaks through being filled. *Default:* build it; it is one more look-ahead
  column in `finalize_lookahead`.
- **Q383. Card twins for the shifted and process-leak kinds (S1, P1)?** *Options:* both; S1 only
  (the cheaper one, and the time-alignment check is the one with no card trap at all); neither
  (the loan versions are tested at M4). *Default:* both: the two mechanisms become generic over
  the product (a flag product's event is the flag going 0 → 1, a loan's the count rising), about
  40 lines, and the run-through then meets every trap-column kind on `cc_acquisition`.
- **Q384. Extras on by default?** Turning `--extra-columns` on in every preset (say 20) would give
  the ranking a graded set (real > weak > noise) at no code cost, but every column would be a
  float normal. *Default:* no; the typed columns above cover the kinds, the mart grows 147 → 157,
  and the extras stay the scale switch.
- **Q385. Defer the `unstable` kind to M4?** Feature Checks' stability (per-month AUC range, PSI
  across the window) is deep at release 1.0, so nothing would test the column before M4.
  *Default:* defer, noted in the backlog line; it costs one more regeneration in M4 (`dev` a
  minute, `canonical` six).
- **Q386. Make the trap summary the acceptance list for "the traps are flagged" (M2.2, M5a)?**
  A mapping from trap kind to the Feature Checks step that must flag it (quality: `low_fill`,
  `near_constant`, `all_null`, `high_cardinality`; leakage: `leak`, `missing_leak`,
  `process_leak`, `upstream_target`; time alignment: `shifted`; redundancy: `noisy_copy`; the
  null controls in the bottom decile of EDA's ranking), kept in the test, not in the synthetic
  spec (the dev-only package plays upstream and shouldn't know the framework's step names). The
  e2e test (M2.4) loops over `truth.json`'s trap list with it, so "flagged" is checked, not
  eyeballed. *Default:* yes; written when Feature Checks is built (M2.2), the kind → step table in
  `tests/`. *Answered (SDS, 10-25): default, with the question how this translates to real data,
  since only the synthetic mart has `_trap_` names and it never enters the bank.* It doesn't
  translate, and it mustn't: the mapping is a **test**, not a framework feature.
  - Feature Checks flags a column from its statistics alone and never reads its name. A code-rule
    test asserts that `src/core_modelling/` never contains the string `_trap_` (added in 2b).
  - Outside the bank we know which columns are planted and of what kind (`truth.json`'s trap
    list), so the test can check that each kind was caught by the step meant for it. That is the
    evidence the steps work, in the same way "beats the oracle = leaks" (D-100 (e)) relies on an
    oracle that exists only outside the bank.
  - Inside the bank the same steps run name-blind on real columns, and the DS reads the flags in
    the Feature Checks log, the ledger and the report. No trap list exists there, and none is
    needed.
  - Where the test runs: with the synthetic tests, outside the bank. Inside the bank only if
    `synthetic/` travels with the light suite at the pre-release (D-014 (light tests now; the
    pre-release moves the code into the bank's internal repo)). That is unsettled: the package
    calls itself dev-only while the tests import it. To settle with the test harness owner before
    the pre-release; not this file's question.
  - The mapping, by kind: quality ← `constant`, `near_constant`, `all_null`, `low_fill`,
    `high_cardinality`; leakage ← `leak`, `missing_leak`, `process_leak`, `upstream_target`; time
    alignment ← `shifted`; redundancy ← `redundant`; the null controls in the bottom decile of
    EDA's ranking.
- **Q387. Who builds minor step 2b, and when?** *Options:* (a) this chat builds 2b now: the
  synthetic package is idle until Stage 1's major step 2, so no two chats touch it at once; 2a
  (the holdings table and the `dev` preset) stays with the Stage 1 chat; 2c (regenerate, notebook,
  docs) runs once, after both, by whichever chat finishes second, and the version goes to 0.5.0
  once. (b) The Stage 1 chat absorbs 2b into its major step 2 and this file hands over.
  *Default:* (a); the build starts on your go.

### The amended plan for major step 2
Major step 2, Target Factory and the synthetic additions, ends in the SDS's review. Minor steps,
each ending in the review subagents:
- **2a. `holdings` table + `dev` preset** (as planned, Q352, Q363). Files:
  `synthetic/output.py`, `spec/presets.py`, one test, `conf/base/environment.example.yml`.
- **2b. Noise, low-fill and card-twin trap columns** (new). Files: `spec/traps.py` (eight rows),
  `mechanisms/traps.py` (`TRAP_KINDS`, `TRAP_TYPES`; the persistent ones in `start_trap_state`,
  the monthly ones in `trap_columns`; M1, S1 and P1 in `finalize_lookahead`, with `_shifted` and
  `_applications` generic over the product), `generate.py` (`STREAMS` + `noise`),
  `checks/traps.py` (the rows in the table's Expected column), `checks/mart.py` (the null rule
  lists the low-fill and missing-leak columns as checked by the traps family),
  `synthetic/__init__.py` 0.5.0, `tests/data/synthetic_mart_columns.txt`, the look-ahead list in
  `tests/test_synthetic_population.py`, the `_trap_` guard in `tests/test_code_rules.py` (Q386).
  About 250–300 changed lines. Left out: `unstable`, drift
  noise, extras on by default. Reviews: code-reviewer, simplicity-review, ml-correctness-auditor
  (the look-ahead columns stay the only ones reading later months; the oracle stays clean).
- **2c. Regenerate and document** (new). `dev` and `canonical` regenerated in the background with
  `--checks`; the shared columns diffed against 0.4.0 once; `notebooks/00_synthetic_data.ipynb`
  rerun (section 6, appendix); docs: `test_harness.md` (Levels 1–3, trap summary, null rule,
  presets; future to-dos reduced to `unstable`), `synthetic/REVIEW.md`, `docs/roadmap.md` (depth
  table row, backlog line, M1 row), `docs/UPDATES.md`, D-064 extended (the kinds; the card-twin
  rule), `conf/local` pointed at `dev`.
- **2d. Target Factory** (as planned, Q364–Q367).

### What it changes downstream
- **M2.2's "done when"** (`timeline_proposal.md`): "the traps are flagged" is read against the
  trap summary, per Q386: for every trap column with a card target or no target, the step named
  by its kind flags it, and the null controls rank in the bottom decile.
- **M5a, run-through 1 on `cc_acquisition`** meets: the card's real-column traps (Simpson's, the
  half-strict income threshold, the onboarding wave, the eligibility-defining columns, the decimal
  limit), every trap-column kind, the null controls, the quality and low-fill columns. The loan's
  real-column traps (rare level, inverted U, hidden openings) wait for M4's count-rise family.
- The depth table's synthetic row moves "noise and very-low-fill columns" from release 1.0 to the
  pre-release; the backlog line keeps `unstable` for M4.
