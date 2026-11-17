"""The use-case config schema: one Pydantic model per section of the YAML (D-129).

The config is the use case's intent, validated at load and frozen once the target is built
(D-125). Every model forbids unknown keys, so a misspelt or retired field fails naming the key.
Fields the automation level fills (`levels.py`) have no default here: a dict that skipped
`apply_level_defaults` fails loud instead of carrying None. Values that an audit-log replay writes
(`features.excluded`, `features.kept`, `features.held`, `housekeeping`) are empty in a config file,
so the resolved config validates with this same schema (D-125, D-134). A period (the unit of
analysis, `time.period`) is held as its last day, the framework's one convention; a config may
write it as any day the period spec accepts (a month: its first or its last day, D-129). The
Stage 2 and Stage 3 fields changed in place, with no schema bump and no migration (D-136). The
modelling choices a task decides (`TASK_CHOICES`) are checked against the task and, left null,
filled at every validation, so the config states the value in force.
"""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core_modelling.periods import PERIODS

Estimator = Literal["lgbm", "xgboost", "xgb_limitdepth", "catboost"]  # FLAML's names (D-037)
USE_CASE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
TWEEDIE_VARIANCE_POWER = 1.5  # the Tweedie objective's power when the config leaves it null
# They count positives several times behind the calibration's back; sampling does that job with
# the prior-shift offset applied. Compared lowercased; a library's aliases are refused by each
# family's allowed-parameter check.
CLASS_WEIGHT_PARAMETERS = ("scale_pos_weight", "is_unbalance", "class_weight", "class_weights",
                           "auto_class_weights")  # fmt: skip
# Names each family's `fixed_params` sets, refused in the search space (compared lowercased):
# they belong to training.objective, training.seed, training.monotone and the encoder, or the
# framework fixes them. Each maps to the field to use instead (None: fixed).
FRAMEWORK_PARAMETERS: dict[str, str | None] = {
    "objective": "training.objective", "loss_function": "training.objective",
    "tweedie_variance_power": "training.tweedie_variance_power",
    "random_state": "training.seed", "random_seed": "training.seed", "seed": "training.seed",
    "monotone_constraints": "training.monotone",
    "categorical_feature": "features.kinds", "cat_features": "features.kinds",
    "enable_categorical": "training.categoricals.unordered",
    "feature_types": "training.categoricals.unordered",
    "n_jobs": None, "thread_count": None, "nthread": None, "num_threads": None, "missing": None,
    "allow_writing_files": None, "use_best_model": None,
}  # fmt: skip
# The per-task modelling choices, plain data (D-050): the allowed values and the default of each.
# `tasks.TASK_SPECS` carries them too; they live here because `tasks.py` imports pyspark and the
# config package, so the schema cannot import it. Metric names are FLAML's where it has one (T9:
# `ap`); the two deviances are the framework's own (the Tweedie one at a power of 1.5). A
# calibration default is the decision's entry, else the objective's, else `calibration_default`.
# A deviance is defined for positive predictions only, which a log link gives and an identity
# link does not: the metrics that need one of the objectives fitted on the log scale
# (`model/calibration.py`, `LINK_BY_OBJECTIVE`).
DEVIANCE_METRICS = ("tweedie_deviance", "poisson_deviance")
LOG_LINK_OBJECTIVES = ("tweedie", "poisson")
TASK_CHOICES: dict[str, dict] = {
    "binary": {
        "metrics": ["log_loss", "roc_auc", "ap"],
        "metric_by_decision": {"probability": "log_loss", "threshold": "log_loss",
                               "ranking": "roc_auc", "top_n": "roc_auc"},
        "objectives": ["log_loss"],
        "objective_default": "log_loss",
        "calibration_methods": ["platt", "beta", "none"],
        "calibration_by_decision": {"probability": "platt"},
        "calibration_by_objective": {},
        "calibration_default": "none",
    },
    "regression": {
        "metrics": ["rmse", "mae", "r2", "tweedie_deviance", "poisson_deviance"],
        "metric_by_decision": {"probability": "rmse", "threshold": "rmse", "ranking": "rmse",
                               "top_n": "rmse"},
        "objectives": ["squared_error", "tweedie", "poisson", "absolute_error", "huber"],
        "objective_default": "squared_error",
        "calibration_methods": ["mean", "none"],
        "calibration_by_decision": {},
        "calibration_by_objective": {"tweedie": "mean", "poisson": "mean"},
        "calibration_default": "none",
    },
}  # fmt: skip


class StrictModel(BaseModel):
    """Base of every section: unknown keys fail loud, naming the key (one shallow level)."""

    model_config = ConfigDict(extra="forbid")


def _unique_names(steps: list) -> list:
    """Refuse duplicate `name` entries in an ordered step list."""
    names = [step.name for step in steps]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"step names must be unique; repeated: {repeated}")
    return steps


