# Handover: synthetic_build — steps 3–7 of the synthetic data, built in one go
_Written: 2026-10-16 · branch: main · last commit before the build: see `git log` (the spec and this
plan are committed together)_

## Goal
Finish the synthetic data generator (M1 steps 3–7) in one go, then one thorough review by the SDS
(D-067). The **spec** is `docs/components/test_harness.md` (what the data is; every number lives
there or in the spec modules). **This file** is how to build it: architecture, stages, function
signatures, checks, the integration protocol, the review package. When the two disagree, the spec
wins; fix this file. Removed when M1 closes.

## State
| Stage | Builds (test_harness step) | Status | Commit |
|---|---|---|---|
| A | Foundations: refactor, 0/1 flags, hidden attributes, new chains, time hooks, writer, slow suite | done (review pending) | see log |
| B | Amounts, time effects, segment overlap (step 3) | done (review pending); 12/12 mutations caught | see log |
| C | Mart: names, rollups, null rule, types, prefix stability (step 4) | done (review pending) | see log |
| D | Traps, drift evidence, dirty switches, extra columns (step 5) | done (f8c0fd0; Simpson regrouped by onboarding channel eb4fa2c); review pending | see log |
| E | Oracle: window probabilities, metrics, relevance, regression oracle, `truth.json` (step 6) | done (review pending) | see log |
| F | Output, source mapping, CLI, budgets, notebook, review guide (step 7) | not started | |

## Pending fixes
Stage B review fixes applied (2026-10-16).

## Read first
1. `CLAUDE.md` §1 (code rules), §4 (ML invariants), §5 (environment traps).
2. `docs/components/test_harness.md`, whole (the spec).
3. `docs/decisions.md` D-056, D-063–D-069.
4. The existing package: `synthetic/src/synthetic/` (presets, products, population, latents,
   hazards, holdings, generate, check_table, checks_*, holding_events) and `tests/`.

---

## 1. Ground rules for every agent
- **Code rules** (`CLAUDE.md` §1, D-063, D-067): every function, private and test functions
  included, has type hints and a docstring; every module opens with a docstring that explains what
  it is for and how it fits (a short paragraph). Functions ≤ ~50 lines, modules ≤ ~300 lines;
  split by responsibility, named `verb_noun`. Functions, not classes. No new dependencies (numpy,
  pandas, pyarrow, scipy, pyspark, pyyaml are available). Comments say why. No dead code.
- **Spec as plain data.** Every number in the spec lives in a spec module (`presets`, `products`,
  `levels`), never inline in mechanism code. Mechanisms read `spec[...]`. Spec typos fail loud
  (`KeyError` is fine).
- **Random streams.** Each mechanism draws only from its own stream (§2.4). Within a stream, draws
  happen in a fixed order and every draw is a fixed-size array per client (or client × slot / path),
  **never sized by an outcome** (draw for everyone, then use where needed). This keeps prefix
  stability and keeps one mechanism's change from re-drawing another's columns.
- **No in-place changes** to state arrays: build new arrays and replace the dict entry (the
  holdings step relies on `before` staying as it was).
- **Fail loud.** No `except` that hides an error; validate shapes and alignment where data meets.
- **0/1 flags are integers in the mart.** Never apply `~` or `&` to an integer flag (bitwise on
  ints gives −1/−2, which is truthy): compare `== 1`, or convert with
  `check_table.flags_as_bool`.
- **Memory.** Never load the whole canonical mart in pandas: read only the columns you need
  (`output.read_output(out_dir, table, columns)`).
- **Commands:** `source .venv/bin/activate`; `ruff check .` and `ruff format <files you touched>`;
  `pytest` (fast) and `pytest -m slow` (canonical). Both green before you report.
- **Don't edit docs** (`docs/`, `worknotes/`, `CLAUDE.md`) unless your task says so; report what
  should change instead. Don't commit; the integrator commits.
- **Report back:** files changed (with line counts), what you built, deviations from this plan and
  why, anything unverified, test results (counts and timings), open issues.

## 2. Architecture

### 2.1 Module map (`synthetic/src/synthetic/`)
| Module | Kind | Holds | Stage |
|---|---|---|---|
| `presets` | spec | population spec, `RETAIL`, `PRESETS`; adds `separation`, `TRAPS`, imports `LEVELS`/`SEASONS` | A, D |
| `products` | spec | product spec and holding rules (new chains, drivers, bonus trigger) | A |
| `levels` | spec (new) | `LEVELS` (amount multiples, variation, counts, subcategories, card, loans, deposit, wealth, logins, ramp) and `SEASONS` (time-effect tables, bonus, school fees, drift); per-file E501 ignore like `presets` | A (stub), B |
| `seasons` | mechanism (new) | time-effect functions: wake shifts, bonus trigger, seasonal factors, school fees and bonuses due, login drift | A, B |
| `population`, `latents` | mechanism | + true income; + `separation` | A |
| `hazards`, `holdings` | mechanism | + time terms in the score; static `requires`; flag names; hidden chains | A |
| `variation` | mechanism (new) | client effects, AR(1) noise, power-law multipliers, median offset (`exponnorm`), overdispersed counts, Dirichlet shares, exact splits | B |
| `balances` | mechanism (new) | current/savings, term deposit, wealth, loan outstanding and instalments | B |
| `flows` | mechanism (new) | inflow, spending outflow, subcategories, own-product payments, booking, school fees, bonuses, FX | B |
| `cards` | mechanism (new) | limits (tiers), wanted spend and subcategories, the monthly card step; works on any array shape (also `(n, paths)` for the regression oracle) | B |
| `logins` | mechanism (new) | login counts, days since last login, drift | B |
| `amounts` | mechanism (new) | hidden client attributes; `start_amounts` / `step_amounts` orchestrating the above | A (attributes), B |
| `names` | mechanism (new) | the column-name grammar: build and parse | C |
| `mart` | mechanism (new) | rollup spec, history buffer, rollups, recency, ratios, column order, arrow schema | C |
| `traps` | mechanism (new) | null controls, quality, leak columns (look-ahead), extra columns, trap summary | D |
| `dirty` | mechanism (new) | dirty-data switches applied to a finished mart | D |
| `regression` | mechanism (new) | Monte Carlo of next-3-month card spend | E |
| `oracle` | ground truth (new) | standard targets, realised targets, window probabilities, oracle metrics, relevance ranking | E |
| `truth` | ground truth (new) | building `truth.json`: schema, spec, calibration, metrics, traps; JSON-safe values | A (basic), E |
| `generate` | loop | `start_simulation` / `advance_simulation` / `finish_simulation`, `generate_mart` | A, B–E |
| `output` | IO (new) | `write_mart`, `read_output`, `load_truth` (version guard) | A, F |
| `__main__` | CLI (new) | `python -m synthetic …` | F |
| `check_table` | checks | + `flags_as_bool`, analytical-SE row helpers | A |
| `checks_population`, `checks_holdings`, `checks_holding_drivers`, `holding_events` | checks | adapted to 0/1 flags and the new chains | A |
| `checks_amount_rules`, `checks_amount_levels`, `checks_seasons` | checks (new) | step 3 | B |
| `checks_mart` | checks (new) | step 4 | C |
| `target_windows` | checks (new) | the checks' own realised targets over forward windows | D |
| `checks_traps` | checks (new) | step 5 | D |
| `checks_oracle` | checks (new) | step 6 | E |
| `check_suite` | checks (new) | `CHECK_FAMILIES` and `run_checks(out_dir, families)` | A, extended per stage |

