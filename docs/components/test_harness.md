# Synthetic data and test harness
**Status:** designing · **Legacy:** `tests/smoke_test.py` (stub-based — do not copy its stubs)
**Related:** [dataset](dataset.md) (time model) · [target factory](target_factory.md) · [EDA](eda.md) ·
[feature checks](feature_checks.md) · [environment](environment.md) · `tests/README.md` · D-014, D-041 · OD-16

## Purpose
Real data never leaves the bank, so everything outside it runs on a synthetic multi-month client
panel with **known ground truth**, through **real** local PySpark. In the crunch, stubs hid every
environment bug (T15).

This is not just a test fixture. The synthetic dataset **drives development**:
- It is generated once, kept in `data/01_raw/`, and read by every stage, notebook and demo exactly as
  real data will be read. On a laptop, `conf/local/` maps the logical source to it.
- Its outputs (EDA, checks, models, monitoring) are how changes get judged, not just whether code
  runs.
- It must make EDA, Feature Checks and the leakage screens *verifiably sensible*: heavily skewed
  targets, correlated heavy-tailed distributions, clear segments, planted traps.
- 24 consistent months support everything downstream: observation windows, client-grouped splits,
  OOT validation, calibration, inference, and monitoring with matured labels ([dataset](dataset.md)
  time model).

## Phase 2 requirements
1. Produce a **raw monthly panel**: one row per client per month, with holdings, balances, activity,
   demographics and categoricals. **No targets.** Target Factory derives them exactly as it will on
   real data, so that stage gets tested too.
2. **Canonical size:** ~100k clients × 24 months (≈ 2.4M rows), plus a small fast preset for unit
   tests. Backward windows ≤ 6 months, so a 24-month history leaves room for window + validation +
   inference + label maturation.
3. **Segmented population.** Within each segment, latent client traits are correlated. The structure
   differs by segment, so pooled and within-segment relationships diverge.
4. **Heavy-tailed features** with tunable power-law tails. They are rank-correlated through shared
   latents and coherent with each other: no zero-balance client transacts millions.
5. **Sticky holdings and usage (stationary and persistent).** A client either has a product or not,
   and switching is rare. Usage moves between active and dormant in long spells, never flickering
   month to month. Particular attention goes to the zero ↔ non-zero transitions, because one
   product's usage feeds other models.
6. **Exact zeros:** non-holders and dormant users have exactly 0 activity, so product usage is
   derivable.
7. **Rare categorical levels** (Zipf frequencies).
8. **Time consistency:** persistent client traits, client entry and exit, seasonality, optional drift.
9. **Rare to semi-rare transition events** (adoption, activation, reactivation), each with a
   controllable rate per product.
10. **Planted traps,** each switchable on or off and recorded in the ground truth.
11. **Deterministic from a seed.** Function arguments plus named presets.
12. **A ground-truth JSON sidecar** that tests and demos assert against.

## Design constraints
- **A top-level `synthetic/` package**, dev-only and not part of `core_modelling` (D-041). It has its own
  modules from the start: latents, holdings & usage, balances & flows, demographics & categoricals,
  traps, ground truth, presets, writing. It is installed as its own editable dev package so tests and
  notebooks can import it. Whether it travels in the release zip is decided with OD-04; real data
  does the testing inside the bank.
- **Libraries:** numpy, pandas, scipy (`scipy.stats`, `scipy.special`, `scipy.optimize`), and any other
  devcontainer library that helps (D-042).
- One `numpy.random.Generator` (PCG64) is created from the seed and passed explicitly. No global random
  state. The draw order is fixed, so output is identical for a given seed and the pinned numpy version
  on both dev machines.
- Vectorised over clients; the only loop is over months.
- **All column names come from one naming map** (`COLUMN_NAMES`). The defaults are placeholders;
  banking-like names come later, and renaming must be a one-place change.
- Products are generic: `K` products, each with two flags, `has_balance` (a stock) and `has_activity`
  (flows). Concrete products, rates and archetypes come later (OD-16); the maths must support any of
  them.

---

## The maths

Notation: client `i`, month `t = 1..T`, segment `s`, product `k`, latent dimension `d = 1..D`
(default `D = 4`, e.g. wealth, activity, digital, credit appetite — names are only for
readability). `σ(x)` is the logistic function.