Name = Annotated[str, Field(pattern=r"^\s*\S")]  # a source or column name: not empty or blank


class PreviousModel(StrictModel):
    """A baseline: a score column of a source, judged like the model."""

    previous_model: Name


class HistoricPredictedRate(StrictModel):
    """A baseline: one rate in use (a number), or a column judged like a previous model."""

    historic_predicted_rate: float | Name


Baseline = Literal["population_base_rate", "single_feature"] | PreviousModel | HistoricPredictedRate


class Decision(StrictModel):
    """How the scores are used; declared before any result and never loggable (§4.3). `metric`
    left null is filled from the type (`TASK_CHOICES`); `UseCaseConfig` checks it against the
    task."""

    type: Literal["top_n", "threshold", "ranking", "probability"]
    n: int | None = Field(default=None, ge=1)
    metric: str | None = None
    baselines: list[Baseline] = Field(
        default=["population_base_rate", "single_feature"], min_length=1
    )

    @model_validator(mode="after")
    def _check_n_matches_type(self) -> "Decision":
        """A top-N decision needs the list size, and only a top-N decision reads it, so an `n`
        under another type would be ignored."""
        if self.type == "top_n" and self.n is None:
            raise ValueError("decision.type 'top_n' needs decision.n (the list size)")
        if self.type != "top_n" and self.n is not None:
            raise ValueError(
                f"decision.n is read only when decision.type is 'top_n'; decision.type is "
                f"{self.type!r}: leave decision.n null"
            )
        return self


class SourceKeys(StrictModel):
    """A source's own key column names; a field left out is named as in `data.keys`."""

    unit_id: Name | None = None
    period: Name | None = None


class SourceEntry(StrictModel):
    """A logical source whose key columns are named other than `data.keys` (e.g. an extract)."""

    source: Name
    keys: SourceKeys

    @model_validator(mode="after")
    def _check_own_key(self) -> "SourceEntry":
        """At least one own key name; keys restating `data.keys` are the writer's to avoid
        (`dataset.md`, Key names)."""
        if self.keys.unit_id is None and self.keys.period is None:
            raise ValueError(
                f"source {self.source!r}: keys names no column; name one, or list the source "
                "by its plain name"
            )
        return self


class Sources(StrictModel):
    """An entity's logical sources, each a name or `{source, keys}`: the first feature source
    is the governing spine, keyed by `data.keys`. A plain name stays a string in the dump, so
    the hashes of a config without own keys are unchanged."""

    features: list[Name | SourceEntry] = Field(min_length=1)
    targets: Name | SourceEntry | None = None

    @model_validator(mode="after")
    def _check_features(self) -> "Sources":
        """The spine is a plain name, no logical source is named twice, ignoring case (the
        join's marker columns are Spark columns), and a target source that is also a feature
        source is keyed as its feature entry."""
        if isinstance(self.features[0], SourceEntry):
            raise ValueError(
                f"sources.features: the first feature source {self.features[0].source!r} is the "
                "spine, keyed by data.keys; name it plainly and set data.keys to its key columns"
            )
        names = [(e if isinstance(e, str) else e.source).lower() for e in self.features]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(f"sources.features names a source twice: {repeated}")
        target = self.targets if isinstance(self.targets, str | None) else self.targets.source
        twin = names.index(target.lower()) if target and target.lower() in names else None
        if twin is not None and self.features[twin] != self.targets:
            raise ValueError(
                f"sources.targets {target!r} is also a feature source: key it exactly as in "
                "sources.features, since the same rows under another period column would shift "
                "the target against the features"
            )
        return self


class Entity(StrictModel):
    """One entity the use case applies to (D-034)."""

    sources: Sources


class Keys(StrictModel):
    """The sources' key column names, renamed to `unit_id` and `period` at load."""

    unit_id: str
    period: str


class EligibilityStep(StrictModel):
    """One ordered eligibility entry: a named `define` condition, or a `filter` with a reason."""

    name: str
    define: str | None = None
    filter: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_define_or_filter(self) -> "EligibilityStep":
        """Exactly one of `define` / `filter`, and a `filter` says why."""
        if (self.define is None) == (self.filter is None):
            raise ValueError(f"eligibility step {self.name!r} needs exactly one of define / filter")
        if self.filter is not None and not self.reason:
            raise ValueError(f"eligibility filter {self.name!r} needs a reason")
        return self


class Eligibility(StrictModel):
    """The two ordered step lists (D-129): `analysis` filters drop their rows before EDA;
    `modelling` filters keep them for EDA, tagged by the step's name, and drop them before
    Feature Checks. A define in either list serves the steps after it."""

    analysis: list[EligibilityStep] = []
    modelling: list[EligibilityStep] = []

    @model_validator(mode="after")
    def _check_names_unique_across_both(self) -> "Eligibility":
        """One name space: a tag column and a log entry are named after the step."""
        _unique_names([*self.analysis, *self.modelling])
        return self


