# Synthetic data — review guide (round 2)

For the SDS's review of the finished generator (M1, D-067). Round 1 was the SDS's review on
2026-10-19; this round applies it (D-070). After the SDS says OK, a short summary goes to
`worknotes/sync.md` for the LDS. Spec and code map: `docs/components/test_harness.md`.

## 1. What changed since round 1
| Your feedback | What was done | Where to look |
|---|---|---|
| 50 modules on one level; checks mixed in; rules files mixed with functions | Four role folders: `spec/` (rules as plain data), `mechanisms/` (the functions that simulate), `truth/` (oracle, regression oracle, `truth.json`), `checks/`. Modules whose functions are tied together are merged (hazards + holdings, population + latents, balances + flows, names + mart, traps + dirty, oracle + month grid, month rows into the loop; in checks: table + stats, the three helper modules into `events`, holdings + drivers, levels + mix, traps + trap columns). 46 modules → 33 (+ 4 folder `__init__`s; `checks/switches.py` holds the off-by-default switch checks); 10 check families → 8 | `synthetic/src/synthetic/`; spec → Code map |
| Gigantic `truth.json`; measure code against effect | `truth.json` 234 → 55 KB: the relevance rankings went (your choice), so did every copy or field nothing reads: turnover, drift and null-rule copies, the column → module mapping, the duplicate trap list. The oracle part now holds the sizing once per target. Section 2 has the code-vs-effect review | `truth/truth_file.py`; spec → Ground truth |
| Top-down spec with a function summary | `test_harness.md` rewritten: Summary → How it works (the month loop in one diagram) → Code map → Interface → requirements → details. The build-history table went (it is in `docs/UPDATES.md`). The component template now asks every future doc for the same order | spec; `docs/components/README.md` |
| Exit rates | Monthly exits 0.7 / 0.8 / 0.9 / 1.1% (private → mass; were 0.2 / 0.4 / 0.6 / 1.0%), about 8–12% a year; entries 0.2 points above. Traditional wealth needed 42 adoptions a month (was 30) to refill the leavers' holdings and keep its ≈ 33-year holding | notebook §2; `spec/presets.py`, `spec/products.py` |
| Point 3: a chart with income on the x axis | Share holding a card, personal, auto and home loan by declared income, the minimum incomes marked (5,000 and 15,000 AED). Also, in §4, card limit vs declared income (the limit tiers show as bands) and a table of tiers per profile | notebook §3, §4 |
| Tables don't say what their values are | Every table has a line above it, or column names, saying what it holds and which statistic | notebook, throughout |
| `<NA>` in `months_since_last_spend_cc` | A true null: pandas shows a missing value in a nullable integer column as `<NA>`. The notebook now prints the dtype (`Int64`), the null count, that no value is a string, and the parquet type (`int64`) with its null count. Spark reads it as null (`tests/test_synthetic_mart.py`). The example client now spends in some months, so the column takes values | notebook §7 |
| What is an "unplanted" trap? | Renamed: `trap_column` true = a column added only to test the framework, its name ending in `_trap_<kind>`; false = the trap sits in real columns (age's inverted U, nationality's rare level, income's eligibility gap, logins' Simpson and drift), which keep their real names (your choice) | spec → Trap summary; notebook §8 |
| Single-column AUCs for activation targets | Every numeric column alone against the realised target (w = 3, one month, 20% sample), top 8 per target, next to the oracle, for card, digital, FX activation and current/savings reactivation | notebook §9 |
| Open point 2: moderate leak | `cc_campaign_response_score_trap_leak`, AUC 0.877 (set 0.875) against the oracle's 0.842 | spec → Trap summary; notebook §8 |
| Open point 3: as-of misalignment | `loan_personal_bal_trap_shifted` holds next month's `loan_personal_bal`; AUC 0.945 for openings next month against the oracle's 0.766; null where there is no next month | same |
| (found by the audit of this round) | The higher exits exposed a flaw: the starting book's tenure (a Beta share of adult life per profile) wasn't the turnover's steady state, so shares of products built up over tenure drifted down (traditional wealth, Private: 0.60 → 0.49 by month 24). Tenure and age now come from the turnover itself: tenure exponential at the entry rate, clients joining younger than the book's mean age by its mean tenure. That drops 9 parameters (the Beta pairs, the fixed −5-year shift); tenure, age and shares now hold, and the holdings family checks shares at the last month too | spec → Population; notebook §3 |
| Open points 1, 4, 5 | Exits stay random; dirty defects stay out of the rollups (a stated limit); loan rates and login levels accepted. The round-1 decisions (`onboarding_channel`, the revolver cap, relaunch × 1.8, FX loading, calendar terms on adoption only, medians at trait means) are taken as confirmed and now live in the spec | spec |

