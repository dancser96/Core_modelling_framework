"""The panel: sources joined to the spine, eligibility in two kinds, the candidates (D-129).

Hand-made sources written to parquet check the join (a left-join miss, a shared column, a spine
with a gap, a target source that matches nothing) and the join log. Eligibility runs on a
hand-made keyed panel: a define reused by a filter and dropped, a `before: eda` filter dropping
rows, a `before: model` filter tagging them, a null condition counting as false, and the
references a condition may not make (§4.9; the keys, the target, another filter's tag).
"""

from collections.abc import Callable
from datetime import date

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import EligibilityStep
from core_modelling.dataset.panel import apply_eligibility, load_panel, resolve_candidates
from core_modelling.environment import EnvironmentConfig

# Window 2024-11 … 2024-12, v = 2025-03, w = 3: the target source needs 2024-11 … 2025-06.
TIME = {
    "train_months": {"first": date(2024, 11, 1), "last": date(2024, 12, 1)},
    "validation_month": date(2025, 3, 1),
    "target_window_months": 3,
}
MONTHS = [
    date(2024, 11, 30), date(2024, 12, 31), date(2025, 1, 31), date(2025, 2, 28),
    date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31), date(2025, 6, 30),
]  # fmt: skip
SPINE = "unit_id string, month date, income double, cc_flag int, segment string"


def _spine(spark: SparkSession, units: dict[str, tuple], months: list[date] = MONTHS) -> DataFrame:
    """A keyed spine: per unit the same (income, cc_flag, segment) in every month."""
    rows = [(unit, month, *values) for unit, values in units.items() for month in months]
    return spark.createDataFrame(rows, SPINE)


def _flags(spark: SparkSession, units: dict[str, list[int]]) -> DataFrame:
    """A keyed target source: per unit a `value` flag month by month from `MONTHS[0]`."""
    rows = [
        (unit, MONTHS[i], flag) for unit, flags in units.items() for i, flag in enumerate(flags)
    ]
    return spark.createDataFrame(rows, "unit_id string, month date, value int")


def _config(variant: Callable[..., UseCaseConfig], **data: object) -> UseCaseConfig:
    """The skeleton's config on the hand-made sources: the mart and `extra` as features, the
    flag source as targets, no eligibility unless given."""
    sources = {"features": ["retail_mart", "extra"], "targets": "retail_holdings"}
    return variant(
        time=TIME,
        entities={"entity_a": {"sources": sources}},
        data={"eligibility": [], "target": {"column": "value"}, "model_input": None, **data},
    )


@pytest.fixture
def sources(spark: SparkSession) -> dict[str, DataFrame]:
    """Three units on the spine; `extra` lacks unit c; a holds the flag from month 2, b always,
    c never."""
    spine = _spine(spark, {"a": (1000.0, 0, "x"), "b": (None, 1, "y"), "c": (50.0, 0, "x")})
    extra = spark.createDataFrame(
        [(u, m, 0.5) for u in ("a", "b") for m in MONTHS],
        "unit_id string, month date, score double",
    )
    flags = _flags(spark, {"a": [0, 0, 1, 1, 1, 1, 1, 1], "b": [1] * 8, "c": [0] * 8})
    return {"retail_mart": spine, "extra": extra, "retail_holdings": flags}


