"""The Feature Checks stage end to end on the unit preset (D-134, D-136, D-137): EDA then Feature
Checks on the card config (every candidate) and on a regression variant (a narrow candidate
list), each run once in a module fixture on this module's own data root, so its audit-log
entries reach no other test module. What a run must leave: every file and table of
`feature_checks/`, `feature_checks.json` with the keys Training and the report read, the ledger
with every Feature Checks column, the `flag` entries written once (a rerun writes only a `run`
entry, with the compared periods and never the validation period), a held feature released by a
`keep`, the refusals of a missing or stale EDA and of a ledger from another EDA run, a report
with plotly.js once and every section, a skipped step's null columns, and `run(..., stages=["eda",
"feature_checks"])`.
"""

import json
import re
import shutil
from collections.abc import Callable
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest
import yaml
from plotly.offline import get_plotlyjs
from pyspark.sql import SparkSession

from core_modelling.artifacts import StageResult, check_upstream, read_stage
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import read_entries, record_decision
from core_modelling.config.identities import data_definition_hash
from core_modelling.config.replay import open_flags
from core_modelling.eda import run_eda
from core_modelling.environment import EnvironmentConfig, audit_log_dir, feature_dir
from core_modelling.feature_checks import run_feature_checks
from core_modelling.feature_checks.findings import STEP_ORDER
from core_modelling.feature_checks.run import FEATURE_CHECKS_SETTINGS
from core_modelling.ledger import COLUMNS_BY_STAGE, read_ledger, resolve_features
from core_modelling.periods import period_spec
from core_modelling.run import run

ENTITY = "entity_a"
TABLES = {"findings", "unavailable", "per_period", "clusters", "proposed_decisions"}
META_KEYS = {"config_hash", "data_definition_hash", "resolved_input_hash", "replayed_to",
             "settings_digest", "settings", "compared_periods", "steps_run", "steps_skipped",
             "findings", "held", "entries_written", "eda_headline", "timings"}  # fmt: skip
HEADINGS = ["Summary", "Choices", "How to read", "EDA headline", "Warnings", "Flags and notes",
            "Held features", "Core", "Findings per step", "Quality", "Leakage", "Time alignment",
            "Stability", "Redundancy", "Proposed decisions", "Ledger with decisions", "Extended",
            "Per period", "Appendix",
            "Resolved config", "Decisions", "Entries written", "Timings"]  # fmt: skip
REGRESSION_CANDIDATES = ["age", "income", "segment", "onboarding_channel", "employment_status",
                         "cc_active_flag", "cc_bal*", "cc_limit", "spend_cc_*"]  # fmt: skip


@pytest.fixture(scope="module")
def env(unit_env: EnvironmentConfig, tmp_path_factory: pytest.TempPathFactory) -> EnvironmentConfig:
    """The unit environment on this module's own data root."""
    roots = unit_env.roots.model_copy(update={"data": str(tmp_path_factory.mktemp("fc_data"))})
    return unit_env.model_copy(update={"roots": roots})


@pytest.fixture(scope="module")
def card_cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The card config without a model input."""
    return variant(data={"model_input": None})


@pytest.fixture(scope="module")
def regression_cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """Card spend summed forward for holders, on a narrow candidate list (test_eda's)."""
    return variant(
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
        features={"candidates": {"include": REGRESSION_CANDIDATES, "exclude": []}},
    )


@pytest.fixture(scope="module")
def card(spark: SparkSession, env: EnvironmentConfig, card_cfg: UseCaseConfig) -> StageResult:
    """The card config's EDA, then its first Feature Checks run."""
    run_eda(card_cfg, ENTITY, env, spark)
    return run_feature_checks(card_cfg, ENTITY, env, spark)


@pytest.fixture(scope="module")
def regression(
    spark: SparkSession, env: EnvironmentConfig, regression_cfg: UseCaseConfig
) -> StageResult:
    """The regression variant's EDA, then its first Feature Checks run."""
    run_eda(regression_cfg, ENTITY, env, spark)
    return run_feature_checks(regression_cfg, ENTITY, env, spark)


@pytest.fixture(params=["card", "regression"])
def result(request: pytest.FixtureRequest) -> StageResult:
    """Each config's first run in turn."""
    return request.getfixturevalue(request.param)


def _files(cfg: UseCaseConfig, env: EnvironmentConfig, folder: Path) -> tuple[str, str]:
    """The config (without housekeeping: a file carries intent only) and the environment written
    as files in `folder`, for `record_decision` and `run`; the data definition is kept, so the
    file shares the audit log."""
    config_path, env_path = folder / "config.yml", folder / "environment.yml"
    config_path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json", exclude={"housekeeping"}), sort_keys=False)
    )
    env_path.write_text(yaml.safe_dump(env.model_dump(mode="json")))
    return str(config_path), str(env_path)