class Target(StrictModel):
    """The target spec: a rule over `column` (built), or an upstream `column` alone. The rule name
    is checked against the task's spec when the target is built, not here."""

    column: str
    rule: str | None = None
    lineage: list[str] = []


class Split(StrictModel):
    """The client split (seeded hash), applied from Training on (D-030)."""

    test_share: float = Field(default=0.3, gt=0, lt=1)
    seed: int = 42


class RateBand(StrictModel):
    """The contract check's ceiling on the true population's target rate; no floor."""

    max: float = Field(default=0.5, gt=0, le=1)


class Data(StrictModel):
    """Keys, eligibility, target, split, rate band and the saved model input."""

    keys: Keys
    eligibility: Eligibility = Eligibility()
    target: Target
    split: Split = Split()
    rate_band: RateBand = RateBand()
    model_input: str | None = None


class ObservationWindow(StrictModel):
    """The observation window t1 … tk, each period as its last day."""

    first: date
    last: date


def _accepted_period_end(value: date, period: str, path: str) -> date:
    """The typo rule: a date the period may not be written as (a month: a day that is neither its
    first nor its last) is refused naming `path`; an accepted date moves to its period's end."""
    spec = PERIODS[period]
    if not spec.accept(value):
        raise ValueError(
            f"{path} {value} must be the first or the last day of a {period}, "
            f"e.g. {spec.end(value)}"
        )
    return spec.end(value)


class Time(StrictModel):
    """The unit of analysis, the observation window, the target window `w` (periods t+1 … t+w)
    and the validation period, null for an EDA-only config (Training refuses it); the dates are
    held as their period's last day."""

    period: Literal["month", "week", "day"] = "month"
    observation_window: ObservationWindow
    target_window: int = Field(ge=1)
    validation_period: date | None

    @model_validator(mode="after")
    def _move_to_period_end(self) -> "Time":
        """The typo rule on the window's bounds and the validation period, when set; the accepted
        dates move to their period's end."""
        period, window = self.period, self.observation_window
        window.first = _accepted_period_end(window.first, period, "time.observation_window.first")
        window.last = _accepted_period_end(window.last, period, "time.observation_window.last")
        if self.validation_period is not None:
            self.validation_period = _accepted_period_end(
                self.validation_period, period, "time.validation_period"
            )
        return self

    @model_validator(mode="after")
    def _check_window_order(self) -> "Time":
        """The window's first period is not after its last."""
        first, last = self.observation_window.first, self.observation_window.last
        if first > last:
            raise ValueError(f"time.observation_window.first {first} is after last {last}")
        return self

    @model_validator(mode="after")
    def _check_validation_after_window(self) -> "Time":
        """No training target window overlaps the validation period's: v ≥ tk + w (§4.2), counted
        in periods by the spec's index; nothing to check without a validation period."""
        if self.validation_period is None:
            return self
        spec = PERIODS[self.period]
        gap = spec.index(self.validation_period) - spec.index(self.observation_window.last)
        if gap < self.target_window:
            raise ValueError(
                f"time.validation_period {self.validation_period} is {gap} {self.period}s after "
                f"the window's last period; it must be at least target_window "
                f"({self.target_window}) after it"
            )
        return self


class Candidates(StrictModel):
    """Glob patterns over the feature sources' columns."""

    include: list[str] = ["*"]
    exclude: list[str] = []


class Features(StrictModel):
    """The candidates and the kind overrides (`{column: numeric | categorical}`, over the
    Spark-schema default; a key naming no candidate is refused when the frames are built, since
    the candidates are patterns until then). `order` declares an ordered categorical's levels,
    lowest first; a name that is no candidate, or no categorical, is refused when the frames are
    built. `excluded`, `kept` and `held` are written by the audit log's replay and empty in a
    file; for Training a held feature acts as an excluded feature without a final decision
    (D-134)."""

    candidates: Candidates = Candidates()
    kinds: dict[str, Literal["numeric", "categorical"]] = {}
    order: dict[str, list[str]] = {}
    excluded: list[str] = []
    kept: list[str] = []
    held: list[str] = []

    @field_validator("order")
    @classmethod
    def _check_order_levels(cls, order: dict[str, list[str]]) -> dict[str, list[str]]:
        """Each declared order lists at least one level, each once: a level's position is its
        code."""
        for feature, levels in order.items():
            repeated = sorted({level for level in levels if levels.count(level) > 1})
            if not levels or repeated:
                problem = f"repeats {repeated}" if repeated else "is empty"
                raise ValueError(
                    f"features.order.{feature} {problem}: list every train level once, lowest first"
                )
        return order


