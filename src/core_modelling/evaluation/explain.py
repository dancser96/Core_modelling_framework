"""Evaluation's explanation tables (evaluation.md → "The explanation tables").

The driver holds one set of rows here, `collect_explanation_sample`'s: up to `PERMUTATION_ROWS`
test rows chosen by a seeded hash of the keys, with their raw feature values and scores, plus
the three waterfall rows, one of them at the score `explanation_cut` reads off the slices
table. The first `EXPLANATION_ROWS` of them in hash order are the explanation sample (marked
`sampled`); all of them, the permutation sample (`permutation.py`). Everything else reads those
rows, or Spark aggregates: the families' own contributions on the encoder's codes
(`compute_contributions`, in the shape of Training's `explanation_sample`, so the importance
view puts train out of fold beside test), the encoder's null and unseen shares per part
(`encoding_shares`), the feature table and partial dependence with ICE. Every statistic reads
the sampled rows only (`sampled_rows`): the waterfall rows are picked by hand, so they are drawn
but never counted. Nothing is fitted and nothing is chosen on these numbers (`CLAUDE.md` §4.4,
§4.5); validation appears only in the shares, which are reported. The contributions are on the
margin's scale (the log scale for Tweedie and Poisson).
"""

from collections.abc import Iterator
from functools import reduce
from operator import and_

import numpy as np
import pandas as pd
from pyspark.sql import Column, DataFrame, Row
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, LongType, StringType, StructField, StructType

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import Slices
from core_modelling.dataset.frames import collect_frame
from core_modelling.environment import EnvironmentConfig
from core_modelling.evaluation.permutation import PERMUTATION_ROWS
from core_modelling.evaluation.slices import decision_slice
from core_modelling.model.bundle import OUTPUT_COLUMNS, Bundle
from core_modelling.model.encoder import encode_frame
from core_modelling.model.families import FAMILIES
from core_modelling.model.scoring import score_frame
from core_modelling.run_artifacts import BASE_COLUMN, CONTRIBUTION_SUFFIX, EXPLANATION_ROWS
from core_modelling.sources import KEYS
from core_modelling.statistics.distributions import level_text
from core_modelling.statistics.metrics import curve_at_depths, slice_labels
from core_modelling.statistics.score_cells import PARTS, POOLED

WATERFALL_COLUMN = "waterfall"  # null for a sampled row, else which waterfall row it is
SAMPLED_COLUMN = "sampled"  # true on the explanation sample's hashed rows, which are counted
ORDER, HASHED = "sample_order", "hashed"  # the collect's own columns, dropped on the driver
# The cut without a usable decision slice: a capture depth, so always cut, named as the slices
# table names it
FALLBACK_SLICE = slice_labels(Slices(top_pct=[0.1]))[0]
# A float32 library (XGBoost) sums its contributions to the margin within rounding only
SUM_TOLERANCE = 1e-4
GRID_POINTS = 20  # partial dependence: quantiles of a numeric, the most frequent levels
ICE_ROWS = 50  # ICE lines drawn, evenly spaced through the sample
PDP_COLUMNS = ["feature", "curve", "row", "point", "value", "level", "score"]
ALL_NULL = "null on every sample row"  # partial dependence's reason for a feature it leaves out
SHARE_SCHEMA = StructType(
    [
        StructField("part", StringType()),
        StructField("feature", StringType()),
        StructField("rows", LongType()),
        StructField("nulls", DoubleType()),
        StructField("unseen", DoubleType()),
    ]
)


