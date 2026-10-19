"""Checks of the off-by-default switches: dirty data and extra columns.

They are not a suite family (the canonical dataset has neither switch on); the tests call them on
small datasets written with the switch on. `check_dirty` (a dataset written with `dirty=True`):
every defect is present as `truth["dirty"]` records it. `check_extra_columns` (a dataset with
extra columns): weak columns track a hidden trait, noise columns none.
"""

import numpy as np
import pandas as pd

from synthetic.checks.events import KEYS, LATENT_COLUMNS, observation_month, to_panel
from synthetic.checks.table import fisher_row, range_row, row, violations_row

LOGIN_COUNTS = ["login_digital_mobile_cnt", "login_digital_online_cnt"]
# The outage nulls "the digital columns": taken to be the login measures of the month.
OUTAGE_COLUMNS = [*LOGIN_COUNTS, "days_since_last_login_digital"]
EXTRA_ORACLE_COLUMNS = [*KEYS, *LATENT_COLUMNS]  # the mart side: keys and every `extra_*` column
# Restated from the trap summary (docs/components/test_harness.md).
UNIT_CHANGE = 12  # income × 12 from the unit-change month on
# A × 1,000 typo stands far above the client's other months; 100 leaves room for real moves.
TYPO_MIN_RATIO = 100
WEAK_RANGE = (0.1, 0.3)  # a weak extra column's rank correlation with its trait


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
