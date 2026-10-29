"""The use-case config schema: one Pydantic model per section of the YAML (D-129).

The config is the use case's intent, validated at load and frozen once the target is built
(D-125). Every model forbids unknown keys, so a misspelt or retired field fails naming the key.
Fields the automation level fills (`levels.py`) have no default here: a dict that skipped
`apply_level_defaults` fails loud instead of carrying None. Values that an audit-log replay writes
(`features.excluded`, `features.kept_despite_flags`, `housekeeping`) are empty in a config file, so
the resolved config validates with this same schema (D-125). A period (the unit of analysis,
`time.period`) is held as its last day, the framework's one convention; a config may write it as
any day the period spec accepts (a month: its first or its last day, D-129).
"""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from core_modelling.periods import PERIODS

# FLAML's own metric names (T9): `ap`, not `average_precision`.
FLAML_METRICS = {
    "roc_auc", "ap", "log_loss", "f1", "accuracy", "macro_f1", "micro_f1",
    "r2", "rmse", "mae", "mse", "mape",
}  # fmt: skip
Estimator = Literal["lgbm", "xgboost", "catboost"]  # the three families; the forests never (D-037)
USE_CASE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"


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


def _check_metric(value: str | None) -> str | None:
    """Refuse a metric name FLAML does not know (T9)."""
    if value is not None and value not in FLAML_METRICS:
        raise ValueError(
            f"{value!r} is not a FLAML metric name; use one of {sorted(FLAML_METRICS)} "
            "(FLAML says 'ap', not 'average_precision'; T9)"
        )
    return value


Metric = Annotated[str | None, AfterValidator(_check_metric)]


class Decision(StrictModel):
    """How the scores are used; declared before any result and never loggable (§4.3)."""

    type: Literal["top_n", "threshold", "ranking", "probability"]
    n: int | None = Field(default=None, ge=1)
    metric: Metric = None
    gate_metric: Metric = None
    baselines: list[
        Literal["population_base_rate", "previous_model", "historic_predicted_rate"]
    ] = Field(default=["population_base_rate"], min_length=1)

    @model_validator(mode="after")
    def _check_top_n_has_n(self) -> "Decision":
        """A top-N decision needs the list size."""
        if self.type == "top_n" and self.n is None:
            raise ValueError("decision.type 'top_n' needs decision.n (the list size)")
        return self


class Sources(StrictModel):
    """An entity's logical sources: the first feature source is the governing spine."""

    features: list[str] = Field(min_length=1)
    targets: str | None = None


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


class Time(StrictModel):
    """The unit of analysis, the observation window, the target window `w` (periods t+1 … t+w)
    and the validation period; the three dates are held as their period's last day."""

    period: Literal["month", "week", "day"] = "month"
    observation_window: ObservationWindow
    target_window: int = Field(ge=1)
    validation_period: date

    @model_validator(mode="after")
    def _move_to_period_end(self) -> "Time":
        """The typo rule: a date the period may not be written as (a month: a day that is neither
        its first nor its last) is refused; the accepted dates move to their period's end."""
        spec = PERIODS[self.period]
        window = self.observation_window
        for path, value in (
            ("observation_window.first", window.first),
            ("observation_window.last", window.last),
            ("validation_period", self.validation_period),
        ):
            if not spec.accept(value):
                raise ValueError(
                    f"time.{path} {value} must be the first or the last day of a {self.period}, "
                    f"e.g. {spec.end(value)}"
                )
        window.first, window.last = spec.end(window.first), spec.end(window.last)
        self.validation_period = spec.end(self.validation_period)
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
        in periods by the spec's index."""
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
    """The candidates; the two lists are written by the audit log's replay, empty in a file."""

    candidates: Candidates = Candidates()
    excluded: list[str] = []
    kept_despite_flags: list[str] = []


class Strata(StrictModel):
    """Stratification variables shared by EDA, Evaluation and Monitoring (D-038)."""

    variables: list[str]
    max_levels: int = Field(default=10, ge=2)
    min_events: int = Field(default=50, ge=1)


class KeyFeatures(StrictModel):
    """EDA's key features: the top-N by univariate ranking plus the listed ones."""

    top_n: int = Field(ge=0)
    include: list[str] = []


class Eda(StrictModel):
    """EDA's knobs."""

    key_features: KeyFeatures
    chart_sample_share: float | None = Field(default=None, gt=0, le=1)


class CheckStep(StrictModel):
    """One ordered Feature Checks step: flags and logs, never drops (§4.6)."""

    name: str
    params: dict[str, object] = {}


DEFAULT_CHECK_STEPS = [
    CheckStep(name="quality"),
    CheckStep(name="leakage"),
    CheckStep(name="time_alignment"),
    CheckStep(name="eligibility_constant"),
    CheckStep(name="stability", params={"psi_max": 0.25}),
    CheckStep(name="redundancy"),
]


class FeatureChecks(StrictModel):
    """The ordered check steps and their thresholds."""

    steps: Annotated[list[CheckStep], AfterValidator(_unique_names)] = DEFAULT_CHECK_STEPS


class Selection(StrictModel):
    """Automated feature selection by rule, on the train split only; the floor's statistic comes
    from the per-task spec (binary: univariate AUC)."""

    univariate_floor: float = Field(default=0.515, ge=0.5, le=1)
    importance_floor: float | None = Field(default=None, ge=0)


class Categoricals(StrictModel):
    """Rarer and unseen levels map to `__other__` (D-037)."""

    min_level_count: int = Field(default=50, ge=1)


class Calibration(StrictModel):
    """The calibration step, fitted out-of-fold inside train (D-049)."""

    method: Literal["platt", "isotonic", "none"] = "platt"


class Sampling(StrictModel):
    """Train-only sampling, declared by a person (D-117): one method with its one parameter."""

    method: Literal["negative_downsampling", "client_sample"]
    seed: int = 42
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
    """The modelling path, model families, budgets, seeds, selection, calibration, sampling."""

    path: Literal["automl"] = "automl"
    estimator_list: list[Estimator] = Field(default=["lgbm", "xgboost", "catboost"], min_length=1)
    max_iter: int = Field(ge=1)
    time_budget_s: int | None = Field(default=None, ge=1)
    seed: int = 42
    search_space: dict[str, dict[str, object]] = {}
    selection: Selection = Selection()
    categoricals: Categoricals = Categoricals()
    calibration: Calibration = Calibration()
    sampling: Sampling | None = None


class Slices(StrictModel):
    """Metric slices at the top of the score ranking; either list may be empty."""

    top_pct: list[Annotated[float, Field(gt=0, le=1)]]
    top_n: list[Annotated[int, Field(ge=1)]] = []


class Evaluation(StrictModel):
    """Metric slices and the extended views to add (the core views always render)."""

    slices: Slices
    views: list[str] = []


class PromotionGate(StrictModel):
    """The gate metric's minimum; null until the lifecycle stage is built."""

    min: float | None = None


class Lifecycle(StrictModel):
    """register and promote settings."""

    promotion_gate: PromotionGate = PromotionGate()


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
    eda: Eda
    feature_checks: FeatureChecks = FeatureChecks()
    training: Training
    evaluation: Evaluation
    lifecycle: Lifecycle = Lifecycle()
    inference: Inference = Inference()
    monitoring: Monitoring = Monitoring()
    housekeeping: dict[str, object] | None = None

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
