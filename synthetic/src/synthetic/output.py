"""Writing a synthetic dataset to disk and reading it back.

`write_mart` drives the month loop (`generate`) and writes each month as it comes, so memory holds
about one month: `<out>/mart/snapshot_month=YYYY-MM-01/part-0.parquet`, the oracle likewise under
`<out>/oracle/`, and `<out>/truth.json` last, so a folder without a truth file is an incomplete
dataset. The truth's oracle part (metrics and relevance rankings) is computed once every month is
on disk and the simulation's state is gone, from the columns it needs read back (one target's at
a time, `oracle.target_columns`, then a 20% client sample for the rankings). The month is a
partition column, never stored inside the files; Spark infers it as a date from the folder name
(T18). The mart is written with the explicit types of `mart.arrow_schema`
(flags int32, counts int64 with nulls where nullable, `cc_limit` decimal(18, 2)), so every month
has the same schema whatever its values; the oracle keeps the types pandas gives it. `read_output`
reads a table back in month order with `snapshot_month` as `datetime.date` values and decimals as
floats, so it returns the mart as it was in memory (Spark sees the decimal); `load_truth` refuses
a dataset written by another generator version or another numpy or scipy minor version (the
seed-to-data mapping depends on them), so stale data fails loud.
"""

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy

from synthetic import __version__
from synthetic.dirty import dirty_panel
from synthetic.generate import advance_simulation, finish_simulation, start_simulation
from synthetic.mart import arrow_schema
from synthetic.oracle import BINARY_TARGETS, METRIC_ORACLE_COLUMNS, target_columns, target_metrics
from synthetic.presets import PRESETS
from synthetic.relevance import SAMPLE_EVERY, relevance_rankings
from synthetic.truth import build_truth, complete_truth, with_oracle

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
    month is held until the end, so it is refused above the unit preset's size (clients ×
    months); the oracle part comes from the clean panel.
    """
    out = Path(out_dir)
    existing = [name for name in (*TABLES, "truth.json") if (out / name).exists()]
    if existing:
        raise FileExistsError(f"{out} already holds {existing}; write into an empty folder")
    if dirty:
        _check_dirty_size(preset, n_clients, n_months)
    sim = start_simulation(preset, n_clients, seed, n_months, n_extra_columns)
    if dirty:
        truth = _write_dirty(out, sim)
    else:
        truth = _write_clean(out, sim)
        del sim  # the starting book's state; the oracle part reads the written months instead
        truth = _with_written_oracle(out_dir, truth)
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def _check_dirty_size(preset: str, n_clients: int | None, n_months: int | None) -> None:
    """Raise if a dirty dataset would be larger than the unit preset (clients × months): dirty
    data holds the whole panel in memory."""
    size, unit = PRESETS[preset], PRESETS["unit"]
    clients = size["n_clients"] if n_clients is None else n_clients
    months = size["n_months"] if n_months is None else n_months
    if clients * months > unit["n_clients"] * unit["n_months"]:
        raise ValueError(
            f"dirty data holds the whole panel in memory: {clients:,} clients × {months} months "
            f"is larger than the unit preset ({unit['n_clients']:,} × {unit['n_months']})"
        )


def _write_clean(out: Path, sim: dict) -> dict:
    """Run the month loop, writing each month as it becomes final; the truth without its oracle
    part (the simulation's state is freed on return)."""
    products = list(sim["spec"]["products"])
    columns = None
    while sim["month"] < sim["last_month"]:
        sim, final = advance_simulation(sim)
        _write_months(out, final, products)
        if columns is None and final:
            columns = list(final[0][0].columns)
    final = finish_simulation(sim)
    _write_months(out, final, products)
    if columns is None and final:
        columns = list(final[0][0].columns)
    if columns is None:
        raise ValueError("the simulation wrote no panel month")
    return build_truth(sim, columns)


def _write_dirty(out: Path, sim: dict) -> dict:
    """Run the month loop holding every month, plant the defects and write the panel; the full
    truth, its oracle part from the clean panel."""
    frames = []
    while sim["month"] < sim["last_month"]:
        sim, final = advance_simulation(sim)
        frames += final
    frames += finish_simulation(sim)
    sim, planted = dirty_panel(sim, frames)
    _write_months(out, planted, list(sim["spec"]["products"]))
    clean = [pd.concat([pair[i] for pair in frames], ignore_index=True) for i in (0, 1)]
    return complete_truth(sim, *clean)


def _with_written_oracle(out_dir: str, truth: dict) -> dict:
    """The truth with its oracle part, from the written months: each target's metrics from the
    columns it needs, then the relevance rankings from every column of the 20% client sample."""
    metrics = {}
    for target in BINARY_TARGETS:  # one target's columns at a time bounds the memory
        mart_columns, oracle_columns = target_columns(target)
        mart = read_output(out_dir, "mart", mart_columns)
        oracle = read_output(out_dir, "oracle", oracle_columns)
        metrics[target] = target_metrics(mart, oracle, truth, target)
    mart = read_output(out_dir, "mart", client_sample=SAMPLE_EVERY)
    oracle = read_output(out_dir, "oracle", METRIC_ORACLE_COLUMNS, SAMPLE_EVERY)
    return with_oracle(truth, metrics, relevance_rankings(mart, oracle, truth))


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
    """The dataset's truth.json; raises if another generator version, or another numpy or scipy
    major.minor version, wrote it (stale data: the seed-to-data mapping depends on them)."""
    truth = json.loads(Path(out_dir, "truth.json").read_text())
    if truth["generator_version"] != __version__:
        raise ValueError(
            f"{out_dir} was written by synthetic {truth['generator_version']}, this is "
            f"{__version__}: generate it again"
        )
    for name, installed in (("numpy", np.__version__), ("scipy", scipy.__version__)):
        written = truth["versions"][name]
        if _major_minor(written) != _major_minor(installed):
            raise ValueError(
                f"{out_dir} was written with {name} {written}, this is {installed}: the "
                "seed-to-data mapping may differ, generate it again"
            )
    return truth


def _major_minor(version: str) -> str:
    """A version's major.minor part (`2.3.5` → `2.3`)."""
    return ".".join(version.split(".")[:2])


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
