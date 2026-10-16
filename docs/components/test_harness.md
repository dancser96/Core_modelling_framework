# Synthetic data and test harness
**Status:** designing — spec settled 2026-10-14 (D-056); steps 0–2 done; steps 3–7 to be built in one go after the question round Q140–Q208, with one review at the end · **Legacy:** `tests/smoke_test.py` (stub-based — do not copy its stubs)
**Related:** [dataset](dataset.md) (time model) · [target factory](target_factory.md) · [EDA](eda.md) ·
[feature checks](feature_checks.md) · [environment](environment.md) · [config](config.md) · `tests/README.md` ·
D-014, D-041, D-056, D-057, D-062, D-064–D-066 · OD-15, OD-17

## Build plan

Status: `not started` · `in progress` · `in review` · `done`. Each step ends with `pytest` and `ruff`
green, the code-reviewer and simplicity-review (plus ml-correctness-auditor from step 4), docs and
worknotes updated, and a stop for the builder's review at the step's gate.

| Step | Builds | Proof (`pytest`, via the step's check table) | Builder's gate | Status |
|---|---|---|---|---|
| 0 | `synthetic` package skeleton, compat shim, local Spark session, parquet round trip | Dates, integers, doubles, strings, booleans and nulls survive pandas → parquet (month-partitioned) → Spark → pandas; `flaml` imports after `core_modelling` (T1); green on the Mac (the PC only when the builder switches, `docs/guides/setup_windows_wsl2.md`) | — | done |
| 1 | Population, client description, day counters, entry and exit, latent traits; the checking notebook | Same seed → identical data, other seed → different; mix within CI (subsegment; nationality group, employment, emirate and salary transfer per profile; top country); day counters grow by exactly the days in the month; relationship ≤ residence ≤ age; residence nulls; income missingness and medians; residence gap; latent stationarity and month-to-month persistence per profile; income slope on the wealth trait (new clients); entry and exit rates per profile, read from the mart; no crash with months without new clients; every function typed and documented | Does it look like our book? | done |
| 2 | Holdings and states: current/savings, credit card, loans, term deposit, wealth, e-banking, FX and digital activity | Rules that always hold (statuses and their transitions, account counts and maturities, no early settlement, digital only with e-banking, product count); realised events match the oracle's chances, overall and per chance decile, and the oracle sets a chance exactly where the mart shows a client at risk; shares per profile near the spec and flat over the panel; steady-state event volumes near the spec; the income-threshold jump and exemptions; churned vs never; the onboarding wave; expected positives per target | Rates and dynamics | done |
| 3 | Monthly flows, balances, subcategories, logins | Exact zeros for non-holders and dormant clients; subcategories add up exactly; lag-1 autocorrelation; Hill estimate of the tail index within ±30%; amount / (1 + balance) within quantile bounds; within-segment Spearman signs; pooled vs within-segment differ as configured; medians ordered by subsegment | Does it look like our book? | not started |
| 4 | Feature mart: rollups, names, history, null rule, month-partitioned parquet | An independent Spark recompute matches every rollup (T8); every name parses with the grammar; column-list snapshot; **prefix stability**: 20 and 24 months from the same seed give identical months 1–20, except the declared leak columns; the null rule holds | Names and columns | not started |
| 5 | Traps, seasonality, drift, dirty-data switches | Every trap meets its expected behaviour in the trap table | — | not started |
| 6 | Ground truth and the oracle file, including the regression target's true mean and quantiles | Oracle AUC pooled and per segment; the leaks beat the oracle; oracle probabilities match realised events per decile; regression oracle covers its realised values at the stated quantiles; `truth.json` schema | — | not started |
| 7 | Canonical dataset, `conf/local/` mapping, Spark fixtures, budgets | The canonical mart read through the source mapping: 24 partitions, row count, column list; runtime, memory and disk within budget | M1 done | not started |

**Checks as data.** Each step adds a `check_*` function that returns a table: check, stratum, `n`,
expected, realised, tolerance, passed. `pytest` asserts every row passes; the checking notebook shows
the same tables with charts, so tests and review evidence can't drift apart. Expected values are
restated from the spec and read from the mart, never taken from the generator's own functions or
records. The check tests run at the canonical size: in the 5k preset many Private strata are too
small to show anything. Tolerances come from sampling theory: 4.5 standard errors, a family-wise
false-failure rate of about 0.1% over step 1's ~155 rows (no failing seed among 0–5 at 100k). Each
new check is shown to fail on a deliberately broken generator before it counts. With the fixed test
seed a failing row is a generator bug, never a tolerance to widen. Each step's checks have their own
module (`checks_<step>.py`), with the shared table logic in `check_table.py`.

**Checking notebook** (`notebooks/00_synthetic_data.ipynb`, dev only, temporary): generates a
preset, shows the check table, and gives a simplified EDA (null shares and quantiles per column,
aggregations and cross-tabs by subsegment and month, distributions, a few client trajectories, the
hidden traits). Inline pandas and plotly only, no function definitions. The guided EDA notebook
replaces it once EDA exists.

Framework tests later assert against the ground truth: screens flag every trap, the top oracle
drivers rank near the top, null controls rank near the bottom, and no model beats the oracle AUC.

## Purpose
Real data never leaves the bank, so everything outside it runs on synthetic data with **known ground
truth**, through **real** local PySpark. In the crunch, stubs hid every environment bug (T15).

The generator plays the upstream data owner. It writes the kind of **feature mart** retail use cases
read inside the bank, so every stage meets realistic shapes: nulls, collinear rollups, wide tables,
rare levels. It is not just a test fixture; it **drives development**:
- It is generated once into `data/01_raw/` and read by every stage, notebook and demo exactly as real
  data will be read. On a laptop, `conf/local/` maps the logical source to it.
- Its outputs (EDA, checks, models, monitoring) are how changes get judged, not just whether code
  runs.
- It makes EDA, Feature Checks and the leakage screens *verifiably sensible*: skewed targets,
  correlated heavy-tailed amounts, clear segments, planted traps.
- 24 consistent months support observation windows, client-grouped splits, OOT validation,
  calibration, inference and monitoring with matured labels ([dataset](dataset.md) time model).

## Phase 2 requirements
1. **An upstream-style feature mart**, one wide table per entity: one row per client per month, from
   the client's first month until exit, with the client description, current-month values and
   backward rollups. **No targets**: Target Factory builds them from the current-month columns, so
   that stage gets tested too. The one exception is a target built "upstream" (trap F22).
2. **Size:** `canonical` ≈ 100k clients × 24 months (≈ 2.4M rows); `n_clients` scales it (e.g. 50k on
   an 8 GB laptop); `unit` ≈ 5k × 24 for tests. Backward windows ≤ 6 months.
3. **Width ≈ 150 columns** including traps, plus an off-by-default switch that adds many weak or noise
   columns for scale tests.
4. **Segmented population** with the realistic mix below. Latent traits are correlated within each
   segment and differ between segments, so pooled and within-segment relationships diverge.
5. **Heavy-tailed, coherent amounts:** power-law tails, rank-correlated through shared traits; no
   zero-balance client transacts millions.
6. **Sticky holdings and usage:** switching is rare, active and dormant spells are long, and the
   zero ↔ non-zero transitions are explicit and recorded.
7. **Exact zeros** for non-holders and dormant users. **Nulls only where the retail data has them:**
   months before relationship start (and rollups reaching into them), missing income, ratios with no
   denominator, the declared quality traps.
8. **Rare categorical levels** (Zipf frequencies).
9. **Time consistency:** fixed client descriptors, day counters that grow by the days in the month,
   entry and exit, seasonality, optional drift.
10. **Rare to semi-rare events** (adoption, activation, reactivation), each with a controllable rate.
11. **Planted traps,** each switchable and recorded in the ground truth.
12. **Deterministic from a seed**, generated month by month: a month never depends on later months,
    except the declared leak columns.
13. **Ground truth:** `truth.json` plus a per-row oracle file. The oracle is never mapped as a source;
    it would be a leak.

## Design constraints
- **A top-level `synthetic/` package**, dev-only and not part of `core_modelling` (D-041). Its own
  editable install (`synthetic/pyproject.toml`, `synthetic/src/synthetic/`). Modules so far:
  `presets` and `products` (the spec), `population`, `latents`, `hazards` (each client's monthly
  chances and their calibration), `holdings`, `generate` (the month loop), `check_table` plus
  the checks per step (`checks_population`; `checks_holdings`, `checks_holding_drivers` and
  `holding_events` for step 2). Flows, mart (rollups + names), traps, truth and write arrive
  with their steps. Whether it travels in the release zip is decided with OD-04.
- **Libraries:** numpy, pandas, pyarrow; scipy pinned on first use (D-042).
- **One random stream per mechanism** (population, latents, later holdings, flows, traps), spawned
  from the seed (`SeedSequence.spawn`) and passed explicitly; no global random state. New mechanisms
  append a stream, which leaves the earlier ones identical, so a later step never re-draws an
  earlier step's columns. Within a stream, draws happen in a fixed order, month by month.
- Vectorised over clients; the only loop is over months. Memory stays bounded: one month of clients
  plus a 6-month history buffer, written month by month.
- **The population and products are a plain-data spec** (`presets.RETAIL`), so another domain or
  entity is another spec, not new code. Products drive three small chain functions: a 0/1 holding
  chain, an account-count chain and an active/dormant usage chain.
- **Column names come from one grammar** ([below](#names)), built from parts, so renaming is a
  one-place change.
- Spark doesn't generate anything. It reads what was written, through the environment adapter.
- **Every mechanism has its term in the oracle.** A mechanism the oracle doesn't know about makes the
  oracle stop being the ceiling.

---

## Population and client description

### Segment mix
Shares are fixed; client counts scale with `n_clients`. `segment` has 3 levels; `subsegment` has 9,
ordered by wealth. Both are fixed for all months. The Private and Priority Upper/Lower split is a
mock-up. Private is sized at 1k for significance; the smallest stratum (Upper Private, 250) still
exercises minimum support per stratum (D-050).

| Segment | Subsegments (wealthiest first) | Share | Clients at 100k |
|---|---|---|---|
| Private | Upper / Lower | 0.25% / 0.75% | 250 / 750 |
| Priority | Upper / Lower | 1% / 3% | 1,000 / 3,000 |
| PSB | UA / A / UM / MM / LM | 4.3% / 4.3% / 20.5% / 61.6% / 4.3% | 4,300 / 4,300 / 20,500 / 61,600 / 4,300 |

### Mix by profile
Subsegments share their mixes, turnover and latent spread through four profiles. The values live in
`synthetic/src/synthetic/presets.py`; they are ballpark, close to public UAE figures without copying
any bank's book. ARAB means Arab nationalities outside the UAE and GCC, only slightly wealthier than
ASIA; WESTERN peaks in Priority. The emirate is drawn independently of residence status and
nationality: "Others" is about equally common across them.

| Profile | Subsegments | Nationality: ASIA / ARAB / WESTERN / UAE / GCC / AFRICA / OTHER | Employment: Employed / Self-employed / Unemployed / Retired / Other | Emirate "Others" | Salary transfer (employed) | Non-resident |
|---|---|---|---|---|---|---|
| private | Upper, Lower Private | 15 / 8 / 20 / 40 / 12 / 3 / 2 | 25 / 30 / 10 / 20 / 15 | 25% | 30% | 15% |
| priority | Upper, Lower Priority | 30 / 12 / 28 / 18 / 6 / 3 / 3 | 55 / 22 / 8 / 7 / 8 | 7% | 50% | 3% |
| affluent | UA, A | 50 / 14 / 12 / 14 / 3 / 4 / 3 | 76 / 13 / 4 / 3 / 4 | 11% | 65% | 0% |
| mass | UM, MM, LM | 74 / 12 / 1.5 / 4 / 0.5 / 7 / 1 | 91 / 5 / 1.5 / 1 / 1.5 | 11% | 70% | 0% |

Overall at 100k, first month: ASIA 70%, ARAB 12%, AFRICA 6.6%, UAE 5.8%, WESTERN 3.6%, OTHER 1.3%,
GCC 1.1%; Employed 88%, Unemployed 2% (1.7% of PSB, 11% of Private), Retired 1.6% (19% of Private);
Dubai 51%. Median declared income of an employed client, AED a month: Upper Private 150k, Lower
Private 90k, Upper Priority 60k, Lower Priority 40k, UA 30k, A 20k, UM 12k, MM 6k, LM 3k
(Self-employed × 1.3, Retired × 0.5). Income is missing for 2% of Employed, 10% of Self-employed,
80% of Unemployed, 60% of Retired and 85% of Other clients, and for 30% more of Private clients.

### Client description
| Field | Generation | Notes |
|---|---|---|
| `age` | Birth month from a truncated normal per subsegment (18–85); whole years, changes in the birth month | PSB youngest, Private oldest |
| `residence_days` | Days since arrival in the country; grows by the days in each month. Arrival comes before the relationship by a varied gap: 60% open an account within months of arriving (exponential, mean 0.3 years), the rest had lived here for years (mean 4 years) | Null for UAE nationals and non-residents (table above). Gap: median ≈ 0.4 years, 10% over 5.6 years |
| `relationship_days` | Days since relationship start; grows by the days in each month | ≤ residence for residents; ≤ age |
| `nationality_group` | ASIA, ARAB, WESTERN, UAE, GCC, AFRICA, plus a rare OTHER; mix per profile | ASIA dominates PSB; UAE leads Private; WESTERN peaks in Priority |
| `nationality` | ~60 countries, Zipf within the group (F1) | Many levels, rare levels |
| `employment_status` | Employed, Self-employed, Unemployed, Retired, Other (mostly investors); mix per profile | Unemployed and Retired concentrated in Private |
| `income` | Declared monthly income, static | Missing not at random (mostly Other, Unemployed and Private), plus a little random missingness |
| `salary_transfer_flag` | Employed only; the salary credit ≈ income sits inside inflow (F2) | |
| `emirate` | The 7 emirates plus Others (outside the UAE or unknown); mix per profile (F8) | Dubai-heavy; Others 25% / 7% / 11% in Private / Priority / PSB |

**Entry and exit, higher for the lower segments:** monthly exits 0.2% / 0.4% / 0.6% / 1.0% and
entries 0.4% / 0.6% / 0.8% / 1.2% (private / priority / affluent / mass), so between ≈ 2.4% and
12% of clients leave a year. Every profile grows ≈ 0.2% a month, so the mix stays flat. New clients
start at relationship day 0; leavers' rows stop. `n_clients` is the size 13 months before the panel
starts (≈ 103k at month 1 for 100k). Dormant clients stay on the books with zero activity.

### Income thresholds (half-strict eligibility)
Credit cards and the three loans have a minimum income ([rates](#product-rates)). Below it, the
odds of adopting are a fifth of those above; at the threshold they jump. Clients without a declared
income count as above if they are Private or Priority, Retired or Other (mostly investors), and as
below otherwise. A plain `income >= X` eligibility filter therefore drops the exempt ones silently
(Spark treats a comparison with null as not true): a realistic trap that the eligibility step log
must make visible.

## Products and behaviour
| Product | Kind | Generated | Derived / target |
|---|---|---|---|
| Current/savings (CASA) | Near-universal stock + flows | Balance; inflow and outflow by subcategory | |
| Credit card (`cc`) | 0/1 holding with an onboarding wave + active/dormant usage (step 3) | Limit, utilisation, revolver flag (F4); spend by subcategory; inflow = repayment ≈ last balance × repayment rate | Utilisation null without a card |
| Personal / auto / home loan | Active account count | Openings; closures at maturity (term-driven, no early settlement); amortising outstanding balance; months to maturity (F5) | Target: the count goes up |
| Term deposit | 0/1 holding + balance | | never / churned / active |
| Digital wealth, traditional wealth | 0/1 holding + assets under management; Retired clients lean to traditional wealth | | never / churned / active |
| FX | Activity only, active/dormant | Monthly count and volume; driven by the cross-border trait, travel spend and nationality | Dormancy on ≤ 6-month windows |
| E-banking / digital | Registration (0/1, onboarding wave) + digital activity (active/dormant) | Online and mobile login counts; days since last login, `-1` for never (F7) | |
| Remittance | Subcategory of account outflow | Amount and count (F3) | |

Also derived: the number of products held (F6).

- **Never / churned / active** (term deposit and both wealth products). Each client's history runs
  from relationship start, so some clients held the product before month 1. Acquisition is one
  target (0 → 1), whether the client never held the product or churned; churned clients adopt at
  twice the odds, so the status carries signal.
- **Onboarding wave** (credit card, e-banking): many new clients take the product in their first 3
  months, up to their steady-state share; after that, adoption is low. Other products build up over
  each client's tenure from "never held" at relationship start, for new and existing clients alike.
- **Loans:** no top-ups and no opening dates. Target Factory's rule kinds are therefore a threshold on
  a forward sum, and a flag or count going up ([target factory](target_factory.md)).
- **What an event is in the mart** (the oracle prices exactly these):
  - a 0/1 product is acquired when its flag is 1 in any month of the window, for a non-holder at
    the observation month; an end-of-window rule misses ≈ 1–10% of acquisitions (lost again);
  - a loan opens when its count rises in any month of the window; an account maturing in the
    same month hides an opening (≈ 0.5% of personal loans), which makes `maturity_months`
    predictive under a "count at the end" rule;
  - a new client's entry-month events sit on its first row, not in a month-on-month move;
  - a loan's closing is fixed by `maturity_months` (no early settlement): a closing target would
    score AUC 1 from an as-of feature, so it is degenerate, not a leak;
  - targets for status products are built from the flag, so lineage exclusion doesn't drop the
    status column and its legitimate churned signal.
- **Subcategories** are persistent per-client shares that add up exactly:
  - card spend: travel / retail / online / dining;
  - account outflow: remittance / cash / bills / transfers;
  - inflow: salary / transfers / other.
- **Autocorrelation:** month-on-month correlation ≈ 0.9+ for log current/savings balances and
  ≈ 0.6–0.8 for log flows in active months.
- **Seasonality:** a month-of-year profile per measure: summer travel peak (July–August; balances
  dip), December spend, January bonus inflow.
- **Latent traits** (`D = 5`): wealth, transactional activity, digital, credit appetite, cross-border.
  They shift by subsegment, nationality group and employment.

### Product rates
From public UAE ballparks (D-064), mostly surveys and partly dated: about 53 credit cards per 100
adults; low personal-loan penetration among expats, since banks prefer salary-transfer clients for
unsecured lending; about 30% of residents own a home, often bought in cash; mobile banking used by
about 72–90% of residents; low penetration of investment products. Sources:
[cards](https://thenationalnews.com/business/uae-credit-cards-among-costliest-1.494195),
[personal loans](https://arabianbusiness.com/gcc/lending-less-407739),
[home ownership](https://gulfnews.com/business/property/70-of-uae-residents-still-opt-to-rent-rather-than-buy-homes-1.1863459),
[mobile banking](https://expatica.com/ae/finance/banking/mobile-banking-in-the-united-arab-emirates-72232),
[investment products](https://www.marmoremena.com/uae-asset-management-industry-an-overview/).
Exact levels matter much less than the dynamics and correlations working.

**As few numbers as possible per product** (D-065), values in `synthetic/src/synthetic/products.py`:
the share held per profile; for 0/1 products the adoptions a month in a 100k book (credit card and
e-banking: after onboarding); for loans the term. How long a holding lasts is derived. Adoptions
that refill the holdings of clients who left the bank count towards the volume.

| Product | Minimum income (AED a month) | Held at month 1 (private / priority / affluent / mass) | Set | Derived | Realised a month per 100k |
|---|---|---|---|---|---|
| Current/savings | — | 99% everywhere | — | — | — |
| Credit card | 5,000 | 85 / 80 / 65 / 30% | 500 adoptions a month after onboarding | held ≈ 6 years | ≈ 520 after onboarding, ≈ 720 with it |
| E-banking | — | 80 / 90 / 90 / 75% | 120 registrations a month after onboarding | held for decades | ≈ 130 after onboarding |
| Term deposit | — | 40 / 30 / 15 / 4% | 260 adoptions a month | held ≈ 2.5 years | ≈ 280 |
| Digital wealth | — | 10 / 20 / 12 / 2% | 400 adoptions a month | held ≈ 10 months | ≈ 400 |
| Traditional wealth | — | 60 / 35 / 10 / 1%, higher for Retired | 30 adoptions a month | held ≈ 33 years | ≈ 43 (≈ 32 net of the book's growth) |
| Personal loan (≥ 1 account) | 5,000 | 5 / 10 / 20 / 20%, mostly salary-transfer clients | 48-month term (UAE maximum) | — | ≈ 680 new loans |
| Auto loan | 5,000 | 3 / 8 / 12 / 6% | 60-month term (UAE maximum) | — | ≈ 160 new loans |
| Home loan | 15,000 | 15 / 20 / 10 / 2% | 300-month term (UAE maximum for expatriates) | — | ≈ 50 new loans |
| FX activity | — | Active: 60 / 45 / 30 / 12% | Mean active spell 24 months | — | — |
| Digital activity | — | Active: 80% of e-banking clients | Mean active spell 36 months | — | — |

Realised volumes run a little above the set ones because the book grows ≈ 0.2% a month and its
tenure mix is younger than its long-run mix, so products that build up over tenure keep growing
(the volume check nets that growth out). Loans set by term put the volume where the share and term
imply: personal loans come out near 680 a month, above the ≈ 400 first discussed. Private clients'
personal loans run off over the panel (≈ 6% → 4%) because the book ages and the chance peaks in
the mid-30s.

**Holdings at month 1 agree with income, traits and tenure.** Starting holdings come from the same
chances as later adoption, income threshold included (maths §3). Loan holders at the start
therefore sit mostly above the threshold, with the same half-strict leak below it as new loans.

### Second entity (optional, M3; likely not needed)
If it is ever needed, a smaller subsidiary: ≈ 30k clients, PSB-like profiles only (no Private), more ARAB and AFRICA
clients, no traditional wealth or home loans, ≈ 100 columns with a few differently named ones (e.g.
the income column). It is another spec dict in `presets.py`, generated and written separately, so it
tests that entities are never merged (D-034) and that sources differ by entity.

---

## The maths

Notation: client `i`, month `t`, subsegment `s`, product `k`, latent dimension `d = 1..5`. `σ(x)` is
the logistic function.

### 1. Latent traits
```
z_i ~ N(μ_s + shift(nationality_group, employment), Σ_s),   Σ_s = D_s R_s D_s,   L_s = chol(Σ_s)
```
Each subsegment has its own mean; scales and the **correlation matrix `R`** are set per profile, with
every correlation between traits kept within [0, 0.2] (the wealthy profiles decouple wealth from
credit appetite). A `separation` knob scales the distances
between the means; it controls how much pooled AUC inflates over within-segment AUC (arrives in
step 3, where pooled vs within-segment relationships are checked).

### 2. Persistence over time (stationary AR(1))
```
z_i,t = m_i + ρ (z_i,t−1 − m_i) + sqrt(1 − ρ²) · L_s ε_i,t,     ε ~ N(0, I)
```
`m_i` is the client's mean from §1; scalar `ρ` ≈ 0.95 a month keeps the stationary distribution exact.
Segments never change.
- **Entry and exit:** each month a client exits with its profile's probability, and each subsegment
  gains `Binomial(n_s, entry rate of its profile)` new clients; entrants draw `z` from their
  stationary distribution and start at relationship day 0.
- **Burn-in:** `B` months (default 12) are simulated before month 1 and discarded from the output.
  They put latents, holdings and balances in steady state and provide the history that month 1's
  rollups need.
- **Pre-panel holding history:** the starting book's holdings are drawn from each client's history
  since relationship start (maths §3).

### 3. Holdings and accounts
Every product has one monthly chance per client, on the log-odds scale:
```
logit p_i,k,t = α_k,profile + Σ_d β_k,d · z_i,d,t + age_k(age_i,t) + effects_k(descriptors_i)
                + log(0.2) · below_threshold_k(i) + log(2) · churned_i,k
```
- `age_k` is a slope per decade or an inverted U around a peak (personal and auto loans peak in the
  mid-30s, home loans at 42); `effects_k` are salary transfer (credit card, personal loans),
  nationality (home loans) and Retired (traditional wealth). The churned term applies to status
  products only.
- **0/1 products:** a holder leaves with the product's leaving chance `q_k`; a non-holder adopts with
  `p`. `q_k` = (adoptions a month − refills of holders who left the bank) / holders, from the spec.
- **Loans:** each month accounts that reach their term close (no early settlement), then at most one
  account opens with chance `p`; each account runs the product's fixed term.
- **Usage:** a dormant client wakes with `p`; an active one lapses with
  `σ(logit(1 / mean active months) − 0.5 · score)`, so keen clients stay active longer.
- **Onboarding wave** (credit card, e-banking): in a new client's first 3 months the chance is the
  constant `1 − (1 − π_i)^(1/3)` that reaches the client's steady-state share `π_i = p / (p + q)`.
- **History and starting book:** other 0/1 products follow never → held ⇄ churned from relationship
  start; with monthly chances turned into rates the chain has a closed form for the chance of
  holding (and of having churned) after `T` months of tenure. The starting book draws each client's
  state from it, and loans as `Poisson(p × min(T, term))` accounts opened uniformly in that window.
- **Calibration:** one bisection per product and profile on the intercept `α`, on the starting book:
  the mean held-after-tenure chance (or the steady-state share, with onboarding; the mean number of
  accounts, for loans; the active share, for usage) equals the spec. The chances are recorded per
  row in the oracle.
- Sizing rule, recorded in the ground truth: every target keeps ≳ 200 events in a 6-month window at
  the canonical size, or is flagged as low-confidence.

### 4. Balances (stocks): lognormal body, power-law tail
For holders of a balance product:
```
log X_i,k,t = λ0_k + λ_k·z_i,t + η_i,k + ν_i,k,t
B_i,k,t     = X_i,k,t · W_i,k,       W_i,k ~ Pareto(x_m = 1, a_k)   (drawn once per client-product)
```
`η` is a persistent client effect; `ν` is small monthly noise (itself AR). By **Breiman's lemma**, a
lognormal times an independent Pareto has a regularly varying tail with index `a_k`, so
`P(B > x) ~ x^(−a_k)`: a true power-law tail on a lognormal body. `W` is persistent, so balances
don't jump. Non-holders: exactly 0.

### 5. Usage (flows): persistent active/dormant states, overdispersed counts, coherent amounts
```
P(active_t = 1 | active_t−1 = 0) = σ(ψ0_k + ψ_k·z_i,t + season_t)     wake-up (rare)
P(active_t = 0 | active_t−1 = 1) = σ(ω0_k − ω_k·z_i,t)                 lapse (rare)
N_i,k,t      = active · (1 + Poisson(λ·G)),   G ~ Gamma(θ, 1/θ),   λ = exp(κ0_k + κ_k·z + season_t)
log T_i,k,t  = τ0_k + φ_k · log(1 + B_total,i,t) + τ_k·z + ξ,      ξ ~ N(0, s_ξ²)
amount       = N · T,     subcategory amounts = amount · share_i   (share_i ~ Dirichlet, per client)
```
- **Persistence:** active spells last `1/p_lapse` months on average, dormant spells `1/p_wake`.
  Calibrate `ψ0_k` and `ω0_k` to a target active share and a mean active spell of two years or more.
- **Zero ↔ non-zero events are recorded:** first activation, dormancy, reactivation.
- Gamma–Poisson gives negative-binomial overdispersion. **Coherence:** the ticket size scales with
  the client's own total balance (elasticity `φ ∈ (0, 1)`), so low-balance clients have small
  tickets.

### 6. Seasonality and drift
- `season_t` is a month-of-year profile per measure, applied on the log / logit scale.
- **Drift** (F23): a gradual digital-uptake trend, and a step in login counts from month `t0` (an app
  relaunch). Ground truth records the feature, `t0` and the size.

---

## Feature mart

### Names
`{measure}_{product}[_{subcat}]_{kind}_{a}_{b}_months_{agg}`, e.g.
`outflow_cc_travel_vol_0_2_months_avg`.
- `kind`: `vol` (amount), `cnt` (count), `bal` (balance), `flag`.
- `a_b`: months back, `0` = the current month. Backward windows include the current month (T8):
  `0_0` (current month), `0_2`, `0_5`.
- `agg`: `avg`, `sum`, `max`, `min`, `std`, `nz` (number of non-zero months).
- Also `months_since_last_{measure}_{product}[_{subcat}]` (null when there was no non-zero month since
  joining) and one ratio form, `{…}_0_2_vs_3_5_months_ratio`.
- Client-description fields keep plain names (`age`, `segment`, …).

`avg` comes for every measure; the other aggregations only for a chosen subset, to stay near 150
columns.

### Null rule and history
Monthly values before relationship start are null, so **a rollup whose window reaches before
relationship start is null**. This mirrors the retail dataset; the framework does not enforce it.
Note for any Spark recompute: `avg` ignores nulls, so the step-4 cross-check counts the months in the
window explicitly. Clients already on the books at month 1 have complete windows, from the burn-in
months. So the whole 24 months are usable: with `w = 3`, a 6-month window (months 1–6), validation
month 9, scoring months 10–21 whose labels
mature by month 24.

### Physical form
Parquet partitioned by `snapshot_month` (a date, the first of the month), written one month at a
time. `conf/local/` maps the logical source to it (step 7). `truth.json` and the oracle files sit
next to it and are never mapped.

## Planted traps
Each is switchable and recorded in the ground truth.

| Trap | Construction | Expected behaviour |
|---|---|---|
| Calibrated leak (F17) | `L = μ_L · y_fwd + N(0, σ_L²)`, `y_fwd` = adoption in `(t, t+w]`, `μ_L/σ_L = √2 · Φ⁻¹(AUC_target)` | Univariate AUC ≈ target (e.g. 0.97); the leakage screen flags it |
| Process leak (F16) | Loan applications this month: an opening at `t+1` is preceded by an application at `t` with probability `p_app`; a few applications never open | Beats the oracle; leakage screen plus human review |
| Upstream target (F22) | One target built "upstream" (e.g. card activation in the next 3 months); its source columns listed in the ground truth | The "Target Factory skipped" path; lineage exclusion (T12) |
| Inverted U (F18) | Age effect on personal-loan adoption peaks in the mid-30s | Spearman ≈ 0, mutual information high |
| Simpson's reversal (F19) | Logins vs card activation: positive within subsegment, negative pooled | Stratified EDA views show the reversal |
| Rare high-rate level | A nationality below `f_rare` with a large adoption effect | Stands out in event rate by level; unstable in CV |
| Null controls (F20) | Independent columns with the marginals of real ones (lognormal, zero-inflated count, Zipf categorical) | Univariate AUC ≈ 0.5; ranked last |
| Quality (F21) | A near-constant flag (99.9% one value) and an all-null column | Flagged by the quality checks |
| Drift (F23) | §6 | PSI > 0.25 after `t0`, ≈ 0 before |
| Collinearity (organic) | Rollups of one measure over `0_2` and `0_5`; exact identities: `<product>_status == "active"` ⇔ `<product>_flag`, `product_cnt` = sum of the product flags and loan counts > 0 | Correlation views and VIF flag the clusters (VIF is infinite for the identities) |
| Eligibility-defining (organic) | Product-specific flows are 0 for non-holders (T11); the product's own flag under its acquisition eligibility; `loan_<type>_maturity_months` (all null) under "first loan"; `digital_active_flag` under `ebanking_flag == 0`; `fx_active_flag` under FX activation | Constant within the eligible population; flagged. A status column only loses its "active" level and must not be flagged dead (never vs churned is signal). truth.json records each column's "function of holding" so the flag can be asserted |
| Null-income eligibility (organic) | [Income thresholds](#income-thresholds-half-strict-eligibility) | The eligibility step log shows the drop |
| Dirty switches (F24), off in canonical | Duplicate client-months; a month with the digital columns null (outage); income × 12 from `t0` (unit change); typo outliers | Contract checks fail loud; operational monitoring flags them |

Later: a column shifted one month forward (F25, as-of misalignment) and an interaction-only feature
(F26).

## Ground truth and oracle
- **`truth.json`:**
  - seed, preset, `n_clients`, generator version, numpy and scipy versions (the seed-to-data
    mapping depends on them);
  - the column schema: name, kind (`id` / `time` / `static` / `holding` / `stock` / `flow` /
    `categorical` / `trap` / `noise`), generating mechanism;
  - segments and latent parameters (`μ`, `D`, `R`, `separation`, `ρ`), entry and exit rates;
  - per product: calibrated parameters, thresholds, realised event rates per month and segment,
    expected positives;
  - per product and event: the **oracle relevance ranking** (Spearman of every feature with the true
    hazard at the reference month) and the **oracle AUC** (true window probability against realised
    events, pooled and per segment);
  - traps (columns, type, parameters), drift, the null rule.
- **Oracle file** (`oracle/`, parquet): per client and month, the hidden traits (`z_*`) and the
  chance applied to every event that month, given the state at the end of the previous month
  (`p_<product>_acquire`, `p_<loan>_open`, `p_<usage>_activate` / `_lapse`; null where the client
  was not at risk). Row `t` holds the chance of the move into month `t`, which the month-`t`
  features already show; never join it to an observation at `t`.
- **Window probability** (built in step 6, keyed to the observation month so no consumer shifts
  rows): for an observation at `t`, `1 − ∏(1 − p̃_s)` over `s = t+1 … t+w`, where `p̃_s` is the
  chance the client would face with its state frozen at `t` (never / churned as at `t`, onboarding by
  tenure, loan slots and maturities as scheduled at `t`), on the realised trait path. Multiplying
  the recorded rows instead conditions on the outcome (after an event the rows go null or change)
  and understates positives: card acquisition AUC 0.71 instead of 0.81, which would make sound
  models "beat the oracle". Clients who leave inside the window follow Target Factory's rule
  (default: target null, so the oracle conditions on staying). The oracle conditions on the
  realised trait path, which is still a valid upper bound because traits and exits get no feedback
  from holdings (difference ≈ 0.002 AUC); the regression oracle's Monte Carlo integrates over the
  path instead. This also serves OD-17: each sampling option's bias and calibration can be measured
  against the truth.
- **Regression target** (D-060; supported whatever OD-15 settles): card spend over the next 3 months
  among card holders. It is heavy-tailed with many exact zeros from dormancy, a natural case for a
  quantile loss. The oracle file carries its true mean and 10% / 50% / 90% quantiles per client and
  month, from a Monte Carlo of the forward chains starting at the true state. Target Factory builds
  the target itself from the current-month columns (a forward sum).

**The oracle AUC is the ceiling.** A model or univariate screen that beats it is almost certainly
leaking.

## Interface
```python
PRESETS: dict[str, dict]                  # "unit", "canonical": spec, n_clients, n_months

def generate_mart(preset: str = "unit", n_clients: int | None = None,
                  seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (mart, oracle, truth) in memory. The oracle holds the hidden per-row truth."""

def check_population(mart, oracle, truth) -> pd.DataFrame:     # step 1
def check_holdings(mart, oracle, truth) -> pd.DataFrame:       # step 2 (events: holding_events)

# planned (step 7)
def write_mart(out_dir: str, preset: str = "canonical", n_clients: int | None = None,
               seed: int = 0) -> dict:
    """Generate month by month, write the partitioned mart, truth.json and oracle; return truth."""
```
Arguments arrive with the steps that need them (traps in step 5, `n_months` for the prefix-stability
test in step 4). A small CLI (`python -m synthetic --preset canonical --n-clients 50000`) comes with
step 7.

## Presets and budgets
| Preset | Clients × months | Use |
|---|---|---|
| `unit` | ~5k × 24 (≈ 120k rows) | Unit tests and the end-to-end test |
| `canonical` | 100k × 24 (≈ 2.4M rows); `n_clients=50_000` on the 8 GB laptop | The shared development dataset, in `data/01_raw/synthetic_canonical/` |

Budgets, measured in step 7: `canonical` in ≤ 10 min with peak memory ≤ ~3 GB; `unit` in ≤ 20 s.

## Open questions
Steps 3–7 are built in one go, with one review by the SDS at the end (2026-10-15). Before that,
one question round settles everything they need (Q140–Q208, 2026-10-15: amounts, the mart's columns,
traps, oracle, output and how the build runs). The answers go into this spec and into the build plan.
