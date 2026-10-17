# Synthetic data — review guide

For the SDS's one review of the finished generator (M1, D-067). After the SDS says OK, a short
summary goes to `worknotes/sync.md` for the LDS. Spec: `docs/components/test_harness.md`. Build plan
and its history: `worknotes/handovers/synthetic_build.md`.

## 1. What was built
- A 100k-client × 24-month retail **feature mart** (2.5M rows, 145 columns): client description
  (incl. a new `onboarding_channel`), holdings and states, current-month amounts, 65 rollups,
  recency and ratios, and 8 planted trap columns; one lowercase name grammar; nulls only where retail
  data has them; 0/1 integer flags, one `decimal(18,2)` column (`cc_limit`).
- **Hidden truth:** an oracle file (traits, the chance behind every event, state-free scores, loan
  slots, hidden attributes, a Monte Carlo oracle for next-3-month card spend) and `truth.json`
  (spec, calibration, column schema, trap summary, oracle AUCs and relevance rankings for 12
  standard targets × windows of 1, 3 and 6 months).
- **Checks:** 10 families, 1,197 rows, written independently of the generator from the spec; every
  row passes at 100k. Every check family was shown to fail on deliberately broken generators.
- Code: `synthetic/src/synthetic/` (46 modules, ~8,200 lines incl. checks), `tests/` (~800 lines).
- Commits, oldest first: `2cdf746`, `bdf0f16` (A: foundations), `6335a3d`, `b1cce83` (B: amounts),
  `c9ded4f` (C: mart), `f8c0fd0`, `eb4fa2c` (D: traps), `2f61135` (E: oracle), `bbde9af` (F:
  output), `e5abb2e` (notebook), then the final review fixes (code review: 0 blocking; ML-correctness
  audit: safe).

## 2. Regenerate and check
```bash
source .venv/bin/activate
python -m synthetic --preset canonical --out data/01_raw/synthetic_canonical --checks
pytest                 # fast suite, ≈ 3 min
pytest -m slow         # canonical size, each check family in its own process, ≈ 10–15 min
```
- Generation takes ≈ 6 minutes at 100k (peak RSS ≈ 1.8 GB; budget 10 min / 3 GB). `--checks`
  then runs every family in its own process (one family needs several GB at 100k) and saves the
  tables in `<out>/checks/`; on a busy 8 GB Mac that took 45 minutes of wall time, ≈ 10 on a quiet
  one. The CLI exits with an error if any row fails.
- `--n-clients 50000` halves memory, but a few rows (home-loan sizing, null-control ranks) need
  100k to pass.
- Close memory-heavy apps first: with 130 MB of free RAM, runs took 5–10× longer.
- The folder must be new or empty; `load_truth` refuses a dataset written by another generator
  version (or numpy/scipy), so a stale `data/01_raw/` fails loud.
- To read it through the environment adapter, copy `conf/base/sources.example.yml` to
  `conf/local/sources.yml` with the absolute path (already done on the Mac).

## 3. The review, in order
### 3.1 The checking notebook (`notebooks/00_synthetic_data.ipynb`, committed with outputs)
| Section | What right looks like |
|---|---|
| 1 Check tables | 10 families, `failed` 0 everywhere |
| 2 Population | Mass ≈ 87%, Private ≈ 1%; ages rise with wealth; ASIA dominates Mass, UAE leads Private; digital onboarding 15% → 55% from Private to Mass; entry and exit rates flat per profile |
| 3 Holdings | Shares near the spec's tables and flat over 24 months (digital activity drifts up by design); never / churned / active split for term deposits |
| 4 Amounts | Medians ordered by subsegment, Private far above; heavy right tail of balances; booking identity exact (0.0000); revolvers mostly at 0.3–0.9 utilisation, few at the limit; outflow and card-spend mixes more extreme for Private vs Mass; remittance near 0 for UAE/GCC |
| 5 Time effects | Travel spend up in July–August, least for Mass; balances dip in summer; bills spike in September, January, April; mobile logins jump at 2026-01 |
| 6 Segments, Simpson | ≈ 25% of MM above the UM median; card chance rises with logins within each onboarding channel, falls pooled |
| 7 Mart columns | Kinds and null shares as in the spec's null rule; one client's rollups line up with its balances |
| 8 Traps | The trap summary; leak, upstream, process-leak, rare-level, Simpson and drift rows pass |
| 9 Oracle | AUCs below (w = 1/3/6); calibration points on the diagonal; regression coverage rows pass; `income` and inflow rollups top the card ranking, null controls at the bottom |
| 10 Trajectories | Balances persist month to month, card spend varies, hidden traits drift slowly |

### 3.2 The spec (`docs/components/test_harness.md`)
Read in this order: "Amounts" (levels, variation, current/savings, subcategories, card, loans,
deposits, wealth, FX and logins, time effects, overlap), "Feature mart" → Columns and Null rule,
"Trap summary", "Ground truth and oracle".

### 3.3 Code entry points
`generate.start_simulation` / `advance_simulation` (the month loop) → `holdings.step_holdings`
(chances) → `amounts.step_amounts` (amounts) → `cards.step_card` → `mart.history_columns`
(rollups) → `traps.finalize_leaks` (the only look-ahead) → `oracle.window_probability` (the
ceiling) → `regression.simulate_card_spend` → `output.write_mart`.

