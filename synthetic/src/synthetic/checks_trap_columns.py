"""Step-5 checks on the traps that sit on any product: null controls, quality, login drift, and the
off-by-default switches (dirty data, extra columns).

`column_trap_rows` is part of the `check_traps` table (`checks_traps` adds the traps on the two
trap products). Null controls and the near-constant flag use one row per client (the panel's
middle month, `target_windows.observation_month`); the drift reads every active user's month.
`check_dirty` runs on a dataset written with `dirty=True` (the unit preset): each defect must be
present as `truth["dirty"]` records it. Assumed record (the generator's layout is not fixed yet):
`duplicate_rows` (count of extra rows repeating a client-month), `outage_month` and
`unit_change_month` (dates as "YYYY-MM-DD"), and `typos` (a list of `{client_id, snapshot_month}`).
`check_extra_columns` runs on a dataset with extra columns: weak ones track a hidden trait, noise
ones none.
"""

import numpy as np
import pandas as pd

from synthetic.check_stats import auc, fisher_row, hanley_se, psi, side_row
from synthetic.check_table import Z_TOL, range_row, row, share_row, violations_row
from synthetic.holding_events import LATENT_COLUMNS
from synthetic.target_windows import (
    BINARY_TARGETS,
    KEYS,
    observation_month,
    realised_target,
    to_panel,
)

NUMERIC_NULL_CONTROLS = [
    "insurance_premium_vol_trap_null_control",
    "branch_visit_cnt_trap_null_control",
]
CATEGORICAL_NULL_CONTROL = "preferred_language_trap_null_control"
NEAR_CONSTANT = "paper_statement_flag_trap_near_constant"
ALL_NULL = "legacy_risk_grade_trap_all_null"
LOGINS = "login_digital_mobile_cnt"
LOGIN_COUNTS = [LOGINS, "login_digital_online_cnt"]
# The outage nulls "the digital columns": taken to be the login measures of the month.
OUTAGE_COLUMNS = [*LOGIN_COUNTS, "days_since_last_login_digital"]
TRAP_COLUMNS = [*NUMERIC_NULL_CONTROLS, CATEGORICAL_NULL_CONTROL, NEAR_CONSTANT, ALL_NULL]
COLUMN_TRAP_MART_COLUMNS = [*TRAP_COLUMNS, "digital_active_flag", LOGINS]
DIRTY_MART_COLUMNS = [*KEYS, "income", "casa_bal", *OUTAGE_COLUMNS]
EXTRA_ORACLE_COLUMNS = [*KEYS, *LATENT_COLUMNS]  # the mart side: keys and every `extra_*` column

# Restated from the trap summary (docs/components/test_harness.md) and plan §4.2.
NULL_CONTROL_WINDOW = 3
NEAR_CONSTANT_ZEROS = 0.999
DRIFT_FIRST_MONTH = 4  # panel month where the drift reference starts (plan §4.2: months 4–15)
DRIFT_PSI_MIN, STABLE_PSI_MAX = 0.25, 0.1
HASH_KEY = "trap-null-halves"  # 16 characters, as pandas' hash needs: splits clients in halves
UNIT_CHANGE = 12  # income × 12 from the unit-change month on
# A × 1,000 typo stands far above the client's other months; 100 leaves room for real moves.
TYPO_MIN_RATIO = 100
WEAK_RANGE = (0.1, 0.3)  # a weak extra column's rank correlation with its trait


def column_trap_rows(panel: pd.DataFrame, spec: dict) -> list[dict]:
    """Rows for the traps on any product: null controls, quality, drift (`to_panel` order)."""
    month = pd.to_datetime(panel["snapshot_month"])
    at_obs = (month == observation_month(panel)).to_numpy()
    return (
        _check_null_controls(panel, at_obs)
        + _check_quality(panel, at_obs)
        + _check_drift(spec, panel, month)
    )


