"""A null `time.validation_period`, an EDA-only config (config.md requirement 8; D-129, D-131):
every reader before Training takes the window's last period where it took the validation period.

On the unit preset (monthly, w = 3): the target source must reach the window's last period + w
and no further, a source ending earlier is refused naming `time.observation_window.last`; the
panel is prepared and passes the contract with the window's periods only; a model input saved
from a null and a dated config records the null and serves both through every meta reader; a
null reader whose window's last period + w is beyond the saved labels is refused naming that
period. A held name that is no column is refused like an excluded or a kept one.
"""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from pyspark.sql import DataFrame, SparkSession

from core_modelling.config import UseCaseConfig
from core_modelling.dataset import save_model_input
from core_modelling.dataset.model_input import (
    METADATA_FILE,
    read_model_input,
    read_model_input_metadata,
    saved_candidates,
)
from core_modelling.dataset.panel import load_panel, prepare_panel
from core_modelling.environment import EnvironmentConfig, Source
from core_modelling.periods import PERIODS, period_labels
from core_modelling.target_factory import load_targets, run_target_factory

ENTITY = "entity_a"
INPUT = "retail_acquisition_input"
MONTH = PERIODS["month"]
EDA_ONLY = "cc_eda_only"  # a second use case on the same sources, without a validation period