class Strata(StrictModel):
    """Stratification variables shared by EDA, Evaluation and Monitoring (D-038)."""

    variables: list[str]
    max_levels: int = Field(default=10, ge=2)
    min_events: int = Field(default=50, ge=1)


class KeyFeatures(StrictModel):
    """EDA's key features: the top-N of the ranking, skipping a candidate associated above
    `max_correlation` with one already chosen, plus the listed ones."""

    top_n: int = Field(default=10, ge=0)
    include: list[str] = []
    max_correlation: float = Field(default=0.9, gt=0, le=1)


class Eda(StrictModel):
    """EDA's knobs: the snapshot period it collects whole, the quantile bins per numeric (null:
    every value its own bin) and the key features (D-135)."""

    snapshot: Literal["last"] | date = "last"
    bins: int | None = Field(default=100, ge=2)
    key_features: KeyFeatures = KeyFeatures()


class NullsMayBeZeros(StrictModel):
    """The `nulls_may_be_zeros` note: many nulls and almost never a zero among the values."""

    missing_min: float = Field(default=0.2, gt=0, le=1)
    zero_share_max: float = Field(default=0.005, ge=0, le=1)


class Quality(StrictModel):
    """Feature Checks' `quality` step: all-null, constant, high-missing, near-constant and
    high-cardinality flags, two null notes."""

    dominant_share_max: float = Field(default=0.99, gt=0, le=1)
    missing_share_max: float = Field(default=0.95, gt=0, le=1)
    max_levels: int = Field(default=50, ge=2)
    nulls_may_be_zeros: NullsMayBeZeros = NullsMayBeZeros()
    nulls_informative_min: float = Field(default=0.55, ge=0.5, le=1)


class Leakage(StrictModel):
    """Feature Checks' `leakage` step: too strong, missingness leak, rare-value leak (flags).

    `rare_effect_max` is on Cohen's h (binary) or d (regression) scale: 0.2 small, 0.5 medium,
    0.8 large; capped at 3, so a ratio-era value (5, 10) fails at load instead of never firing (h
    tops out at π, a d above 3 is implausible). `dominant_share_min` is the filled rows' share one
    value must hold before the other values pooled are a minority (the rare-value rule's and
    `near_constant`'s detail).
    """

    concordance_max: float = Field(default=0.80, gt=0.5, le=1)
    null_concordance_max: float = Field(default=0.70, gt=0.5, le=1)
    rare_effect_max: float = Field(default=0.8, gt=0, le=3)
    dominant_share_min: float = Field(default=0.90, gt=0.5, lt=1)


class TimeAlignment(StrictModel):
    """Feature Checks' `time_alignment` step: lagged signal drop, client constant (flags)."""

    signal_kept_min: float = Field(default=0.5, gt=0, le=1)
    constant_clients_min: float = Field(default=0.99, gt=0, le=1)
    concordance_min: float = Field(default=0.6, ge=0.5, le=1)


class Stability(StrictModel):
    """Feature Checks' `stability` step: concordance unstable (flag); PSI in two tiers, a note
    from `psi_note_min` and a flag from `psi_max` (Monitoring's drift threshold); new levels
    (note).

    `concordance_range_min` is relative to the window's signal: the per-period concordances'
    range must reach it × |`concordance_window` − 0.5| (0.5: the periods differ by half the
    signal; 2: from the full signal to its mirror image), so a wobble that matters for a weak
    feature does not flag a strong one. `concordance_range_floor` is the absolute range it never
    goes below, so a feature with no signal needs a real swing (the EDS's Q547).
    """

    psi_note_min: float = Field(default=0.10, gt=0)
    psi_max: float = Field(default=0.25, gt=0)
    heterogeneity_p_max: float = Field(default=0.01, gt=0, lt=1)
    concordance_range_min: float = Field(default=0.5, ge=0, le=2)
    concordance_range_floor: float = Field(default=0.05, ge=0, le=1)
    new_level_share_max: float = Field(default=0.01, gt=0, le=1)

    @model_validator(mode="after")
    def _check_psi_tiers(self) -> "Stability":
        """The PSI note's floor is not above the flag's bound: the note fires between the two."""
        if self.psi_note_min > self.psi_max:
            raise ValueError(
                f"feature_checks.stability.psi_note_min {self.psi_note_min} must be at most "
                f"feature_checks.stability.psi_max {self.psi_max}: the PSI note fires from the "
                "first, the flag from the second"
            )
        return self


class Redundancy(StrictModel):
    """Feature Checks' `redundancy` step: correlated and associated pairs (notes), clustered."""

    correlation_max: float = Field(default=0.90, gt=0, le=1)
    association_max: float = Field(default=0.90, gt=0, le=1)


