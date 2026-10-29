"""The contract checks: the eligible observation window before any sampling (§4.8).

`check_contract` runs on the rows every modelling filter passes, in the window's periods, after
checking that every window period and the validation period has some: the shared checks (unique
keys; the null callout) and the task's own from the per-task spec (D-050: binary checks both
classes and the rate band, regression a finite, non-constant target). A failure raises with its
numbers. The one callout that never stops the run: a built target whose windows held nulls in
the target column, so would-be negatives may be nulls that the modelling frames drop, to be
filled upstream when a null means a value (docs/components/dataset.md, requirement 9). The
share is over the target source's rows in the window with a complete target window, before
eligibility, and comes from the panel's join log (`load_panel` keeps it per use case), so the
saved model input needs no `null_in_window` column.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.periods import label_by_period, period_labels, period_spec
from core_modelling.tasks import TASK_SPECS

SHOWN_KEYS = 5
NULL_POPULATION = (
    "target-source rows in the window with a complete target window, before eligibility"
)


def check_contract(
    panel: DataFrame, cfg: UseCaseConfig, null_in_window_share: float | None
) -> list[dict]:
    """Every contract check on the eligible rows of the observation window (`eligible = 1`),
    after the check that every window period and the validation period has eligible rows; one
    log entry each, printed; a failing check raises with its numbers. `null_in_window_share` is
    the share of the target source's window rows (complete target window, before eligibility)
    whose target window held a null (None: an upstream target)."""
    eligible = panel.where(F.col("eligible") == 1)
    window = cfg.time.observation_window
    in_window = eligible.where(F.col("period").between(window.first, window.last))
    checks = [_check_unique_keys, *TASK_SPECS[cfg.task]["contract_checks"]]
    log = [{"step": "contract", **_check_eligible_periods(eligible, cfg)}]
    log += [{"step": "contract", **check(in_window, cfg)} for check in checks]
    log.append({"step": "contract", **_null_callout(null_in_window_share, cfg)})
    for entry in log:
        print(f"contract {entry['check']}: {_shown(entry)}")
    return log


def _check_eligible_periods(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """Every period of the window and the validation period has eligible rows: a period without
    any would leave the modelling frames quietly."""
    spec, window, validation = (
        period_spec(cfg),
        cfg.time.observation_window,
        cfg.time.validation_period,
    )
    periods = F.col("period").between(window.first, window.last) | (F.col("period") == validation)
    counts = eligible.where(periods).groupBy("period").count().orderBy("period").collect()
    per_period = label_by_period(counts, "count", spec)
    wanted = period_labels(window.first, window.last, spec) + [spec.label(validation)]
    empty = [period for period in wanted if not per_period.get(period)]
    if empty:
        raise ValueError(
            f"no eligible row in the periods {empty}: every period of the window and the "
            "validation period must have some"
        )
    min_rows = min(per_period.values())
    return {"check": "eligible_rows", "min_rows": min_rows, "per_period": per_period}


def _shown(entry: dict) -> str:
    """The entry's scalar values on one line (the per-period tables stay in the log)."""
    scalars = {
        key: f"{value:.4f}" if isinstance(value, float) else value
        for key, value in entry.items()
        if key not in ("step", "check") and value is not None and not isinstance(value, dict)
    }
    return ", ".join(f"{key} {value}" for key, value in scalars.items())


def _check_unique_keys(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """One row per unit and period."""
    repeated = eligible.groupBy("unit_id", "period").count().where("count > 1")
    shown = repeated.limit(SHOWN_KEYS).collect()
    if shown:
        keys = ", ".join(f"({row.unit_id}, {row.period})" for row in shown)
        raise ValueError(f"the eligible window has repeated (unit_id, period) keys, e.g. {keys}")
    return {"check": "unique_keys", "repeated": 0}


def _null_callout(share: float | None, cfg: UseCaseConfig) -> dict:
    """The share of the target source's window rows (complete target window, before eligibility)
    whose target window held a null in the target column, and the callout when it is above 0:
    the nulls may hide negatives, which the modelling frames drop; unknown (None) for an
    upstream target."""
    if share is None:
        return {"check": "null_in_window", "share": None, "callout": None,
                "note": "unknown for an upstream target"}  # fmt: skip
    callout = None
    if share:
        callout = (
            f"{share:.1%} of the target source's rows in the window with a complete target "
            f"window (before eligibility) had a null in {cfg.data.target.column!r} at t or in "
            "the window; a null never counts as an event: a null at t gives a null target, "
            "dropped from the modelling frames, and a null in the window may hide an event; if "
            "a null means a value here (0 for a non-holder), fill it upstream"
        )
    return {"check": "null_in_window", "share": share, "callout": callout,
            "population": NULL_POPULATION}  # fmt: skip
