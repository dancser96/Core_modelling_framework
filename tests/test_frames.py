"""The frames on the unit preset: the window frame, the modelling frames, the model input
shared by two use cases and prepared on read, the collect printout, and one weekly run on a
hand-made panel (D-030, D-129, D-131, D-133).

The skeleton's config runs end to end on the written unit preset: EDA's window keeps every
client after the analysis filter with the holders tagged, Feature Checks gets its eligible rows,
the modelling frames hold the eligible rows with a known target split by client, the saved model
input gives the same frames back, a model input saved from two configs serves each, a changed
eligibility, window, split or candidate list is prepared on read while a changed target spec, a
validation period the saved target source can't label, a missing use case, an older sidecar or
uncovered periods are refused, and the printout turns into the callout above a tiny budget.
Regression runs through the same path with client sampling; a weekly panel runs through it
with `YYYY-Www` labels.
"""

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import DateType

from core_modelling.config import UseCaseConfig
from core_modelling.dataset import Frames, build_frames, save_model_input
from core_modelling.dataset.frames import estimate_collect
from core_modelling.dataset.model_input import METADATA_FILE, saved_candidates
from core_modelling.environment import EnvironmentConfig, Source
from core_modelling.periods import PERIODS

ENTITY = "entity_a"
INPUT = "cc_acquisition_input"
WEEK = PERIODS["week"]
SUNDAYS = [date(2025, 1, 5) + timedelta(days=7 * i) for i in range(10)]  # 2025-W01 … W10


@pytest.fixture(scope="module")
def env(unit_env: EnvironmentConfig, tmp_path_factory: pytest.TempPathFactory) -> EnvironmentConfig:
    """The unit environment with the model input mapped to a temporary folder."""
    path = str(tmp_path_factory.mktemp("model_input") / "cc_acquisition" / ENTITY)
    sources = {**unit_env.sources[ENTITY], INPUT: Source(format="parquet", path=path)}
    return unit_env.model_copy(update={"sources": {ENTITY: sources}})