## 2. Simplicity: code against effect
Measured on the code and on a profile of the 5k preset (18.9 s in all).
| Item | Code | Effect | Outcome |
|---|---|---|---|
| Relevance rankings | ≈ 170 lines; half of `truth.json`; a read of every column for 20% of clients after writing | A ranking anyone can recompute from mart + oracle | Cut (your choice) |
| `separation` knob | ≈ 55 lines in generator, checks and a slow test | None at its only value, 1.0 | Cut (your choice) |
| Regression oracle | ≈ 170 lines + ≈ 60 of checks + a paths axis through 5 modules | 57% of generation time; the ceiling for next-3-month card spend | Kept (your choice): regression is the likely second task (OD-15) |
| Fields of `truth.json` nothing reads | ≈ 90 lines (turnover records, drift and null-rule copies, the column → module mapping) | Copies of the spec or the doc | Cut |
| Exact medians (`scipy.stats.exponnorm` offsets) | ≈ 45 lines + ≈ 40 of checks | Medians land exactly on your level table, so the table is readable and checkable | Kept |
| Starting book from each client's history (closed-form chain) | ≈ 35 lines | No long burn-in; holdings agree with tenure from month 1 | Kept |
| Dirty data, extra columns | ≈ 120 + 30 lines, off by default | The contract-check and scale tests need them | Kept |
| New-client ramp, market index, bonus trigger | ≈ 10–15 lines each | Small realism; each has its check | Kept: too small to matter |

## 3. Regenerate and check
```bash
source .venv/bin/activate
python -m synthetic --preset canonical --out data/01_raw/synthetic_canonical --checks
pytest                 # fast suite, ≈ 3 min
pytest -m slow         # canonical size, each check family in its own process, ≈ 15–20 min
```
- Generation takes ≈ 6 minutes at 100k; `--checks` then runs each family in its own process
  (10–15 minutes on a quiet Mac) and exits with an error if any row fails. Close memory-heavy apps
  first.
- The folder must be new or empty; `load_truth` refuses a dataset written by another generator
  version (now 0.4.0), so a stale `data/01_raw/` fails loud.

## 4. The review, in order
### 4.1 The checking notebook (`notebooks/00_synthetic_data.ipynb`, committed with outputs)
| Section | What right looks like |
|---|---|
| 1 Check tables | 8 families, 1,263 rows, `failed` 0 everywhere |
| 2 Population | Mass ≈ 87%, Private ≈ 1%; ages rise with wealth; digital onboarding 15% → 55% from Private to Mass; exit rates ≈ 0.7–1.1% a month, flat over the panel, entries 0.2 points above |
| 3 Holdings | Shares near the spec and flat (digital activity drifts up by design); holding shares jump at 5,000 AED (card, personal and auto loans) and 15,000 AED (home loan) |
| 4 Amounts | Medians ordered by subsegment, Private far above; card limits in tier bands that rise with income; booking identity exact (0.0000); revolvers mostly at 0.3–0.9 utilisation; outflow and card-spend mixes more extreme for Private vs Mass; remittance near 0 for UAE/GCC |
| 5 Time effects | Travel spend up in July–August, least for Mass; balances dip in summer; bills spike in September, January, April; mobile logins jump at 2026-01 |
| 6 Segments, Simpson | ≈ 25% of MM above the UM median; card chance rises with logins within each onboarding channel, falls pooled |
| 7 Mart columns | Kinds and null shares as in the null rule; `<NA>` shown to be a null (Int64, parquet int64 with nulls) |
| 8 Traps | The trap summary with `trap_column`; the leak, upstream, shifted, rare-level, Simpson, null-control and drift rows pass |
| 9 Oracle | AUCs below; calibration points on the diagonal; regression coverage rows pass; no single column reaches the oracle on an activation target |
| 10 Trajectories | Balances persist month to month, card spend varies, hidden traits drift slowly |

### 4.2 The spec (`docs/components/test_harness.md`)
Read the first four sections (Summary, How it works, Code map, Interface); then the details only
where the notebook raised a question.

