"""The frames on the unit preset: EDA's snapshot and `rows`, the modelling frames, the model
input shared by two use cases and prepared on read, the collect printout, and one weekly run on
a hand-made panel (D-030, D-129, D-131, D-133, D-135).

The skeleton's config runs end to end on the written unit preset: EDA's snapshot keeps every
client of the snapshot period after the analysis filter with the holders tagged, `rows` stays in
Spark with the label inside the window only and never the validation period, the modelling
frames hold the eligible rows with a known target split by client with the features passed only
(required for Training and Evaluation, refused for EDA), Training's without the validation
period, downsampling thins train only, after the contract and whatever the features, the saved
model input gives
the same frames back, a model input saved from two configs serves each, a changed eligibility,
window, split or candidate list is prepared on read while a changed target spec, a validation
period the saved target source can't label, a missing use case, an older sidecar or uncovered
periods are refused, and the printout turns into the callout worded for the frame above a tiny
budget; a saved spine's `eligible` column is a candidate as `source_eligible` in both lists.
Regression runs through the same path with client sampling; a weekly panel runs through it
with `YYYY-Www` labels and an unsupported date column dropped; an EDA-only config (a null
validation period) compares the window and the latest period; EDA's frames refuse a candidate
list with no supported column and a snapshot period without rows.
"""

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from conftest import REGRESSION
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DateType

from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import resolve_config
from core_modelling.config.identities import resolved_input_hash
from core_modelling.dataset import Frames, build_frames, save_model_input
from core_modelling.dataset.frames import _eda_frames, collect_frame, estimate_collect
from core_modelling.dataset.model_input import METADATA_FILE, saved_candidates
from core_modelling.environment import EnvironmentConfig, Source
from core_modelling.periods import PERIODS

ENTITY = "entity_a"
INPUT = "retail_acquisition_input"
WEEK = PERIODS["week"]
SUNDAYS = [date(2025, 1, 5) + timedelta(days=7 * i) for i in range(10)]  # 2025-W01 … W10
WINDOW_LABELS = ["2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08"]
PRUNED = ["income", "segment", "cc_limit"]  # a feature set without the other candidates


@pytest.fixture(scope="module")
def env(unit_env: EnvironmentConfig, tmp_path_factory: pytest.TempPathFactory) -> EnvironmentConfig:
    """The unit environment with the model input mapped to a temporary folder."""
    path = str(tmp_path_factory.mktemp("model_input") / "retail_acquisition" / ENTITY)
    sources = {**unit_env.sources[ENTITY], INPUT: Source(format="parquet", path=path)}
    return unit_env.model_copy(update={"sources": {ENTITY: sources}})


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
def candidates(eda_frames: Frames) -> list[str]:
    """Every candidate, each of a supported kind on the unit preset: the feature set
    `resolve_features` gives when nothing is excluded or held."""
    return eda_frames.meta["candidates"]


@pytest.fixture(scope="module")
def training_frames(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig, candidates: list[str]
) -> Frames:
    """Training's frames on every candidate, built once for the module."""
    resolved = resolve_config(in_memory, ENTITY, env)
    return build_frames(resolved, ENTITY, env, spark, "training", features=candidates)


@pytest.fixture(scope="module")
def evaluation_frames(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig, candidates: list[str]
) -> Frames:
    """Evaluation's frames on every candidate, built once for the module."""
    return build_frames(in_memory, ENTITY, env, spark, "evaluation", features=candidates)