def test_panel_joins_the_sources_and_targets_to_the_spine(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """The spine's columns, the joined source's, `target` and `null_in_window`; months from the
    window's first to the spine's last; a join miss is null; the log has one entry per source."""
    env = write_sources(sources)
    panel, log = load_panel(_config(variant), "entity_a", env, spark)
    assert panel.columns == [
        "unit_id", "month", "income", "cc_flag", "segment", "score", "target", "null_in_window"
    ]  # fmt: skip
    rows = {(r.unit_id, r.month): r for r in panel.collect()}
    assert sorted({m for _, m in rows}) == MONTHS
    assert rows[("c", MONTHS[0])].score is None  # not in `extra`
    assert [rows[("a", m)].target for m in MONTHS[:3]] == [1, 1, 0]
    assert [entry["source"] for entry in log] == ["retail_mart", "extra", "retail_holdings"]
    assert [entry["role"] for entry in log] == ["spine", "joined", "targets"]
    assert log[0]["rows"]["2024-11"] == 3
    assert log[1]["matched_share"] == pytest.approx(2 / 3) and log[1]["matched"]["2025-06"] == 2
    assert log[2]["matched_share"] == 1


def test_panel_keeps_months_from_the_window_only(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A spine month before the window's first is left out."""
    earlier = _spine(spark, {"a": (1.0, 0, "x")}, [date(2024, 10, 31)])
    sources["retail_mart"] = sources["retail_mart"].unionByName(earlier)
    env = write_sources(sources)
    panel, _ = load_panel(_config(variant), "entity_a", env, spark)
    assert panel.agg(F.min("month")).collect()[0][0] == MONTHS[0]


def test_shared_feature_column_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A non-key column in two feature sources fails naming the source and the column."""
    sources["extra"] = sources["extra"].withColumn("income", F.lit(1.0))
    env = write_sources(sources)
    with pytest.raises(ValueError, match=r"'extra' shares the columns \['income'\]"):
        load_panel(_config(variant), "entity_a", env, spark)


def test_spine_with_a_gap_before_the_validation_month_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """The spine needs every month from the window's first to the validation month."""
    sources["retail_mart"] = sources["retail_mart"].where(F.col("month") != MONTHS[2])
    env = write_sources(sources)
    with pytest.raises(ValueError, match=r"spine 'retail_mart' lacks the months \['2025-01'\]"):
        load_panel(_config(variant), "entity_a", env, spark)


def test_target_source_matching_no_spine_row_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """Keys that never meet (other unit ids) give no target in the window: loud, never a panel
    of null targets."""
    sources["retail_holdings"] = _flags(spark, {"A": [0, 0, 1, 1, 1, 1, 1, 1]})
    env = write_sources(sources)
    with pytest.raises(ValueError, match=r"no known target in the window's months \['2024-11'"):
        load_panel(_config(variant), "entity_a", env, spark)


def test_replayed_feature_names_must_be_columns(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A name in `features.excluded` that no source has fails loud (a typo would exclude
    nothing)."""
    env = write_sources(sources)
    cfg = _config(variant).model_copy(deep=True)
    cfg.features.excluded = ["incom"]
    with pytest.raises(ValueError, match=r"features.excluded names columns .* \['incom'\]"):
        load_panel(cfg, "entity_a", env, spark)


def _steps(*entries: dict) -> list[EligibilityStep]:
    """Eligibility steps from dicts."""
    return [EligibilityStep.model_validate(entry) for entry in entries]


@pytest.fixture
def keyed_panel(spark: SparkSession) -> DataFrame:
    """Four units over two months with a target: a has an income and no card, b a card, c no
    income and a card, d no income and a null card flag (segment x keeps d past `known`)."""
    units = {
        "a": (1000.0, 0, "x"),
        "b": (2000.0, 1, "y"),
        "c": (None, 1, "x"),
        "d": (None, None, "x"),
    }
    spine = _spine(spark, units, MONTHS[:2])
    return spine.withColumn("target", F.lit(0)).withColumn("null_in_window", F.lit(False))


def test_eligibility_defines_drops_and_tags(keyed_panel: DataFrame) -> None:
    """A define is reused by a filter and dropped; a `before: eda` filter drops its rows with the
    log; a `before: model` filter tags them, a null condition tagging 0; `eligible` follows the
    tags."""
    steps = _steps(
        {"name": "has_income", "define": "income IS NOT NULL"},
        {"name": "known", "filter": "has_income OR segment = 'x'", "reason": "r", "before": "eda"},
        {"name": "non_holders", "filter": "cc_flag = 0", "reason": "r2", "before": "model"},
    )
    panel, log = apply_eligibility(keyed_panel, steps)
    assert panel.columns == [*keyed_panel.columns, "non_holders", "eligible"]
    rows = {r.unit_id: r for r in panel.where(F.col("month") == MONTHS[0]).collect()}
    assert sorted(rows) == ["a", "b", "c", "d"]
    assert {u: r.non_holders for u, r in rows.items()} == {"a": 1, "b": 0, "c": 0, "d": 0}
    assert {u: r.eligible for u, r in rows.items()} == {"a": 1, "b": 0, "c": 0, "d": 0}
    assert [entry["step"] for entry in log] == ["eligibility", "eligibility"]
    assert [entry["name"] for entry in log] == ["known", "non_holders"]
    assert log[0]["before"] == "eda" and log[0]["rows"] == {"2024-11": 4, "2024-12": 4}
    assert log[0]["rows_out"] == {"2024-11": 4, "2024-12": 4} and log[0]["reason"] == "r"
    assert log[0]["null_condition"] == {"2024-11": 0, "2024-12": 0}
    assert log[1]["before"] == "model" and log[1]["tagged_1"] == {"2024-11": 1, "2024-12": 1}
    assert log[1]["null_condition"] == {"2024-11": 1, "2024-12": 1}  # d: cc_flag null


def test_eligible_is_1_everywhere_without_pre_model_filters(keyed_panel: DataFrame) -> None:
    """With no `before: model` filter every remaining row is eligible."""
    panel, log = apply_eligibility(keyed_panel, [])
    assert panel.columns == [*keyed_panel.columns, "eligible"]
    assert panel.agg(F.min("eligible")).collect()[0][0] == 1 and log == []


@pytest.mark.parametrize(
    "condition",
    ["target = 1", "month > date '2024-11-30'", "unit_id = 'a'", "non_holders = 1", "eligible = 1",
     "null_in_window"],
    ids=["target", "month", "unit_id", "another tag", "eligible", "null_in_window"],
)  # fmt: skip
def test_condition_may_reference_source_columns_and_defines_only(
    keyed_panel: DataFrame, condition: str
) -> None:
    """The keys, the target, the helper columns and another filter's tag are refused in a
    condition, naming the step (eligibility SQL is a leakage surface outside the screens)."""
    steps = _steps(
        {"name": "non_holders", "filter": "cc_flag = 0", "reason": "r", "before": "model"},
        {"name": "bad", "filter": condition, "reason": "r", "before": "eda"},
    )
    with pytest.raises(ValueError, match="eligibility step 'bad'.*sources' columns"):
        apply_eligibility(keyed_panel, steps)


def test_condition_must_be_boolean_and_step_names_must_be_new(keyed_panel: DataFrame) -> None:
    """A non-boolean expression, a step named like a column and a step named like a column the
    dataset adds (`split`, `eligible`) all fail naming the step."""
    with pytest.raises(TypeError, match="eligibility step 'rich': 'income' is double, not a bool"):
        apply_eligibility(keyed_panel, _steps({"name": "rich", "define": "income"}))
    for name in ("income", "split", "eligible"):
        steps = _steps({"name": name, "filter": "income > 0", "reason": "r", "before": "eda"})
        with pytest.raises(ValueError, match=f"step '{name}' is named like a column"):
            apply_eligibility(keyed_panel, steps)


@pytest.mark.parametrize(
    "sql, what",
    [("hash(*) % 2 = 0", "a star"), ("income > (SELECT 1)", "a subquery"),
     ("income > avg(income) OVER ()", "a window")],
    ids=["star", "subquery", "window"],
)  # fmt: skip
def test_condition_is_a_plain_expression(keyed_panel: DataFrame, sql: str, what: str) -> None:
    """A star in a call, a subquery and a window function are refused before Spark sees them:
    each could read beyond the row's own source columns."""
    steps = _steps({"name": "odd", "define": sql})
    with pytest.raises(ValueError, match=f"eligibility step 'odd': .* holds {what}"):
        apply_eligibility(keyed_panel, steps)


def test_candidates_follow_the_patterns_minus_the_reserved_names(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """Include then exclude patterns over the columns, minus the keys, the helper columns, the
    lineage and the eligibility steps' names; no candidate left fails loud."""
    cfg = _config(
        variant,
        eligibility=[
            {"name": "has_income", "define": "income IS NOT NULL"},
            {"name": "non_holders", "filter": "cc_flag = 0", "reason": "r", "before": "model"},
        ],
    )
    columns = ["unit_id", "month", "income", "cc_flag", "segment", "score", "x_trap",
               "non_holders", "eligible", "target", "null_in_window", "split"]  # fmt: skip
    assert resolve_candidates(columns, cfg, ["cc_flag"]) == ["income", "segment", "score", "x_trap"]
    patterns = variant(features={"candidates": {"include": ["s*"], "exclude": ["*_trap"]}})
    assert resolve_candidates(columns, patterns, ["cc_flag"]) == ["segment", "score"]
    with pytest.raises(ValueError, match=r"matches none of \[\]; never candidates: .*'cc_flag'"):
        resolve_candidates(["unit_id", "month", "cc_flag", "target"], cfg, ["cc_flag"])