def _check_null_controls(panel: pd.DataFrame, at_obs: np.ndarray) -> list[dict]:
    """Null controls: AUC 0.5 for every binary standard target (w=3), one month.

    The categorical control is scored by its level's event rate, estimated on the other half of the
    clients (split by a seeded hash of `client_id`), so the rates never see the rows they score.
    """
    hashed = pd.util.hash_pandas_object(panel["client_id"], index=False, hash_key=HASH_KEY)
    first_half = (hashed % 2 == 0).to_numpy()
    level, rows = panel[CATEGORICAL_NULL_CONTROL], []
    for target in BINARY_TARGETS:
        y = realised_target(panel, target, NULL_CONTROL_WINDOW)
        use = at_obs & y.notna().to_numpy()
        rows += [_null_row(target, c, panel.loc[use, c], y[use]) for c in NUMERIC_NULL_CONTROLS]
        fit, score = use & first_half, use & ~first_half
        rates = y[fit].groupby(level[fit]).mean()
        # A level the fitting half never saw gets its overall rate, as a fitted encoder would.
        scores = level[score].map(rates).fillna(y[fit].mean())
        rows.append(_null_row(target, CATEGORICAL_NULL_CONTROL, scores, y[score]))
    return rows


def _null_row(target: str, column: str, scores: pd.Series, y: pd.Series) -> dict:
    """A null control's AUC against 0.5, within Z_TOL Hanley–McNeil standard errors at 0.5."""
    hit = y.to_numpy() == 1
    tolerance = Z_TOL * hanley_se(0.5, hit.sum(), (~hit).sum())
    check = f"null control: AUC for {target} (w={NULL_CONTROL_WINDOW}, one month)"
    return row(check, column, len(hit), 0.5, auc(scores, hit), tolerance)


def _check_quality(panel: pd.DataFrame, at_obs: np.ndarray) -> list[dict]:
    """Quality traps: the near-constant flag is 0 for 99.9% of clients (one month); the all-null
    column is null in every row."""
    flag = panel.loc[at_obs, NEAR_CONSTANT]
    zeros = (flag == 0).sum()
    return [
        share_row(
            "quality: near-constant flag is 0", "one month", NEAR_CONSTANT_ZEROS, zeros, len(flag)
        ),
        violations_row("quality: all-null column holds no value", panel[ALL_NULL].notna()),
    ]


def _check_drift(spec: dict, panel: pd.DataFrame, month: pd.Series) -> list[dict]:
    """Login drift: the PSI of active users' mobile logins after the app relaunch against months
    4 to just before it is above 0.25; within those months (second half vs first) below 0.1.

    PSI bins are the earlier sample's deciles (`check_stats.psi`). Panel months count from 1.
    """
    months = pd.DatetimeIndex(np.sort(month.unique()))
    relaunch = months.get_loc(pd.Timestamp(spec["seasons"]["drift"]["app_relaunch_month"])) + 1
    active = panel["digital_active_flag"].to_numpy() == 1
    logins = pd.Series(
        panel.loc[active, LOGINS].astype("float64").to_numpy(),
        index=months.searchsorted(month[active]) + 1,  # panel month, so slices pick month spans
    ).sort_index()
    mid, last = (DRIFT_FIRST_MONTH + relaunch) // 2, len(months)
    reference = logins.loc[DRIFT_FIRST_MONTH : relaunch - 1].to_numpy()
    after = psi(reference, logins.loc[relaunch + 1 : last].to_numpy())
    early, late = logins.loc[DRIFT_FIRST_MONTH : mid - 1], logins.loc[mid : relaunch - 1]
    stable = psi(early.to_numpy(), late.to_numpy())
    check = "drift: PSI of mobile logins, active users"
    after_span = f"months {relaunch + 1}–{last} vs {DRIFT_FIRST_MONTH}–{relaunch - 1}"
    stable_span = f"months {mid}–{relaunch - 1} vs {DRIFT_FIRST_MONTH}–{mid - 1}"
    return [
        side_row(check, after_span, len(reference), DRIFT_PSI_MIN, after),
        side_row(check, stable_span, len(early), STABLE_PSI_MAX, stable, above=False),
    ]