@pytest.fixture(scope="module")
def downsampled(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config in memory with negative downsampling declared."""
    sampling = {"method": "negative_downsampling", "keep_fraction": 0.3}
    return variant(data={"model_input": None}, training={"sampling": sampling})


@pytest.fixture(scope="module")
def downsampled_frames(
    spark: SparkSession, env: EnvironmentConfig, downsampled: UseCaseConfig, candidates: list[str]
) -> Frames:
    """Evaluation's frames of the downsampled config on every candidate."""
    return build_frames(downsampled, ENTITY, env, spark, "evaluation", features=candidates)


@pytest.fixture(scope="module")
def pruned_frames(
    spark: SparkSession, env: EnvironmentConfig, downsampled: UseCaseConfig
) -> Frames:
    """Evaluation's frames of the downsampled config on three features (`PRUNED`)."""
    return build_frames(downsampled, ENTITY, env, spark, "evaluation", features=PRUNED)


@pytest.fixture(scope="module")
def saved_input(spark: SparkSession, env: EnvironmentConfig, cc_config: UseCaseConfig) -> str:
    """The card config's model input, saved once at `env`'s path for the tests that only read
    it; a test that saves another table or changes it uses its own folder (`_with_input`)."""
    return save_model_input(cc_config, ENTITY, env, spark)


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame in key order with a fresh index."""
    return frame.sort_values(["unit_id", "period"]).reset_index(drop=True)


def test_snapshot_keeps_every_client_of_the_snapshot_period_with_the_tags(
    eda_frames: Frames, in_memory: UseCaseConfig
) -> None:
    """The window's last period only; the candidates, then the tag, `eligible`, `target` and
    `split`; the lineage column gone; holders present and tagged 0; the analysis filter's rows
    gone, so the snapshot's rows are the last analysis step's rows out for its period and the
    population's rows, each counted on its own; the log in order, the analysis step first, the
    compared periods before the collect; the meta with the hashes, the candidates, the kinds
    from the Spark schema, no unsupported column, the snapshot period and the population
    counts."""
    snapshot = eda_frames.snapshot
    assert eda_frames.train is None and eda_frames.validation is None
    assert snapshot["period"].unique().tolist() == [in_memory.time.observation_window.last]
    assert snapshot.columns[-4:].tolist() == ["non_holders", "eligible", "target", "split"]
    assert "cc_flag" not in snapshot.columns and "target_cc_acquisition" not in snapshot.columns
    assert snapshot.columns[2:-4].tolist() == eda_frames.meta["candidates"]
    assert (snapshot["non_holders"] == 0).any()
    assert snapshot["eligible"].equals(snapshot["non_holders"])
    assert not (snapshot["income"].isna() & (snapshot["salary_transfer_flag"] == 0)).any()
    assert snapshot["target"].isna().any()  # leavers inside the window keep their rows
    steps = [entry["step"] for entry in eda_frames.log]
    # the joins: the spine, the extract and the target source
    assert steps == ["join", "join", "join", "eligibility", "eligibility", "contract",
                     "contract", "contract", "contract", "compared_periods", "collect"]  # fmt: skip
    assert [e["name"] for e in eda_frames.log[3:5]] == ["income_known_or_salaried", "non_holders"]
    assert eda_frames.meta["tags"] == ["non_holders"] and eda_frames.meta["lineage"] == ["cc_flag"]
    assert eda_frames.meta["collect"][0]["rows"] == len(snapshot)
    assert eda_frames.meta["collect"][0]["frame"] == "snapshot"
    kinds = eda_frames.meta["kinds"]
    assert list(kinds) == eda_frames.meta["candidates"] and eda_frames.meta["unsupported"] == {}
    assert kinds["cc_limit"] == "numeric" and kinds["segment"] == "categorical"
    assert eda_frames.meta["snapshot_period"] == "2025-08"
    analysis = [e for e in eda_frames.log if e["step"] == "eligibility" and e["kind"] == "analysis"]
    assert len(snapshot) == analysis[-1]["rows_out"]["2025-08"]
    assert eda_frames.meta["population"].set_index("period").loc["2025-08", "rows"] == len(snapshot)


def test_every_candidate_and_the_lineage_column_name_their_source(eda_frames: Frames) -> None:
    """Each candidate maps to the feature source it comes from; the lineage `cc_flag`, in the
    mart and the target source alike, to the mart: the feature sources come first."""
    sources, meta = eda_frames.meta["column_sources"], eda_frames.meta
    assert list(sources) == [*meta["candidates"], "cc_flag"]
    assert set(sources[name] for name in meta["candidates"]) == {"retail_mart", "retail_fs_extract"}
    assert sources["cc_flag"] == "retail_mart"


def test_collected_snapshot_is_sorted_by_the_keys_with_a_fresh_index(eda_frames: Frames) -> None:
    """`toPandas()` has no set order, so a positional seeded sample needs the keys' order (T34)."""
    snapshot = eda_frames.snapshot
    ordered = snapshot.sort_values(["unit_id", "period"], ignore_index=True)
    assert snapshot.equals(ordered)
    assert snapshot.index.equals(pd.RangeIndex(len(snapshot)))


def test_rows_hold_the_eligible_compared_periods_with_the_label_inside_the_window_only(
    eda_frames: Frames,
) -> None:
    """`rows` stays in Spark with the keys, the candidates and `target`; eligible rows only; the
    window, the gap (2025-09, 2025-10) and the latest period (the spine's last, after v), never
    the validation period 2025-11; the label null outside the window (§4.4); the log entry and
    the population counts name the same periods."""
    rows = eda_frames.rows
    assert isinstance(rows, DataFrame)
    assert rows.columns == ["unit_id", "period", *eda_frames.meta["candidates"], "target"]
    entry = next(entry for entry in eda_frames.log if entry["step"] == "compared_periods")
    assert entry == {"step": "compared_periods", "window": WINDOW_LABELS,
                     "gap": ["2025-09", "2025-10"], "latest": ["2026-09"]}  # fmt: skip
    counted = (
        rows.groupBy("period")
        .agg(F.count(F.lit(1)).alias("rows"), F.count("target").alias("labelled"))
        .orderBy("period")
        .collect()
    )
    by_period = {f"{row.period:%Y-%m}": (row.rows, row.labelled) for row in counted}
    assert list(by_period) == [*entry["window"], *entry["gap"], *entry["latest"]]
    assert "2025-11" not in by_period
    assert all(by_period[period][1] > 0 for period in entry["window"])
    assert all(by_period[period][1] == 0 for period in [*entry["gap"], *entry["latest"]])
    assert by_period["2025-08"][0] == int(eda_frames.snapshot["eligible"].sum())
    population = eda_frames.meta["population"]
    assert population["period"].tolist() == list(by_period)
    assert population.set_index("period").loc["2025-08", "eligible_rows"] == by_period["2025-08"][0]
    assert (
        population.set_index("period")["known_target"].isna().tolist() == [False] * 6 + [True] * 3
    )


def test_an_eda_only_config_compares_the_window_and_the_latest_period(
    spark: SparkSession, env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """`time.validation_period: null`: the snapshot is built and `rows` holds the window and the
    latest period after it (the spine's last), no gap, the label inside the window only."""
    eda_only = variant(data={"model_input": None}, time={"validation_period": None})
    frames = build_frames(eda_only, ENTITY, env, spark, "eda")
    assert frames.snapshot["period"].unique().tolist() == [eda_only.time.observation_window.last]
    entry = next(entry for entry in frames.log if entry["step"] == "compared_periods")
    assert entry == {"step": "compared_periods", "window": WINDOW_LABELS, "gap": [],
                     "latest": ["2026-09"]}  # fmt: skip
    counted = frames.rows.groupBy("period").agg(F.count("target").alias("labelled"))
    labelled = {f"{row.period:%Y-%m}": row.labelled for row in counted.orderBy("period").collect()}
    assert list(labelled) == [*WINDOW_LABELS, "2026-09"] and labelled["2026-09"] == 0
    assert all(labelled[period] > 0 for period in WINDOW_LABELS)
    assert frames.meta["population"]["period"].tolist() == list(labelled)


def test_eda_frames_refuse_no_supported_candidate_and_a_snapshot_period_without_rows(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig
) -> None:
    """On hand-made prepared panels: a candidate list of date columns only fails naming the
    unsupported types and `features.candidates`; a panel without a row of the snapshot period
    fails naming `eda.snapshot`, the period and the analysis filters, before the collect."""
    helpers = "eligible int, target int, split string"
    dates = spark.createDataFrame(
        [("u1", date(2025, 8, 31), date(2024, 1, 1), 1, 0, "train")],
        f"unit_id string, period date, opened_on date, {helpers}",
    )
    message = r"unsupported type \(\{'opened_on': 'date'\}\).*features\.candidates"
    with pytest.raises(ValueError, match=message):
        _eda_frames(dates, in_memory, env, [], {"candidates": ["opened_on"]})
    early = spark.createDataFrame(
        [("u1", date(2025, 3, 31), 1.0, 1, 0, "train")],
        f"unit_id string, period date, x double, {helpers}",
    )
    message = r"eda.snapshot is 2025-08, but .* \(data.eligibility.analysis\)"
    with pytest.raises(ValueError, match=message):
        _eda_frames(early, in_memory, env, [], {"candidates": ["x"]})


def test_modelling_frames_hold_eligible_labelled_rows_split_by_client(
    evaluation_frames: Frames,
    eda_frames: Frames,
    in_memory: UseCaseConfig,
    candidates: list[str],
) -> None:
    """Evaluation's frames: train and test share the window and no client; validation is the
    OOT period; the keys, the features, `target` and `split` only; every row with a known
    target; train plus test are the eligible labelled rows of the window (EDA's `rows` with a
    label), the snapshot period's among them; validation is the eligible rows of its period
    less the null targets; the null-target and sampling entries in the log; the collect
    measurements in the meta."""
    train, test, validation = (
        evaluation_frames.train,
        evaluation_frames.test,
        evaluation_frames.validation,
    )
    assert evaluation_frames.snapshot is None and evaluation_frames.rows is None
    assert not set(train["unit_id"]) & set(test["unit_id"])
    assert (train["split"] == "train").all() and (test["split"] == "test").all()
    assert validation["period"].unique().tolist() == [in_memory.time.validation_period]
    window = in_memory.time.observation_window
    periods = set(train["period"]) | set(test["period"])
    assert min(periods) == window.first and max(periods) == window.last and len(periods) == 6
    for frame in (train, test, validation):
        assert frame["target"].notna().all()
        assert frame.columns.tolist() == ["unit_id", "period", *candidates, "target", "split"]
    labelled_rows = eda_frames.rows.where(F.col("target").isNotNull()).select("unit_id", "period")
    at_window = pd.concat([train, test])
    assert set(zip(at_window["unit_id"], at_window["period"], strict=True)) == {
        (row.unit_id, row.period) for row in labelled_rows.collect()
    }
    snapshot = eda_frames.snapshot
    labelled = snapshot[(snapshot["eligible"] == 1) & snapshot["target"].notna()]
    assert (at_window["period"] == window.last).sum() == len(labelled)
    steps = [entry["step"] for entry in evaluation_frames.log]
    assert steps[-5:] == ["null_target", "sampling", "collect", "collect", "collect"]
    null_target = evaluation_frames.log[-5]
    assert set(null_target["share"]) == {*WINDOW_LABELS, "2025-11"}
    eligible_rows = next(e for e in evaluation_frames.log if e.get("check") == "eligible_rows")
    at_v = eligible_rows["per_period"]["2025-11"] * (1 - null_target["share"]["2025-11"])
    assert len(validation) == round(at_v)
    assert evaluation_frames.meta["sampling"] == {"step": "sampling", "method": None}
    measured = [entry["frame"] for entry in evaluation_frames.meta["collect"]]
    assert measured == ["train", "test", "validation"]
    assert all(
        e["measured_bytes"] > 0 < e["estimate_bytes"] for e in evaluation_frames.meta["collect"]
    )


def test_training_gets_train_and_test_only_never_the_validation_period(
    training_frames: Frames, evaluation_frames: Frames
) -> None:
    """Training's train and test are Evaluation's; its validation is None and never collected:
    no validation collect in the log or the meta, and the null-target share covers the window's
    periods only (§4.4); everything before (joins, eligibility, contract) is Evaluation's."""
    assert training_frames.validation is None
    for name in ("train", "test"):
        built, expected = getattr(training_frames, name), getattr(evaluation_frames, name)
        pd.testing.assert_frame_equal(built, expected)
    steps = [entry["step"] for entry in training_frames.log]
    assert steps[-4:] == ["null_target", "sampling", "collect", "collect"]
    assert set(training_frames.log[-4]["share"]) == set(WINDOW_LABELS)
    assert [entry["frame"] for entry in training_frames.meta["collect"]] == ["train", "test"]
    assert training_frames.log[:-4] == evaluation_frames.log[:-5]


def test_a_feature_left_out_is_in_no_frame(pruned_frames: Frames) -> None:
    """Three features passed: every frame carries the keys, those three, `target` and `split`,
    in that order, and nothing else (no other candidate, tag or `eligible`)."""
    for frame in (pruned_frames.train, pruned_frames.test, pruned_frames.validation):
        assert frame.columns.tolist() == ["unit_id", "period", *PRUNED, "target", "split"]
        assert "cc_bal" not in frame.columns and "non_holders" not in frame.columns


def test_downsampling_leaves_test_and_validation_whole(
    evaluation_frames: Frames, downsampled_frames: Frames
) -> None:
    """Sampling is train-only (§4.7, §4.12): with negative downsampling declared, test and
    validation are the unsampled build's frames, while train keeps every positive and a subset
    of its rows; the record's rows before are the unsampled train split's."""
    for name in ("test", "validation"):
        built, whole = getattr(downsampled_frames, name), getattr(evaluation_frames, name)
        pd.testing.assert_frame_equal(built, whole)
    full, sampled = evaluation_frames.train, downsampled_frames.train
    assert len(sampled) < len(full)
    assert (sampled["target"] == 1).sum() == (full["target"] == 1).sum()
    keys = set(zip(sampled["unit_id"], sampled["period"], strict=True))
    assert keys < set(zip(full["unit_id"], full["period"], strict=True))
    record = downsampled_frames.meta["sampling"]
    assert record["rows_before"] == len(full) and record["rows_after"] == len(sampled)


def test_contract_checks_count_the_unsampled_population(
    evaluation_frames: Frames, downsampled_frames: Frames
) -> None:
    """The contract runs before any sampling (§4.8): the downsampled build's contract entries
    are the unsampled build's, and each window period's eligible rows less the null targets are
    the unsampled train and test rows of that period."""
    contract = [entry for entry in evaluation_frames.log if entry["step"] == "contract"]
    assert [entry for entry in downsampled_frames.log if entry["step"] == "contract"] == contract
    eligible_rows = next(entry for entry in contract if entry["check"] == "eligible_rows")
    null_share = next(e for e in evaluation_frames.log if e["step"] == "null_target")["share"]
    unsampled = pd.concat([evaluation_frames.train, evaluation_frames.test])["period"]
    per_period = unsampled.map(lambda period: f"{period:%Y-%m}").value_counts()
    for label in WINDOW_LABELS:
        expected = eligible_rows["per_period"][label] * (1 - null_share[label])
        assert per_period[label] == round(expected)
    assert len(downsampled_frames.train) < len(evaluation_frames.train)  # sampling did run


def test_a_pruned_feature_set_samples_the_same_train_rows(
    downsampled_frames: Frames, pruned_frames: Frames
) -> None:
    """Pruning the columns moves no row (§4.12): with the same sampling, three features give the
    same train, test and validation rows, in the same order with the same values, as every
    candidate, and the same sampling record."""
    for name in ("train", "test", "validation"):
        pruned, full = getattr(pruned_frames, name), getattr(downsampled_frames, name)
        pd.testing.assert_frame_equal(pruned, full[pruned.columns])
    assert pruned_frames.meta["sampling"] == downsampled_frames.meta["sampling"]


def test_features_are_required_by_the_modelling_stages_and_refused_by_eda(
    spark: SparkSession, env: EnvironmentConfig, in_memory: UseCaseConfig
) -> None:
    """Training and Evaluation without `features`, with an empty list or with a repeated name
    fail naming `resolve_features`, before the panel is built; `eda` with `features` fails;
    Training refuses a held or an excluded feature; a name that is no candidate (the lineage
    `cc_flag`, the framework's `target`) fails naming it."""
    for stage in ("training", "evaluation"):
        with pytest.raises(ValueError, match=rf"the {stage} frames need `features`: pass resolve_"):
            build_frames(in_memory, ENTITY, env, spark, stage)
        with pytest.raises(ValueError, match=r"`features` is empty: .* resolve_features\(ledger"):
            build_frames(in_memory, ENTITY, env, spark, stage, features=[])
        with pytest.raises(ValueError, match=r"`features` repeats \['income'\]: pass each name"):
            build_frames(in_memory, ENTITY, env, spark, stage, features=["income", "income"])
    with pytest.raises(ValueError, match="eda reads every candidate: build its frames without"):
        build_frames(in_memory, ENTITY, env, spark, "eda", features=["income"])
    with pytest.raises(ValueError, match="build_frames for training needs the resolved config"):
        build_frames(in_memory, ENTITY, env, spark, "training", features=["income"])
    resolved = resolve_config(in_memory, ENTITY, env)
    message = r"features names \['cc_flag', 'target'\], which are not candidates of the panel"
    with pytest.raises(ValueError, match=message):
        build_frames(resolved, ENTITY, env, spark, "training", ["income", "cc_flag", "target"])
    resolved.features.held, resolved.features.excluded = ["income"], ["age"]
    resolved.housekeeping["resolved_input_hash"] = resolved_input_hash(resolved)
    with pytest.raises(ValueError, match=r"names \['income', 'age'\], held or excluded"):
        build_frames(resolved, ENTITY, env, spark, "training", features=["income", "age", "tenure"])


def test_model_input_round_trip_gives_the_same_frames(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    saved_input: str,
    evaluation_frames: Frames,
    candidates: list[str],
) -> None:
    """The saved model input, read back by the config that names it, gives the modelling frames
    built in memory; it holds the sources and `target_cc_acquisition` only, its period
    partition is a date, the label of every period with a complete forward window; its
    metadata holds the join definition, the use case's target and the join log."""
    path = saved_input
    assert path == env.sources[ENTITY][INPUT].path
    saved = spark.read.parquet(path)
    assert isinstance(saved.schema["period"].dataType, DateType)
    assert not {"eligible", "split", "target", "non_holders"} & set(saved.columns)
    periods = sorted(r.period for r in saved.select("period").distinct().collect())
    labelled = saved.where("target_cc_acquisition IS NOT NULL").select("period").distinct()
    assert {r.period for r in labelled.collect()} == set(periods[: -cc_config.time.target_window])
    assert cc_config.time.validation_period in {r.period for r in labelled.collect()}
    metadata = json.loads(Path(path, METADATA_FILE).read_text())
    assert metadata["use_cases"] == ["cc_acquisition"] and metadata["schema_version"] == 4
    target = metadata["targets"]["cc_acquisition"]
    assert target["target_spec_hash"] == evaluation_frames.meta["target_spec_hash"]
    assert target["lineage"] == ["cc_flag"] and target["null_in_window_share"] == 0.0
    assert [entry["step"] for entry in metadata["log"]] == ["join", "join", "join"]
    assert set(metadata["columns"]) == set(saved.columns)  # Spark lists the partition last
    from_input = build_frames(cc_config, ENTITY, env, spark, "evaluation", features=candidates)
    for name in ("train", "test", "validation"):
        built, read = getattr(evaluation_frames, name), getattr(from_input, name)
        pd.testing.assert_frame_equal(_sorted(built), _sorted(read[built.columns]))
    assert from_input.meta["candidates"] == evaluation_frames.meta["candidates"]
    assert from_input.meta["column_sources"] == evaluation_frames.meta["column_sources"]
    assert saved_candidates(cc_config, ENTITY, env) == evaluation_frames.meta["candidates"]


def test_model_input_saved_from_two_configs_serves_each(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    td_config: UseCaseConfig,
    training_frames: Frames,
    candidates: list[str],
    tmp_path: Path,
) -> None:
    """One table with two target columns: the first use case gets the frames built in memory,
    the second its own snapshot with its own eligibility, neither seeing the other's target; a
    use case the table lacks is refused naming `save_model_input`."""
    env = _with_input(env, tmp_path)
    path = save_model_input([cc_config, td_config], ENTITY, env, spark)
    saved = spark.read.parquet(path)
    assert {"target_cc_acquisition", "target_td_acquisition"} <= set(saved.columns)
    metadata = json.loads(Path(path, METADATA_FILE).read_text())
    assert metadata["use_cases"] == ["cc_acquisition", "td_acquisition"]
    resolved = resolve_config(cc_config, ENTITY, env)
    cc = build_frames(resolved, ENTITY, env, spark, "training", features=candidates)
    pd.testing.assert_frame_equal(_sorted(training_frames.train), _sorted(cc.train))
    td = build_frames(td_config, ENTITY, env, spark, "eda")
    assert "target_cc_acquisition" not in td.snapshot.columns
    assert "td_flag" not in td.snapshot.columns
    assert "target_cc_acquisition" not in td.meta["candidates"] and td.meta["lineage"] == [
        "td_flag"
    ]
    assert td.snapshot["eligible"].equals(td.snapshot["non_holders"])
    assert saved_candidates(td_config, ENTITY, env) == td.meta["candidates"]
    unsaved = cc_config.model_copy(update={"use_case": "fx_activation"})
    with pytest.raises(
        ValueError, match="no target for use case 'fx_activation'.*save_model_input"
    ):
        build_frames(unsaved, ENTITY, env, spark, "eda")


def test_changed_settings_after_the_join_are_prepared_on_read(
    spark: SparkSession,
    env: EnvironmentConfig,
    saved_input: str,
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A changed eligibility, snapshot, split, candidate list or kind is not refused: the saved
    table is prepared again from the reader's config."""
    everyone = variant(data={"eligibility": {"modelling": []}})
    frames = build_frames(everyone, ENTITY, env, spark, "eda")
    assert (frames.snapshot["eligible"] == 1).all()
    assert "non_holders" not in frames.snapshot.columns
    earlier = variant(eda={"snapshot": "2025-04-01"}, data={"split": {"seed": 7}})
    frames = build_frames(earlier, ENTITY, env, spark, "eda")
    assert frames.snapshot["period"].unique().tolist() == [date(2025, 4, 30)]
    assert frames.meta["snapshot_period"] == "2025-04"
    assert set(frames.snapshot["split"]) == {"train", "test"}
    narrowed = variant(
        features={"candidates": {"include": ["*"], "exclude": ["income"]},
                  "kinds": {"product_cnt": "categorical"}},
    )  # fmt: skip
    frames = build_frames(narrowed, ENTITY, env, spark, "eda")
    assert "income" not in frames.snapshot.columns and "income" not in frames.rows.columns
    assert "income" not in saved_candidates(narrowed, ENTITY, env)
    assert frames.meta["kinds"]["product_cnt"] == "categorical"


def test_stale_or_missing_model_input_is_refused(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
) -> None:
    """Another target spec, periods the table doesn't cover, another feature source list, an
    older sidecar schema (by name) or no saved table each fail naming `save_model_input`."""
    env = _with_input(env, tmp_path)
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
    sidecar.write_text(json.dumps({**json.loads(sidecar.read_text()), "schema_version": 3}))
    stale = r"schema_version 3 \(written by framework .*\); this version reads 4: rebuild it with"
    with pytest.raises(ValueError, match=stale):
        build_frames(cc_config, ENTITY, env, spark, "eda")
    none = {**env.sources[ENTITY], INPUT: Source(format="parquet", path=str(tmp_path / "none"))}
    empty = env.model_copy(update={"sources": {ENTITY: none}})
    with pytest.raises(ValueError, match="no model input at .*: save it with save_model_input"):
        build_frames(cc_config, ENTITY, empty, spark, "eda")


def test_validation_period_beyond_the_saved_labels_is_refused(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    saved_input: str,
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A reader whose validation period needs labels later than the saved target source reaches
    (it ends at `target_last`, so labels are known up to `target_last` - w) is refused naming
    the periods, before the saved periods are compared (§4.2)."""
    path = saved_input
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


def test_collect_printout_becomes_a_callout_worded_for_the_frame_above_the_budget(
    spark: SparkSession,
    env: EnvironmentConfig,
    in_memory: UseCaseConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The printout names rows, columns and the estimate, never the budget; above the budget
    the callout appears with it and the frame is still collected: the snapshot's names
    `eda.snapshot` and the hash, never sampling; a training frame's names `training.sampling`."""
    tiny = env.model_copy(update={"collect_budget_gb": 1e-6})
    frames = build_frames(in_memory, ENTITY, tiny, spark, "eda")
    out = capsys.readouterr().out
    snapshot = frames.snapshot
    assert f"collect snapshot: {len(snapshot):,} rows × {snapshot.shape[1]} columns" in out
    assert "conversion peak\n" in out and "collected snapshot:" in out
    assert "above the budget (1e-06 GB): raise collect_budget_gb" in out
    assert "smaller eda.snapshot population through eligibility" in out
    assert "data-definition hash" in out and "training.sampling" not in out
    frame = spark.createDataFrame(
        [("u1", date(2025, 3, 31), 1)], "unit_id string, period date, x int"
    )
    one_byte = env.model_copy(update={"collect_budget_gb": 1e-9})  # a one-row frame is above it
    _, entry = collect_frame(frame, "train", one_byte)
    out = capsys.readouterr().out
    assert "above the budget (1e-09 GB): declare training.sampling (negative_downsampling" in out
    assert "spark.driver.maxResultSize" in out and entry["frame"] == "train"


def test_regression_runs_through_the_same_path_with_client_sampling(
    spark: SparkSession, env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Card spend summed forward for holders, sampled by client: whole clients kept, holders
    only (their `cc_flag` passed as a feature), the record with the rows before and after, the
    regression contract entries."""
    cfg = variant(**REGRESSION, training={"sampling": {"method": "client_sample", "share": 0.5}})
    cfg = resolve_config(cfg, ENTITY, env)
    frames = build_frames(cfg, ENTITY, env, spark, "training", features=["cc_flag", "income"])
    record = frames.meta["sampling"]
    assert record["method"] == "client_sample" and record["rows_after"] < record["rows_before"]
    assert len(frames.train) == record["rows_after"]
    assert frames.train.groupby("unit_id")["period"].count().max() == 6
    assert (frames.train["cc_flag"] == 1).all() and "spend_cc_vol" not in frames.train.columns
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


def _weekly_config(variant: Callable[..., UseCaseConfig], **data: object) -> UseCaseConfig:
    """The skeleton's config on the weekly mart (the spine is the target source): window W01 …
    W04, w = 2, validation week W06, the non-holders tagged; `data` merges into its data
    section."""
    return variant(
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
            **data,
        },
    )


def test_weekly_panel_runs_end_to_end_with_week_labels(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
) -> None:
    """`time.period: week` on a hand-made weekly mart (the spine is the target source) with a
    date column: the snapshot is W04, `rows` the window weeks, the gap week W05 and the latest
    week W10 (after the validation week W06), labelled in the window only; the date column is a
    candidate, unsupported and dropped from both frames; the join log and the null-target entry
    are keyed by `YYYY-Www`; the modelling frames split by client with the validation week W06
    and the card flag as the lineage, never a candidate."""
    mart = _weekly_mart(spark).withColumn("opened_on", F.lit(date(2024, 6, 1)))
    env = write_sources({"retail_mart": mart})
    cfg = _weekly_config(variant)
    eda = build_frames(cfg, ENTITY, env, spark, "eda")
    join = [entry for entry in eda.log if entry["step"] == "join"]
    assert [entry["source"] for entry in join] == ["retail_mart", "retail_mart"]
    assert list(join[0]["rows"]) == [f"2025-W{week:02d}" for week in range(1, 11)]
    assert (
        join[1]["null_in_window"]["2025-W08"] == 0.0
        and join[1]["null_in_window"]["2025-W09"] is None
    )
    assert eda.snapshot["period"].unique().tolist() == [SUNDAYS[3]]
    assert eda.meta["candidates"] == ["income", "opened_on"] and eda.meta["lineage"] == ["cc_flag"]
    assert eda.meta["kinds"] == {"income": "numeric"}
    assert eda.meta["unsupported"] == {"opened_on": "date"}
    assert "opened_on" not in eda.snapshot.columns and "opened_on" not in eda.rows.columns
    compared = next(entry for entry in eda.log if entry["step"] == "compared_periods")
    assert compared == {"step": "compared_periods", "window": ["2025-W01", "2025-W02", "2025-W03",
                        "2025-W04"], "gap": ["2025-W05"], "latest": ["2025-W10"]}  # fmt: skip
    labelled = eda.rows.where(F.col("target").isNotNull()).select("period").distinct().collect()
    assert sorted(row.period for row in labelled) == SUNDAYS[:4]
    assert sorted(r.period for r in eda.rows.select("period").distinct().collect()) == [
        *SUNDAYS[:5], SUNDAYS[9]
    ]  # fmt: skip
    evaluation = build_frames(cfg, ENTITY, env, spark, "evaluation", features=["income"])
    assert evaluation.validation["period"].unique().tolist() == [SUNDAYS[5]]
    assert not set(evaluation.train["unit_id"]) & set(evaluation.test["unit_id"])
    assert len(evaluation.train) > 0 < len(evaluation.test)
    assert set(evaluation.train["period"]) | set(evaluation.test["period"]) <= set(SUNDAYS[:4])
    null_target = next(entry for entry in evaluation.log if entry["step"] == "null_target")
    assert set(null_target["share"]) == {f"2025-W{week:02d}" for week in (1, 2, 3, 4, 6)}


def _with_input(env: EnvironmentConfig, tmp_path: Path) -> EnvironmentConfig:
    """The environment with the model input mapped to the test's `input` folder."""
    saved = Source(format="parquet", path=str(tmp_path / "input"))
    return env.model_copy(update={"sources": {ENTITY: {**env.sources[ENTITY], INPUT: saved}}})


def test_read_side_clash_is_refused_at_save(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
) -> None:
    """A spine `target` beside a `source_target` fails at save, naming both, before anything
    is written, not at every later read."""
    mart = _weekly_mart(spark).withColumn("target", F.lit(0)).withColumn("source_target", F.lit(1))
    env = _with_input(write_sources({"retail_mart": mart}), tmp_path)
    cfg = _weekly_config(variant, model_input=INPUT)
    with pytest.raises(ValueError, match="the panel has both 'target' and 'source_target'"):
        save_model_input(cfg, ENTITY, env, spark)
    assert not Path(tmp_path, "input").exists()


def test_saved_candidates_read_a_source_eligible_like_the_frames(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
) -> None:
    """A spine carrying `eligible`: the saved table's candidate list, resolved without Spark,
    names it `source_eligible` as the frames read from the table do."""
    env = write_sources({"retail_mart": _weekly_mart(spark).withColumn("eligible", F.lit(1))})
    env = _with_input(env, tmp_path)
    cfg = _weekly_config(variant, model_input=INPUT)
    save_model_input(cfg, ENTITY, env, spark)
    frames = build_frames(cfg, ENTITY, env, spark, "eda")
    assert frames.meta["candidates"] == ["income", "source_eligible"]
    assert saved_candidates(cfg, ENTITY, env) == frames.meta["candidates"]


def test_saved_candidates_leave_out_a_built_target_column_named_target(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
) -> None:
    """A built target over the spine's `target` flag: the saved table's candidate list leaves
    `source_target` out as the lineage, as the frames read from the table do (§4.6)."""
    mart = _weekly_mart(spark).withColumnRenamed("cc_flag", "target")
    env = write_sources({"retail_mart": mart})
    env = _with_input(env, tmp_path)
    holders = {"name": "non_holders", "filter": "source_target = 0", "reason": "r"}
    cfg = _weekly_config(
        variant,
        model_input=INPUT,
        target={"column": "target"},
        eligibility={"analysis": [], "modelling": [holders]},
    )
    save_model_input(cfg, ENTITY, env, spark)
    assert saved_candidates(cfg, ENTITY, env) == ["income"]
    assert build_frames(cfg, ENTITY, env, spark, "eda").meta["candidates"] == ["income"]


def test_unknown_stage_null_validation_period_and_empty_frame_are_refused(
    spark: SparkSession,
    env: EnvironmentConfig,
    in_memory: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A stage the frames don't serve, the modelling frames of an EDA-only config (a null
    validation period, refused before the panel is built), and a frame with no row to collect
    fail loud."""
    with pytest.raises(ValueError, match="unknown stage 'scoring'; the frames serve"):
        build_frames(in_memory, ENTITY, env, spark, "scoring")
    eda_only = variant(data={"model_input": None}, time={"validation_period": None})
    for stage in ("training", "evaluation"):
        with pytest.raises(ValueError, match="time.validation_period is null: an EDA-only config"):
            build_frames(eda_only, ENTITY, env, spark, stage)
    with pytest.raises(ValueError, match="the frame 'x' is empty"):
        estimate_collect(spark.createDataFrame([], "unit_id int"), "x")
