"""Evaluation's explanation tables: the contributions sum to the margin, an ignored feature has
a flat partial dependence, a feature null on every sample row leaves it, and the feature table's
flag, on small bundles fitted here (no Spark). Two tests run in real local Spark (their names
hold `spark`; the main thread runs them): the samples repeat, the permutation sample holds the
explanation sample's rows and the waterfall rows are marked, and the encoding shares equal a
pandas count. Permutation importance is `test_permutation.py`'s, the effect features
`test_effects.py`'s.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from test_bundle import (
    CALIBRATIONS,
    IDENTITY,
    KINDS,
    OBJECTIVES,
    ORDER,
    SEARCHED,
    SEED,
    bundle_content,
    raw_frame,
    targets,
)

from core_modelling.config import UseCaseConfig
from core_modelling.environment import EnvironmentConfig, Roots
from core_modelling.evaluation import explain
from core_modelling.evaluation.explain import (
    PDP_COLUMNS,
    all_null_features,
    collect_explanation_sample,
    compute_contributions,
    encoding_shares,
    feature_table,
    partial_dependence,
)
from core_modelling.model import load_bundle, score_frame
from core_modelling.model.bundle import Bundle, write_bundle
from core_modelling.model.encoder import encode_frame, fit_encoder
from core_modelling.model.families import FAMILIES
from core_modelling.model.scoring import score_spark
from core_modelling.run_artifacts import BASE_COLUMN, CONTRIBUTION_SUFFIX
from core_modelling.sources import KEYS

# `flat` is constant in train, so no family splits on it: the feature the model ignores
FEATURES = ["income", "flat", "channel", "rating", "age"]
FLAT_KINDS = {**KINDS, "flat": "numeric"}


def _with_flat(frame: pd.DataFrame, constant: bool) -> pd.DataFrame:
    """`frame` with `flat`: 1.0 everywhere (train), or varied values the model never split on."""
    values = np.ones(len(frame)) if constant else np.random.default_rng(3).normal(size=len(frame))
    return frame.assign(flat=values)


def _bundle(tmp_path: Path, family: str = "lgbm", task: str = "binary") -> Bundle:
    """A bundle fitted on `raw_frame` with the ignored `flat`, written and loaded back."""
    frame = _with_flat(raw_frame(), constant=True)
    encoder = fit_encoder(frame, FEATURES, FLAT_KINDS, ORDER, 50, "native")
    encoded, _ = encode_frame(frame, encoder)
    power = 1.5 if OBJECTIVES[task] == "tweedie" else None
    fixed = FAMILIES[family].fixed_params(task, OBJECTIVES[task], encoder, {}, SEED, 1, power)
    booster = FAMILIES[family].fit(
        encoded, targets(frame, task), {**fixed, **SEARCHED[family]}, task
    )
    folder = str(tmp_path / f"bundle_{family}_{task}")
    content = bundle_content(encoder, task, family, CALIBRATIONS[task])
    write_bundle(folder, family, booster, content, IDENTITY)
    return load_bundle(folder)


def _sample(bundle: Bundle, rows: int = 400) -> pd.DataFrame:
    """An explanation sample as collected: keys, the raw features (`flat` varied), the target,
    the scores and an empty `waterfall`."""
    frame = _with_flat(raw_frame(rows, seed=1), constant=False)
    frame = frame.assign(period=date(2024, 1, 1), target=targets(frame, bundle.task))
    frame = pd.concat([frame, score_frame(bundle, frame)], axis=1)
    return frame.assign(waterfall=None)[[*KEYS, *FEATURES, "target", "margin", "score_raw",
                                         "score", "waterfall"]]  # fmt: skip


@pytest.mark.parametrize(
    ("family", "task"),
    [("lgbm", "binary"), ("xgboost", "binary"), ("catboost", "binary"), ("lgbm", "regression")],
)
def test_contributions_sum_to_the_margin_in_trainings_shape(
    family: str, task: str, tmp_path: Path
) -> None:
    """Each family's contributions and base value sum to the stored margin, in the columns of
    Training's explanation sample; the ignored feature contributes nothing; a sample whose
    margin is not its rows' is refused."""
    bundle = _bundle(tmp_path, family, task)
    sample = _sample(bundle)
    out = compute_contributions(bundle, sample)
    names = [f"{name}{CONTRIBUTION_SUFFIX}" for name in FEATURES]
    assert list(out.columns[: len(KEYS) + 2 * len(FEATURES) + 1]) == [
        *KEYS, *FEATURES, *names, BASE_COLUMN
    ]  # fmt: skip
    total = out[[*names, BASE_COLUMN]].sum(axis=1)
    np.testing.assert_allclose(total, sample["margin"], rtol=1e-5, atol=1e-5)
    assert (out[f"flat{CONTRIBUTION_SUFFIX}"] == 0).all()
    with pytest.raises(ValueError, match="differ from the stored margin"):
        compute_contributions(bundle, sample.assign(margin=sample["margin"] + 1.0))