### 1. Segments and latent client traits
```
s_i ~ Categorical(π)                                   segment mix
z_i ~ N(μ_s, Σ_s),   Σ_s = D_s R_s D_s,   L_s = chol(Σ_s)
```
- Each segment has its own mean `μ_s`, scales `D_s` and **correlation matrix `R_s`**.
- A `separation` knob scales the distances between the `μ_s`. It controls how much pooled AUC
  inflates relative to within-segment AUC.

### 2. Persistence over time (stationary AR(1) per segment)
```
z_i,t = μ_s + ρ (z_i,t−1 − μ_s) + sqrt(1 − ρ²) · L_s ε_i,t,     ε ~ N(0, I)
```
This keeps the stationary distribution exactly `N(μ_s, Σ_s)`. Use a scalar `ρ` (default ~0.95
monthly); a per-dimension `ρ` would break exact stationarity.

- **Segment migration** (optional, rare, monthly probability `m`): keep the client's standardised
  position, `z ← μ_new + L_new L_old⁻¹ (z − μ_old)`. This preserves stationarity in the new
  segment.
- **Entry and exit:** each month a client exits with probability `h_exit`. New clients enter to
  keep the population roughly constant. Entrants draw `z` from their segment's stationary
  distribution and start at tenure 0.
- **Burn-in:** simulate `B` months (default 12) before month 1 and discard them, so latents,
  holdings and balances start in steady state rather than at an arbitrary initialisation.

### 3. Product holdings (sticky Markov adoption / attrition)
For non-holders at `t−1`, adoption happens with probability:
```
p_i,k,t = σ(α_k + β_k·z_i,t + γ_k,s + c_k,cat(i) + season_t)
```
- **Holders** attrite with a small probability `q_k` (well under 1% a month). A holding therefore
  lasts `1/q_k` months on average — years, not months — and holding status never flickers.
- **The adoption events are the future targets.** Target Factory turns them into
  "adopted within the next `w` months".
- **Intercept calibration:** for a desired window adoption rate `r_w` among non-holders, the
  monthly rate is `r_m = 1 − (1 − r_w)^(1/w)`. Solve `α_k` by bisection (monotone) so that
  `mean(p)` over non-holders at the reference month equals `r_m`.
- Sizing rule recorded in the ground truth:
  `expected positives ≈ N_eligible · r_w`. Presets must keep this ≳ 200 for any rate under test,
  or flag it as low-confidence.

### 4. Balances (stocks) — lognormal body, power-law tail
For holders of a `has_balance` product:
```
log X_i,k,t = λ0_k + λ_k·z_i,t + η_i,k + ν_i,k,t
B_i,k,t     = X_i,k,t · W_i,k,       W_i,k ~ Pareto(x_m = 1, a_k)   (drawn once per client-product)
```
- `η` is a persistent client effect. `ν` is small monthly noise, which can itself be AR.
- By **Breiman's lemma**, the product of a lognormal and an independent Pareto has a regularly
  varying tail with index `a_k`: `P(B > x) ~ x^(−a_k)`. That gives a true power-law tail on top of
  a lognormal body. `W` is persistent, so balances don't jump month to month.
- **Non-holders:** balance is exactly 0, or null if `structural_nulls=True`.

### 5. Usage (flows): persistent active/dormant states, overdispersed counts, coherent amounts
Usage is a two-state chain per client and product. It applies to holders of a `has_activity` product,
and to every eligible client for usage-only products:
```
P(active_t = 1 | active_t−1 = 0) = σ(ψ0_k + ψ_k·z_i,t + season_t)     wake-up (rare)
P(active_t = 0 | active_t−1 = 1) = σ(ω0_k − ω_k·z_i,t)                 lapse (rare)
N_i,k,t      = active · (1 + Poisson(λ·G)),   G ~ Gamma(θ, 1/θ),   λ = exp(κ0_k + κ_k·z + season_t)
log T_i,k,t  = τ0_k + φ_k · log(1 + B_total,i,t) + τ_k·z + ξ,      ξ ~ N(0, s_ξ²)
amount       = N · T
```
- **Persistence:** active spells last `1/p_lapse` months on average and dormant spells `1/p_wake`;
  the stationary active share is `p_wake / (p_wake + p_lapse)`. Calibrate `ψ0_k` and `ω0_k` to a
  target active share and a target mean active spell (e.g. two years or more), so usage never
  flickers between zero and non-zero.