Each checks module declares `MART_COLUMNS` and `ORACLE_COLUMNS` (lists) and one public
`check_<family>(mart, oracle, truth) -> pd.DataFrame`.

### 2.2 The month loop (`generate`)
```python
STREAMS = ("population", "latents", "holdings", "amounts", "cards", "logins", "traps", "leaks",
           "extras", "regression")                      # appended once, in Stage A

def start_simulation(preset: str, n_clients: int | None, seed: int, n_months: int | None,
                     n_extra_columns: int) -> dict:
def advance_simulation(sim: dict) -> tuple[dict, list[tuple[pd.DataFrame, pd.DataFrame]]]:
def finish_simulation(sim: dict) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
def generate_mart(preset="unit", n_clients=None, seed=0, n_months=None, dirty=False,
                  n_extra_columns=0) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
```
`sim` holds the spec, the streams, the calibration, the client state and the buffers.
`advance_simulation` runs one month and returns the panel months that are now final (none during
burn-in; from Stage D, month `t` is final once `t+3` exists, for the leak columns);
`finish_simulation` flushes the rest with truncated windows. `generate_mart` and `output.write_mart`
both drive this loop and differ only in where the months go. Order within one month:
1. exits and entries (population stream); new clients get descriptors, traits, income, true income,
   wealth base and hidden attributes (`amounts.draw_hidden_attributes`, attributes stream);
2. one AR(1) step of the traits for clients who stayed;
3. holdings (`step_holdings`, with the month for time terms);
4. amounts (`step_amounts`: current/savings activity and balance, flows, card, loans, deposit,
   wealth, FX, logins) from the holdings at the end of the month;
5. the month's mart values → history buffer → rollups, recency, ratios → trap columns that need no
   look-ahead → extra columns;
6. oracle row: traits, chances, scores, loan slots, hidden attributes, regression oracle (panel
   months only);
7. look-ahead buffer → leak columns for month `t − 3` → emit.

Per-client state is reindexed every month the same way (keep stayers, append new clients): one
helper `_keep_and_append(state: dict, stay: np.ndarray, new: dict, n_new: int) -> dict` for all
state dicts (holdings, amounts, history, trap state).

### 2.3 State and hidden attributes
- **`clients` DataFrame** (static per client): descriptors, dates, `income`, `salary_transfer_flag`,
  plus hidden columns never emitted to the mart: `true_income`, `wealth_base`, `remitter_flag`,
  `bonus_month` (1–4, 0 = none), `bonus_factor`, `school_payer_flag`, `school_fee`,
  `repay_share`, `other_share`.
- **holdings state** (as now) + chains `cc_activity`, `casa_activity`, `cc_revolver`.
- **amounts state** (per client): client effects and AR noise per measure, power-law multipliers per
  stock, last current/savings balance and its random part, card limit and balance, loan principal
  per slot, term-deposit balance and months since rollover, days since last login (NaN = never);
  plus the market index (scalar, per month; 1 in the month the starting book is drawn). Mean
  subcategory shares are not state: they follow the client's current trait deviations (as
  persistent as the traits).
- **history** (mart): per rolled-up measure an `(n, 6)` array, newest last; last non-zero month per
  recency measure.

### 2.4 Random streams
| Stream | Draws |
|---|---|
| population | subsegments, descriptors, dates, income, exits, entries (as now) |
| latents | traits (as now) |
| holdings | one uniform per product (incl. the new chains) and client per month (as now) |
| amounts | effects, noise, multipliers; current/savings, flows, subcategories, loans, deposit, wealth, FX, market shock |
| cards | limit tiers and adjustments; travel months; card subcategory shares and counts |
| logins | login counts, days since last login |
| traps | null controls and quality columns |
| leaks | leak columns (look-ahead) |
| extras | extra columns |
| regression | the regression oracle's paths |
| attributes | hidden client attributes (remitter, bonus, school fees, repayment share), so amounts' draws never move holdings |

### 2.5 Output, types, reading back
- `<out>/mart/snapshot_month=YYYY-MM-01/part-0.parquet`, `<out>/oracle/…` likewise,
  `<out>/truth.json`. pyarrow writes one month at a time with an explicit schema from
  `mart.arrow_schema`: flags `int32`; counts `int64`; nullable counters `int64` with nulls;
  amounts `float64` rounded to 0.01; `cc_limit` `decimal128(18, 2)` (cast from float, never NaN);
  strings; the partition value is a date (T18). The month is a partition column, so it is not
  stored inside the files.
