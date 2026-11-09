# To do: a trap and a control column for every Feature Checks finding (synthetic data)
_Written 2026-11-09 for the SDS's synthetic-data extension (Q545: "there must be trap and check
columns for every single test"). Covered today: 13 of the 20 findings have a dedicated trap, almost
none a dedicated control. Delete this note once the extension is in and `tests/test_traps.py` maps
every row._

**What each finding needs.** A **trap** that must raise it on its config, and a **control**: a
column close to the threshold that must not, so a rule that over-fires fails too. The null
controls (`*_trap_null_control`: pure noise, never flagged) cover "noise raises nothing" only;
they sit below 0.55, so they never reach the checks gated on signal.

**How the test would read controls (a proposal).** One more truth row kind, e.g. `control`, with
the finding it must not raise (`must_not_raise: leakage.too_strong`), asserted like `TRAP_FINDINGS`
the other way round; `test_every_trap_row_is_mapped_or_listed` then covers controls too. Trap
kinds live in `synthetic/mechanisms/traps.py` `TRAP_KINDS`; the mapping in `tests/test_traps.py`.

**Rules this round changes, which the new columns should exercise.** `rare_value_leak` on Cohen's
h (binary) or d (regression) at 0.8 (Q539); no check skips for low support, each detail stating
support and significance (Q540); `too_strong` on the higher of the plain and the best-order window
concordance (Q541); a shared null set named in the note (Q543); `concordance_unstable`'s range
relative to the signal and the leaf `leakage.dominant_share_min` (Q544).

## Per finding (trap must fire · control must not)
- **quality**
  - `all_null` · trap ✓ (`all_null`) · control: implicit (`low_fill` raises `high_missing`).
  - `constant` · trap ✓ (`constant`, `eligibility_defining`) · control **missing**: one value
    plus nulls (null counts as a value, so not constant).
  - `high_missing` · trap ✓ (`low_fill`) · control **missing**: about 90% null (below 0.95).
  - `near_constant` · trap ✓ · control **missing**: about 98% one value (below 0.99).
  - `high_cardinality` · trap ✓ (300-level code) · control: implicit (categoricals under 50
    levels); `nationality` (64 meaningful levels) fires by design.
  - `nulls_may_be_zeros` (note) · trap **missing**: a numeric about 30% null and never 0, where
    null means 0 · control **missing**: the same with zeros among its values.
  - `nulls_informative` (note) · trap: natural (the roll-ups' new-client null sets, Q543) · control
    **missing**: random nulls (about 20%, unrelated to anything).
- **leakage**
  - `too_strong` · traps ✓ (`leak`, `upstream_target`) · **missing**: a U-shaped leak whose plain
    concordance is below 0.80 and its best order above (Q541) · control **missing**: an honest
    feature near 0.75.
  - `missingness_leak` · trap ✓ (`missing_leak`, the offer code) · **missing**: a field blanked
    on conversion at a null share below 0.5% (read below EDA's range) · control: implicit (the
    roll-ups' null sets at about 0.58).
  - `rare_value_leak` · trap ✓ (`process_leak`, card) · **missing**: a categorical post-outcome
    code on the card target (Q533), and a regression trap for Cohen's d (the test-only regression
    variant) · controls: natural (`segment` h 0.64, the travel-spend roll-ups 0.43–0.48: must
    not fire at 0.8) · **missing**: a minority with few events (Q540: may fire, its detail
    "not significant").
- **time_alignment**
  - `lagged_signal_drop` · trap ✓ (`shifted`) · **missing**: a flip (lagged value orders clients
    the other way, R54) · control **missing**: a fast-moving honest feature that keeps about 60%
    of its signal.
  - `client_constant` · trap ✓ (`lookahead`) · controls: natural (`income`,
    `onboarding_channel`, `subsegment` fire by design: a person keeps them) · **missing**: a
    constant non-predictive attribute (below the 0.6 gate: must not fire).
- **stability**
  - `concordance_unstable` · trap **missing** (planned as `unstable` for M4): a weak feature whose
    signal swings by about its own size across the window · control **missing**: a strong feature
    with the same absolute swing (Q544: must not fire).
  - `psi_window_large` · trap **missing**: a feature whose distribution moves by PSI ≥ 0.25 inside
    the window (one legitimate ratio fires by accident at 0.26) · control: the note below.
  - `psi_window` (note) · trap **missing**: a 0.10–0.25 move inside the window.
  - `psi_latest_large` · trap ✓ (`drift`: the login roll-ups) · control: the raw login column
    (0.22–0.25: a note, borderline; a clear 0.15 would be safer).
  - `psi_latest` (note) · trap: borderline only (the raw login column) · **missing**: a clear
    0.10–0.25 move into the latest period.
  - `new_levels` (note) · trap **missing**: a categorical with a new code on at least 1% of the
    latest period's rows · control **missing**: a new code below 1%.
- **redundancy**
  - `correlated_pair` · trap ✓ (`redundant`) · control: implicit (related numerics below 0.90).
  - `associated_pair` · trap ✓ (`collinearity`) · control: implicit.

## The count-free guard (Q545 (B), in the test now)
No column the truth marks legitimate raises `too_strong`, `missingness_leak` or
`lagged_signal_drop` on the `dev` card config. The controls above make this per finding.