def check_dirty(mart: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Dirty switches: every defect present as `truth["dirty"]` records it (rules, any size)."""
    record = truth["dirty"]
    found = int(mart.duplicated(KEYS).sum())
    clean = mart.drop_duplicates(KEYS)  # each client-month once, for the other defects
    rows = [
        row(
            "dirty: duplicate client-months present",
            "all",
            len(mart),
            1,
            float(found > 0),
            0,
            rule=True,
        ),
        row(
            "dirty: duplicate client-months as recorded",
            "all",
            len(mart),
            record["duplicate_rows"],
            found,
            0,
            rule=True,
        ),
        *_outage_rows(clean, pd.Timestamp(record["outage_month"])),
        _unit_change_row(clean, pd.Timestamp(record["unit_change_month"])),
        _typo_row(clean, pd.DataFrame(record["typos"])),
    ]
    return pd.DataFrame(rows)


def _outage_rows(clean: pd.DataFrame, outage: pd.Timestamp) -> list[dict]:
    """The outage month has every login column null; login counts are null in no other month."""
    in_outage = (pd.to_datetime(clean["snapshot_month"]) == outage).to_numpy()
    return [
        violations_row(
            "dirty: login columns all null in the outage month",
            clean.loc[in_outage, OUTAGE_COLUMNS].notna().any(axis=1),
        ),
        violations_row(
            "dirty: login counts null only in the outage month",
            clean.loc[~in_outage, LOGIN_COUNTS].isna().any(axis=1),
        ),
    ]


def _unit_change_row(clean: pd.DataFrame, change: pd.Timestamp) -> dict:
    """Declared income is 12 × the month before the unit change in every month from it on."""
    month = pd.to_datetime(clean["snapshot_month"])
    before = clean.loc[month == change - pd.DateOffset(months=1), ["client_id", "income"]]
    after = clean.loc[month >= change, ["client_id", "income"]]
    pairs = before.merge(after, on="client_id", suffixes=("_0", "_1")).dropna()
    bad = ~np.isclose(pairs["income_1"], UNIT_CHANGE * pairs["income_0"], rtol=1e-9, atol=0.01)
    return violations_row("dirty: income × 12 from the unit-change month on", pd.Series(bad))


def _typo_row(clean: pd.DataFrame, typos: pd.DataFrame) -> dict:
    """Every recorded typo is in the mart, positive, and ≥ 100 × the client's median `casa_bal`
    over its other months."""
    balance = pd.DataFrame(
        dict(
            client_id=clean["client_id"].to_numpy(),
            month=pd.to_datetime(clean["snapshot_month"]).to_numpy(),
            casa_bal=clean["casa_bal"].astype("float64").to_numpy(),
        )
    )
    recorded = pd.DataFrame(
        dict(client_id=typos["client_id"], month=pd.to_datetime(typos["snapshot_month"]))
    ).drop_duplicates()
    marked = balance.merge(recorded, on=["client_id", "month"], how="left", indicator=True)
    other_months = (marked["_merge"] == "left_only").to_numpy()
    usual_by_client = balance[other_months].groupby("client_id")["casa_bal"].median()
    at_typo = recorded.merge(balance, on=["client_id", "month"], how="left")
    usual = at_typo["client_id"].map(usual_by_client)
    bad = ~((at_typo["casa_bal"] > 0) & (at_typo["casa_bal"] >= TYPO_MIN_RATIO * usual))
    return violations_row("dirty: casa_bal typos ≥ 100 × the client's usual balance", bad)


def check_extra_columns(mart: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    """Extra columns (one month): a weak column's strongest rank correlation with the five hidden
    traits lies in [0.1, 0.3]; a noise column's is within Z_TOL Fisher-z standard errors of 0."""
    extra = [c for c in mart.columns if c.startswith("extra_")]
    if not extra:
        raise ValueError("the mart has no extra columns")
    panel = to_panel(mart[[*KEYS, *extra]], oracle[EXTRA_ORACLE_COLUMNS])
    one = panel[pd.to_datetime(panel["snapshot_month"]) == observation_month(panel)]
    corr = _trait_correlations(one, extra)
    strongest = corr.to_numpy()[np.arange(len(extra)), corr.abs().to_numpy().argmax(axis=1)]
    rows = []
    for column, rho in zip(extra, strongest, strict=True):
        kind = column.rsplit("_trap_", 1)[-1]
        if kind == "weak":
            check = "extra: weak column's strongest |rank correlation| with a trait"
            rows.append(range_row(check, column, len(one), *WEAK_RANGE, abs(rho)))
        elif kind == "noise":
            check = "extra: noise column's strongest rank correlation with a trait"
            rows.append(fisher_row(check, column, len(one), 0.0, rho, rank=True))
        else:
            raise ValueError(f"extra column {column} is neither _trap_weak nor _trap_noise")
    return pd.DataFrame(rows)


def _trait_correlations(one: pd.DataFrame, extra: list[str]) -> pd.DataFrame:
    """Spearman correlation of every extra column (rows) with every hidden trait (columns)."""
    ranks = one[[*extra, *LATENT_COLUMNS]].rank()
    z = ((ranks - ranks.mean()) / ranks.std(ddof=0)).to_numpy()
    corr = z[:, : len(extra)].T @ z[:, len(extra) :] / len(z)
    return pd.DataFrame(corr, index=extra, columns=LATENT_COLUMNS)
