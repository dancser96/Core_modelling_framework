"""The panel: sources joined to the spine with one target column per use case, the preparation
for one config, eligibility in two kinds, the candidates (D-129, D-131; the addendum's B).

Hand-made sources written to parquet check the join (a left-join miss, a shared column, a spine
with a gap, a feature or a target source that matches nothing, a target column colliding with a
source column), the join log and the meta; two configs on the same sources give two labelled
target columns, each prepared panel keeps its own as `target` and never lists the other's target
or upstream source column as a candidate, each window is checked for labels on its own, and
configs differing in a shared field are refused naming the use cases and the field. Source
columns named `target`, `split`, `eligible` are read as `source_<name>`; an upstream target
column in the panel, even one named `target`, is the label and never a column of the prepared
panel; `read_side_columns` plans the drops and renames without Spark.
Eligibility runs on a hand-made keyed panel: a define reused by a filter and dropped, an
analysis filter dropping rows, a modelling filter tagging them, a null condition counting as
false, and the references a condition may not make (§4.9; the keys, the target, another
filter's tag).
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import Eligibility
from core_modelling.dataset.eligibility import apply_eligibility, modelling_tags, resolve_candidates
from core_modelling.dataset.panel import (
    DROP_REASONS,
    PANEL_META_KEYS,
    build_panel,
    load_panel,
    prepare_panel,
    read_side_columns,
    target_column,
)
from core_modelling.environment import EnvironmentConfig, Source
from core_modelling.periods import PERIODS

MONTH = PERIODS["month"]
# Window 2024-11 … 2024-12, v = 2025-03, w = 3: the target source needs 2024-11 … 2025-06.
TIME = {
    "observation_window": {"first": date(2024, 11, 1), "last": date(2024, 12, 1)},
    "validation_period": date(2025, 3, 1),
    "target_window": 3,
}
MONTHS = [
    date(2024, 11, 30), date(2024, 12, 31), date(2025, 1, 31), date(2025, 2, 28),
    date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31), date(2025, 6, 30),
]  # fmt: skip
SPINE = "unit_id string, period date, income double, cc_flag int, segment string"
OWN, OTHER = "cc_acquisition", "cc_retention"  # the skeleton's use case and a second one
EMPTY = {"analysis": [], "modelling": []}  # no eligibility (the variant merges a nested dict)
KEYS_AND_CANDIDATES = ["unit_id", "period", "income", "cc_flag", "segment", "score"]
ONE_SOURCE = {"sources": {"features": ["retail_mart"], "targets": "retail_holdings"}}


def _spine(spark: SparkSession, units: dict[str, tuple], months: list[date] = MONTHS) -> DataFrame:
    """A keyed spine: per unit the same (income, cc_flag, segment) in every month."""
    rows = [(unit, month, *values) for unit, values in units.items() for month in months]
    return spark.createDataFrame(rows, SPINE)


def _flags(spark: SparkSession, units: dict[str, list[int]]) -> DataFrame:
    """A keyed target source: per unit a `value` flag month by month from `MONTHS[0]`."""
    rows = [
        (unit, MONTHS[i], flag) for unit, flags in units.items() for i, flag in enumerate(flags)
    ]
    return spark.createDataFrame(rows, "unit_id string, period date, value int")


def _config(variant: Callable[..., UseCaseConfig], **data: object) -> UseCaseConfig:
    """The skeleton's config on the hand-made sources: the mart and `extra` as features, the
    flag source as targets, no eligibility unless given."""
    sources = {"features": ["retail_mart", "extra"], "targets": "retail_holdings"}
    return variant(
        time=TIME,
        entities={"entity_a": {"sources": sources}},
        data={"eligibility": EMPTY, "target": {"column": "value"}, "model_input": None, **data},
    )


def _other(variant: Callable[..., UseCaseConfig], **sections: object) -> UseCaseConfig:
    """A second use case on the same sources with a target window of 2 (another target spec),
    plus any section changed."""
    cfg = _config(variant).model_dump()
    cfg["use_case"], cfg["time"]["target_window"] = OTHER, 2
    for name, change in sections.items():
        cfg[name] = {**cfg[name], **change}
    return UseCaseConfig.model_validate(cfg)


@pytest.fixture
def sources(spark: SparkSession) -> dict[str, DataFrame]:
    """Three units on the spine; `extra` lacks unit c; a holds the flag from month 2, b always,
    c never."""
    spine = _spine(spark, {"a": (1000.0, 0, "x"), "b": (None, 1, "y"), "c": (50.0, 0, "x")})
    extra = spark.createDataFrame(
        [(u, m, 0.5) for u in ("a", "b") for m in MONTHS],
        "unit_id string, period date, score double",
    )
    flags = _flags(spark, {"a": [0, 0, 1, 1, 1, 1, 1, 1], "b": [1] * 8, "c": [0] * 8})
    return {"retail_mart": spine, "extra": extra, "retail_holdings": flags}


def test_panel_joins_the_sources_and_targets_to_the_spine(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """The spine's columns, the joined source's and `target_<use_case>`, nothing else; periods
    from the window's first to the spine's last; a join miss is null; the log has one entry per
    source; the meta holds the join definition and the use case's target."""
    env = write_sources(sources)
    panel, log, meta = load_panel([_config(variant)], "entity_a", env, spark)
    assert panel.columns == [
        "unit_id", "period", "income", "cc_flag", "segment", "score", "target_cc_acquisition"
    ]  # fmt: skip
    rows = {(r.unit_id, r.period): r for r in panel.collect()}
    assert sorted({p for _, p in rows}) == MONTHS
    assert rows[("c", MONTHS[0])].score is None  # not in `extra`
    assert [rows[("a", m)].target_cc_acquisition for m in MONTHS[:3]] == [1, 1, 0]
    assert [entry["source"] for entry in log] == ["retail_mart", "extra", "retail_holdings"]
    assert [entry["role"] for entry in log] == ["spine", "joined", "targets"]
    assert log[0]["rows"]["2024-11"] == 3 and log[0]["period_tag"] == "period end"
    assert log[1]["matched_share"] == pytest.approx(2 / 3) and log[1]["matched"]["2025-06"] == 2
    assert log[2]["matched_share"] == 1 and log[2]["use_case"] == OWN
    assert (
        log[2]["null_in_window"]["2024-11"] == 0.0 and log[2]["null_in_window"]["2025-06"] is None
    )
    assert meta["sources"] == {"features": ["retail_mart", "extra"]} and meta["period"] == "month"
    assert meta["keys"] == {"unit_id": "client_id", "period": "snapshot_month"}
    assert meta["periods"] == {"first": "2024-11", "last": "2025-06"}
    target = meta["targets"][OWN]
    assert target["column"] == "target_cc_acquisition" and target["source"] == "retail_holdings"
    assert target["lineage"] == ["value"] and target["target_window"] == 3
    assert target["observation_window"] == {"first": "2024-11", "last": "2024-12"}
    assert target["validation_period"] == "2025-03" and target["null_in_window_share"] == 0.0


