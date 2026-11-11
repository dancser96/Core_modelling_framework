"""Feature Checks' inputs: EDA's artifacts gathered and checked into one `CheckInputs`.

`check_inputs` refuses EDA artifacts the steps cannot read (a missing ledger column, table, table
column or `eda.json` key: `EDA_LEDGER_COLUMNS`, `EDA_TABLES`, the column lists, `EDA_META_KEYS`)
and EDA tables without rows for a read candidate, so a stale EDA fails here and not inside a step.
It gathers what every step reads: the read candidates' ledger rows (neither lineage nor
unsupported, which are automatic exclusions and never reach a step), EDA's cells,
client-constant, correlation, ranking and per-period concordance tables, the compared periods,
the level encoding's prior on the window and the label-free per-period table
(`measures.per_period_table`). The steps themselves are in `steps.py`.
"""

from dataclasses import dataclass

import pandas as pd

from core_modelling.config.schema import Leakage, UseCaseConfig
from core_modelling.feature_checks.measures import PERIOD_GROUPS, per_period_table
from core_modelling.ledger import read_candidates
from core_modelling.statistics.scope import encoding_prior_rows

EDA_LEDGER_COLUMNS = ["feature", "kind", "levels", "lineage", "unsupported", "concordance",
                      "concordance_window", "missing_share_window", "null_concordance_window",
                      "zero_share_window", "dominant_share_window"]  # fmt: skip
EDA_TABLES = ("cells", "client_constant", "correlation", "ranking", "concordance_per_period")
EDA_RANKING_COLUMNS = ["feature", "raw_sign_window", "concordance_window",
                       "concordance_best_order_window", "unavailable"]  # fmt: skip
EDA_PER_PERIOD_COLUMNS = ["feature", "period", "rows", "support", "concordance", "se",
                          "unavailable"]  # fmt: skip
EDA_META_KEYS = ["compared_periods", "snapshot_period", "over_ceiling", "clients", "headline"]


@dataclass(frozen=True, eq=False)  # DataFrame fields: no field-wise ==
class CheckInputs:
    """What every step reads: the read candidates' ledger rows (identity and EDA columns), EDA's
    tables (`concordance_per_period` its window concordance per period), the label-free
    per-period table, `eda.json`'s compared periods, snapshot period and level ceiling list, and
    the run's settings (`clients` `eda.json`'s window clients that scale a support to effective
    clients, `exact` that `eda.bins` is null, `prior_rows` the level encoding's prior on the
    window; the leakage step's `null_concordance_max`, the `nulls_informative` note's upper
    bound, and `dominant_share_min`, which `near_constant`'s detail reads too)."""

    ledger: pd.DataFrame
    cells: pd.DataFrame
    client_constant: pd.DataFrame
    correlation: pd.DataFrame
    ranking: pd.DataFrame
    concordance_per_period: pd.DataFrame
    per_period: pd.DataFrame
    periods: dict[str, list[str]]
    snapshot_period: str
    over_ceiling: list[str]
    task: str
    clients: dict[str, float]
    exact: bool
    prior_rows: float
    null_concordance_max: float
    dominant_share_min: float


def check_inputs(
    ledger: pd.DataFrame,
    eda_tables: dict[str, pd.DataFrame],
    eda_meta: dict,
    resolved: UseCaseConfig,
) -> CheckInputs:
    """The steps' inputs from EDA's ledger as read (`read_ledger`), the json and tables
    `read_stage` returns and the resolved config: the read candidates only, the encoding's
    prior on the window, the leakage settings and the label-free per-period table."""
    _check_eda_artifacts(ledger, eda_tables, eda_meta)
    read = _read_candidates(ledger, eda_tables)
    periods = {group: list(eda_meta["compared_periods"][group]) for group in PERIOD_GROUPS}
    cells, task, snapshot = eda_tables["cells"], resolved.task, eda_meta["snapshot_period"]
    prior_rows = encoding_prior_rows(cells, task, resolved.strata.min_events, periods["window"])
    per_period = per_period_table(
        cells, dict(zip(read["feature"], read["kind"], strict=True)), periods=periods,
        snapshot_period=snapshot,
    )  # fmt: skip
    leakage = resolved.feature_checks.leakage or Leakage()
    return CheckInputs(
        ledger=read, cells=cells, client_constant=eda_tables["client_constant"],
        correlation=eda_tables["correlation"], ranking=eda_tables["ranking"],
        concordance_per_period=eda_tables["concordance_per_period"], per_period=per_period,
        periods=periods, snapshot_period=snapshot, over_ceiling=list(eda_meta["over_ceiling"]),
        task=task, clients=dict(eda_meta["clients"]), exact=resolved.eda.bins is None,
        prior_rows=prior_rows, null_concordance_max=leakage.null_concordance_max,
        dominant_share_min=leakage.dominant_share_min,
    )  # fmt: skip


def _check_eda_artifacts(ledger: pd.DataFrame, tables: dict[str, pd.DataFrame], meta: dict) -> None:
    """Refuse EDA artifacts the steps cannot read, naming what is missing; the ledger's columns
    are checked before any is read."""
    ranking = tables.get("ranking", pd.DataFrame(columns=EDA_RANKING_COLUMNS))
    per_period = tables.get("concordance_per_period", pd.DataFrame(columns=EDA_PER_PERIOD_COLUMNS))
    missing = {
        "ledger columns": [column for column in EDA_LEDGER_COLUMNS if column not in ledger],
        "tables": [name for name in EDA_TABLES if name not in tables],
        "ranking columns": [column for column in EDA_RANKING_COLUMNS if column not in ranking],
        "concordance_per_period columns": [
            column for column in EDA_PER_PERIOD_COLUMNS if column not in per_period
        ],
        "eda.json keys": [key for key in EDA_META_KEYS if key not in meta],
    }
    missing = {what: names for what, names in missing.items() if names}
    if missing:
        raise ValueError(f"Feature Checks: EDA's artifacts lack {missing}: run EDA (run_eda)")


def _read_candidates(ledger: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The ledger's read candidates (neither lineage nor unsupported: automatic exclusions),
    refused when there are none or EDA's tables hold no rows for one."""
    read = read_candidates(ledger).reset_index(drop=True)
    if read.empty:
        raise ValueError(
            "Feature Checks: no read candidates (every candidate is lineage or unsupported)"
        )
    features = set(read["feature"])
    uncovered = {
        name: sorted(features - set(tables[name]["feature"]))
        for name in ("cells", "client_constant", "ranking", "concordance_per_period")
    }
    uncovered = {name: names for name, names in uncovered.items() if names}
    if uncovered:
        raise ValueError(
            f"Feature Checks: EDA's tables hold no rows for the read candidates {uncovered}: "
            "rerun EDA (run_eda)"
        )
    return read
