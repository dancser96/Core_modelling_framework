# Synthetic data — review guide

The review guide for the synthetic data generator (M1, D-067), version 0.4.0. Approved by the SDS
on 2026-10-19; the LDS reviews it next (summary on `worknotes/sync.md`). The spec and code map are
in `docs/components/test_harness.md`; history is in `docs/UPDATES.md` and D-056–D-071.

## 1. What it is
- A retail book of 100k clients over 24 months, written as an upstream-style feature mart: 147
  columns, one row per client per month.
- The code is in four role folders under `synthetic/src/synthetic/` (32 modules, D-070):
  - `spec/`: the rules, as plain data;
  - `mechanisms/`: the functions that simulate;
  - `truth/`: the oracle, the regression oracle and `truth.json`;
  - `checks/`: 8 check families, written from the spec and never from the generator's code.
- `truth.json` (55 KB) keeps only what can't be recomputed: the spec, calibration, column kinds,
  per-target oracle metrics and the dirty-data record.
- Traps of two kinds:
  - **Trap columns** (`trap_column` true), named `<column>_trap_<kind>`: two leaks (one strong,
    one moderate), the upstream target, the process leak (applications) and a column shifted one
    month ahead.
  - **Traps in real columns**, which keep their real names: age's inverted U, nationality's rare
    level, income's eligibility gap, logins' Simpson effect and drift.
- **The book is in steady state.** Monthly exits are 0.7 / 0.8 / 0.9 / 1.1% (Private → Mass),
  with entries 0.2 points above. Tenure is exponential at the entry rate, and clients join younger
  than the book's mean age by the mean tenure, so ages, tenure and shares stay flat over the panel.

## 2. Regenerate and check
```bash
source .venv/bin/activate
python -m synthetic --preset canonical --out data/01_raw/synthetic_canonical --checks
pytest                 # fast suite, ≈ 3 min
pytest -m slow         # canonical size, each check family in its own process, ≈ 15–20 min
```
- Generation takes about 6 minutes at 100k. `--checks` then runs each family in its own process
  (10–15 minutes on a quiet Mac) and exits with an error if any row fails. Close memory-heavy apps
  first.
- The output folder must be new or empty. `load_truth` refuses a dataset written by another
  generator version, so a stale `data/01_raw/` fails loudly.

## 3. The review, in order
### 3.1 The checking notebook (`notebooks/00_synthetic_data.ipynb`, committed with outputs)
| Section | What right looks like |
|---|---|
| 1 Check tables | 8 families, 1,263 rows, `failed` 0 everywhere |
| 2 Population | Mass ≈ 87%, Private ≈ 1%; ages rise with wealth; digital onboarding 15% (Private) → 55% (Mass); exits ≈ 0.7–1.1% a month and flat over the panel, entries 0.2 points above |
| 3 Holdings | Shares near the spec and flat (digital activity drifts up by design); holding shares by declared income jump at 5,000 AED (card, personal and auto loans) and at 15,000 AED (home loan) |
| 4 Amounts | Medians ordered by subsegment, Private far above; card limits fall in tier bands that rise with income; the booking identity is exact (0.0000); revolvers mostly at 0.3–0.9 utilisation; outflow and card-spend mixes more extreme for Private than for Mass; remittances near 0 for UAE/GCC clients |
| 5 Time effects | Travel spend up in July–August, least for Mass; balances dip in summer; bills spike in September, January and April; mobile logins jump at 2026-01 |
| 6 Segments, Simpson | ≈ 25% of MM above the UM median; the card chance rises with logins within each onboarding channel and falls when pooled |
| 7 Mart columns | Kinds and null shares follow the null rule; `<NA>` is a true null (`Int64` in pandas, `int64` with nulls in parquet) |
| 8 Traps | The trap summary with `trap_column`; the leak, upstream, shifted, rare-level, Simpson, null-control and drift rows pass |
| 9 Oracle | AUCs as in §4; calibration points on the diagonal; the regression coverage rows pass; no single column gets near the oracle on an activation target |
| 10 Trajectories | Balances persist month to month, card spend varies, hidden traits drift slowly |

Every table in the notebook states which columns it shows and which statistic.

### 3.2 The spec (`docs/components/test_harness.md`)
Read Level 1 (the summary) and Level 2 (how it fits together), about a fifth of the doc. Read
Level 3 only where the notebook raised a question.

### 3.3 The code
Follow the spec's code map (Level 3):
1. `generate.py`;
2. `mechanisms/holdings.py`;
3. `mechanisms/amounts.py` and what it calls;
4. `mechanisms/mart.py`;
5. `mechanisms/traps.py`;
6. `truth/oracle.py`;
7. one check family.

## 4. Standard targets at 100k
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

A target is flagged low-confidence below 200 events in 6 months. None is at 100k. At 50k,
`wealth_trad_acquire` and `loan_home_open` (≈ 140 each) would be.

Each leak beats the oracle on its own window:
- card acquisition (w = 3, one month): the strong leak 0.967 and the moderate one 0.877, against
  the oracle's 0.842;
- personal-loan opening (next month): applications 0.899 and the shifted balance 0.945, against
  0.766.

A leak needn't win on every window: the moderate leak only ties the oracle at w = 1 and falls below
it at w = 6.

## 5. Settled choices
| Choice | Why |
|---|---|
| The regression oracle is kept (57% of generation time) | It is the ceiling for next-3-month card spend, and regression is the likely second task (OD-15) |
| Exact medians (`scipy.stats.exponnorm` offsets) | Medians land exactly on the spec's level table, so the table can be read and checked |
| The starting book is built from each client's history in closed form | No long burn-in, and holdings agree with tenure from month 1 |
| Dirty data and extra columns, off by default | The contract-check and scale tests need them |
| Exits are random, not driven by traits | Kept simple; churn isn't a target |
| Traditional wealth: 42 adoptions a month | Covers the refills of leavers' holdings (≈ 33 a month), so it keeps its ≈ 33-year holding |
| The moderate leak's AUC is fixed at 0.875, not tied to the oracle's | About 0.03 above the oracle at 100k |
| The shifted column is null where a client has no next month | A real misaligned column would also be empty in the latest month, which gives it away |
| The AUC range rule covers pooled oracle AUCs only | A small segment's AUC can dip below 0.5 by chance; per-segment AUCs are reported, not ruled |
| The spec's subsegment ages are the book's mean ages | Nobody joins before 18, so the youngest subsegments come out 1–2 years older (LM 33 rather than 31) |

## 6. Known limitations
- The oracle ignores two rare paths, and both make it under-predict slightly:
  - losing and re-adopting a required product inside the window;
  - an opening hidden by a maturity, when a client's 4 loan slots are full.

  Boosting on every mart column on top of the oracle never beat it.
- Every check passes at 100k. A few statistical rows need that size.
- Dirty defects don't reach the rollups, whereas a real upstream mart would roll up its own bad
  values.
- At 100k, generation peaks at about 1.8 GB RSS, or about 3 GB including compressed memory.