def test_the_folder_holds_every_file_and_table(result: StageResult) -> None:
    """`feature_checks/` holds the json, the log, the resolved config, the report and every
    table, and reads back whole; its digest passes the check Training runs, and every step ran."""
    folder = Path(result.paths["folder"])
    for name in ("feature_checks.json", "log.json", "resolved_config.yml", "report.html"):
        assert (folder / name).is_file(), name
    meta, tables = read_stage(str(folder), "feature_checks")
    assert set(tables) == TABLES and META_KEYS <= set(meta) and meta["stage"] == "feature_checks"
    check_upstream(meta, result.config, FEATURE_CHECKS_SETTINGS)
    assert meta["steps_run"] == STEP_ORDER and meta["steps_skipped"] == []
    assert meta["held"] == result.config.features.held


def test_the_ledger_holds_every_feature_checks_column(result: StageResult) -> None:
    """The saved ledger holds the identity, EDA and Feature Checks columns, its sidecar names the
    stage and its digest; `flags` and `notes` are the findings each feature raised."""
    folder = Path(result.paths["folder"]).parent
    ledger = read_ledger(str(folder), result.meta["data_definition_hash"])
    stages = ("identity", "eda", "feature_checks")
    assert ledger.columns.tolist() == [c for stage in stages for c in COLUMNS_BY_STAGE[stage]]
    sidecar = json.loads((folder / "_ledger.json").read_text())
    assert sidecar["stage"] == "feature_checks"
    assert sidecar["settings_digest"] == result.meta["settings_digest"]
    findings, read = (
        result.tables["findings"],
        ledger.loc[~(ledger["lineage"] | ledger["unsupported"])],
    )
    for kind, column in (("flag", "flags"), ("note", "notes")):
        raised = findings.loc[findings["kind"] == kind].groupby("feature")["finding"].agg(set)
        stored = {
            name: set(found) for name, found in zip(read["feature"], read[column], strict=True)
        }
        assert stored == {name: raised.get(name, set()) for name in read["feature"]}, column


def test_flag_entries_are_written_once_and_a_rerun_writes_a_run_entry(
    card: StageResult, card_cfg: UseCaseConfig, env: EnvironmentConfig, spark: SparkSession
) -> None:
    """The first run writes one `flag` entry per raised flag finding with its features, then one
    `run` entry listing the window, gap and latest periods, never the validation period; an
    unchanged rerun writes only a `run` entry and holds the same features."""
    log = audit_log_dir(env, card_cfg, ENTITY)
    entries = read_entries(log)[: len(card.meta["entries_written"])]  # the first run's
    findings = card.tables["findings"]
    flags = findings.loc[findings["kind"] == "flag"].groupby("finding")["feature"].agg(sorted)
    written = {entry.finding: entry.features for entry in entries if entry.op == "flag"}
    assert written == flags.to_dict() and entries[-1].op == "run"
    assert len(entries) == len(written) + 1 == len(card.meta["entries_written"])
    periods = card.meta["compared_periods"]
    assert entries[-1].periods == [*periods["window"], *periods["gap"], *periods["latest"]]
    validation = period_spec(card_cfg).label(card_cfg.time.validation_period)
    assert validation not in entries[-1].periods
    assert entries[-1].replayed_to == 0
    before = len(read_entries(log))
    rerun = run_feature_checks(card_cfg, ENTITY, env, spark)
    assert rerun.meta["entries_written"] == [{"seq": before + 1, "op": "run", "finding": None}]
    assert card.config.features.held == sorted(open_flags(entries))
    assert rerun.config.features.held == sorted(open_flags(read_entries(log)))


def test_a_keep_releases_the_held_feature(
    card: StageResult,
    card_cfg: UseCaseConfig,
    env: EnvironmentConfig,
    spark: SparkSession,
    tmp_path: Path,
) -> None:
    """A `keep` recorded on a held feature (every flag open on it) takes it out of the next run's
    held set and proposed decisions, and `resolve_features` gives it back to Training; the run
    writes no flag entry."""
    config_path, env_path = _files(card_cfg, env, tmp_path)
    assert data_definition_hash(card_cfg, ENTITY) == card.meta["data_definition_hash"]
    feature = card.config.features.held[0]
    record_decision(config_path, ENTITY, keep=[feature], reason="known", env_path=env_path)
    after = run_feature_checks(card_cfg, ENTITY, env, spark)
    assert feature in card.config.features.held and feature not in after.config.features.held
    assert feature in after.config.features.kept
    proposed = after.tables["proposed_decisions"]
    assert not any(feature in features for features in proposed["features"])
    assert feature in resolve_features(after.ledger, after.config)
    assert feature not in resolve_features(card.ledger, card.config)
    assert [entry["op"] for entry in after.meta["entries_written"]] == ["run"]


