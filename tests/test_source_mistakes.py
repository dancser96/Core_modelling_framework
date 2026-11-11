"""Mistake tests: the acceptance list for the source guardrails (test_harness.md, To-do item 2).

Each test takes the unit preset's clean feature-store extract (`fs_extract`), plants one mistake
in it with pandas, writes it to parquet as a new logical source beside the mart and shows what
the framework does: the guardrail refuses it naming the source; the join only prints it (the
matched share, `other days`); the left join accepts it by design (missing periods leave nulls);
or, for a padded id, nothing catches it beyond a lower matched share (a documented gap).
Source-level mistakes are read with `read_keyed_source` alone; join-level ones build the panel
with `load_panel`, on real local Spark.
"""

import re
from collections.abc import Callable
from datetime import date
from functools import partial
from pathlib import Path

import pandas as pd
import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import SourceEntry, SourceKeys
from core_modelling.dataset.panel import load_panel
from core_modelling.environment import EnvironmentConfig, Source
from core_modelling.sources import read_keyed_source
from synthetic.output import read_output

NAME = "planted"  # the logical name of the extract with a mistake in it
OWN_KEYS = {"unit_id": "customer_no", "period": "as_of_date"}
ENTRY = SourceEntry(source=NAME, keys=SourceKeys(**OWN_KEYS))
VALIDATION_DAY = date(2025, 11, 30)  # cc_acquisition's validation period at its last day
WEEK_DAYS = (3, 10, 17, 24)  # weekly rows inside each month, none its first or last day
COMPARED = ["app_sessions_30d", "bureau_score"]  # extract columns checked in the panel


def _planted_env(
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    tmp_path: Path,
    plant: Callable[[pd.DataFrame], pd.DataFrame],
) -> EnvironmentConfig:
    """`unit_env` plus the clean extract with `plant` applied, written to parquet as `NAME`."""
    folder = tmp_path / NAME
    folder.mkdir()
    plant(read_output(unit_output[0], "fs_extract")).to_parquet(folder / "part-0.parquet")
    sources = {**unit_env.sources["entity_a"], NAME: Source(format="parquet", path=str(folder))}
    return unit_env.model_copy(update={"sources": {"entity_a": sources}})