class FeatureChecks(StrictModel):
    """The five steps' thresholds, one typed entry each. The steps run in a fixed order (quality,
    leakage, time_alignment, stability, redundancy), so no order lives here; a step left out of a
    present mapping is None and not run, and the section left out runs all five (D-137)."""

    quality: Quality | None = None
    leakage: Leakage | None = None
    time_alignment: TimeAlignment | None = None
    stability: Stability | None = None
    redundancy: Redundancy | None = None

    @model_validator(mode="after")
    def _check_a_step_runs(self) -> "FeatureChecks":
        """A present mapping names at least one step: Feature Checks running no check is a
        mistake, since the checks wrap the engine (§4.5)."""
        steps = list(type(self).model_fields)
        if all(getattr(self, step) is None for step in steps):
            raise ValueError(
                f"a present feature_checks mapping must name at least one step "
                f"({', '.join(steps)}); leave the section out to run all five"
            )
        return self

    @model_validator(mode="after")
    def _check_nulls_informative_below_leak(self) -> "FeatureChecks":
        """`quality.nulls_informative_min` lies below the leak bound the quality step uses: the
        `nulls_informative` note fires between the two, the leak flag above. With `leakage` left
        out, the quality step takes `Leakage().null_concordance_max` (the default) as that bound,
        so the check runs against it."""
        if self.quality is None:
            return self
        low = self.quality.nulls_informative_min
        high = (self.leakage or Leakage()).null_concordance_max
        if low >= high:
            raise ValueError(
                f"feature_checks.quality.nulls_informative_min {low} must be below "
                f"feature_checks.leakage.null_concordance_max {high}, or the nulls_informative "
                "note can never fire"
            )
        return self


EVERY_CHECK = FeatureChecks(
    quality=Quality(),
    leakage=Leakage(),
    time_alignment=TimeAlignment(),
    stability=Stability(),
    redundancy=Redundancy(),
)


class Selection(StrictModel):
    """Automated feature selection by rule, on the train split only: one representative per
    redundancy cluster, the floor (dropped below a train concordance of 0.5 + `floor_z` · SE;
    null: off) and importance pruning against noise columns."""

    cluster: bool = True
    floor_z: float | None = Field(default=2.0, gt=0)
    prune: bool = True


class Categoricals(StrictModel):
    """A level seen in fewer distinct train clients joins `__other__` (D-037); an unordered
    categorical is declared to the library (`native`) or passed as its integer codes (`codes`)."""

    min_level_client_count: int = Field(default=50, ge=1)
    unordered: Literal["native", "codes"] = "native"


class Calibration(StrictModel):
    """The calibration step, fitted out-of-fold inside train (D-049). `method` left null is
    filled from the task and the decision (`TASK_CHOICES`); `UseCaseConfig` checks it against
    the task."""

    method: str | None = None


class SearchRange(StrictModel):
    """A searched leaf of `training.search_space`: `low` to `high`, on a log scale or not, whole
    numbers or not; `start` is the first trial's value (left out: the family's default start)."""

    low: int | float
    high: int | float
    log: bool
    integer: bool
    start: int | float | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "SearchRange":
        """`low` below `high` (a constant is written `{value: …}`), above 0 on a log scale,
        whole numbers for an integer range, and `start` inside the range."""
        bounds = [self.low, self.high, *([] if self.start is None else [self.start])]
        if self.low >= self.high:
            raise ValueError(
                f"low {self.low} must be below high {self.high}; a constant is written {{value: …}}"
            )
        if self.log and self.low <= 0:
            raise ValueError(f"a log range needs low above 0, got {self.low}")
        if self.integer and not all(isinstance(bound, int) for bound in bounds):
            raise ValueError(f"an integer range takes whole numbers, got {bounds}")
        if self.start is not None and not self.low <= self.start <= self.high:
            raise ValueError(f"start {self.start} lies outside {self.low} … {self.high}")
        return self


class SearchValue(StrictModel):
    """A leaf of `training.search_space` held constant."""

    value: bool | int | float | str


class Sampling(StrictModel):
    """Train-only sampling, declared by a person (D-117): one method with its one parameter. It
    draws with `training.seed`, which the audit log never sets, so no person picks the sample."""

    method: Literal["negative_downsampling", "client_sample"]
    keep_fraction: float | None = Field(default=None, gt=0, lt=1)
    share: float | None = Field(default=None, gt=0, lt=1)

    @model_validator(mode="after")
    def _check_parameter_matches_method(self) -> "Sampling":
        """`negative_downsampling` takes `keep_fraction`, `client_sample` takes `share`."""
        needed = "keep_fraction" if self.method == "negative_downsampling" else "share"
        other = "share" if needed == "keep_fraction" else "keep_fraction"
        if getattr(self, needed) is None or getattr(self, other) is not None:
            raise ValueError(f"sampling method {self.method!r} takes {needed} only, not {other}")
        return self


