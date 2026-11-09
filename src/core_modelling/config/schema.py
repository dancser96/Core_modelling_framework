"""The use-case config schema: one Pydantic model per section of the YAML (D-129).

The config is the use case's intent, validated at load and frozen once the target is built
(D-125). Every model forbids unknown keys, so a misspelt or retired field fails naming the key.
Fields the automation level fills (`levels.py`) have no default here: a dict that skipped
`apply_level_defaults` fails loud instead of carrying None. Values that an audit-log replay writes
(`features.excluded`, `features.kept`, `features.held`, `housekeeping`) are empty in a config file,
so the resolved config validates with this same schema (D-125, D-134). A period (the unit of
analysis, `time.period`) is held as its last day, the framework's one convention; a config may
write it as any day the period spec accepts (a month: its first or its last day, D-129). The
Stage 2 fields (`eda`, `feature_checks`, `features.kinds`) changed in place, with no schema bump
and no migration (D-136).
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


Name = Annotated[str, Field(pattern=r"^\s*\S")]  # a source or column name: not empty or blank


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
    the candidates are patterns until then). `excluded`, `kept` and `held` are written by the
    audit log's replay and empty in a file; for Training a held feature acts as an excluded
    feature without a final decision (D-134)."""

    candidates: Candidates = Candidates()
    kinds: dict[str, Literal["numeric", "categorical"]] = {}
    excluded: list[str] = []
    kept: list[str] = []
    held: list[str] = []


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
    feature does not flag a strong one.
    """

    psi_note_min: float = Field(default=0.10, gt=0)
    psi_max: float = Field(default=0.25, gt=0)
    heterogeneity_p_max: float = Field(default=0.01, gt=0, lt=1)
    concordance_range_min: float = Field(default=0.5, ge=0, le=2)
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
    eda: Eda = Eda()
    feature_checks: FeatureChecks = EVERY_CHECK
    training: Training
    evaluation: Evaluation
    lifecycle: Lifecycle = Lifecycle()
    inference: Inference = Inference()
    monitoring: Monitoring = Monitoring()
    housekeeping: dict[str, object] | None = None

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


def snapshot_period(cfg: UseCaseConfig) -> date:
    """The period EDA collects whole, as its last day: `eda.snapshot`, `last` being the window's
    last period (a date was checked at load to lie inside the window)."""
    if cfg.eda.snapshot == "last":
        return cfg.time.observation_window.last
    return cfg.eda.snapshot
