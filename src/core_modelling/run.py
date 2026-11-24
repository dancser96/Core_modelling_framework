"""`run`: the stages of one or several use cases from their configs, in order (D-024).

`STAGES` maps a stage name to the function that runs it for one entity over the list of
configs; `run` loads every config and the environment, opens the Spark session and runs the
asked stages for the asked entities. Target Factory prints its summary per use case and saves
the model input, one table for every config given, when the configs name one (D-131; the Stage 1
addendum, section B). EDA and then Feature Checks run per config and return the paths they wrote
(`eda/`, `feature_checks/`, each with its report); each resolves the config itself (the audit log
replayed, D-125), and Feature Checks reads EDA's artifacts, so it runs after EDA. Training trains
one numbered run per config and returns the paths of its `training/` folder; at `autonomous` it
first runs whichever of EDA and Feature Checks has not run on the config's data definition
(D-132). Evaluation evaluates per config the latest trained run of its data definition, or
the run named (`run=`, with Evaluation alone and one config), and returns the paths of its
`evaluation/` folder. The later stages arrive with M2.4.
"""

from collections.abc import Callable
from functools import partial
from pathlib import Path

from pyspark.sql import SparkSession

from core_modelling import ledger
from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.audit_log import resolve_config
from core_modelling.dataset import save_model_input
from core_modelling.eda import run_eda
from core_modelling.environment import EnvironmentConfig, get_spark_session, load_environment
from core_modelling.evaluation import run_evaluation
from core_modelling.feature_checks import run_feature_checks
from core_modelling.target_factory import run_target_factory
from core_modelling.training import run_training

Stage = Callable[[list[UseCaseConfig], str, EnvironmentConfig, SparkSession], dict]


def _run_target_factory_stage(
    cfgs: list[UseCaseConfig], entity: str, env: EnvironmentConfig, spark: SparkSession
) -> dict:
    """Every config's target summary (by use case), then the one model input saved when the
    configs name one."""
    # The target source is read twice on purpose: the summary first, so a refused target is
    # reported before anything is written, then once more inside the save.
    out = {"summary": {cfg.use_case: run_target_factory(cfg, entity, env, spark) for cfg in cfgs}}
    if any(cfg.data.model_input is not None for cfg in cfgs):
        out["model_input"] = save_model_input(cfgs, entity, env, spark)
    return out


def _run_eda_stage(
    cfgs: list[UseCaseConfig], entity: str, env: EnvironmentConfig, spark: SparkSession
) -> dict:
    """Every config's EDA, by use case: the paths it wrote. The result itself is not kept, so
    one config's snapshot is freed before the next is collected."""
    return {cfg.use_case: run_eda(cfg, entity, env, spark).paths for cfg in cfgs}


def _run_feature_checks_stage(
    cfgs: list[UseCaseConfig], entity: str, env: EnvironmentConfig, spark: SparkSession
) -> dict:
    """Every config's Feature Checks, by use case: the paths it wrote."""
    return {cfg.use_case: run_feature_checks(cfg, entity, env, spark).paths for cfg in cfgs}


STAGE2_RUNNERS = {"eda": run_eda, "feature_checks": run_feature_checks}


def _run_training_stage(
    cfgs: list[UseCaseConfig], entity: str, env: EnvironmentConfig, spark: SparkSession
) -> dict:
    """Every config's Training, by use case: the paths it wrote. At `autonomous` a config whose
    EDA or Feature Checks artifacts are missing gets them first, in that order (D-132): what is
    missing is looked up again after each, since an EDA run removes Feature Checks' folder. At
    `assisted`, and for stale artifacts at both levels, `run_training` refuses."""
    out = {}
    for cfg in cfgs:
        resolved = resolve_config(cfg, entity, env)
        if resolved.automation_level == "autonomous":
            for stage in ledger.STAGES:
                if stage in ledger.missing_stage2(resolved, entity, env):
                    print(f"run {stage} for {entity} first: training needs it (autonomous)")
                    STAGE2_RUNNERS[stage](cfg, entity, env, spark)
        out[cfg.use_case] = run_training(cfg, entity, env, spark).paths
    return out


