"""The modelling chain's acceptance tests on the `dev` preset (evaluation.md "How it is checked",
D-100 (e); marker `acceptance`, A59).

The card config runs through Training and Evaluation three times, each on its own copy of the
data-definition folder `dev_stage2` left (EDA, Feature Checks, the ledger and the audit log), so
a person's decision in one run never reaches another and the shared folder stays as it was:

1. the plain run (`lgbm`, 15 trials, A59): the model beats the single-feature baseline on
   validation, its validation AUC is not above the oracle's by more than two standard errors,
   and its observed to expected is within 10%;
2. the leak run: a person keeps the card's strongest leak trap (a `keep` entry in the audit
   log), and the oracle is beaten, so the oracle check can fail;
3. the downsampled run (`negative_downsampling`): observed to expected is within 10% again.

The standard error is read from the client-bootstrap interval at `REPLICATES` replicates (see
there). The oracle's AUC is the truth's window probability of the card target against the
scores table's own target, on the scores' validation rows.

Measured on the 8 GB laptop: 6 min 45 s with `test_traps.py`, which shares `dev_stage2`.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

import pandas as pd
import pytest
import yaml
from conftest import DEV_CONFIGS, ENTITY, with_evaluation, with_training
from pyspark.sql import SparkSession

from core_modelling.artifacts import StageResult
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import record_decision
from core_modelling.environment import feature_dir, load_environment, models_dir
from core_modelling.evaluation import run_evaluation
from core_modelling.statistics.score_cells import POOLED
from core_modelling.training import run_training
from synthetic.output import read_output
from synthetic.truth.oracle import auc, target_columns, window_probability

pytestmark = pytest.mark.acceptance

CARD = DEV_CONFIGS[0]  # the card config, `cc_config`'s file
TARGET = "cc_acquire"  # the truth's target the card config models
SEARCH = {"estimator_list": ["lgbm"], "max_iter": 15}  # the autonomous share of one family (A59)
# 100 replicates put each end of the 95% percentile interval between the 2nd and 3rd draw from
# the edge: the standard error read from its width is then within about 10% (one standard
# deviation), so the two-error bound moves by about 0.2 of an error; 20, the schema's least,
# leaves about 22%. The cells grow with the replicates, and at dev's size 100 stay cheap.
REPLICATES = 100
DOWNSAMPLING = {"method": "negative_downsampling", "keep_fraction": 0.25}
STANDARD_ERRORS = 2
OBSERVED_TO_EXPECTED_TOLERANCE = 0.10


@dataclass(frozen=True)
class Evaluated:
    """One trained and evaluated run: Training's and Evaluation's results and the folder of its
    scores table."""

    training: StageResult
    evaluation: StageResult
    scores: str


@pytest.fixture(scope="module")
def card(cc_config: UseCaseConfig) -> UseCaseConfig:
    """The card config with `SEARCH` and `REPLICATES`."""
    trained = with_training(cc_config, **SEARCH)
    return with_evaluation(trained, intervals={"replicates": REPLICATES})


def _copy_stage2(dev_env_file: str, checks_folder: str, cfg: UseCaseConfig, root: Path) -> str:
    """An environment file under `root` whose data root is `root/data` and whose sources are the
    dev environment's (so the sources' identity the stages recorded still holds), with a copy of
    the data-definition folder holding `checks_folder` (Feature Checks' folder of `dev_stage2`)
    at the same place under the new root. Returns the file's path."""
    content = yaml.safe_load(Path(dev_env_file).read_text())
    content["roots"]["data"] = str(root / "data")
    path = root / "environment.yml"
    path.write_text(yaml.safe_dump(content))
    copy = feature_dir(load_environment(str(path)), cfg, ENTITY)
    shutil.copytree(Path(checks_folder).parent, copy)
    return str(path)


def _train_and_evaluate(cfg: UseCaseConfig, env_path: str, spark: SparkSession) -> Evaluated:
    """Training of `cfg` on the environment at `env_path`, then Evaluation of that run."""
    env = load_environment(env_path)
    training = run_training(cfg, ENTITY, env, spark)
    run_id = training.meta["run_id"]
    evaluation = run_evaluation(cfg, ENTITY, env, spark, run_id)
    scores = models_dir(env, evaluation.config, run_id, "evaluation", "scores")
    return Evaluated(training, evaluation, scores)


@pytest.fixture(scope="module")
def evaluated(
    spark: SparkSession,
    dev_env_file: str,
    dev_stage2: dict[str, str],
    card: UseCaseConfig,
    tmp_path_factory: pytest.TempPathFactory,
) -> Evaluated:
    """The plain run: `card` trained and evaluated on its own copy of `dev_stage2`."""
    root = tmp_path_factory.mktemp("acceptance_plain")
    env_path = _copy_stage2(dev_env_file, dev_stage2[card.use_case], card, root)
    return _train_and_evaluate(card, env_path, spark)


@pytest.fixture(scope="module")
def evaluated_leak(
    spark: SparkSession,
    dev_env_file: str,
    dev_stage2: dict[str, str],
    dev_output: tuple[str, dict],
    card: UseCaseConfig,
    tmp_path_factory: pytest.TempPathFactory,
) -> Evaluated:
    """The leak run: on its own copy of `dev_stage2`, a person keeps `_leak_column` (a `keep`
    entry in the audit log, settling its open flags), then `card` is trained and evaluated."""
    root = tmp_path_factory.mktemp("acceptance_leak")
    env_path = _copy_stage2(dev_env_file, dev_stage2[card.use_case], card, root)
    record_decision(CARD, ENTITY, keep=[_leak_column(dev_output[1])], env_path=env_path,
                    reason="kept on purpose: the acceptance test's leak")  # fmt: skip
    return _train_and_evaluate(card, env_path, spark)


@pytest.fixture(scope="module")
def evaluated_downsampled(
    spark: SparkSession,
    dev_env_file: str,
    dev_stage2: dict[str, str],
    card: UseCaseConfig,
    tmp_path_factory: pytest.TempPathFactory,
) -> Evaluated:
    """The downsampled run: `card` with `DOWNSAMPLING`, trained and evaluated on its own copy of
    `dev_stage2`; its test reads no interval, so the schema's fewest replicates do."""
    sampled = with_training(card, sampling=DOWNSAMPLING)
    cfg = with_evaluation(sampled, intervals={"replicates": 20})
    root = tmp_path_factory.mktemp("acceptance_downsampled")
    env_path = _copy_stage2(dev_env_file, dev_stage2[cfg.use_case], cfg, root)
    return _train_and_evaluate(cfg, env_path, spark)


@pytest.fixture(scope="module")
def oracle_chance(dev_output: tuple[str, dict], cc_config: UseCaseConfig) -> pd.DataFrame:
    """The truth's window probability of `TARGET` over the config's target window at the
    validation period, one row per client the mart holds then: `unit_id` (the client id as a
    string, as the scores hold it) and `chance`, null where the truth has no target (not
    eligible, or the client leaves within the window)."""
    out_dir, truth = dev_output
    mart_columns, oracle_columns = target_columns(TARGET)
    mart = read_output(out_dir, "mart", mart_columns)
    oracle = read_output(out_dir, "oracle", oracle_columns)
    chance = window_probability(mart, oracle, truth, TARGET, cc_config.time.target_window)
    month = pd.to_datetime(mart["snapshot_month"]).dt.strftime("%Y-%m")
    at = month == pd.Timestamp(cc_config.time.validation_period).strftime("%Y-%m")
    return pd.DataFrame({"unit_id": mart.loc[at, "client_id"].astype(str), "chance": chance[at]})


def _leak_column(truth: dict) -> str:
    """The card target's strongest leak trap, found from the truth's trap list (never by name):
    the `leak` row with the highest univariate AUC."""
    leaks = [trap for trap in truth["spec"]["traps"] if trap["kind"] == "leak"
             and trap["target"] == TARGET and "auc" in trap["parameters"]]  # fmt: skip
    assert leaks, f"the truth lists no {TARGET} leak with an AUC"
    return max(leaks, key=lambda trap: trap["parameters"]["auc"])["column"]


def _pooled(result: StageResult, metric: str, part: str) -> pd.Series:
    """The metrics table's row of `metric` on `part`, pooled over its periods and without a
    stratum: `value`, `low`, `high`, …"""
    table = result.tables["metrics"]
    row = table.loc[(table["metric"] == metric) & (table["part"] == part)
                    & (table["period"] == POOLED) & table["stratum"].isna()]  # fmt: skip
    assert len(row) == 1, f"{len(row)} pooled {metric} rows on {part}"
    return row.iloc[0]


def _standard_error(row: pd.Series, level: float) -> float:
    """A metric's standard error from its client-bootstrap percentile interval at `level`:
    (high − low) / (2 z), z the standard normal quantile at (1 + level) / 2 (1.96 at 95%), as a
    normal interval of that width would give."""
    return float((row["high"] - row["low"]) / (2 * NormalDist().inv_cdf((1 + level) / 2)))


def _oracle_auc(scores: str, chance: pd.DataFrame) -> float:
    """The oracle's AUC on the scores' validation rows: the truth's window probability against
    the scores table's own target, matched by client (the part holds the validation period
    alone). Fails when a scored row has no probability, so both sides cover the same rows."""
    rows = pd.read_parquet(scores, columns=["unit_id", "target"],
                           filters=[("part", "==", "validation")])  # fmt: skip
    joined = rows.astype({"unit_id": str}).merge(chance, on="unit_id", how="left")
    unmatched = int(joined["chance"].isna().sum())
    assert unmatched == 0, f"{unmatched} of {len(joined)} validation rows have no oracle chance"
    assert joined["target"].notna().all(), "a scored validation row has no target"
    return auc(joined["chance"].to_numpy(), joined["target"].to_numpy())


def _auc_against_oracle(run: Evaluated, chance: pd.DataFrame) -> tuple[float, float, float]:
    """`(the model's pooled validation AUC, the oracle's on the same rows, the model's standard
    error)`."""
    row = _pooled(run.evaluation, "roc_auc", "validation")
    level = run.evaluation.config.evaluation.intervals.level
    return float(row["value"]), _oracle_auc(run.scores, chance), _standard_error(row, level)


def test_the_model_beats_the_single_feature_baseline_on_validation(evaluated: Evaluated) -> None:
    """The model adds something: its validation AUC is above the single-feature baseline's (the
    train-chosen feature with the highest concordance, both from the baselines table). A failure
    means the search, selection or encoding loses what one feature alone ranks, or the single
    feature was not chosen."""
    table = evaluated.evaluation.tables["baselines"]
    on = table.loc[(table["part"] == "validation") & (table["metric"] == "roc_auc")]
    on = on.set_index("scorer")
    assert on.at["single_feature", "unavailable"] == "", on.at["single_feature", "unavailable"]
    model, single = on.at["model", "value"], on.at["single_feature", "value"]
    assert model > single, f"validation AUC: model {model:.4f}, single feature {single:.4f}"


def test_the_validation_auc_is_not_above_the_oracle(
    evaluated: Evaluated, oracle_chance: pd.DataFrame
) -> None:
    """No leak passes: the model's validation AUC ≤ the oracle's on the same rows + 2 standard
    errors (the model's, from its bootstrap interval). The oracle knows the true chance, so a
    model above it by more than chance allows has read the future. A failure means a leak
    reached the model (a held flag that let a feature through, a target column in the
    candidates) or the scores' rows or labels differ from the truth's."""
    model, oracle, error = _auc_against_oracle(evaluated, oracle_chance)
    bound = oracle + STANDARD_ERRORS * error
    assert model <= bound, f"validation AUC {model:.4f} > oracle {oracle:.4f} + 2 × {error:.4f}"


def test_a_kept_leak_beats_the_oracle(
    evaluated_leak: Evaluated, oracle_chance: pd.DataFrame, dev_output: tuple[str, dict]
) -> None:
    """The oracle check can fail: with the strongest leak trap kept by a person, the leak
    reaches the model and its validation AUC > the oracle's + 2 standard errors. A failure
    means the check above could pass with a leak in the model (the bound too loose, or the
    oracle's AUC read on other rows), or the keep did not bring the feature into training."""
    leak = _leak_column(dev_output[1])
    assert leak in evaluated_leak.training.meta["final_features"], f"{leak} is not in the model"
    model, oracle, error = _auc_against_oracle(evaluated_leak, oracle_chance)
    bound = oracle + STANDARD_ERRORS * error
    assert model > bound, f"validation AUC {model:.4f} ≤ oracle {oracle:.4f} + 2 × {error:.4f}"


@pytest.mark.parametrize(
    "name, method",
    [("evaluated", None), ("evaluated_downsampled", DOWNSAMPLING["method"])],
)
def test_observed_to_expected_is_within_ten_percent(
    name: str, method: str | None, request: pytest.FixtureRequest
) -> None:
    """The calibration level, and with downsampling the prior-shift offset: on the test part,
    pooled, the events over the summed score are within 10% of 1. Test shares the training
    window, so a moving base rate (reported per period, never corrected) cannot explain a miss;
    validation is not asserted for that reason. A failure without sampling means the
    calibration step misses the level; with it, that the offset is wrong or not applied."""
    run: Evaluated = request.getfixturevalue(name)
    assert run.training.meta["sampling"]["method"] == method, run.training.meta["sampling"]
    ratio = float(_pooled(run.evaluation, "observed_to_expected", "test")["value"])
    assert abs(ratio - 1) <= OBSERVED_TO_EXPECTED_TOLERANCE, f"observed to expected {ratio:.3f}"
