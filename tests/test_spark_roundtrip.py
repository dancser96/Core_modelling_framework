"""Local Spark reads what pandas writes: the path every synthetic mart takes (T15, T18)."""

import datetime as dt
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyspark.sql import SparkSession


def test_month_partitioned_parquet_roundtrip(spark: SparkSession, tmp_path: Path) -> None:
    """Types and nulls survive pandas → parquet (partitioned by period) → Spark → pandas."""
    jan, feb = dt.date(2025, 1, 1), dt.date(2025, 2, 1)
    frame = pd.DataFrame(
        {
            "client_id": pd.array([1, 2, 3, 4], dtype="int64"),
            # Partition column: Spark infers `date` from the folder name; a timestamp here would
            # silently become a string.
            "snapshot_month": [jan, jan, feb, feb],
            "event_date": [jan, None, feb, feb],  # a date inside the file, not a timestamp (T18)
            "login_cnt": pd.array([0, 5, None, 2], dtype="Int64"),
            "casa_bal": [0.0, 1234.5, np.nan, 1e9],
            "segment": ["PSB", None, "Private", "Priority"],
            "has_cc": [True, None, True, False],
        }
    )
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_to_dataset(table, str(tmp_path), partition_cols=["snapshot_month"])

    sdf = spark.read.parquet(str(tmp_path))
    back = sdf.toPandas().sort_values("client_id").reset_index(drop=True)

    assert dict(sdf.dtypes) == {
        "client_id": "bigint",
        "login_cnt": "bigint",
        "casa_bal": "double",
        "segment": "string",
        "has_cc": "boolean",
        "event_date": "date",
        "snapshot_month": "date",
    }
    # Back in pandas, an integer column with nulls becomes float64 and dates are datetime.date.
    expected = frame.assign(login_cnt=[0.0, 5.0, np.nan, 2.0])
    pd.testing.assert_frame_equal(back[frame.columns], expected)


def test_flaml_imports_after_core_modelling() -> None:
    """The numpy compat shim lets flaml (and pandas-on-Spark) import on numpy 2."""
    # A fresh interpreter, so an import made earlier in this test run can't hide the failure (T1).
    code = "import core_modelling, flaml"
    subprocess.run([sys.executable, "-c", code], check=True)