- In memory (`generate_mart`) `cc_limit` stays a float; the decimal type exists only when written.
- `read_output(out_dir, table, columns)` reads with pyarrow, adds `snapshot_month` as a date,
  casts decimals to float (the synthetic package's own reader; the Spark test asserts the decimal
  type).
- **`truth` keys are strings** (JSON): `build_truth` turns every dict key into `str(key)` (`True` →
  `"True"`, school-fee terms `{"9": 0.4, …}`), NaN into null, tuples into lists, and round-trips
  through JSON, so the in-memory truth equals what `load_truth` reads. Checks reading
  `truth["spec"]` must look keys up as strings.
- `write_mart` refuses a folder that already holds output (no mixing of runs).
- `load_truth(out_dir)` raises if `truth["generator_version"]` differs from
  `synthetic.__version__` (stale-data guard). Bump `__version__` to `0.3.0` when the build is done.

### 2.6 Tests and markers
- `pyproject.toml`: `markers = ["slow: canonical-size checks (pytest -m slow)"]`,
  `addopts = "-m 'not slow'"` (a later `-m slow` overrides it).
- `tests/conftest.py`:
  - `spark` (as now);
  - `unit_output` (session): `write_mart` of the `unit` preset (seed 0) into a temp folder →
    `(out_dir, truth)`;
  - `canonical_output` (session, slow tests only): runs `python -m synthetic --preset canonical
    --seed 0 --out <tmp>` in a **subprocess**, records wall time and peak memory
    (`resource.getrusage(RUSAGE_CHILDREN).ru_maxrss`; bytes on macOS, KiB on Linux) →
    `(out_dir, truth, timing)`. Until Stage F adds the CLI, call `write_mart` in a subprocess via
    `python -c`.
- One test file per family: `test_synthetic_<family>.py`. Each has a fast test (unit output: the
  rows with tolerance 0 pass) and a slow test (canonical output: every row passes), reading the
  family's declared columns.

---

## 3. Stages

### Stage A — foundations
**Goal:** the existing generator restructured for the rest of the build, with steps 1–2 still green.
1. **Streams** (§2.4) and the loop (§2.2): refactor `generate.py` into `start_simulation`,
   `advance_simulation`, `finish_simulation`, `generate_mart` and `_keep_and_append`. No look-ahead
   yet (every panel month is final immediately).
2. **True income and wealth base:** `draw_income` also returns `true_income` (the value before
   hiding; no new draws). `_new_clients` adds `wealth_base` = subsegment median income ×
   exp(`income.wealth_loading` × wealth deviation) (spec "Hidden client attributes").
3. **Hidden attributes:** `amounts.draw_hidden_attributes(spec, clients, age, rng) -> pd.DataFrame` with
   the columns of §2.3 (values: spec "Amounts" → current/savings, subcategories, credit card, time
   effects). Stage B adds the rest of `amounts`.
4. **`separation`** in `RETAIL` (default 1.0): `latent_means` uses
   `centre + separation × (subsegment mean − centre)`, `centre` = share-weighted mean of the
   subsegment means. At 1.0 nothing changes.
5. **Products** (`products.py`, spec "Product rates"):
   - `cc`: traits add `digital: 0.3`;
   - `loan_personal`: `effects` adds `nationality: {"Ghana": 1.5}`;
   - `HOLDING_RULES["bonus_trigger"] = {"products": ["td", "wealth_digital", "wealth_trad"],
     "odds": 2.0, "months_after": 2}`;
   - new usage chains, appended after `digital`, with two optional fields: `flag` (the mart or
     oracle column; default `<key>_active_flag`) and `in_mart` (default True):
     `cc_activity` (requires `cc`, shares 0.85/0.85/0.80/0.75, mean active 24, traits activity
     0.6, flag `cc_active_flag`); `casa_activity` (requires `casa`, shares 0.91/0.93/0.94/0.96,
     mean active 180, traits activity 0.5, effects salary transfer +2.4, flag `casa_active_flag`);
     `cc_revolver` (requires `cc`, shares 0.10/0.20/0.30/0.45, mean active 24, traits credit 0.5,
     wealth −0.3, flag `revolver_flag`, `in_mart=False` → oracle).
6. **Time terms in the score:** `product_score(spec, key, clients, z, age, month=None)`; with a
   month it adds `seasons.wake_shift(spec, key, clients, month)` (FX summer, digital drift) and
   `seasons.after_bonus(spec, key, clients, month)` (log 2 in the 2 months after the client's bonus
   month, for the trigger's products). `calibrate` calls it without a month (spec maths §3).
   `step_holdings` and `start_holdings` pass the month. Put the drift and FX-wake tables in
   `levels.SEASONS` now (Stage B fills the rest).
7. **Chains that require a static product** (`casa`): no leaving chance (`keep = 1`) and no
   `_gained` state. Flags from the spec's `flag` name; `in_mart=False` chains go to the oracle.
8. **Mart flags as 0/1 `int32`** at month assembly. `check_table.flags_as_bool(df) -> pd.DataFrame`
   converts every `*_flag` column to bool; `build_panel` and the population checks call it. Adapt
   `holding_events` and the step-2 checks to the `flag` names and to oracle-only chains (the panel
   joins mart and oracle, so `revolver_flag` is there).
9. **Writer and truth (basic):** `output.write_mart`, `read_output`, `load_truth` (§2.5) and
   `truth.build_truth(sim) -> dict` (what `generate_mart` builds today, JSON-safe; versions of numpy,
   scipy, pandas, pyarrow). Oracle columns `true_income` and `wealth_base`.
10. **Slow suite** (§2.6): fixtures, markers; the step-1/2 tests become a fast rules test on
    `unit_output` and a slow full test on `canonical_output`. `check_suite.run_checks`.

**Done when:** fast and slow suites green; steps 1–2 rows all pass at 100k (shares of the new chains
included); 20 vs 24 months give identical months 1–20 (a quick in-memory test on `unit`); the
mart's description columns are unchanged vs `2e50bc4` for the same seed (population and latents
streams untouched).

