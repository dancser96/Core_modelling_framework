"""`run`: the stages of a use case from a config, in order (D-024).

`STAGES` maps a stage name to the function that runs it for one entity; `run` loads the config
and the environment, opens the Spark session and runs the asked stages for the asked entities.
Stage 1 has one stage: Target Factory, whose summary is printed and whose model input is saved
when the config names one (D-131). The later stages take the resolved config (the audit log
replayed, D-125) and arrive with M2.2–M2.4.
"""

from collections.abc import Callable
from pathlib import Path

from pyspark.sql import SparkSession

from core_modelling.config import UseCaseConfig, load_config
from core_modelling.dataset import save_model_input
from core_modelling.environment import EnvironmentConfig, get_spark_session, load_environment
from core_modelling.target_factory import run_target_factory

Stage = Callable[[UseCaseConfig, str, EnvironmentConfig, SparkSession], dict]


def _run_target_factory_stage(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> dict:
    """The target summary, then the model input saved when the config names one."""
    out = {"summary": run_target_factory(cfg, entity, env, spark)}
    if cfg.data.model_input is not None:
        out["model_input"] = save_model_input(cfg, entity, env, spark)
    return out


STAGES: dict[str, Stage] = {"target_factory": _run_target_factory_stage}


def run(
    config_path: str | Path,
    env_path: str | None = None,
    stages: list[str] | None = None,
    entity: str | None = None,
) -> dict:
    """The stages (default: all built) for the entities of the config (default: all it lists),
    in order; per entity and stage, what the stage returned."""
    stages = list(stages or STAGES)
    unknown = [stage for stage in stages if stage not in STAGES]
    if unknown:
        raise ValueError(f"unknown stages {unknown}; the built stages: {list(STAGES)}")
    cfg = load_config(config_path)
    env = load_environment(env_path)
    entities = [entity] if entity else list(cfg.entities)
    if entity is not None and entity not in cfg.entities:
        raise ValueError(f"unknown entity {entity!r}: the config has {sorted(cfg.entities)}")
    spark = get_spark_session(env)
    out: dict[str, dict] = {}
    for name in entities:
        out[name] = {}
        for stage in stages:
            print(f"run {stage} for {name}")
            out[name][stage] = STAGES[stage](cfg, name, env, spark)
    return out