def explanation_cut(slices: pd.DataFrame, curves: pd.DataFrame, cfg: UseCaseConfig) -> dict:
    """Where the explanation sample's `cut` row is taken: the decision's slice (`decision_slice`)
    on the test part, pooled over its periods, or `FALLBACK_SLICE` when no slice is configured
    or its row is unavailable; a configured slice without a row fails loud. Returns `slice`,
    `available` (False on the fallback), `reason` (why it fell back, else ''), `depth` (the
    slice's rows over the part's) and `score`, the lowest score of the first score bin of the
    test curve that reaches the depth (`curve_at_depths`)."""
    test = slices.loc[(slices["part"] == "test") & (slices["period"] == POOLED)]
    chosen = decision_slice(cfg)
    label = None if chosen is None else slice_labels(chosen)[0]
    reason = "no slice is configured" if label is None else ""
    if label is not None:
        row = test.loc[test["slice"] == label]
        if row.empty:
            raise ValueError(f"the test slices hold no row for the decision's slice {label!r}")
        if row["unavailable"].iloc[0]:
            reason = f"the decision's slice {label} is {row['unavailable'].iloc[0]}"
    if reason:
        row = test.loc[test["slice"] == FALLBACK_SLICE]
        if row.empty:
            raise ValueError(f"the test slices hold no row for {FALLBACK_SLICE!r}")
    depth = float(row["rows"].iloc[0] / row["part_rows"].iloc[0])
    at = curve_at_depths(curves.loc[curves["part"] == "test"], [depth])
    return {"slice": row["slice"].iloc[0], "available": not reason, "reason": reason,
            "depth": depth, "score": float(at["threshold"].iloc[0])}  # fmt: skip


def collect_explanation_sample(
    rows: DataFrame, scores: DataFrame, cfg: UseCaseConfig, env: EnvironmentConfig, cut: float
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The explanation and permutation samples of the test part, from one collect: the first
    `PERMUTATION_ROWS` test rows (every one, when fewer) in the order of a hash of the keys and
    `training.seed` (so a rerun takes the same rows), plus the three waterfall rows.

    Receives Evaluation's rows (one per client, period and part, with the features) and the
    scores table; `cut` is the score at the decision's cut, which only the slices table knows.
    The rows are picked on the scores alone (`_chosen_rows`), and `rows` is read only to join
    the features to those keys. Returns, each one row per client and period:

    - the explanation sample: the first `EXPLANATION_ROWS` hashed rows (`sampled` true) and the
      waterfall rows, with `rows`' columns, `OUTPUT_COLUMNS`, `waterfall` (`highest`: the top
      score of the part; `cut`: the score nearest `cut`; `typical`: the sampled row nearest the
      sampled rows' median score; else null) and `sampled`;
    - the permutation sample: every hashed row, with `rows`' columns;
    - the collect's log entry (`collect_frame`'s).
    """
    chosen, known = _chosen_rows(scores.where(F.col("part") == "test"), cfg, cut)
    picked = rows.where(F.col("part") == "test").join(F.broadcast(chosen), KEYS)
    # a join that lost or doubled a row fails in the collect, against the known count
    collected, entry = collect_frame(picked, "explanation_sample", env, rows=known)
    collected = collected.sort_values([ORDER, *KEYS], ignore_index=True)  # the hash order
    first = collected.index[collected[HASHED].to_numpy()][:EXPLANATION_ROWS]
    collected[SAMPLED_COLUMN] = collected.index.isin(first)
    explanation = collected.loc[collected[SAMPLED_COLUMN] | collected[WATERFALL_COLUMN].notna()]
    explanation = explanation.drop(columns=[ORDER, HASHED]).sort_values(KEYS, ignore_index=True)
    permutation = collected.loc[collected[HASHED], rows.columns]
    return _mark_typical(explanation), permutation.sort_values(KEYS, ignore_index=True), entry


def _chosen_rows(test: DataFrame, cfg: UseCaseConfig, cut: float) -> tuple[DataFrame, int]:
    """The test scores to collect, lazy, and how many: the keys, `OUTPUT_COLUMNS`, the hash
    (`sample_order`), `hashed` (among the first `PERMUTATION_ROWS` by the hash, then the keys)
    and `waterfall` (`highest` or `cut`, else null), on the hashed and the waterfall rows only.
    Three small Spark jobs over the scores: the hashed rows' keys (a top-k, no global sort),
    then each waterfall row; the selection itself is a filter on the last hashed row."""
    order = F.xxhash64(*KEYS, F.lit(cfg.training.seed)).alias(ORDER)
    test = test.select(*KEYS, *OUTPUT_COLUMNS, order)
    hashed = test.select(ORDER, *KEYS).orderBy(ORDER, *KEYS).limit(PERMUTATION_ROWS).collect()
    if not hashed:
        raise ValueError("the test part has no scored row to explain")
    highest = _pick_row(test, [F.col("score").desc(), F.col(ORDER)], [])
    at_cut = _pick_row(test, [F.abs(F.col("score") - F.lit(cut)), F.col(ORDER)], [highest])
    keys = {tuple(row[key] for key in KEYS) for row in hashed}
    extra = sum(tuple(row[key] for key in KEYS) not in keys for row in (highest, at_cut))
    marked = test.select(
        "*",
        _at_or_before(hashed[-1], [ORDER, *KEYS]).alias(HASHED),
        F.when(_is_row(highest), "highest").when(_is_row(at_cut), "cut").alias(WATERFALL_COLUMN),
    )
    chosen = marked.where(F.col(HASHED) | F.col(WATERFALL_COLUMN).isNotNull())
    return chosen, len(hashed) + extra


def _at_or_before(row: Row, columns: list[str]) -> Column:
    """True on the rows at or before `row` in the order of `columns`, compared in turn (no
    value null): the selection a top-k by those columns ends at."""
    head, *rest = columns
    value = F.lit(row[head])
    if not rest:
        return F.col(head) <= value
    return (F.col(head) < value) | ((F.col(head) == value) & _at_or_before(row, rest))


def _pick_row(test: DataFrame, order: list[Column], taken: list[Row]) -> Row:
    """The keys of the first test row in `order`, other than the rows `taken`; an empty part
    fails loud."""
    left = test
    for row in taken:
        left = left.where(~_is_row(row))
    found = left.orderBy(*order).select(*KEYS).first()
    if found is None:
        raise ValueError("the test part has too few rows for the three waterfall rows")
    return found


def _is_row(row: Row) -> Column:
    """True on the row with `row`'s keys, every one of `KEYS`."""
    return reduce(and_, [F.col(key) == F.lit(row[key]) for key in KEYS])


