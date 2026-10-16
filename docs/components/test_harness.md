# Synthetic data and test harness
**Status:** designing — spec settled 2026-10-14 (D-056), completed 2026-10-16 (D-068, D-069); steps 0–2 done; steps 3–7 built in one go, with one review by the SDS at the end (D-067) · **Legacy:** `tests/smoke_test.py` (stub-based — do not copy its stubs)
**Related:** [dataset](dataset.md) (time model) · [target factory](target_factory.md) · [EDA](eda.md) ·
[feature checks](feature_checks.md) · [environment](environment.md) · [config](config.md) · `tests/README.md` ·
`synthetic/REVIEW.md` (review guide, from step 7) · D-014, D-041, D-056, D-057, D-062, D-064–D-069 · OD-15, OD-17

## Build plan

Status: `not started` · `in progress` · `in review` · `done`. Steps 0–2 each ended at a gate with the
SDS. Steps 3–7 are built in one go (D-067): each stage ends with `pytest` (fast and slow) and `ruff`
green, the code-reviewer and simplicity-review (plus the ml-correctness-auditor from the mart on),
and every new check shown to fail on a deliberately broken generator; the SDS reviews once at the end,
guided by `synthetic/REVIEW.md`. The task-by-task plan, with instructions for the agents that build
it, is `worknotes/handovers/synthetic_build.md` (removed when M1 closes).