### Stage B — amounts (spec "Amounts", maths §4–§6)
**Goal:** every current-month amount column of the spec's column list, with the hidden oracle
columns. Public functions (helpers free, within the size rules):
```python
# variation.py
def draw_effects(rng, n: int, sds: np.ndarray) -> np.ndarray            # (n, m) persistent N(0, sd²)
def start_noise(rng, n: int, sds: np.ndarray) -> np.ndarray             # stationary AR(1) start
def step_noise(noise: np.ndarray, rho: np.ndarray, sds: np.ndarray, rng) -> np.ndarray
def draw_multipliers(rng, n: int, tails: np.ndarray) -> np.ndarray     # Pareto(x_m=1, a)
def median_offset(sd: np.ndarray, rate: np.ndarray) -> np.ndarray      # log median, exponnorm
def draw_counts(rng, mean: np.ndarray, active: np.ndarray) -> np.ndarray
def draw_shares(rng, mean_shares: np.ndarray, concentration: float) -> np.ndarray  # zero stays 0
def split_amount(total: np.ndarray, shares: np.ndarray) -> np.ndarray   # rounded parts; sum exact
# balances.py
def casa_balance(...)   def deposit_balance(...)   def wealth_balance(...)
def loan_amounts(spec, key, remaining, principal, ...) -> tuple[np.ndarray, np.ndarray]
# flows.py
def account_flows(...) -> dict[str, np.ndarray]   # inflow/outflow parts, counts, booking
def fx_amounts(...) -> tuple[np.ndarray, np.ndarray]
# cards.py
def draw_limits(spec, clients, credit_dev, rng) -> np.ndarray
def wanted_spend(spec, ..., month, rng) -> tuple[np.ndarray, np.ndarray]   # total, (…, 4) parts
def step_card(prev_balance, limit, revolver, held, held_before, active, wanted, repay_share) -> dict
# logins.py
def draw_logins(spec, clients, digital_dev, age, active, month, rng) -> tuple[np.ndarray, np.ndarray]
def step_days_since_login(prev_days, mobile, online, active, days_in_month, rng) -> np.ndarray
# seasons.py (Stage B part)
def season_factor(spec, measure: str, profiles: np.ndarray, month) -> np.ndarray
def travel_chance(spec, profiles, crossborder_dev, month) -> np.ndarray
def school_fee_due(spec, clients, month) -> np.ndarray
def bonus_due(spec, clients, month) -> np.ndarray
def login_drift(spec, month) -> float
# amounts.py
def start_amounts(spec, clients, z, means, holdings, month, rngs) -> dict[str, np.ndarray]
def step_amounts(spec, state, clients, z, means, holdings, month, rngs
                 ) -> tuple[dict, dict[str, np.ndarray], dict[str, np.ndarray]]  # state, mart, oracle
```
Details and pitfalls:
- **Median offset:** `scipy.stats.exponnorm.median(K=1/(sd·rate), loc=0, scale=sd)`; with no
  power-law part the offset is 0. Stocks: `sd² = λ²σ²_{d,profile} + e² + s²`. Flows: add
  `φ² sd²_casa` to the normal part, use `rate = a_casa / φ`, subtract `φ · c_casa` (spec maths §4).
  Verified numerically on 2026-10-16 (empirical median 0.4631 vs `exponnorm` 0.4616 at 2M draws).
