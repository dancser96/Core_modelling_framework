"""Control checks: the five monthly control columns meet their spec rows.

`check_controls` builds one table for the columns drawn each month from that month alone: the
honest score and the score delivered every other month (noisy readings of the oracle's `score_cc`,
so their correlation with it follows from the spec's loading and noise, and neither beats the
oracle), the one-value column, the wait whose level steps up and the contact channel whose mix
shifts and later gains a level. Correlation and AUC rows use one row per client: the panel's middle
month and the month after it, one even and one odd calendar month (the scores' noise or delivery
follows the month's parity); AUCs are for card acquisition in 3 months, from
`events.realised_target`, among the non-holders whose target is known, and the oracle enters
through its window probabilities. Shares of values drawn row by row pool every row they cover;
the drift rows compare months around the spec's step dates, whatever window a config uses. Rules
use every row.
"""

import numpy as np
import pandas as pd

from synthetic.checks.events import KEYS, observation_month, realised_target, to_panel
from synthetic.checks.table import (
    Z_TOL,
    auc,
    categorical_psi,
    fisher_row,
    hanley_se,
    psi,
    range_row,
    row,
    share_row,
    side_row,
    trap_parameters,
    violations_row,
)
from synthetic.truth.oracle import window_probability

HONEST = "cc_propensity_score_trap_honest"
VENDOR = "cc_vendor_score_trap_unstable"
STATEMENT = "statement_format_trap_one_value"
WAIT = "support_wait_min_trap_drift_window"
CHANNEL = "contact_channel_trap_drift_moderate"
CONTROL_COLUMNS = [HONEST, VENDOR, STATEMENT, WAIT, CHANNEL]

# The columns' parameters (loadings, noise, shares, levels, step months) come from the spec rows
# (`trap_parameters`); what is set here is the checks' own: thresholds and the target's window.
SCORE = "score_cc"  # the oracle score both scores read, standardised over the month's clients
TARGET, WINDOW = "cc_acquire", 3
VENDOR_EVEN_AUC_MIN = 0.58
STEP_PSI_MIN, STABLE_PSI_MAX = 0.25, 0.1
CHANNEL_PSI_RANGE = (0.10, 0.25)

# What `oracle.window_probability` reads for cc_acquire: the profile, tenure and the card flag.
MART_COLUMNS = [*KEYS, "subsegment", "relationship_days", "cc_flag", *CONTROL_COLUMNS]
ORACLE_COLUMNS = [*KEYS, SCORE]