## 4. Traps and standard targets
Trap summary: the spec's table and `truth.json` (`traps`); notebook section 8.

| Target (eligible at t) | Oracle AUC, w = 1 / 3 / 6 | Events a month at 100k |
|---|---|---|
| `cc_acquire` (non-holders) | 0.863 / 0.843 / 0.831 | ≈ 1,860 |
| `td_acquire` | 0.730 / 0.726 / 0.724 | ≈ 910 |
| `wealth_digital_acquire` | 0.789 / 0.786 / 0.782 | ≈ 1,290 |
| `wealth_trad_acquire` | 0.836 / 0.831 / 0.826 | ≈ 140 |
| `ebanking_acquire` | 0.950 / 0.924 / 0.898 | ≈ 840 |
| `loan_personal_open` (all) | 0.756 / 0.755 / 0.756 | ≈ 2,070 |
| `loan_auto_open` | 0.707 / 0.707 / 0.707 | ≈ 490 |
| `loan_home_open` | 0.793 / 0.793 / 0.794 | ≈ 140 |
| `fx_activate` (dormant) | 0.746 / 0.744 / 0.742 | ≈ 1,730 |
| `digital_activate` (registered, dormant) | 0.818 / 0.787 / 0.791 | ≈ 5,050 |
| `cc_activate` (holders, dormant card) | 0.769 / 0.714 / 0.709 | ≈ 3,430 |
| `casa_reactivate` (dormant account) | 0.721 / 0.705 / 0.694 | ≈ 1,450 |

Events a month count positive rows of the w = 3 target, which repeat across up to 3 months. The
low-confidence flag in `truth.json` sizes on events (expected events in 6 months, fewer than 200 is
flagged): none is flagged at 100k; at 50k, `wealth_trad_acquire` and `loan_home_open` (≈ 145 events
each) would be. The leaks
beat the oracle as designed: card pre-approval score 0.970 vs 0.843; loan applications 0.897 vs
0.756 (next month). The regression oracle covers next-3-month card spend at its stated quantiles.

## 5. Decisions taken during the build (please confirm)
Each is in the spec; none changes a decision of yours, but some go beyond what we agreed.
1. **`onboarding_channel` (branch / digital), a new column.** Simpson's reversal by subsegment
   can't appear: Mass is 94% of the eligible rows. Grouped by onboarding channel it does
   (within +0.12 / +0.13, pooled −0.17): digitally onboarded clients are almost all registered
   for e-banking (+3.0), more active (+1.5), log in twice as often and take cards less (−1.5).
2. **Revolvers spend less as the card fills up** (wanted spend × (1 − last utilisation)), no new
   parameter. Without it, 45% of revolver months sat exactly at the limit; now 0.5%.
3. **App relaunch × 1.8** (spec said × 1.3): × 1.3 gave PSI 0.07, not the specified > 0.25.
4. **FX trait loading 0.25** (was 0.4), so its month-to-month correlation sits inside your
   0.6–0.8 band rather than on its edge.
5. **`separation` also spreads subsegment median incomes**; otherwise it had no effect on amounts.
6. **Calendar effects act only on adoption and wake-up odds**, not on how long spells last.
7. **Medians are defined for a client at its own trait means**: holders and active users are
   selected on the traits their amounts load on, so their realised medians sit a little higher.
8. **Null controls are checked in the bottom fifth** of each relevance ranking, not the bottom
   tenth: many columns are unrelated to any one target and tie with them at noise level.
9. Smaller: hidden attributes have their own random stream; dormancy among salary-transfer clients
   comes out ≈ 0.6% (spec ≈ 1%, inside the agreed 0.5–2.5% range); the market index is 1 in the
   month the starting book is drawn.

## 6. Open points for you (suggestions from the final audit; not built)
1. **Exits don't depend on behaviour.** Leavers are missing completely at random, so the choice of
   leavers-as-null vs leavers-as-negatives will look harmless here and won't be on real data,
   where dormancy precedes exit. Option: exit chance depends on dormancy, with the exit chance per
   row in the oracle. Touches D-066. *Leaning: yes, small.*
2. **A second, moderate leak** just above the oracle (≈ +0.03 AUC), so leakage screens are tested
   on "implausibly strong for this target", not only on an absurd 0.97. *Leaning: yes.*
3. **The as-of misalignment trap** (a column shifted a month), deferred in round 1. One column
   through the existing look-ahead buffer. *Leaning: yes, before Target Factory work.*
4. **Dirty defects don't reach the rollups** (an upstream mart would roll up its own bad values).
   *Leaning: state it, don't build it.*
5. Unverified ballparks: loan interest rates (7 / 4 / 5%); login levels (no UAE figure found).

## 7. Known limitations
- The oracle ignores two rare paths (losing and re-adopting a required product inside the window;
  an opening hidden by a maturity refilling a full set of 4 loan slots). Both make it slightly
  under-predict, so no model can exploit them; boosting every mart column on top of the oracle
  never beat it (audit, 9 target/window pairs).
- Every check passes at 100k; a few statistical rows need that size.
- `oracle.py` (327 lines) and `checks_oracle.py` (325) are slightly over the ~300-line guideline;
  `fx_cnt` is labelled a holding column in the truth schema (it is an FX count).
- Generation footprint at 100k is ≈ 3.2 GB including compressed memory (RSS 1.8 GB).
