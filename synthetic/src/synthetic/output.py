"""Writing a synthetic dataset to disk and reading it back.

`write_mart` drives the month loop (`generate`) and writes each month as it comes, so memory holds
about one month: `<out>/mart/snapshot_month=YYYY-MM-01/part-0.parquet`, the oracle likewise under
`<out>/oracle/`, and `<out>/truth.json` last, so a folder without a truth file is an incomplete
dataset. The month is a partition column, never stored inside the files; Spark infers it as a date
from the folder name (T18). The mart is written with the explicit types of `mart.arrow_schema`
(flags int32, counts int64 with nulls where nullable, `cc_limit` decimal(18, 2)), so every month
has the same schema whatever its values; the oracle keeps the types pandas gives it. `read_output`
reads a table back in month order with `snapshot_month` as `datetime.date` values and decimals as
floats, so it returns the mart as it was in memory (Spark sees the decimal); `load_truth` refuses
a dataset written by another generator version, so stale data fails loud.
"""

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from synthetic import __version__
from synthetic.dirty import dirty_panel
from synthetic.generate import advance_simulation, finish_simulation, start_simulation
from synthetic.mart import arrow_schema
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
    With `dirty` on, the defects are planted in the whole panel (`dirty.dirty_panel`), so every
    month is held until the end (small presets).
    """
    out = Path(out_dir)
    existing = [name for name in (*TABLES, "truth.json") if (out / name).exists()]
    if existing:
        raise FileExistsError(f"{out} already holds {existing}; write into an empty folder")
    sim = start_simulation(preset, n_clients, seed, n_months, n_extra_columns)
    products = list(sim["spec"]["products"])
    held = []
    while sim["month"] < sim["last_month"]:
        sim, final = advance_simulation(sim)
        if dirty:
            held += final
        else:
            _write_months(out, final, products)
    final = held + finish_simulation(sim)
    if dirty:
        sim, final = dirty_panel(sim, final)
    _write_months(out, final, products)
    truth = build_truth(sim)
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def read_output(
    out_dir: str, table: str, columns: list[str] | None = None, client_sample: int | None = None
) -> pd.DataFrame:
    """One table ("mart" or "oracle") in month order, with `snapshot_month` as dates.

    `columns` reads only those (in that order); None reads every column, keys first.
    `client_sample` n keeps only the clients whose id is a multiple of n, in every month: a fixed
    sample of about 1/n of the clients, for checks that read every column of a large dataset.
    """
    if table not in TABLES:
        raise ValueError(f"table must be one of {TABLES}, not {table!r}")
    folders = sorted(Path(out_dir, table).glob(f"{PARTITION}=*"))
    if not folders:
        raise FileNotFoundError(f"no months in {Path(out_dir, table)}")
    stored = None if columns is None else [c for c in columns if c != PARTITION]
    parts = [_read_month(folder / "part-0.parquet", stored, client_sample) for folder in folders]
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


def _read_month(path: Path, columns: list[str] | None, client_sample: int | None) -> pa.Table:
    """One month's file, decimals cast to float64 (pandas would get Python `Decimal` objects),
    optionally only the clients whose id is a multiple of `client_sample`."""
    # No partition inference: `read_output` adds the month as a date, not as pyarrow's guess.
    part = pq.read_table(path, columns=columns, partitioning=None)
    if client_sample is not None:
        ids = pq.read_table(path, columns=["client_id"]).column("client_id").to_numpy()
        part = part.filter(pa.array(ids % client_sample == 0))
    fields = [
        pa.field(f.name, pa.float64()) if pa.types.is_decimal(f.type) else f for f in part.schema
    ]
    return part.cast(pa.schema(fields, metadata=part.schema.metadata))


def _write_months(
    out: Path, frames: list[tuple[pd.DataFrame, pd.DataFrame]], products: list[str]
) -> None:
    """Write each (mart, oracle) month into its partition folder of each table; the mart with
    its explicit schema (`products`: the spec's product keys, to parse the column names)."""
    for frame_pair in frames:
        for table, frame in zip(TABLES, frame_pair, strict=True):
            months = frame[PARTITION].unique()
            if len(months) != 1:
                raise ValueError(f"a {table} frame must hold one month, not {len(months)}")
            folder = out / table / f"{PARTITION}={months[0].isoformat()}"
            folder.mkdir(parents=True)  # an existing folder raises: a month written twice
            stored = pa.Table.from_pandas(frame.drop(columns=PARTITION), preserve_index=False)
            if table == "mart":
                schema = arrow_schema(stored.column_names, products)
                # The pandas metadata stays, so the mart reads back with its in-memory dtypes.
                stored = stored.cast(schema.with_metadata(stored.schema.metadata))
            pq.write_table(stored, folder / "part-0.parquet")


def _folder_month(folder: Path) -> dt.date:
    """The month of a partition folder (`snapshot_month=YYYY-MM-01`)."""
    return dt.date.fromisoformat(folder.name.removeprefix(f"{PARTITION}="))