- **Zero ↔ non-zero events are explicit and recorded:** first activation (first-ever dormant →
  active), dormancy (active → dormant), reactivation (dormant for ≥ k months → active). Each can
  become a target.
- **Exact zeros:** `N = 0` and `amount = 0` for non-holders and dormant clients.
- Gamma–Poisson gives negative-binomial overdispersion.
- **Coherence:** the ticket size `T` scales with the client's own total balance through the
  elasticity `φ ∈ (0, 1)`, plus the wealth latent. Low-balance clients therefore have small
  tickets by construction.

### 6. Demographics and categoricals
- `tenure` counts months since entry. `age` is drawn per segment (truncated) and ages with time.
- **Categoricals** (e.g. region, channel) use Zipf frequencies, `P(level j) ∝ j^(−a_cat)`, with
  `J` levels, so there is a long tail of rare levels. Each level gets a small effect
  `c_j ~ N(0, s_cat²)` on adoption, so categoricals carry real signal.
- Optional MCAR missingness at a small rate on chosen demographic fields.

### 7. Seasonality and drift
- `season_t = A · sin(2π (month_of_year_t − φ_season) / 12)`, applied on the log / logit scale to
  activity and adoption.
- **Drift injection** (optional): from month `t0`, add `δ_drift` on the log scale to one feature's
  generator (or shift the segment mix). Ground truth records the feature, `t0` and size.

### 8. Planted traps (each toggleable)
| Trap | Construction | Expected behaviour |
|---|---|---|
| Leak | `L = μ_L · y_fwd + N(0, σ_L²)`, where `y_fwd` = adoption in `(t, t+w]` and `μ_L/σ_L = √2 · Φ⁻¹(AUC_target)` | Univariate AUC ≈ `AUC_target` (e.g. 0.97); the leakage screen flags it |
| Eligibility-defining | A column equal to (a function of) the current holding/activity of product `k` | Constant within that product's eligible (non-holder) population; flagged |
| Collinear cluster | `x_c,j = x + ε_j`, `Var(ε_j) = (ρ_c⁻² − 1)·Var(x)` on the log scale | Pairwise correlation ≈ `ρ_c`; VIF and the correlation views flag it |
| Drift | Section 7 | PSI > 0.25 after `t0`, ≈ 0 before |
| Rare high-rate level | A categorical level with frequency below `f_rare` and a large adoption effect `ω` | Stands out in event-rate-by-level; unstable in CV |
| Null controls | Independent features matching the marginals of real ones (a lognormal, a zero-inflated count, a Zipf categorical) | Univariate AUC ≈ 0.5; ranked at the bottom |

### 9. Ground truth (JSON sidecar)
The sidecar records:
- seed, preset, generator version
- the column schema: name, kind (`id`/`time`/`static`/`holding`/`stock`/`flow`/`categorical`/
  `trap`/`noise`), and its generating latents and parameters
- the segments (`π`, `μ`, `D`, `R`, `separation`), `ρ`, entry/exit rates, migration rate
- per product:
  - calibrated `α_k`, `β_k`, `γ_k`, attrition `q_k`, usage transition rates and mean spell lengths
  - the realised monthly adoption / activation / reactivation rates per month and segment
  - expected positives
- per product and event type, the **oracle relevance ranking**: Spearman correlation of every feature
  with the true hazard `p` at the reference month
- per product and event type, the **oracle AUC**: AUC of the true window probability `1 − ∏(1 − p)`
  against the realised events, pooled and within each segment
- traps: column names, type, parameters
- drift: feature, `t0`, size

**The oracle AUC is the ceiling.** A model or univariate screen that beats it is almost certainly
leaking — a cheap, strong invariant test.