### 4.3 The code
Follow the spec's Code map: `generate.py` → `mechanisms/holdings.py` → `mechanisms/amounts.py` and
what it calls → `mechanisms/mart.py` → `mechanisms/traps.py` → `truth/oracle.py` → one check family.

## 5. Standard targets at 100k
| Target (eligible at t) | Oracle AUC, w = 1 / 3 / 6 | Positive rows a month (w = 3) | Expected events in 6 months |
|---|---|---|---|
| `cc_acquire` (non-holders) | 0.867 / 0.846 / 0.833 | ≈ 1,900 | ≈ 4,700 |
| `td_acquire` | 0.747 / 0.745 / 0.743 | ≈ 830 | ≈ 1,700 |
| `wealth_digital_acquire` | 0.795 / 0.793 / 0.791 | ≈ 1,250 | ≈ 2,600 |
| `wealth_trad_acquire` | 0.885 / 0.882 / 0.881 | ≈ 130 | ≈ 280 |
| `ebanking_acquire` | 0.951 / 0.926 / 0.900 | ≈ 900 | ≈ 3,200 |
| `loan_personal_open` (all) | 0.766 / 0.766 / 0.768 | ≈ 2,100 | ≈ 4,400 |
| `loan_auto_open` | 0.718 / 0.716 / 0.714 | ≈ 510 | ≈ 1,000 |
| `loan_home_open` | 0.830 / 0.828 / 0.828 | ≈ 140 | ≈ 290 |
| `fx_activate` (dormant) | 0.744 / 0.743 / 0.740 | ≈ 1,740 | ≈ 3,500 |
| `digital_activate` (registered, dormant) | 0.826 / 0.795 / 0.799 | ≈ 5,140 | ≈ 15,900 |
| `cc_activate` (holders, dormant card) | 0.771 / 0.712 / 0.703 | ≈ 3,440 | ≈ 10,900 |
| `casa_reactivate` (dormant account) | 0.717 / 0.700 / 0.693 | ≈ 1,450 | ≈ 3,900 |

The AUCs moved a little from round 1 (traditional wealth and home loans up most), because age and
tenure now go together as they would in a real book. No target is flagged low-confidence (fewer
than 200 events in 6 months) at 100k; at 50k, `wealth_trad_acquire` and `loan_home_open` (≈ 140
each) would be. The leak columns beat the oracle on their own windows: 0.967 and 0.877 vs 0.842
(card acquisition, w = 3, one month); applications 0.899 and the shifted balance 0.945 vs 0.766
(personal-loan opening, next month). A leak needn't beat it on every window: the moderate leak only
ties it at w = 1 and falls below it at w = 6 (spec → Trap summary).

## 6. Decisions taken in this round (please confirm)
1. **Traditional wealth: 42 adoptions a month** (was 30). With the higher exits, 30 no longer
   covered the refills of leavers' holdings (≈ 33 a month); 42 keeps its leaving chance, and so
   its ≈ 33-year holding, as before.
2. **The moderate leak's AUC is fixed at 0.875**, not tied to the oracle's; at 100k that is
   ≈ +0.03 above it.
3. **The shifted column is null where the client has no next month** (it left, or the panel's
   last month). A real misaligned column would also be empty for the latest month, and that is a
   tell.
4. **The AUC range rule covers pooled oracle AUCs;** per segment it is checked at 100k only (in
   the 5k preset, a Private segment's oracle AUC can dip below 0.5 by chance).
5. **The book's tenure and age come from the turnover:** tenure exponential at the entry rate;
   clients join younger than the book's mean age by the mean tenure (was a fixed 5 years). This
   replaces a Beta per profile and is the only way shares stay flat. The spec's subsegment ages
   are now the book's mean ages; the youngest come out 1–2 years older, since nobody joins before
   18.
6. **`CLAUDE.md` §1** now says tied functions stay together past ~300 lines, a package with more
   than a handful of modules uses role subfolders (D-070), and work runs in parallel with
   subagents by default (D-071, your request).

## 7. Known limitations
- The oracle ignores two rare paths (losing and re-adopting a required product inside the window;
  an opening hidden by a maturity refilling a full set of 4 loan slots). Both make it slightly
  under-predict; boosting every mart column on top of the oracle never beat it (round-1 audit).
- Every check passes at 100k; a few statistical rows need that size.
- Dirty defects don't reach the rollups (a real upstream mart would roll up its own bad values).
- Generation peaks at ≈ 1.8 GB RSS (≈ 3 GB including compressed memory) at 100k.
