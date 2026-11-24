"""The scores table: Evaluation's one scoring pass (evaluation.md → "Scoring and the scores
table"), committed whole with the stage's other artifacts.

`score_parts` scores the evaluation rows inside Spark through `score_spark` and keeps, beside
the scores, what the tables read later: the client's split, the target, the strata and the
baselines' columns, named by the caller and never found by a prefix, so a re-render or
`compare_runs` reads the stored scores alone. The test part's rows with a null target are
scored and kept too: the drift reference describes every eligible test row, while every metric
reads the rows with a known target only. `write_scores` writes them as parquet from Spark
beside the stage's folder; Evaluation reads them back for every cell (`cells.py`) and never
scores twice, and `write_stage` moves them into the stage's folder with its other artifacts.
"""

import secrets
import shutil

from pyspark.sql import DataFrame

from core_modelling.artifacts import local_path
from core_modelling.config import UseCaseConfig
from core_modelling.model.bundle import OUTPUT_COLUMNS, Bundle
from core_modelling.model.scoring import score_spark
from core_modelling.sources import KEYS

BASELINE_PREFIX = "baseline_"  # how `add_baselines` names a ranking baseline's column
SCORES_FOLDER = "scores"  # the scores table's folder in the stage's, and its staging suffix


def score_parts(
    bundle_folder: str, bundle: Bundle, rows: DataFrame, cfg: UseCaseConfig, baselines: list[str]
) -> DataFrame:
    """The evaluation rows scored inside Spark, one row per client, period and part, never
    collected. Receives the bundle (loaded once by the caller) and its folder, which
    `score_spark` ships, and `build_frames(…, "evaluation")`'s rows with `add_baselines`'
    columns, named in `baselines`; returns the scores table's columns: `unit_id, period, part,
    split, target`, `OUTPUT_COLUMNS`, the strata, then `baselines`. Rows whose features are not
    the bundle's (a feature it lacks, or a column that is no key, stratum or baseline), a
    baseline named like a feature or a kept column, or a bundle of another task, are refused
    before Spark runs."""
    if bundle.task != cfg.task:
        raise ValueError(
            f"the bundle at {bundle_folder} is a {bundle.task} model; the config's task is "
            f"{cfg.task}"
        )
    _check_features(bundle_folder, rows, bundle.features, cfg, baselines)
    strata = cfg.strata.variables
    keep = [*KEYS, "part", "split", "target", *strata, *baselines]
    scored = score_spark(bundle_folder, rows, keep)
    return scored.select(*KEYS, "part", "split", "target", *OUTPUT_COLUMNS, *strata, *baselines)


def _check_features(
    folder: str, rows: DataFrame, features: list[str], cfg: UseCaseConfig, baselines: list[str]
) -> None:
    """Fail loud, naming the difference, on a baseline named like a bundle feature or a column
    the scores keep anyway, and when the rows' features are not the bundle's: a bundle feature
    the rows lack, or a column the rows hold that is no feature of the bundle, no key, `part`,
    `target`, `split`, stratum or baseline (a carried column that `add_baselines` did not
    replace counts as a feature the bundle lacks)."""
    riding = {*KEYS, "part", "target", "split", *cfg.strata.variables}
    clashing = [name for name in baselines if name in riding or name in features]
    if clashing:
        raise ValueError(
            f"the baselines {clashing} are named like a feature of the bundle at {folder} or a "
            "column the scores keep anyway"
        )
    lacking = [name for name in features if name not in rows.columns]
    extra = [
        name for name in rows.columns if name not in {*riding, *baselines} and name not in features
    ]
    if lacking or extra:
        raise ValueError(
            f"the rows' features differ from the bundle's at {folder}: the rows lack {lacking} "
            f"and hold {extra}, which the bundle lacks; build the evaluation frames with the "
            "bundle's features (`Bundle.features`), never the feature set in force now"
        )


def write_scores(scores: DataFrame, stage_folder: str) -> str:
    """The scores table as parquet, written by Spark beside the stage's folder as
    `<stage_folder>.scores-<token>` (a random token, as `artifacts.py`'s siblings, so two
    sessions or hosts never meet), which it returns; never overwritten. A failed or interrupted
    write removes what it staged and re-raises, so only a killed process leaves a `.scores-*`
    folder, which `run_evaluation` refuses before any Spark work (`check_siblings`). The stage
    commits the table whole with its other artifacts, so `run_evaluation`:

    1. writes it: `staged = write_scores(scores, evaluation_folder)`;
    2. reads it back with `spark.read.parquet(staged)` for every `score_edges` and
       `score_cells`, so nothing is scored twice;
    3. ends with `write_stage(result, evaluation_folder, "evaluation", texts,
       folders={"scores": staged})`, which moves it in as `scores/` before the swap.
    """
    target = local_path(stage_folder)
    staged = target.with_name(f"{target.name}.{SCORES_FOLDER}-{secrets.token_hex(6)}")
    if staged.exists():  # the cleanup below must never remove a folder this call did not write
        raise ValueError(
            f"{staged} is left from an earlier Evaluation that did not finish; look at it and "
            "remove it before rerunning"
        )
    try:
        scores.write.mode("errorifexists").parquet(str(staged))
    except BaseException:
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return str(staged)