def _joined(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """`cc_acquisition` joining the planted extract (with its own key names) after the mart."""
    features = ["retail_mart", {"source": NAME, "keys": OWN_KEYS}]
    return variant(entities={"entity_a": {"sources": {"features": features}}})


def _matched_share(out: str, name: str) -> float:
    """The matched share the join line of source `name` printed, as a fraction."""
    return float(re.search(rf"join {name} .*?: ([\d.]+)% of the spine", out).group(1)) / 100


def _repeat(frame: pd.DataFrame) -> pd.DataFrame:
    """Every row twice."""
    return pd.concat([frame, frame], ignore_index=True)


def _weekly(frame: pd.DataFrame) -> pd.DataFrame:
    """Each month's row repeated on four days inside the month, as a weekly table would be."""
    weeks = [frame.assign(as_of_date=frame.as_of_date.map(lambda d, k=k: d.replace(day=k)))
             for k in WEEK_DAYS]  # fmt: skip
    return pd.concat(weeks, ignore_index=True)


def _null_ids(frame: pd.DataFrame) -> pd.DataFrame:
    """A few rows without an id."""
    return frame.assign(customer_no=frame.customer_no.where(frame.index >= 5, None))


def _month_strings(frame: pd.DataFrame) -> pd.DataFrame:
    """The period as a `YYYY-MM` string."""
    return frame.assign(as_of_date=frame.as_of_date.map(lambda d: d.strftime("%Y-%m")))


def _keep(frame: pd.DataFrame) -> pd.DataFrame:
    """The clean extract, unchanged."""
    return frame


def _rename_bureau_score(frame: pd.DataFrame, to: str) -> pd.DataFrame:
    """`bureau_score` renamed `to`."""
    return frame.rename(columns={"bureau_score": to})


def _other_ids(frame: pd.DataFrame) -> pd.DataFrame:
    """Ids from another system: every id shifted by 10**9."""
    return frame.assign(customer_no=(frame.customer_no.astype("int64") + 10**9).astype(str))


def _on_the_15th(frame: pd.DataFrame) -> pd.DataFrame:
    """Periods tagged on each month's 15th."""
    return frame.assign(as_of_date=frame.as_of_date.map(lambda d: d.replace(day=15)))


def _without_validation(frame: pd.DataFrame) -> pd.DataFrame:
    """The validation period's rows dropped."""
    return frame[frame.as_of_date != VALIDATION_DAY]


def _half_padded(frame: pd.DataFrame) -> pd.DataFrame:
    """The even ids zero-padded (`000123`), the odd ones left as they are."""
    ids = frame.customer_no
    return frame.assign(customer_no=ids.where(ids.astype("int64") % 2 == 1, "000" + ids))


@pytest.mark.parametrize(
    ("entry", "plant", "error", "message"),
    [
        (NAME, _keep, ValueError, r"no key column \['client_id', 'snapshot_month'\]"),
        (ENTRY, _repeat, ValueError, r"duplicate \(unit_id, period\) keys .*\)$"),
        (ENTRY, _weekly, ValueError, r"duplicate \(unit_id, period\) keys .*finer period"),
        (ENTRY, _null_ids, ValueError, "has rows with a null unit id"),
        (ENTRY, _month_strings, TypeError, "'as_of_date' is string, not a date or timestamp"),
    ],
    ids=["plain_name", "repeated_rows", "weekly_rows", "null_ids", "period_string"],
)
def test_source_mistake_is_refused_naming_the_source(
    spark: SparkSession,
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    tmp_path: Path,
    entry: str | SourceEntry,
    plant: Callable[[pd.DataFrame], pd.DataFrame],
    error: type[Exception],
    message: str,
) -> None:
    """Undeclared key names, repeated rows, weekly rows (with the finer-period hint, which plain
    repeats lack), null ids and a string period each fail at read, naming the source."""
    env = _planted_env(unit_output, unit_env, tmp_path, plant)
    with pytest.raises(error, match=rf"source '{NAME}'.*{message}"):
        read_keyed_source(cc_config, "entity_a", entry, env, spark)


@pytest.mark.parametrize(
    ("renamed", "shown"),
    [("income", r"\['income'\]"), ("Income", r"\['Income \(as income\)'\]")],
)
def test_column_shared_with_the_mart_is_refused(
    spark: SparkSession,
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
    renamed: str,
    shown: str,
) -> None:
    """An extract column renamed to the mart's `income`, or to `Income` (case only), fails the
    join naming the source and, for the case clash, both spellings."""
    plant = partial(_rename_bureau_score, to=renamed)
    env = _planted_env(unit_output, unit_env, tmp_path, plant)
    with pytest.raises(ValueError, match=rf"'{NAME}' shares the columns {shown} with an earlier"):
        load_panel([_joined(variant)], "entity_a", env, spark)


def test_other_id_system_is_refused_naming_both_id_types(
    spark: SparkSession,
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
) -> None:
    """Ids from another system (every id shifted by 10**9) match no spine row: refused naming
    the source and both raw id types."""
    env = _planted_env(unit_output, unit_env, tmp_path, _other_ids)
    with pytest.raises(
        ValueError, match=rf"'{NAME}' matched no spine row: .* its id is string, the spine's bigint"
    ):
        load_panel([_joined(variant)], "entity_a", env, spark)


def test_clean_extract_joins_its_string_id_and_prints_its_share(
    spark: SparkSession,
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The clean extract matches about 85% of the spine's rows, and a covered client's row
    carries its values: the extract's string id joined the mart's integer one."""
    panel, _, _ = load_panel([cc_config], "entity_a", unit_env, spark)
    assert 0.80 <= _matched_share(capsys.readouterr().out, "retail_fs_extract") <= 0.90
    extract = read_output(unit_output[0], "fs_extract")
    known = extract[extract.as_of_date == VALIDATION_DAY]
    row = known.iloc[0]
    key = (F.col("unit_id") == row.customer_no) & (F.col("period") == VALIDATION_DAY)
    joined = panel.where(key).select(COMPARED).collect()
    assert [tuple(r) for r in joined] == [tuple(row[COMPARED])]


def test_periods_on_the_15th_join_and_print_other_days(
    spark: SparkSession,
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Periods tagged on each month's 15th join as their month; the join line says so."""
    env = _planted_env(unit_output, unit_env, tmp_path, _on_the_15th)
    load_panel([_joined(variant)], "entity_a", env, spark)
    out = capsys.readouterr().out
    assert f"join {NAME} (joined, other days periods, keyed on customer_no, as_of_date)" in out
    assert 0.80 <= _matched_share(out, NAME) <= 0.90


def test_missing_validation_period_is_accepted_with_nulls_there_only(
    spark: SparkSession,
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """By design (the EDS, 2026-10-30) the left join takes an extract without the validation
    period: its columns are null in that period and only there, and the missing period is
    printed by name."""
    env = _planted_env(unit_output, unit_env, tmp_path, _without_validation)
    panel, _, _ = load_panel([_joined(variant)], "entity_a", env, spark)
    out = capsys.readouterr().out
    label = VALIDATION_DAY.strftime("%Y-%m")
    assert f"source '{NAME}' has no rows in ['{label}']" in out and "null there" in out
    counts = panel.groupBy("period").agg(F.count("bureau_score").alias("known")).collect()
    empty = [row.period for row in counts if row.known == 0]
    assert empty == [VALIDATION_DAY] and len(counts) > 1


def test_padded_ids_are_not_caught_beyond_a_lower_matched_share(
    spark: SparkSession,
    unit_output: tuple[str, dict],
    unit_env: EnvironmentConfig,
    variant: Callable[..., UseCaseConfig],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Documents a gap: half the clients' ids zero-padded (`000123`) raise nothing; only the
    printed matched share drops to about half of the clean extract's (~85%)."""
    env = _planted_env(unit_output, unit_env, tmp_path, _half_padded)
    load_panel([_joined(variant)], "entity_a", env, spark)
    assert 0.35 <= _matched_share(capsys.readouterr().out, NAME) <= 0.50