@pytest.fixture(scope="module")
def in_memory(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config without a model input: the frames are built in memory."""
    return variant(data={"model_input": None})


@pytest.fixture(scope="module")
def td_config(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """A second use case on the same sources and model input: term-deposit acquisition, scored
    for clients without a deposit."""
    holders = {"name": "non_holders", "filter": "td_flag = 0", "reason": "scored without one"}
    return variant(
        use_case="td_acquisition",
        data={"target": {"column": "td_flag"}, "eligibility": {"modelling": [holders]}},
    )


@pytest.fixture(scope="module")
def eda_frames(spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig) -> Frames:
    """The window frame, built once for the module."""
    return build_frames(in_memory, ENTITY, env, spark, "eda")


@pytest.fixture(scope="module")
def feature_checks_frames(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig
) -> Frames:
    """Feature Checks' frame, built once for the module."""
    return build_frames(in_memory, ENTITY, env, spark, "feature_checks")


@pytest.fixture(scope="module")
def training_frames(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig
) -> Frames:
    """The modelling frames, built once for the module."""
    return build_frames(in_memory, ENTITY, env, spark, "training")


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame in key order with a fresh index."""
    return frame.sort_values(["unit_id", "period"]).reset_index(drop=True)


def test_window_frame_keeps_every_client_after_the_analysis_filter_with_the_tags(
    eda_frames: Frames, in_memory: UseCaseConfig
) -> None:
    """Every window period; the candidates, then the tag, `eligible`, `target` and `split`; the
    lineage column gone; holders present and tagged 0; the analysis filter's rows gone; the log
    in order, the analysis step first; the meta with the hashes and the candidates."""
    window = eda_frames.window
    assert eda_frames.train is None and eda_frames.validation is None
    periods = sorted(window["period"].unique())
    assert periods[0] == in_memory.time.observation_window.first and len(periods) == 6
    assert window.columns[-4:].tolist() == ["non_holders", "eligible", "target", "split"]
    assert "cc_flag" not in window.columns and "target_cc_acquisition" not in window.columns
    assert window.columns[2:-4].tolist() == eda_frames.meta["candidates"]
    assert (window["non_holders"] == 0).any() and window["eligible"].equals(window["non_holders"])
    assert not (window["income"].isna() & (window["salary_transfer_flag"] == 0)).any()
    assert window["target"].isna().any()  # leavers inside the window keep their rows
    steps = [entry["step"] for entry in eda_frames.log]
    assert steps == ["join", "join", "eligibility", "eligibility", "contract", "contract",
                     "contract", "contract", "collect"]  # fmt: skip
    assert [e["name"] for e in eda_frames.log[2:4]] == ["income_known_or_salaried", "non_holders"]
    assert eda_frames.meta["tags"] == ["non_holders"] and eda_frames.meta["lineage"] == ["cc_flag"]
    assert eda_frames.meta["collect"][0]["rows"] == len(window)


def test_feature_checks_frame_is_the_eligible_window(
    feature_checks_frames: Frames, eda_frames: Frames
) -> None:
    """The window's eligible rows, every client, the same columns as EDA's frame, no split
    applied; the collect entry names it."""
    frame = feature_checks_frames.window
    assert (frame["eligible"] == 1).all() and feature_checks_frames.train is None
    assert len(frame) == int(eda_frames.window["eligible"].sum())
    assert frame.columns.tolist() == eda_frames.window.columns.tolist()
    assert set(frame["split"]) == {"train", "test"}
    assert set(frame["period"]) == set(eda_frames.window["period"])  # the window, never v
    assert feature_checks_frames.meta["collect"][0]["frame"] == "eligible_window"


def test_modelling_frames_hold_eligible_labelled_rows_split_by_client(
    training_frames: Frames, eda_frames: Frames, in_memory: UseCaseConfig
) -> None:
    """Train and test share the window and no client; validation is the OOT period; every row
    eligible with a known target; train plus test is the window's eligible labelled rows; the
    null-target and sampling entries in the log; the collect measurements in the meta."""
    train, test, validation = (
        training_frames.train,
        training_frames.test,
        training_frames.validation,
    )
    assert training_frames.window is None
    assert not set(train["unit_id"]) & set(test["unit_id"])
    assert (train["split"] == "train").all() and (test["split"] == "test").all()
    assert validation["period"].unique().tolist() == [in_memory.time.validation_period]
    window_periods = set(eda_frames.window["period"])  # the labelled gap periods never reach a fit
    assert set(train["period"]) | set(test["period"]) <= window_periods
    for frame in (train, test, validation):
        assert (frame["eligible"] == 1).all() and frame["target"].notna().all()
        assert frame.columns.tolist() == eda_frames.window.columns.tolist()
    window = eda_frames.window
    labelled = window[(window["eligible"] == 1) & window["target"].notna()]
    assert len(train) + len(test) == len(labelled)
    steps = [entry["step"] for entry in training_frames.log]
    assert steps[-5:] == ["null_target", "sampling", "collect", "collect", "collect"]
    null_target = training_frames.log[-5]
    assert set(null_target["share"]) == {f"{p:%Y-%m}" for p in window["period"].unique()} | {
        "2025-11"
    }
    assert training_frames.meta["sampling"] == {"step": "sampling", "method": None}
    measured = [entry["frame"] for entry in training_frames.meta["collect"]]
    assert measured == ["train", "test", "validation"]
    assert all(
        e["measured_bytes"] > 0 < e["estimate_bytes"] for e in training_frames.meta["collect"]
    )


def test_model_input_round_trip_gives_the_same_frames(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    training_frames: Frames,
) -> None:
    """The saved model input, read back by the config that names it, gives the modelling frames
    built in memory; it holds the sources and `target_cc_acquisition` only, its period
    partition is a date, the label of every period with a complete forward window; its
    metadata holds the join definition, the use case's target and the join log."""
    path = save_model_input(cc_config, ENTITY, env, spark)
    assert path == env.sources[ENTITY][INPUT].path
    saved = spark.read.parquet(path)
    assert isinstance(saved.schema["period"].dataType, DateType)
    assert not {"eligible", "split", "target", "non_holders"} & set(saved.columns)
    periods = sorted(r.period for r in saved.select("period").distinct().collect())
    labelled = saved.where("target_cc_acquisition IS NOT NULL").select("period").distinct()
    assert {r.period for r in labelled.collect()} == set(periods[: -cc_config.time.target_window])
    assert cc_config.time.validation_period in {r.period for r in labelled.collect()}
    metadata = json.loads(Path(path, METADATA_FILE).read_text())
    assert metadata["use_cases"] == ["cc_acquisition"] and metadata["schema_version"] == 3
    target = metadata["targets"]["cc_acquisition"]
    assert target["target_spec_hash"] == training_frames.meta["target_spec_hash"]
    assert target["lineage"] == ["cc_flag"] and target["null_in_window_share"] == 0.0
    assert [entry["step"] for entry in metadata["log"]] == ["join", "join"]
    assert set(metadata["columns"]) == set(saved.columns)  # Spark lists the partition last
    from_input = build_frames(cc_config, ENTITY, env, spark, "evaluation")
    for name in ("train", "test", "validation"):
        built, read = getattr(training_frames, name), getattr(from_input, name)
        pd.testing.assert_frame_equal(_sorted(built), _sorted(read[built.columns]))
    assert from_input.meta["candidates"] == training_frames.meta["candidates"]
    assert saved_candidates(cc_config, ENTITY, env) == training_frames.meta["candidates"]


def test_model_input_saved_from_two_configs_serves_each(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    td_config: UseCaseConfig,
    training_frames: Frames,
) -> None:
    """One table with two target columns: the first use case gets the frames built in memory,
    the second its own window with its own eligibility, neither seeing the other's target; a
    use case the table lacks is refused naming `save_model_input`."""
    path = save_model_input([cc_config, td_config], ENTITY, env, spark)
    saved = spark.read.parquet(path)
    assert {"target_cc_acquisition", "target_td_acquisition"} <= set(saved.columns)
    metadata = json.loads(Path(path, METADATA_FILE).read_text())
    assert metadata["use_cases"] == ["cc_acquisition", "td_acquisition"]
    cc = build_frames(cc_config, ENTITY, env, spark, "training")
    pd.testing.assert_frame_equal(_sorted(training_frames.train), _sorted(cc.train))
    td = build_frames(td_config, ENTITY, env, spark, "eda")
    assert "target_cc_acquisition" not in td.window.columns and "td_flag" not in td.window.columns
    assert "target_cc_acquisition" not in td.meta["candidates"] and td.meta["lineage"] == [
        "td_flag"
    ]
    assert td.window["eligible"].equals(td.window["non_holders"])
    assert saved_candidates(td_config, ENTITY, env) == td.meta["candidates"]
    unsaved = cc_config.model_copy(update={"use_case": "fx_activation"})
    with pytest.raises(
        ValueError, match="no target for use case 'fx_activation'.*save_model_input"
    ):
        build_frames(unsaved, ENTITY, env, spark, "eda")


def test_changed_settings_after_the_join_are_prepared_on_read(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A changed eligibility, window, split or candidate list is not refused: the saved table
    is prepared again from the reader's config."""
    save_model_input(cc_config, ENTITY, env, spark)
    everyone = variant(data={"eligibility": {"modelling": []}})
    frames = build_frames(everyone, ENTITY, env, spark, "eda")
    assert (frames.window["eligible"] == 1).all() and "non_holders" not in frames.window.columns
    moved = variant(time={"observation_window": {"first": "2025-04-01"}})
    assert sorted(build_frames(moved, ENTITY, env, spark, "eda").window["period"].unique())[0] == (
        moved.time.observation_window.first
    )
    reseeded = variant(data={"split": {"seed": 7}})
    assert set(build_frames(reseeded, ENTITY, env, spark, "feature_checks").window["split"]) == {
        "train", "test"
    }  # fmt: skip
    narrowed = variant(features={"candidates": {"include": ["*"], "exclude": ["income"]}})
    assert "income" not in build_frames(narrowed, ENTITY, env, spark, "eda").window.columns
    assert "income" not in saved_candidates(narrowed, ENTITY, env)


def test_stale_or_missing_model_input_is_refused(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
) -> None:
    """Another target spec, periods the table doesn't cover, another feature source list, an
    older sidecar schema (by name) or no saved table each fail naming `save_model_input`."""
    path = save_model_input(cc_config, ENTITY, env, spark)
    shorter = variant(time={"target_window": 2})
    with pytest.raises(ValueError, match="built from another target spec; rebuild it with save_"):
        build_frames(shorter, ENTITY, env, spark, "eda")
    earlier = variant(time={"observation_window": {"first": "2025-02-01"}})
    with pytest.raises(ValueError, match=r"covers the periods 2025-03 … \d{4}-\d{2}, not 2025-02"):
        build_frames(earlier, ENTITY, env, spark, "eda")
    sources = {"features": ["retail_mart", "retail_holdings"], "targets": "retail_holdings"}
    with pytest.raises(ValueError, match="built with sources .*; rebuild it with save_model_input"):
        build_frames(variant(entities={ENTITY: {"sources": sources}}), ENTITY, env, spark, "eda")
    sidecar = Path(path, METADATA_FILE)
    sidecar.write_text(json.dumps({**json.loads(sidecar.read_text()), "schema_version": 2}))
    with pytest.raises(ValueError, match="has schema_version 2; this version reads 3; rebuild"):
        build_frames(cc_config, ENTITY, env, spark, "eda")
    none = {**env.sources[ENTITY], INPUT: Source(format="parquet", path=str(tmp_path / "none"))}
    empty = env.model_copy(update={"sources": {ENTITY: none}})
    with pytest.raises(ValueError, match="no model input at .*: save it with save_model_input"):
        build_frames(cc_config, ENTITY, empty, spark, "eda")


def test_validation_period_beyond_the_saved_labels_is_refused(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A reader whose validation period needs labels later than the saved target source reaches
    (it ends at `target_last`, so labels are known up to `target_last` - w) is refused naming
    the periods, before the saved periods are compared (§4.2)."""
    path = save_model_input(cc_config, ENTITY, env, spark)
    target = json.loads(Path(path, METADATA_FILE).read_text())["targets"]["cc_acquisition"]
    month, w = PERIODS["month"], cc_config.time.target_window
    last = date.fromisoformat(target["target_last"])
    first_unlabelled = month.from_index(month.index(last) - w + 1)
    later = variant(time={"validation_period": first_unlabelled})
    message = (
        f"the target source of 'cc_acquisition' ends at {month.label(last)}, so labels are known "
        f"up to {month.label(month.from_index(month.index(last) - w))}; time.validation_period "
        f"{month.label(first_unlabelled)} needs it to reach "
        f"{month.label(month.from_index(month.index(last) + 1))}; rebuild"
    )
    with pytest.raises(ValueError, match=message):
        build_frames(later, ENTITY, env, spark, "eda")


def test_collect_printout_becomes_a_callout_above_the_budget(
    spark: SparkSession,
    env: EnvironmentConfig,
    in_memory: UseCaseConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The printout names rows, columns, the estimate and the budget; above the budget the
    callout appears and the frame is still collected."""
    tiny = env.model_copy(update={"collect_budget_gb": 1e-6})
    frames = build_frames(in_memory, ENTITY, tiny, spark, "eda")
    out = capsys.readouterr().out
    assert f"collect window: {len(frames.window):,} rows × {frames.window.shape[1]} columns" in out
    assert "(budget 1e-06 GB)" in out and "above the budget: declare training.sampling" in out
    assert "spark.driver.maxResultSize" in out and "collected window:" in out


def test_regression_runs_through_the_same_path_with_client_sampling(
    spark: SparkSession, env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Card spend summed forward for holders, sampled by client: whole clients kept, the record
    with the rows before and after, the regression contract entries."""
    cfg = variant(
        task="regression",
        entities={ENTITY: {"sources": {"features": ["retail_mart"], "targets": None}}},
        data={
            "model_input": None,
            "target": {"rule": "forward_sum", "column": "spend_cc_vol"},
            "eligibility": {
                "modelling": [
                    {"name": "holders", "filter": "cc_flag = 1", "reason": "spend needs a card"}
                ]
            },
        },
        training={"sampling": {"method": "client_sample", "share": 0.5}},
    )
    frames = build_frames(cfg, ENTITY, env, spark, "training")
    record = frames.meta["sampling"]
    assert record["method"] == "client_sample" and record["rows_after"] < record["rows_before"]
    assert len(frames.train) == record["rows_after"]
    assert frames.train.groupby("unit_id")["period"].count().max() == 6
    assert (frames.train["holders"] == 1).all() and "spend_cc_vol" not in frames.train.columns
    checks = [entry["check"] for entry in frames.log if entry["step"] == "contract"]
    assert checks == ["eligible_rows", "unique_keys", "target_range", "null_in_window"]


def _weekly_mart(spark: SparkSession) -> DataFrame:
    """Forty units over ten weeks: every even unit takes a card in week 2 + (unit mod 8) and
    keeps it, the odd ones never; one income per unit."""
    rows = []
    for unit in range(40):
        card_week = unit % 8 + 2 if unit % 2 == 0 else None
        for week, sunday in enumerate(SUNDAYS, start=1):
            holds = int(card_week is not None and week >= card_week)
            rows.append((f"u{unit:02d}", sunday, 1000.0 + unit, holds))
    return spark.createDataFrame(rows, "unit_id string, period date, income double, cc_flag int")


def test_weekly_panel_runs_end_to_end_with_week_labels(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
) -> None:
    """`time.period: week` on a hand-made weekly mart (the spine is the target source): the
    window frame holds the four window weeks, the join log and the null-target entry are keyed
    by `YYYY-Www`, the modelling frames split by client with the validation week W06 and the
    card flag as the lineage, never a candidate."""
    env = write_sources({"retail_mart": _weekly_mart(spark)})
    cfg = variant(
        time={
            "period": "week",
            "observation_window": {"first": SUNDAYS[0], "last": SUNDAYS[3]},
            "target_window": 2,
            "validation_period": SUNDAYS[5],
        },
        entities={ENTITY: {"sources": {"features": ["retail_mart"], "targets": None}}},
        data={
            "model_input": None,
            "eligibility": {
                "analysis": [],
                "modelling": [{"name": "non_holders", "filter": "cc_flag = 0", "reason": "r"}],
            },
        },
    )
    eda = build_frames(cfg, ENTITY, env, spark, "eda")
    join = [entry for entry in eda.log if entry["step"] == "join"]
    assert [entry["source"] for entry in join] == ["retail_mart", "retail_mart"]
    assert list(join[0]["rows"]) == [f"2025-W{week:02d}" for week in range(1, 11)]
    assert (
        join[1]["null_in_window"]["2025-W08"] == 0.0
        and join[1]["null_in_window"]["2025-W09"] is None
    )
    assert sorted(eda.window["period"].unique()) == SUNDAYS[:4]
    assert eda.meta["candidates"] == ["income"] and eda.meta["lineage"] == ["cc_flag"]
    training = build_frames(cfg, ENTITY, env, spark, "training")
    assert training.validation["period"].unique().tolist() == [SUNDAYS[5]]
    assert not set(training.train["unit_id"]) & set(training.test["unit_id"])
    assert len(training.train) > 0 < len(training.test)
    assert set(training.train["period"]) | set(training.test["period"]) <= set(SUNDAYS[:4])
    null_target = next(entry for entry in training.log if entry["step"] == "null_target")
    assert set(null_target["share"]) == {f"2025-W{week:02d}" for week in (1, 2, 3, 4, 6)}


def test_unknown_stage_and_empty_frame_are_refused(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig
) -> None:
    """A stage the frames don't serve, and a frame with no row to collect, fail loud."""
    with pytest.raises(ValueError, match="unknown stage 'scoring'; the frames serve"):
        build_frames(in_memory, ENTITY, env, spark, "scoring")
    with pytest.raises(ValueError, match="the frame 'x' is empty"):
        estimate_collect(spark.createDataFrame([], "unit_id int"), "x")