@pytest.fixture(scope="module")
def eda_only(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config as an EDA-only use case of its own: no validation period."""
    return variant(use_case=EDA_ONLY, time={"validation_period": None})


@pytest.fixture(scope="module")
def env(unit_env: EnvironmentConfig, tmp_path_factory: pytest.TempPathFactory) -> EnvironmentConfig:
    """The unit environment with the model input mapped to a temporary folder."""
    path = str(tmp_path_factory.mktemp("model_input_null_v") / ENTITY)
    sources = {**unit_env.sources[ENTITY], INPUT: Source(format="parquet", path=path)}
    return unit_env.model_copy(update={"sources": {ENTITY: sources}})


@pytest.fixture(scope="module")
def saved(
    spark: SparkSession, env: EnvironmentConfig, cc_config: UseCaseConfig, eda_only: UseCaseConfig
) -> dict:
    """The model input saved once from the dated skeleton and the EDA-only config; its sidecar."""
    path = save_model_input([cc_config, eda_only], ENTITY, env, spark)
    return json.loads(Path(path, METADATA_FILE).read_text())


def _eda_only_on(
    variant: Callable[..., UseCaseConfig], first: date | str, last: date | str
) -> UseCaseConfig:
    """The skeleton without a validation period, on the window `first` … `last`."""
    window = {"first": first, "last": last}
    return variant(time={"validation_period": None, "observation_window": window})


def _window_labels(cfg: UseCaseConfig) -> list[str]:
    """The labels of the config's observation window."""
    window = cfg.time.observation_window
    return period_labels(window.first, window.last, MONTH)


def _eligible_rows(log: list[dict]) -> dict:
    """The contract's per-period eligible rows from a preparation's log."""
    return next(entry for entry in log if entry.get("check") == "eligible_rows")["per_period"]


def test_target_source_must_reach_the_window_last_plus_w(
    spark: SparkSession,
    unit_env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A window ending w periods before the target source's last period is summarised, its
    labels known; one period later is refused naming the missing period and
    `time.observation_window.last`."""
    _, log = load_targets(cc_config, ENTITY, unit_env, spark)
    w, source_last = cc_config.time.target_window, log["periods"][-1]
    fits = MONTH.from_index(MONTH.index(source_last) - w)
    cfg = _eda_only_on(variant, fits, fits)
    summary = run_target_factory(cfg, ENTITY, unit_env, spark).per_period
    assert summary.iloc[-1]["period"] == "all"
    assert summary.loc[summary["period"] == MONTH.label(fits), "mean_target"].notna().all()
    late = MONTH.from_index(MONTH.index(fits) + 1)
    needed = MONTH.label(MONTH.from_index(MONTH.index(late) + w))
    with pytest.raises(
        ValueError,
        match=rf"lacks the periods \['{needed}'\].* to {needed} "
        r"\(time\.observation_window\.last \+ target_window\)",
    ):
        load_targets(_eda_only_on(variant, late, late), ENTITY, unit_env, spark)


@pytest.fixture(scope="module")
def loaded(
    spark: SparkSession, unit_env: EnvironmentConfig, eda_only: UseCaseConfig
) -> tuple[DataFrame, dict]:
    """The EDA-only config's panel, loaded once (lazy), with its meta."""
    panel, _, meta = load_panel([eda_only], ENTITY, unit_env, spark)
    return panel, meta


def test_null_validation_panel_passes_the_contract_on_the_window(
    loaded: tuple[DataFrame, dict], eda_only: UseCaseConfig
) -> None:
    """The panel is prepared and the contract checks the window's periods only; the meta
    records the null validation period."""
    panel, meta = loaded
    assert meta["targets"][EDA_ONLY]["validation_period"] is None
    _, log, _ = prepare_panel(panel, eda_only, ENTITY, meta["targets"])
    assert list(_eligible_rows(log)) == _window_labels(eda_only)


def test_held_name_that_is_no_column_is_refused(
    loaded: tuple[DataFrame, dict], variant: Callable[..., UseCaseConfig]
) -> None:
    """A held feature names a column of the sources, like an excluded or a kept one."""
    panel, meta = loaded
    held = variant(
        use_case=EDA_ONLY, time={"validation_period": None}, features={"held": ["no_such"]}
    )
    with pytest.raises(ValueError, match=r"features\.held names columns .*: \['no_such'\]"):
        prepare_panel(panel, held, ENTITY, meta["targets"])


def test_model_input_from_a_null_and_a_dated_config_serves_both(
    spark: SparkSession,
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    eda_only: UseCaseConfig,
    saved: dict,
) -> None:
    """The sidecar keeps `validation_period`, null for the EDA-only use case; every meta reader
    accepts it for both configs, and the EDA-only read checks the window's periods only."""
    targets = saved["targets"]
    assert targets[EDA_ONLY]["validation_period"] is None
    validation = MONTH.label(cc_config.time.validation_period)
    assert targets["cc_acquisition"]["validation_period"] == validation
    for cfg in (cc_config, eda_only):
        assert read_model_input_metadata(cfg, ENTITY, env)["use_cases"] == saved["use_cases"]
        assert "income" in saved_candidates(cfg, ENTITY, env)
    _, log, meta = read_model_input(eda_only, ENTITY, env, spark)
    assert list(_eligible_rows(log)) == _window_labels(eda_only)
    assert meta["candidates"] == saved_candidates(eda_only, ENTITY, env)
    _, log, _ = read_model_input(cc_config, ENTITY, env, spark)
    assert list(_eligible_rows(log)) == [*_window_labels(cc_config), validation]


def test_null_reader_beyond_the_saved_labels_or_periods_is_refused(
    env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    variant: Callable[..., UseCaseConfig],
    saved: dict,
) -> None:
    """A window whose last period + w is beyond the saved target source's last period is
    refused naming the window's last period; a window starting before the saved periods names
    the window's last period as the end of the periods it needs."""
    w = cc_config.time.target_window
    source_last = date.fromisoformat(saved["targets"]["cc_acquisition"]["target_last"])
    late = MONTH.from_index(MONTH.index(source_last) - w + 1)
    message = (
        f"the target source of 'cc_acquisition' ends at {MONTH.label(source_last)}, so labels "
        f"are known up to {MONTH.label(MONTH.from_index(MONTH.index(source_last) - w))}; "
        f"time.observation_window.last {MONTH.label(late)} needs it to reach "
        f"{MONTH.label(MONTH.from_index(MONTH.index(source_last) + 1))}; rebuild"
    )
    with pytest.raises(ValueError, match=message):
        read_model_input_metadata(_eda_only_on(variant, late, late), ENTITY, env)
    earlier = _eda_only_on(variant, "2025-02-01", "2025-08-01")
    with pytest.raises(ValueError, match=r"not 2025-02 \(.*\) … 2025-08 \(time\.observation_wi"):
        read_model_input_metadata(earlier, ENTITY, env)