class Training(StrictModel):
    """The modelling path, the families and their budgets, the seed, the folds, the objective,
    the monotone constraints, the search ranges, selection, the categoricals, calibration and
    sampling. `objective` and `tweedie_variance_power` left null are filled from the task
    (`TASK_CHOICES`); `UseCaseConfig` checks them against the task."""

    path: Literal["automl"] = "automl"
    estimator_list: list[Estimator] = Field(
        default=["lgbm", "xgboost", "xgb_limitdepth", "catboost"], min_length=1
    )
    max_iter: int = Field(ge=1)
    trials: dict[Estimator, Annotated[int, Field(ge=1)]] | None = None
    time_budget_s: int | None = Field(default=None, ge=1)
    seed: int = 42
    folds: int = Field(default=5, ge=2)
    fold_repeats: int = Field(default=1, ge=1)
    objective: str | None = None
    tweedie_variance_power: float | None = Field(default=None, gt=1, lt=2)
    monotone: dict[str, Literal["increasing", "decreasing"]] = {}
    search_space: dict[Estimator, dict[str, SearchRange | SearchValue]] = {}
    selection: Selection = Selection()
    categoricals: Categoricals = Categoricals()
    calibration: Calibration = Calibration()
    sampling: Sampling | None = None

    @field_validator("estimator_list")
    @classmethod
    def _check_families_once(cls, families: list[str]) -> list[str]:
        """Each family listed once: the budget is split over the list."""
        repeated = sorted({family for family in families if families.count(family) > 1})
        if repeated:
            raise ValueError(f"training.estimator_list repeats {repeated}; list each family once")
        return families

    @model_validator(mode="after")
    def _check_trials_name_the_families(self) -> "Training":
        """`trials` replaces `max_iter` with a budget per family, so it names every listed family
        and no other."""
        if self.trials is not None and set(self.trials) != set(self.estimator_list):
            raise ValueError(
                f"training.trials names {sorted(self.trials)}; it must name exactly the listed "
                f"families {sorted(self.estimator_list)}, or be left null to split max_iter"
            )
        return self

    @model_validator(mode="after")
    def _check_search_space_families(self) -> "Training":
        """A range override applies to a listed family only."""
        unlisted = sorted(set(self.search_space) - set(self.estimator_list))
        if unlisted:
            raise ValueError(
                f"training.search_space names {unlisted}, which training.estimator_list does not "
                f"list ({self.estimator_list}); list the family or drop its entry"
            )
        return self

    @model_validator(mode="after")
    def _check_no_class_weights(self) -> "Training":
        """A class weight changes the class balance without the calibration knowing, so every
        score would come out too high; sampling does the same job with the offset."""
        for family, space in self.search_space.items():
            weights = sorted(name for name in space if name.lower() in CLASS_WEIGHT_PARAMETERS)
            if weights:
                raise ValueError(
                    f"training.search_space.{family} sets {weights}: a class weight shifts every "
                    "score without the calibration knowing; use training.sampling: "
                    "{method: negative_downsampling, keep_fraction: …}, which the prior-shift "
                    "offset undoes"
                )
        return self

    @model_validator(mode="after")
    def _check_no_framework_parameters(self) -> "Training":
        """A parameter the framework sets for every fit is not the search space's: a `{value}`
        there would fight `fixed_params` (the objective, the seed, the constraints, the encoder's
        categoricals, the threads)."""
        for family, space in self.search_space.items():
            owned = [name for name in space if name.lower() in FRAMEWORK_PARAMETERS]
            if owned:
                uses = [
                    f"{name}: use {FRAMEWORK_PARAMETERS[name.lower()]}"
                    if FRAMEWORK_PARAMETERS[name.lower()]
                    else f"{name}: fixed by the framework"
                    for name in owned
                ]
                raise ValueError(
                    f"training.search_space.{family} sets what the framework sets for every fit "
                    f"({'; '.join(uses)}); drop the entry"
                )
        return self

    @model_validator(mode="after")
    def _check_lgbm_monotone_method(self) -> "Training":
        """The method is a constant (`{value}`); LightGBM's `advanced` broke the constraint when
        measured, and `intermediate` with `colsample_bynode` falls back to `basic` with only a
        warning."""
        space = self.search_space.get("lgbm", {})
        method = space.get("monotone_constraints_method")
        path = "training.search_space.lgbm.monotone_constraints_method"
        if isinstance(method, SearchRange):
            raise ValueError(f"{path} names a method, written {{value: intermediate}}, not a range")
        chosen = str(method.value).lower() if method is not None else None
        if chosen == "advanced":
            raise ValueError(
                f"{path}: advanced broke the monotone constraint when measured; use basic (the "
                "default) or intermediate"
            )
        if chosen == "intermediate" and "colsample_bynode" in space:
            raise ValueError(
                f"{path}: intermediate with colsample_bynode makes LightGBM fall back to basic "
                "with only a warning; drop colsample_bynode"
            )
        return self

    @model_validator(mode="after")
    def _check_absolute_error_unconstrained(self) -> "Training":
        """The absolute error takes no monotone constraint, whatever the families: LightGBM
        refuses the pair, XGBoost fits and breaks the constraint without a word, and only
        CatBoost held it when measured (T43). Importance pruning fits LightGBM for every run."""
        if self.objective == "absolute_error" and self.monotone:
            raise ValueError(
                f"training.objective 'absolute_error' takes no monotone constraint, and "
                f"training.monotone constrains {sorted(self.monotone)}: LightGBM refuses the "
                "pair and XGBoost breaks the constraint without a word; use training.objective "
                "'huber', which also resists large amounts and holds a constraint in every "
                "family, or drop the constraints"
            )
        return self