def _run_evaluation_stage(
    cfgs: list[UseCaseConfig],
    entity: str,
    env: EnvironmentConfig,
    spark: SparkSession,
    run: str | None = None,
) -> dict:
    """Every config's Evaluation, by use case: the paths it wrote. `run` names the run to
    evaluate (given with one config only), else each config's latest trained run is."""
    return {cfg.use_case: run_evaluation(cfg, entity, env, spark, run).paths for cfg in cfgs}


STAGES: dict[str, Stage] = {
    "target_factory": _run_target_factory_stage,
    "eda": _run_eda_stage,
    "feature_checks": _run_feature_checks_stage,
    "training": _run_training_stage,
    "evaluation": _run_evaluation_stage,
}  # the run order
# What `run` runs when no stage is named: the stages built today. Frozen from 1.0, so a stage
# built later runs only when named and an unchanged `run <config>` keeps doing the same
DEFAULT_STAGES = ("target_factory", "eda", "feature_checks", "training", "evaluation")


def _entities(cfgs: list[UseCaseConfig], entity: str | None) -> list[str]:
    """The entities to run: the one given, which every config must list, else the first
    config's, which every other config must list exactly (a config's extra entity would
    otherwise be skipped quietly)."""
    first = cfgs[0]
    if entity is not None:
        for cfg in cfgs:
            if entity not in cfg.entities:
                raise ValueError(
                    f"unknown entity {entity!r}: the config {cfg.use_case!r} has "
                    f"{sorted(cfg.entities)}"
                )
        return [entity]
    for cfg in cfgs[1:]:
        if sorted(cfg.entities) != sorted(first.entities):
            raise ValueError(
                f"the configs {first.use_case!r} and {cfg.use_case!r} list different entities "
                f"({sorted(first.entities)} vs {sorted(cfg.entities)}); give the entity to run, "
                "or list the same entities in every config"
            )
    return list(first.entities)


def run(
    config_paths: str | Path | list[str | Path],
    env_path: str | None = None,
    stages: list[str] | None = None,
    entity: str | None = None,
    run: str | None = None,
) -> dict:
    """The stages (default: `DEFAULT_STAGES`, frozen from 1.0; a stage built later runs only
    when named) for the entities (the one given, which every config must list; default: the configs'
    entities, which must agree) of one config or a list; per entity and stage, what the stage
    returned. `run` names the trained run Evaluation evaluates (`r007`): it is accepted with
    `stages=["evaluation"]` and one config only, and refused before anything runs otherwise.

    The asked stages run in `STAGES` order, whatever order they are given in, so
    `stages=["feature_checks", "eda"]` refreshes EDA before Feature Checks reads it.
    """
    asked = list(stages or DEFAULT_STAGES)
    unknown = [stage for stage in asked if stage not in STAGES]
    if unknown:
        raise ValueError(f"unknown stages {unknown}; the built stages: {list(STAGES)}")
    stages = [stage for stage in STAGES if stage in asked]
    paths = [config_paths] if isinstance(config_paths, str | Path) else list(config_paths)
    if not paths:
        raise ValueError("run needs at least one config")
    if run is not None and (stages != ["evaluation"] or len(paths) != 1):
        raise ValueError(
            f"run={run!r} names one trained run: give it with stages=['evaluation'] and one "
            f"config; got the stages {stages} and {len(paths)} configs"
        )
    cfgs = [load_config(path) for path in paths]
    entities = _entities(cfgs, entity)
    env = load_environment(env_path)
    spark = get_spark_session(env)
    out: dict[str, dict] = {}
    for name in entities:
        out[name] = {}
        for stage in stages:
            print(f"run {stage} for {name}")
            runner = STAGES[stage] if run is None else partial(STAGES[stage], run=run)
            out[name][stage] = runner(cfgs, name, env, spark)
    return out