def test_the_partial_dependence_of_an_ignored_feature_is_flat(tmp_path: Path) -> None:
    """Sweeping `flat` over its sample quantiles moves no score, on the mean and on every ICE
    line; `income` moves it; a categorical's points carry level text, not values."""
    bundle = _bundle(tmp_path, task="regression")
    table = partial_dependence(bundle, _sample(bundle), ["flat", "income", "channel"])
    flat = table[table["feature"] == "flat"]
    assert flat["point"].nunique() > 10
    assert flat.groupby("row", dropna=False)["score"].nunique().eq(1).all()
    income = table[(table["feature"] == "income") & (table["curve"] == "pdp")]
    assert income["score"].nunique() > 1 and income["row"].isna().all()
    channel = table[table["feature"] == "channel"]
    assert channel["value"].isna().all() and set(channel["level"]) <= {"branch", "online", "phone"}
    assert table.loc[table["curve"] == "ice", "row"].nunique() == explain.ICE_ROWS


def test_the_partial_dependence_of_a_feature_the_bundle_lacks_is_refused(tmp_path: Path) -> None:
    """A feature name that is none of the bundle's is refused, naming it, before any scoring."""
    bundle = _bundle(tmp_path, task="regression")
    with pytest.raises(ValueError, match=r"the bundle has no features \['tenure'\]"):
        partial_dependence(bundle, _sample(bundle), ["income", "tenure"])


def test_a_feature_null_on_every_sample_row_leaves_the_partial_dependence(tmp_path: Path) -> None:
    """`income` null on every sample row has no grid: it is named before anything runs, the
    partial dependence of the rest is computed, and of no feature it is an empty table with its
    columns; asked for anyway, it fails loud."""
    bundle = _bundle(tmp_path, task="regression")
    sample = _sample(bundle).assign(income=np.nan)
    assert all_null_features(sample, ["flat", "income", "channel"]) == ["income"]
    table = partial_dependence(bundle, sample, ["flat", "channel"])
    assert set(table["feature"]) == {"flat", "channel"}
    empty = partial_dependence(bundle, sample, [])
    assert empty.empty and list(empty.columns) == PDP_COLUMNS
    with pytest.raises(ValueError, match="null on every sample row"):
        partial_dependence(bundle, sample, ["income"])


def test_the_feature_table_flags_nulls_at_scoring_that_train_never_had() -> None:
    """`b` has no null in train and some on validation: flagged; `a` had nulls in train."""
    ledger = pd.DataFrame(
        {"feature": ["a", "b", "c"], "selected": [True, True, False], "null_share": [0.1, 0.0, 0]}
    )
    contributions = pd.DataFrame({"a__contribution": [0.3, -0.3], "b__contribution": [0.1, 0.0]})
    shares = pd.DataFrame(
        {
            "part": ["test", "test", "validation", "validation"],
            "feature": ["a", "b", "a", "b"],
            "rows": [10, 10, 5, 5],
            "null_share": [0.2, 0.0, 0.2, 0.4],
            "unseen_share": [np.nan, np.nan, np.nan, np.nan],
        }
    )
    table = feature_table(contributions, shares, ledger).set_index("feature")
    assert list(table.index) == ["a", "b"]
    assert table["contribution_share"].tolist() == pytest.approx([0.3 / 0.35, 0.05 / 0.35])
    assert table["null_not_in_train"].tolist() == [False, True]
    assert table.loc["b", "null_share_validation"] == 0.4
    unknown = ledger.assign(null_share=[0.1, np.nan, 0])
    with pytest.raises(ValueError, match=r"no train null_share for the features \['b'\]"):
        feature_table(contributions, shares, unknown)