def test_two_configs_give_two_target_columns_each_prepared_for_its_own(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """Two use cases on the same sources: one column per target, both in the log and the meta;
    each prepared panel keeps its own target as `target`, drops the other and never lists it
    as a candidate even with `include: ["*"]` (§4.6); an unsaved use case is refused. The second
    name has a hyphen and upper case: its column is lower-cased, its meta key kept as written."""
    env = write_sources(sources)
    mixed = "cc-Retention"
    own = _config(variant)
    other = UseCaseConfig.model_validate({**_other(variant).model_dump(), "use_case": mixed})
    panel, log, meta = load_panel([own, other], "entity_a", env, spark)
    assert panel.columns[-2:] == ["target_cc_acquisition", "target_cc-retention"]
    assert [entry["role"] for entry in log] == ["spine", "joined", "targets", "targets"]
    assert set(meta["targets"]) == {OWN, mixed}
    rows = {r.unit_id: r for r in panel.where(F.col("period") == MONTHS[0]).collect()}
    assert rows["a"]["target_cc_acquisition"] == 1 and rows["a"]["target_cc-retention"] == 1
    for cfg, dropped in ((own, mixed), (other, OWN)):
        assert cfg.features.candidates.include == ["*"]
        prepared, prepared_log, prepared_meta = prepare_panel(
            panel, cfg, "entity_a", meta["targets"]
        )
        assert target_column(dropped) not in prepared.columns
        assert prepared_meta["candidates"] == ["income", "cc_flag", "segment", "score"]
        assert prepared.columns == [*KEYS_AND_CANDIDATES, "eligible", "target", "split"]
        assert [entry["step"] for entry in prepared_log][:2] == ["drop", "contract"]
        assert prepared_log[0]["dropped"] == {target_column(dropped): "another use case's target"}
    unsaved = _other(variant)
    unsaved = unsaved.model_copy(update={"use_case": "fx_activation"})
    with pytest.raises(ValueError, match=r"no target for use case 'fx_activation'; its use cases"):
        prepare_panel(panel, unsaved, "entity_a", meta["targets"])


@pytest.mark.parametrize(
    "change, field",
    [
        ({"entities": {"entity_a": ONE_SOURCE}}, "sources.features"),
        ({"data": {"keys": {"unit_id": "customer_id", "period": "snapshot_month"}}}, "keys"),
        ({"data": {"model_input": "other_input"}}, "model_input"),
        ({"time": {"period": "week"}}, "time.period"),
    ],
    ids=["sources", "keys", "model_input", "period"],
)
def test_configs_must_share_the_data_definition(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
    change: dict,
    field: str,
) -> None:
    """Configs differing in the feature sources, the keys, the model input or the period fail
    naming the two use cases and the field, before any source is read; so do repeated use cases,
    also when they differ only in case (Spark column names are case-insensitive)."""
    env = write_sources(sources)
    other = _other(variant, **change)
    with pytest.raises(ValueError, match=f"'cc_acquisition' and 'cc_retention' differ in {field}"):
        load_panel([_config(variant), other], "entity_a", env, spark)
    with pytest.raises(ValueError, match=r"distinct ignoring case .*repeated: \['cc_acquisition'"):
        load_panel([_config(variant), _config(variant)], "entity_a", env, spark)
    upper = _config(variant).model_copy(update={"use_case": "CC_Acquisition"})
    with pytest.raises(
        ValueError,
        match=r"distinct ignoring case .*repeated: \['CC_Acquisition', 'cc_acquisition'\]",
    ):
        load_panel([_config(variant), upper], "entity_a", env, spark)


def test_target_column_colliding_with_a_source_column_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A source carrying a column named `target_<use_case>` fails naming the use case."""
    sources["extra"] = sources["extra"].withColumn(target_column(OWN), F.lit(1))
    env = write_sources(sources)
    with pytest.raises(ValueError, match="'target_cc_acquisition' of use case 'cc_acquisition' is"):
        load_panel([_config(variant)], "entity_a", env, spark)


def test_panel_keeps_periods_from_the_window_only(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A spine period before the window's first is left out."""
    earlier = _spine(spark, {"a": (1.0, 0, "x")}, [date(2024, 10, 31)])
    sources["retail_mart"] = sources["retail_mart"].unionByName(earlier)
    env = write_sources(sources)
    panel, _, _ = load_panel([_config(variant)], "entity_a", env, spark)
    assert panel.agg(F.min("period")).collect()[0][0] == MONTHS[0]


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
        load_panel([_config(variant)], "entity_a", env, spark)


def test_spine_with_a_gap_before_the_validation_period_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """The spine needs every period from the window's first to the validation period."""
    sources["retail_mart"] = sources["retail_mart"].where(F.col("period") != MONTHS[2])
    env = write_sources(sources)
    with pytest.raises(ValueError, match=r"spine 'retail_mart' lacks the periods \['2025-01'\]"):
        load_panel([_config(variant)], "entity_a", env, spark)


def test_feature_source_matching_no_spine_row_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A joined feature source whose keys never meet the spine's (here an integer id against a
    string one) is refused naming the source and both id types, never joined as all nulls."""
    sources["extra"] = spark.createDataFrame(
        [(1, m, 0.5) for m in MONTHS], "unit_id int, period date, score double"
    )
    env = write_sources(sources)
    with pytest.raises(
        ValueError,
        match="feature source 'extra' matched no spine row: .* its id is int, the spine's string",
    ):
        load_panel([_config(variant)], "entity_a", env, spark)


def test_target_source_matching_no_spine_row_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """Keys that never meet (other unit ids) give no target in the window: loud, naming the use
    case, never a panel of null targets."""
    sources["retail_holdings"] = _flags(spark, {"A": [0, 0, 1, 1, 1, 1, 1, 1]})
    env = write_sources(sources)
    with pytest.raises(ValueError, match=r"no known target of use case 'cc_acquisition' in the"):
        load_panel([_config(variant)], "entity_a", env, spark)


def test_second_config_window_is_checked_for_labels_on_its_own(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """Each config's observation window is checked against its own target column: the first
    config's window is labelled, the second's (later, from another target source whose unit
    ids never meet the spine's) is refused naming its use case and its periods."""
    sources["other_holdings"] = _flags(spark, {"A": [0] * 8, "B": [1] * 8, "C": [0] * 8})
    env = write_sources(sources)
    features = {"features": ["retail_mart", "extra"], "targets": "other_holdings"}
    later = _other(
        variant,
        time={"observation_window": {"first": date(2024, 12, 1), "last": date(2025, 1, 1)}},
        entities={"entity_a": {"sources": features}},
    )
    with pytest.raises(
        ValueError,
        match=r"of use case 'cc_retention' in the window's periods \['2024-12', '2025-01'\]",
    ):
        load_panel([_config(variant), later], "entity_a", env, spark)


def test_other_use_case_upstream_source_column_is_dropped(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A second use case whose target is the spine's `cc_flag` upstream (no rule): that column
    is forward-looking, so the first use case's prepared panel drops it with the other target
    column; for the second it is the lineage, reserved as ever (§4.6)."""
    units = {"a": (1000.0, 0, "x"), "b": (None, 1, "y"), "c": (50.0, 0, "x")}
    unflagged = {unit: (income, None, segment) for unit, (income, _, segment) in units.items()}
    # No value in the source's last w = 2 periods, where an upstream target can't be known yet.
    sources["retail_mart"] = _spine(spark, units, MONTHS[:6]).unionByName(
        _spine(spark, unflagged, MONTHS[6:])
    )
    env = write_sources(sources)
    features = {"features": ["retail_mart", "extra"], "targets": None}
    upstream = _other(
        variant,
        data={"target": {"column": "cc_flag", "rule": None}},
        entities={"entity_a": {"sources": features}},
    )
    own = _config(variant)
    panel, _, meta = load_panel([own, upstream], "entity_a", env, spark)
    assert meta["targets"][OTHER]["upstream"] and not meta["targets"][OWN]["upstream"]
    assert meta["targets"][OWN]["target_last"] == "2025-06-30"
    prepared, _, prepared_meta = prepare_panel(panel, own, "entity_a", meta["targets"])
    assert "cc_flag" not in prepared.columns and target_column(OTHER) not in prepared.columns
    assert prepared_meta["candidates"] == ["income", "segment", "score"]
    prepared, _, prepared_meta = prepare_panel(panel, upstream, "entity_a", meta["targets"])
    assert "cc_flag" not in prepared.columns and prepared_meta["lineage"] == ["cc_flag"]
    assert prepared_meta["candidates"] == ["income", "segment", "score"]


def test_source_columns_named_like_the_helper_columns_are_read_as_source_columns(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A spine carrying `target`, `split` and `eligible` builds: they come back as
    `source_<name>` with the source's values beside the dataset's own, the first preparation
    entry says so, printed, a filter may name `source_eligible`, and `source_split` is a
    candidate."""
    sources["retail_mart"] = (
        sources["retail_mart"]
        .withColumn("target", F.lit(7))
        .withColumn("split", F.lit("upstream"))
        .withColumn("eligible", F.when(F.col("unit_id") == "c", 0).otherwise(1))
    )
    env = write_sources(sources)
    flagged = {"name": "flagged", "filter": "source_eligible = 1", "reason": "r"}
    cfg = _config(variant, eligibility={"analysis": [flagged], "modelling": []})
    panel, log, meta = build_panel(cfg, "entity_a", env, spark)
    rows = {r.unit_id: r for r in panel.where(F.col("period") == MONTHS[0]).collect()}
    assert sorted(rows) == ["a", "b"]  # c dropped by `source_eligible = 1`
    assert rows["a"].source_target == 7 and rows["a"].target == 1 and rows["b"].target == 0
    assert rows["a"].source_split == "upstream" and rows["a"].split in ("train", "test")
    assert rows["a"].source_eligible == 1 and rows["a"].eligible == 1
    prepared = [entry for entry in log if entry["step"] != "join"]
    renamed = {name: f"source_{name}" for name in ("target", "split", "eligible")}
    assert prepared[0] == {"step": "rename", "renamed": renamed}
    assert "source_split" in meta["candidates"] and "split" not in meta["candidates"]
    out = capsys.readouterr().out
    assert (
        "column 'target' of the sources read as 'source_target' (the dataset adds its own "
        "'target'); if it is a label, list it in data.target.lineage" in out
    )
    assert "column 'split' of the sources read as 'source_split' (the dataset adds its own" in out


def _labelled_spine(spine: DataFrame, column: str) -> DataFrame:
    """The spine with an upstream 0/1 label `column`, unknown in the last w = 3 months, where
    such a target can't be known yet."""
    labels = {"a": [0, 1, 1, 0, 1], "b": [1] * 5, "c": [0] * 5}
    rows = [
        (unit, month, flag)
        for unit, flags in labels.items()
        for month, flag in zip(MONTHS, [*flags, None, None, None], strict=True)
    ]
    frame = spine.sparkSession.createDataFrame(rows, f"unit_id string, period date, {column} int")
    return spine.join(frame, ["unit_id", "period"])


def _upstream(variant: Callable[..., UseCaseConfig], column: str, **data: object) -> UseCaseConfig:
    """The skeleton's config with the spine's `column` as an upstream target (no rule)."""
    features = {"features": ["retail_mart", "extra"], "targets": None}
    target = {"column": column, "rule": None}
    return variant(
        time=TIME,
        entities={"entity_a": {"sources": features}},
        data={"eligibility": EMPTY, "target": target, "model_input": None, **data},
    )


def test_upstream_target_column_named_target_is_the_label(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`data.target.column: target` names the upstream column as the source does: `target`
    holds its values where labelled, and the raw column is dropped, printed and logged, never
    `source_target`."""
    raw = _labelled_spine(sources["retail_mart"], "target")
    sources["retail_mart"] = raw
    env = write_sources(sources)
    panel, log, meta = build_panel(_upstream(variant, "target"), "entity_a", env, spark)
    assert panel.columns == [*KEYS_AND_CANDIDATES, "eligible", "target", "split"]
    assert meta["lineage"] == ["target"] and "rename" not in [entry["step"] for entry in log]
    reason = "this use case's label: its values are `target`'s"
    assert {"step": "drop", "dropped": {"target": reason}} in log
    assert f"column 'target' dropped: {reason}" in capsys.readouterr().out
    expected = {(r.unit_id, r.period): r.target for r in raw.collect()}
    assert {(r.unit_id, r.period): r.target for r in panel.collect()} == expected


def test_eligibility_never_names_the_own_upstream_target_column(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """The own upstream target column is the label (forward-looking): a condition naming it
    fails naming the step (§4.6)."""
    sources["retail_mart"] = _labelled_spine(sources["retail_mart"], "label_fwd")
    env = write_sources(sources)
    peek = {"name": "peek", "filter": "label_fwd = 1", "reason": "r"}
    cfg = _upstream(variant, "label_fwd", eligibility={"analysis": [], "modelling": [peek]})
    with pytest.raises(ValueError, match="eligibility step 'peek'.*sources' columns"):
        build_panel(cfg, "entity_a", env, spark)


def test_built_target_over_a_spine_column_named_target_keeps_it_as_lineage(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """A `flag_goes_up` target over the spine's `target` flag: the flag is read as
    `source_target`, a filter may name it (the holder at t), it is the lineage (under its read
    name) and never a
    candidate even with `include: ["*"]` (§4.6), and the built labels equal those of the same
    flag under another name."""
    flags = sources["retail_holdings"].withColumnRenamed("value", "target")
    sources["carded"] = sources["retail_mart"].join(flags, ["unit_id", "period"])
    env = write_sources(sources)
    holders = {"name": "non_holders", "filter": "source_target = 0", "reason": "r"}
    features = {"features": ["carded", "extra"], "targets": None}
    cfg = variant(
        time=TIME,
        entities={"entity_a": {"sources": features}},
        data={
            "eligibility": {"analysis": [], "modelling": [holders]},
            "target": {"column": "target", "rule": "flag_goes_up"},
            "model_input": None,
        },
    )
    assert cfg.features.candidates.include == ["*"]
    panel, _, meta = build_panel(cfg, "entity_a", env, spark)
    assert meta["lineage"] == ["source_target"]  # the read name, as the frames carry it
    assert meta["candidates"] == ["income", "cc_flag", "segment", "score"]
    rows = {r.unit_id: r for r in panel.where(F.col("period") == MONTHS[0]).collect()}
    assert {u: r.non_holders for u, r in rows.items()} == {"a": 1, "b": 0, "c": 1}
    reference, _, _ = build_panel(_config(variant), "entity_a", env, spark)
    labels = {(r.unit_id, r.period): r.target for r in reference.collect()}
    assert {(r.unit_id, r.period): r.target for r in panel.collect()} == labels


def _target_meta_of(column: str, upstream: bool, label: str, source: str) -> dict:
    """A use case's target as the meta records it: the fields `read_side_columns` reads."""
    return {"column": column, "upstream": upstream, "lineage": [label], "source": source}


OWN_COLUMN, OTHER_COLUMN = target_column(OWN), target_column(OTHER)
LABELS = ["target", "split", "eligible", "label_fwd"]
READ_SIDE_CASES = [
    *[
        pytest.param([name], {OWN: _target_meta_of(OWN_COLUMN, True, name, "retail_mart")},
                     {name: DROP_REASONS["own label"]}, {}, id=f"own label {name} in the spine")
        for name in LABELS
    ],
    *[
        pytest.param([name], {OWN: _target_meta_of(OWN_COLUMN, True, name, "retail_holdings")},
                     {}, {name: f"source_{name}"} if name != "label_fwd" else {},
                     id=f"own label {name} in a target source")
        for name in LABELS
    ],
    pytest.param(
        ["cc_flag", "target"],
        {OWN: _target_meta_of(OWN_COLUMN, False, "cc_flag", "retail_holdings"),
         OTHER: _target_meta_of(OTHER_COLUMN, True, "target", "retail_mart")},
        {"target": DROP_REASONS["label"], OTHER_COLUMN: DROP_REASONS["target"]}, {},
        id="other's label target in the spine",
    ),
    pytest.param(["target"], {OWN: _target_meta_of(OWN_COLUMN, False, "target", "retail_mart")},
                 {}, {"target": "source_target"}, id="built over target"),
    pytest.param(["Target"], {OWN: _target_meta_of(OWN_COLUMN, False, "Target", "retail_mart")},
                 {}, {"Target": "source_Target"}, id="built over Target, any case"),
]  # fmt: skip


@pytest.mark.parametrize("extra, targets, dropped, renamed", READ_SIDE_CASES)
def test_read_side_columns_drop_labels_in_the_panel_and_rename_the_rest(
    cc_config: UseCaseConfig, extra: list[str], targets: dict, dropped: dict, renamed: dict
) -> None:
    """An upstream label is dropped only when its target source is a feature source; another
    use case's target and in-panel label are dropped; a remaining helper-named column is
    renamed before the own target becomes `target`; with the lineage under its read name, only
    `income` is a candidate (§4.6). Pure Python, no Spark."""
    columns = ["unit_id", "period", "income", *extra, *[t["column"] for t in targets.values()]]
    plan = read_side_columns(columns, targets, OWN, ["retail_mart", "extra"])
    assert plan == (dropped, {**renamed, OWN_COLUMN: "target"})
    assert list(plan[1])[-1] == OWN_COLUMN  # applied last
    read = [plan[1].get(c, c) for c in columns if c not in plan[0]]
    lineage = [plan[1].get(c, c) for c in targets[OWN]["lineage"]]
    assert resolve_candidates(read, cc_config, lineage) == ["income"]


@pytest.mark.parametrize("name", ["target", "Target"])
def test_read_side_clash_is_refused(name: str) -> None:
    """A source `target` beside a source `source_target`, either in any case, fails naming both
    and the panel."""
    columns = ["unit_id", "period", name, "source_target", OWN_COLUMN]
    targets = {OWN: _target_meta_of(OWN_COLUMN, False, "cc_flag", "retail_holdings")}
    with pytest.raises(ValueError, match=f"the panel has both '{name}' and 'source_{name}'"):
        read_side_columns(columns, targets, OWN, ["retail_mart"])


def test_join_entry_records_a_source_column_read_under_another_name(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
    tmp_path: Path,
) -> None:
    """A feature source's non-key `period` joins as `source_period`, named in its join entry;
    the spine's entry, with nothing renamed, has no `renamed`."""
    del sources["extra"]
    env = write_sources(sources)
    path = str(tmp_path / "extra")
    rows = [(u, m, 0.5, 7) for u in ("a", "b") for m in MONTHS]
    schema = "client_id string, snapshot_month date, score double, period int"
    spark.createDataFrame(rows, schema).write.parquet(path)
    extra = {**env.sources["entity_a"], "extra": Source(format="parquet", path=path)}
    env = env.model_copy(update={"sources": {"entity_a": extra}})
    panel, log, _ = load_panel([_config(variant)], "entity_a", env, spark)
    assert "source_period" in panel.columns
    assert log[1]["renamed"] == {"period": "source_period"} and "renamed" not in log[0]


def test_build_panel_prepares_the_one_config(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    sources: dict[str, DataFrame],
) -> None:
    """`build_panel` is `load_panel` of the one config then `prepare_panel`: the keys, the
    candidates, `eligible`, `target` and `split`, the join log then the preparation's, the
    meta with `PANEL_META_KEYS`; a name in `features.excluded` that no source has, or that
    is the framework's own column, fails loud."""
    env = write_sources(sources)
    panel, log, meta = build_panel(_config(variant), "entity_a", env, spark)
    assert panel.columns == [*KEYS_AND_CANDIDATES, "eligible", "target", "split"]
    rows = {r.unit_id: r for r in panel.where(F.col("period") == MONTHS[0]).collect()}
    assert rows["a"].target == 1 and rows["c"].target == 0 and rows["a"].eligible == 1
    steps = [entry["step"] for entry in log]
    assert steps == ["join", "join", "join", "contract", "contract", "contract", "contract"]
    assert tuple(meta) == PANEL_META_KEYS and meta["lineage"] == ["value"]
    cfg = _config(variant).model_copy(deep=True)
    cfg.features.excluded = ["incom"]
    with pytest.raises(ValueError, match=r"features.excluded names columns .* \['incom'\]"):
        build_panel(cfg, "entity_a", env, spark)
    cfg.features.excluded = ["target"]
    with pytest.raises(ValueError, match=r"excluded names \['target'\], the framework's own"):
        build_panel(cfg, "entity_a", env, spark)


def _eligibility(analysis: list[dict] = (), modelling: list[dict] = ()) -> Eligibility:
    """The two step lists from dicts."""
    return Eligibility.model_validate({"analysis": list(analysis), "modelling": list(modelling)})


@pytest.fixture
def keyed_panel(spark: SparkSession) -> DataFrame:
    """Four units over two periods with a target: a has an income and no card, b a card, c no
    income and a card, d no income and a null card flag (segment x keeps d past `known`)."""
    units = {
        "a": (1000.0, 0, "x"),
        "b": (2000.0, 1, "y"),
        "c": (None, 1, "x"),
        "d": (None, None, "x"),
    }
    return _spine(spark, units, MONTHS[:2]).withColumn("target", F.lit(0))


def test_eligibility_defines_drops_and_tags(keyed_panel: DataFrame) -> None:
    """A define is reused by a filter and dropped; an analysis filter drops its rows with the
    log; a modelling filter tags them, a null condition tagging 0; `eligible` follows the
    tags; the per-period dicts are keyed by the period's label."""
    eligibility = _eligibility(
        analysis=[
            {"name": "has_income", "define": "income IS NOT NULL"},
            {"name": "known", "filter": "has_income OR segment = 'x'", "reason": "r"},
        ],
        modelling=[{"name": "non_holders", "filter": "cc_flag = 0", "reason": "r2"}],
    )
    panel, log = apply_eligibility(keyed_panel, eligibility, MONTH)
    assert panel.columns == [*keyed_panel.columns, "non_holders", "eligible"]
    rows = {r.unit_id: r for r in panel.where(F.col("period") == MONTHS[0]).collect()}
    assert sorted(rows) == ["a", "b", "c", "d"]
    assert {u: r.non_holders for u, r in rows.items()} == {"a": 1, "b": 0, "c": 0, "d": 0}
    assert {u: r.eligible for u, r in rows.items()} == {"a": 1, "b": 0, "c": 0, "d": 0}
    assert [entry["step"] for entry in log] == ["eligibility", "eligibility"]
    assert [entry["name"] for entry in log] == ["known", "non_holders"]
    assert log[0]["kind"] == "analysis" and log[0]["rows"] == {"2024-11": 4, "2024-12": 4}
    assert log[0]["rows_out"] == {"2024-11": 4, "2024-12": 4} and log[0]["reason"] == "r"
    assert log[0]["null_condition"] == {"2024-11": 0, "2024-12": 0}
    assert log[1]["kind"] == "modelling" and log[1]["tagged_1"] == {"2024-11": 1, "2024-12": 1}
    assert log[1]["null_condition"] == {"2024-11": 1, "2024-12": 1}  # d: cc_flag null


def test_define_in_the_analysis_list_serves_a_modelling_filter(keyed_panel: DataFrame) -> None:
    """The two lists run as one order, analysis first: a modelling filter may use an analysis
    define by name; the define is dropped at the end."""
    eligibility = _eligibility(
        analysis=[{"name": "has_income", "define": "income IS NOT NULL"}],
        modelling=[{"name": "earners", "filter": "has_income", "reason": "r"}],
    )
    panel, log = apply_eligibility(keyed_panel, eligibility, MONTH)
    tags = {r.unit_id: r.earners for r in panel.where(F.col("period") == MONTHS[0]).collect()}
    assert tags == {"a": 1, "b": 1, "c": 0, "d": 0}
    assert "has_income" not in panel.columns and log[0]["kind"] == "modelling"


def test_analysis_step_cannot_use_a_modelling_define(keyed_panel: DataFrame) -> None:
    """The order is analysis first, so a modelling define is unknown to an analysis step and the
    reference fails naming the step."""
    eligibility = _eligibility(
        analysis=[{"name": "earners", "filter": "has_income", "reason": "r"}],
        modelling=[{"name": "has_income", "define": "income IS NOT NULL"}],
    )
    with pytest.raises(ValueError, match="eligibility step 'earners'.*earlier define names only"):
        apply_eligibility(keyed_panel, eligibility, MONTH)


def test_eligible_is_1_everywhere_without_modelling_filters(keyed_panel: DataFrame) -> None:
    """With no modelling filter every remaining row is eligible."""
    panel, log = apply_eligibility(keyed_panel, Eligibility(), MONTH)
    assert panel.columns == [*keyed_panel.columns, "eligible"]
    assert panel.agg(F.min("eligible")).collect()[0][0] == 1 and log == []


@pytest.mark.parametrize(
    "condition",
    ["target = 1", "period > date '2024-11-30'", "unit_id = 'a'", "non_holders = 1",
     "eligible = 1"],
    ids=["target", "period", "unit_id", "another tag", "eligible"],
)  # fmt: skip
def test_condition_may_reference_source_columns_and_defines_only(
    keyed_panel: DataFrame, condition: str
) -> None:
    """The keys, the target, the helper columns and another filter's tag are refused in a
    condition, naming the step (eligibility SQL is a leakage surface outside the screens)."""
    eligibility = _eligibility(
        modelling=[
            {"name": "non_holders", "filter": "cc_flag = 0", "reason": "r"},
            {"name": "bad", "filter": condition, "reason": "r"},
        ]
    )
    with pytest.raises(ValueError, match="eligibility step 'bad'.*sources' columns"):
        apply_eligibility(keyed_panel, eligibility, MONTH)


def test_condition_must_be_boolean_and_step_names_must_be_new(keyed_panel: DataFrame) -> None:
    """A non-boolean expression, a step named like a column and a step named like a column the
    dataset adds (`split`, `eligible`) all fail naming the step."""
    rich = _eligibility(analysis=[{"name": "rich", "define": "income"}])
    with pytest.raises(TypeError, match="eligibility step 'rich': 'income' is double, not a bool"):
        apply_eligibility(keyed_panel, rich, MONTH)
    for name in ("income", "split", "eligible"):
        taken = _eligibility(analysis=[{"name": name, "filter": "income > 0", "reason": "r"}])
        with pytest.raises(ValueError, match=f"step '{name}' is named like a column"):
            apply_eligibility(keyed_panel, taken, MONTH)


@pytest.mark.parametrize(
    "sql, what",
    [("hash(*) % 2 = 0", "a star"), ("income > (SELECT 1)", "a subquery"),
     ("income > avg(income) OVER ()", "a window"), ("rand() < 0.5", "a non-deterministic function"),
     ("datediff(current_date(), period) > 180", "a non-deterministic function")],
    ids=["star", "subquery", "window", "rand", "current_date"],
)  # fmt: skip
def test_condition_is_a_plain_expression(keyed_panel: DataFrame, sql: str, what: str) -> None:
    """A star in a call, a subquery, a window function and a non-deterministic function are
    refused before Spark sees them: the first three could read beyond the row's own source
    columns, the last would change the population between the build and a later run (§4.9)."""
    odd = _eligibility(analysis=[{"name": "odd", "define": sql}])
    with pytest.raises(ValueError, match=f"eligibility step 'odd': .* holds {what}"):
        apply_eligibility(keyed_panel, odd, MONTH)


def test_candidates_follow_the_patterns_minus_the_reserved_names(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """Include then exclude patterns over the columns, minus the keys, the helper columns, the
    lineage and the eligibility steps' names; no candidate left fails loud."""
    cfg = _config(
        variant,
        eligibility={
            "analysis": [{"name": "has_income", "define": "income IS NOT NULL"}],
            "modelling": [
                {"name": "carded", "define": "cc_flag = 1"},  # a define is never a tag
                {"name": "non_holders", "filter": "NOT carded", "reason": "r"},
            ],
        },
    )
    assert modelling_tags(cfg) == ["non_holders"]
    columns = ["unit_id", "period", "income", "cc_flag", "segment", "score", "x_trap",
               "non_holders", "eligible", "target", "split"]  # fmt: skip
    assert resolve_candidates(columns, cfg, ["cc_flag"]) == ["income", "segment", "score", "x_trap"]
    assert "carded" not in resolve_candidates([*columns, "carded"], cfg, ["cc_flag"])
    patterns = variant(features={"candidates": {"include": ["s*"], "exclude": ["*_trap"]}})
    assert resolve_candidates(columns, patterns, ["cc_flag"]) == ["segment", "score"]
    with pytest.raises(ValueError, match=r"matches none of \[\]; never candidates: .*'cc_flag'"):
        resolve_candidates(["unit_id", "period", "cc_flag", "target"], cfg, ["cc_flag"])