def _mark_typical(sample: pd.DataFrame) -> pd.DataFrame:
    """The sample with its typical row marked: of the sampled rows not marked yet, the one whose
    score is nearest their median (the first in key order on a tie)."""
    free = sample.loc[sample[SAMPLED_COLUMN] & sample[WATERFALL_COLUMN].isna(), "score"]
    if free.empty:
        raise ValueError("the explanation sample holds no sampled row besides the waterfall rows")
    sample.loc[(free - free.median()).abs().idxmin(), WATERFALL_COLUMN] = "typical"
    return sample


def sampled_rows(contributions: pd.DataFrame) -> pd.DataFrame:
    """The explanation sample's hashed rows (`sampled`), the ones every statistic reads: the
    waterfall rows outside them are picked by hand, so they are drawn, never counted."""
    return contributions.loc[contributions[SAMPLED_COLUMN].astype(bool)]


def compute_contributions(bundle: Bundle, sample: pd.DataFrame) -> pd.DataFrame:
    """The family's own contributions on the encoder's codes of `sample` (the explanation
    sample, with its `margin`). Returns the same rows in the shape of Training's
    `explanation_sample`: the keys, the features' raw values, `<feature>__contribution` per
    feature, `base_value`; then the sample's other columns. A row's contributions and base
    value sum to its stored margin, or it fails loud (the rows are not what was scored)."""
    encoded, _ = encode_frame(sample, bundle.encoder)
    values = FAMILIES[bundle.family].contributions(bundle.booster, encoded)
    names = [f"{name}{CONTRIBUTION_SUFFIX}" for name in bundle.features]
    parts = pd.DataFrame(values, index=sample.index, columns=[*names, BASE_COLUMN])
    margin = sample["margin"].to_numpy(dtype=np.float64)
    gap = np.abs(values.sum(axis=1) - margin)
    if (gap > SUM_TOLERANCE * np.maximum(1.0, np.abs(margin))).any():
        raise ValueError(
            f"the contributions differ from the stored margin by up to {gap.max():.3g}: the "
            "sample's feature values are not the ones its scores were computed from"
        )
    front = [*KEYS, *bundle.features]
    rest = [name for name in sample.columns if name not in front]
    return pd.concat([sample[front], parts, sample[rest]], axis=1)


