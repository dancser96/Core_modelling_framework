"""`run`: the stages of one or several use cases from their configs, in order (D-024).

`STAGES` maps a stage name to the function that runs it for one entity over the list of
configs; `run` loads every config and the environment, opens the Spark session and runs the
asked stages for the asked entities. Stage 1 has one stage: Target Factory, whose summary is
printed per use case and whose model input, one table for every config given, is saved when
the configs name one (D-131; the Stage 1 addendum, section B). The later stages take the
resolved config (the audit log replayed, D-125) and arrive with M2.2–M2.4.
"""

from collections.abc import Callable
from pathlib import Path

from pyspark.sql import SparkSession

from core_modelling.config import UseCaseConfig, load_config
from core_modelling.dataset import save_model_input
from core_modelling.environment import EnvironmentConfig, get_spark_session, load_environment
from core_modelling.target_factory import run_target_factory

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


STAGES: dict[str, Stage] = {"target_factory": _run_target_factory_stage}


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
) -> dict:
    """The stages (default: all built) for the entities (the one given, which every config
    must list; default: the configs' entities, which must agree) of one config or a list, in
    order; per entity and stage, what the stage returned."""
    stages = list(stages or STAGES)
    unknown = [stage for stage in stages if stage not in STAGES]
    if unknown:
        raise ValueError(f"unknown stages {unknown}; the built stages: {list(STAGES)}")
    paths = [config_paths] if isinstance(config_paths, str | Path) else list(config_paths)
    if not paths:
        raise ValueError("run needs at least one config")
    cfgs = [load_config(path) for path in paths]
    entities = _entities(cfgs, entity)
    env = load_environment(env_path)
    spark = get_spark_session(env)
    out: dict[str, dict] = {}
    for name in entities:
        out[name] = {}
        for stage in stages:
            print(f"run {stage} for {name}")
            out[name][stage] = STAGES[stage](cfgs, name, env, spark)
    return out