def _spark_rows(spark: SparkSession, bundle: Bundle) -> tuple[pd.DataFrame, object]:
    """Evaluation-like rows: 300 test rows and 100 validation rows (some with a channel and a
    rating unseen in train), as pandas and as a Spark frame."""
    frame = _with_flat(raw_frame(400, seed=2), constant=False)
    frame["part"] = np.where(np.arange(400) < 300, "test", "validation")
    frame["period"] = np.where(frame["part"] == "test", date(2024, 1, 1), date(2024, 6, 1))
    frame.loc[frame.index[-10:], "channel"] = "fax"
    frame.loc[frame.index[-5:], "rating"] = "D"
    frame["target"] = targets(frame, bundle.task)
    frame = frame[[*KEYS, "part", *FEATURES, "target"]]
    return frame, spark.createDataFrame(frame)


def test_spark_the_samples_repeat_and_the_waterfall_rows_are_marked(
    spark: SparkSession, cc_config: UseCaseConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two collects give the same rows; the permutation sample is the first 120 test rows by the
    hash and the explanation sample's 50 sampled rows are the first of them; the highest test
    score and the score nearest the cut are marked, and one typical row among the sampled ones;
    no validation row is taken; the collect's rows were known before it."""
    monkeypatch.setattr(explain, "EXPLANATION_ROWS", 50)
    monkeypatch.setattr(explain, "PERMUTATION_ROWS", 120)
    bundle = _bundle(tmp_path)
    _, rows = _spark_rows(spark, bundle)
    scores = score_spark(str(tmp_path / "bundle_lgbm_binary"), rows, [*KEYS, "part"])
    test = scores.where("part = 'test'").toPandas()
    cut = float(test["score"].quantile(0.9))
    env = EnvironmentConfig(schema_version=1, roots=Roots(data=str(tmp_path)))
    first, permuted, entry = collect_explanation_sample(rows, scores, cc_config, env, cut)
    second, again, _ = collect_explanation_sample(rows, scores, cc_config, env, cut)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(permuted, again)
    assert (first["part"] == "test").all() and (permuted["part"] == "test").all()
    assert len(permuted) == 120 and list(permuted.columns) == rows.columns
    assert int(first["sampled"].sum()) == 50 and 50 <= len(first) <= 52
    keys = set(permuted[KEYS].itertuples(index=False, name=None))
    sampled = first.loc[first["sampled"], KEYS].itertuples(index=False, name=None)
    assert set(sampled) <= keys
    assert entry["frame"] == "explanation_sample"
    picked = first.loc[first["waterfall"].isin(["highest", "cut"]), KEYS]
    outside = [key for key in picked.itertuples(index=False, name=None) if key not in keys]
    assert entry["rows"] == 120 + len(outside)
    marked = first.set_index("waterfall")
    assert first["waterfall"].value_counts().to_dict() == {"highest": 1, "cut": 1, "typical": 1}
    assert marked.loc["typical", "sampled"]
    assert marked.loc["highest", "score"] == test["score"].max()
    assert abs(marked.loc["cut", "score"] - cut) == (test["score"] - cut).abs().min()


def test_spark_encoding_shares_equal_a_pandas_count(spark: SparkSession, tmp_path: Path) -> None:
    """Per part and feature, the rows, the null share and the unseen share (a channel or a
    rating train never had) equal a count on the collected rows."""
    bundle = _bundle(tmp_path)
    frame, rows = _spark_rows(spark, bundle)
    shares = encoding_shares(rows, bundle).set_index(["part", "feature"])
    seen = {"channel": {"branch", "online", "phone"}, "rating": {"A", "B", "C"}}
    for (part, name), row in shares.iterrows():
        values = frame.loc[frame["part"] == part, name]
        assert row["rows"] == len(values)
        assert row["null_share"] == pytest.approx(values.isna().mean())
        if name in seen:
            unseen = values.notna() & ~values.isin(seen[name])
            assert row["unseen_share"] == pytest.approx(unseen.mean())
        else:
            assert pd.isna(row["unseen_share"])
    assert len(shares) == 2 * len(FEATURES)