def encoding_shares(rows: DataFrame, bundle: Bundle) -> pd.DataFrame:
    """Per part and feature of the bundle, the rows and the encoder's null and unseen shares
    (an unseen level: one the encoder did not see in train; null for a numeric), in one Spark
    pass. Each partition counts with `encode_frame` itself, so a level is told seen or unseen
    exactly as scoring codes it. Returns `part, feature, rows, null_share, unseen_share`."""
    encoder = bundle.encoder

    def count_batches(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
        """One partition's counts per part and feature, from the encoder's shares."""
        for batch in batches:
            for part, group in batch.groupby("part", sort=False):
                _, shares = encode_frame(group, encoder)
                yield pd.DataFrame(
                    {"part": part, "feature": shares["feature"], "rows": len(group),
                     "nulls": np.rint(shares["null_share"] * len(group)),
                     "unseen": np.rint(shares["unseen_share"] * len(group))}
                )  # fmt: skip

    counted = rows.select("part", *bundle.features).mapInPandas(count_batches, SHARE_SCHEMA)
    sums = [F.sum(name).alias(name) for name in ("rows", "nulls", "unseen")]
    table = counted.groupBy("part", "feature").agg(*sums).toPandas()
    table["null_share"] = table["nulls"] / table["rows"]
    table["unseen_share"] = table["unseen"] / table["rows"]
    position = table["feature"].map({name: index for index, name in enumerate(bundle.features)})
    table = table.assign(position=position).sort_values(["part", "position"])
    return table[["part", "feature", "rows", "null_share", "unseen_share"]].reset_index(drop=True)


def contribution_shares(contributions: pd.DataFrame, features: list[str]) -> pd.Series:
    """Each feature's share of the mean absolute contribution, from a frame with
    `<feature>__contribution` columns; a frame of only zero contributions fails loud."""
    columns = [f"{name}{CONTRIBUTION_SUFFIX}" for name in features]
    missing = [name for name in columns if name not in contributions.columns]
    if missing:
        raise ValueError(f"the contributions lack the columns {missing}")
    mean_abs = contributions[columns].abs().mean().set_axis(features)
    if not mean_abs.sum() > 0:
        raise ValueError("every contribution is 0, so no feature has a share")
    return mean_abs / mean_abs.sum()


def feature_table(
    contributions: pd.DataFrame, shares: pd.DataFrame, run_ledger: pd.DataFrame
) -> pd.DataFrame:
    """One row per final feature (the per-run ledger's `selected`), largest test contribution
    share first: `feature, contribution_share, contribution_rank, null_share_train`, the null
    and unseen shares on test and validation (`encoding_shares`), and `null_not_in_train`, true
    when a feature holds nulls at scoring and none in train. Train's null share is the per-run
    ledger's, the encoder's on the frame the model was fitted on (the Stage 2 copy's is EDA's,
    over every client, test included); a final feature without one fails loud."""
    final = run_ledger.loc[run_ledger["selected"].astype(bool), "feature"].tolist()
    share = contribution_shares(contributions, final)
    table = pd.DataFrame({"feature": final, "contribution_share": share.to_numpy()})
    table["contribution_rank"] = table["contribution_share"].rank(ascending=False, method="min")
    train = run_ledger.set_index("feature")["null_share"]
    table["null_share_train"] = train.reindex(final).to_numpy(dtype=np.float64)
    unknown = table.loc[table["null_share_train"].isna(), "feature"].tolist()
    if unknown:
        raise ValueError(f"the per-run ledger has no train null_share for the features {unknown}")
    wide = shares.set_index(["feature", "part"])[["null_share", "unseen_share"]]
    absent = [(name, part) for name in final for part in PARTS if (name, part) not in wide.index]
    if absent:
        raise ValueError(f"the encoding shares lack the feature and part pairs {absent}")
    for part in PARTS:
        for column in ("null_share", "unseen_share"):
            table[f"{column}_{part}"] = [wide.loc[(name, part), column] for name in final]
    at_scoring = table[[f"null_share_{part}" for part in PARTS]].max(axis=1) > 0
    table["null_not_in_train"] = at_scoring & (table["null_share_train"] == 0)
    table = table.astype({"contribution_rank": "int64"})
    return table.sort_values("contribution_share", ascending=False, kind="stable").reset_index(
        drop=True
    )


def all_null_features(sample: pd.DataFrame, features: list[str]) -> list[str]:
    """The `features` null on every row of `sample`, in order: partial dependence has no grid to
    sweep for them, so it leaves them out with `ALL_NULL` as the reason, decided before it runs
    (D-035)."""
    return [name for name in features if sample[name].isna().all()]


def partial_dependence(bundle: Bundle, sample: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Partial dependence and ICE of each of `features` on the sample's score. Each feature is
    set in turn to every point of its grid on every sample row (numeric: `GRID_POINTS` quantiles
    of its sample values; categorical: its `GRID_POINTS` most frequent sample levels). Returns
    long rows `feature, curve, row, point, value, level, score`: `curve` `pdp` (the mean over
    the rows, `row` null) or `ice` (one of `ICE_ROWS` evenly spaced rows, by position);
    `value` the numeric's grid value, `level` the categorical's level text (`PDP_COLUMNS`; no
    row for no feature). A feature null on every sample row has no grid and fails: leave out
    `all_null_features` first."""
    kinds = {entry["name"]: entry["kind"] for entry in bundle.encoder["features"]}
    unknown = [name for name in features if name not in kinds]
    if unknown:
        raise ValueError(f"the bundle has no features {unknown}")
    if not features:
        return pd.DataFrame(columns=PDP_COLUMNS)
    frame, rows = sample[bundle.features], len(sample)
    ice = np.unique(np.linspace(0, rows - 1, min(ICE_ROWS, rows)).astype(int))
    tables = []
    for name in features:
        numeric = kinds[name] == "numeric"
        grid = _grid(frame[name], numeric, name)
        swept = pd.concat([frame.assign(**{name: value}) for value in grid], ignore_index=True)
        scores = score_frame(bundle, swept)["score"].to_numpy().reshape(len(grid), rows)
        pdp = scores.mean(axis=1)[:, None]
        tables.append(_curve_rows(name, "pdp", grid, numeric, pdp, [None]))
        tables.append(_curve_rows(name, "ice", grid, numeric, scores[:, ice], ice.tolist()))
    return pd.concat(tables, ignore_index=True)


def _curve_rows(
    name: str, curve: str, grid: list, numeric: bool, scores: np.ndarray, rows: list
) -> pd.DataFrame:
    """One curve kind of a feature as long rows: `scores` holds one row per grid point and one
    column per entry of `rows` (the sample positions, or `[None]` for the mean)."""
    points = np.repeat(np.arange(len(grid)), len(rows))
    return pd.DataFrame(
        {
            "feature": name,
            "curve": curve,
            "row": pd.array(rows * len(grid), dtype="Int64"),
            "point": points,
            "value": [float(grid[point]) if numeric else np.nan for point in points],
            "level": [None if numeric else level_text(grid[point]) for point in points],
            "score": scores.ravel(),
        }
    )


def _grid(values: pd.Series, numeric: bool, name: str) -> list:
    """A feature's grid from its sample values, null left out: about `GRID_POINTS` quantiles of
    a numeric, or a categorical's `GRID_POINTS` most frequent raw values (ties by value)."""
    known = values.dropna()
    if known.empty:
        raise ValueError(f"the feature {name!r} is null on every sample row: no grid to sweep")
    if numeric:
        points = np.linspace(0, 1, GRID_POINTS)
        return list(np.unique(np.quantile(known.astype(float), points, method="nearest")))
    counts = known.value_counts().sort_index().sort_values(ascending=False, kind="stable")
    return list(counts.index[:GRID_POINTS])
