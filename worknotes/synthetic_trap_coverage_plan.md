# Synthetic 0.6.0: a trap and a control for every Feature Checks finding — execution plan
_Written 2026-11-09 (Fable planning session) for an Opus build session. The SDS answers §8 first
(defaults stand where unanswered). Source: `worknotes/synthetic_trap_coverage.md` (Q545's to-do
list; delete it when §6 is done). Scope: `synthetic/`, `tests/`, docs. `src/core_modelling/` is
not touched: the framework stays name-blind and unchanged._

**In short.** Nine new trap columns (three derived from existing columns without a random draw),
six "natural control" rows on real columns, two random streams appended last, synthetic 0.6.0,
both datasets regenerated. Every finding in `feature_checks/findings.py` (20) then has a trap
that must raise it and a control close to the threshold that must not, and `tests/test_traps.py`
asserts both from `truth.json`. Three items of the note are dropped with a reason (§8: Q547–Q549):
the lagged flip, the ~60% lag control, the few-events minority.

**Kick-off prompt for Opus (copy, then add the SDS's §8 answers):**
```
Read CLAUDE.md §0 (UPDATES, roadmap not needed), then worknotes/synthetic_trap_coverage_plan.md
in full, then docs/components/test_harness.md (Level 2 "Traps and the oracle", Level 3 "Trap
summary", "Feature mart"), docs/components/feature_checks.md ("The finding table", "Trap
acceptance test"), synthetic/src/synthetic/{spec/traps.py, mechanisms/traps.py, generate.py,
checks/traps.py}, tests/test_traps.py. The SDS's answers to §8: <…>. Execute §6 minor step by
minor step with the reviews it names; stop for the SDS at the end of §6 (one major step).
Report what changed, the measured values of §6.3's table, what to review first, open risks.
```

---

## 1. Design rules that keep the columns few
1. **One column, several roles.** Every planted column is a trap for at least one finding or a
   control for at least two; the roles are listed per column in §2 and asserted per role in §5.
2. **Natural controls first.** Where a real column already sits where the control should (a
   static attribute without signal, a dominant level at h 0.64, random-looking nulls), it becomes
   a spec row of `trap_column: False` (like `onboarding`, `simpson`), not a new column (§3).
3. **Derived beats drawn.** Three leaks are deterministic functions of existing columns and the
   months ahead (no stream, no draw).
4. **Existing columns stay byte-identical at the same seed** (D-064): the new draws come from two
   streams appended last, `controls` (per-month columns) and `control_leaks` (look-ahead columns).
5. **No new framework code.** Controls test the rules as built; a control that fires is a rule
   over-firing, which the test then reports.
6. **Honest columns stay honest.** The two score columns read the oracle's `score_cc` *of the same
   month* plus noise, as `fs_extract`'s trait proxies read the traits (test_harness.md,
   "Feature-store extract"): a noisy transform of the oracle adds no mechanism, so the oracle
   stays the ceiling. Everything that reads later months is a declared look-ahead column.

## 2. The new trap columns (nine)
Names follow the grammar `<name>_trap_<kind>`; new kinds join `TRAP_KINDS`: `spend_leak`,
`honest`, `unstable`, `one_value`, `drift_window`, `drift_moderate` (the first four columns reuse
`leak`, `missing_leak`, `process_leak`). "Must raise" and "must not raise" are what
`tests/test_traps.py` asserts (§5); "measure" is what §6.3 calibrates on the `dev` preset.
Parameters are starting values; the measured ones go into the spec row and its `expected` text.