class Slices(StrictModel):
    """Metric slices at the top of the score ranking; either list may be empty."""

    top_pct: list[Annotated[float, Field(gt=0, le=1)]]
    top_n: list[Annotated[int, Field(ge=1)]] = []


class Intervals(StrictModel):
    """The client bootstrap behind every interval: its replicates and the coverage."""

    replicates: int = Field(default=200, ge=20)  # fewer give no usable percentile interval
    level: float = Field(default=0.95, gt=0, lt=1)


class Evaluation(StrictModel):
    """Metric slices, the report's views to leave out and the intervals."""

    slices: Slices
    # Any name for now: the view names are Evaluation's, which checks them when it is built.
    skip_views: list[str] = []
    intervals: Intervals = Intervals()


class Inference(StrictModel):
    """Which model version scores: `production` or a registered run_id (a pin)."""

    model: str = "production"


class Drift(StrictModel):
    """Drift thresholds."""

    psi_max: float = Field(default=0.25, gt=0)


class RetrainPolicy(StrictModel):
    """When monitoring says "retrain recommended"; null = not set."""

    max_age_months: int | None = Field(default=None, ge=1)
    psi_flags: int | None = Field(default=None, ge=1)


class Monitoring(StrictModel):
    """Drift thresholds, the outcome join and the retrain policy."""

    drift: Drift = Drift()
    outcome_join: bool = True
    retrain_policy: RetrainPolicy = RetrainPolicy()


