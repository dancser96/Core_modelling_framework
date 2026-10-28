"""The frames on the unit preset: the window frame, the modelling frames, the model input round
trip, the collect printout (D-030, D-131, D-133).

The skeleton's config runs end to end on the written unit preset: EDA's window keeps every
client after the pre-EDA filter with the holders tagged, the modelling frames hold the eligible
rows with a known target split by client, the saved model input gives the same frames back and
is refused when stale, and the printout turns into the callout above a tiny budget. Regression
runs through the same path with client sampling.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import DateType

from core_modelling.config import UseCaseConfig
from core_modelling.dataset import Frames, build_frames, save_model_input
from core_modelling.dataset.frames import estimate_collect
from core_modelling.dataset.model_input import METADATA_FILE
from core_modelling.environment import EnvironmentConfig, Source

ENTITY = "entity_a"
INPUT = "cc_acquisition_input"


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
def eda_frames(spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig) -> Frames:
    """The window frame, built once for the module."""
    return build_frames(in_memory, ENTITY, env, spark, "eda")


@pytest.fixture(scope="module")
def training_frames(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig
) -> Frames:
    """The modelling frames, built once for the module."""
    return build_frames(in_memory, ENTITY, env, spark, "training")


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame in key order with a fresh index."""
    return frame.sort_values(["unit_id", "month"]).reset_index(drop=True)


def test_window_frame_keeps_every_client_after_the_pre_eda_filter_with_the_tags(
    eda_frames: Frames, in_memory: UseCaseConfig
) -> None:
    """Every window month; the candidates, then the tag, `eligible`, `target` and `split`; the
    lineage column gone; holders present and tagged 0; the pre-EDA filter's rows gone; the log in
    order; the meta with the hashes and the candidates."""
    window = eda_frames.window
    assert eda_frames.train is None and eda_frames.validation is None
    months = sorted(window["month"].unique())
    assert months[0] == in_memory.time.train_months.first and len(months) == 6
    assert window.columns[-4:].tolist() == ["non_holders", "eligible", "target", "split"]
    assert "cc_flag" not in window.columns and "null_in_window" not in window.columns
    assert window.columns[2:-4].tolist() == eda_frames.meta["candidates"]
    assert (window["non_holders"] == 0).any() and window["eligible"].equals(window["non_holders"])
    assert not (window["income"].isna() & (window["salary_transfer_flag"] == 0)).any()
    assert window["target"].isna().any()  # leavers inside the window keep their rows
    steps = [entry["step"] for entry in eda_frames.log]
    assert steps == ["join", "join", "eligibility", "eligibility", "contract", "contract",
                     "contract", "contract", "collect"]  # fmt: skip
    assert [e["name"] for e in eda_frames.log[2:4]] == ["non_holders", "income_known_or_salaried"]
    assert eda_frames.meta["tags"] == ["non_holders"] and eda_frames.meta["lineage"] == ["cc_flag"]
    assert eda_frames.meta["collect"][0]["rows"] == len(window)