## Interface (planned, package `synthetic`)
```python
COLUMN_NAMES: dict[str, str]              # one naming map; placeholder defaults
PRESETS: dict[str, dict]                  # "unit", "canonical"

def generate_panel(n_clients: int, n_months: int, seed: int = 0,
                   preset: str | None = None, traps: dict | None = None,
                   **params) -> tuple[pd.DataFrame, dict]:
    """Return (long raw panel, ground truth). Explicit params override preset values."""

def write_panel(panel: pd.DataFrame, truth: dict, out_dir: str) -> None:
    """Write panel parquet + truth.json (local paths only; e.g. data/01_raw/<name>/)."""
```
Spark conversion happens where the data is read (the environment adapter or a pytest fixture), not
in the generator. A dev-only notebook generates the canonical dataset and shows its ground truth.

## Presets (defaults)
Every preset is a full multi-month raw panel. No single-snapshot presets.

| Preset | Clients × months | Use |
|---|---|---|
| `unit` | ~5k × 24 (≈120k rows) | Unit tests and the end-to-end test; generates in seconds |
| `canonical` | ~100k × 24 (≈2.4M rows) | The shared development dataset: notebooks, demos, report reviews. Generated once into `data/01_raw/synthetic_canonical/` |

Columns: ~30–50 including traps and null controls. Runtimes are estimates until measured.

## Generator validation tests (the generator must prove itself first)
1. **Determinism:** same seed → identical frame (hash). Different seed → different frame.
2. **Stationarity:** at the last month, per-segment latent means and covariances are within
   tolerance of `μ_s`, `Σ_s`.
3. **Correlation:** within-segment Spearman correlations between heavy-tailed features have the
   configured sign and size. Pooled vs within-segment differ in the configured direction.
4. **Exact zeros:** activity is exactly 0 wherever the client doesn't hold the product or is dormant.
   Zero fractions are within tolerance of configuration.
4b. **Persistence:** month-to-month switch rates for holdings and usage match the calibrated
   transition rates; mean spell lengths are within tolerance; the share of clients who switch ≥ 3
   times in 12 months stays below a small threshold (no flicker).
5. **Tails:** a Hill estimator on the top 1% of balances recovers `a_k` (loose, ±30%).
6. **Coherence:** the ratio of amount to `1 + B_total` stays within configured quantile bounds
   (no millions on zero balance).
7. **Rates:** realised adoption / activation / reactivation rates are inside the binomial CI of the
   calibrated targets.
8. **Traps:** leak AUC ≈ target; null controls ≈ 0.5; rare-level frequency < `f_rare`; drift PSI
   above/below thresholds; eligibility-defining column constant within the eligible population.
9. **Oracle:** the oracle AUC is computed; for the planted leak, `AUC(leak) > oracle AUC`.

Framework tests then assert against the ground truth: screens flag every trap, the top oracle
drivers rank near the top, null controls rank near the bottom, and no model beats the oracle AUC.

## Suggested build order (one reviewed step each)
1. Package skeleton (`synthetic/`, own install), segments, latents, AR(1), migration, entry/exit,
   burn-in, plus tests 1–2.
2. Holdings and usage chains with intercept and transition calibration, plus tests 4b and 7.
3. Stocks (lognormal × Pareto) and flows (Gamma–Poisson counts + coherent tickets), plus tests 3–6.
4. Demographics, Zipf categoricals, seasonality, drift.
5. Traps and null controls, plus test 8.
6. Ground truth with oracle ranking and AUC, `write_panel`, plus test 9.
7. Pytest fixtures (session-scoped local SparkSession, `unit` panel); generate the `canonical`
   dataset into `data/01_raw/` and map it in `conf/local/`.

## Open questions
- Todo (OD-17): the ground truth must support comparing sampling options, i.e. per-row true
  probabilities, so bias and calibration of each option can be measured against the oracle,
  including for clients who convert after being negative in earlier months.
- Todo (window ablation): check that 24 months with ≤ 6-month backward windows leave room for a
  6-month window, a validation month and a second validation month, as in the
  [dataset](dataset.md) example.
- Product archetypes, ballpark transition rates, and whether to generate two entities with
  different product catalogues and schemas (OD-16; the builder will share rates when this is built).
- Column names: banking-like names to be specified later (`COLUMN_NAMES`).
- Derived targets for other task types (e.g. future amounts, next product, time to event): the raw
  panel already supports them through Target Factory. Confirm when the second task type is chosen
  (OD-15).