- **`D`** (the current/savings random part) comes from the balance path whether or not the account
  is dormant (the observed balance freezes, the path doesn't).
- **Booking:** compute the change in the observed monthly average balance (first row: from 0;
  starting book's first simulated month: from the initial balance), then book the gap; inflow −
  outflow equals it after rounding (rounded parts, totals as sums).
- **Card step** must accept arrays of any matching shape (the regression oracle calls it with
  `(n, paths)`); no `pd` objects inside. Order inside a month: limit (new cards), wanted spend,
  carried / interest / cap / spend, repayment, balance, utilisation. A card given up this month:
  repayment = last balance, then everything 0. A new card: no balance carried.
- **Loans:** principal drawn when a slot opens (`remaining == term` after the holdings step) and for
  the starting book's slots; outstanding after `j = term − remaining` instalments; the instalment
  is paid by slots that were open at the end of last month (including one maturing this month).
- **Term deposit:** balance at adoption and each 12th month held; starting holders get a uniform
  phase (0–11).
- **Wealth:** the market index is 1 in the month the starting book is drawn; its monthly log
  return is drawn from the amounts stream once per month.
- **Logins:** active ⇒ at least one login; `days_since_last_login` NaN until the first login;
  starting-book registered-but-dormant clients start at a uniform 30–720 days.
- **New-client ramp** applies to the observed current/savings balance only.
- **Seasonal months** from `np.datetime64` month `m`: month of year = `m.astype(int) % 12 + 1`.
- **Mart values** this stage adds (spec "Columns", current-month groups); **oracle** adds
  `remitter_flag`, `school_payer_flag`, `bonus_month`, `pareto_casa`, `pareto_td`,
  `pareto_wealth_digital`, `pareto_wealth_trad` (and `revolver_flag` from Stage A).
- Amounts are never negative; round to 0.01 at the end of each computation.

**Done when:** the step-3 check families pass (fast and slow), steps 1–2 still pass, canonical
generation ≤ ~5 min.

### Stage C — mart (spec "Feature mart")
```python
# names.py
MEASURES, KINDS, SUBCATS, AGGS                                  # vocabularies (tuples)
def state_name(product: str, kind: str) -> str
def activity_name(measure: str, product: str, kind: str, subcat: str | None = None) -> str
def rollup_name(base: str, first: int, last: int, agg: str) -> str
def recency_name(base: str) -> str
def ratio_name(base: str) -> str
def trap_name(name: str, kind: str) -> str
def parse_column(name: str, products: list[str]) -> dict      # raises ValueError if it doesn't parse;
#   `products` = list(spec["products"]) incl. chain keys; must also accept description, trap and extra names
# mart.py
ROLLUPS: list[tuple[str, tuple[str, ...], tuple[str, ...]]]   # (base, windows, aggs), from the spec
RECENCY: list[str];  RATIOS: list[str]
def start_history(bases: list[str], n: int) -> dict[str, np.ndarray]
def advance_history(history, values: dict[str, np.ndarray]) -> dict   # after _keep_and_append
def rollup_columns(history, months_on_book: np.ndarray) -> dict[str, np.ndarray]
def recency_columns(last_nonzero, values, month_index) -> tuple[dict, dict]
def ratio_columns(history, months_on_book) -> dict[str, np.ndarray]
def arrow_schema(columns: list[str]) -> pa.Schema
```
Details: rollup null iff `months_on_book < window length` (`months_on_book` = 1 in the join month,
so a `_0_2_` rollup is non-null from the 3rd month on the book — the checks use exactly this); utilisation's rollups average non-null
months (null if none); `std` is the sample standard deviation (ddof 1, as Spark's `stddev`); `nz`
counts non-zero, non-null months; ratio null if the 3–5 average is 0 or tenure < 6; nullable
counters (maturity months, recency, days since login, `nz` rollups) and the upstream target are
`Int64` in memory, statuses may be `category`; recency counts
back from the current month (0 = active now), null if no non-zero month since the later of
relationship start and the start of the simulation. Column order as the spec's table; a committed
snapshot `tests/data/synthetic_mart_columns.txt` (one name per line).
Tests: names parse; column snapshot; null rule; types (Spark reads `int` flags, `decimal(18,2)`
`cc_limit`, `date` partition); **Spark recompute** of every rollup, recency and ratio on
`unit_output` with window functions (explicit month counts; `stddev_samp`); **prefix stability**
(unit, 20 vs 24 months, every mart and oracle column equal in months 1–20 except the declared leak
columns, which exist from Stage D).

### Stage D — traps (spec "Trap summary")
- `presets.TRAPS`: plain data, one entry per trap of the summary (product, target, column, kind,
  parameters, expected behaviour), read by `traps` and copied into `truth.json`.
- `traps.py`:
  - `start_trap_state(spec, clients, rng) -> dict` (persistent per client: premium level, language);
  - `trap_columns(spec, state, n, rng) -> dict` (null controls, quality; per month);
  - `finalize_leaks(spec, frames: list[tuple[pd.DataFrame, pd.DataFrame]], rng) -> pd.DataFrame`:
    adds the leak, upstream-target and process-leak columns to the oldest buffered month from its
    own and the next up-to-3 months (mart and oracle rows joined by `client_id`); draws are
    `n`-sized for that month regardless of outcomes;
  - `extra_columns(n_extra, z, means, rng) -> dict`;
  - `trap_summary(spec) -> pd.DataFrame` (the spec table from `TRAPS`, for truth and the notebook).
- `dirty.py`: `apply_dirty(spec, mart, rng) -> tuple[pd.DataFrame, dict]` (the defects and their
  record for `truth["dirty"]`); `generate_mart(dirty=True)` / `write_mart(dirty=True)` only.
- `generate`: the 3-month look-ahead buffer; `finish_simulation` flushes with truncated windows.
- Prefix stability now excludes exactly the three look-ahead columns.

### Stage E — oracle and truth (spec "Ground truth and oracle")
```python
# oracle.py
STANDARD_TARGETS: dict[str, dict]     # name → kind (acquire/open/activate/regression), product, eligibility
def realised_target(mart: pd.DataFrame, target: str, w: int) -> pd.Series
def window_probability(mart, oracle, truth: dict, target: str, w: int) -> pd.Series
def oracle_metrics(mart, oracle, truth) -> dict          # AUCs pooled / per segment, events, sizing
def relevance_ranking(mart, oracle, truth, target: str, sample: np.ndarray) -> pd.DataFrame
# regression.py
def simulate_card_spend(spec, sim: dict, month, rng, n_paths: int = 200) -> dict[str, np.ndarray]
```
- **`window_probability`** (D-066, spec): pivot `score_<product>` to a clients × months array;
  for eligible rows at `t`, `p̃_s` from the profile intercept (truth calibration) + `score_s` +
  `log 2 · churned_t` (status products); onboarding by tenure (`months_on_book_s ≤ 3`, chance
  `1 − (1 − π_s)^(1/3)`, `π_s = p_s / (p_s + q)`); loans: `p_s` × [a slot free at `s` under the
  schedule at `t`] × [no maturity at `s`] from `<loan>_remaining_1..4` at `t`; chains: wake chance,
  the steady share `w/(w + lapse)` at `t+1` if the required product was gained at `t`. Null where
  the target is null (not eligible, leaves before `t+w`, past the panel). Then `1 − ∏(1 − p̃_s)`.
- Oracle columns added: `score_<product>` for every non-static product = the log-odds of adoption,
  opening or wake-up without the intercept and the state terms, **calendar terms included**
  (`product_score + time_terms`, exactly what `step_holdings` adds to the intercept);
  `lapse_<chain>` for every usage chain = its monthly lapse chance before compounding (needed for
  the steady share of a fresh registrant at `t+1`); `<loan>_remaining_1..4` (months left per slot
  at the end of the month, 0 = empty).
- **Regression oracle:** for card holders at `t`, simulate months `t+1..t+3` × 200 paths from the
  true state (traits AR step with each client's chol factor, card holding/onboarding/re-adoption,
  card activity, revolver, current/savings noise for `D`, spend noise, travel months and shares,
  seasonality, the card step); output mean and quantiles (`np.quantile`, linear). Process clients in
  chunks of ~5,000 to bound memory. Reuse the generator's functions; never re-implement the card
  step.
- **`truth.json`** completes: schema (`truth.column_schema`), metrics per standard target and `w` ∈
  {1, 3, 6}, relevance (w = 3; rank correlation per month on a seeded 20% client sample, median
  over months; η for categoricals), traps, drift, market index, dirty record. `write_mart` computes
  metrics after writing every month, reading back only the columns needed (≈ 50).
- **`truth` key layout** (the contract the checks read; keys are strings):
  - `truth["columns"]`: list of `{name, type, kind, mechanism}` for every mart column;
  - `truth["traps"]`: list of trap records, each with `column` (null for organic traps without one),
    `product`, `target`, `kind`, `parameters`, `expected`;
  - `truth["dirty"]`: the dirty-switch record (only when on);
  - `truth["market_index"]`: `"YYYY-MM"` → index value (Stage B);
  - `truth["oracle"]["targets"][target]["w1" | "w3" | "w6"]`: `{auc, auc_by_segment, events_per_month,
    expected_positives_6m, low_confidence}`;
  - `truth["oracle"]["relevance"][target]`: list of `{column, score}` sorted by score, most relevant
    first (w = 3).
  - required top-level keys: `generator_version, versions, seed, preset, n_clients, n_months,
    first_month, spec, calibration, turnover, market_index, columns, traps, drift, null_rule,
    oracle` (+ `dirty` when on);
  - **AUC definition** (the checks recompute it and must match within 1e-9): Mann–Whitney AUC (ties
    count ½) of `window_probability` against the realised target over every mart row where both
    are non-null, all months pooled; `auc_by_segment` the same within each `segment`, null where a
    class is empty.
- **Relevance for categoricals:** η is biased upward with many levels (≈ √((k−1)/n)); use a
  held-out η (level means fitted on one half of the clients, scored on the other), or the null
  control `preferred_language_trap_null_control` can leave the bottom 10%.
- **Regression oracle observation months** for the checks: panel months 2, 3, 9, 14, 15, 21 (2 and
  14 are Novembers, so a December inside the window is tested).

### Stage F — output, CLI, notebook, review guide (spec "Physical form", "Presets and budgets")
- `__main__.py`: argparse (`--preset`, `--n-clients`, `--seed`, `--n-months`, `--out`, `--dirty`,
  `--extra-columns`); prints rows, columns, timings.
- `conf/base/sources.example.yml`: `retail_mart: {format: parquet, path: data/01_raw/synthetic_canonical/mart}`.
- `core_modelling/environment.py`: private `_load_sources(path: str) -> dict` (pyyaml) and
  `_read_source(spark, source: dict) -> DataFrame` (parquet by path, or a table by name). M2
  redesigns them; keep them minimal and private.
- Tests: read `unit_output` through a temporary mapping; Spark types (`int` flags, `decimal(18,2)`,
  `date`); CLI smoke (`unit`, `--n-months 3`); stale-data guard; **budgets** (slow): canonical
  ≤ 600 s and peak ≤ 3 GB from the `canonical_output` subprocess timing.
- Generate the canonical dataset into `data/01_raw/synthetic_canonical/` with the CLI.
- **Notebook** `notebooks/00_synthetic_data.ipynb`, rebuilt from a scratch generator script (not
  committed): reads `data/01_raw/synthetic_canonical/` (path derived from the package location,
  never the cwd) and calls `load_truth` first. Sections: 0 setup and versions; 1 every check family
  (pass counts, then the failing rows if any); 2 population; 3 holdings and chains; 4 amounts
  (levels by subsegment, tails, persistence, current/savings booking, card mechanics, loans,
  deposits, wealth with the market index, subcategories, remittance, FX, logins); 5 time effects
  per profile (summer, December, school fees, bonuses, drift); 6 segment overlap and pooled vs
  within; 7 mart columns (list, nulls, types, rollup example for one client); 8 traps (the summary
  table, then the evidence for each); 9 oracle (AUC table, calibration per decile, regression
  coverage, relevance top and bottom); 10 a few client trajectories and the hidden traits. Inline
  pandas and plotly only, aggregates only (keep the file small); committed with outputs.
- **`synthetic/REVIEW.md`** (§6).

## 4. Checks (independent agents)
### 4.1 Independence rules
- Write checks from the spec (`test_harness.md`) and §4.2 only. **Don't read the generator's
  mechanism modules** (`hazards`, `holdings`, `variation`, `balances`, `flows`, `cards`, `logins`,
  `amounts`, `mart`, `traps`, `regression`); read only the spec modules (`presets`, `products`,
  `levels`) through `truth["spec"]`, `check_table.py`, an existing checks module for style, and
  `oracle.window_probability` (the API under test in `checks_oracle`).
- Expected values are restated from the spec (formulas applied to the data and the oracle's hidden
  columns), never computed by calling generator functions.
- Rows: `row`, `share_row`, `violations_row` and the new helpers in `check_table`. Analytical
  standard errors on one row per client (pick one month, or one pair of consecutive months);
  ranges checked as ranges; 4.5 × seed spread only where §4.2 says so.
- Each module ≤ ~300 lines; one public `check_<family>` per module; `MART_COLUMNS` and
  `ORACLE_COLUMNS` declared.
- Report: the rows (names, strata, expected, tolerance) and which deliberately broken generators
  should trip which rows (§4.3).

### 4.2 Rows per family
**Stage A (adapt):** step-1/2 checks unchanged in substance; shares and at-risk rules extend to the
new chains automatically through the spec; add: `casa_active_flag` = 1 ⇒ `casa_flag` = 1;
`cc_active_flag` = 1 ⇒ `cc_flag` = 1; dormant share by salary transfer (≈ 1% with, ≈ 10% without:
ranges 0.5–2.5% and 7–13%); revolver share at month 1 per profile vs the spec (share rows on the
oracle's `revolver_flag` among holders); the flat-share check leaves out `digital`, which trends
by design (drift), and gets a row of its own: the digital active share rises over the panel.

**`checks_amount_rules` (all tolerance 0):**
- non-holders (card not held now nor last month): `cc_limit`, `cc_bal`, spend columns,
  `repayment_cc_vol`, `interest_cc_vol` all 0; `cc_utilisation_ratio` null iff `cc_flag` 0;
  `cc_active_flag` 0;
- `cc_limit` ∈ the tiers when held; `0 ≤ cc_utilisation_ratio ≤ 1`; `interest_cc_vol ≤ 0.03 ×`
  last `cc_bal` (+0.01); `interest_cc_vol > 0` ⇒ `revolver_flag` = 1; `repayment_cc_vol ≥ 0.05 ×`
  last `cc_bal` − 0.01 when held both months; spend 0 when `cc_active_flag` 0;
- loans: `loan_<k>_bal` 0 iff `loan_<k>_cnt` 0; instalment 0 when the count is 0 now and last
  month; outstanding falls month on month while the count is unchanged;
- `td_bal` 0 iff not held, ≥ 10,000 when held, changes at most once in any 12 consecutive held
  months; `wealth_*_bal` 0 iff not held, > 0 when held;
- current/savings dormant (`casa_active_flag` 0): every inflow/outflow column and count 0,
  `casa_bal` equal to last month's;
- totals equal the sum of their subcategories (inflow, outflow, card spend) within 0.005;
- **booking identity:** `inflow_casa_vol − outflow_casa_vol = casa_bal − last casa_bal` within 0.02
  for active months (first row: last balance 0);
- salary 0 without salary transfer; salary = `true_income` outside the bonus month;
  salary / `true_income` ∈ [2, 3] in the bonus month for bonus clients;
- remittance 0 for UAE and GCC nationals and when `remitter_flag` 0; count > 0 iff amount > 0 for
  remittance, card spend, FX, outflow;
- `fx_vol > 0` iff `fx_active_flag` 1; logins > 0 iff `digital_active_flag` 1; logins 0 when
  `ebanking_flag` 0;
- `days_since_last_login_digital`: within [0, days in month) when active; previous + days in month
  when dormant with a previous value; null only if never logged in (null last month and no login
  now);
- every amount ≥ 0 and a multiple of 0.01; counts whole numbers.

**`checks_amount_levels`:**
- median of `amount / (multiple × base × adjustments)` = 1 per profile for `casa_bal` (active,
  tenure ≥ 3, March–May), `td_bal`, `wealth_*_bal` (÷ the market index from `truth`), `fx_vol`
  (active, March–May), card spend (transactors with utilisation < 0.5, March–May): tolerance on
  the log scale 4.5 × 1.2533 × sd / √n, one month per client;
- medians of `casa_bal` strictly ordered by subsegment (rule);
- lag-1 correlation of logs between two consecutive months, one pair per client: `casa_bal`
  (active both months) ≥ 0.9; `spend_cc_vol`, `fx_vol`, `inflow_casa_other_vol` (positive both
  months) in [0.6, 0.8];
- Hill estimate on the top 5% of `amount / (multiple × base × …)` among mass clients in one month:
  within ±30% of the tail index for `casa_bal`, `td_bal`, `wealth_trad_bal` (numerically checked on
  2026-10-16: the estimate lands within ≈ 5%);
- overlap: share of MM clients above the UM median `casa_bal` in [0.20, 0.30]; Upper Priority above
  the Lower Private median < 0.05;
- pooled rank correlation of `casa_bal` with `spend_cc_vol` (active card holders, one month) above
  the median within-subsegment value (rule); the gap shrinks at `separation` 0.5 (slow test at 30k);
- remitter share among non-nationals per profile vs 30/40/50/60% (share rows, oracle flag);
  remittance share of spending outflow higher in mass than private (rule); cash share falls with
  `z_digital` (negative rank correlation within mass, Fisher SE);
- new-client ramp: mean log(`casa_bal` month 1 / month 3) of new clients active in both = log 0.5
  − E[noise change] (≈ log 0.5; tolerance from the data's SE);
- logins per active month: ordered private < priority < affluent < mass (rule); mass / private
  ratio of means ≈ 16/7 × the trait adjustment (±15%, a range).

**`checks_seasons`:**
- mean log ratio July / June of `casa_bal` per profile (active both, tenure ≥ 3) = log of the dip
  factor (SE from the data);
- among travel months, card travel spend July–August vs March–May per profile ≈ the factor
  (transactors with utilisation < 0.5; ratio of means, SE from the data);
- share of card holders with travel spend > 0 in July–August vs March–May: ≈ 2 per profile, a
  range [1.6, 2.1] (the cap and the trait tilt bend it);
- December non-travel card spend vs November per profile ≈ the factor;
- school fees: payers' `outflow_casa_bills_vol` September vs August ratio ≫ non-payers' (rule:
  payers' mean jump ≥ 50% of the expected term fee; non-payers' ratio within SE of 1);
- FX: active share rises into July–August more for private than mass (rule on the sign);
- drift: mean `login_digital_mobile_cnt` among active users, month 16 / month 15 ≈ 1.3 (SE from the
  data); digital activation rate, last 6 months vs first 6, above 1 (rule).

**`checks_mart`:** every column parses; the column list equals the snapshot; flags only 0/1;
rollups null iff tenure < window (rule, per rollup); no other unexpected nulls (each nullable column
null only in its cases); utilisation rollups null iff no card month in the window or tenure short;
dtypes in memory.

**`target_windows` + `checks_traps`:** the checks' own realised targets for the standard targets
(spec table; D-066 events; null for leavers and past the panel). Rows:
- leak AUC vs the realised `cc_acquire` target (w = 3) = 0.97 ± 4.5 Hanley–McNeil SE; leak AUC >
  oracle AUC (rule);
- upstream target equals the realised target where both are non-null (rule); 0 where the realised
  target is null because the client left (rule); null exactly for holders and the last 3 months
  (rule);
- process leak: share of openings at `t+1` with an application at `t` = 0.8 (share row); declined
  share of applications = 0.3 (share row); AUC of applications vs `loan_personal_open` (w = 1) >
  oracle AUC (rule);
- rare level: monthly opening rate for Ghana / the rest of the same profiles above 2 (rule) and
  consistent with the oracle's mean chances (ratio within SE);
- Simpson: within each subsegment, rank correlation of `login_digital_mobile_cnt_0_2_months_avg`
  with the oracle's `cc_acquire` probability (w = 3) among eligible rows > 0; pooled < 0 (rules);
- null controls: |AUC − 0.5| ≤ 4.5 SE for each binary standard target (w = 3) (categorical: AUC of
  its level rates estimated on one half of the clients, scored on the other);
- quality: near-constant share = 0.999 (share row); all-null 100% (rule);
- drift: PSI (10 quantile bins of the earlier months) of `login_digital_mobile_cnt` among active
  users, months 17–24 vs 4–15 > 0.25; months 10–15 vs 4–9 < 0.1;
- dirty switches (unit, `dirty=True`): each defect present as recorded; extra columns: weak ones'
  rank correlation with the hidden traits in [0.1, 0.3], noise ones within 4.5 SE of 0.

**`checks_oracle`:** for every binary standard target with `w` = 3: realised rate vs mean
`window_probability` per decile (binomial SE) and overall; for `w` = 1 and 6 overall only; the AUC
the checks compute equals `truth`'s within 1e-9 (two independent realised-target implementations);
the leaks beat the oracle; regression: on observation months 3, 9, 15, 21 (non-overlapping
windows), P(realised ≤ q50) ≈ 0.5, P(realised < q10) ≤ 0.1 + tol, P(realised ≤ q90) ≥ 0.9 − tol,
realised / predicted mean per decile ≈ 1 (SE from the data); `truth.json` schema: required keys,
every mart column in the schema, every trap column in the summary, AUCs within [0.5, 1]; relevance:
null controls in the bottom 10% for every target.

### 4.3 Mutation tests (the integrator runs them; each must trip its intended rows)
| Family | Deliberately broken generator → rows that must fail |
|---|---|
| A | revolver share × 1.5 → revolver shares; casa dormancy ignores salary transfer → dormant shares |
| amount rules | booking skipped for one subcategory → identity; card cap ignored → utilisation ≤ 1; spend while dormant → dormant card rule; td redrawn monthly → 12-month rule |
| amount levels | casa multiple × 1.3 → medians; AR ρ 0.95 for flows → lag-1 band; Pareto removed → Hill; ramp off → ramp row |
| seasons | summer dip removed → July/June rows; school fees in October → September jump; relaunch factor 1.0 → drift row |
| mart | rollup window shifted by a month → Spark recompute; null rule ignored → null rows |
| traps | leak μ halved → leak AUC; upstream counts leavers as null → leaver rule; process-leak chance 0.5 → 0.8 share |
| oracle | window probability without frozen churned status → status-product deciles (churned stratum first); regression paths without seasonality → the summer and November-observation rows |

Run mutations at 30–50k clients where the canonical size is too slow; record each in the log.

## 5. Integration protocol (per stage)
1. Builder agent (general-purpose) implements the stage from this plan; reports (§1).
2. The integrator reads the diff, runs `ruff`, fast and slow suites, and fixes small issues.
3. In parallel: the stage's independent checks agent (§4); the code-reviewer agent (simplicity
   included) on the stage's files; from Stage C the ml-correctness-auditor; silent-failure-hunter
   on `output`.
4. The integrator fixes or justifies every finding, runs the mutation tests (§4.3), updates the
   State table and `worknotes/log.md`, and commits to main (no push).
5. The next builder may start once the previous stage's code is committed; checks and reviews of
   stage N run alongside the builder of stage N+1 when they touch different files.

## 6. Final review package
- **`synthetic/REVIEW.md`** (written for the SDS; the LDS gets a summary later):
  1. what was built, in five lines, and the commits;
  2. how to regenerate (`python -m synthetic …`, ~N minutes) and run the checks (`pytest`,
     `pytest -m slow`, timings);
  3. **the review, in order**, each with "what right looks like": the notebook sections 1–10;
     then spec sections (Amounts, Columns, Trap summary, Ground truth); then code entry points
     (`generate.advance_simulation`, `amounts.step_amounts`, `cards.step_card`,
     `oracle.window_probability`);
  4. the trap summary (link) and the standard targets with their oracle AUCs;
  5. deviations from the spec, known limitations, anything unverified;
  6. decisions to confirm.
- After the SDS says OK: a short summary for the LDS in `worknotes/sync.md` (review item + "since
  the last sync"), then the M1 status in `docs/UPDATES.md` and `docs/roadmap.md`.

## 7. Gotchas
- Integer flags with `~` (see §1); pandas boolean masks need bools.
- `rng.gamma(0)` returns 0: zero mean shares stay exactly 0 in `draw_shares`.
- pyarrow can't cast NaN to decimal: `cc_limit` is 0 without a card, never NaN.
- Spark infers the `snapshot_month` partition as a date only from `YYYY-MM-DD` folder names; never
  write nanosecond timestamps (T18).
- The oracle's row `t` is the chance of the move into `t` (state at the end of `t − 1`); window
  probabilities freeze the state at `t` (D-066). Leak columns are the only look-ahead.
- Holdings calibrate on the starting book without time terms; shares then wobble slightly with the
  season (the bonus trigger, FX summer, digital drift): the flat-share checks exclude `digital`
  (it trends) and accept the season.
- The starting book has no history before the simulation starts: recency is null until a first
  non-zero month inside the simulation.
- Memory: the canonical oracle has ~65 columns; read subsets. `checks_mart` reads every mart
  column: run it on the unit output, and at canonical size on a client sample (filter rows when
  reading, e.g. `client_id % 5 == 0`), never on the whole mart.
- Test functions need docstrings and type hints too (`tests/test_code_rules.py`).
