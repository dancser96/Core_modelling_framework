"""Environment adapter: a logical source read through a mapping file, as `conf/local/` maps it."""

from pathlib import Path

import pytest
import yaml
from pyspark.sql import SparkSession

from core_modelling.environment import _load_sources, _read_source
from synthetic.checks.mart import snapshot_columns
from synthetic.output import read_output


def test_mapped_source_reads_the_written_mart(
    spark: SparkSession, unit_output: tuple[str, dict], tmp_path: Path
) -> None:
    """The unit mart read through a mapping file: every month, every row, the snapshot's columns
    (Spark puts the partition column last) and the written types."""
    out_dir = unit_output[0]
    mapping = tmp_path / "sources.yml"
    mapping.write_text(
        yaml.safe_dump({"retail_mart": {"format": "parquet", "path": f"{out_dir}/mart"}})
    )
    sdf = _read_source(spark, _load_sources(str(mapping))["retail_mart"])
    assert sdf.select("snapshot_month").distinct().count() == 24
    assert sdf.count() == len(read_output(out_dir, "mart", ["client_id"]))
    snapshot = snapshot_columns()
    assert sdf.columns == [c for c in snapshot if c != "snapshot_month"] + ["snapshot_month"]
    types = dict(sdf.dtypes)
    assert {t for c, t in types.items() if c.endswith("_flag")} == {"int"}
    assert (types["cc_limit"], types["snapshot_month"]) == ("decimal(18,2)", "date")


def test_source_mapping_fails_loud(spark: SparkSession, tmp_path: Path) -> None:
    """A missing mapping file, a source without a format, an unknown format and a relative
    parquet path all raise."""
    with pytest.raises(FileNotFoundError):
        _load_sources(str(tmp_path / "missing.yml"))
    mapping = tmp_path / "sources.yml"
    mapping.write_text("retail_mart:\n  path: somewhere\n")
    with pytest.raises(ValueError, match="without a format"):
        _load_sources(str(mapping))
    with pytest.raises(ValueError, match="unknown source format"):
        _read_source(spark, {"format": "csv", "path": "somewhere"})
    with pytest.raises(ValueError, match="must be absolute or a URI"):
        _read_source(spark, {"format": "parquet", "path": "data/01_raw/synthetic_canonical/mart"})
