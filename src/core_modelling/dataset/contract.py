"""The contract checks: the eligible observation window before any sampling (§4.8).

`check_contract` runs on the rows every pre-model filter passes, in the window's months, after
checking that every window month and the validation month has some: the shared checks (unique
keys; the null callout) and the task's own from the per-task spec (D-050: binary checks both
classes and the rate band, regression a finite, non-constant target). A failure raises with its
numbers. The one callout that never stops the run: a built target whose
windows held nulls while `data.target.null_as` is unset, so would-be negatives may be nulls that
the modelling frames drop (docs/components/dataset.md, requirement 9).
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.sources import missing_months
from core_modelling.tasks import TASK_SPECS

SHOWN_KEYS = 5


def check_contract(panel: DataFrame, cfg: UseCaseConfig) -> list[dict]:
    """Every contract check on the eligible rows of the observation window (`eligible = 1`),
    after the check that every window month and the validation month has eligible rows; one log
    entry each, printed; a failing check raises with its numbers."""
    eligible = panel.where(F.col("eligible") == 1)
    window = cfg.time.train_months
    in_window = eligible.where(F.col("month").between(window.first, window.last))
    checks = [_check_unique_keys, *TASK_SPECS[cfg.task]["contract_checks"], _null_callout]
    log = [{"step": "contract", **_check_eligible_months(eligible, cfg)}]
    log += [{"step": "contract", **check(in_window, cfg)} for check in checks]
    for entry in log:
        print(f"contract {entry['check']}: {_shown(entry)}")
    return log


def _check_eligible_months(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """Every month of the window and the validation month has eligible rows: a month without
    any would leave the modelling frames quietly."""
    window, validation = cfg.time.train_months, cfg.time.validation_month
    months = F.col("month").between(window.first, window.last) | (F.col("month") == validation)
    counts = eligible.where(months).groupBy("month").count().orderBy("month").collect()
    per_month = {f"{row.month:%Y-%m}": row["count"] for row in counts}
    wanted = missing_months([], window.first, window.last) + [f"{validation:%Y-%m}"]
    empty = [month for month in wanted if not per_month.get(month)]
    if empty:
        raise ValueError(
            f"no eligible row in the months {empty}: every month of the window and the "
            "validation month must have some"
        )
    return {"check": "eligible_rows", "per_month": per_month}


def _shown(entry: dict) -> str:
    """The entry's scalar values on one line (the per-month tables stay in the log)."""
    scalars = {
        key: f"{value:.4f}" if isinstance(value, float) else value
        for key, value in entry.items()
        if key not in ("step", "check") and value is not None and not isinstance(value, dict)
    }
    return ", ".join(f"{key} {value}" for key, value in scalars.items())


def _check_unique_keys(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """One row per unit and month."""
    repeated = eligible.groupBy("unit_id", "month").count().where("count > 1")
    shown = repeated.limit(SHOWN_KEYS).collect()
    if shown:
        keys = ", ".join(f"({row.unit_id}, {row.month})" for row in shown)
        raise ValueError(f"the eligible window has repeated (unit_id, month) keys, e.g. {keys}")
    return {"check": "unique_keys", "repeated": 0}


def _null_callout(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """The share of eligible rows whose target window held a null in the target column, and the
    callout when it is above 0 without `null_as`: the nulls may hide negatives, which the
    modelling frames drop; unknown for an upstream target."""
    share = eligible.agg(F.avg(F.col("null_in_window").cast("double"))).collect()[0][0]
    if share is None:
        return {"check": "null_in_window", "share": None, "callout": None,
                "note": "unknown for an upstream target"}  # fmt: skip
    callout = None
    if share and cfg.data.target.null_as is None:
        callout = (
            f"{share:.1%} of the eligible window's rows had a null in {cfg.data.target.column!r} "
            "at t or in the target window; a null never counts as an event, so if a null means "
            "0 (a non-holder) set data.target.null_as: 0; else a null at t gives a null target, "
            "dropped from the modelling frames, and a null in the window may hide an event"
        )
    return {"check": "null_in_window", "share": share, "callout": callout}