| # | Column · kind · type | Where built · draws | Construction (parameters) | Must raise | Must not raise (control for) |
|---|---|---|---|---|---|
| 1 | `cc_review_score_trap_leak` · `leak` with `shape: u` · int64 | `finalize_lookahead`, `_leak` extended; 1 normal per row from `control_leaks` | `round(centre + scale·(ε + a·acquired·sign(ε)))`, acquirers (card within w = 3) pushed away from the centre on their own side, holders ε only. `{"shape": "u", "offset": 1.0, "w": 3, "centre": 500, "scale": 100}`. Plain concordance ≈ 0.5 by symmetry; best-order ≈ P(\|ε₁\| + a > \|ε₂\|) ≈ 0.88 | `leakage.too_strong` (best order; the detail opens "best order; in bin order 0.5xx"), on card | — |
| 2 | `td_offer_rate_trap_missing_leak` · `missing_leak`, product `td`, target `td_acquire` · float64 | `finalize_lookahead`, new `_blanked_on_conversion`; 1 uniform per row | A rate `round(2.5 + 2.5·u, 2)` for every client, holders included; **null** where the client holds no deposit at t and takes one within w = 3 months inside the panel (`_acquired`). `{"w": 3, "rate_range": [2.5, 5.0]}`. Null share = the TD prevalence (≈ 0.2% per row on `dev`), below EDA's 0.5% range, null concordance 1.0 | `leakage.missingness_leak` on the TD config (the below-range path, Q545's "read below EDA's range") | on the **card** config: `leakage.missingness_leak`, `quality.nulls_informative` (tiny random nulls read below the range ≈ 0.5; §5's cross-config test) |
| 3 | `application_cc_status_trap_process_leak` · `process_leak`, card · string | `finalize_lookahead`, derived from `application_cc_cnt_trap_process_leak` and next month's `cc_flag`; no draw | `approved` = applied at t and `cc_flag` = 1 at t+1; `declined` = applied, not taken; `none` otherwise (and in the panel's last month). `{"of": "application_cc_cnt_trap_process_leak", "levels": ["none", "approved", "declined"]}` | `leakage.rare_value_leak` on card (the categorical path, Q533: minority 1.3%, rate ≈ 73% vs 2%, h ≈ 1.8) | — (it also raises `lagged_signal_drop` like its numeric twin: by design, not asserted) |
| 4 | `cc_spend_review_trap_spend_leak` · `spend_leak`, product `cc`, target `spend_cc_next_3_months` · int32 | `finalize_lookahead`, new `_spend_leak`; derived from `spend_cc_vol` over t+1 … t+3; no draw | 1 for a card holder at t whose spend over the next 3 months (within the panel; a leaver counts 0) exceeds `threshold`, else 0; 0 for non-holders. `{"w": 3, "threshold": 30_000}` (the ≈ 95th percentile of holders' 3-month spend: calibrate so the dominant 0 holds ≥ 0.92 of holders' rows) | `leakage.rare_value_leak` on the regression variant (Cohen's d ≥ 0.8): asserted in `tests/test_feature_checks.py` (§5) | — (on the card config it is constant 0 among non-holders: `quality.constant` by design, like `eligibility_defining`) |
| 5 | `cc_propensity_score_trap_honest` · `honest`, card · int64 | new `control_columns` in `buffer_month`; 1 normal per row from `controls` | `round(600 + 100·(a·z + σ_m·ε))`, `z` the month's `score_cc` standardised over the month's clients, `σ_m` = `sigma[0]` in even calendar months and `sigma[1]` in odd ones. `{"product": "cc", "loading": 1.0, "sigma": [0.8, 1.4], "centre": 600, "scale": 100}`. Targets: pooled window concordance ≈ 0.75 on card (below 0.80, the oracle's ceiling is 0.84–0.86); per-period range ≈ 0.06–0.08, so Cochran's p ≤ 0.01 while range / signal ≈ 0.3 < 0.5 | — | `leakage.too_strong` (an honest 0.75), `stability.concordance_unstable` (Q544: a strong feature with the trap's absolute swing), `time_alignment.lagged_signal_drop` (an honest slow mover keeps ≈ 0.9), `time_alignment.client_constant` |
| 6 | `cc_vendor_score_trap_unstable` · `unstable`, card · int64 | `control_columns`; 1 normal per row | `round(300 + 50·(b·z·on_m + ε))`, `on_m` = 1 in even calendar months, 0 in odd ones (a score delivered every other month, noise in between). `{"product": "cc", "loading": 0.6, "centre": 300, "scale": 50}`. Targets: even-month concordance ≈ 0.62–0.65, odd ≈ 0.50, pooled ≈ 0.56–0.57: range ≈ 0.13 ≥ 0.5 × 0.07, p ≪ 0.01 | `stability.concordance_unstable` on card (D-064's deferred `unstable` kind, built now: Q551) | `leakage.too_strong` |
| 7 | `statement_format_trap_one_value` · `one_value` · string | `control_columns`; 2 uniforms per row | One value `"e-statement"` for every client, null at random on `null_share` 0.02 (N4: one value plus nulls is not constant; dominant share 0.98 < 0.99); from `new_level_month` 2026-03 the value `"paper"` on `new_level_share` 0.004 of rows. `{"value": "e-statement", "null_share": 0.02, "new_level": "paper", "new_level_share": 0.004, "new_level_month": "2026-03"}` | — | `quality.constant`, `quality.near_constant`, `quality.nulls_informative` (random nulls), `stability.new_levels` (0.4% < 1%), `quality.high_missing` |
| 8 | `support_wait_min_trap_drift_window` · `drift_window` · float64 | `control_columns`; 1 uniform + 1 normal per row | Null at random on `null_share` 0.30 (no call this month: a null that means 0), else `round(median·exp(σ·ε), 1)` with the median × `factor` from `step_month` on, never 0. `{"null_share": 0.3, "median": 6.0, "sigma": 0.6, "factor": 1.8, "step_month": "2025-06"}`. Targets: PSI(window first → last) ≥ 0.30 on the example configs' window 2025-03 … 2025-08 (the null bin is constant, so it contributes nothing); PSI(window last → latest) ≈ 0 | `stability.psi_window_large`, `quality.nulls_may_be_zeros` (both configs: label-free) | `stability.psi_latest`, `stability.psi_latest_large`, `quality.nulls_informative`, `quality.high_missing` |
| 9 | `contact_channel_trap_drift_moderate` · `drift_moderate` · string | `control_columns`; 2 uniforms per row | Levels with shares `before` until `step_month`, `after` from it (PSI ≈ 0.15 by the share formula); from `new_level_month` a new level on `new_level_share` of rows, taken proportionally from the others. `{"levels": ["branch", "phone", "web", "app"], "before": [0.4, 0.3, 0.2, 0.1], "after": [0.25, 0.3, 0.25, 0.2], "step_month": "2025-06", "new_level": "chat", "new_level_share": 0.03, "new_level_month": "2026-03"}`. PSI(window last → latest) ≈ 0.17 comes from the new level alone (0.03 · ln(0.03 / 10⁻⁴)); the framework's categorical PSI path gets its first planted drift | `stability.psi_window`, `stability.psi_latest`, `stability.new_levels` (both configs) | `stability.psi_window_large`, `stability.psi_latest_large` |

Notes on the table:
- Column order: #1–#4 join the look-ahead block (`finalize_lookahead` places it before the first
  `_trap_` column); #5–#9 are a per-month block after the 0.5.0 noise block and before the extra
  columns. `tests/data/synthetic_mart_columns.txt` goes from 157 to 166 lines.
- `lookahead_months` stays 3: add `spend_leak` to its windowed kinds (the U leak is a `leak` row).
- The drift dates (2025-06, 2026-03) are chosen for the example configs' window 2025-03 … 2025-08,
  validation 2025-11, latest 2026-09, as the app relaunch (2026-01) already is; the spec rows say
  so and the generator's own checks (§6.2) compare months around each step, config-free (Q550).
- The honest and unstable scores standardise `score_cc` within the month (`oracle_values` carries
  `score_<product>` in `buffer_month`); "even calendar month" gives 3 of the window's 6 periods.
- `concordance_unstable` is **not** a control role on the noise columns (#7–#9): with no signal the
  relative-range condition is always met and Cochran's p ≤ 0.01 happens by chance 1% of the time
  per column. It is a control role on #5 only, where the strong signal makes the rule bite.

## 3. Natural controls: spec rows on real columns (no new column)
Rows with `trap_column: False`, `target: "cc_acquire"` (the values below are the canonical card
run of 2026-11-09; confirm on `dev` in §6.3). Their kinds are not in `TRAP_KINDS` (they name no
column), like `onboarding` or `simpson`.

| Kind | Column (`also`) | What it is | Must raise | Must not raise |
|---|---|---|---|---|
| `static_attribute` | `emirate` (`employment_status`, `salary_transfer_flag`) | Fixed per client, drawn without the traits: constant share 1.0, concordance 0.51–0.53, below the 0.6 gate | — | `time_alignment.client_constant` |
| `dominant_level` | `segment` (`spend_cc_travel_vol_0_5_months_avg`, `spend_cc_travel_vol_0_2_months_avg`) | A dominant value with a real minority: h 0.64 (PSB vs the rest), the travel roll-ups 0.43–0.48 | — | `leakage.rare_value_leak` |
| `shared_null_set` | `casa_bal_0_5_months_avg` (`inflow_casa_vol_0_5_months_avg`) | The six-month roll-ups' null set (clients with fewer than six months): null concordance 0.584, one set of 37 features (Q543) | `quality.nulls_informative` | `leakage.missingness_leak` |
| `recency_null_zero` | `months_since_last_spend_cc` | 90.8% null among non-holders, never 0 (0 would mean a holder) | `quality.nulls_may_be_zeros` | `quality.high_missing` (0.908 < 0.95) |
| `recency_with_zeros` | `months_since_last_fx` | 79.6% null, 63% zeros among the values | — | `quality.nulls_may_be_zeros`, `quality.high_missing` |
| `weak_nulls` | `residence_days` (`income`) | Nulls with a cause but almost no label signal: null concordance 0.512 and 0.504 | — | `quality.nulls_informative`, `leakage.missingness_leak` |

## 4. Coverage after the change (every finding: trap → control)
| Finding | Trap that must raise it | Control that must not |
|---|---|---|
| `quality.all_null` | `all_null` (+ `cc_utilisation_ratio` under the eligibility) | the `low_fill` columns (implicit) |
| `quality.constant` | the two `constant`, `eligibility_defining` | #7 `one_value` |
| `quality.high_missing` | the two `low_fill` | `recency_null_zero` (0.908), #7, #8 |
| `quality.near_constant` | `near_constant` | #7 (0.98) |
| `quality.high_cardinality` | `high_cardinality` (300 levels) | categoricals under 50 levels (implicit); `nationality` fires by design |
| `quality.nulls_may_be_zeros` | #8 `drift_window` (30% null, no zeros), `recency_null_zero` | `recency_with_zeros` |
| `quality.nulls_informative` | `shared_null_set` | `weak_nulls`, #7, #8 |
| `leakage.too_strong` | the two `leak`, `upstream_target`, #1 U leak (best order) | #5 `honest` (0.75), #6 |
| `leakage.missingness_leak` | `missing_leak` offer code (card), #2 TD rate (td, below range) | `shared_null_set`, `weak_nulls`, #2 on the card config |
| `leakage.rare_value_leak` | `process_leak` numeric and #3 categorical (card), #4 (regression d) | `dominant_level`, #7 (no minority) |
| `time_alignment.lagged_signal_drop` | `shifted` (card) | #5, every legitimate column (`NEVER_ON_LEGITIMATE`; the login counts keep 0.80–0.85) |
| `time_alignment.client_constant` | `lookahead` | `static_attribute`, #5 |
| `stability.concordance_unstable` | #6 `unstable` | #5 `honest` |
| `stability.psi_window_large` | #8 | #9 |
| `stability.psi_window` | #9 | #8 raises the flag instead (exclusive); columns at PSI ≈ 0 (implicit) |
| `stability.psi_latest_large` | `drift` (the login roll-ups) | #9 (≈ 0.17), #8 (≈ 0) |
| `stability.psi_latest` | #9 | #8 |
| `stability.new_levels` | #9 (3%) | #7 (0.4%) |
| `redundancy.correlated_pair` | `redundant` | numerics below 0.90 (implicit) |
| `redundancy.associated_pair` | `collinearity` (the status ⇔ flag identities) | implicit |

## 5. Truth and test design (`tests/test_traps.py`)
The mapping stays in the test (D-064: the synthetic package never names a Feature Checks finding;
Q546). Changes:
1. **`TRAP_FINDINGS` values become tuples of findings** (`_missed` loops over them); new keys:
   `("missing_leak", "td_acquire")` → `missingness_leak`; `("unstable", "cc_acquire")` →
   `concordance_unstable`; `("drift_window", None)` → `psi_window_large`, `nulls_may_be_zeros`;
   `("drift_moderate", None)` → `psi_window`, `psi_latest`, `new_levels`;
   `("shared_null_set", "cc_acquire")` → `nulls_informative`; `("recency_null_zero",
   "cc_acquire")` → `nulls_may_be_zeros`. The existing `("leak", "cc_acquire")` and
   `("process_leak", "cc_acquire")` keys cover #1 and #3 as further rows of their key.
2. **`CONTROL_FINDINGS: dict[tuple, tuple[str, ...]]`**, the findings that must not fire on a row's
   columns (`_columns`, so `also` counts), asserted with `_asserted_on` like the traps, by a new
   `test_each_control_raises_no_forbidden_finding` (failure lines like `_missed`'s). Entries: the
   "must not raise" cells of §2 and §3 (every kind of §2 and §3 appears; a row may be in both
   dicts).
3. **`test_every_trap_row_is_mapped_or_listed`:** `placed` = `TRAP_FINDINGS` ∪ `KIND_CHECKS` ∪
   `NOT_CHECKS` ∪ `CONTROL_FINDINGS`; a kind in none of them still fails.
4. **`NOT_CHECKS`:** `("spend_leak", "spend_cc_next_3_months")`: "asserted on the regression
   variant in test_feature_checks.py".
5. **The cross-config control:** `test_sub_range_nulls_unrelated_to_the_target_raise_nothing`: the
   `("missing_leak", "td_acquire")` row's column (found from the truth) raises neither
   `missingness_leak` nor `nulls_informative` on the **card** run.
6. **`tests/test_feature_checks.py`** (unit preset, the `regression` fixture): add
   `"*_trap_spend_leak"` to `REGRESSION_CANDIDATES` in `tests/test_eda.py`, and one test that the
   regression run's findings hold `leakage.rare_value_leak` on it with the detail naming
   `Cohen's d` (the task's `rare_effect_name`) and a value ≥ 0.8 — the Cohen's d path.
7. Unchanged: `test_null_controls_carry_no_signal_and_no_flag` (the four null controls),
   `test_legitimate_columns_raise_no_leak_or_lag_flag` (the new columns are trap rows, so the
   count-free guard skips them; the natural rows' real columns stay under it), the D-088 counts,
   the bins rule (the new numerics have hundreds of distinct values; #4 has two: a singleton floor).

Expected new by-design holds on the card config (for the review guide and `UPDATES`): #1
(`too_strong`), #3 (`rare_value_leak`, also `lagged_signal_drop`), #4 (`quality.constant`), #6
(`concordance_unstable`), #8 (`psi_window_large`); on the TD config: #2 (`missingness_leak`), #8.

## 6. Execution: one major step, five minor steps
Routing (D-072 (l)): Opus on the main thread for the spec, mechanisms, calibration and
integration (`xhigh`); one Opus subagent for the generator checks and the synthetic tests (`xhigh`,
disjoint files, works from this plan's names and parameters); one Sonnet subagent for the docs
after the measured values exist. Reviews per minor step: `code-reviewer`; `ml-correctness-auditor`
on minor step 1 (the honest columns read month t only; every later-month read is a declared
look-ahead row; the leaks are built as their `expected` says); `simplicity-review` on the diff. No
Fable. Spark and the generator: one memory-heavy job at a time; long runs in the background with a
deadline (T36). Durations as known: `dev` generation ≈ 1 min, canonical ≈ 6 min plus 10–15 min of
checks, the trap test ≈ 5.5 min of compute.

### 6.1 Spec and mechanisms (main thread) ∥ 6.2 Checks and synthetic tests (subagent)
**6.1 files:** `synthetic/src/synthetic/spec/traps.py`, `mechanisms/traps.py`, `generate.py`,
`synthetic/src/synthetic/__init__.py` (0.6.0).
- `spec/traps.py`: the nine rows of §2 (`trap_column: True`) in two groups ("Credit card",
  "Term deposit", "Any product") and the six rows of §3 (`trap_column: False`); `expected` texts
  state what must fire and what must not, with the §6.3 measured values once known.
- `mechanisms/traps.py`:
  - `TRAP_KINDS` += the six kinds; constants for the nine names; `TRAP_TYPES` += nine types (§2).
  - `control_columns(spec, scores: dict[str, np.ndarray], month: np.datetime64, rng) ->
    dict[str, object]`: #5–#9 in the mart's order; docstring lists the draws in order (honest
    normal, unstable normal, one-value null uniform, one-value new-level uniform, wait null
    uniform, wait normal, channel level uniform, channel new-level uniform). Helpers, one job each:
    `_standard_score(values) -> np.ndarray`, `_even_month(month) -> bool`,
    `_dated(month, iso_month) -> bool` (month ≥ `"YYYY-MM"`), `_level_shares(record, month)`.
  - `finalize_lookahead(spec, frames, rng, card_rng, control_rng)`: adds #1–#4 to `columns`;
    `_leak` reads `p.get("shape")`: `"u"` pushes acquirers away from the centre on their own side
    (`ε + offset · acquired · sign(ε)`), else as now; `_blanked_on_conversion(spec, frames, u)`,
    `_application_status(spec, frames, applications: np.ndarray)`, `_spend_leak(spec, frames)`.
    Draws from `control_rng`: the U leak's normals, then the rate's uniforms.
  - `lookahead_months`: `windowed` += `"spend_leak"`.
- `generate.py`: `STREAMS` += `"controls"`, `"control_leaks"` (appended last; the docstring's
  stream list); `buffer_month` adds `traps |= control_columns(spec, oracle_values, sim["month"],
  rngs["controls"])` after `noise_columns`; both `finalize_lookahead` calls pass
  `rngs["control_leaks"]`.
- Left out deliberately: no persistent per-client state for the new columns (all are drawn per
  month), no change to any existing column, draw or stream, no change to `output.py`,
  `truth_file.py` or the extract.

**6.2 files:** `synthetic/src/synthetic/checks/traps.py`, `checks/mart.py`,
`tests/test_synthetic_mart.py`, `tests/data/synthetic_mart_columns.txt` (regenerated after 6.1
lands: the test that compares it says how).
- `checks/traps.py`: constants for the nine columns, `MART_COLUMNS`/`ORACLE_COLUMNS` extended
  (`score_cc` for the two scores; `td_flag`, `spend_cc_vol`), rows written from the spec:
  - #1: AUC of \|x − centre\| for `cc_acquire` (w = 3) above the oracle's; AUC of x within `Z_TOL`
    Hanley SE of 0.5.
  - #2: rule: null exactly where no deposit at t and one within 3 months inside the panel; values
    within `rate_range`.
  - #3: rule: `approved` ⇔ applied and `cc_flag` = 1 next month, `declined` ⇔ applied and not,
    `none` otherwise.
  - #4: rule: 1 ⇔ holder and next-3-month spend > threshold (`values_at`); holders' dominant share
    of 0 ≥ 0.90 (side row).
  - #5: AUC for `cc_acquire` (w = 3, one month) within the measured range (`range_row`); even-month
    minus odd-month AUC ≥ 0.03 (side row); rank correlation with `score_cc` within the month in
    its measured range.
  - #6: even-month AUC ≥ 0.58 (side row); odd-month AUC within `Z_TOL` SE of 0.5.
  - #7: rule: one value or null before `new_level_month`; null share (share row); new-level share
    after the month (share row).
  - #8: null share; rule: no zeros among the values; PSI(the three months before the step → the
    three after) ≥ 0.25; PSI(a later pair of months) ≤ 0.1 (`table.psi` on the non-null values).
  - #9: level shares before and after (share rows); a small `categorical_psi(a, b)` helper on
    level shares (`table.py`) for PSI(before → after) in [0.10, 0.25]; new-level share.
- `checks/mart.py`: extend `STRING_COLUMNS`, `INTEGER_COLUMNS` and `ANY_NULLS` (#2, #7, #8 have
  random nulls) as the module docstring says.
- `tests/test_synthetic_mart.py`: `TRAP_SPARK_TYPES` += nine entries (`bigint`, `double`,
  `string`, `int`, `bigint`, `bigint`, `string`, `double`, `string`).
- Verification: `pytest tests/test_synthetic_traps.py tests/test_synthetic_mart.py
  tests/test_synthetic_population.py -q` (unit preset; `test_truth_lists_every_trap` and the
  "months do not depend on later months" test cover the new rows and the look-ahead discipline),
  `ruff check` on the touched files.

### 6.3 Calibration on `dev` (main thread; one Spark job at a time)
1. `python -m synthetic --preset dev --out <scratch>/dev` (≈ 1 min); a 15-line scratch script
   (in the scratchpad, not the repo) writes an environment file like `tests/conftest.py`'s
   `write_environment_file`, runs `run([cc, td], env_path=…, stages=["target_factory"])`, then
   `eda` and `feature_checks` per config, and prints for every `_trap_` and §3 column the ledger
   row (`read_ledger`: `concordance_window`, `missing_share_window`, `null_concordance_window`,
   `dominant_share_window`, `signal_kept`, `constant_share`, `psi_window`, `psi_latest`,
   `heterogeneity_p`, `concordance_range`, `new_level_share`, `flags`, `notes`) and its findings
   (`read_stage(folder, "feature_checks")[1]["findings"]`), plus EDA's `concordance_per_period`
   rows for #5 and #6.
2. Compare with the targets below; change the spec parameters, regenerate, rerun (two or three
   rounds at most); record the measured values in the spec rows' `expected`, the check rows' ranges
   and the table below.

| Column | Target on the card config (`dev`) | Knob |
|---|---|---|
| #1 | best-order window concordance ≥ 0.85, plain 0.45–0.55 | `offset` |
| #2 (TD config) | null share 0.1–0.4%, null concordance ≥ 0.9, `missingness_leak` raised; card config: neither flag nor note | `w` fixed |
| #3 | h ≥ 1.5, detail "significant" | — |
| #4 (unit, regression) | dominant share ≥ 0.92, d ≥ 1.0 | `threshold` |
| #5 | pooled 0.73–0.77; range 0.05–0.09; `heterogeneity_p` ≤ 0.01 and no `concordance_unstable` (range / signal < 0.5); `signal_kept` ≥ 0.8 | `loading`, `sigma` |
| #6 | even periods 0.60–0.66, odd 0.48–0.52; pooled 0.55–0.58; `concordance_unstable` raised | `loading` |
| #7 | dominant 0.975–0.985; `new_level_share` 0.003–0.006 | shares |
| #8 | `psi_window` 0.30–0.60, `psi_latest` < 0.05; missing 0.30 | `factor` |
| #9 | `psi_window` 0.12–0.20, `psi_latest` 0.12–0.22, `new_level_share` 0.025–0.035 | `after`, `new_level_share` |
| §3 rows | as §3's values ± sampling noise; every must / must-not holds | — (if one fails on `dev`, drop that `also` column, never the rule) |

Keep the card's events per window period in view (`eda.json`'s `population`: about 300–400 on
`dev`); the SE of a concordance there is ≈ 0.015, which the swing targets assume.

### 6.4 The acceptance test (main thread)
Files: `tests/test_traps.py` (§5.1–5.5), `tests/test_eda.py` (`REGRESSION_CANDIDATES`),
`tests/test_feature_checks.py` (§5.6). Run `pytest tests/test_traps.py -q` (its own process, about
6 minutes) and `pytest tests/test_feature_checks.py -q -k regression`. Then `code-reviewer` on the
diff of 6.1–6.4 and the `ml-correctness-auditor` on 6.1; fix or justify every finding.

### 6.5 Regenerate, re-run, document (background jobs first, docs meanwhile)
1. Remove the gitignored, regenerable `data/01_raw/synthetic_dev/`,
   `data/01_raw/synthetic_canonical/` and `data/05_model_input/retail_acquisition/` (a saved model
   input does not notice new source columns: the hashes see logical names, D-131; Q557), then in
   the background with a deadline: `python -m synthetic --preset dev --out data/01_raw/synthetic_dev`,
   `python -m synthetic --preset canonical --out data/01_raw/synthetic_canonical --checks` (every
   check row must pass at 100k), then `python -m core_modelling run conf/base/cc_acquisition.yml
   conf/base/td_acquisition.yml --stages target_factory eda feature_checks` (the audit log stays;
   new `flag` entries appear where sets changed).
2. Re-run `notebooks/00_synthetic_data.ipynb` in place (it shows the trap list and the check
   tables; committed with outputs, D-064). Notebooks 01–03 are not re-run unless the SDS asks
   (Q556).
3. Docs (Sonnet, from the measured values): `docs/components/test_harness.md` (status line 0.6.0;
   Level 1 and Level 3 column counts 157 → 166 and "Trap columns (29)"; the name grammar's kinds;
   the stream list; the Trap summary: nine rows, a short "Controls" paragraph defining a control
   and naming the six natural rows, and one line on what is not planted and why: a lagged flip
   (§8 Q547)); `docs/components/feature_checks.md` ("Trap acceptance test": the controls and the
   cross-config test; `rare_value_leak`, `missingness_leak`, `concordance_unstable` "Catches" lines;
   the open question "no synthetic trap yet" removed); `docs/decisions.md` D-064 extended in place
   (controls as the test's second mapping, the natural rows, `unstable` built in M2.2 not M4, the
   two streams); `docs/roadmap.md` (the M1 backlog line: the `unstable` kind is built);
   `docs/UPDATES.md` (the synthetic row: 0.6.0; one log line); `tests/README.md` (the trap test
   paragraph: traps and controls); `synthetic/REVIEW.md` (version and §1 bullets);
   `docs/glossary.md` (one entry: trap column, control column, natural control).
4. Delete `worknotes/synthetic_trap_coverage.md`; append the `worknotes/log.md` entry (what,
   measured values, files, D-064). `sync.md` only via `/brief`.
5. Full suite once, in the background with a deadline (`pytest`), after everything above; the
   touched files' tests and `ruff check` ran per step.

## 7. What the SDS reviews first
1. `spec/traps.py`: the fifteen new rows and their `expected` texts (the design in one page).
2. `mechanisms/traps.py`: `control_columns`, `_leak`'s U shape, `_blanked_on_conversion`,
   `_spend_leak` (the look-ahead boundary).
3. `tests/test_traps.py`: `TRAP_FINDINGS`, `CONTROL_FINDINGS`, the two new tests.
4. The measured table of §6.3 against the targets.
Tests beyond that are not for review (the SDS reads code, not tests).

## 8. Questions for the SDS (numbered on from Q545; each with its default)
- **Q546. Where the control mapping lives.** The note proposed a truth-row field
  (`must_not_raise: leakage.too_strong`). Default: in the test (`CONTROL_FINDINGS`, keyed by kind
  and target like `TRAP_FINDINGS`), so finding names have one owner and the synthetic package
  stays framework-agnostic (D-064: "the test maps each kind"); the spec row's `expected` prose says
  both sides for a reader.
- **Q547. Drop the lagged flip trap (R54).** Under a 3-month target the lagged value cannot order
  clients the other way while the pooled window direction stays: the windows at t−1 and t
  overlap in two of three months, so any sign pattern that flips the lag flips the window too and
  the pooled concordance falls to 0.5 (a global monthly sign flip mirrors the bins, which also
  cancel). A flip is a one-period-window or per-period phenomenon. The detail's `FLIPPED` branch is
  unit-tested on built cells (`tests/test_feature_checks_steps.py`). Default: drop; one line in
  test_harness.md says why.
- **Q548. The ~60% lag control.** An honest monthly feature keeps most of its signal because the
  drivers (traits, AR(1) at 0.95; tenure) persist; a feature keeping 60% needs a transient cause
  the oracle must know (a campaign term in the card score), a new mechanism. Default: no new
  column; #5 (kept ≈ 0.9) and the count-free guard over every legitimate column (the login counts
  keep 0.80–0.85) are the controls, which already fail a rule over-firing up to 0.8.
- **Q549. The few-events minority control** ("may fire, detail says not significant"). It needs h
  just above 0.8 on about 40 rows: seed-fragile either way, and `NOT_SIGNIFICANT` is unit-tested
  both ways (`test_feature_checks_steps.py`). Default: drop.
- **Q550. Drift dates in the spec** (2025-06 inside the example window, 2026-03 after the
  validation period), as the app relaunch already is. Default: accept; the rows say which window
  they assume, the generator's checks compare months around the step, config-free.
- **Q551. Build the `unstable` kind now** (D-064 deferred it to M4 with stability; stability is
  built). Default: yes, as #6, with #5 as its control.
- **Q552. Natural controls as spec rows** (`trap_column: False`, §3) rather than names in the
  test, so the test still finds every column from the truth. Default: spec rows.
- **Q553. The regression (Cohen's d) trap asserted in `test_feature_checks.py`'s regression
  variant** (unit preset) rather than a third config in the trap test (+ EDA and Feature Checks on
  `dev`). Default: yes.
- **Q554. Stale items (§9).** Default: keep every column; refresh four `expected` texts.
- **Q555. Byte identity of existing columns** through two appended streams (D-064), so the
  reviewable diff is the new columns only; both datasets are regenerated anyway (0.6.0 is refused
  by `load_truth` on 0.5.3 data). Default: keep.
- **Q556. Notebooks after regeneration.** Default: `00_synthetic_data` re-run in place; the model
  input, EDA and Feature Checks re-run for both example configs by CLI so notebook 03 and the
  helper notebook read current artifacts; notebooks 01–03 not re-executed.
- **Q557. A saved model input does not notice new source columns** (the hashes see logical names,
  D-131): the fix in §6.5 is to delete and re-save. Default: out of scope here; one line in the log
  and a candidate backlog item (compare the saved table's columns with the sources' at read and
  print the difference).

## 9. Stale review of the current trap list
Verdict: nothing is stale enough to remove; four `expected` texts are.
- **Refresh (cheap):** `collinearity` ("correlation views and VIF" → the redundancy clusters and
  `explained_by_others`), `rare_level` ("unstable in cross-validation" → an EDA by-level view; no
  config models the loan), `inverted_u` ("mutual information high" → the best-order concordance,
  Q489), `lookahead` (its concordance is now measured: 0.78 card on `dev`).
- **Keep, with the trade-off stated:**
  - The four null controls (premium, visits, language, consent): each is a different type (a
    persistent amount, a zero-inflated count, a Zipf categorical, a flag) and the test's
    "noise raises nothing" set. The new noise columns raise notes by design, so they cannot
    replace them. Removing the consent flag would also move the `noise` stream's later draws.
  - The personal-loan twins (`application_loan_personal_cnt_trap_process_leak`,
    `loan_personal_bal_trap_shifted`) and the loan real-column rows (`rare_level`, `inverted_u`,
    `hidden_openings`, `eligibility_defining` on the loan): untested (no loan config) but they
    document real behaviours and cost one `NOT_CHECKS` line each; the shifted loan column is also
    the only trap with an all-null latest period (it raises `psi_latest_large` on the card config
    by design). Removing the loan application's draw would move the two leaks' values (same
    stream). A loan config in the trap test would add about 3 minutes per run: not now.
  - `cc_campaign_response_score_trap_leak` (0.875): the near-threshold `too_strong` trap; the
    0.97 leak alone would not catch a threshold drifting to 0.9.
  - `extra` and `dirty` (off by default): dormant until the scale tests and monitoring; the dirty
    switch is used by `test_synthetic_traps.py` and `test_synthetic_output.py` already.

## 10. Gotchas for the builder
- Every `*_flag` column in a frame must be boolean before `with_int_flags`; the trap names end in
  `_trap_<kind>`, so #4 is not caught by that rule and is typed by `TRAP_TYPES` (int32).
- `_acquired` reads `<product>_flag` ahead; for #2 the product is `td`; a leaver counts as not
  acquired (filled), the panel's last three months fill more (the leak fades, like the offer code).
- #3 must read the card application array built in the same `finalize_lookahead` call (`columns[
  CC_APPLICATION]`), never the previous month's frame.
- #5 and #6 standardise within the month over every client (holders too); the card config's
  eligibility restricts the rows the framework sees, the generator does not.
- The checks' PSI (`table.psi`, deciles of the earlier sample) differs from the framework's merged
  bins; the check asserts the generator's drift, the trap test the framework's finding.
- `test_months_do_not_depend_on_later_months` must still pass: only `finalize_lookahead` reads
  ahead.
- A new row's kind in none of the test's dicts fails `test_every_trap_row_is_mapped_or_listed`:
  place every kind of §2 and §3 before running the trap test.
- Do not widen a check tolerance to pass; a failing row is a generator bug or a wrong target
  (then change the target and say so in the log).