class UseCaseConfig(StrictModel):
    """One use case's whole intent: the shared sections plus one section per stage."""

    schema_version: int
    task: Literal["binary", "regression"]
    use_case: str
    domain: str
    automation_level: Literal["autonomous", "assisted"]
    decision: Decision
    entities: dict[str, Entity] = Field(min_length=1)
    data: Data
    time: Time
    features: Features = Features()
    strata: Strata
    eda: Eda = Eda()
    feature_checks: FeatureChecks = EVERY_CHECK
    training: Training
    evaluation: Evaluation
    inference: Inference = Inference()
    monitoring: Monitoring = Monitoring()
    housekeeping: dict[str, object] | None = None

    @model_validator(mode="after")
    def _fill_task_defaults(self) -> "UseCaseConfig":
        """Fill the nulls the task and the decision decide (`_fill_task_nulls`), so the config
        states the value in force, recording them as `housekeeping.task_filled` (path → value).
        A recorded value still unchanged at a later validation (a replayed state, a dump) is
        derived again, so a `set` of the objective refills the calibration; any other value is
        explicit and stays (a `set` takes its path off the record, D-125)."""
        # The value compare keeps a recorded path edited outside the log (a dump re-validated,
        # e.g. `variant(training={"objective": "tweedie"})`) explicit instead of re-deriving it.
        recorded = (self.housekeeping or {}).get("task_filled", {})
        for path, value in recorded.items():
            *parents, leaf = path.split(".")
            node = self
            for name in parents:
                node = getattr(node, name)
            if getattr(node, leaf) == value:
                setattr(node, leaf, None)
        filled = _fill_task_nulls(self)
        if filled or recorded:
            self.housekeeping = {**(self.housekeeping or {}), "task_filled": filled}
        return self

    @model_validator(mode="after")
    def _check_task_choices(self) -> "UseCaseConfig":
        """The metric, the objective and the calibration method are ones the task allows."""
        choices = TASK_CHOICES[self.task]
        for path, value, allowed in (
            ("decision.metric", self.decision.metric, choices["metrics"]),
            ("training.objective", self.training.objective, choices["objectives"]),
            ("training.calibration.method", self.training.calibration.method,
             choices["calibration_methods"]),
        ):  # fmt: skip
            if value not in allowed:
                raise ValueError(
                    f"{path} {value!r} is not one the {self.task} task allows: {allowed} (null "
                    "takes the task's default)"
                )
        return self

    @model_validator(mode="after")
    def _check_tweedie_power(self) -> "UseCaseConfig":
        """The variance power belongs to the Tweedie objective only."""
        power, objective = self.training.tweedie_variance_power, self.training.objective
        if power is not None and objective != "tweedie":
            raise ValueError(
                f"training.tweedie_variance_power {power} is read only under training.objective "
                f"'tweedie'; the objective is {objective!r}: leave the power null in the config "
                "file, or through the audit log set training.tweedie_variance_power to null first"
            )
        return self

    @model_validator(mode="after")
    def _check_deviance_has_a_log_link(self) -> "UseCaseConfig":
        """A deviance metric needs an objective fitted on the log scale: under an identity link
        a prediction can be zero or negative, where the deviance is not defined, so the run
        would stop mid-search on whatever data first produces one."""
        metric, objective = self.decision.metric, self.training.objective
        if metric in DEVIANCE_METRICS and objective not in LOG_LINK_OBJECTIVES:
            raise ValueError(
                f"decision.metric {metric!r} needs a training.objective of "
                f"{' or '.join(LOG_LINK_OBJECTIVES)}, whose predictions are always positive; "
                f"under {objective!r} a prediction can be zero or negative, where the deviance "
                "is not defined. Set the objective, or judge by rmse or mae"
            )
        return self

    @model_validator(mode="after")
    def _check_snapshot_in_window(self) -> "UseCaseConfig":
        """`eda.snapshot` is `last` or a period inside the observation window, by period index
        (T19); a date moves to its period's end under the typo rule, like the window's bounds."""
        if self.eda.snapshot == "last":
            return self
        spec, window = PERIODS[self.time.period], self.time.observation_window
        snapshot = _accepted_period_end(self.eda.snapshot, self.time.period, "eda.snapshot")
        if not spec.index(window.first) <= spec.index(snapshot) <= spec.index(window.last):
            raise ValueError(
                f"eda.snapshot {spec.label(snapshot)} is outside the observation window "
                f"{spec.label(window.first)} … {spec.label(window.last)}; name a period inside "
                "it, or `last` for the window's last period"
            )
        self.eda.snapshot = snapshot
        return self

    @model_validator(mode="after")
    def _check_sampling_suits_task(self) -> "UseCaseConfig":
        """`negative_downsampling` keeps the positives of a binary target; regression has none."""
        sampling = self.training.sampling
        if self.task != "binary" and sampling and sampling.method == "negative_downsampling":
            raise ValueError(
                f"training.sampling.method 'negative_downsampling' needs a binary target; task "
                f"{self.task!r} samples clients (client_sample, D-117)"
            )
        return self

    @field_validator("use_case")
    @classmethod
    def _check_use_case_name(cls, value: str) -> str:
        """Letters, digits, underscores and hyphens, a letter or digit first, in any case."""
        if not re.fullmatch(USE_CASE_PATTERN, value):
            raise ValueError(
                f"use_case {value!r} may hold only letters, digits, underscores and hyphens, a "
                "letter or digit first, since it names folders and the column "
                "target_<use_case>, both compared ignoring case; e.g. 'cc_acquisition' or "
                "'fx-activation'"
            )
        return value


def _fill_task_nulls(cfg: UseCaseConfig) -> dict[str, object]:
    """Fill, in place and in this order, the null `decision.metric` (by the decision type), the
    null `training.objective`, the null `training.tweedie_variance_power` under `tweedie` and the
    null `training.calibration.method` (the decision's entry, else the objective's, else the
    task's default), from `TASK_CHOICES`; returns path → value filled."""
    choices, decision, training = TASK_CHOICES[cfg.task], cfg.decision, cfg.training
    filled: dict[str, object] = {}
    if decision.metric is None:
        decision.metric = choices["metric_by_decision"][decision.type]
        filled["decision.metric"] = decision.metric
    if training.objective is None:
        training.objective = choices["objective_default"]
        filled["training.objective"] = training.objective
    if training.tweedie_variance_power is None and training.objective == "tweedie":
        training.tweedie_variance_power = TWEEDIE_VARIANCE_POWER
        filled["training.tweedie_variance_power"] = TWEEDIE_VARIANCE_POWER
    if training.calibration.method is None:
        training.calibration.method = (
            choices["calibration_by_decision"].get(decision.type)
            or choices["calibration_by_objective"].get(training.objective)
            or choices["calibration_default"]
        )
        filled["training.calibration.method"] = training.calibration.method
    return filled


def snapshot_period(cfg: UseCaseConfig) -> date:
    """The period EDA collects whole, as its last day: `eda.snapshot`, `last` being the window's
    last period (a date was checked at load to lie inside the window)."""
    if cfg.eda.snapshot == "last":
        return cfg.time.observation_window.last
    return cfg.eda.snapshot
