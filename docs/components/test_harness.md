# Synthetic data and test harness
**Status:** tested (built 2026-10-17; the SDS's review applied and approved, 2026-10-19);
reviewed and accepted by the LDS, 2026-10-21, guided by `synthetic/REVIEW.md` (D-067, D-070) ·
**Legacy:** `tests/smoke_test.py` (stub-based — do not copy its stubs)
**Related:** [dataset](dataset.md) (time model) · [target factory](target_factory.md) ·
[EDA](eda.md) · [feature checks](feature_checks.md) · [environment](environment.md) ·
[config](config.md) · `tests/README.md` · `synthetic/REVIEW.md` (review guide) · D-014, D-041,
D-056, D-057, D-062, D-064–D-070, D-080 · OD-17

Read it in three levels:
- **Level 1** (a two-minute read) gives the essentials.
- **Level 2** (about ten minutes) explains how the parts connect.
- **Level 3** is the reference for every number and rule. Its sections follow Level 2's order.

## Level 1: Summary
**What it is.** Real data never leaves the bank, so everything outside it runs on synthetic data
with **known ground truth**. The dev-only `synthetic/` package plays the bank's upstream data owner.
Every stage, test, notebook and demo reads its output through real local PySpark, exactly as it
will read real data. Stubs hid every environment bug in the crunch (T15).

**What it writes** to `data/01_raw/synthetic_canonical/`, in about 6 minutes on the 8 GB Mac:
- **The feature mart:** 100k clients × 24 months (≈ 2.5M rows), 147 columns, one row per client per
  month. It holds:
  - the client description;
  - holdings and balances, flows and logins;
  - 3- and 6-month rollups;
  - trap columns.

  It holds no targets: Target Factory builds them, so that stage gets tested too.
- **The oracle:** the hidden truth beside the mart. It holds each client's hidden traits and the
  true chance behind every event.
- **`truth.json`:** the seed, the spec, the calibration and, per standard target, the oracle's AUC.

**The book.** A UAE-style retail book in 4 profiles: Private 1%, Priority 4%, Affluent 9% and Mass
86% of clients.
- **Five hidden traits** per client drive everything: wealth, activity, digital, credit appetite and
  cross-border. They decide what each client holds, adopts, uses and drops, and how large its
  amounts are.
- **Products:** current/savings, credit card, term deposit, digital and traditional wealth,
  e-banking, and personal, auto and home loans.
- **Usage:** FX, digital, card and current/savings activity, plus a hidden revolver state.
- **Realistic behaviour:** holdings and usage are sticky; amounts are heavy-tailed; there is
  seasonality and drift; about 8–12% of clients leave each year and as many join.

**What it is for.**
- **Traps the framework must catch**, on credit card acquisition and personal-loan opening: two
  leaks, a target built upstream, a process leak, a column shifted a month ahead, null controls, a
  rare level, an inverted U, a Simpson's reversal and drift. Dirty data is available on demand.
- **A ceiling:** for each of 12 standard targets, the oracle's AUC (about 0.7–0.95) is what a
  perfect model would reach. A model that beats it is leaking.

**How it is trusted.** 8 check families compare 1,263 statistics with this spec, and all pass at
100k. The checks are written from the spec and never call the code that makes the data. The notebook
`notebooks/00_synthetic_data.ipynb` gives a visual tour of the data, with the checks in an
appendix.

**Run it:** `python -m synthetic --preset canonical --out data/01_raw/synthetic_canonical --checks`.
A 5k-client `unit` preset serves the tests.

## Level 2: How it fits together

### Who the clients are
- **Segments:** 9 subsegments in 4 profiles, ordered by wealth:
  - Private: Upper, Lower;
  - Priority: Upper, Lower;
  - Affluent: UA, A;
  - Mass: UM, MM, LM.

  A profile sets its subsegments' mixes (nationality, employment, emirate), turnover and trait
  spread. Segments never change.
- **Income and age:**
  - Median declared income runs from AED 3k a month (LM) to 150k (Upper Private).
  - Mean age runs from 31 to 54.
  - A client's true income is its subsegment's median, times an employment multiplier, higher
    with its wealth trait, with noise.
  - Declared income is the true income where declared. It is missing more often for the
    Unemployed, Retired and Other, and for Private clients: not at random.
- **Hidden traits:**
  - Each subsegment has its own trait means: the wealthier subsegments sit higher on wealth,
    activity and cross-border.
  - Credit appetite is highest in Affluent and upper Mass, and lowest in Private.
  - Nationality shifts the traits:
    - Asian, African and Western expatriates are more cross-border, UAE nationals much less;
    - Western clients are more digital;
    - UAE and GCC clients have more credit appetite.
  - Employment shifts them too:
    - Retired clients are wealthier but less active, less digital and less keen on credit;
    - the Unemployed are less active and less keen on credit.
  - Traits drift slowly, so a client's behaviour changes gradually rather than jumping.
- **Turnover:** 0.7% (Private) to 1.1% (Mass) of clients leave each month, at random. Entries run
  0.2 points higher. The book is in its steady state, so shares, ages and tenure stay flat over the
  panel.

### Who holds which product, and who picks one up
Every move has a monthly chance per client: adopting, opening, losing, waking up or lapsing. The
chance has two parts:
- **A profile intercept**, calibrated so each profile holds its spec share. It sets *how many*
  hold the product.
- **The client's score**, from traits, age, descriptors, the income threshold and calendar
  effects. It sets *who* holds it within a profile.

| Product | Held by (Private → Mass) | Likelier to pick it up, within a profile |
|---|---|---|
| Credit card | 85 / 80 / 65 / 30% | Credit appetite, activity, the digital trait; salary transfer; income ≥ AED 5k. Less likely if onboarded digitally. Most take it in their first 3 months |
| E-banking | 80 / 90 / 90 / 75% | The digital trait, younger clients; almost every digitally onboarded client. Mostly in the first 3 months |
| Term deposit | 40 / 30 / 15 / 4% | Wealth, older and less digital clients; in the 2 months after a bonus |
| Digital wealth | 10 / 20 / 12 / 2% | Digital and wealthy clients, younger ones; after a bonus. Holdings last about 10 months |
| Traditional wealth | 60 / 35 / 10 / 1% | Wealth, older, less digital and Retired clients; after a bonus. Held for decades |
| Personal loan | 5 / 10 / 20 / 20% | Credit appetite, less wealth; salary transfer; ages around the mid-30s; one rare nationality; income ≥ AED 5k |
| Auto loan | 3 / 8 / 12 / 6% | Credit appetite and wealth; ages around the mid-30s; income ≥ AED 5k |
| Home loan | 15 / 20 / 10 / 2% | Wealth; ages around 42; UAE, GCC and Western nationals; income ≥ AED 15k |
| FX activity | 60 / 45 / 30 / 12% active | The cross-border trait (so mostly expatriates); more wake-ups in summer |
| Digital activity | 80% of e-banking clients | The digital trait, younger and digitally onboarded clients; trending up |
| Card activity | 75–85% of card holders | The activity trait |
| Current/savings activity | 91–96% | Activity; salary-transfer clients rarely go dormant |
| Revolver (hidden) | 10 / 20 / 30 / 45% of card holders | Credit appetite, less wealth |

What ties the products together:
- **Sticky.** Holdings last years: a card about 6 years, a term deposit 2.7 years, traditional
  wealth about 33. Active spells last 2–15 years on average. Most client-months see no change, so
  events are rare.
- **Shared traits make products correlate.** Wealthy clients hold deposits, wealth and home loans
  together. Credit-hungry clients hold cards, personal loans and revolving balances. Digital
  clients register, log in and buy digital wealth.
- **Half-strict income thresholds.** Below a card's or loan's minimum income, the odds of adopting
  are a fifth. Clients with no declared income count as above the threshold if they are Private,
  Priority, Retired or Other. A plain `income >= X` filter in Spark drops them silently: a trap.
- **History matters.** Clients who held a term deposit or a wealth product before re-adopt at twice
  the odds, so `never / churned / active` status carries signal.
- **Built up over tenure.** Products other than the card and e-banking build up over each client's
  tenure. Month 1's holdings already agree with each client's tenure, income and traits.
- **Loans close only at maturity**, so a loan's closing is known in advance and is not a useful
  target.

### How amounts follow the holdings
- **One formula for every amount.** It is the profile's median multiple of a hidden base. Flows
  (inflow, card spend, FX) scale with the true income, balances with a wealth base. The multiple
  is then scaled by:
  - a persistent client effect;
  - monthly noise;
  - the client's trait deviations;
  - for balances, a persistent power-law multiplier.

  Private sits far above everyone else; neighbouring subsegments overlap (about 25% of MM clients
  hold more than the UM median). A retired Private client has small flows but large balances.
- **Balances persist** (month-to-month correlation ≥ 0.9). Flows vary more (0.6–0.8).
- **Non-holders and dormant months** have exactly 0.
- **Current/savings account:**
  - The balance comes first, and inflow − outflow equals its change exactly.
  - A salary-transfer client's salary is its true income.
  - Clients who bank their salary elsewhere have smaller flows.
  - Card repayments and loan instalments leave the account as outflow.
- **Card:**
  - The limit comes from income in product tiers.
  - Revolvers carry a balance and pay interest; transactors repay in full.
  - Utilisation is the balance over the limit.
- **Loans, deposits and wealth:**
  - Loans repay as annuities.
  - A term deposit is fixed through each 12-month term.
  - Wealth balances move with one shared market index.
- **Mixes by profile:**
  - Private clients spend more on travel and move money by transfer.
  - Mass clients spend more on retail, cash and remittances.
  - Only remitters remit, and no UAE or GCC national does.
- **Time effects:**
  - Travel spend and FX rise in July–August, while balances dip.
  - Spending rises in December.
  - School fees fall in September, January and April.
  - Bonuses in January–April raise deposit and wealth adoption.
  - Two drifts: digital wake-ups trend up, and an app relaunch in 2026-01 multiplies mobile logins
    by 1.8.

### What the mart holds
- **147 columns in groups:**
  - keys and the client description (14);
  - holdings and states (20);
  - current/savings (13), card (11), and loans, deposit and wealth (9);
  - FX and digital (5);
  - rollups over the last 3 and 6 months (56);
  - recency (5) and ratios (4);
  - trap columns (10).
- **Names follow one grammar**, so a name says what the column is: `spend_cc_travel_vol`,
  `casa_bal_0_5_months_avg`, `months_since_last_spend_cc`.
- **Nulls appear only where retail data has them.** Examples: missing income, utilisation without
  a card, and a rollup whose window reaches before the client joined. Non-holders get exact zeros.
- **Collinear by construction**, as real marts are. A measure's 3- and 6-month rollups move
  together, and identities hold exactly. For example, subcategories sum to their total, and inflow
  − outflow equals the balance change.

### Traps and the oracle
- **Where the traps sit.** Traps sit on two products, so a test of either target meets every kind:
  credit card acquisition and personal-loan opening. A few concern no product.
- **Trap columns** (`trap_column` true) exist only to test the framework, and their names end in
  `_trap_<kind>`:
  - the two leaks;
  - the target built upstream;
  - the process leak;
  - the shifted column;
  - the null controls and the quality columns.
- **Traps in real columns** keep their real names, since the framework meets them under those names
  in real data:
  - age's inverted U;
  - a rare nationality;
  - the income threshold;
  - the Simpson's reversal: logins against card uptake, by onboarding channel;
  - the login drift.
- **The oracle prices the truth.** For an observation at month `t` and a target window of `w`
  months, the window probability is the client's true chance of the event. It comes from the
  recorded scores, with the client's state frozen at `t`.
- **The ceiling.** The oracle's AUC is the ceiling for that target and window: a model that beats
  it there is almost certainly leaking. Each leak beats the oracle on the window it was built for:
  - card acquisition (`w` = 3): 0.97 and 0.88 against 0.84;
  - personal-loan opening next month: 0.90 and 0.95 against 0.77.

  The null controls score about 0.5 on every target.
- **A regression ceiling too.** The oracle also gives the true mean and quantiles of each card
  holder's next-3-month card spend, for regression (D-080).

### How a month runs, and where the code is
The generator is a loop over months, vectorised over clients. It starts 13 months before the panel:
12 burn-in months fill the 6-month histories and settle the book. Each month:
1. Clients leave and join.
2. Hidden traits take a small random step.
3. Holdings move (adopt, open, lose, wake up, lapse), and every chance is recorded.
4. Amounts follow the holdings: balances, the card, current/savings flows, FX and logins.
5. Rollups, recency and ratios are updated from each client's 6-month history.
6. Each client gets a mart row and an oracle row.
7. The look-ahead trap columns are filled once the next 3 months exist; then the month is written.

The run is deterministic from a seed:
- Each mechanism has its own random stream, so adding a mechanism leaves the others' columns
  unchanged.
- A month never depends on later months, except the declared look-ahead trap columns.

The code lives under `synthetic/src/synthetic/`, in four folders by role:
- **`spec/`** holds the rules as plain data: population, products, amounts and traps.
- **`mechanisms/`** holds the functions that simulate:
  - `holdings.step_holdings` moves every product;
  - `amounts.step_amounts` sets every amount;
  - `mart` builds names and rollups;
  - `traps` builds the trap columns.
- **`truth/`** holds the oracle (`window_probability`, the standard targets), the regression oracle
  and `truth.json`.
- **`checks/`** holds the 8 check families.

At the top level:
- `generate.py` runs the month loop;
- `output.py` writes and reads the dataset;
- `__main__.py` is the command line.

### How it is checked
- **Eight families**, one table each: population, holdings, amount rules, amount levels, seasons,
  mart, traps and oracle. Each row compares a statistic with what this spec says.
- **Tolerance:** 4.5 standard errors, so a correct generator fails a family about once in a
  thousand runs. A rule that must always hold has tolerance 0.
- **Independent of the generator.** The checks never call the code that makes the data, so a
  generator bug can't pass its own check. Every check was shown to fail on a deliberately broken
  generator.
- **Two test suites:**
  - `pytest` (about 3 minutes) runs the rule rows on the 5k preset;
  - `pytest -m slow` regenerates the 100k dataset and runs every row.
- **The notebook** gives a visual tour of each area, with the check tables in an appendix.

## Level 3: Details

Every number and rule, in Level 2's order: the requirements, then the clients, products,
amounts, mart, traps and oracle, then the code, the checks, the interface and the maths.

### Requirements and design constraints
1. **An upstream-style feature mart**, one wide table per entity: one row per client per month, from
   the client's first month until exit, with the client description, current-month values and
   backward rollups. **No targets**: Target Factory builds them from the current-month columns, so
   that stage gets tested too. The one exception is a target built "upstream" (a trap).
2. **Size:** `canonical` ≈ 100k clients × 24 months; `unit` ≈ 5k × 24 for tests. Backward windows
   ≤ 6 months. **Width:** 147 columns, plus an off-by-default switch for many weak or noise columns.
3. **Segmented population** with a realistic mix; hidden traits correlated within each segment
   and different between segments, so pooled and within-segment relationships diverge.
4. **Heavy-tailed, coherent amounts:** power-law tails, rank-correlated through shared traits; no
   zero-balance client transacts millions.
5. **Sticky holdings and usage:** switching is rare, active and dormant spells are long.
6. **Exact zeros** for non-holders and dormant users; **nulls only where the retail data has them**.
7. **Time consistency:** fixed descriptors, day counters that grow by the days in the month, entry
   and exit, seasonality, drift. **Rare to semi-rare events**, each with a controllable rate.
8. **Traps** on two products, each recorded in the trap summary (D-069).
9. **Deterministic from a seed**, generated month by month; a month never depends on later months,
   except the declared look-ahead trap columns.
10. **Ground truth:** `truth.json` plus a per-row oracle file. The generator assumes no particular
    observation window (D-068).

Design constraints:
- Libraries: numpy, pandas, pyarrow, scipy (pinned, D-042). Spark doesn't generate anything; it
  reads what was written, through the environment adapter.
- **One random stream per mechanism** (population, latents, holdings, amounts, cards, logins, traps,
  leaks, extras, regression, attributes), spawned from the seed and passed explicitly. A new
  mechanism appends a stream, leaving the earlier ones identical: a new stream never changes
  another stream's columns. Within a stream, a new draw moves every later one.
- Vectorised over clients; the only loop is over months. Memory holds one month of clients, a
  6-month history and a 3-month look-ahead buffer.
- The population, products, amounts and traps are a plain-data spec, so another domain or entity is
  another spec, not new code. Products drive three chain kinds: 0/1 holdings, account counts,
  active/dormant usage.
- **Every mechanism has its term in the oracle**; one it doesn't know about would make the oracle
  stop being the ceiling.
- **Simplicity by measured effect** (D-070): a mechanism stays only if its effect is worth its code.
  Cut in round 1: the relevance rankings (recomputable from the oracle) and the `separation` knob
  (no effect at its only value). Kept by the SDS's choice: the regression oracle.

### Population and client description

#### Segment mix
Shares are fixed; client counts scale with `n_clients`. `segment` has 3 levels; `subsegment` has 9,
ordered by wealth. Both are fixed for all months. The Private and Priority Upper/Lower split is a
mock-up. Private is sized at 1k for significance; the smallest stratum (Upper Private, 250) still
exercises minimum support per stratum (D-050).

| Segment | Subsegments (wealthiest first) | Share | Clients at 100k |
|---|---|---|---|
| Private | Upper / Lower | 0.25% / 0.75% | 250 / 750 |
| Priority | Upper / Lower | 1% / 3% | 1,000 / 3,000 |
| PSB | UA / A / UM / MM / LM | 4.3% / 4.3% / 20.5% / 61.6% / 4.3% | 4,300 / 4,300 / 20,500 / 61,600 / 4,300 |

#### Mix by profile
Subsegments share their mixes, turnover and trait spread through four profiles. The values live in
`spec/presets.py`; they are ballpark, close to public UAE figures without copying any bank's book.
ARAB means Arab nationalities outside the UAE and GCC, only slightly wealthier than ASIA; WESTERN
peaks in Priority. The emirate is drawn independently of residence status and nationality.

| Profile | Subsegments | Nationality: ASIA / ARAB / WESTERN / UAE / GCC / AFRICA / OTHER | Employment: Employed / Self-employed / Unemployed / Retired / Other | Emirate "Others" | Salary transfer (employed) | Non-resident | Exit / entry a month |
|---|---|---|---|---|---|---|---|
| private | Upper, Lower Private | 15 / 8 / 20 / 40 / 12 / 3 / 2 | 25 / 30 / 10 / 20 / 15 | 25% | 30% | 15% | 0.7% / 0.9% |
| priority | Upper, Lower Priority | 30 / 12 / 28 / 18 / 6 / 3 / 3 | 55 / 22 / 8 / 7 / 8 | 7% | 50% | 3% | 0.8% / 1.0% |
| affluent | UA, A | 50 / 14 / 12 / 14 / 3 / 4 / 3 | 76 / 13 / 4 / 3 / 4 | 11% | 65% | 0% | 0.9% / 1.1% |
| mass | UM, MM, LM | 74 / 12 / 1.5 / 4 / 0.5 / 7 / 1 | 91 / 5 / 1.5 / 1 / 1.5 | 11% | 70% | 0% | 1.1% / 1.3% |

**Entry and exit:** about 8% (Private) to 12% (Mass) of clients leave a year. Exits are random:
they don't depend on behaviour (the SDS, 2026-10-19), so the choice between leavers as null and
leavers as negatives looks harmless here and won't be on real data. Every profile grows ≈ 0.2% a
month, so the mix stays flat. New clients start at relationship day 0; leavers' rows stop.
`n_clients` is the size 13 months before the panel starts (≈ 103k at month 1 for 100k). Dormant
clients stay on the books with zero activity.

**The book's tenure and age are the turnover's steady state** (D-070,
[maths §2](#2-persistence-over-time-stationary-ar1)).
- Clients join at the entry rate and leave at the exit rate. In a book growing at entry − exit,
  tenure is therefore exponential at the entry rate: a mean of 9.3 / 8.3 / 7.6 / 6.4 years
  (private / priority / affluent / mass).
- Clients join younger than the book's mean age by that mean tenure. The starting book adds its
  tenure to the age it joined at.
- So tenure and age stay put month after month, and with them the shares of products that build
  up over tenure or age (term deposit, wealth, loans).
- Measured on 30k clients (2026-10-19): mean tenure and age move by under 0.1 year over the panel
  in Affluent and Mass.
- The subsegment ages in the spec are the book's mean ages. The youngest subsegments come out 1–2
  years older (LM 33 rather than 31), because nobody joins before 18.

Median declared income of an employed client, AED a month: Upper Private 150k, Lower Private 90k,
Upper Priority 60k, Lower Priority 40k, UA 30k, A 20k, UM 12k, MM 6k, LM 3k (Self-employed × 1.3,
Retired × 0.5). Income is missing for 2% of Employed, 10% of Self-employed, 80% of Unemployed, 60%
of Retired and 85% of Other clients, and for 30% more of Private clients.

#### Client description
| Field | Generation | Notes |
|---|---|---|
| `age` | The age at joining from a truncated normal per subsegment (18–85, mean: the book's mean age less the profile's mean tenure), plus the tenure for the starting book; whole years, changes in the birth month | PSB youngest, Private oldest |
| `residence_days` | Days since arrival in the country; grows by the days in each month. Arrival comes before the relationship by a varied gap: 60% open an account within months of arriving (exponential, mean 0.3 years), the rest had lived here for years (mean 4 years) | Null for UAE nationals and non-residents |
| `relationship_days` | Days since relationship start; grows by the days in each month | ≤ residence for residents; ≤ age |
| `nationality_group` | ASIA, ARAB, WESTERN, UAE, GCC, AFRICA, plus a rare OTHER; mix per profile | ASIA dominates PSB; UAE leads Private |
| `nationality` | ~60 countries, Zipf within the group | Many levels, rare levels |
| `employment_status` | Employed, Self-employed, Unemployed, Retired, Other (mostly investors); mix per profile | Unemployed and Retired concentrated in Private |
| `income` | Declared monthly income, static: the hidden true income where declared | Missing not at random, plus a little at random |
| `salary_transfer_flag` | Employed only; the salary credit equals the true income and sits inside inflow | |
| `emirate` | The 7 emirates plus Others (outside the UAE or unknown); mix per profile | Dubai-heavy |
| `onboarding_channel` | `branch` or `digital`; digital for 15 / 30 / 45 / 55% (private → mass) | Digitally onboarded clients are almost all registered for e-banking (+3.0 on its log-odds), more often digitally active (+1.5), log in twice as often and take cards less often (−1.5): the grouping of the Simpson trap |

**Hidden client attributes** (oracle only), drawn with the client:
- the **true income** (the income before hiding);
- the **wealth base**: the subsegment's median income × exp(0.3 × the client's within-profile
  wealth-trait deviation). It carries no employment multiplier, so a retired Private client has
  small flows but large balances;
- the remitter flag, the bonus month and size, the school-fee payer flag and fee, and the card
  repayment share;
- the persistent effects and power-law multipliers of each amount ([amounts](#amounts)).

#### Income thresholds (half-strict eligibility)
Credit cards and the three loans have a minimum income ([rates](#product-rates)).
- Below it, the odds of adopting are a fifth of those above; at the threshold they jump.
- Clients without a declared income count as above if they are Private or Priority, Retired or
  Other (mostly investors), and as below otherwise.

A plain `income >= X` eligibility filter therefore drops the exempt clients silently, because Spark
treats a comparison with null as not true. It is a realistic trap that the eligibility step log
must make visible.

### Products and holdings
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

- **Never / churned / active** (term deposit and both wealth products).
  - Each client's history runs from relationship start, so some clients held the product before
    month 1.
  - Acquisition is one target (0 → 1), whether the client never held the product or churned.
  - Churned clients adopt at twice the odds, so the status carries signal.
- **Onboarding wave** (credit card, e-banking): many new clients take the product in their first 3
  months, up to their steady-state share; after that, adoption is low. Other products build up over
  each client's tenure from "never held" at relationship start.
- **Active/dormant chains** (usage kind). A chain that requires a product is at risk only if the
  client held it at the end of last month.
  - FX, for every client.
  - Digital activity, among e-banking clients.
  - Card activity, among card holders.
  - Current/savings activity, among account holders; salary-transfer clients are rarely dormant.
  - The revolver state, among card holders; hidden in the oracle.
- **Loans:** no top-ups and no opening dates. Target Factory's rule kinds are therefore a threshold
  on a forward sum, and a flag or count going up ([target factory](target_factory.md)).
- **One event trigger:** a bonus doubles the odds of adopting a term deposit or a wealth product in
  the 2 months after it.
  - Half of salary-transfer clients get one, once a year, in a month of their own between January
    and April.
  - It is in the oracle, and gives recent-window columns signal of their own.
- **What an event is in the mart** (the oracle prices exactly these; D-066):
  - a 0/1 product is acquired when its flag is 1 in any month of the window, for a non-holder at
    the observation month; an end-of-window rule misses ≈ 1–10% of acquisitions (lost again);
  - a loan opens when its count rises in any month of the window; an account maturing in the
    same month hides an opening (≈ 0.5% of personal loans), which makes `maturity_months`
    predictive under a "count at the end" rule;
  - a usage chain activates when its active flag is 1 in any month of the window, for a client
    dormant at the observation month (and holding the required product);
  - a loan's closing is fixed by `maturity_months` (no early settlement): a closing target would
    score AUC 1 from an as-of feature, so it is degenerate, not a leak;
  - targets for status products are built from the flag, so lineage exclusion doesn't drop the
    status column and its legitimate churned signal.
- **Hidden traits** (`D = 5`): wealth, transactional activity, digital, credit appetite,
  cross-border. They shift by subsegment, nationality group and employment.

#### Product rates
From public UAE ballparks (D-064), mostly surveys and partly dated. Exact levels matter much less
than the dynamics and correlations. The ballparks:
- about 53 credit cards per 100 adults;
- low personal-loan penetration among expats, since banks prefer salary-transfer clients for
  unsecured lending;
- about 30% of residents own a home, often bought in cash;
- mobile banking used by about 72–90% of residents;
- low penetration of investment products.

Sources: [cards](https://thenationalnews.com/business/uae-credit-cards-among-costliest-1.494195),
[personal loans](https://arabianbusiness.com/gcc/lending-less-407739),
[home ownership](https://gulfnews.com/business/property/70-of-uae-residents-still-opt-to-rent-rather-than-buy-homes-1.1863459),
[mobile banking](https://expatica.com/ae/finance/banking/mobile-banking-in-the-united-arab-emirates-72232),
[investment products](https://www.marmoremena.com/uae-asset-management-industry-an-overview/).

**As few numbers as possible per product** (D-065), values in `spec/products.py`:
- the share held (or active) per profile;
- for 0/1 products, the adoptions a month in a 100k book (credit card and e-banking: after
  onboarding). These include the adoptions that refill the holdings of clients who left the bank;
- for loans, the term;
- for usage chains, the mean active spell.

How long a holding lasts is derived from these.

| Product | Minimum income (AED a month) | Held (private / priority / affluent / mass) | Set | Derived |
|---|---|---|---|---|
| Current/savings | — | 99% everywhere | — | — |
| Credit card | 5,000 | 85 / 80 / 65 / 30% | 500 adoptions a month after onboarding | held ≈ 6 years |
| E-banking | — | 80 / 90 / 90 / 75% | 120 registrations a month after onboarding | held for decades |
| Term deposit | — | 40 / 30 / 15 / 4% | 260 adoptions a month | held ≈ 2.7 years |
| Digital wealth | — | 10 / 20 / 12 / 2% | 400 adoptions a month | held ≈ 10 months |
| Traditional wealth | — | 60 / 35 / 10 / 1%, higher for Retired | 42 adoptions a month (≈ 33 refill leavers' holdings) | held ≈ 33 years |
| Personal loan (≥ 1 account) | 5,000 | 5 / 10 / 20 / 20%, mostly salary-transfer clients | 48-month term (UAE maximum) | — |
| Auto loan | 5,000 | 3 / 8 / 12 / 6% | 60-month term (UAE maximum) | — |
| Home loan | 15,000 | 15 / 20 / 10 / 2% | 300-month term (UAE maximum for expatriates) | — |
| FX activity | — | Active: 60 / 45 / 30 / 12% | Mean active spell 24 months | — |
| Digital activity | — | Active: 80% of e-banking clients | Mean active spell 36 months | — |
| Card activity | — | Active: 85 / 85 / 80 / 75% of card holders | Mean active spell 24 months | — |
| Current/savings activity | — | Active: 91 / 93 / 94 / 96% (≈ 10% dormant without salary transfer, ≈ 1% with it) | Mean active spell 180 months | Dormant spell ≈ 12 months |
| Revolver (hidden) | — | 10 / 20 / 30 / 45% of card holders | Mean spell 24 months | — |

Drivers (log-odds loadings and effects) live in `spec/products.py`. Beyond traits and age:
- **For the reversal trap:** the card adds the digital trait (0.3) and the onboarding channel
  (digital −1.5); e-banking and digital activity add the onboarding channel (+3.0, +1.5).
- **Personal loan:** a rare high-rate nationality (+1.5).
- **Term deposit and wealth:** the bonus trigger.
- **Calendar:** FX wake-ups rise in summer and digital wake-ups trend up
  ([time effects](#time-effects)).
- **Usage chains:** card activity loads on activity (0.6); current/savings activity on activity
  (0.5) and salary transfer (+2.4); the revolver state on credit appetite (0.5) and wealth (−0.3).

The shares hold over the whole panel, since the book's tenure and age are in their steady state
([entry and exit](#mix-by-profile)): the holdings checks compare them with the spec at the first
and at the last panel month (digital activity, the uptake-trend product, at the first only).
Realised volumes run a little above the set ones because the book, and with it the holders, grow
≈ 0.2% a month; for products that build up over tenure the volume check nets that growth out.
Holdings at month 1 agree with income, traits and tenure: starting holdings come from the same
chances as later adoption, the income threshold included (maths §3).

**Second entity** (optional, M3; likely not needed): a smaller PSB-like subsidiary is another spec
dict, generated and written separately, to test that entities are never merged (D-034). Not built.

### Amounts
Every amount is a **median multiple of a hidden base per profile**: flows scale with the true
income, balances with the wealth base. Values live in `spec/amounts.py`; the formulas are in
[maths §4–§6](#4-amounts-lognormal-body-power-law-tail). All amounts are AED, rounded to 0.01;
counts are whole numbers.

#### Levels
Median multiple of the base, per profile, in a non-seasonal month after the new-client ramp. The
median holds for a client at its own trait means. Holders and active users are selected on the
same traits their amounts load on, so their realised medians sit a little higher.

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

#### Persistence and variation
- **Stocks** (current/savings, term deposit, wealth) combine four parts:
  - a persistent client effect (sd 0.7 for current/savings, 0.5 for the others);
  - monthly AR(1) noise (ρ 0.8, stationary sd 0.25);
  - the wealth trait's deviation from the client's mean (loading 0.3);
  - a persistent power-law multiplier.

  Target: lag-1 correlation of log balances ≥ 0.9.
- **Flows** (non-salary inflow, spending outflow, card spend, FX) combine:
  - a persistent client effect (sd 0.4);
  - AR(1) noise (ρ 0.3, stationary sd 0.35);
  - one trait's deviation: activity 0.2 for account flows, activity 0.3 for card spend,
    cross-border 0.25 for FX;
  - the client's current/savings deviation × 0.3.

  Target: lag-1 correlation of log flows in consecutive active months 0.6–0.8.
- **Counts** are overdispersed: 1 + Poisson(mean × G), G ~ Gamma(shape 2, scale 1/2) per client and
  month, in active months; 0 otherwise.
  - Outflow mean 12; card spend 10 (× exp(0.3 × activity deviation)).
  - Remittance 1 + Poisson(0.5); FX 1 + Poisson(1).
  - Inflow count: salary (1) + Poisson(2 G) + 1 if a balance transfer came in.
- **New clients** ramp up: current/savings balance × 0.5 in their first month, × 0.75 in the second,
  full from the third.

#### Current/savings account
- **Balance first.** The monthly average balance follows its own path, with the summer dip.
  Inflow = salary + transfers + other; outflow = remittance + cash + bills + transfers.
- **Salary** = true income for salary-transfer clients, every month, plus the bonus in the bonus
  month; 0 for everyone else.
- **Non-salary inflow** is (inflow multiple − 1) × income for salary-transfer clients and 0.4 ×
  inflow multiple × income for the others, times the flow variation. It splits into transfers and
  other: the "other" share is 0.2 Employed, 0.6 Self-employed, 0.3 Unemployed, 0.5 Retired and
  0.7 Other, plus 0.1 in Private.
- **Spending outflow** = 0.85 × (salary without bonus + non-salary inflow) × its own flow
  variation, split into the outflow subcategories; school fees add to bills.
- **Own-product payments** (card repayment, loan instalments) leave the account as outflow
  transfers. Term-deposit and wealth top-ups stay out.
- **Booking:** any change in the balance beyond the month's flows is booked as a transfer, in or
  out. So **inflow − outflow equals the change in the monthly average balance exactly**, and the
  summer dip shows as outflow above inflow.
- **Dormant months:** inflow, outflow, every subcategory and their counts are exactly 0, and the
  balance stays frozen at its last value. On reactivation the balance returns to its path, booked
  as a transfer.

#### Subcategories
Each client's mean shares are the profile's base shares, tilted by its current trait deviations and
descriptors, then renormalised. Monthly shares vary around them (Dirichlet, concentration 50), so
subcategories aren't perfectly collinear with their totals; they add up to the total exactly.

| Profile | Outflow (spending): remittance / cash / bills / transfers | Card spend: travel / retail / online / dining |
|---|---|---|
| Private | 5 / 3 / 12 / 80 | 45 / 25 / 15 / 15 |
| Priority | 12 / 8 / 20 / 60 | 30 / 32 / 20 / 18 |
| Affluent | 20 / 15 / 25 / 40 | 18 / 40 / 24 / 18 |
| Mass | 30 / 30 / 25 / 15 | 6 / 50 / 24 / 20 |

- **Remittance:** only remitters send remittances.
  - The persistent remitter flag is held by 30 / 40 / 50 / 60% of non-nationals (private → mass)
    and by no UAE or GCC national.
  - A non-remitter's remittance is exactly 0, and its share goes to the other three subcategories.
  - The share is × 1.2 for ASIA and AFRICA, × 0.5 for WESTERN and × 0.8 for OTHER.
  - It is also × (income / subsegment median)^−0.3, so it falls as income rises.
- **Cash** × exp(−0.4 × digital deviation − 0.2 × wealth deviation).
- **Card travel** happens only in travel months.
  - The chance of a travel month is min(0.95, base × 2 in July–August × exp(0.5 × cross-border
    deviation)), with base 0.5 / 0.4 / 0.3 / 0.1 (private → mass).
  - In other months travel spend is 0 and its share goes to the others.
  - The summer factor multiplies the travel amount itself, so total spend rises with it.
- **Share tilts:** travel × exp(0.4 × cross-border deviation), online × exp(0.4 × digital
  deviation).

#### Credit card
- **Limit:** set when the card is taken, from a few product tiers.
  - Tiers: AED 5k, 10k, 20k, 35k, 50k, 75k, 100k, 150k, 250k, 500k.
  - The limit is the largest tier at or below the limit multiple × true income (at least the
    lowest tier).
  - 10% of new cards get one tier up (credit trait above the client's mean) or down (otherwise).
  - It is redrawn only when the client takes a card again; 0 without a card.
  - Stored as `decimal(18,2)`, the mart's one decimal column.
- **Revolver or transactor** (hidden chain). Each client has a fixed repayment share between 5% and
  30% (uniform).
- **Each month,** with `M` the month-end balance:
  - transactor: repays last month's balance in full; `M` = this month's spend;
  - revolver: repays its share of last month's balance; interest = 3% of what it carried;
    `M` = carried + interest + spend;
  - spend is the wanted spend, for a revolver × (1 − last month's utilisation) (it spends less as
    the card fills up), capped at limit − carried − interest (≥ 0); 0 in a dormant month;
  - a card given up this month repays its whole balance and ends at 0.
- **Utilisation** = `M` / limit, null without a card. Interest above 0 reveals a revolver.

#### Loans, term deposit, wealth
- **Loans:** an annuity per account, summed per loan type.
  - Principal at opening = multiple × true income × exp(N(0, 0.3²)): personal 8, auto 5, home 60
    (the UAE cap for personal loans is 20×).
  - Equal monthly instalments at fixed annual rates of 7% / 4% / 5% (ballparks the SDS accepted),
    from the month after opening until maturity.
  - The outstanding balance and instalment per loan type are summed over the client's accounts.
    The starting book's accounts are amortised from their opening.
- **Term deposit:** the balance is drawn at adoption and at each 12-month rollover (at least AED
  10k) and stays fixed in between. 0 when not held.
- **Wealth:** assets under management = the stock formula × one shared market index.
  - The index has a monthly log return N(0.005, 0.03²); it is 1 in the month the starting book is
    drawn and is recorded in the truth.
  - Digital and traditional wealth have their own client effects and noise. 0 when not held.

#### FX and logins
- **FX** is a separate activity: currency conversion, foreign transfers and travel money;
  remittances stay in account outflow. Volume and count only in active months; its summer factor
  applies in July–August.
- **Logins** (digital activity), for an active user:
  - logins a month 7 / 10 / 13 / 16 (private → mass) × exp(0.4 × digital deviation), × 2 for
    digitally onboarded clients;
  - the mobile share is σ(1.5 + 0.5 × digital deviation − 0.3 × (age − 40) / 10);
  - mobile and online counts are each overdispersed, and an active month has at least one login;
  - dormant or unregistered clients have 0 logins. The login levels are ballparks the SDS
    accepted.
- **Days since last login** (month end): for an active month, a uniform day after the month's last
  login; dormant months add the days in the month; null if the client never logged in.
  Starting-book clients registered but dormant are taken to have logged in 30–720 days before.

#### Time effects
Seasonality differs by profile: Mass clients travel little, and school fees vary less than income,
so they weigh most on Affluent budgets.

| Effect | When | Private | Priority | Affluent | Mass |
|---|---|---|---|---|---|
| Card travel spend × | July–August | 1.6 | 1.5 | 1.4 | 1.15 |
| FX volume × | July–August | 1.4 | 1.3 | 1.25 | 1.1 |
| FX wake-up log-odds + | moves into July, August | 0.5 | 0.4 | 0.3 | 0.1 |
| Current/savings balance × | July–August | 0.90 | 0.92 | 0.94 | 0.98 |
| Card spend other than travel × | December | 1.15 | 1.12 | 1.12 | 1.08 |
| School-fee payers (clients aged 28–55 when drawn) | — | 50% | 50% | 45% | 15% |
| School fees a year (AED; × lognormal, sd 0.3) | 40% September, 30% January, 30% April | 120k | 80k | 50k | 12k |

- **Bonuses:** half of salary-transfer clients, in a fixed month of their own (January–April),
  worth 1–2 × income, every year; booked in salary inflow. Trigger: term-deposit and wealth
  adoption odds × 2 in the 2 following months. Calendar effects act on adoption and wake-up odds
  only, not on how long spells last.
- **Ramadan** stays out (round 1, Q94).
- **Drift** (monitoring trap):
  - Digital wake-up log-odds rise by log(1.2) a year from the first panel month: a gradual uptake
    trend.
  - An app relaunch at panel month 16 (2026-01) multiplies mobile logins by 1.8. The factor is set
    so the PSI clears 0.25 (1.3 gave 0.07).

#### Segment overlap
Subsegments overlap in amounts, but their medians are ordered.
- About 25% of MM clients hold more current/savings than the UM median. The target range is
  20–30%, set by the current/savings client effect.
- Private is far apart from everyone else: fewer than 5% of Upper Priority clients sit above the
  Lower Private median.

### Feature mart

#### Names
All names are lowercase and come from one grammar (`mechanisms/mart.py`):
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
- **Trap columns** end in `_trap_{kind}` (D-069); extra columns are `extra_{nnnn}_trap_weak` /
  `extra_{nnnn}_trap_noise`.

#### Columns
147 columns, in this order:

| Group | Columns |
|---|---|
| Keys and description (14) | `client_id`, `snapshot_month`, `segment`, `subsegment`, `nationality_group`, `nationality`, `employment_status`, `income`, `salary_transfer_flag`, `emirate`, `onboarding_channel`, `age`, `residence_days`, `relationship_days` |
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
| Trap columns (10) | [trap summary](#trap-summary): five look-ahead columns, then the null controls and quality columns |

#### Null rule, history and types
- **Nulls only where the retail data has them:**
  - missing income;
  - residence for nationals and non-residents;
  - utilisation without a card; months to maturity without an account;
  - days since last login for clients who never logged in;
  - months since last when there is no non-zero month since the later of relationship start and
    the start of the simulation;
  - ratios whose 3–5 average is 0;
  - the trap columns: the upstream target (holders, immature months), the shifted column (no next
    month), the all-null one.

  A null is a true null in pandas, parquet and Spark. Nullable integers display as `<NA>` in
  pandas.
- **A rollup whose window reaches before relationship start is null**, as in the retail dataset.
  Spark's `avg` ignores nulls, so any recompute counts the months in the window explicitly.
  Utilisation's rollups average the months with a card.
- Clients already on the books at month 1 have complete windows from the burn-in months, so all 24
  months are usable. The generator assumes no particular observation window; [dataset](dataset.md)
  has an example.
- **Types:**
  - flags are 0/1 integers (`int`);
  - counts and nullable counters are `bigint`, as are maxima and minima of counts;
  - amounts are `double` rounded to 0.01 (derived averages, deviations and ratios are not
    rounded);
  - `cc_limit` is `decimal(18,2)`;
  - categoricals and statuses are strings; `snapshot_month` is a date (T18).

#### Physical form
Parquet partitioned by `snapshot_month` (`snapshot_month=YYYY-MM-01/`), written one month at a
time by pyarrow into `<out>/mart/` and `<out>/oracle/`, with `<out>/truth.json` beside them.
`conf/local/` maps the logical source to `<out>/mart/` (an example lives in `conf/base/`);
`truth.json` and the oracle are never mapped. The canonical dataset lives in
`data/01_raw/synthetic_canonical/`.

### Trap summary
Traps sit on **two products**, so a test of either target meets every kind (D-069): credit card
acquisition (`cc_flag` 0 → 1) and personal-loan opening (`loan_personal_cnt` rises). A few concern
no product. There are two sorts:
- **Trap columns** (`trap_column` true) are added only to test the framework. Their names end in
  `_trap_<kind>`, so anyone reading the mart sees them.
- **Traps in real columns** (`trap_column` false) are ordinary columns whose realistic behaviour is
  the trap, such as age's inverted U or nationality's rare level. They keep their real names: the
  framework meets the same columns under the same names in the real mart, two of them carry two
  traps, and some traps sit in no single column.

The list lives in `spec/traps.py` and in `truth.json` (`spec.traps`); the notebook shows it with
each trap's evidence.

| Product | Trap | Trap column? | Column | Construction | Expected behaviour |
|---|---|---|---|---|---|
| Credit card | Calibrated leak | yes | `cc_preapproval_score_trap_leak` | `round(500 + 100 · (μ · y + ε))`, `y` = acquisition in the next 3 months (within the panel), `ε ~ N(0, 1)`, `μ = √2 · Φ⁻¹(0.97)`; holders get `ε` only | Univariate AUC ≈ 0.97 for card acquisition in 3 months; beats the oracle on its own window (w = 3; also at w = 1, not at w = 6); the leakage screen flags it |
| Credit card | Moderate leak | yes | `cc_campaign_response_score_trap_leak` | As above with `round(50 + 10 · …)` and AUC 0.875; its own `ε`, independent of the first leak's (checked) | Just above the oracle at w = 3 (≈ +0.03 AUC), about level at w = 1, below at w = 6, but far above any real column: tests "implausibly strong for this target", not only an absurd 0.97 |
| Credit card | Upstream target | yes | `cc_acquire_next_3_months_flag_trap_upstream_target` | 1 if the card is taken in any of the next 3 months, for non-holders; null for holders and in the last 3 panel months; leavers without a card count as 0 (upstream treats leavers as negatives) | The "Target Factory skipped" path and lineage exclusion (T12); Target Factory's own target matches it except for leavers (null there) |
| Credit card | Simpson's reversal | no | login columns, `onboarding_channel` | Digitally onboarded clients log in far more (registered, active, × 2 logins) but take cards less (−1.5); within each channel the card chance loads on the digital trait (0.3), as logins do | Logins vs card acquisition: positive within each onboarding channel, negative pooled. (Grouping by subsegment can't show it: Mass is 94% of the eligible rows) |
| Credit card | Half-strict income threshold | no | `income` | [Income thresholds](#income-thresholds-half-strict-eligibility) | The eligibility step log shows the null-income drop |
| Credit card | Onboarding wave | no | `relationship_days` | Most adoption in the first 3 months | Strongest single driver for new clients |
| Credit card | Eligibility-defining | no | card amounts, `cc_active_flag` | 0 for non-holders | Constant within the eligible population; flagged |
| Credit card | Decimal column | no | `cc_limit` | `decimal(18,2)` | Read by Spark as decimal; pandas gets Python objects unless it casts |
| Personal loan | Process leak | yes | `application_loan_personal_cnt_trap_process_leak` | An opening at `t+1` is preceded by an application at `t` with chance 0.8; declined applications (never opened) are 30% of all, drawn with chance ∝ the client's opening chance at `t+1` | Beats the oracle for openings in the next month (w = 1), not at w = 3 or 6; leakage screen plus human review |
| Personal loan | As-of misalignment | yes | `loan_personal_bal_trap_shifted` | Holds next month's `loan_personal_bal` (an upstream join on the wrong month); null where the client has no next month: it leaves, or it is the panel's last month. The real column comes from the name, so the spec's parameters are just `{"months": 1}` | Beats the oracle for openings next month (w = 1), not at w = 3 or 6; a time-alignment check (the column against its real sibling one month on) catches it. Two realistic tells: its nulls reveal next-month exits, which would leak the negatives of a target that counts leavers as negatives (an option D-066 allows), and it is all-null in the latest month |
| Personal loan | Rare high-rate level | no | `nationality` = Ghana (≈ 0.35% of clients) | +1.5 on the personal-loan log-odds | Stands out in event rate by level; unstable in CV |
| Personal loan | Inverted U | no | `age` | Peak in the mid-30s | Spearman ≈ 0, mutual information high |
| Personal loan | Hidden openings | no | `loan_personal_maturity_months` | A maturity in the same month hides an opening | Predictive under a "count at the end" rule only |
| Personal loan | Eligibility-defining | no | `loan_personal_maturity_months` | All null under "first loan" eligibility | Flagged as all-null within the eligible population |
| Any | Null controls | yes | `insurance_premium_vol_trap_null_control` (lognormal, persistent per client), `branch_visit_cnt_trap_null_control` (zero-inflated Poisson), `preferred_language_trap_null_control` (Zipf categorical, persistent) | Independent of everything | Univariate AUC ≈ 0.5 for every target |
| Any | Quality | yes | `paper_statement_flag_trap_near_constant` (99.9% zeros), `legacy_risk_grade_trap_all_null` (all null) | | Flagged by the quality checks |
| Any | Drift (monitoring) | no | login columns | [Time effects](#time-effects) | PSI > 0.25 after panel month 16, ≈ 0 before |
| Any | Collinearity | no | rollups and identities | Rollups of one measure over `0_2` and `0_5`; `<product>_status == "active"` ⇔ `<product>_flag`; `product_cnt` = product flags + loan counts > 0; inflow − outflow = change in `casa_bal`; subcategories sum to their total | Correlation views and VIF flag the clusters (infinite for the identities) |
| Any | Dirty switches, off by default | no | — | Duplicate client-months; a month with the login columns null (an outage); income × 12 from one month on (a unit change); a few `casa_bal` typos × 1,000 | Contract checks fail loud; operational monitoring flags them (tests on the `unit` preset only). Known limit: the rollups stay clean, while a real upstream mart would roll up its own bad values (stated, not built) |
| Any | Extra columns, off by default | yes | `extra_{nnnn}_trap_weak` / `_trap_noise` | 10% weak (a trait plus noise, rank correlation 0.1–0.3), the rest pure noise | Scale tests; weak ones rank above noise |

Later (not in M1): an interaction-only feature.

### Ground truth and oracle
- **Oracle file** (`oracle/`, parquet, same keys and partitions as the mart). Per client and month:
  - the hidden traits `z_*`;
  - the chance applied to every event that month, given the state at the end of the previous month
    (`p_<product>_acquire`, `p_<loan>_open`, `p_<chain>_activate` / `_lapse`; null where the client
    was not at risk). Row `t` holds the chance of the move into month `t`, which the month-`t`
    features already show; never join it to an observation at `t`;
  - `score_<product>`: each product's log-odds of adoption, opening or wake-up without the
    intercept and the state terms, calendar terms included (§3), the input for window
    probabilities; `lapse_<chain>`: each usage chain's monthly lapse chance;
  - each loan slot's months to maturity (`<loan>_remaining_1..4`, 0 = empty);
  - hidden attributes: `true_income`, `wealth_base`, `remitter_flag`, `school_payer_flag`,
    `bonus_month` (0 = none), `revolver_flag`, the power-law multipliers `pareto_<stock>`;
  - the regression oracle: `spend_cc_next_3_months_{mean,q10,q50,q90}` for card holders.
- **Window probability, on demand** (`window_probability(mart, oracle, truth, target, w)`, D-066).
  It is keyed to the observation month, so no consumer shifts rows.
  - **The formula:** for an observation at `t`, the chance of an event is `1 − ∏(1 − p̃_s)` over
    `s = t+1 … t+w`. `p̃_s` is the chance the client would face with its state frozen at `t`, on
    the realised trait path, from the intercepts in `truth.json` and `score_<product>` at `s`.
  - **"Frozen at `t`" means:**
    - never / churned status as at `t`;
    - onboarding by tenure;
    - loan slots and maturities as scheduled at `t`; a maturity in month `s` hides an opening;
    - for a chain, the required product's leaving chance compounded month by month, and the steady
      share `w / (w + lapse)` at `t+1` when the required product was adopted at `t`.
  - **Checks:** with `w = 1` it equals the recorded chance at `t+1` (tested to 1e-12). The oracle
    family sets it against the checks' own realised targets: nulls agree, events match the sum of
    the probabilities, and the AUCs and truth's sizing (expected events in 6 months, the
    low-confidence flag) are recomputed and equal truth's to 1e-9. Oracle AUCs must lie in
    [0.5, 1]: a rule for pooled AUCs; per segment it is checked at the canonical size only (a
    small segment of the 5k preset can dip below 0.5).
  - **Not the recorded rows:** multiplying the recorded chances instead conditions on the outcome
    and understates positives (card acquisition AUC ≈ 0.77 instead of ≈ 0.84 at `w = 3`, ≈ 0.72
    instead of ≈ 0.83 at `w = 6`; 30k clients, 2026-10-19).
  - **Null** where the target is: not eligible at `t`, the client leaves before `t+w`, or the
    window runs past the panel.
  - **Why it is still the ceiling:** the oracle conditions on the realised trait path, but traits
    and exits get no feedback from holdings.
  - It also checks that option 1's offset brings scores back to the true level; comparing every
    sampling option against it is on the Phase 3 wishlist (D-123).
- **Standard targets** (oracle AUCs and sizing for `w` = 1, 3 and 6 months):

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
  spend per card holder.
  - They come from 200 simulated forward paths of the card chains, traits, the current/savings
    deviation and spend, starting at the true state. The paths have their own random stream and
    are conditioned on the client staying.
  - It integrates over the trait path, unlike the window probability.
  - It takes more than half the generation time; it is kept for regression, the second
    task type (D-080).
- **`truth.json`** holds only what can't be recomputed from the mart and the oracle file:
  - `generator_version`, numpy / scipy / pandas / pyarrow `versions` (the seed-to-data mapping
    depends on them), `seed`, `preset`, `n_clients`, `n_months`, `first_month`;
  - `spec`: population, products, amounts, seasons and the trap list (`spec.traps`, the trap
    summary);
  - `calibration`: intercepts per product and profile, leaving chances, usage mean scores;
  - `market_index`: the path behind wealth balances;
  - `columns`: one entry per mart column: name, written type, kind (`id`, `time`, `static`,
    `categorical`, `holding`, `stock`, `flow`, `count`, `rollup`, `trap`, `noise`);
  - `oracle`: per binary standard target:
    - `expected_events_6m`, which is 6 × the mean monthly sum of the one-month window probability:
      events, not positive rows, which repeat across up to `w` months;
    - `low_confidence`, true when there are fewer than 200 such events;
    - per window `w1`, `w3`, `w6`: the oracle AUC (Mann–Whitney over every row where target and
      probability are set, all months pooled), the AUC per segment, and the realised positive rows
      a month;
  - `dirty`: the record of the defects, when dirty data is on.

**The oracle AUC is the ceiling.** A model or univariate screen that beats it on the target's own
window (the oracle AUC for the same target and `w`) is almost certainly leaking. The converse
doesn't hold: a leak beats the oracle on the window it was built for, not necessarily on others.
The card leaks (built for `w = 3`) beat it at `w = 3`; at `w = 1` the moderate one about ties it,
and at `w = 6` neither beats it. The loan leaks (process leak, shifted column) beat it at `w = 1`
only (measured on 30k clients, 2026-10-19).

### Code map
`synthetic/` is a separate editable package (`synthetic/pyproject.toml`, D-041). It is dev-only and
never part of `core_modelling`. Under `synthetic/src/synthetic/`, folders split by role: rules and
numbers without logic, the functions that simulate, the hidden truth, and the checks.

**Top level**
- `__main__.py`: the CLI. `python -m synthetic …` runs `output.write_mart`, then
  `checks.suite.write_checks`.
- `generate.py`: the month loop.
  - `generate_mart` runs it in memory: `start_simulation`, `advance_simulation`,
    `finish_simulation`.
  - `month_rows` builds the mart and oracle rows.
  - `buffer_month` holds a month until its look-ahead columns exist.
- `output.py`: `write_mart` drives the loop, writes month by month, then writes the truth.
  `read_output` reads columns or a client sample; `load_truth` is the stale-data guard.

**`spec/`: rules and numbers, no logic**
- `presets.py`: subsegments, profiles, mixes, income → `RETAIL` (the one spec dict) and `PRESETS`.
  Its only functions are two small dict builders (`_sub`, `_profile`).
- `products.py`: `PRODUCTS` (shares, volumes, drivers) and `HOLDING_RULES`.
- `amounts.py`: `LEVELS` (multiples, variation, card, loans, logins) and `SEASONS` (time effects).
- `traps.py`: `TRAPS`, the trap summary.

**`mechanisms/`: the functions that simulate**
- `clients.py`: `draw_clients`, `draw_income`, `draw_hidden_attributes`; the hidden traits
  (`latent_means`, `draw_latents`, `step_latents`).
- `holdings.py`:
  - `product_score`, `time_terms`, `calibrate` (the intercepts);
  - `start_holdings`, and `step_holdings` (every move and its chance);
  - `holding_columns`.
- `seasons.py`: calendar effects: `wake_shift`, `after_bonus`, `season_factor`, `travel_chance`,
  `school_fee_due`, `bonus_due`, `login_drift`.
- `variation.py`: the random parts of amounts:
  - client effects, AR(1) noise and Pareto multipliers;
  - `measure_offsets` (exact medians);
  - counts, Dirichlet shares and `split_amount`.
- `accounts.py`: balances (current/savings, deposit, wealth, loans), the flows through the account
  (inflow, spending, booking), and FX.
- `cards.py`: limit tiers, wanted spend, `step_card` (revolver or transactor).
- `logins.py`: mobile and online logins, days since the last login.
- `amounts.py`: `start_amounts`, `step_market` and `step_amounts`, which runs, in order:
  - the noise steps;
  - the balances;
  - the card;
  - the current/savings flows, which book the card repayment and the loan instalments;
  - FX;
  - logins.
- `mart.py`: the name grammar (`parse_column`); history → rollups, recency and ratios;
  `arrow_schema` (the written types).
- `traps.py`:
  - the trap columns, and `finalize_lookahead` for the look-ahead ones;
  - the extra columns;
  - `apply_dirty` and `dirty_panel` (dirty data).

**`truth/`: the hidden truth**
- `oracle.py`: `STANDARD_TARGETS`, `realised_target`, `window_probability`, `oracle_metrics`.
- `regression.py`: `simulate_card_spend`, a Monte Carlo of next-3-month card spend.
- `truth_file.py`: `build_truth`, `column_schema`, `with_oracle` → `truth.json`.

**`checks/`: written from this spec, never calling the mechanisms**
- `suite.py`: `CHECK_FAMILIES`, `run_checks`, `write_checks` (a process per family),
  `read_checks`.
- `table.py`:
  - row helpers: share, rule, range, one-sided, events against Σp (`sum_row`), named offenders
    (`offenders_row`);
  - estimators: Hill, AUC, PSI.
- `events.py`: the checks' own reading of the data:
  - month-on-month events (`build_panel`, built on `to_panel`);
  - forward-window targets;
  - spec values restated.
- `switches.py`: `check_dirty` and `check_extra_columns`, for the off-by-default switches (not a
  family).
- One module per family, each with `check_<family>(mart, oracle, truth)`: `population.py`,
  `holdings.py`, `amount_rules.py`, `amount_levels.py`, `seasons.py`, `mart.py`, `traps.py`,
  `oracle.py`.

**Inside one month** (`advance_simulation`):
1. `_turn_over` picks the leavers and draws the joiners (`clients.*`, `traps.start_trap_state`).
2. `clients.step_latents` moves the hidden traits.
3. `_join_month` starts the joiners' holdings and amounts.
4. `holdings.step_holdings` moves every product and returns the chances and scores.
5. `amounts.step_market` runs, then `amounts.step_amounts`.
6. `mart.advance_history` updates each client's history.
7. On panel months only:
   1. `regression.simulate_card_spend`;
   2. `buffer_month`, which calls `traps.trap_columns`, `traps.extra_columns` and `month_rows`;
   3. `traps.finalize_lookahead`, once the look-ahead months exist.

**Reading the code for review**, in order:
1. `generate.py` (the loop);
2. `mechanisms/holdings.py` (the chances);
3. `mechanisms/amounts.py` and what it calls;
4. `mechanisms/mart.py`;
5. `mechanisms/traps.py`;
6. `truth/oracle.py` (the ceiling);
7. one check family, e.g. `checks/holdings.py`.

### Outputs and checks
**What comes out** (`<out>/`):
- `mart/snapshot_month=YYYY-MM-01/part-0.parquet`: the feature mart, written month by month with
  explicit types.
- `oracle/…`: the same keys and partitions, hidden columns only. It is never mapped as a source.
- `truth.json`: what can't be recomputed from the two tables ([ground truth](#ground-truth-and-oracle)).
- `checks/<family>.parquet`: the saved check tables (with `--checks`).

**How it is checked.**
- **One table per family.** Each family (`checks/<family>.py`) returns a table with one row per
  check. Its columns are check, stratum, n, expected, realised, tolerance, passed and rule.
- **Where expected values come from.** They are restated from this spec and read from the mart.
  Where the spec defines a value through hidden inputs, the inputs come from the oracle's columns.
- **Two generator functions, both under test.** The checks call only:
  - `mechanisms.mart.parse_column`: the mart family checks that every name parses;
  - `truth.oracle.window_probability`: the ceiling.

  They never call the mechanisms that produce the data, so a generator bug can't pass its own
  check. Every check was shown to fail on a deliberately broken generator.
- **Tolerances:** 4.5 standard errors, a family-wise false-failure rate of about 0.1%.
  - Standard errors are analytical where the statistic has one, on one row per client. Examples:
    binomial shares, Fisher z, Hanley–McNeil AUCs, α/√k for the Hill estimator.
  - A spec range is checked as a range.
  - A rule that must always hold has tolerance 0.
- **Two suites:**
  - `pytest` (≈ 3 min) runs the rule rows on the 5k preset. It also runs prefix stability, the
    Spark recompute of every rollup, the written types and the off-by-default switches: dirty
    data and extra columns, in `checks/switches.py`, which is not a family.
  - `pytest -m slow` writes the canonical dataset and runs every row of every family at 100k.
    Each family runs in its own process, because one needs several GB.
- **The notebook** reads the written canonical dataset and its saved check tables.
  - It opens with a visual tour in Level 2's order: the book, holdings, amounts, time, the mart,
    traps, the ceiling (leakage screen, gains, calibration, regression band) and client stories.
  - An appendix holds the check tables and the tables behind each chart.
  - It is committed with its outputs. That is allowed because it holds synthetic data only (an
    exception in `notebooks/README.md`).
  - The guided EDA notebook replaces it once EDA exists.

Framework tests will later assert against the ground truth:
- screens flag every trap;
- null controls carry no signal;
- no model beats the oracle AUC.

### Interface
```python
from synthetic.generate import generate_mart
from synthetic.output import write_mart, read_output, load_truth
from synthetic.truth.oracle import STANDARD_TARGETS, realised_target, window_probability
from synthetic.checks.suite import run_checks, write_checks, read_checks
from synthetic.mechanisms.traps import trap_summary

generate_mart(preset="unit", n_clients=None, seed=0, n_months=None, dirty=False,
              n_extra_columns=0) -> (mart, oracle, truth)     # in memory, small presets
write_mart(out_dir, preset="canonical", ...) -> truth           # month by month to disk
read_output(out_dir, table, columns=None, client_sample=None) -> pd.DataFrame
load_truth(out_dir) -> dict          # fails loud if another generator, numpy or scipy version wrote it
window_probability(mart, oracle, truth, target, w) -> pd.Series   # the true chance, keyed to t
realised_target(mart, target, w) -> pd.Series
run_checks(out_dir, families=None, client_sample=None) -> {family: table}
```
```bash
python -m synthetic --preset canonical --seed 0 --out data/01_raw/synthetic_canonical --checks
#   --n-clients 50000 (half the memory) · --n-months · --dirty · --extra-columns N
```
The folder must be new or empty. With `--checks`, every family runs in its own process, the tables
are saved in `<out>/checks/`, and the CLI exits with status 1 if any row fails. To read the dataset
through the environment adapter, copy `conf/base/sources.example.yml` to `conf/local/sources.yml`
with the absolute path.

| Preset | Clients × months | Use |
|---|---|---|
| `unit` | ~5k × 24 (≈ 125k rows) | Unit tests and the end-to-end test |
| `canonical` | 100k × 24 (≈ 2.5M rows); `--n-clients 50000` if memory runs short (a few statistical rows then need 100k) | The shared development dataset |

**Budgets:** `canonical` ≤ 10 min and ≤ 3 GB peak; `unit` ≤ 20 s. Measured on the 8 GB Mac
(2026-10-19): `canonical` 337–355 s, within the 3 GB budget (the slow budget test passed); `unit`
≈ 19 s. More than half the time goes to the regression oracle's simulated paths.
`synthetic.__version__` goes up whenever the output changes, so a stale `data/01_raw/` fails loud.

### The maths
Notation: client `i`, month `t`, subsegment `s`, profile `p`, product `k`, latent dimension
`d = 1..5`. `σ(x)` is the logistic function.

#### 1. Latent traits
```
z_i ~ N(μ_s + shift(nationality_group, employment), Σ_p),   Σ_p = D_p R_p D_p,   L_p = chol(Σ_p)
```
Each subsegment has its own mean; scales and the **correlation matrix `R`** are set per profile,
with every correlation between traits kept within [0, 0.2] (the wealthy profiles decouple wealth
from credit appetite).

#### 2. Persistence over time (stationary AR(1))
```
z_i,t = m_i + ρ (z_i,t−1 − m_i) + sqrt(1 − ρ²) · L_p ε_i,t,     ε ~ N(0, I)
```
`m_i` is the client's mean from §1; scalar `ρ` ≈ 0.95 a month keeps the stationary distribution
exact. Segments never change. `Δz_i,d,t = z_i,d,t − m_i,d` is the trait deviation used by amounts.
- **Entry and exit:** each month a client exits with its profile's probability, and each subsegment
  gains `Binomial(n_s, entry rate of its profile)` new clients; entrants draw `z` from their
  stationary distribution and start at relationship day 0.
- **Starting book's tenure and age:** with entry rate `e` and exit rate `x`, a client joined `τ`
  ago is still here with chance `exp(−x τ)`, and the book was `exp(−(e − x) τ)` times its size
  then, so tenure in a book growing at `e − x` has density `∝ exp(−e τ)`: exponential at the entry
  rate, mean `1 / e`. Clients join at an age `~ N(mean age − 1 / e, sd)` truncated to 18–85; the
  starting book draws `τ ~ Exp(e)` and is `τ` older than the age it joined at, so age and tenure
  are jointly stationary (`clients._draw_dates`).
- **Burn-in:** `B` months (default 12) are simulated before month 1 and discarded from the output.
  They put traits, holdings and amounts in steady state and provide the history that month 1's
  rollups need.

#### 3. Holdings and accounts
Every product has one monthly chance per client, on the log-odds scale:
```
logit p_i,k,t = α_k,p + score_i,k,t + log(2) · churned_i,k
score_i,k,t   = Σ_d β_k,d · z_i,d,t + age_k(age_i,t) + effects_k(descriptors_i)
                + log(0.2) · below_threshold_k(i) + time_k,p(t) + log(2) · after_bonus_i,k,t
```
- **Terms:**
  - `age_k` is a slope per decade or an inverted U around a peak (personal and auto loans peak in
    the mid-30s, home loans at 42).
  - `effects_k` are salary transfer (credit card, personal loans, current/savings activity),
    nationality (home loans; the rare level on personal loans), Retired (traditional wealth) and
    the onboarding channel (card, e-banking, digital activity).
  - The churned term applies to status products only.
  - `time_k,p(t)` is the FX summer wake-up and the digital drift; `after_bonus` is the bonus
    trigger.
- **0/1 products:** a holder leaves with the product's leaving chance `q_k`; a non-holder adopts
  with `p`. `q_k` = (adoptions a month − refills of holders who left the bank) / holders, from the
  spec.
- **Loans:** each month accounts that reach their term close (no early settlement), then at most one
  account opens with chance `p`; each account runs the product's fixed term.
- **Usage:** a dormant client wakes with `p`; an active one lapses with
  `σ(logit(1 / mean active months) − 0.5 · (score − mean score))`, so keen clients stay active
  longer.
- **Onboarding wave** (credit card, e-banking): in a new client's first 3 months the chance is the
  constant `1 − (1 − π_i)^(1/3)` that reaches the client's steady-state share `π_i = p / (p + q)`.
- **History and starting book:** other 0/1 products follow never → held ⇄ churned from relationship
  start; the stepped chain has an exact closed form for the chance of holding (and of having
  churned) after `T` months of tenure, and the starting book draws each client's state from it.
  Loans start with `Binomial(min(T, term), p)` accounts opened uniformly in that window.
- **Calibration:** `brentq` per product and profile on the intercept `α`, on the starting book.
  - It matches the spec's share: the mean held-after-tenure chance; the steady-state share for
    products with onboarding; the chance of at least one account for loans; the active share for
    usage.
  - Time effects and the bonus trigger are left out, so the shares wobble slightly with the
    season.
- **Sizing rule**, recorded in the ground truth: every standard target keeps ≳ 200 events in a
  6-month window at the canonical size, or is flagged as low-confidence.

#### 4. Amounts: lognormal body, power-law tail
For a holder in an active month:
- `m` is the level multiple;
- `base` is the true income or the wealth base;
- `adj` is the salary-transfer adjustment and `ramp` the new-client ramp;
- `season` is the profile's seasonal factor;
- `M_t` is the market index for wealth, 1 otherwise.
```
N_i,k,t  = λ_k · Δz_i,d(k),t + η_i,k + ν_i,k,t,    η ~ N(0, e_k²) once,  ν AR(1) (ρ_k, sd s_k)
stock    B_i,k,t = m_k,p · base_i · adj_i · ramp_i,t · season_k,p(t) · M_t · exp(N_i,k,t − c_k,p) · W_i,k
flow     F_i,k,t = m_k,p · income_i · adj_i · season_k,p(t) · exp(N_i,k,t + φ · D_i,t − c_k,p)
         W_i,k ~ Pareto(x_m = 1, a_k) once;   D_i,t = log of the current/savings balance's random part
```
- **The median offset `c`** makes the median of the random part exactly 1, so the median amount is
  the spec's multiple.
  - The sum of a normal and `log W ~ Exponential(a)` is an exponentially modified normal, whose
    median is in `scipy.stats.exponnorm`.
  - For a stock, `c = log median` of `N(0, s²) + Exp(a)` with `s² = λ² σ_d,p² + e² + s²(ν)`.
  - For a flow, the balance term adds `φ² s²_casa` to the normal part and an `Exp(a_casa / φ)`
    part, less `φ c_casa`.
- **The tail:** by Breiman's lemma, a lognormal times an independent Pareto has a regularly varying
  tail with index `a`. That is a true power-law tail on a lognormal body.
  - `B^φ` has index `a / φ`, so flows have thinner tails.
  - `W` is persistent, so balances don't jump.
- **Non-holders and dormant months:** exactly 0.

#### 5. Counts, subcategories, card balance
```
count     = active · (1 + Poisson(μ_k · exp(0.3 Δz_activity) · G)),   G ~ Gamma(2, 1/2)
shares_t  ~ Dirichlet(50 · s̄_i),   s̄_i = base_p ⊙ tilts_i / Σ;   sub-amount = round(total · share)
card      M_t = carried_t + 0.03 · carried_t · revolver + spend_t,
          carried_t = revolver · (1 − k_i) · M_t−1,   repayment_t = M_t−1 − carried_t
          spend_t = min(wanted_t · (1 − u_t−1 if revolver), limit − (1.03 · carried_t if revolver))
          utilisation u_t = M_t / limit
loan      instalment = P r / (1 − (1 + r)^−n),   outstanding after j instalments = P (1 + r)^j − A ((1 + r)^j − 1) / r
```
Sub-amounts are rounded first and the total is their sum, so subcategories add up exactly.

#### 6. Seasonality and drift
Seasonal factors are per measure and profile ([time effects](#time-effects)): multiplicative on
amounts, additive on log-odds for wake-ups. Drift is the digital uptake trend and the app
relaunch; their parameters are in the spec (`seasons.drift`).

## Open questions
None. Answered in the SDS's review (2026-10-19):
- exits stay random;
- the moderate leak and the shifted column are built;
- dirty defects stay out of the rollups (stated as a known limit);
- the loan rates and login levels are accepted;
- the decisions taken during the build are confirmed.

### Future to-dos (the LDS, 2026-10-21)
Not built now. Each new column names what it is, like the traps (`_trap_<kind>`, D-069).
- **More noise columns** of several kinds (univariate, random), to further prove the checks work.
  Today there are the three null controls (`*_trap_null_control`) and the off-by-default
  `extra_{nnnn}_trap_noise` / `_trap_weak` columns; new ones would be e.g. `_trap_noise`.
- **Columns with very low fill rates** (say 0.1–2% filled), to test the quality checks. Today the
  mart has only an all-null and a near-constant column; new ones would be e.g. `_trap_low_fill`.