def test_a_missing_or_stale_eda_is_refused(
    card: StageResult,
    variant: Callable[..., UseCaseConfig],
    env: EnvironmentConfig,
    tmp_path: Path,
) -> None:
    """Without EDA's artifact the stage asks for an EDA run; with EDA run under another `eda.bins`
    it is refused naming the changed setting, before anything is written to the audit log."""
    empty = env.model_copy(update={"roots": env.roots.model_copy(update={"data": str(tmp_path)})})
    cfg = variant(data={"model_input": None})
    with pytest.raises(FileNotFoundError, match="run the eda stage first"):
        run_feature_checks(cfg, ENTITY, empty, None)
    other = variant(data={"model_input": None}, eda={"bins": 20})
    log = audit_log_dir(env, other, ENTITY)
    before = len(read_entries(log))
    with pytest.raises(ValueError, match=r"eda ran with eda = "):
        run_feature_checks(other, ENTITY, env, None)
    assert len(read_entries(log)) == before


def test_a_ledger_from_another_eda_run_is_refused(
    card: StageResult, card_cfg: UseCaseConfig, env: EnvironmentConfig, tmp_path: Path
) -> None:
    """A ledger whose `concordance_window` differs from `eda/`'s ranking for one read candidate
    (a crash between EDA's two writes) is refused, naming the feature and asking for EDA."""
    copy = env.model_copy(update={"roots": env.roots.model_copy(update={"data": str(tmp_path)})})
    shutil.copytree(env.roots.data, tmp_path, dirs_exist_ok=True)
    path = Path(feature_dir(copy, card_cfg, ENTITY), "ledger.parquet")
    ledger = pd.read_parquet(path)
    row = ledger.loc[~(ledger["lineage"] | ledger["unsupported"])].index[0]
    ledger.loc[row, "concordance_window"] += 0.001
    ledger.to_parquet(path)
    feature = ledger.loc[row, "feature"]
    with pytest.raises(ValueError, match=rf"different EDA runs.*{feature}.*rerun EDA"):
        run_feature_checks(card_cfg, ENTITY, copy, None)


def test_the_report_has_plotly_once_and_every_section(result: StageResult) -> None:
    """The report parses, embeds plotly.js once and carries every heading in order, with the
    hold-out sentence and the all-client warning."""
    text = Path(result.paths["report.html"]).read_text(encoding="utf-8")
    HTMLParser().feed(text)
    assert text.count(get_plotlyjs()[:300]) == 1
    headings = [unescape(h) for h in re.findall(r'<h[2-6] id="[^"]+">([^<]+)</h', text)]
    assert headings == HEADINGS
    plain = unescape(text)
    assert "acts as an excluded feature without a final decision" in plain
    assert "have seen the labels of the clients that later form the test split" in plain
    size = Path(result.paths["report.html"]).stat().st_size
    print(f"{result.config.task} report: {size:,} B")


def test_a_step_left_out_is_skipped_with_null_columns(
    regression: StageResult,
    regression_cfg: UseCaseConfig,
    env: EnvironmentConfig,
    spark: SparkSession,
) -> None:
    """A step left out of a present mapping is not run: no finding of it, its ledger columns null
    (the column set stays), no clusters, and the report says so; no flag entry is written."""
    raw = regression_cfg.model_dump()
    raw["feature_checks"]["redundancy"] = None
    out = run_feature_checks(UseCaseConfig.model_validate(raw), ENTITY, env, spark)
    assert out.meta["steps_skipped"] == ["redundancy"] and "redundancy" not in out.meta["steps_run"]
    assert "redundancy" not in set(out.tables["findings"]["step"]) and out.tables["clusters"].empty
    ledger = read_ledger(str(Path(out.paths["folder"]).parent))
    assert (
        ledger.columns.tolist()[-len(COLUMNS_BY_STAGE["feature_checks"]) :]
        == (COLUMNS_BY_STAGE["feature_checks"])
    )
    assert ledger[["cluster", "explained_by_others", "partners"]].isna().all().all()
    assert "Not run" in out.views["steps"]["redundancy"][0]
    assert [entry["op"] for entry in out.meta["entries_written"]] == ["run"]


def test_run_writes_both_folders(
    regression: StageResult, regression_cfg: UseCaseConfig, env: EnvironmentConfig, tmp_path: Path
) -> None:
    """`run(..., stages=["eda", "feature_checks"])` writes `eda/` and then `feature_checks/` for
    the config and returns their paths by use case."""
    config_path, env_path = _files(regression_cfg, env, tmp_path)
    out = run(config_path, env_path, stages=["eda", "feature_checks"], entity=ENTITY)[ENTITY]
    use_case = regression_cfg.use_case
    assert out["eda"][use_case]["folder"] == feature_dir(env, regression_cfg, ENTITY, "eda")
    folder = out["feature_checks"][use_case]["folder"]
    assert folder == feature_dir(env, regression_cfg, ENTITY, "feature_checks")
    meta = json.loads(Path(folder, "feature_checks.json").read_text())
    assert meta["steps_run"] == STEP_ORDER