def test_modelling_frames_hold_eligible_labelled_rows_split_by_client(
    training_frames: Frames, eda_frames: Frames, in_memory: UseCaseConfig
) -> None:
    """Train and test share the window and no client; validation is the OOT month; every row
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
    assert validation["month"].unique().tolist() == [in_memory.time.validation_month]
    for frame in (train, test, validation):
        assert (frame["eligible"] == 1).all() and frame["target"].notna().all()
        assert frame.columns.tolist() == eda_frames.window.columns.tolist()
    window = eda_frames.window
    labelled = window[(window["eligible"] == 1) & window["target"].notna()]
    assert len(train) + len(test) == len(labelled)
    steps = [entry["step"] for entry in training_frames.log]
    assert steps[-5:] == ["null_target", "sampling", "collect", "collect", "collect"]
    null_target = training_frames.log[-5]
    assert set(null_target["share"]) == {f"{m:%Y-%m}" for m in window["month"].unique()} | {
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
    built in memory; its month partition is a date, its metadata holds the hashes, the
    candidates and the logs."""
    path = save_model_input(cc_config, ENTITY, env, spark)
    assert path == env.sources[ENTITY][INPUT].path
    saved = spark.read.parquet(path)
    assert isinstance(saved.schema["month"].dataType, DateType)
    months = {r.month for r in saved.select("month").distinct().collect()}
    labelled = {r.month for r in saved.where("target IS NOT NULL").select("month").collect()}
    window = cc_config.time.train_months
    in_window = {m for m in months if window.first <= m <= window.last}
    assert labelled == in_window | {cc_config.time.validation_month}  # label-free elsewhere
    metadata = json.loads(Path(path, METADATA_FILE).read_text())
    assert metadata["data_definition_hash"] == training_frames.meta["data_definition_hash"]
    assert metadata["candidates"] == training_frames.meta["candidates"]
    steps = [entry["step"] for entry in metadata["log"]]
    assert steps[:4] == ["join", "join", "eligibility", "eligibility"]
    from_input = build_frames(cc_config, ENTITY, env, spark, "evaluation")
    for name in ("train", "test", "validation"):
        built, read = getattr(training_frames, name), getattr(from_input, name)
        pd.testing.assert_frame_equal(_sorted(built), _sorted(read[built.columns]))
    assert from_input.meta["candidates"] == training_frames.meta["candidates"]


def test_stale_or_missing_model_input_is_refused(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
) -> None:
    """Another data definition, another split or no saved table each fail naming
    `save_model_input`."""
    save_model_input(cc_config, ENTITY, env, spark)
    moved = variant(time={"train_months": {"first": "2025-04-01"}})
    with pytest.raises(ValueError, match="another data definition; rebuild it with save_model"):
        build_frames(moved, ENTITY, env, spark, "eda")
    reseeded = variant(data={"split": {"seed": 7}})
    with pytest.raises(ValueError, match="split with other settings .*; rebuild it"):
        build_frames(reseeded, ENTITY, env, spark, "eda")
    sources = {**env.sources[ENTITY], INPUT: Source(format="parquet", path=str(tmp_path / "none"))}
    empty = env.model_copy(update={"sources": {ENTITY: sources}})
    with pytest.raises(ValueError, match="no model input at .*: save it with save_model_input"):
        build_frames(cc_config, ENTITY, empty, spark, "eda")


def test_collect_printout_becomes_a_callout_above_the_budget(
    spark: SparkSession,
    env: EnvironmentConfig,
    in_memory: UseCaseConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The printout names rows, columns, the estimate and the budget; above the budget the
    callout appears and the frame is still collected."""
    tiny = env.model_copy(update={"collect_budget_gb": 1e-6})
    frames = build_frames(in_memory, ENTITY, tiny, spark, "feature_checks")
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
            "eligibility": [
                {
                    "name": "holders",
                    "filter": "cc_flag = 1",
                    "reason": "spend needs a card",
                    "before": "model",
                }
            ],  # fmt: skip
        },
        training={"sampling": {"method": "client_sample", "share": 0.5}},
    )
    frames = build_frames(cfg, ENTITY, env, spark, "training")
    record = frames.meta["sampling"]
    assert record["method"] == "client_sample" and record["rows_after"] < record["rows_before"]
    assert len(frames.train) == record["rows_after"]
    assert frames.train.groupby("unit_id")["month"].count().max() == 6
    assert (frames.train["holders"] == 1).all() and "spend_cc_vol" not in frames.train.columns
    checks = [entry["check"] for entry in frames.log if entry["step"] == "contract"]
    assert checks == ["eligible_rows", "unique_keys", "target_range", "null_in_window"]


def test_unknown_stage_and_empty_frame_are_refused(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig
) -> None:
    """A stage the frames don't serve, and a frame with no row to collect, fail loud."""
    with pytest.raises(ValueError, match="unknown stage 'scoring'; the frames serve"):
        build_frames(in_memory, ENTITY, env, spark, "scoring")
    with pytest.raises(ValueError, match="the frame 'x' is empty"):
        estimate_collect(spark.createDataFrame([], "unit_id int"), "x")