def check_controls(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Every monthly control column of the trap summary."""
    panel = to_panel(mart, oracle)
    month = pd.to_datetime(panel["snapshot_month"])
    first = observation_month(panel)
    parity = {_parity(m): m for m in (first, first + pd.DateOffset(months=1))}
    target = realised_target(panel, TARGET, WINDOW)
    chance = window_probability(panel[mart.columns], panel[oracle.columns], truth, TARGET, WINDOW)
    rows = (
        _check_honest(truth, panel, month, parity, target, chance)
        + _check_vendor(truth, panel, month, parity, target)
        + _check_statement(truth, panel, month)
        + _check_wait(truth, panel, month)
        + _check_channel(truth, panel, month)
    )
    return pd.DataFrame(rows)


def _parity(month: pd.Timestamp) -> str:
    """The parity of `month`'s calendar month: "even" (February, April, …) or "odd"."""
    return "even" if month.month % 2 == 0 else "odd"


def _known(this: np.ndarray, target: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """The rows of `this` month whose target is known, and their 0/1 labels as bools."""
    use = this & target.notna().to_numpy()
    return use, target[use].to_numpy() == 1


def _correlation(panel: pd.DataFrame, column: str, this: np.ndarray) -> float:
    """The Pearson correlation of `column` with the oracle score over `this` month's rows."""
    x, score = (panel.loc[this, c].to_numpy(dtype=float) for c in (column, SCORE))
    return float(np.corrcoef(x, score)[0, 1])


def _check_honest(
    truth: dict,
    panel: pd.DataFrame,
    month: pd.Series,
    parity: dict[str, pd.Timestamp],
    target: pd.Series,
    chance: pd.Series,
) -> list[dict]:
    """The honest score: in each parity's month its correlation with the oracle score is
    loading / √(loading² + σ²) (the standardised score has variance 1, the noise is independent),
    and its AUC for card acquisition is below the oracle's; that AUC is higher in the even month,
    whose noise is quieter."""
    p = trap_parameters(truth, HONEST)
    rows, aucs, n = [], {}, 0
    for name, at in parity.items():
        this = (month == at).to_numpy()
        stratum = f"{name} month {at:%Y-%m}"
        loading, sigma = p["loading"], p["sigma"][name]
        expected = loading / np.sqrt(loading**2 + sigma**2)
        check = f"honest {HONEST}: correlation with {SCORE}"
        rows.append(
            fisher_row(check, stratum, this.sum(), expected, _correlation(panel, HONEST, this))
        )
        use, y = _known(this, target)
        aucs[name] = auc(panel.loc[use, HONEST], y)
        n += use.sum()
        check = f"honest {HONEST}: AUC for {TARGET} (w={WINDOW}) below the oracle's"
        oracle_auc = auc(chance[use], y)
        rows.append(side_row(check, stratum, use.sum(), oracle_auc, aucs[name], above=False))
    check = f"honest {HONEST}: AUC for {TARGET} (w={WINDOW}) above the odd month's"
    stratum = f"even month {parity['even']:%Y-%m} vs {parity['odd']:%Y-%m}"
    rows.append(side_row(check, stratum, n, aucs["odd"], aucs["even"]))
    return rows


def _check_vendor(
    truth: dict,
    panel: pd.DataFrame,
    month: pd.Series,
    parity: dict[str, pd.Timestamp],
    target: pd.Series,
) -> list[dict]:
    """The vendor score: correlated with the oracle score at loading / √(loading² + 1) in the even
    month and not at all in the odd one, where its AUC for card acquisition is 0.5; in the even
    month that AUC is above 0.58."""
    loading = trap_parameters(truth, VENDOR)["loading"]  # in even months; noise alone in odd ones
    expected = {"even": loading / np.sqrt(loading**2 + 1), "odd": 0.0}
    rows = []
    for name, at in parity.items():
        this = (month == at).to_numpy()
        check = f"unstable {VENDOR}: correlation with {SCORE}"
        corr = _correlation(panel, VENDOR, this)
        rows.append(fisher_row(check, f"{name} month {at:%Y-%m}", this.sum(), expected[name], corr))
    check = f"unstable {VENDOR}: AUC for {TARGET} (w={WINDOW})"
    use, y = _known((month == parity["odd"]).to_numpy(), target)
    tolerance = Z_TOL * hanley_se(0.5, y.sum(), (~y).sum())
    realised = auc(panel.loc[use, VENDOR], y)
    rows.append(row(check, f"odd month {parity['odd']:%Y-%m}", use.sum(), 0.5, realised, tolerance))
    use, y = _known((month == parity["even"]).to_numpy(), target)
    stratum = f"even month {parity['even']:%Y-%m}"
    realised = auc(panel.loc[use, VENDOR], y)
    rows.append(side_row(check, stratum, use.sum(), VENDOR_EVEN_AUC_MIN, realised))
    return rows


def _check_statement(truth: dict, panel: pd.DataFrame, month: pd.Series) -> list[dict]:
    """The one-value column: the value or null before the new level's month, the value, the new
    level or null from it; nulls on the spec's share of the rows; the new level on its share of
    the filled rows from its month."""
    p = trap_parameters(truth, STATEMENT)
    only, new, new_month = p["value"], p["new_level"], p["new_level_month"]
    value = panel[STATEMENT]
    filled = value.notna().to_numpy()
    late = (month >= pd.Timestamp(new_month)).to_numpy()
    allowed = np.where(late, value.isin([only, new]), value == only)
    bad = pd.Series(filled & ~allowed)
    check = f"one value {STATEMENT}"
    return [
        violations_row(f"{check}: {only!r} or null before {new_month}", bad[~late]),
        violations_row(f"{check}: {only!r}, {new!r} or null from {new_month}", bad[late]),
        share_row(f"{check}: null", "all", p["null_share"], (~filled).sum(), len(value)),
        share_row(
            f"{check}: {new!r} among the filled rows",
            f"from {new_month}",
            p["new_level_share"],
            (value[late] == new).sum(),
            (filled & late).sum(),
        ),
    ]


def _check_wait(truth: dict, panel: pd.DataFrame, month: pd.Series) -> list[dict]:
    """The wait: null on the spec's share of the rows, never 0; the PSI of its values in the three
    months from the step against the three before is at least 0.25, and between two later months,
    the third after the step and the panel's last, below 0.1.

    PSI bins are the earlier sample's deciles (`table.psi`).
    """
    p = trap_parameters(truth, WAIT)
    wait = panel[WAIT].to_numpy(dtype=float)
    null = np.isnan(wait)
    step, latest = pd.Timestamp(p["step_month"]), month.max()
    earlier, later = step - pd.DateOffset(months=3), step + pd.DateOffset(months=3)
    before, after = (_values_in(wait, month, start, 3) for start in (earlier, step))
    reference, current = (_values_in(wait, month, start, 1) for start in (later, latest))
    check = f"window drift {WAIT}"
    return [
        share_row(f"{check}: null", "all", p["null_share"], null.sum(), len(wait)),
        violations_row(f"{check}: no zero among the values", pd.Series(wait[~null] == 0)),
        side_row(
            f"{check}: PSI of the values across the step",
            f"{step:%Y-%m} and the next 2 months vs the 3 before",
            len(before),
            STEP_PSI_MIN,
            psi(before, after),
        ),
        side_row(
            f"{check}: PSI of the values after the step",
            f"{latest:%Y-%m} vs {later:%Y-%m}",
            len(reference),
            STABLE_PSI_MAX,
            psi(reference, current),
            above=False,
        ),
    ]


def _values_in(
    values: np.ndarray, month: pd.Series, start: pd.Timestamp, months: int
) -> np.ndarray:
    """The non-null `values` of the rows in the `months` months from `start` on."""
    inside = ((month >= start) & (month < start + pd.DateOffset(months=months))).to_numpy()
    return values[inside & ~np.isnan(values)]


def _check_channel(truth: dict, panel: pd.DataFrame, month: pd.Series) -> list[dict]:
    """The contact channel: its level shares in the month before the step and the month after,
    the PSI between those two months within [0.10, 0.25]; the new level on its share of the rows
    from its month, never before."""
    p = trap_parameters(truth, CHANNEL)
    shares = {side: dict(zip(p["levels"], p[side], strict=True)) for side in ("before", "after")}
    new_level, new_month = p["new_level"], p["new_level_month"]
    channel = panel[CHANNEL]
    step = pd.Timestamp(p["step_month"])
    sides = {"before": step - pd.DateOffset(months=1), "after": step + pd.DateOffset(months=1)}
    in_month = {side: channel[(month == at).to_numpy()] for side, at in sides.items()}
    check = f"moderate drift {CHANNEL}"
    rows = [
        share_row(
            f"{check}: share of {level!r}",
            f"{at:%Y-%m}",
            share,
            (in_month[side] == level).sum(),
            len(in_month[side]),
        )
        for side, at in sides.items()
        for level, share in shares[side].items()
    ]
    new = (month >= pd.Timestamp(new_month)).to_numpy()
    rows += [
        range_row(
            f"{check}: PSI of the level shares across the step",
            f"{sides['after']:%Y-%m} vs {sides['before']:%Y-%m}",
            len(in_month["after"]),
            *CHANNEL_PSI_RANGE,
            categorical_psi(in_month["before"], in_month["after"]),
        ),
        share_row(
            f"{check}: share of {new_level!r}",
            f"from {new_month}",
            p["new_level_share"],
            (channel[new] == new_level).sum(),
            new.sum(),
        ),
        violations_row(f"{check}: no {new_level!r} before {new_month}", channel[~new] == new_level),
    ]
    return rows