| Step | Builds | Proof (`pytest`, via the step's check table) | Status |
|---|---|---|---|
| 0 | `synthetic` package skeleton, compat shim, local Spark session, parquet round trip | Dates, integers, doubles, strings, booleans and nulls survive pandas → parquet (month-partitioned) → Spark → pandas; `flaml` imports after `core_modelling` (T1); green on the Mac (the PC only when the SDS switches, `docs/guides/setup_windows_wsl2.md`) | done |
| 1 | Population, client description, day counters, entry and exit, latent traits; the checking notebook | Same seed → identical data, other seed → different; mix within CI (subsegment; nationality group, employment, emirate and salary transfer per profile; top country); day counters grow by exactly the days in the month; relationship ≤ residence ≤ age; residence nulls; income missingness and medians; residence gap; latent stationarity and month-to-month persistence per profile; income slope on the wealth trait (new clients); entry and exit rates per profile, read from the mart; no crash with months without new clients | done |
| 2 | Holdings and states: current/savings, credit card, loans, term deposit, wealth, e-banking, FX and digital activity | Rules that always hold (statuses and their transitions, account counts and maturities, no early settlement, digital only with e-banking, product count); realised events match the oracle's chances, overall and per chance decile, and the oracle sets a chance exactly where the mart shows a client at risk; shares per profile near the spec and flat over the panel; steady-state event volumes near the spec; the income-threshold jump and exemptions; churned vs never; the onboarding wave | done |
| 3 | Amounts: balances, flows, card and loan mechanics, subcategories, logins; time effects; segment overlap | Exact zeros for non-holders and dormant clients; subcategories add up exactly; net flow equals the balance change; card and loan rules; medians per profile at the spec's multiples; lag-1 correlations in their bands; Hill tail index within ±30%; seasonality per profile; overlap of MM and UM; pooled vs within-subsegment rank correlations | not started |
| 4 | Feature mart: rollups, names, history, null rule, types, month-partitioned parquet written month by month | An independent Spark recompute matches every rollup (T8); every name parses with the grammar; column-list snapshot; **prefix stability**: 20 and 24 months from the same seed give identical months 1–20, except the declared leak columns; the null rule; types (0/1 flags, the decimal column) | not started |
| 5 | Traps on two products, drift, dirty-data switches, extra columns; the trap summary | Every trap meets its expected behaviour in the trap summary | not started |
| 6 | Oracle file and `truth.json`: window probabilities on demand, oracle AUCs, relevance ranking, the regression oracle | Oracle probabilities match realised events per decile for every standard target; the leaks beat the oracle; regression quantiles cover realised values as stated; `truth.json` schema | not started |
| 7 | Canonical dataset, source mapping, CLI, budgets, the checking notebook with outputs, the review guide | The canonical mart read through the source mapping: 24 partitions, row count, column list; runtime and memory within budget; stale-data guard | not started |

**Checks as data.** Each step adds a `check_*` function that returns a table: check, stratum, `n`,
expected, realised, tolerance, passed. `pytest` asserts every row passes; the checking notebook shows
the same tables with charts, so tests and review evidence can't drift apart. Expected values are
restated from the spec and read from the mart (and, where the spec defines them through hidden
inputs, the oracle's hidden columns), never taken from the generator's own functions or records.
- **Two suites.** Plain `pytest` runs in about a minute on the `unit` preset: there, only the rows
  for rules that always hold (tolerance 0) must pass, plus prefix stability, the Spark recompute,
  dirty switches and types. `pytest -m slow` writes the canonical dataset once per session and runs
  every row of every check family at 100k: in the 5k preset many Private strata are too small to
  show anything. Both pass before anything is called done.
- **Tolerances.** 4.5 standard errors: a family-wise false-failure rate of about 0.1% over ~150–300
  rows per family (no failing seed among 0–5 at 100k for steps 1–2). Standard errors are
  analytical where the statistic has one, computed on one row per client so rows are independent
  (binomial shares, Fisher-z for correlations, Hanley–McNeil for AUCs, α/√k for the Hill
  estimator). For the few statistics without one, the tolerance is 4.5 × their standard deviation
  over 20 seeds at 100k, measured once and recorded next to the check. A spec range (e.g. lag-1
  correlation 0.6–0.8) is checked as a range.
- Each new check is shown to fail on a deliberately broken generator before it counts. With the
  fixed test seed a failing row is a generator bug, never a tolerance to widen.
- Each family has its own module (`checks_<family>.py`) declaring the mart and oracle columns it
  reads, so canonical checks load column subsets from parquet; shared table logic is in
  `check_table.py`; realised targets over forward windows are computed by the checks' own code.

**Checking notebook** (`notebooks/00_synthetic_data.ipynb`, dev only, temporary): reads the written
canonical dataset, shows every check table and a simplified EDA per area (population, holdings,
amounts, time effects, segments, mart columns, traps, oracle), plus a few client trajectories and
the hidden traits. Inline pandas and plotly only, no function definitions; charts plot aggregates,
so the notebook stays small. It is committed with its outputs (synthetic data only; an exception to
`notebooks/README.md`). The guided EDA notebook replaces it once EDA exists.

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
   that stage gets tested too. The one exception is a target built "upstream" (a planted trap).
2. **Size:** `canonical` ≈ 100k clients × 24 months (≈ 2.5M rows); `n_clients` scales it (e.g. 50k on
   an 8 GB laptop); `unit` ≈ 5k × 24 for tests. Backward windows ≤ 6 months.
3. **Width ≈ 145 columns** including traps ([column list](#columns)), plus an off-by-default switch
   that adds many weak or noise columns for scale tests.
4. **Segmented population** with the realistic mix below. Latent traits are correlated within each
   segment and differ between segments, so pooled and within-segment relationships diverge.
5. **Heavy-tailed, coherent amounts:** power-law tails, rank-correlated through shared traits; no
   zero-balance client transacts millions.
6. **Sticky holdings and usage:** switching is rare, active and dormant spells are long, and the
   zero ↔ non-zero transitions are explicit and recorded.
7. **Exact zeros** for non-holders and dormant users. **Nulls only where the retail data has them**
   ([null rule](#null-rule-history-and-types)).
8. **Rare categorical levels** (Zipf frequencies).
9. **Time consistency:** fixed client descriptors, day counters that grow by the days in the month,
   entry and exit, seasonality, drift.
10. **Rare to semi-rare events** (adoption, activation, reactivation), each with a controllable rate.
11. **Planted traps,** on two products, each switchable and recorded in the ground truth (D-069).
12. **Deterministic from a seed**, generated month by month: a month never depends on later months,
    except the declared leak columns.
13. **Ground truth:** `truth.json` plus a per-row oracle file. The oracle is never mapped as a source;
    it would be a leak. The generator assumes no particular observation window (D-068).

## Design constraints
- **A top-level `synthetic/` package**, dev-only and not part of `core_modelling` (D-041). Its own
  editable install (`synthetic/pyproject.toml`, `synthetic/src/synthetic/`). The spec is plain data
  (`presets`, `products`, `levels`, `seasons`); mechanisms each have a module (`population`,
  `latents`, `hazards`, `holdings`, `variation`, `balances`, `flows`, `cards`, `logins`, `amounts`,
  `mart`, `names`, `traps`, `regression`); `generate` runs the month loop; `oracle` and `truth` hold
  the ground truth; `output` writes and reads the dataset; the checks have one module per family.
  Module map: `worknotes/handovers/synthetic_build.md`. Whether it travels in the release zip is
  decided with OD-04.
- **Libraries:** numpy, pandas, pyarrow, scipy (pinned, D-042).
- **One random stream per mechanism** (population, latents, holdings, amounts, cards, logins, traps,
  leaks, extras, regression oracle), spawned from the seed (`SeedSequence.spawn`) and passed
  explicitly; no global random state. New mechanisms append a stream, which leaves the earlier ones
  identical. Within a stream, draws happen in a fixed order, month by month, and every draw is a
  fixed-size array per client, never sized by an outcome.
- Vectorised over clients; the only loop is over months. Memory stays bounded: one month of clients
  plus a 6-month history and a 3-month look-ahead buffer (for the leak columns), written month by
  month.
- **The population, products and amounts are a plain-data spec**, so another domain or entity is
  another spec, not new code. Products drive three small chain functions: a 0/1 holding chain, an
  account-count chain and an active/dormant usage chain.
- **Column names come from one grammar** ([names](#names)), built from parts.
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
| `nationality` | ~60 countries, Zipf within the group | Many levels, rare levels |
| `employment_status` | Employed, Self-employed, Unemployed, Retired, Other (mostly investors); mix per profile | Unemployed and Retired concentrated in Private |
| `income` | Declared monthly income, static: the hidden true income where declared | Missing not at random (mostly Other, Unemployed and Private), plus a little random missingness |
| `salary_transfer_flag` | Employed only; the salary credit equals the true income and sits inside inflow | |
| `emirate` | The 7 emirates plus Others (outside the UAE or unknown); mix per profile | Dubai-heavy; Others 25% / 7% / 11% in Private / Priority / PSB |

**Hidden client attributes** (oracle only), drawn when the client is drawn: the **true income** (step
1's income before hiding), the **wealth base** (the subsegment's median income × exp(0.3 × the
client's within-profile wealth-trait deviation): no employment multiplier, so a retired Private
client has small flows but large balances), the remitter flag, the bonus month and size, the
school-fee payer flag and fee, the card repayment share, and the persistent effects and power-law
multipliers of each amount ([amounts](#amounts)).

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
| Current/savings (CASA) | Near-universal account + active/dormant chain | Monthly average balance; inflow and outflow by subcategory, with counts | Reactivation |
| Credit card (`cc`) | 0/1 holding with an onboarding wave + active/dormant chain + hidden revolver state | Limit (product tiers), month-end balance, utilisation, spend by subcategory, repayment, interest | Acquisition (trap product); activation |
| Personal / auto / home loan | Active account count | Openings; closures at maturity (no early settlement); outstanding balance and instalment (annuity); months to maturity | Opening: the count goes up (trap product: personal) |
| Term deposit | 0/1 holding + balance | Balance fixed within each 12-month term | never / churned / active |
| Digital wealth, traditional wealth | 0/1 holding + assets under management; Retired clients lean to traditional wealth | Assets move with one shared market index | never / churned / active |
| FX | Activity only, active/dormant | Monthly volume and count; driven by the cross-border trait, travel months and income | Activation |
| E-banking / digital | Registration (0/1, onboarding wave) + digital activity (active/dormant) | Mobile and online login counts; days since last login (null if never logged in) | Activation |
| Remittance | Subcategory of account outflow | Amount and count; exactly 0 for non-remitters | |

Also derived: the number of products held.

- **Never / churned / active** (term deposit and both wealth products). Each client's history runs
  from relationship start, so some clients held the product before month 1. Acquisition is one
  target (0 → 1), whether the client never held the product or churned; churned clients adopt at
  twice the odds, so the status carries signal.
- **Onboarding wave** (credit card, e-banking): many new clients take the product in their first 3
  months, up to their steady-state share; after that, adoption is low. Other products build up over
  each client's tenure from "never held" at relationship start, for new and existing clients alike.
- **Active/dormant chains** (usage kind): FX for every client; digital activity among e-banking
  clients; card activity among card holders (a new card can be active from the month after
  adoption); current/savings activity among account holders (salary-transfer clients are rarely
  dormant); the revolver state among card holders, hidden in the oracle. A chain that requires a
  product is at risk only if the client held it at the end of last month.
- **Loans:** no top-ups and no opening dates. Target Factory's rule kinds are therefore a threshold on
  a forward sum, and a flag or count going up ([target factory](target_factory.md)).
- **One event trigger:** a bonus (half of salary-transfer clients, once a year in a month of their
  own between January and April) doubles the odds of adopting a term deposit or a wealth product in
  the 2 following months. It is in the oracle, and gives recent-window columns signal of their own.
- **What an event is in the mart** (the oracle prices exactly these; D-066):
  - a 0/1 product is acquired when its flag is 1 in any month of the window, for a non-holder at
    the observation month; an end-of-window rule misses ≈ 1–10% of acquisitions (lost again);
  - a loan opens when its count rises in any month of the window; an account maturing in the
    same month hides an opening (≈ 0.5% of personal loans), which makes `maturity_months`
    predictive under a "count at the end" rule;
  - a usage chain activates when its active flag is 1 in any month of the window, for a client
    dormant at the observation month (and holding the required product);
  - a new client's entry-month events sit on its first row, not in a month-on-month move;
  - a loan's closing is fixed by `maturity_months` (no early settlement): a closing target would
    score AUC 1 from an as-of feature, so it is degenerate, not a leak;
  - targets for status products are built from the flag, so lineage exclusion doesn't drop the
    status column and its legitimate churned signal.
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
the share held (or active) per profile; for 0/1 products the adoptions a month in a 100k book
(credit card and e-banking: after onboarding); for loans the term; for usage chains the mean active
spell. How long a holding lasts is derived. Adoptions that refill the holdings of clients who left
the bank count towards the volume.

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
| Card activity | — | Active: 85 / 85 / 80 / 75% of card holders | Mean active spell 24 months | — | — |
| Current/savings activity | — | Active: 91 / 93 / 94 / 96% (≈ 10% dormant without salary transfer, ≈ 1% with it) | Mean active spell 180 months | Dormant spell ≈ 12 months | — |
| Revolver (hidden) | — | 10 / 20 / 30 / 45% of card holders (≈ 35–40% overall) | Mean spell 24 months | — | — |

Drivers beyond step 2: the card adds the digital trait (0.3, for the reversal trap); the personal
loan has a rare high-rate nationality (+1.5); term deposit and wealth have the bonus trigger; FX
wake-ups rise in summer; digital wake-ups trend up ([time effects](#time-effects)). Card activity
loads on activity (0.6); current/savings activity on activity (0.5) and salary transfer (+2.4); the
revolver state on credit appetite (0.5) and wealth (−0.3).

Realised volumes run a little above the set ones because the book grows ≈ 0.2% a month and its
tenure mix is younger than its long-run mix, so products that build up over tenure keep growing
(the volume check nets that growth out). Loans set by term put the volume where the share and term
imply: personal loans come out near 680 a month, above the ≈ 400 first discussed (accepted at the
step-2 gate, as were traditional-wealth holdings lasting ≈ 33 years). Private clients' personal
loans run off over the panel (≈ 6% → 4%) because the book ages and the chance peaks in the mid-30s.

**Holdings at month 1 agree with income, traits and tenure.** Starting holdings come from the same
chances as later adoption, income threshold included (maths §3). Loan holders at the start
therefore sit mostly above the threshold, with the same half-strict leak below it as new loans.

### Second entity (optional, M3; likely not needed)
If it is ever needed, a smaller subsidiary: ≈ 30k clients, PSB-like profiles only (no Private), more ARAB and AFRICA
clients, no traditional wealth or home loans, ≈ 100 columns with a few differently named ones (e.g.
the income column). It is another spec dict in `presets.py`, generated and written separately, so it
tests that entities are never merged (D-034) and that sources differ by entity. Not built in M1.

---

## Amounts

Every amount is a **median multiple of a hidden base per profile**: flows scale with the true income,
balances with the wealth base. Values live in `synthetic/src/synthetic/levels.py` (amounts) and
`seasons.py` (time effects); the formulas are in [maths §4–§6](#4-amounts-lognormal-body-power-law-tail).
All amounts are AED, rounded to 0.01; counts are whole numbers.

### Levels
Median multiple of the base, per profile, for a holder in an active, non-seasonal month, after the
new-client ramp:

| Measure | Base | Private | Priority | Affluent | Mass | Tail index |
|---|---|---|---|---|---|---|
| Current/savings balance (monthly average) | wealth | 40 | 4 | 1.5 | 0.5 | 2.0 |
| Inflow | income | 1.5 | 1.3 | 1.15 | 1.05 | through the balance |
| Card spend (wanted, before the limit) | income | 0.4 | 0.3 | 0.3 | 0.35 | through the balance |
| Card limit (target; then a product tier) | income | 3 | 2.5 | 2 | 1.5 | — |
| Term deposit (minimum AED 10k) | wealth | 20 | 10 | 6 | 3 | 1.8 |
| Traditional wealth | wealth | 60 | 15 | 8 | 4 | 1.5 |
| Digital wealth | wealth | 10 | 4 | 2 | 1 | 1.5 |
| FX volume | income | 1.0 | 0.6 | 0.4 | 0.3 | through the balance |

Clients without salary transfer bank their salary elsewhere: their current/savings inflow and
outflow are × 0.4 and their balance × 0.6. A lower tail index is a heavier tail; flows inherit a
thinner tail through their link to the balance (elasticity 0.3).

### Persistence and variation
- **Stocks** (current/savings, term deposit, wealth): a persistent client effect (sd 0.7 for
  current/savings, 0.5 for the others), monthly AR(1) noise (ρ 0.8, stationary sd 0.25), the wealth
  trait's deviation from the client's mean (loading 0.3) and a persistent power-law multiplier.
  Target: lag-1 correlation of log balances ≥ 0.9.
- **Flows** (non-salary inflow, spending outflow, card spend, FX): a persistent client effect (sd
  0.4), AR(1) noise (ρ 0.3, stationary sd 0.35), one trait's deviation (activity 0.2 for account
  flows, activity 0.3 for card spend, cross-border 0.4 for FX) and the client's current/savings
  deviation × 0.3. Target: lag-1 correlation of log flows in consecutive active months 0.6–0.8.
- **Counts** are overdispersed: 1 + Poisson(mean × G), G ~ Gamma(shape 2, scale 1/2) per client and
  month, in active months; 0 otherwise. Means: outflow 12, card spend 10 (× exp(0.3 × activity
  deviation)), remittance 1 + Poisson(0.5), FX 1 + Poisson(1); inflow count = salary (1) +
  Poisson(2 G) + 1 if a balance transfer came in.
- **New clients** ramp up: current/savings balance × 0.5 in their first month, × 0.75 in the
  second, full from the third.

### Current/savings account
- **Balance first.** The monthly average balance follows its own path (above, with the summer dip).
  Inflow = salary + transfers + other; outflow = remittance + cash + bills + transfers.
- **Salary** = true income for salary-transfer clients, every month, plus the bonus in the bonus
  month; 0 for everyone else. **Non-salary inflow** = (inflow multiple − 1) × income for
  salary-transfer clients, 0.4 × inflow multiple × income for the others (times the flow variation),
  split into transfers and other: the "other" share is 0.2 for Employed, 0.6 Self-employed,
  0.3 Unemployed, 0.5 Retired, 0.7 Other, plus 0.1 in Private.
- **Spending outflow** = 0.85 × (salary without bonus + non-salary inflow) × its own flow
  variation, split into the outflow subcategories; school fees add to bills.
- **Own-product payments** (card repayment, loan instalments) leave the account as outflow
  transfers. Term-deposit and wealth top-ups stay out (those balances move on their own).
- **Booking:** any change in the balance beyond the month's flows is booked as a transfer: in when
  the balance rose more than inflow minus outflow, out otherwise. So **inflow − outflow equals the
  change in the monthly average balance exactly**, and the summer dip shows as outflow above inflow.
- **Dormant months** (current/savings activity): inflow, outflow, every subcategory and their counts
  are exactly 0, and the balance stays frozen at its last value; own-product payments are then made
  from elsewhere and don't appear. On reactivation the balance returns to its path, booked as a
  transfer.

### Subcategories
Each client has persistent mean shares: the profile's base shares, tilted by traits and descriptors,
renormalised. Monthly shares vary around them (Dirichlet, concentration 50), so subcategories aren't
perfectly collinear with their totals; they add up to the total exactly.

| Profile | Outflow (spending): remittance / cash / bills / transfers | Card spend: travel / retail / online / dining |
|---|---|---|
| Private | 5 / 3 / 12 / 80 | 45 / 25 / 15 / 15 |
| Priority | 12 / 8 / 20 / 60 | 30 / 32 / 20 / 18 |
| Affluent | 20 / 15 / 25 / 40 | 18 / 40 / 24 / 18 |
| Mass | 30 / 30 / 25 / 15 | 6 / 50 / 24 / 20 |

- **Remittance:** only remitters, a persistent flag held by 30 / 40 / 50 / 60% of non-nationals
  (private → mass) and by no UAE or GCC national; non-remitters' remittance is exactly 0 and their
  share goes to the other three. The share × 1.2 for ASIA and AFRICA, × 0.5 for WESTERN, × 0.8 for
  OTHER, and × (income / subsegment median)^−0.3, so it falls as income rises.
- **Cash** × exp(−0.4 × digital deviation − 0.2 × wealth deviation).
- **Card travel** happens only in travel months (chance per month 0.5 / 0.4 / 0.3 / 0.1, doubled in
  July–August, capped at 0.95, × exp(0.5 × cross-border deviation)); otherwise travel spend is 0 and
  its share goes to the others. Travel × exp(0.4 × cross-border deviation), online × exp(0.4 ×
  digital deviation).

### Credit card
- **Limit:** set when the card is taken, from a few product tiers (AED 5k, 10k, 20k, 35k, 50k, 75k,
  100k, 150k, 250k, 500k): the largest tier at or below the limit multiple × true income (at least
  the lowest tier). 10% of new cards get one tier up (credit trait above the client's mean) or down
  (otherwise). Redrawn only when the client takes a card again. 0 without a card. Stored as
  `decimal(18,2)`, the mart's one decimal column (the real marts store amounts that way).
- **Revolver or transactor** (hidden chain, above). Each client has a fixed repayment share between
  5% and 30% (uniform).
- **Each month,** with `M` the month-end balance:
  - transactor: repays last month's balance in full; `M` = this month's spend;
  - revolver: repays its share of last month's balance; interest = 3% of what it carried;
    `M` = carried + interest + spend;
  - spend is the wanted spend, capped at limit − carried − interest (≥ 0); 0 in a dormant month;
  - a card given up this month repays its whole balance and ends at 0.
- **Utilisation** = `M` / limit, null without a card. Interest above 0 reveals a revolver.

### Loans, term deposit, wealth
- **Loans:** principal at opening = multiple × true income × exp(N(0, 0.3²)): personal 8, auto 5,
  home 60 (the UAE cap for personal loans is 20×). Equal monthly instalments at fixed annual rates
  of 7% / 4% / 5% (unverified ballparks), from the month after opening until maturity. Outstanding
  balance and instalment per loan type are summed over the client's accounts. The starting book's
  accounts are amortised from their opening.
- **Term deposit:** the balance is drawn at adoption and at each 12-month rollover (the stock formula
  with fresh noise, at least AED 10k) and stays fixed in between. 0 when not held.
- **Wealth:** assets under management = the stock formula × one shared market index (monthly log
  return N(0.005, 0.03²), 1 at the first simulated month, recorded in the truth). Digital and
  traditional wealth have their own client effects and noise. 0 when not held.

### FX and logins
- **FX** is a separate activity: currency conversion, foreign transfers and travel money; remittances
  stay in account outflow. Volume and count only in active months.
- **Logins** (digital activity): logins a month for an active user 7 / 10 / 13 / 16 (private →
  mass) × exp(0.4 × digital deviation); the mobile share is σ(1.5 + 0.5 × digital deviation −
  0.3 × (age − 40) / 10); mobile and online counts are each overdispersed, and an active month has
  at least one login. Dormant or unregistered: 0 logins.
- **Days since last login** (month end): for an active month, a uniform day after the month's last
  login; dormant months add the days in the month; null if the client never logged in.
  Starting-book clients registered but dormant at the start are taken to have logged in 30–720 days
  before (uniform).

### Time effects
Seasonality differs by profile: Mass clients travel little, and school fees vary less than income,
so they weigh most on Affluent (especially A) budgets.

| Effect | When | Private | Priority | Affluent | Mass |
|---|---|---|---|---|---|
| Card travel spend × | July–August | 1.6 | 1.5 | 1.4 | 1.15 |
| FX volume × | July–August | 1.4 | 1.3 | 1.25 | 1.1 |
| FX wake-up log-odds + | moves into July, August | 0.5 | 0.4 | 0.3 | 0.1 |
| Current/savings balance × | July–August | 0.90 | 0.92 | 0.94 | 0.98 |
| Card spend other than travel × | December | 1.15 | 1.12 | 1.12 | 1.08 |
| School-fee payers (clients aged 28–55 when drawn) | — | 50% | 50% | 45% | 15% |
| School fees a year (AED; × lognormal, sd 0.3) | 40% September, 30% January, 30% April | 120k | 80k | 50k | 12k |

- **Bonuses:** half of salary-transfer clients, in a fixed month of their own (January–April,
  uniform), worth 1–2 × income (uniform, fixed per client), every year; booked in salary inflow.
  Trigger: term-deposit and wealth adoption odds × 2 in the 2 following months.
- **Ramadan** stays out (round 1, Q94).
- **Drift** (monitoring trap): digital wake-up log-odds + log(1.2) per year from the first panel
  month (a gradual uptake trend); an app relaunch at panel month 16 (2026-01) multiplies mobile
  logins by 1.3. Login columns then show PSI > 0.25 against earlier months.

### Segment overlap
Subsegments overlap in amounts but their medians are ordered: about 25% of MM clients hold more
current/savings than the UM median (target range 20–30%, set by the current/savings client effect),
and Private is far apart from everyone else (fewer than 5% of Upper Priority clients above the Lower
Private median). The `separation` knob scales the distances between subsegment trait means
(default 1); at 0.5 the pooled rank correlation of balance with card spend falls towards the
within-subsegment one.

---

## The maths

Notation: client `i`, month `t`, subsegment `s`, profile `p`, product `k`, latent dimension
`d = 1..5`. `σ(x)` is the logistic function.

### 1. Latent traits
```
z_i ~ N(μ_s + shift(nationality_group, employment), Σ_p),   Σ_p = D_p R_p D_p,   L_p = chol(Σ_p)
```
Each subsegment has its own mean; scales and the **correlation matrix `R`** are set per profile, with
every correlation between traits kept within [0, 0.2] (the wealthy profiles decouple wealth from
credit appetite). `separation` scales the distances between the subsegment means around their
book-weighted average.

### 2. Persistence over time (stationary AR(1))
```
z_i,t = m_i + ρ (z_i,t−1 − m_i) + sqrt(1 − ρ²) · L_p ε_i,t,     ε ~ N(0, I)
```
`m_i` is the client's mean from §1; scalar `ρ` ≈ 0.95 a month keeps the stationary distribution exact.
Segments never change. `Δz_i,d,t = z_i,d,t − m_i,d` is the trait deviation used by amounts.
- **Entry and exit:** each month a client exits with its profile's probability, and each subsegment
  gains `Binomial(n_s, entry rate of its profile)` new clients; entrants draw `z` from their
  stationary distribution and start at relationship day 0.
- **Burn-in:** `B` months (default 12) are simulated before month 1 and discarded from the output.
  They put latents, holdings and amounts in steady state and provide the history that month 1's
  rollups need.

### 3. Holdings and accounts
Every product has one monthly chance per client, on the log-odds scale:
```
logit p_i,k,t = α_k,p + score_i,k,t + log(2) · churned_i,k
score_i,k,t   = Σ_d β_k,d · z_i,d,t + age_k(age_i,t) + effects_k(descriptors_i)
                + log(0.2) · below_threshold_k(i) + time_k,p(t) + log(2) · after_bonus_i,k,t
```
- `age_k` is a slope per decade or an inverted U around a peak (personal and auto loans peak in the
  mid-30s, home loans at 42); `effects_k` are salary transfer (credit card, personal loans,
  current/savings activity), nationality (home loans; the rare level on personal loans) and Retired
  (traditional wealth). The churned term applies to status products only. `time_k,p(t)` is the FX
  summer wake-up and the digital drift; `after_bonus` the bonus trigger.
- **0/1 products:** a holder leaves with the product's leaving chance `q_k`; a non-holder adopts with
  `p`. `q_k` = (adoptions a month − refills of holders who left the bank) / holders, from the spec.
- **Loans:** each month accounts that reach their term close (no early settlement), then at most one
  account opens with chance `p`; each account runs the product's fixed term.
- **Usage:** a dormant client wakes with `p`; an active one lapses with
  `σ(logit(1 / mean active months) − 0.5 · (score − mean score))`, so keen clients stay active longer.
- **Onboarding wave** (credit card, e-banking): in a new client's first 3 months the chance is the
  constant `1 − (1 − π_i)^(1/3)` that reaches the client's steady-state share `π_i = p / (p + q)`.
- **History and starting book:** other 0/1 products follow never → held ⇄ churned from relationship
  start; the stepped chain has an exact closed form for the chance of holding (and of having
  churned) after `T` months of tenure, and the starting book draws each client's state from it.
  Loans start with `Binomial(min(T, term), p)` accounts opened uniformly in that window.
- **Calibration:** `brentq` per product and profile on the intercept `α`, on the starting book: the
  mean held-after-tenure chance (the steady-state share, with onboarding; the chance of at least one
  account, for loans; the active share, for usage) equals the spec. Time effects and the bonus
  trigger are left out of the calibration, so the shares wobble slightly with the season.
- Sizing rule, recorded in the ground truth: every standard target keeps ≳ 200 events in a 6-month
  window at the canonical size, or is flagged as low-confidence.

### 4. Amounts: lognormal body, power-law tail
For a holder, in an active month (`m` the level multiple, `base` the true income or wealth base,
`adj` the salary-transfer adjustment, `ramp` the new-client ramp, `season` the profile's seasonal
factor, `M_t` the market index for wealth, 1 otherwise):
```
N_i,k,t  = λ_k · Δz_i,d(k),t + η_i,k + ν_i,k,t,    η ~ N(0, e_k²) once,  ν AR(1) (ρ_k, sd s_k)
stock    B_i,k,t = m_k,p · base_i · adj_i · ramp_i,t · season_k,p(t) · M_t · exp(N_i,k,t − c_k,p) · W_i,k
flow     F_i,k,t = m_k,p · income_i · adj_i · season_k,p(t) · exp(N_i,k,t + φ · D_i,t − c_k,p)
         W_i,k ~ Pareto(x_m = 1, a_k) once;   D_i,t = log of the current/savings balance's random part
```
`c` makes the median of the random part exactly 1, so the median amount is the spec's multiple. The
sum of a normal and `log W ~ Exponential(a)` is an exponentially modified normal, whose median is in
`scipy.stats.exponnorm`: for a stock `c = log median` of `N(0, s²) + Exp(a)` with
`s² = λ² σ_d,p² + e² + s²(ν)`; for a flow the balance term adds `φ² s²_casa` to the normal part and
an `Exp(a_casa / φ)` part, less `φ c_casa`. By **Breiman's lemma** a lognormal times an independent
Pareto has a regularly varying tail with index `a`: a true power-law tail on a lognormal body, and
`B^φ` has index `a / φ`, so flows have thinner tails. `W` is persistent, so balances don't jump.
Non-holders and dormant months: exactly 0.

### 5. Counts, subcategories, card balance
```
count     = active · (1 + Poisson(μ_k · exp(0.3 Δz_activity) · G)),   G ~ Gamma(2, 1/2)
shares_t  ~ Dirichlet(50 · s̄_i),   s̄_i = base_p ⊙ tilts_i / Σ;   sub-amount = round(total · share)
card      M_t = carried_t + 0.03 · carried_t · revolver + spend_t,
          carried_t = revolver · (1 − k_i) · M_t−1,   repayment_t = M_t−1 − carried_t
          spend_t = min(wanted_t, limit − (1.03 · carried_t if revolver)),   utilisation = M_t / limit
loan      instalment = P r / (1 − (1 + r)^−n),   outstanding after j instalments = P (1 + r)^j − A ((1 + r)^j − 1) / r
```
Sub-amounts are rounded first and the total is their sum, so subcategories add up exactly.

### 6. Seasonality and drift
- Seasonal factors are per measure and profile ([time effects](#time-effects)), multiplicative on
  amounts and additive on log-odds for wake-ups.
- **Drift:** the digital uptake trend and the app relaunch. The truth records the columns, the month
  and the size.

---

## Feature mart

### Names
All names are lowercase and come from one grammar (`synthetic/src/synthetic/names.py`):
- **Product state:** `{product}_{kind}`, kind ∈ `flag`, `active_flag`, `status`, `cnt`,
  `maturity_months`, `bal`, `limit`, `utilisation_ratio`, `vol` — e.g. `cc_flag`,
  `loan_home_maturity_months`, `casa_bal`, `cc_limit`, `fx_vol`.
- **Activity:** `{measure}_{product}[_{subcat}]_{kind}`, measure ∈ `inflow`, `outflow`, `spend`,
  `repayment`, `interest`, `instalment`, `login`, `application`; kind ∈ `vol`, `cnt` — e.g.
  `outflow_casa_remittance_vol`, `spend_cc_travel_vol`, `login_digital_mobile_cnt`.
- **Rollups:** `{base}_{a}_{b}_months_{agg}`, months back `a` to `b` (0 = the current month;
  windows include it, T8): `0_2`, `0_5`; agg ∈ `avg`, `sum`, `max`, `min`, `std` (sample), `nz`
  (months with a non-zero value) — e.g. `spend_cc_travel_vol_0_2_months_avg`.
- **Recency:** `months_since_last_{measure}_{product}[_{subcat}]` and
  `days_since_last_login_digital`.
- **Ratio:** `{base}_0_2_vs_3_5_months_ratio` (average of months 0–2 over months 3–5).
- **Planted trap columns** end in `_trap_{kind}` (D-069); extra columns are
  `extra_{nnnn}_trap_weak` / `extra_{nnnn}_trap_noise`.
- Current-month values carry the plain names; the client description keeps plain names (`age`,
  `segment`, …).

### Columns
About 145 columns, in this order:

| Group | Columns |
|---|---|
| Keys and description (13) | `client_id`, `snapshot_month`, `segment`, `subsegment`, `nationality_group`, `nationality`, `employment_status`, `income`, `salary_transfer_flag`, `emirate`, `age`, `residence_days`, `relationship_days` |
| Holdings and states (20) | `casa_flag`, `casa_active_flag`, `cc_flag`, `cc_active_flag`, `td_flag`, `td_status`, `wealth_digital_flag`, `wealth_digital_status`, `wealth_trad_flag`, `wealth_trad_status`, `ebanking_flag`, `digital_active_flag`, `fx_active_flag`, `loan_{personal,auto,home}_cnt`, `loan_{personal,auto,home}_maturity_months`, `product_cnt` |
| Current/savings (13) | `casa_bal`; `inflow_casa_vol`, `inflow_casa_{salary,transfers,other}_vol`, `inflow_casa_cnt`; `outflow_casa_vol`, `outflow_casa_{remittance,cash,bills,transfers}_vol`, `outflow_casa_cnt`, `outflow_casa_remittance_cnt` |
| Card (11) | `cc_limit`, `cc_bal`, `cc_utilisation_ratio`, `spend_cc_vol`, `spend_cc_cnt`, `spend_cc_{travel,retail,online,dining}_vol`, `repayment_cc_vol`, `interest_cc_vol` |
| Loans, deposit, wealth (9) | `loan_{personal,auto,home}_bal`, `instalment_loan_{personal,auto,home}_vol`, `td_bal`, `wealth_digital_bal`, `wealth_trad_bal` |
| FX and digital (5) | `fx_vol`, `fx_cnt`, `login_digital_mobile_cnt`, `login_digital_online_cnt`, `days_since_last_login_digital` |
| 3- and 6-month averages (36) | `_0_2_months_avg` and `_0_5_months_avg` of `casa_bal`, `cc_bal`, `inflow_casa_vol`, `inflow_casa_salary_vol`, `inflow_casa_other_vol`, `outflow_casa_vol`, `outflow_casa_remittance_vol`, `outflow_casa_cash_vol`, `outflow_casa_bills_vol`, `outflow_casa_cnt`, `spend_cc_vol`, `spend_cc_cnt`, `spend_cc_travel_vol`, `spend_cc_online_vol`, `cc_utilisation_ratio`, `fx_vol`, `login_digital_mobile_cnt`, `login_digital_online_cnt` |
| 6-month averages only (4) | `td_bal`, `wealth_digital_bal`, `wealth_trad_bal`, `loan_personal_bal` |
| Other 6-month aggregates (16) | `casa_bal` min / max / std; `inflow_casa_vol`, `spend_cc_vol`, `fx_vol`, `login_digital_mobile_cnt` max / std / nz; `spend_cc_travel_vol` nz |
| Recency (5) | `months_since_last_{inflow_casa, outflow_casa_remittance, outflow_casa_cash, spend_cc, fx}` |
| Ratios (4) | `casa_bal`, `inflow_casa_vol`, `spend_cc_vol`, `login_digital_mobile_cnt` (`_0_2_vs_3_5_months_ratio`) |
| Planted traps (8) | [trap summary](#trap-summary) |

`avg` comes for every rolled-up measure; the other aggregations only for a chosen subset, to stay
near 145 columns.

### Null rule, history and types
- **Nulls only where the retail data has them:** missing income; residence for nationals and
  non-residents; utilisation without a card; months to maturity without an account; days since
  last login for clients who never logged in; months since last with no non-zero month since the
  later of relationship start and the start of the simulation; ratios whose 3–5 average is 0; the
  upstream target (holders, immature months); the all-null trap.
- **A rollup whose window reaches before relationship start is null**, as in the retail dataset
  (the framework does not enforce it). Spark's `avg` ignores nulls, so any recompute counts the
  months in the window explicitly. Utilisation's rollups average the months with a card.
- Clients already on the books at month 1 have complete windows, from the burn-in months, so all 24
  months are usable. The generator assumes no particular observation window; [dataset](dataset.md)
  has an example.
- **Types:** flags are 0/1 integers (`int`), counts `bigint`, nullable counters `bigint` with
  nulls, amounts `double` rounded to 0.01, `cc_limit` `decimal(18,2)`, categoricals and statuses
  strings, `snapshot_month` a date (T18).

### Physical form
Parquet partitioned by `snapshot_month` (`snapshot_month=YYYY-MM-01/`), written one month at a time
by pyarrow into `<out>/mart/` and `<out>/oracle/`, with `<out>/truth.json` beside them. `conf/local/`
maps the logical source to `<out>/mart/` (an example lives in `conf/base/`); `truth.json` and the
oracle are never mapped. The canonical dataset lives in `data/01_raw/synthetic_canonical/`.

## Trap summary
Planted traps sit on **two products**, so a test of either target meets every kind (D-069): credit
card acquisition (`cc_flag` 0 → 1) and personal-loan opening (`loan_personal_cnt` rises). Planted
columns end in `_trap_<kind>`; organic traps arise from realistic mechanics and keep their names.
`truth.json` lists every trap with its column, product, target and parameters; the notebook shows
this table with each trap's evidence.

| Product | Trap | Column | Construction | Expected behaviour |
|---|---|---|---|---|
| Credit card | Calibrated leak | `cc_preapproval_score_trap_leak` | `round(500 + 100 · (μ · y + ε))`, `y` = acquisition in the next 3 months (within the panel), `ε ~ N(0, 1)`, `μ = √2 · Φ⁻¹(0.97)`; holders get `ε` only | Univariate AUC ≈ 0.97 for card acquisition in 3 months; beats the oracle; the leakage screen flags it |
| Credit card | Upstream target | `cc_acquire_next_3_months_flag_trap_upstream_target` | 1 if the card is taken in any of the next 3 months, for non-holders; null for holders and in the last 3 panel months; clients who leave inside the window count as 0 (upstream treats leavers as negatives) | The "Target Factory skipped" path and lineage exclusion (T12); Target Factory's own target matches it except for leavers (null there) |
| Credit card | Simpson's reversal | login columns | Logins per active month rise from Private to Mass, while Mass clients take cards least; the card chance loads on the digital trait (0.3) | Logins vs card acquisition: positive within each subsegment, negative pooled; stratified EDA shows it |
| Credit card | Half-strict income threshold (organic) | `income` | [Income thresholds](#income-thresholds-half-strict-eligibility) | The eligibility step log shows the null-income drop |
| Credit card | Onboarding wave (organic) | `relationship_days` | Most adoption in the first 3 months | Strongest single driver for new clients |
| Credit card | Eligibility-defining (organic) | card amounts, `cc_active_flag` | 0 for non-holders | Constant within the eligible population; flagged |
| Credit card | Decimal column | `cc_limit` | `decimal(18,2)` | Read by Spark as decimal; pandas gets Python objects unless it casts |
| Personal loan | Process leak | `application_loan_personal_cnt_trap_process_leak` | An opening at `t+1` is preceded by an application at `t` with chance 0.8; declined applications (never opened) are 30% of all, drawn with chance ∝ the client's opening chance at `t+1` | Beats the oracle for openings in the next month; leakage screen plus human review |
| Personal loan | Rare high-rate level | `nationality` = Ghana (≈ 0.35% of clients) | +1.5 on the personal-loan log-odds | Stands out in event rate by level; unstable in CV |
| Personal loan | Inverted U (organic) | `age` | Peak in the mid-30s | Spearman ≈ 0, mutual information high |
| Personal loan | Hidden openings (organic) | `loan_personal_maturity_months` | A maturity in the same month hides an opening | Predictive under a "count at the end" rule only |
| Personal loan | Eligibility-defining (organic) | `loan_personal_maturity_months` | All null under "first loan" eligibility | Flagged as all-null within the eligible population |
| Any | Null controls | `insurance_premium_vol_trap_null_control` (lognormal, persistent per client), `branch_visit_cnt_trap_null_control` (zero-inflated Poisson), `preferred_language_trap_null_control` (Zipf categorical, persistent) | Independent of everything | Univariate AUC ≈ 0.5; ranked last |
| Any | Quality | `paper_statement_flag_trap_near_constant` (99.9% zeros), `legacy_risk_grade_trap_all_null` (all null) | | Flagged by the quality checks |
| Any | Drift (monitoring) | login columns | [Time effects](#time-effects) | PSI > 0.25 after panel month 16, ≈ 0 before |
| Any | Collinearity (organic) | rollups and identities | Rollups of one measure over `0_2` and `0_5`; `<product>_status == "active"` ⇔ `<product>_flag`; `product_cnt` = product flags + loan counts > 0; inflow − outflow = change in `casa_bal`; subcategories sum to their total | Correlation views and VIF flag the clusters (infinite for the identities) |
| Any | Dirty switches, off by default | — | Duplicate client-months; a month with the digital columns null (outage); income × 12 from one month on (unit change); a few `casa_bal` typos × 1,000 | Contract checks fail loud; operational monitoring flags them (tests on the `unit` preset only) |
| Any | Extra columns, off by default | `extra_{nnnn}_trap_weak` / `_trap_noise` | 10% weak (a trait plus noise, rank correlation 0.1–0.3), the rest pure noise | Scale tests; weak ones rank above noise |

Later (not in M1): a column shifted one month forward (as-of misalignment) and an interaction-only
feature.

## Ground truth and oracle
- **Oracle file** (`oracle/`, parquet, same keys and partitions as the mart): per client and month,
  - the hidden traits `z_*`;
  - the chance applied to every event that month, given the state at the end of the previous month
    (`p_<product>_acquire`, `p_<loan>_open`, `p_<chain>_activate` / `_lapse`; null where the client
    was not at risk). Row `t` holds the chance of the move into month `t`, which the month-`t`
    features already show; never join it to an observation at `t`;
  - `score_<product>`: each product's log-odds without the intercept and the state terms (§3), the
    input for window probabilities;
  - each loan slot's months to maturity (`<loan>_remaining_1..4`, 0 = empty);
  - hidden attributes: `true_income`, `wealth_base`, `remitter_flag`, `school_payer_flag`,
    `bonus_month` (0 = none), `revolver_flag`, the power-law multipliers `pareto_<stock>`;
  - the regression oracle: `spend_cc_next_3_months_{mean,q10,q50,q90}` for card holders.
- **Window probability, on demand** (`window_probability(mart, oracle, truth, event, w)`, D-066),
  keyed to the observation month so no consumer shifts rows: for an observation at `t`,
  `1 − ∏(1 − p̃_s)` over `s = t+1 … t+w`, where `p̃_s` is the chance the client would face with its
  state frozen at `t` (never / churned as at `t`, onboarding by tenure, loan slots and maturities as
  scheduled at `t` — a maturity in month `s` hides an opening —, the required product held), on the
  realised trait path, from the intercepts in `truth.json` and `score_<product>` at `s`. Multiplying
  the recorded rows instead conditions on the outcome and understates positives (card acquisition
  AUC 0.71 instead of 0.81). Null where the target is: not eligible at `t`, or the client leaves
  before `t+w`, or the window runs past the panel. The oracle conditions on the realised trait path,
  still a valid upper bound because traits and exits get no feedback from holdings (≈ 0.002 AUC).
  This also serves OD-17: each sampling option's bias and calibration can be measured against it.
- **Standard targets** (oracle AUCs, expected positives, sizing): for `w` = 1, 3 and 6 months,

  | Target | Event | Eligible at `t` |
  |---|---|---|
  | `cc_acquire`, `td_acquire`, `wealth_digital_acquire`, `wealth_trad_acquire`, `ebanking_acquire` | the flag is 1 in any month of the window | flag 0 |
  | `loan_personal_open`, `loan_auto_open`, `loan_home_open` | the count rises in any month of the window | everyone |
  | `fx_activate` | `fx_active_flag` 1 in any month | `fx_active_flag` 0 |
  | `digital_activate` | `digital_active_flag` 1 in any month | `ebanking_flag` 1, `digital_active_flag` 0 |
  | `cc_activate` | `cc_active_flag` 1 in any month | `cc_flag` 1, `cc_active_flag` 0 |
  | `casa_reactivate` | `casa_active_flag` 1 in any month | `casa_flag` 1, `casa_active_flag` 0 |
  | `spend_cc_next_3_months` (regression) | sum of `spend_cc_vol` over the next 3 months | `cc_flag` 1 |

  Clients who leave inside the window and windows past the panel get a null target.
- **Regression oracle** (D-060): the true mean and 10% / 50% / 90% quantiles of next-3-month card
  spend per card holder, from 200 simulated forward paths of the card chains, traits, the
  current/savings deviation and spend, starting at the true state (own random stream, conditioned
  on staying). It integrates over the trait path, unlike the window probability.
- **`truth.json`:**
  - seed, preset, `n_clients`, `n_months`, generator version, numpy / scipy / pandas / pyarrow
    versions (the seed-to-data mapping depends on them);
  - the column schema: name, type, kind (`id` / `time` / `static` / `holding` / `stock` / `flow` /
    `count` / `rollup` / `categorical` / `trap` / `noise`), generating mechanism;
  - the spec (population, products, levels, seasons), calibrated intercepts and leaving chances,
    turnover per month and profile, the market index path;
  - per standard target and window: oracle AUC pooled and per segment, events per month,
    expected positives in a 6-month window and a low-confidence flag;
  - per standard target: the **relevance ranking**, every column's rank correlation (η for
    categoricals) with the true window probability (`w` = 3), the median over observation months;
  - the trap summary, drift, dirty switches when on, the null rule.

**The oracle AUC is the ceiling.** A model or univariate screen that beats it is almost certainly
leaking.

## Interface
```python
PRESETS: dict[str, dict]                  # "unit", "canonical": spec, n_clients, n_months

def generate_mart(preset: str = "unit", n_clients: int | None = None, seed: int = 0,
                  n_months: int | None = None, dirty: bool = False,
                  n_extra_columns: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (mart, oracle, truth) in memory (small presets). The oracle holds the hidden truth."""

def write_mart(out_dir: str, preset: str = "canonical", n_clients: int | None = None,
               seed: int = 0, n_months: int | None = None, dirty: bool = False,
               n_extra_columns: int = 0) -> dict:
    """Generate month by month, write the partitioned mart, oracle and truth.json; return truth."""

def read_output(out_dir: str, table: str, columns: list[str] | None = None) -> pd.DataFrame:
def load_truth(out_dir: str) -> dict:     # fails loud if written by another generator version
def window_probability(mart, oracle, truth, event: str, w: int) -> pd.Series:
def run_checks(out_dir: str, families: list[str] | None = None) -> dict[str, pd.DataFrame]:
def check_population / check_holdings / check_amounts / check_mart / check_traps / check_oracle
```
```bash
python -m synthetic --preset canonical --n-clients 50000 --seed 0 --out data/01_raw/synthetic_canonical
```

## Presets and budgets
| Preset | Clients × months | Use |
|---|---|---|
| `unit` | ~5k × 24 (≈ 120k rows) | Unit tests and the end-to-end test |
| `canonical` | 100k × 24 (≈ 2.5M rows); `n_clients=50_000` if memory runs short | The shared development dataset, in `data/01_raw/synthetic_canonical/` |

Budgets, measured in step 7: `canonical` in ≤ 10 min with peak memory ≤ ~3 GB; `unit` in ≤ 20 s.
`synthetic.__version__` goes up whenever the output changes; `load_truth` refuses a dataset written
by another version, so a stale `data/01_raw/` fails loud.

## Open questions
None before the review. The SDS's review findings, if any, go here.
