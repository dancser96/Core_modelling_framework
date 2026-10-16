"""Writing a synthetic dataset to disk and reading it back.

`write_mart` drives the month loop (`generate`) and writes each month as it comes, so memory holds
about one month: `<out>/mart/snapshot_month=YYYY-MM-01/part-0.parquet`, the oracle likewise under
`<out>/oracle/`, and `<out>/truth.json` last, so a folder without a truth file is an incomplete
dataset. The month is a partition column, never stored inside the files; Spark infers it as a date
from the folder name (T18). `read_output` reads a table back in month order with `snapshot_month`
as `datetime.date` values, as the mart has them in memory; `load_truth` refuses a dataset written
by another generator version, so stale data fails loud. Flags are int32; other columns keep the
types pandas gives them until build stage C adds the explicit arrow schema (decimal `cc_limit`).
"""

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from synthetic import __version__
from synthetic.generate import advance_simulation, finish_simulation, start_simulation
from synthetic.truth import build_truth

TABLES = ("mart", "oracle")
PARTITION = "snapshot_month"


def write_mart(
    out_dir: str,
    preset: str = "canonical",
    n_clients: int | None = None,
    seed: int = 0,
    n_months: int | None = None,
    dirty: bool = False,
    n_extra_columns: int = 0,
) -> dict:
    """Generate month by month, write the partitioned mart, oracle and truth.json; return truth.

    `out_dir` must not hold a dataset already: months left over from another run would mix in.
    """
    if dirty:
        raise NotImplementedError("dirty-data switches are not built yet (test_harness step 5)")
    out = Path(out_dir)
    existing = [name for name in (*TABLES, "truth.json") if (out / name).exists()]
    if existing:
        raise FileExistsError(f"{out} already holds {existing}; write into an empty folder")
    sim = start_simulation(preset, n_clients, seed, n_months, n_extra_columns)
    while sim["month"] < sim["last_month"]:
        sim, final = advance_simulation(sim)
        _write_months(out, final)
    _write_months(out, finish_simulation(sim))
    truth = build_truth(sim)
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def read_output(out_dir: str, table: str, columns: list[str] | None = None) -> pd.DataFrame:
    """One table ("mart" or "oracle") in month order, with `snapshot_month` as dates.

    `columns` reads only those (in that order); None reads every column, keys first.
    """
    if table not in TABLES:
        raise ValueError(f"table must be one of {TABLES}, not {table!r}")
    folders = sorted(Path(out_dir, table).glob(f"{PARTITION}=*"))
    if not folders:
        raise FileNotFoundError(f"no months in {Path(out_dir, table)}")
    stored = None if columns is None else [c for c in columns if c != PARTITION]
    # No partition inference: the month is added as a date below, not as pyarrow's guess.
    parts = [
        pq.read_table(folder / "part-0.parquet", columns=stored, partitioning=None)
        for folder in folders
    ]
    frame = pa.concat_tables(parts).to_pandas()
    # Added in pandas, after pyarrow restored the stored dtypes from the pandas metadata.
    months = np.array([_folder_month(folder) for folder in folders], dtype=object)
    dates = np.repeat(months, [part.num_rows for part in parts])
    frame.insert(min(1, frame.shape[1]), PARTITION, dates)  # keys first: client_id, month
    return frame if columns is None else frame[columns]


def load_truth(out_dir: str) -> dict:
    """The dataset's truth.json; raises if another generator version wrote it (stale data)."""
    truth = json.loads(Path(out_dir, "truth.json").read_text())
    if truth["generator_version"] != __version__:
        raise ValueError(
            f"{out_dir} was written by synthetic {truth['generator_version']}, this is "
            f"{__version__}: generate it again"
        )
    return truth


def _write_months(out: Path, frames: list[tuple[pd.DataFrame, pd.DataFrame]]) -> None:
    """Write each (mart, oracle) month into its partition folder of each table."""
    for frame_pair in frames:
        for table, frame in zip(TABLES, frame_pair, strict=True):
            months = frame[PARTITION].unique()
            if len(months) != 1:
                raise ValueError(f"a {table} frame must hold one month, not {len(months)}")
            folder = out / table / f"{PARTITION}={months[0].isoformat()}"
            folder.mkdir(parents=True)  # an existing folder raises: a month written twice
            stored = pa.Table.from_pandas(frame.drop(columns=PARTITION), preserve_index=False)
            pq.write_table(stored, folder / "part-0.parquet")


def _folder_month(folder: Path) -> dt.date:
    """The month of a partition folder (`snapshot_month=YYYY-MM-01`)."""
    return dt.date.fromisoformat(folder.name.removeprefix(f"{PARTITION}="))
